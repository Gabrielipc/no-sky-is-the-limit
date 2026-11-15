"""DuckDB out-of-core Feature Store over partitioned Parquet (Base + On-Demand Deltas)."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pyarrow as pa
from pyproj import CRS
import pyarrow.parquet as pq

from pipelines import atlas_sources as sources
from pipelines import etl_contract as contract
from pipelines import etl_eligibility as eligibility
from pipelines import etl_extractors as extractors
from pipelines import etl_framing as framing


def eligibility_expression(profile_id: str, climate: bool = True) -> str:
    """Eligibility of each stored window under `profile_id`.

    Rows already gated with that profile keep their stored label (computed in float64
    at extraction); other rows are re-gated in SQL from their stored cover fractions.
    A profile with a cold-climate gate is always re-gated, because the label stored at
    extraction cannot know the global layers. `climate=False` is for queries over
    `base_windows`, which has no global columns.
    """
    profile = eligibility.get_profile(profile_id)
    sql = eligibility.sql_case(profile_id, climate)
    if profile.cold_climate is not None:
        return sql
    return f"CASE WHEN eligibility_profile = '{profile_id}' THEN analog_surface_eligibility ELSE {sql} END"


EARTH_ASSET_CRS_WKT = CRS.from_epsg(4326).to_wkt()


class FeatureStore:
    """Manages reads, atomic batch writes, on-demand delta appends and DuckDB compaction."""

    def __init__(self, root: Path, memory_limit: str = '2GB', threads: int = 4) -> None:
        self.root = Path(root)
        self.memory_limit = memory_limit
        self.threads = threads
        self.spec = contract.load_store_spec()
        self.spill_dir = self.root / self.spec['duckdb_out_of_core']['temp_directory_name']
        for sub in ('base', *(f'enrichment/{e}' for e in contract.ENRICHMENT_SUBSETS), 'manifests', 'manifests/batches'):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def batch_records(self) -> dict[str, dict]:
        bdir = self.root / 'manifests' / 'batches'
        records = {}
        for path in bdir.glob('*.json'):
            try:
                records[path.stem] = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                records[path.stem] = {'status': 'unreadable'}
        return records

    def completed_batch_ids(self, identity: dict | None = None) -> set[str]:
        """Batches to skip on resume: status complete and, if given, the same run identity.

        Records written before statuses and identities existed count as complete with
        `extractors.LEGACY_RUN_IDENTITY`. Incomplete batches are therefore retried.
        """
        done = set()
        for batch_id, meta in self.batch_records().items():
            if meta.get('status', 'complete') != 'complete':
                continue
            if identity is not None and meta.get('identity', extractors.LEGACY_RUN_IDENTITY) != identity:
                continue
            done.add(batch_id)
        return done

    def incomplete_batch_ids(self) -> set[str]:
        return {b for b, m in self.batch_records().items() if m.get('status', 'complete') != 'complete'}

    def batches_with_qa(self, statuses: tuple[str, ...]) -> set[str]:
        """Batch ids whose stored windows include any of `statuses` (e.g. legacy dem_unavailable)."""
        placeholders = ', '.join('?' for _ in statuses)
        with self._connect() as conn:
            return {r[0] for r in conn.execute(
                f'SELECT DISTINCT batch_id FROM base_windows WHERE qa_status IN ({placeholders})', list(statuses)
            ).fetchall()}

    def mark_batch_completed(self, batch_id: str, meta: dict) -> Path:
        bdir = self.root / 'manifests' / 'batches'
        target = bdir / f'{batch_id}.json'
        with TemporaryDirectory(dir=bdir) as tmp:
            staged = Path(tmp) / target.name
            staged.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
            staged.replace(target)
        return target

    def _connect(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect()
        contract.configure_duckdb(conn, self.spill_dir, memory_limit=self.memory_limit, threads=self.threads)
        contract.register_unified_views(conn, self.root)
        return conn

    def _write_manifests(self, manifests: list[dict]) -> None:
        if not manifests:
            return
        # Earth extractors predate the planetary frame: their GLO-30/WorldCover/JRC tiles are EPSG:4326.
        earth = {'crs_wkt': EARTH_ASSET_CRS_WKT, 'planetary_frame': 'EARTH_WGS84'}
        dedup = {}
        for m in manifests:
            enriched = dict(m) if 'planetary_frame' in m else {**earth, **m}
            prov = sources.catalog_provenance(enriched['product_id'])
            if 'doi' not in enriched:
                enriched['doi'] = prov['doi']
            if 'product_version' not in enriched:
                enriched['product_version'] = prov['product_version']
            dedup[(enriched['source_manifest_id'], enriched['asset_id'])] = enriched
        table = contract.validate_table(
            pa.Table.from_pylist(list(dedup.values()), schema=contract.SOURCE_MANIFESTS_SCHEMA),
            'source_manifests',
        )
        mdir = self.root / 'manifests'
        target = mdir / extractors.make_delta_filename('sources')
        with TemporaryDirectory(dir=mdir) as tmp:
            staged = Path(tmp) / target.name
            pq.write_table(table, staged, compression='zstd', compression_level=3)
            staged.replace(target)

    def write_base_batch(self, batch_id: str, rows: list[dict], manifests: list[dict] | None = None) -> list[Path]:
        """Validate and atomically write base_windows partitioned by utm_zone_band."""
        if not rows:
            return []
        table = contract.validate_table(
            pa.Table.from_pylist(rows, schema=contract.BASE_WINDOWS_SCHEMA),
            'base_windows',
        )
        by_band: dict[str, list[int]] = defaultdict(list)
        bands = table['utm_zone_band'].to_pylist()
        for idx, band in enumerate(bands):
            by_band[band].append(idx)

        written: list[Path] = []
        for band, indices in by_band.items():
            part_dir = self.root / 'base' / f'utm_zone_band={band}'
            part_dir.mkdir(parents=True, exist_ok=True)
            target = part_dir / f'part_{batch_id}.parquet'
            sub = table.take(indices).drop(['utm_zone_band'])
            with TemporaryDirectory(dir=part_dir) as tmp:
                staged = Path(tmp) / target.name
                pq.write_table(sub, staged, compression='zstd', compression_level=3)
                staged.replace(target)
            written.append(target)

        if manifests:
            self._write_manifests(manifests)
        return written

    def append_enrichment(self, subset: str, rows: list[dict], manifests: list[dict] | None = None) -> Path | None:
        """Append on-demand enrichment rows as an immutable delta Parquet file."""
        if subset not in contract.ENRICHMENT_SUBSETS:
            raise ValueError(f'Subconjunto de enriquecimiento inválido: {subset}')
        if not rows:
            return None
        table_name = f'enrichment_{subset}'
        schema = contract.TABLE_SCHEMAS[table_name]
        table = contract.validate_table(pa.Table.from_pylist(rows, schema=schema), table_name)
        edir = self.root / 'enrichment' / subset
        target = edir / extractors.make_delta_filename('delta')
        with TemporaryDirectory(dir=edir) as tmp:
            staged = Path(tmp) / target.name
            pq.write_table(table, staged, compression='zstd', compression_level=3)
            staged.replace(target)
        if manifests:
            self._write_manifests(manifests)
        return target

    def compact(self, subset: str) -> Path | None:
        with self._connect() as conn:
            return contract.compact_enrichment(conn, self.root, subset)

    def compact_if_needed(self, subset: str) -> Path | None:
        thresholds = self.spec['storage_budget']['compaction_thresholds']
        edir = self.root / 'enrichment' / subset
        files = list(edir.glob('*.parquet'))
        total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
        if len(files) >= thresholds['max_delta_files'] or total_mb >= thresholds['max_delta_mb']:
            return self.compact(subset)
        return None

    def query_candidates_for_enrichment(
        self, limit: int = 50, profile: str = eligibility.DEFAULT_PROFILE,
    ) -> list[dict]:
        """Return eligible, rankable windows whose spectral module is still on_demand_fetchable."""
        p = eligibility.get_profile(profile)
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                SELECT region_id, longitude, latitude, utm_zone_band, relief_p95_p05_m, slope_240m_p50_deg
                FROM features_unified
                WHERE body = 'Earth'
                  AND qa_status = 'rankable'
                  AND ({eligibility_expression(profile)}) = ?
                  AND abs_al_oh_2p20um_status = 'on_demand_fetchable'
                ORDER BY region_id
                LIMIT ?
                """,
                [p.eligible_status, limit],
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def rank_similar(
        self,
        ref_relief_m: float,
        ref_slope_p50_deg: float,
        ref_slope_p90_deg: float,
        weights: tuple[float, float, float] = (0.4, 0.35, 0.25),
        limit: int = 25,
        only_eligible: bool = True,
        profile: str = eligibility.DEFAULT_PROFILE,
        ref_hypsometric_integral: float | None = None,
    ) -> list[dict]:
        """Out-of-core DuckDB similarity ranking using Entrega 3 topographic contract.

        `profile` selects the scenario eligibility gate; `only_eligible=False` keeps
        every rankable window but still reports its status under that profile.
        With `ref_hypsometric_integral`, windows refined by best framing also report
        `hi_best_abs_delta`; it is informative only and does not enter `distance_score`.
        """
        w_rel, w_s50, w_s90 = weights
        p = eligibility.get_profile(profile)
        elig_sql = eligibility_expression(profile)
        where_clauses = ["body = 'Earth'", "qa_status = 'rankable'"]
        if only_eligible:
            where_clauses.append(f"({elig_sql}) = '{p.eligible_status}'")
        where_sql = ' AND '.join(where_clauses)

        with self._connect() as conn:
            scales = conn.execute(
                f"""
                SELECT
                    GREATEST(COALESCE(quantile_cont(abs(relief_p95_p05_m - ?), 0.75), 0.0), 5.0),
                    GREATEST(COALESCE(quantile_cont(abs(slope_240m_p50_deg - ?), 0.75), 0.0), 0.25),
                    GREATEST(COALESCE(quantile_cont(abs(slope_240m_p90_deg - ?), 0.75), 0.0), 0.5)
                FROM features_unified
                WHERE {where_sql}
                """,
                [ref_relief_m, ref_slope_p50_deg, ref_slope_p90_deg],
            ).fetchone()
            s_rel, s_s50, s_s90 = scales
            cur = conn.execute(
                f"""
                SELECT
                    region_id,
                    longitude,
                    latitude,
                    utm_zone_band,
                    ({elig_sql}) AS scenario_eligibility,
                    '{profile}' AS scenario_profile,
                    analog_surface_eligibility,
                    eligibility_profile,
                    relief_p95_p05_m,
                    slope_240m_p50_deg,
                    slope_240m_p90_deg,
                    roughness_360m_p50_m,
                    bare_or_sparse_fraction,
                    abs_fe3_oxide_0p53_0p90um_status,
                    abs_al_oh_2p20um_status,
                    abs_carbonate_2p30_2p50um_status,
                    hls_status,
                    thermal_status,
                    framing_status,
                    hi_center,
                    hi_best,
                    hi_min,
                    hi_max,
                    best_offset_east_m,
                    best_offset_north_m,
                    best_at_lattice_edge,
                    best_relief_p95_p05_m,
                    abs(hi_best - CAST(? AS DOUBLE)) AS hi_best_abs_delta,
                    (
                        ? * (abs(relief_p95_p05_m - ?) / ?) +
                        ? * (abs(slope_240m_p50_deg - ?) / ?) +
                        ? * (abs(slope_240m_p90_deg - ?) / ?)
                    ) AS distance_score
                FROM features_unified
                WHERE {where_sql}
                ORDER BY distance_score ASC
                LIMIT ?
                """,
                [ref_hypsometric_integral, w_rel, ref_relief_m, s_rel, w_s50, ref_slope_p50_deg, s_s50,
                 w_s90, ref_slope_p90_deg, s_s90, limit],
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def rank_densified(
        self,
        ref_relief_m: float,
        ref_hypsometric_integral: float,
        lattice_step_m: int = framing.DEFAULT_STEP_M,
        max_offset_m: int = framing.DEFAULT_MAX_OFFSET_M,
        limit: int = 25,
        profile: str = eligibility.DEFAULT_PROFILE,
    ) -> list[dict]:
        """Densified-stage ranking of framed candidates by relief and hypsometric integral.

        `refine` chose each best framing by minimising `framing.densified_distance`; this
        ranks candidates by that same distance (fixed weights and framing-step scales),
        so selection and ranking cannot disagree. Only windows framed jointly against the
        same reference relief and integral and the same lattice enter. Slopes are
        reported but do not enter: they repeat the relief axis (rank correlation ~0.9).
        """
        (w_rel, w_hi), (s_rel, s_hi) = framing.DENSIFIED_WEIGHTS, framing.DENSIFIED_SCALES
        p = eligibility.get_profile(profile)
        elig_sql = eligibility_expression(profile)
        where_sql = f"""
            body = 'Earth' AND qa_status = 'rankable'
            AND ({elig_sql}) = '{p.eligible_status}'
            AND framing_status = 'measured'
            AND framing_criterion = '{framing.FRAMING_CRITERION}'
            AND hi_best IS NOT NULL AND best_relief_p95_p05_m IS NOT NULL
            AND abs(framing_reference_hi - CAST(? AS DOUBLE)) <= {framing.REFERENCE_HI_TOLERANCE}
            AND abs(framing_reference_relief_m - CAST(? AS DOUBLE)) <= {framing.REFERENCE_RELIEF_TOLERANCE_M}
            AND framing_step_m = ? AND framing_max_offset_m = ?
        """
        filt = [ref_hypsometric_integral, ref_relief_m, lattice_step_m, max_offset_m]

        with self._connect() as conn:
            if 'framing_criterion' not in {c[0] for c in conn.execute('DESCRIBE features_unified').fetchall()}:
                return []
            n = conn.execute(f'SELECT count(*) FROM features_unified WHERE {where_sql}', filt).fetchone()[0]
            if not n:
                return []
            cur = conn.execute(
                f"""
                SELECT
                    region_id, longitude, latitude, utm_zone_band,
                    ({elig_sql}) AS scenario_eligibility,
                    '{profile}' AS scenario_profile,
                    relief_p95_p05_m, slope_240m_p50_deg, slope_240m_p90_deg,
                    hi_center, hi_best, hi_min, hi_max,
                    best_offset_east_m, best_offset_north_m, best_at_lattice_edge,
                    best_relief_p95_p05_m, best_aspect_240m_resultant_length,
                    framing_step_m, framing_max_offset_m,
                    center_distance_score,
                    abs(best_relief_p95_p05_m - CAST(? AS DOUBLE)) / {s_rel} AS relief_term,
                    abs(hi_best - CAST(? AS DOUBLE)) / {s_hi} AS hi_term,
                    {w_rel} * abs(best_relief_p95_p05_m - CAST(? AS DOUBLE)) / {s_rel}
                      + {w_hi} * abs(hi_best - CAST(? AS DOUBLE)) / {s_hi} AS distance_score,
                    '{framing.DENSIFIED_VECTOR_ID}' AS ranking_vector,
                    '{framing.DENSIFIED_VECTOR_STATUS}' AS ranking_vector_status
                FROM features_unified
                WHERE {where_sql}
                ORDER BY distance_score ASC, region_id
                LIMIT ?
                """,
                [ref_relief_m, ref_hypsometric_integral, ref_relief_m, ref_hypsometric_integral, *filt, limit],
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for rank, row in enumerate(rows, 1):
            row['densified_rank'] = rank
            row['candidates_compared'] = n
        return rows

    def store_stats(self) -> dict:
        """Return storage footprint vs 100 GB budget and row/enrichment counts."""
        parquet_files = [p for p in self.root.rglob('*.parquet') if p.is_file()]
        total_bytes = sum(p.stat().st_size for p in parquet_files)
        max_bytes = self.spec['storage_budget']['max_store_gb'] * (1024 ** 3)
        with self._connect() as conn:
            total_rows = conn.execute('SELECT count(*) FROM base_windows').fetchone()[0]
            by_elig = dict(conn.execute(
                'SELECT analog_surface_eligibility, count(*) FROM base_windows GROUP BY analog_surface_eligibility'
            ).fetchall())
            by_profile = {
                pid: dict(conn.execute(
                    f"SELECT ({eligibility_expression(pid, climate=False)}) AS s, count(*) FROM base_windows "
                    "WHERE body = 'Earth' GROUP BY s"
                ).fetchall())
                for pid in eligibility.PROFILES
            }
            legacy_rows = conn.execute(
                "SELECT count(*) FROM base_windows WHERE body = 'Earth' AND eligibility_profile IS NULL"
            ).fetchone()[0]
            enriched_spectral = conn.execute(
                "SELECT count(*) FROM features_unified WHERE abs_al_oh_2p20um_status != 'on_demand_fetchable' AND body = 'Earth'"
            ).fetchone()[0]
        return {
            'store_root': str(self.root),
            'parquet_files': len(parquet_files),
            'total_bytes': total_bytes,
            'total_gb': round(total_bytes / (1024 ** 3), 6),
            'budget_gb': self.spec['storage_budget']['max_store_gb'],
            'budget_used_pct': round((total_bytes / max_bytes) * 100, 4),
            'total_windows': total_rows,
            'by_eligibility': by_elig,
            'by_scenario_profile': by_profile,
            'legacy_rows_needing_reextraction': legacy_rows,
            'enriched_spectral_earth': enriched_spectral,
        }
