#!/usr/bin/env python3
"""Export the data contracts that backend and frontend consume (specs/api/*.json).

Column names and types come from the code itself (DuckDB over an empty store with the current
schemas), so the files cannot drift from the ETL: `tests/test_contratos.py` regenerates them and
fails if the committed copies differ.

  python scripts/exportar_contratos.py           # rewrite specs/api/
  python scripts/exportar_contratos.py --check   # exit 1 if they are out of date
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_contract as contract  # noqa: E402
from pipelines import etl_publish as publish  # noqa: E402
from pipelines.etl_global_schema import GLOBAL_LAYERS, GLOBAL_RANGES  # noqa: E402
from pipelines.etl_store import FeatureStore  # noqa: E402

OUT = ROOT / 'specs/api'
RELEASE_FILE = OUT / 'release-atlas30-v1.json'
UNIFIED_FILE = OUT / 'features-unified-v1.json'

# Meaning and units of each release column (the table the API reads).
RELEASE_DOCS: dict[str, tuple[str, str | None]] = {
    'region_id': ('Clave estable de la ventana (rejilla utm-ups-v1). Une release, motor y /api/atlas/candidates', None),
    'batch': ('Lote del barrido que produjo la ventana', None),
    'area': ('Ámbito de la release (mundial)', None),
    'zone': ('EPSG de la zona UTM/UPS de la ventana', None),
    'x': ('Coordenada X del centro en su zona (m)', 'm'),
    'y': ('Coordenada Y del centro en su zona (m)', 'm'),
    'longitude': ('Longitud del centro (WGS84)', 'deg'),
    'latitude': ('Latitud del centro (WGS84)', 'deg'),
    'cell_m': ('Celda del DEM (30 m)', 'm'),
    'status': ('Estado QA de la topografía: rankable, dem_unavailable, dem_fetch_failed, insufficient_land, ...', None),
    'asset_ids': ('Teselas GLO-30 usadas (claves de sources.json)', None),
    'worldcover_assets': ('Teselas WorldCover usadas (claves de sources.json)', None),
    'water_assets': ('Teselas JRC usadas (claves de sources.json)', None),
    'land_fraction': ('Fracción de tierra en la huella de 3 km', 'fraction'),
    'valid_elevation': ('Fracción de celdas DEM válidas', 'fraction'),
    'valid_slope': ('Fracción de celdas con pendiente válida', 'fraction'),
    'valid_roughness': ('Cobertura de la rugosidad', 'fraction'),
    'relief_m': ('Relieve P95-P5 de la elevación', 'm'),
    'roughness_m': ('Rugosidad P50 a 360 m', 'm'),
    'slope_p50_deg': ('Pendiente P50 a base de 240 m', 'deg'),
    'slope_p90_deg': ('Pendiente P90 a base de 240 m', 'deg'),
    'slope_histogram': ('Histograma de pendiente (solo releases atlas30 antiguas; NULL en las del ETL)', None),
    'slope_cdf': ('CDF de pendiente (solo releases atlas30 antiguas; NULL en las del ETL)', None),
    'bare_fraction': ('WorldCover desnudo o escaso', 'fraction'),
    'vegetation_fraction': ('WorldCover árboles', 'fraction'),
    'urban_fraction': ('WorldCover construido', 'fraction'),
    'ice_fraction': ('WorldCover nieve o hielo', 'fraction'),
    'worldcover_water_fraction': ('WorldCover agua permanente', 'fraction'),
    'worldcover_valid_fraction': ('Fracción válida de WorldCover', 'fraction'),
    'water_occurrence_pct': ('Ocurrencia media de agua JRC', 'pct'),
    'water_valid_fraction': ('Reservado (NULL)', 'fraction'),
    'cover_status': ('Estado de la cobertura: measured, no_cover_tile, cover_fetch_failed, ...', None),
    'eligibility': ('Elegibilidad bajo el perfil publicado', None),
    'eligibility_profile': ('Perfil de elegibilidad publicado', None),
    'hypsometric_integral': ('Integral hipsométrica de la huella', 'fraction'),
    'aspect_240m_resultant_length': ('Concentración de orientación de pendientes (0 dispersa, 1 una sola dirección)', 'fraction'),
    'framing_status': ('Estado del mejor encuadre (solo candidatas refinadas)', None),
    'hi_center': ('Integral hipsométrica en el encuadre centrado', 'fraction'),
    'hi_best': ('Integral hipsométrica en el mejor encuadre', 'fraction'),
    'best_offset_east_m': ('Desplazamiento este del mejor encuadre', 'm'),
    'best_offset_north_m': ('Desplazamiento norte del mejor encuadre', 'm'),
    'elevation_skew_p95_p05': ('Asimetría de elevación P95/P5', None),
    'slope_240m_gt15_fraction': ('Fracción con pendiente > 15°', 'fraction'),
    'slope_240m_gt25_fraction': ('Fracción con pendiente > 25°', 'fraction'),
}
GLOBAL_UNITS = {
    'precip_annual_mm_cmg': ('Precipitación media anual (IMERG mensual)', 'mm/año'),
    'dry_months_fraction_cmg': ('Fracción de meses climatológicos con < 5 mm', 'fraction'),
    'snow_cover_mean_pct_cmg': ('Cobertura de nieve mensual media (MOD10CM)', 'pct'),
    'snow_months_fraction_cmg': ('Fracción de meses con nieve >= 50 %', 'fraction'),
    'lst_day_night_delta_k_cmg': ('Amplitud térmica día-noche (MYD11C3)', 'K'),
    'albedo_wsa_cmg': ('Albedo de cielo blanco (MCD43C3)', 'fraction'),
    'ati_cmg_per_k': ('Inercia térmica aparente gruesa', '1/K'),
    'emis_mean_b10_b14_cmg': ('Emisividad media bandas 10-14 (AG1km)', None),
    'emis_quartz_index_cmg': ('Índice de cuarzo b11²/(b10·b12)', None),
    'emis_carbonate_index_cmg': ('Índice de carbonato b13/b14', None),
    'emis_mafic_index_cmg': ('Índice máfico (b10+b11)/(b12+b13)', None),
    'soil_moisture_mean_cmg': ('Humedad del suelo media (SMAP L3, AM)', 'm3/m3'),
    'soil_moisture_obs_fraction_cmg': ('Fracción de días con recuperación válida', 'fraction'),
    'permafrost_fraction_cmg': ('Fracción de permafrost (ESA CCI)', 'fraction'),
}
for _layer in GLOBAL_LAYERS:
    GLOBAL_UNITS[f'{_layer}_cmg_status'] = (
        f'Estado de la capa global {_layer}: measured, insufficient_coverage, unobserved_by_product, '
        'on_demand_fetchable (capa aún no construida)', None)


def _empty_store(tmp: Path) -> FeatureStore:
    store = FeatureStore(tmp / 'store', memory_limit='256MB', threads=1)
    store._write_manifests([{
        'source_manifest_id': 'contract', 'product_id': 'contract', 'asset_id': 'contract', 'access_mode': 'contract',
        'sha256_or_etag': None, 'native_resolution_m': 30.0, 'effective_resolution_m': 30.0,
        'observation_period': None, 'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc)}])
    return store


def _columns(conn, sql: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in conn.execute(f'DESCRIBE {sql}').fetchall()]


def build_contracts() -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        store = _empty_store(Path(tmp))
        with store._connect() as conn:
            release_cols = _columns(conn, publish.release_windows_sql(store, 'arid_mars_surface_v2'))
            unified_cols = _columns(conn, 'SELECT * FROM features_unified')
    release = {
        'contract_id': publish.RELEASE_CONTRACT,
        'stability': 'estable; solo se añaden columnas (nunca se renombran ni se quitan)',
        'producer': 'pipelines/etl_publish.py (publish_release)',
        'consumer': 'backend/app/atlas_store.py -> /api/atlas/*',
        'layout': {
            'releases/atlas30/current': 'Nombre de la versión activa (texto)',
            'releases/atlas30/<version>/manifest.json': 'Metadatos: release_contract, version, counts, profile, normalization, eligibility_counts, cover_counts, coverage_status, similarity (opcional)',
            'releases/atlas30/<version>/windows/windows.parquet': 'Una fila por ventana terrestre (columnas abajo)',
            'releases/atlas30/<version>/sources.json': 'asset_id -> {product, sha256_or_etag, native_resolution_m, observation_period, doi, product_version}',
            'releases/atlas30/<version>/batches.json': 'Lotes del barrido con estado y número de ventanas',
            'releases/atlas30/<version>/similarity/<referencia>.json': 'Opcional: respuesta del motor (specs/api/motor-busqueda-v1.schema.json) para jezero, haworth-fondo y de-gerlache-cresta con pesos por defecto',
        },
        'windows_columns': [],
    }
    for name, dtype in release_cols:
        desc, unit = RELEASE_DOCS.get(name) or GLOBAL_UNITS.get(name) or ('', None)
        entry = {'name': name, 'type': dtype, 'nullable': name not in ('region_id', 'longitude', 'latitude', 'status'),
                 'description': desc}
        if unit:
            entry['unit'] = unit
        if name in GLOBAL_RANGES:
            entry['range'] = list(GLOBAL_RANGES[name])
            entry['tier'] = 'context_coarse'
        release['windows_columns'].append(entry)
    unified = {
        'contract_id': 'features-unified-v1',
        'stability': 'interno del ETL; el backend debe leer releases, no el almacén',
        'producer': 'pipelines/etl_contract.py (register_unified_views)',
        'note': 'Vista DuckDB con la base y el último enriquecimiento de cada ventana; la usan el motor y la publicación.',
        'enums': {'feature_status': list(contract.FEATURE_STATUS_ENUM)},
        'columns': [{'name': n, 'type': t} for n, t in unified_cols],
    }
    return {RELEASE_FILE.name: release, UNIFIED_FILE.name: unified}


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + '\n'


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='Comprobar sin escribir')
    args = parser.parse_args(argv)
    stale = []
    for name, doc in build_contracts().items():
        path = OUT / name
        text = render(doc)
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            print(f'escrito {path.relative_to(ROOT)}')
    if stale:
        sys.exit(f'Contratos desactualizados: {", ".join(stale)} (ejecuta scripts/exportar_contratos.py)')


if __name__ == '__main__':
    main()
