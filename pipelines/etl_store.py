"""DuckDB out-of-core Feature Store over partitioned Parquet (Base + On-Demand Deltas)."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from pipelines import etl_contract as contract
from pipelines import etl_extractors as extractors


class FeatureStore:
    """Manages reads, atomic batch writes, on-demand delta appends and DuckDB compaction."""

    def __init__(self, root: Path, memory_limit: str = '2GB', threads: int = 4) -> None:
        self.root = Path(root)
        self.memory_limit = memory_limit
        self.threads = threads
        self.spec = contract.load_store_spec()
        self.spill_dir = self.root / self.spec['duckdb_out_of_core']['temp_directory_name']
        for sub in ('base', 'enrichment/spectral', 'enrichment/temporal', 'manifests', 'manifests/batches'):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def completed_batch_ids(self) -> set[str]:
        bdir = self.root / 'manifests' / 'batches'
        return {p.stem for p in bdir.glob('*.json')}

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
        dedup = {(m['source_manifest_id'], m['asset_id']): m for m in manifests}
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
        if subset not in ('spectral', 'temporal'):
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

    def query_candidates_for_enrichment(self, limit: int = 50) -> list[dict]:
        """Return eligible, rankable windows whose spectral module is still on_demand_fetchable."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT region_id, longitude, latitude, utm_zone_band, relief_p95_p05_m, slope_240m_p50_deg
                FROM features_unified
                WHERE body = 'Earth'
                  AND qa_status = 'rankable'
                  AND analog_surface_eligibility = 'eligible_arid_exposed'
                  AND abs_al_oh_2p20um_status = 'on_demand_fetchable'
                ORDER BY region_id
                LIMIT ?
                """,
                [limit],
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
    ) -> list[dict]:
        """Out-of-core DuckDB similarity ranking using Entrega 3 topographic contract."""
        w_rel, w_s50, w_s90 = weights
        where_clauses = ["body = 'Earth'", "qa_status = 'rankable'"]
        if only_eligible:
            where_clauses.append("analog_surface_eligibility = 'eligible_arid_exposed'")
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
                    analog_surface_eligibility,
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
                [w_rel, ref_relief_m, s_rel, w_s50, ref_slope_p50_deg, s_s50, w_s90, ref_slope_p90_deg, s_s90, limit],
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

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
            'enriched_spectral_earth': enriched_spectral,
        }
