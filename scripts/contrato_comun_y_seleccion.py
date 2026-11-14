#!/usr/bin/env python3
"""Entrega 3: Contrato común entre instrumentos (Tierra-Marte), consulta bajo demanda y selección cuantitativa de características.

Ejecutar con:
  bash scripts/ejecutar_minerales.sh scripts/contrato_comun_y_seleccion.py
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'analogos-matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(Path(tempfile.gettempdir()) / 'analogos-cache'))
Path(os.environ['XDG_CACHE_HOME']).mkdir(parents=True, exist_ok=True)

import h5py
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np
from pyproj import Geod
import rasterio
from rasterio.transform import from_origin
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import analizar_minerales as emit
import analizar_primer_caso as terrain
from analizar_dimensiones import geometry_descriptors
import contrastar_topografia_utah as trial
import explorar_fuentes_atlas as eda
from armonizar_dimensiones_superficie import aggregate_emit_families, shannon_entropy_bits
from pipelines import etl_surface_dimensions as surface_dims
from pipelines import etl_surface_schema as surface_schema
from pipelines import worldview_blind

SPEC_PATH = ROOT / 'specs/analysis/contrato-comun-entrega3.json'
HARMONIZATION_DIR = ROOT / 'docs/evidencia-armonizacion-superficie'
TOPO_VAL_PATH = ROOT / 'docs/evidencia-validacion-topografica/resultados.json'
PHASE2_SPEC = ROOT / 'specs/analysis/primer-caso-fase2.json'
PHASE4_CANDIDATES = ROOT / 'docs/evidencia-fase-4/candidatas.json'
PHASE5_RESULTS = ROOT / 'docs/evidencia-fase-5/resultados.json'
DIMENSIONS_RESULTS = ROOT / 'docs/evidencia-dimensiones/resultados.json'
MATERIAL_SPEC = ROOT / 'specs/analysis/minerales-emit-v1.json'
CONTEXT_SPEC = ROOT / 'specs/sources/contexto-atlas-2024.json'
OUT = ROOT / 'docs/evidencia-entrega-3'

SITE_CATALOG = [
    {
        'site_id': 'mars-jezero-fan',
        'label': 'Jezero · abanico deltaico (Marte)',
        'body': 'Mars',
        'stratum': 'mars_reference_fan',
        'role': 'reference',
        'lon_lat': [77.41, 18.49],
        'dem_source': 'HiRISE_DTM',
        'dem_path': 'data/raw/hirise/DTEEC_002387_1985_003798_1985_A01.IMG',
        'product_id': 'DTEEC_002387_1985_003798_1985_A01',
        'radius_m': 3394839.8133163,
        'valid_range_m': [-2600.51, -2298.75],
        'vertical_reference': 'Mars 2000 equipotential surface, label',
    },
    {
        'site_id': 'desierto',
        'label': 'Utah · cuenca árida / Flaming Gorge',
        'body': 'Earth',
        'stratum': 'arid_sedimentary_basin',
        'role': 'positive_analog_candidate',
        'lon_lat': [-110.6, 38.6],
        'dem_source': 'GLO-30',
        'dem_path': 'data/raw/atlas30/glo30/Copernicus_DSM_COG_10_N38_00_W111_00_DEM.tif',
        'topo_val_key': 'desierto-utah',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'atacama-materiales',
        'label': 'Atacama · cuenca hiperárida / salar y abanicos',
        'body': 'Earth',
        'stratum': 'hyperarid_evaporitic_fan',
        'role': 'positive_analog_candidate',
        'lon_lat': [-67.9, -23.8],
        'dem_source': 'SRTM',
        'dem_path': 'data/raw/srtm/S24W068.tif',
        'valid_range_m': [-500.0, 9000.0],
        'vertical_reference': 'EGM96',
    },
    {
        'site_id': 'sahara-sahel',
        'label': 'Sahel/Sahara · llanura árida (N15W002)',
        'body': 'Earth',
        'stratum': 'arid_aeolian_plain',
        'role': 'positive_analog_candidate',
        'lon_lat': [-1.5, 15.5],
        'dem_source': 'GLO-30',
        'dem_path': 'data/raw/atlas30/glo30/Copernicus_DSM_COG_10_N15_00_W002_00_DEM.tif',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'costa',
        'label': 'Costa árida · escarpe hiperárido (Atacama)',
        'body': 'Earth',
        'stratum': 'arid_escarpment',
        'role': 'morphological_contrast',
        'lon_lat': [-70.1, -23.65],
        'dem_source': 'GLO-30',
        'dem_path': 'data/raw/atlas30/glo30/Copernicus_DSM_COG_10_S24_00_W071_00_DEM.tif',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'montana',
        'label': 'Alpes · relieve alpino y valle',
        'body': 'Earth',
        'stratum': 'alpine_high_relief',
        'role': 'negative_control_relief_and_cover',
        'lon_lat': [11.2, 46.6],
        'dem_source': 'GLO-30',
        'dem_path': 'data/raw/atlas30/glo30/Copernicus_DSM_COG_10_N46_00_E011_00_DEM.tif',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'bosque-oregon',
        'label': 'Oregón · bosque templado húmedo',
        'body': 'Earth',
        'stratum': 'dense_temperate_forest',
        'role': 'negative_control_canopy',
        'lon_lat': [-123.55, 45.55],
        'dem_source': 'GLO-30',
        'topo_val_key': 'bosque-oregon',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'bosque-carolina',
        'label': 'Carolina del Norte · bosque montañoso',
        'body': 'Earth',
        'stratum': 'dense_temperate_forest',
        'role': 'negative_control_canopy',
        'lon_lat': [-82.81, 35.37],
        'dem_source': 'GLO-30',
        'topo_val_key': 'bosque-carolina',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'costa-carolina',
        'label': 'Carolina del Norte · estuario y costa húmeda',
        'body': 'Earth',
        'stratum': 'coastal_water_transition',
        'role': 'negative_control_water',
        'lon_lat': [-77.889, 34.067],
        'dem_source': 'GLO-30',
        'topo_val_key': 'costa-carolina',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'tropico',
        'label': 'Borneo · selva tropical densa',
        'body': 'Earth',
        'stratum': 'tropical_rainforest',
        'role': 'negative_control_canopy',
        'lon_lat': [114.6, 0.6],
        'dem_source': 'GLO-30',
        'dem_path': 'data/raw/atlas30/glo30/Copernicus_DSM_COG_10_N00_00_E114_00_DEM.tif',
        'vertical_reference': 'EGM2008',
    },
    {
        'site_id': 'polar',
        'label': 'Antártida · meseta criosférica',
        'body': 'Earth',
        'stratum': 'polar_cryosphere',
        'role': 'cryosphere_control',
        'lon_lat': [0.2, -80.7],
        'dem_source': 'GLO-30',
        'dem_path': 'data/raw/atlas30/glo30/Copernicus_DSM_COG_10_S81_00_E000_00_DEM.tif',
        'vertical_reference': 'EGM2008',
    },
]


def compute_dem_contract_from_raster(site_meta: dict, windows_m=(1800, 3000), cells_m=(30, 60, 120),
                                     slope_base_m=240, roughness_radius_m=360, halo_m=720) -> dict:
    """Adapter: computes the canonical topographic contract from any Earth or Mars DEM."""
    lon, lat = site_meta['lon_lat']
    max_win = max(windows_m)
    config = {'window_m': max_win, 'margin_m': halo_m}
    half = max_win / 2 + halo_m
    req = {
        'longitude': lon,
        'latitude': lat,
        'body': site_meta['body'],
        'product_id': site_meta.get('product_id', Path(site_meta['dem_path']).stem),
        'input': site_meta['dem_path'],
        'url': None,
        'vertical_reference': site_meta['vertical_reference'],
        'limitations': [],
    }
    if 'radius_m' in site_meta:
        req['radius_m'] = site_meta['radius_m']
    if 'valid_range_m' in site_meta:
        req['valid_range_m'] = site_meta['valid_range_m']

    data, valid, src_transform, src_crs, dst_crs, meta = terrain.read_crop(ROOT / site_meta['dem_path'], req, config)
    out_by_window = {}
    for cell in cells_m:
        n = int(2 * half) // cell
        dst_transform = from_origin(-half, half, cell, cell)
        elev, _ = terrain.aggregate(data, valid, src_transform, src_crs, dst_crs, dst_transform, (n, n), trial.TOLERANCE)
        slp_240 = trial.slope(elev, cell, slope_base_m)
        slp_imm = trial.slope(elev, cell, 2 * cell)
        desc = geometry_descriptors(elev, cell, roughness_radius_m)
        rgh_360 = desc['roughness_rms']
        tpi_360 = desc['topographic_position']
        lap = desc['laplacian']

        for win in windows_m:
            z_w = trial.center_crop(elev, win, cell)
            s240_w = trial.center_crop(slp_240, win, cell)
            simm_w = trial.center_crop(slp_imm, win, cell)
            r360_w = trial.center_crop(rgh_360, win, cell)
            tpi_w = trial.center_crop(tpi_360, win, cell)
            lap_w = trial.center_crop(lap, win, cell)

            def qstats(arr):
                finite = arr[np.isfinite(arr)]
                tot = int(arr.size)
                cnt = int(finite.size)
                cov = float(cnt / tot) if tot else 0.0
                if not cnt:
                    return {'n': 0, 'total_cells': tot, 'coverage': 0.0, 'p05': None, 'p25': None,
                            'p50': None, 'p75': None, 'p90': None, 'p95': None, 'iqr': None, 'p95_minus_p05': None}
                p05, p25, p50, p75, p90, p95 = map(float, np.percentile(finite, [5, 25, 50, 90 - 15, 90, 95]))
                return {
                    'n': cnt,
                    'total_cells': tot,
                    'coverage': cov,
                    'p05': p05,
                    'p25': p25,
                    'p50': p50,
                    'p75': p75,
                    'p90': p90,
                    'p95': p95,
                    'iqr': float(p75 - p25),
                    'p95_minus_p05': float(p95 - p05),
                }

            z_st = qstats(z_w)
            s240_st = qstats(s240_w)
            simm_st = qstats(simm_w)
            r360_st = qstats(r360_w)
            tpi_st = qstats(tpi_w)
            lap_st = qstats(lap_w)

            out_by_window.setdefault(str(win), {})[str(cell)] = {
                'window_m': win,
                'cell_m': cell,
                'dem_source': site_meta['dem_source'],
                'policy': 'sin_mascara',
                'relief_p95_p05_m': z_st['p95_minus_p05'],
                'elevation_coverage': z_st['coverage'],
                'slope_240m_p50_deg': s240_st['p50'],
                'slope_240m_p90_deg': s240_st['p90'],
                'slope_240m_iqr_deg': s240_st['iqr'],
                'slope_240m_coverage': s240_st['coverage'],
                'slope_immediate_base_m': 2 * cell,
                'slope_immediate_p50_deg': simm_st['p50'],
                'slope_immediate_p90_deg': simm_st['p90'],
                'roughness_360m_p50_m': r360_st['p50'],
                'roughness_360m_p90_m': r360_st['p90'],
                'roughness_360m_iqr_m': r360_st['iqr'],
                'roughness_360m_coverage': r360_st['coverage'],
                'tpi_360m_p50_m': tpi_st['p50'],
                'tpi_360m_iqr_m': tpi_st['iqr'],
                'laplacian_iqr_m_inv': lap_st['iqr'],
            }
    return {'site_id': site_meta['site_id'], 'scales_by_window': out_by_window, 'provenance': {
        'input': meta['input'], 'sha256': meta['sha256'], 'bytes': meta['bytes'],
        'native_step_at_center_m': meta['native_step_at_center_m']
    }}


def extract_topography_from_validation(topo_val_data: dict, site_meta: dict) -> dict:
    """Extracts GLO-30 (and 3DEP/SRTM deltas) from the validated 168-configuration matrix."""
    key = site_meta['topo_val_key']
    block = topo_val_data[key]
    policy = block['primary_policy']
    rows = block['measurements']
    out_by_window = {}
    for win in (1800, 3000):
        out_by_window[str(win)] = {}
        for cell in (30, 60, 120):
            def find(desc, setting):
                return next(
                    (r for r in rows if r['window_m'] == win and r['cell_m'] == cell
                     and r.get('policy', 'sin_mascara') == policy
                     and r['descriptor'] == desc and r['setting_m'] == setting),
                    None
                )
            rel = find('relief', None)
            s240 = find('slope', 240)
            simm = find('slope', 2 * cell)
            r360 = find('roughness', 360)
            src = 'GLO-30'
            out_by_window[str(win)][str(cell)] = {
                'window_m': win,
                'cell_m': cell,
                'dem_source': src,
                'policy': policy,
                'relief_p95_p05_m': rel['statistics'][src]['p95_minus_p05'] if rel and rel['statistics'] else None,
                'relief_3dep_m': rel['statistics']['3DEP']['p95_minus_p05'] if rel and rel['statistics'] else None,
                'relief_srtm_m': rel['statistics']['SRTM']['p95_minus_p05'] if rel and rel['statistics'] else None,
                'elevation_coverage': rel['common_fraction'] if rel else 0.0,
                'slope_240m_p50_deg': s240['statistics'][src]['p50'] if s240 and s240['statistics'] else None,
                'slope_240m_p90_deg': s240['statistics'][src]['p90'] if s240 and s240['statistics'] else None,
                'slope_240m_3dep_p50_deg': s240['statistics']['3DEP']['p50'] if s240 and s240['statistics'] else None,
                'slope_240m_abs_delta_vs_3dep_p50_deg': s240['paired_against_3dep'][src]['median_absolute'] if s240 and s240['paired_against_3dep'] else None,
                'slope_240m_coverage': s240['common_fraction'] if s240 else 0.0,
                'slope_immediate_base_m': 2 * cell,
                'slope_immediate_p50_deg': simm['statistics'][src]['p50'] if simm and simm['statistics'] else None,
                'slope_immediate_abs_delta_vs_3dep_p50_deg': simm['paired_against_3dep'][src]['median_absolute'] if simm and simm['paired_against_3dep'] else None,
                'roughness_360m_p50_m': r360['statistics'][src]['p50'] if r360 and r360['statistics'] else None,
                'roughness_360m_p90_m': r360['statistics'][src]['p90'] if r360 and r360['statistics'] else None,
                'roughness_360m_3dep_p50_m': r360['statistics']['3DEP']['p50'] if r360 and r360['statistics'] else None,
                'roughness_360m_abs_delta_vs_3dep_p50_m': r360['paired_against_3dep'][src]['median_absolute'] if r360 and r360['paired_against_3dep'] else None,
                'roughness_360m_coverage': r360['common_fraction'] if r360 else 0.0,
                'roughness_360m_fraction_of_eligible': r360.get('fraction_of_eligible', r360['common_fraction']) if r360 else 0.0,
            }
    return {'site_id': site_meta['site_id'], 'scales_by_window': out_by_window}


def adapt_crism_to_contract(spec: dict) -> dict:
    """CRISM Adapter: maps CRISM MTR3 summary parameters onto the 6 canonical absorption complexes."""
    phase2 = json.loads(PHASE2_SPEC.read_text())
    site = phase2['sites'][0]
    sr_rel = 'data/raw/crism/frt000047a3/frt000047a3_07_sr166j_mtr3.img'
    in_rel = 'data/raw/crism/frt000047a3/frt000047a3_07_in166j_mtr3.img'
    min_cov = spec['quality_thresholds']['min_window_valid_fraction']
    out = {}
    with rasterio.open(ROOT / sr_rel) as values, rasterio.open(ROOT / in_rel) as masks:
        descriptions = list(values.descriptions)
        for width in spec['windows_m']:
            feature = terrain.geometry(site, {'window_m': width})
            geom, crs = feature['geometry'], feature['properties']['crs_wkt']
            window, inside = eda.native_crop(values, geom, crs)
            qa = eda.read_crop(masks, 9, window)
            atm_res = eda.read_crop(masks, 6, window)
            n_total = int(inside.sum())
            in_swath = int(np.isfinite(qa[inside]).sum())
            valid_mask = inside & (qa == 0)
            n_valid = int(valid_mask.sum())
            valid_fraction = float(n_valid / n_total) if n_total else 0.0
            in_swath_fraction = float(n_valid / in_swath) if in_swath else 0.0
            atm_valid = atm_res[valid_mask]
            atm_valid = atm_valid[np.isfinite(atm_valid)]
            atm_p50 = float(np.median(atm_valid)) if atm_valid.size else None

            complex_records = {}
            for comp in spec['spectral_absorption_complexes']:
                cid = comp['complex_id']
                cad = comp['crism_adapter']
                prim = cad['primary_parameter']
                sec = cad['secondary_parameter']
                floor = float(cad['positive_floor'])

                p_arr = eda.read_crop(values, descriptions.index(prim) + 1, window)[valid_mask]
                p_arr = p_arr[np.isfinite(p_arr)]
                s_arr = eda.read_crop(values, descriptions.index(sec) + 1, window)[valid_mask]
                s_arr = s_arr[np.isfinite(s_arr)]

                if p_arr.size:
                    p05, p25, p50, p75, p95 = map(float, np.percentile(p_arr, [5, 25, 50, 75, 95]))
                    iqr = float(p75 - p25)
                    adaptive_thresh = max(floor, p50 + 1.5 * iqr) if floor > 0 else 0.0
                    active_above_floor = float((p_arr > floor).mean())
                    active_hotspot = float((p_arr > adaptive_thresh).mean())
                else:
                    p05 = p50 = p95 = iqr = active_above_floor = active_hotspot = None

                s_p50 = float(np.median(s_arr)) if s_arr.size else None
                s_p95 = float(np.percentile(s_arr, 95)) if s_arr.size else None
                status = 'measured' if valid_fraction >= min_cov else 'insufficient_coverage'

                complex_records[cid] = {
                    'complex_id': cid,
                    'label': comp['label'],
                    'comparability_tier': comp['comparability_tier'],
                    'instrument': 'CRISM_MTR3',
                    'status': status,
                    'primary_indicator': prim,
                    'secondary_indicator': sec,
                    'strength_p50': p50 if status == 'measured' else None,
                    'strength_p95': p95 if status == 'measured' else None,
                    'strength_iqr': iqr if status == 'measured' else None,
                    'unmasked_strength_p50': p50,
                    'unmasked_strength_p95': p95,
                    'secondary_p50': s_p50,
                    'secondary_p95': s_p95,
                    'active_fraction_above_floor': active_above_floor,
                    'hotspot_fraction': active_hotspot,
                    'positive_floor_applied': floor,
                    'support': {
                        'valid_centers': n_valid,
                        'footprint_centers': n_total,
                        'in_swath_centers': in_swath,
                        'valid_fraction_of_footprint': valid_fraction,
                        'valid_fraction_of_swath': in_swath_fraction,
                        'atm_residual_p50': atm_p50,
                    },
                }
            out[str(width)] = {
                'window_m': width,
                'status': 'measured' if valid_fraction >= min_cov else 'insufficient_coverage',
                'footprint_centers': n_total,
                'in_swath_centers': in_swath,
                'valid_centers': n_valid,
                'valid_fraction_of_footprint': valid_fraction,
                'valid_fraction_of_swath': in_swath_fraction,
                'complexes': complex_records,
            }
    return out


def adapt_emit_to_contract(spec: dict) -> dict:
    """EMIT Adapter: maps EMIT L2B unique sensor samples onto the 6 canonical absorption complexes."""
    cfg = json.loads(MATERIAL_SPEC.read_text())
    fit_min = spec['quality_thresholds']['emit_min_restored_fit']
    sigma_ratio = spec['quality_thresholds']['emit_min_depth_sigma_ratio']
    min_samples = spec['quality_thresholds']['min_emit_qualified_samples']

    out_by_site = {}
    for scene in cfg['scenes']:
        site_id = 'desierto' if scene['site_id'] == 'earth-utah' else 'atacama-materiales'
        scene_id = scene['product_id']
        for width in spec['windows_m']:
            geometry = eda.aoi(*eda.CENTERS[site_id], side=width)
            profile = emit.read_scene(scene, geometry)
            with h5py.File(ROOT / scene['mineral']['input']) as ds:
                ix, iy, inside, _, _ = emit.crop_glt(ds, geometry)
                height, columns = ds['group_1_mineral_id'].shape
            valid = inside & (ix > 0) & (iy > 0) & (ix <= columns) & (iy <= height)
            locations = np.flatnonzero(valid)
            keys = (iy.ravel()[locations] - 1) * columns + ix.ravel()[locations] - 1
            _, first = np.unique(keys, return_index=True)
            unique = locations[first]
            n_unique_glt = int(len(unique))

            group_samples = {}
            for gname in ('1', '2'):
                grp = profile['groups'][gname]
                ids = np.asarray(grp['ids'], dtype=float)[unique]
                depth = np.asarray(grp['depth'], dtype=float)[unique]
                fit = np.asarray(grp['fit'], dtype=float)[unique]
                unc = np.asarray(grp['uncertainty'], dtype=float)[unique]
                usable = np.asarray(grp['usable'], dtype=bool)[unique]
                qualified = usable & (2.0 * fit >= fit_min) & (depth > sigma_ratio * unc)

                by_code_family = {}
                for c in grp['classes']:
                    cid_int = int(c['id'])
                    mapped_fam = aggregate_emit_families({str(cid_int): 1}, [c])
                    by_code_family[cid_int] = next(iter(mapped_fam.keys()))

                fams = np.array([by_code_family.get(int(code), 'Otros') if np.isfinite(code) and code > 0 else 'Sin_ajuste'
                                 for code in ids], dtype=object)
                mineral_qualified = qualified & (fams != 'Orgánico o sintético') & (fams != 'Sin_ajuste')
                counts_u = eda.counts(ids[qualified])
                counts_fam = aggregate_emit_families(counts_u, grp['classes'])
                counts_min_fam = {k: v for k, v in counts_fam.items() if k != 'Orgánico o sintético'}

                group_samples[gname] = {
                    'ids': ids,
                    'depth': depth,
                    'restored_fit': 2.0 * fit,
                    'uncertainty': unc,
                    'qualified': qualified,
                    'mineral_qualified': mineral_qualified,
                    'families': fams,
                    'n_qualified_total': int(qualified.sum()),
                    'n_qualified_mineral': int(mineral_qualified.sum()),
                    'n_organic_or_synthetic': int((qualified & (fams == 'Orgánico o sintético')).sum()),
                    'library_entropy_bits': shannon_entropy_bits(counts_u),
                    'family_entropy_bits': shannon_entropy_bits(counts_fam),
                    'mineral_family_entropy_bits': shannon_entropy_bits(counts_min_fam),
                }

            complex_records = {}
            for comp in spec['spectral_absorption_complexes']:
                cid = comp['complex_id']
                ead = comp['emit_l2b_adapter']
                sg = ead['spectral_group']
                if sg is None:
                    complex_records[cid] = {
                        'complex_id': cid,
                        'label': comp['label'],
                        'comparability_tier': comp['comparability_tier'],
                        'instrument': 'EMIT_L2B_MIN',
                        'status': 'unobserved_by_product',
                        'qualified_mineral_fraction': None,
                        'qualified_total_fraction': None,
                        'footprint_sample_fraction': None,
                        'strength_p50': None,
                        'strength_p95': None,
                        'fit_p50': None,
                        'sample_count': 0,
                        'note': ead.get('note'),
                    }
                    continue

                gdata = group_samples[str(sg)]
                target_fams = set(ead['families'])
                in_complex = gdata['mineral_qualified'] & np.isin(gdata['families'], list(target_fams))
                n_comp = int(in_complex.sum())
                n_min_tot = gdata['n_qualified_mineral']
                n_qual_tot = gdata['n_qualified_total']

                if n_min_tot < min_samples:
                    status = 'no_support' if n_min_tot == 0 else 'insufficient_sample'
                elif n_comp == 0:
                    status = 'measured_absent'
                elif n_comp < min_samples:
                    status = 'insufficient_complex_sample'
                else:
                    status = 'measured'

                d_vals = gdata['depth'][in_complex]
                f_vals = gdata['restored_fit'][in_complex]
                raw_p50 = float(np.median(d_vals)) if n_comp > 0 else 0.0
                raw_p95 = float(np.percentile(d_vals, 95)) if n_comp > 0 else 0.0
                complex_records[cid] = {
                    'complex_id': cid,
                    'label': comp['label'],
                    'comparability_tier': comp['comparability_tier'],
                    'instrument': 'EMIT_L2B_MIN',
                    'spectral_group': sg,
                    'status': status,
                    'sample_count': n_comp,
                    'group_qualified_mineral_samples': n_min_tot,
                    'group_qualified_total_samples': n_qual_tot,
                    'group_organic_excluded_samples': gdata['n_organic_or_synthetic'],
                    'qualified_mineral_fraction': float(n_comp / n_min_tot) if n_min_tot >= min_samples else None,
                    'qualified_total_fraction': float(n_comp / n_qual_tot) if n_min_tot >= min_samples and n_qual_tot > 0 else None,
                    'footprint_sample_fraction': float(n_comp / n_unique_glt) if n_min_tot >= min_samples and n_unique_glt > 0 else None,
                    'strength_p50': raw_p50 if status == 'measured' else (0.0 if status == 'measured_absent' else None),
                    'strength_p95': raw_p95 if status == 'measured' else (0.0 if status == 'measured_absent' else None),
                    'unmasked_strength_p50': raw_p50 if n_comp > 0 else None,
                    'unmasked_strength_p95': raw_p95 if n_comp > 0 else None,
                    'fit_p50': float(np.median(f_vals)) if n_comp > 0 else None,
                    'group_library_entropy_bits': gdata['library_entropy_bits'],
                    'group_family_entropy_bits': gdata['family_entropy_bits'],
                    'group_mineral_family_entropy_bits': gdata['mineral_family_entropy_bits'],
                }

            scene_entry = {
                'scene_id': scene_id,
                'product_id': profile['product_id'],
                'date': profile['date'],
                'window_m': width,
                'unique_glt_samples': n_unique_glt,
                'group_1_summary': {k: group_samples['1'][k] for k in (
                    'n_qualified_total', 'n_qualified_mineral', 'library_entropy_bits', 'family_entropy_bits')},
                'group_2_summary': {k: group_samples['2'][k] for k in (
                    'n_qualified_total', 'n_qualified_mineral', 'n_organic_or_synthetic',
                    'library_entropy_bits', 'family_entropy_bits', 'mineral_family_entropy_bits')},
                'complexes': complex_records,
            }
            out_by_site.setdefault(site_id, {}).setdefault(str(width), []).append(scene_entry)
    return out_by_site


def build_common_contract_records(spec: dict) -> dict:
    """Materializes the full Common Feature Contract across Mars and Earth sites."""
    med = json.loads((HARMONIZATION_DIR / 'mediciones.json').read_text())
    topo_val = json.loads(TOPO_VAL_PATH.read_text())
    crism_contract = adapt_crism_to_contract(spec)
    emit_contract = adapt_emit_to_contract(spec)

    # Index cover, water, optical, thermal from mediciones.json
    wc_by_site = {r['site']: r for r in med['cover_and_water'] if r['source'] == 'worldcover'}
    jrc_by_site = {r['site']: r for r in med['cover_and_water'] if r['source'] == 'jrc'}
    themis_by_win = {str(r['window_m']): r for r in med['themis'] if r['offset_native_m'] == [0, 0]}

    hls_by_site = {}
    landsat_by_site = {}
    for r in med['optical_and_landsat']:
        if r['status'] == 'measured':
            if r['source'] == 'hls':
                hls_by_site.setdefault(r['site'], []).append(r)
            elif r['source'] == 'landsat':
                landsat_by_site.setdefault(r['site'], []).append(r)

    site_records = []
    for site_meta in SITE_CATALOG:
        sid = site_meta['site_id']
        if 'topo_val_key' in site_meta:
            topo = extract_topography_from_validation(topo_val, site_meta)
        else:
            topo = compute_dem_contract_from_raster(site_meta)

        # Eligibility & surface context
        if site_meta['body'] == 'Mars':
            eligibility = {
                'status': 'planet_boundary_condition',
                'bare_or_sparse_fraction': 1.0,
                'trees_fraction': 0.0,
                'built_fraction': 0.0,
                'permanent_water_fraction': 0.0,
                'water_occurrence_mean_pct': 0.0,
                'water_extent_gt0_fraction': 0.0,
                'water_extent_ge50_fraction': 0.0,
                'ndvi_p50_median_across_dates': None,
                'analog_surface_eligibility': 'mars_reference_surface',
            }
        else:
            wc = wc_by_site.get(sid)
            jrc = jrc_by_site.get(sid)
            if wc and wc['area_weighted']:
                vals = wc['area_weighted']['values']
                bare = vals.get('60', 0.0)
                trees = vals.get('10', 0.0)
                built = vals.get('50', 0.0)
                perm_water = vals.get('80', 0.0)
                snow_ice = vals.get('70', 0.0)
                wc_status = 'measured'
            elif 'topo_val_key' in site_meta and 'land_cover' in topo_val[site_meta['topo_val_key']]:
                c_rows = topo_val[site_meta['topo_val_key']]['land_cover']
                c30 = next(r for r in c_rows if r['cell_m'] == 30 and r['window_m'] == 3000)
                trees = c30['trees']['mean_of_valid_cells']
                perm_water = c30['water']['mean_of_valid_cells']
                bare = max(0.0, 1.0 - trees - perm_water) if sid not in ('bosque-oregon', 'bosque-carolina') else 0.0
                built = 0.0
                snow_ice = 0.0
                wc_status = 'measured'
            else:
                bare = trees = built = perm_water = snow_ice = None
                wc_status = 'on_demand_fetchable'

            if jrc and jrc['area_weighted']:
                jvals = jrc['area_weighted']['values']
                occ_mean = jvals['mean_occurrence_pct']
                occ_gt0 = jvals['area_fraction_occurrence_gt0']
                occ_ge50 = jvals['area_fraction_occurrence_ge50']
            else:
                occ_mean = occ_gt0 = occ_ge50 = None

            hls_rows = hls_by_site.get(sid, [])
            ndvi_vals = [
                r['policies']['0.01_exclude_high_aerosol']['ndvi']['p50']
                for r in hls_rows
                if r['policies']['0.01_exclude_high_aerosol']['ndvi']['valid_fraction'] >= 0.80
            ]
            ndvi_med = float(np.median(ndvi_vals)) if ndvi_vals else None

            if wc_status != 'measured':
                gate = 'pending_on_demand_cover_check'
            elif perm_water is not None and perm_water >= 0.10:
                gate = 'excluded_permanent_water'
            elif trees is not None and trees >= 0.15:
                gate = 'excluded_dense_canopy'
            elif snow_ice is not None and snow_ice >= 0.50:
                gate = 'cryosphere_analog_only'
            elif bare is not None and bare >= 0.85 and (built or 0.0) <= 0.02:
                gate = 'eligible_arid_exposed'
            else:
                gate = 'mixed_cover_contextual'

            eligibility = {
                'status': wc_status,
                'bare_or_sparse_fraction': bare,
                'trees_fraction': trees,
                'built_fraction': built,
                'permanent_water_fraction': perm_water,
                'snow_or_ice_fraction': snow_ice,
                'water_occurrence_mean_pct': occ_mean,
                'water_extent_gt0_fraction': occ_gt0,
                'water_extent_ge50_fraction': occ_ge50,
                'ndvi_p50_median_across_dates': ndvi_med,
                'ndvi_clear_dates_count': len(ndvi_vals),
                'analog_surface_eligibility': gate,
            }

        # Thermal contract
        if site_meta['body'] == 'Mars':
            t18 = themis_by_win['1800']['inertia']
            t30 = themis_by_win['3000']['inertia']
            thermal_contract = {
                'instrument': 'THEMIS_TI',
                'status': 'measured',
                'comparability_tier': 'requires_on_demand_product',
                'window_1800m': {
                    'thermal_inertia_p50': t18['p50'],
                    'thermal_inertia_iqr': t18['iqr'],
                    'thermal_spatial_cv_iqr_over_p50': float(t18['iqr'] / t18['p50']),
                    'valid_fraction': t18['valid_fraction'],
                },
                'window_3000m': {
                    'thermal_inertia_p50': t30['p50'],
                    'thermal_inertia_iqr': t30['iqr'],
                    'thermal_spatial_cv_iqr_over_p50': float(t30['iqr'] / t30['p50']),
                    'valid_fraction': t30['valid_fraction'],
                },
                'cross_planet_bridge_status': 'Requiere par térmico diurno terrestre (ECOSTRESS/MODIS) y albedo para estimar ATI = (1 - A) / ΔT.',
            }
        else:
            l_rows = landsat_by_site.get(sid, [])
            accepted_scenes = []
            for lr in l_rows:
                st = lr['policies']['3']['aggregated_120m']['0.75']
                if st['valid_fraction'] is not None and st['valid_fraction'] >= 0.80:
                    iqr_approx = float((st['p95'] - st['p05']) / 2.0) if st['p95'] is not None and st['p05'] is not None else None
                    accepted_scenes.append({
                        'scene': lr['scene'],
                        'date': lr['acquisition_date'],
                        'lst_p50_k': st['p50'],
                        'lst_p95_minus_p05_k': float(st['p95'] - st['p05']) if st['p95'] is not None else None,
                        'lst_spatial_relative_spread': float((st['p95'] - st['p05']) / st['p50']) if st['p50'] else None,
                        'valid_fraction': st['valid_fraction'],
                        'st_qa_p50_k': lr['policies']['3']['uncertainty_native_k']['p50'],
                    })
            thermal_contract = {
                'instrument': 'Landsat_8_9_TIRS_ST',
                'status': 'measured_instantaneous_lst' if accepted_scenes else ('insufficient_coverage' if l_rows else 'on_demand_fetchable'),
                'comparability_tier': 'planet_specific_constraint',
                'accepted_scenes_count': len(accepted_scenes),
                'scenes': accepted_scenes,
                'seasonal_lst_range_k': (
                    float(max(s['lst_p50_k'] for s in accepted_scenes) - min(s['lst_p50_k'] for s in accepted_scenes))
                    if len(accepted_scenes) >= 2 else None
                ),
                'cross_planet_bridge_status': 'LST instantánea por escena no es equivalente a inercia térmica THEMIS; puente ATI bajo demanda pendiente.',
            }

        # Spectral contract
        if site_meta['body'] == 'Mars':
            spectral_contract = {
                'instrument': 'CRISM_MTR3',
                'by_window': crism_contract,
            }
        elif sid in emit_contract:
            # Select primary scene per window (for Atacama, 20230130T135427 has full mineral diversity; keep all scenes in scenes_evaluated)
            by_win = {}
            for w_str, scenes_list in emit_contract[sid].items():
                primary = scenes_list[-1]
                by_win[w_str] = {
                    'primary_scene': primary,
                    'all_scenes': scenes_list,
                }
            spectral_contract = {
                'instrument': 'EMIT_L2B_MIN',
                'by_window': by_win,
            }
        else:
            spectral_contract = {
                'instrument': 'EMIT_L2B_MIN',
                'status': 'on_demand_fetchable',
                'by_window': None,
                'note': 'Sin escena EMIT local precargada en esta ventana; consultable bajo demanda vía CMR/LP DAAC cuando el sitio supera filtros de etapa 2.',
            }

        surface_spec = surface_dims.load_surface_spec()
        surface_row = surface_dims.extract_surface_dimensions_window(sid, updated_at='2026-11-14T00:00:00Z')
        official_surface_contract = {}
        for dim_name, dim_cols in surface_schema.SURFACE_DIMENSIONS.items():
            d_spec = surface_spec['dimensions'][dim_name]
            primary_src = d_spec['sources']['primary']
            status = surface_row[f'{dim_name}_status'] if site_meta['body'] == 'Earth' else 'unobserved_by_product'
            official_surface_contract[dim_name] = {
                'status': status,
                'comparability_tier': d_spec['comparability_tier'],
                'primary_product_id': primary_src['product_id'],
                'doi': primary_src.get('doi'),
                'valid_fraction': surface_row[f'{dim_name}_valid_fraction'],
                'metrics': {c: surface_row[c] for c in dim_cols},
            }

        site_records.append({
            'site_id': sid,
            'label': site_meta['label'],
            'body': site_meta['body'],
            'stratum': site_meta['stratum'],
            'role': site_meta['role'],
            'lon_lat': site_meta['lon_lat'],
            'topography_contract': topo['scales_by_window'],
            'eligibility_and_water_contract': eligibility,
            'thermal_contract': thermal_contract,
            'spectral_absorption_contract': spectral_contract,
            'official_surface_dimensions_contract': official_surface_contract,
        })

    return {
        'contract_id': spec['contract_id'],
        'version': spec['version'],
        'sites': site_records,
    }


def _compute_block_adjacency_stats(dev_blocks: list[dict], holdout_blocks: list[dict], geod: Geod) -> dict:
    """Checks orthogonal and diagonal (Chebyshev <= 1 deg) adjacency within the same basin."""
    adjacent_pairs = []
    min_dist_km = float('inf')
    for db in dev_blocks:
        dlon, dlat = db['centroid_lon_lat']
        for hb in holdout_blocks:
            hlon, hlat = hb['centroid_lon_lat']
            _, _, dist_m = geod.inv(dlon, dlat, hlon, hlat)
            min_dist_km = min(min_dist_km, dist_m / 1000.0)
            if (
                db['area_id'] == hb['area_id']
                and max(abs(db['lon_min'] - hb['lon_min']), abs(db['lat_min'] - hb['lat_min'])) <= 1
            ):
                adjacent_pairs.append([db['block_id'], hb['block_id']])
    return {
        'adjacent_dev_holdout_block_pairs': adjacent_pairs,
        'adjacent_dev_holdout_block_pairs_count': len(adjacent_pairs),
        'min_dev_to_holdout_centroid_distance_km': round(min_dist_km, 2) if dev_blocks and holdout_blocks else None,
    }


def partition_spatial_blocks(spec: dict) -> dict:
    """Assigns leak-free spatial blocks (whole-basin primary + 1-block Chebyshev buffer secondary)."""
    p4 = json.loads(PHASE4_CANDIDATES.read_text())
    candidates = p4['candidates']
    policy = spec['spatial_partition_policy']
    holdout_basins = set(policy.get('holdout_basins', ['mojave']))
    legacy_holdout = set(policy.get('legacy_holdout_blocks', []))
    buffer_blocks = set(policy.get('buffer_blocks_1deg_chebyshev', []))
    buffered_dev_ids = set(policy.get('buffered_development_blocks', []))
    geod = Geod(ellps='WGS84')

    blocks = {}
    for c in candidates:
        lon, lat = c['longitude'], c['latitude']
        area_id = c['area_id']
        bx = int(math.floor(lon))
        by = int(math.floor(lat))
        bkey = f'{area_id}:{bx:+04d}_{by:+03d}'
        blocks.setdefault(bkey, {
            'block_id': bkey,
            'area_id': area_id,
            'lon_min': bx,
            'lat_min': by,
            'windows': [],
            'lats': [],
            'lons': [],
        })
        blocks[bkey]['windows'].append(c)
        blocks[bkey]['lats'].append(lat)
        blocks[bkey]['lons'].append(lon)

    by_area = {}
    all_blocks = []
    for bkey, binfo in sorted(blocks.items()):
        binfo['window_count'] = len(binfo['windows'])
        binfo['centroid_lon_lat'] = [float(np.mean(binfo['lons'])), float(np.mean(binfo['lats']))]
        binfo['in_legacy_holdout'] = bkey in legacy_holdout
        by_area.setdefault(binfo['area_id'], []).append(binfo)
        all_blocks.append(binfo)

    # Primary leak-free partition: reserve full basin(s) (`mojave`, 279 windows = 28.67%).
    dev_windows, holdout_windows = [], []
    strict_no_legacy_dev_windows = []
    buffered_dev_windows = []
    block_summaries = []
    dev_block_objs, hold_block_objs = [], []
    legacy_dev_objs, legacy_hold_objs = [], []
    buf_dev_objs, buf_hold_objs, buf_mid_objs = [], [], []

    for b in sorted(all_blocks, key=lambda x: x['block_id']):
        bkey = b['block_id']
        if b['area_id'] in holdout_basins:
            b['split'] = 'holdout'
            holdout_windows.extend(b['windows'])
            hold_block_objs.append(b)
        else:
            b['split'] = 'development'
            dev_windows.extend(b['windows'])
            dev_block_objs.append(b)
            if not b['in_legacy_holdout']:
                strict_no_legacy_dev_windows.extend(b['windows'])

        if b['in_legacy_holdout']:
            legacy_hold_objs.append(b)
        else:
            legacy_dev_objs.append(b)

        if bkey in buffered_dev_ids:
            buf_split = 'development'
            buffered_dev_windows.extend(b['windows'])
            buf_dev_objs.append(b)
        elif bkey in buffer_blocks:
            buf_split = 'buffer_excluded'
            buf_mid_objs.append(b)
        else:
            buf_split = 'holdout'
            buf_hold_objs.append(b)

        block_summaries.append({
            'block_id': bkey,
            'area_id': b['area_id'],
            'split': b['split'],
            'buffered_scheme_split': buf_split,
            'in_legacy_holdout': b['in_legacy_holdout'],
            'window_count': b['window_count'],
            'centroid_lon_lat': b['centroid_lon_lat'],
        })

    primary_adj = _compute_block_adjacency_stats(dev_block_objs, hold_block_objs, geod)
    legacy_adj = _compute_block_adjacency_stats(legacy_dev_objs, legacy_hold_objs, geod)
    buffered_adj = _compute_block_adjacency_stats(buf_dev_objs, buf_hold_objs, geod)
    strict_dev_objs = [b for b in dev_block_objs if not b['in_legacy_holdout']]
    strict_adj = _compute_block_adjacency_stats(strict_dev_objs, hold_block_objs, geod)

    # Compute inter-basin distances (Utah vs Mojave vs Atacama)
    area_centroids = {}
    for area_id, blist in by_area.items():
        lons = [w['longitude'] for b in blist for w in b['windows']]
        lats = [w['latitude'] for b in blist for w in b['windows']]
        area_centroids[area_id] = (float(np.mean(lons)), float(np.mean(lats)))

    inter_area_distances_km = {}
    area_keys = sorted(area_centroids.keys())
    for i in range(len(area_keys)):
        for j in range(i + 1, len(area_keys)):
            a1, a2 = area_keys[i], area_keys[j]
            lon1, lat1 = area_centroids[a1]
            lon2, lat2 = area_centroids[a2]
            _, _, dist_m = geod.inv(lon1, lat1, lon2, lat2)
            inter_area_distances_km[f'{a1}_vs_{a2}'] = round(dist_m / 1000.0, 2)

    return {
        'strategy': policy['strategy'],
        'primary_mode': policy['primary_mode'],
        'holdout_basins': sorted(holdout_basins),
        'total_screening_windows': len(candidates),
        'development_windows_count': len(dev_windows),
        'holdout_windows_count': len(holdout_windows),
        'holdout_fraction': round(len(holdout_windows) / len(candidates), 4),
        'blocks_count': len(block_summaries),
        'development_blocks_count': len(dev_block_objs),
        'holdout_blocks_count': len(hold_block_objs),
        **primary_adj,
        'inter_basin_distances_km': inter_area_distances_km,
        'min_inter_basin_distance_km': min(inter_area_distances_km.values()),
        'strict_basin_dev_no_legacy_holdout': {
            'development_windows_count': len(strict_no_legacy_dev_windows),
            'development_blocks_count': len(strict_dev_objs),
            'legacy_holdout_blocks_excluded': sorted(legacy_holdout & {b['block_id'] for b in all_blocks if b['area_id'] not in holdout_basins}),
            **strict_adj,
        },
        'buffered_block_scheme': {
            'scheme_id': 'chebyshev_1block_buffer_v1',
            'development_windows_count': len(buffered_dev_windows),
            'development_blocks_count': len(buf_dev_objs),
            'buffer_windows_count': sum(b['window_count'] for b in buf_mid_objs),
            'buffer_blocks_count': len(buf_mid_objs),
            'holdout_windows_count': sum(b['window_count'] for b in buf_hold_objs),
            'holdout_blocks_count': len(buf_hold_objs),
            'unfrozen_prior_holdout_blocks_count': 0,
            **buffered_adj,
        },
        'leakage_audit_prior_within_basin_split': {
            'development_windows_count': sum(b['window_count'] for b in legacy_dev_objs),
            'holdout_windows_count': sum(b['window_count'] for b in legacy_hold_objs),
            **legacy_adj,
        },
        'blocks': block_summaries,
        '_dev_windows': dev_windows,
        '_holdout_windows': holdout_windows,
        '_strict_no_legacy_dev_windows': strict_no_legacy_dev_windows,
        '_buffered_dev_windows': buffered_dev_windows,
    }


def _corr_pair(a, b) -> dict:
    rho, _ = spearmanr(a, b)
    r, _ = pearsonr(a, b)
    return {'spearman_rho': round(float(rho), 4), 'pearson_r': round(float(r), 4), 'n': len(a)}


def _compute_regional_collinearity(windows: list[dict]) -> dict:
    """Computes Spearman/Pearson collinearity at 300 m and 600 m over a window list."""
    rel_300, p10_300, p50_300, p90_300 = [], [], [], []
    rel_600, p50_600, p90_600 = [], [], []
    for w in windows:
        m300 = next(m for m in w['metrics'] if m['cell_m'] == 300)
        m600 = next(m for m in w['metrics'] if m['cell_m'] == 600)
        if m300['relief_p95_p5_m'] is not None and m600['relief_p95_p5_m'] is not None:
            rel_300.append(m300['relief_p95_p5_m'])
            p10_300.append(m300['slope_quantiles_deg']['p10'])
            p50_300.append(m300['slope_quantiles_deg']['p50'])
            p90_300.append(m300['slope_quantiles_deg']['p90'])
            rel_600.append(m600['relief_p95_p5_m'])
            p50_600.append(m600['slope_quantiles_deg']['p50'])
            p90_600.append(m600['slope_quantiles_deg']['p90'])

    return {
        'sample_size_development_windows': len(rel_300),
        'pairs': {
            'relief_300m_vs_slope_p90_300m': _corr_pair(rel_300, p90_300),
            'relief_300m_vs_slope_p50_300m': _corr_pair(rel_300, p50_300),
            'slope_p50_300m_vs_slope_p90_300m': _corr_pair(p50_300, p90_300),
            'slope_p10_300m_vs_slope_p50_300m': _corr_pair(p10_300, p50_300),
            'relief_300m_vs_relief_600m': _corr_pair(rel_300, rel_600),
            'slope_p50_300m_vs_slope_p50_600m': _corr_pair(p50_300, p50_600),
            'slope_p90_300m_vs_slope_p90_600m': _corr_pair(p90_300, p90_600),
        },
    }


def analyze_selection_and_redundancy(spec: dict, contract_data: dict, partition: dict) -> dict:
    """Computes collinearity on leak-free development windows, sensor stability ratios, and formal feature decisions."""
    dev_windows = partition.pop('_dev_windows')
    _ = partition.pop('_holdout_windows')  # Frozen for Step 7; never used to select features!
    strict_dev_windows = partition.pop('_strict_no_legacy_dev_windows')
    buffered_dev_windows = partition.pop('_buffered_dev_windows')

    # 1. Collinearity on leak-free regional development windows
    regional_collinearity = _compute_regional_collinearity(dev_windows)
    sensitivity_by_partition = {
        'whole_basin_holdout': regional_collinearity,
        'whole_basin_excluding_legacy_holdout': _compute_regional_collinearity(strict_dev_windows),
        'buffered_1block_holdout': _compute_regional_collinearity(buffered_dev_windows),
    }

    # 2. High-resolution (30 m) collinearity across the 11 contract sites (3000 m window, 30 m cell)
    sites_30m = contract_data['sites']
    rel_30, s240_p50, s240_p90, r360_p50 = [], [], [], []
    for s in sites_30m:
        t30 = s['topography_contract']['3000']['30']
        if all(t30.get(k) is not None for k in ('relief_p95_p05_m', 'slope_240m_p50_deg', 'slope_240m_p90_deg', 'roughness_360m_p50_m')):
            rel_30.append(t30['relief_p95_p05_m'])
            s240_p50.append(t30['slope_240m_p50_deg'])
            s240_p90.append(t30['slope_240m_p90_deg'])
            r360_p50.append(t30['roughness_360m_p50_m'])

    highres_collinearity = {
        'sample_size_sites_30m': len(rel_30),
        'pairs': {
            'relief_30m_vs_slope_240m_p50': _corr_pair(rel_30, s240_p50),
            'relief_30m_vs_slope_240m_p90': _corr_pair(rel_30, s240_p90),
            'slope_240m_p50_vs_slope_240m_p90': _corr_pair(s240_p50, s240_p90),
            'slope_240m_p50_vs_roughness_360m_p50': _corr_pair(s240_p50, r360_p50),
            'relief_30m_vs_roughness_360m_p50': _corr_pair(rel_30, r360_p50),
        },
    }

    # 3. Inter-sensor stability and Signal-to-Sensor-Noise Ratio (SNR_sensor) from the 168-configuration validation
    topo_val = json.loads(TOPO_VAL_PATH.read_text())
    sensor_stability = []
    inter_site_relief_span = max(rel_30) - min(rel_30)
    inter_site_slope_span = max(s240_p50) - min(s240_p50)
    inter_site_rough_span = max(r360_p50) - min(r360_p50)

    for key, block in topo_val.items():
        pol = block['primary_policy']
        rows = [r for r in block['measurements'] if r['window_m'] == 3000 and r['cell_m'] == 30 and r.get('policy', 'sin_mascara') == pol]
        rel_r = next(r for r in rows if r['descriptor'] == 'relief')
        s60_r = next(r for r in rows if r['descriptor'] == 'slope' and r['setting_m'] == 60)
        s240_r = next(r for r in rows if r['descriptor'] == 'slope' and r['setting_m'] == 240)
        r360_r = next(r for r in rows if r['descriptor'] == 'roughness' and r['setting_m'] == 360)

        rel_delta_glo = abs(rel_r['statistics']['GLO-30']['p95_minus_p05'] - rel_r['statistics']['3DEP']['p95_minus_p05'])
        s60_delta_glo = s60_r['paired_against_3dep']['GLO-30']['median_absolute']
        s240_delta_glo = s240_r['paired_against_3dep']['GLO-30']['median_absolute']
        r360_delta_glo = r360_r['paired_against_3dep']['GLO-30']['median_absolute']
        reduction_pct = 100.0 * (1.0 - s240_delta_glo / s60_delta_glo)

        sensor_stability.append({
            'control_id': key,
            'policy': pol,
            'relief_abs_delta_glo30_vs_3dep_m': round(rel_delta_glo, 4),
            'slope_60m_abs_delta_glo30_vs_3dep_deg': round(s60_delta_glo, 4),
            'slope_240m_abs_delta_glo30_vs_3dep_deg': round(s240_delta_glo, 4),
            'slope_discrepancy_reduction_240m_vs_60m_pct': round(reduction_pct, 2),
            'roughness_360m_abs_delta_glo30_vs_3dep_m': round(r360_delta_glo, 4),
            'roughness_360m_common_fraction': round(r360_r['common_fraction'], 4),
            'snr_relief_inter_stratum_over_sensor_delta': round(inter_site_relief_span / max(rel_delta_glo, 0.01), 2),
            'snr_slope_240m_inter_stratum_over_sensor_delta': round(inter_site_slope_span / max(s240_delta_glo, 0.01), 2),
            'snr_roughness_360m_inter_stratum_over_sensor_delta': round(inter_site_rough_span / max(r360_delta_glo, 0.01), 2),
        })

    # 4. On-demand architecture & benchmark summary from specs/sources/contexto-atlas-2024.json and pipelines/atlas_topography.py
    ctx_spec = json.loads(CONTEXT_SPEC.read_text())
    on_demand_summary = {
        'policy_id': spec['on_demand_query_policy']['policy_id'],
        'modes_supported': ['auto', 'range', 'cache'],
        'cache_budget_gb': 100,
        'published_partition_blocks': len(ctx_spec.get('partition', [])),
        'empirical_benchmarks': {
            'regional_screening_gmted75': {
                'windows_evaluated': 973,
                'elapsed_seconds': 9.3,
                'ms_per_window': 9.56,
            },
            'http_206_range_read_glo30_100km_block': {
                'block_id': 'arido-n38w111',
                'elapsed_seconds': 16.35,
                'transferred_mb': 38.46,
                'http_206_requests': 23,
                'equivalent_3km_window_with_halo_mb': 0.42,
            },
            'verified_local_cache_100km_block': {
                'elapsed_seconds_range': [5.15, 5.70],
            },
        },
    }

    # 5. Formal feature selection decisions
    feature_decisions = [
        {
            'feature_id': 'relief_p95_p05_m',
            'dimension': 'topography',
            'decision': 'approved_for_ranking',
            'comparability_tier': 'direct_metric',
            'quantitative_evidence': 'Discrepancia GLO-30 vs. 3DEP de solo 0,28 m en desierto (SNR > 1000 frente al rango inter-estrato de 840 m); separa abanicos sedimentarios (27–82 m) de alta montaña (845 m) y meseta polar (5,5 m).',
        },
        {
            'feature_id': 'slope_240m_p50_deg',
            'dimension': 'topography',
            'decision': 'approved_for_ranking',
            'comparability_tier': 'direct_metric',
            'quantitative_evidence': 'Reducir la derivada a una base explícita de 240 m disminuye entre 51,1 % y 73,7 % el error entre DEM (a 0,05° en Utah) manteniendo la estructura morfológica regional.',
        },
        {
            'feature_id': 'slope_240m_p90_deg',
            'dimension': 'topography',
            'decision': 'approved_for_ranking',
            'comparability_tier': 'direct_metric',
            'quantitative_evidence': 'Capta escarpes y bordes de canal dentro de la ventana que la mediana atenúa (en Jezero 3 km: p50 = 2,13°, p90 = 5,48°; correlación regional con p50 ρ = 0,94 pero necesaria para colas asimétricas).',
        },
        {
            'feature_id': 'roughness_360m_p50_m',
            'dimension': 'topography',
            'decision': 'approved_conditional',
            'comparability_tier': 'direct_metric',
            'quantitative_evidence': 'Estable en desierto sin vegetación (Δ = 0,03 m frente a 3DEP en Utah; Jezero = 1,75 m a 30 m), pero cae a 3,24 % de soporte en costas recortadas y sube >2 m por dosel arbóreo. Se activa solo cuando roughness_coverage >= 0,80 y trees_fraction <= 0,05.',
        },
        {
            'feature_id': 'slope_immediate_60m_deg',
            'dimension': 'topography',
            'decision': 'reformulated_into_contract',
            'comparability_tier': 'direct_metric',
            'quantitative_evidence': 'Sustituida como variable primaria por slope_240m_* porque a 60 m de base el ruido de sensor entre GLO-30/SRTM y 3DEP es de 2x a 3,8x mayor.',
        },
        {
            'feature_id': 'laplacian_curvature',
            'dimension': 'topography',
            'decision': 'discarded',
            'comparability_tier': 'direct_metric',
            'quantitative_evidence': 'Segunda derivada discreta de 4 vecinos altamente sensible al paso de rejilla (cambia un orden de magnitud entre 30, 60 y 120 m) y al ruido de cuantización del DEM.',
        },
        {
            'feature_id': 'topographic_position_tpi',
            'dimension': 'topography',
            'decision': 'reformulated_into_contract',
            'comparability_tier': 'direct_metric',
            'quantitative_evidence': 'Su mediana sobre ventana completa tiende a 0 m por construcción matemática; su dispersión local ya queda recogida por roughness_360m_p50_m e iqr.',
        },
        {
            'feature_id': 'abs_fe3_oxide_0p53_0p90um',
            'dimension': 'spectral_absorption',
            'decision': 'approved_as_context_only',
            'comparability_tier': 'functional_contract_bridge',
            'quantitative_evidence': 'Puente funcional entre CRISM BD530_2 (Jezero p50 = 0,144, p95 = 0,156) y EMIT Grupo 1 óxidos férricos (Atacama p50 = 0,106, p95 = 0,149; Utah p50 = 0,141, p95 = 0,163; 100 % de muestras minerales Grupo 1). Decisión revisada el 14/11/2026: los p50/p95 de CRISM son parámetros de banda continuos sobre toda la huella (IN = 0) y los de EMIT L2B son profundidades del mejor ajuste de biblioteca entre muestras identificadas; las fracciones tampoco comparten denominador ni umbral. Queda como contexto hasta calcular los mismos parámetros CRISM sobre reflectancia EMIT L2A.',
        },
        {
            'feature_id': 'abs_al_oh_2p20um',
            'dimension': 'spectral_absorption',
            'decision': 'approved_as_context_only',
            'comparability_tier': 'functional_contract_bridge',
            'quantitative_evidence': 'Conecta CRISM D2200/BD2210_2 (Jezero p95 = 0,0084) con filosilicatos de Al-OH en EMIT Grupo 2 (Utah: 99,6 % moscovita/illita + caolinita, n = 1590, p95 = 0,043; Atacama: 29,8 % montmorillonita + caolinita, n = 211, p95 = 0,051). Decisión revisada el 14/11/2026: los p50/p95 de CRISM son parámetros de banda continuos sobre toda la huella (IN = 0) y los de EMIT L2B son profundidades del mejor ajuste de biblioteca entre muestras identificadas; las fracciones tampoco comparten denominador ni umbral. Queda como contexto hasta calcular los mismos parámetros CRISM sobre reflectancia EMIT L2A.',
        },
        {
            'feature_id': 'abs_fe_mg_oh_2p30um',
            'dimension': 'spectral_absorption',
            'decision': 'approved_as_context_only',
            'comparability_tier': 'functional_contract_bridge',
            'quantitative_evidence': 'Conecta CRISM D2300/BD2290 (Jezero p95 = 0,0121, firma clave de esmectita Fe/Mg en el abanico) con esmectitas/cloritas de EMIT Grupo 2 (Atacama: 1,8 %, n = 13 < 30 → insufficient_complex_sample; Utah: n = 1 < 30 → insufficient_complex_sample). Decisión revisada el 14/11/2026: los p50/p95 de CRISM son parámetros de banda continuos sobre toda la huella (IN = 0) y los de EMIT L2B son profundidades del mejor ajuste de biblioteca entre muestras identificadas; las fracciones tampoco comparten denominador ni umbral. Queda como contexto hasta calcular los mismos parámetros CRISM sobre reflectancia EMIT L2A.',
        },
        {
            'feature_id': 'abs_carbonate_2p30_2p50um',
            'dimension': 'spectral_absorption',
            'decision': 'approved_as_context_only',
            'comparability_tier': 'functional_contract_bridge',
            'quantitative_evidence': 'Conecta CRISM MIN2295_2480/BD2500_2 (Jezero p95 = +0,0013, max = +0,0087, 7,3 % de píxeles activos > 0) con carbonatos de EMIT Grupo 2 (Atacama: 43,1 % aragonito/dolomita/calcita, n = 305, p95 = 0,041; Utah: n = 5 < 30 → insufficient_complex_sample). Decisión revisada el 14/11/2026: los p50/p95 de CRISM son parámetros de banda continuos sobre toda la huella (IN = 0) y los de EMIT L2B son profundidades del mejor ajuste de biblioteca entre muestras identificadas; las fracciones tampoco comparten denominador ni umbral. Queda como contexto hasta calcular los mismos parámetros CRISM sobre reflectancia EMIT L2A.',
        },
        {
            'feature_id': 'abs_hydrated_sioh_so4_1p9_2p26um',
            'dimension': 'spectral_absorption',
            'decision': 'approved_as_context_only',
            'comparability_tier': 'functional_contract_bridge',
            'quantitative_evidence': 'Conecta CRISM BD1900R2/BD2265 (Jezero p95 = 0,0074, max = 0,0302) con sílice hidratada y sulfatos en EMIT Grupo 2 (Atacama: 25,2 % calcedonia/vidrio basáltico hidratado + jarosita, n = 178, p95 = 0,061; Utah: 0 %, n = 0). Decisión revisada el 14/11/2026: los p50/p95 de CRISM son parámetros de banda continuos sobre toda la huella (IN = 0) y los de EMIT L2B son profundidades del mejor ajuste de biblioteca entre muestras identificadas; las fracciones tampoco comparten denominador ni umbral. Queda como contexto hasta calcular los mismos parámetros CRISM sobre reflectancia EMIT L2A.',
        },
        {
            'feature_id': 'abs_mafic_fe2_1p0um',
            'dimension': 'spectral_absorption',
            'decision': 'approved_conditional',
            'comparability_tier': 'requires_on_demand_product',
            'quantitative_evidence': 'Medido en Marte por CRISM OLINDEX3 (Jezero p50 = 0,121, p95 = 0,140); en Tierra queda tipado como unobserved_by_product en EMIT L2B y se evalúa bajo demanda cuando se consulta reflectancia EMIT L2A a 1,0 µm.',
        },
        {
            'feature_id': 'emit_library_match_fraction_raw_ids',
            'dimension': 'spectral_absorption',
            'decision': 'reformulated_into_contract',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Reemplazada para búsqueda por los 6 complejos funcionales de absorción y la exclusión de coincidencias no minerales (Orgánico o sintético = 861 muestras en Atacama); la agrupación reduce la entropía de 2,39 bits a complejos minerales estables.',
        },
        {
            'feature_id': 'worldcover_bare_trees_built_water_fractions',
            'dimension': 'surface_eligibility_and_water',
            'decision': 'approved_as_eligibility_filter',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Error de muestreo <= 0,22 pp frente a intersección exacta en LAEA; actúa como compuerta de elegibilidad terrestre versionada por escenario en pipelines/etl_eligibility.py (perfil por defecto arid_mars_surface_v2: bare_or_sparse >= 0,85, trees <= 0,05, built <= 0,02, nieve/hielo <= 0,05 y agua <= 0,02 como máximo entre agua permanente de WorldCover y ocurrencia JRC >= 50 %).',
        },
        {
            'feature_id': 'jrc_water_occurrence_and_extent',
            'dimension': 'surface_eligibility_and_water',
            'decision': 'approved_as_eligibility_filter',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Distingue cuencas secas (0,00 % en Atacama, 0,02 % extensión >0 % en Utah) de cuerpos permanentes (32,8 % >=50 % en costa Carolina) y humedales estacionales (7,5 pp intermitentes).',
        },
        {
            'feature_id': 'hls_ndvi_p50',
            'dimension': 'surface_eligibility_and_water',
            'decision': 'approved_as_context_only',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Concordancia L30-S30 del mismo día (Δp50 <= 0,008), pero en desierto el rango estacional (0,065–0,146) es del orden del P95 inter-sensor (0,028); útil para confirmar ausencia de brotes vegetativos por escena, no para ordenar desiertos.',
        },
        {
            'feature_id': 'hls_ndmi_p50',
            'dimension': 'surface_eligibility_and_water',
            'decision': 'discarded',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'En suelo árido responde a diferencias de reflectancia mineral en SWIR1 (1,6 µm) e invierte el orden físico entre costa hiperárida y desierto interior.',
        },
        {
            'feature_id': 'themis_ti_and_landsat_lst',
            'dimension': 'thermal_response',
            'decision': 'approved_as_context_only',
            'comparability_tier': 'requires_on_demand_product',
            'quantitative_evidence': 'THEMIS TI es muy estable en Jezero (253,2 J m⁻² K⁻¹ s⁻¹/² a 1,8 km; Δ <= 0,87 ante traslación de 100 m), mientras Landsat LST varía 38,1 K entre invierno y verano en Utah. No se mezclan en distancia hasta calcular ATI diurna bajo demanda.',
        },
        {
            'feature_id': 'precip_mean_annual_mm_and_dry_months',
            'dimension': 'aridity',
            'decision': 'on_demand_contract_ready',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Contrato formalizado en enrichment_surface con GPM IMERG v07B (DOI 10.5067/GPM/IMERGDF/DAY/07, ~0,1°) y contraste JAXA GSMaP v8; cobertura mínima >= 80 % para restringir aridez climática sin penalizar ventanas no consultadas.',
        },
        {
            'feature_id': 'smap_sm_p50_and_p90_m3m3',
            'dimension': 'soil_moisture',
            'decision': 'on_demand_contract_ready',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Sustituye la ambigüedad de NDMI por humedad volumétrica radiométrica SPL3SMP_E.006 a 9 km (DOI 10.5067/4DQ54OUIJ9DL) filtrada por bit 0 de retrieval_qual_flag y cobertura válida >= 80 %.',
        },
        {
            'feature_id': 'mod10a1_snow_and_clear_days_fraction',
            'dimension': 'snow_persistence',
            'decision': 'on_demand_contract_ready',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Supera las detecciones aisladas de Fmask con series diarias MODIS MOD10A1.061 a 500 m (DOI 10.5067/MODIS/MOD10A1.061, NDSI en [0, 100] y Basic QA <= 1) y contraste SGLI SICE 250 m.',
        },
        {
            'feature_id': 'cci_permafrost_probability_and_alt_m',
            'dimension': 'permafrost',
            'decision': 'on_demand_contract_ready',
            'comparability_tier': 'planet_specific_constraint',
            'quantitative_evidence': 'Integra ESA CCI Permafrost v5.0 desde ESA Open Science Catalog (DOI 10.5285/6ef1a60b678f4048a20b5c8d94d665c9, 1 km, 1997-2023) para caracterización criosférica terrestre sin equipararla con hielo lunar.',
        },
        {
            'feature_id': 'aster_emissivity_mafic_index_and_cf_um',
            'dimension': 'thermal_emissivity',
            'decision': 'on_demand_contract_ready',
            'comparability_tier': 'functional_contract_bridge',
            'quantitative_evidence': 'Adaptador ASTER GED v3 (AG100.003, 100 m, bandas 8,3-11,3 µm, DOI 10.5067/Community/ASTER_GED/AG100.003) hacia el rasgo de Christiansen de LRO Diviner y la emisividad térmica THEMIS.',
        },
        {
            'feature_id': 's1_rtc_vv_vh_sigma0_and_ratio_db',
            'dimension': 'sar_backscatter',
            'decision': 'on_demand_contract_ready',
            'comparability_tier': 'functional_contract_bridge',
            'quantitative_evidence': 'Adaptador Sentinel-1 RTC (OPERA_L2_RTC-S1_V1 / CDSE, 20 m, DOI 10.5067/SNWG/OPERA_L2_RTC-S1_V1) con máscara de layover/sombra para rugosidad decamétrica y puente hacia Mini-RF.',
        },
    ]

    return {
        'spatial_partition': partition,
        'regional_collinearity_development': regional_collinearity,
        'sensitivity_by_partition_scheme': sensitivity_by_partition,
        'highres_collinearity_30m': highres_collinearity,
        'sensor_and_scale_stability': sensor_stability,
        'on_demand_architecture': on_demand_summary,
        'feature_selection_decisions': feature_decisions,
    }


def plot_contract_and_selection(contract_data: dict, selection_data: dict) -> None:
    """Renders a 3-panel summary figure for Entrega 3."""
    fig, (ax_topo, ax_spec, ax_stab) = plt.subplots(1, 3, figsize=(15.2, 5.2), layout='constrained')

    # Panel A: Topographic contract space (Relief vs Slope 240m P50 at 30m cell, 3000m window)
    role_colors = {
        'reference': ('#c84b31', 'D', 95, 'Referencia Marte (Jezero)'),
        'positive_analog_candidate': ('#d9822b', 'o', 75, 'Candidatas áridas (Tierra)'),
        'morphological_contrast': ('#2b7a78', 's', 65, 'Escarpe/contraste árido'),
        'negative_control_canopy': ('#3a7d44', '^', 70, 'Control negativo: dosel'),
        'negative_control_relief_and_cover': ('#6b56a7', 'v', 70, 'Control negativo: alta montaña'),
        'negative_control_water': ('#2879ac', 'P', 75, 'Control negativo: agua/costa'),
        'cryosphere_control': ('#7f8c8d', 'X', 70, 'Control criosférico'),
    }
    plotted_roles = set()
    for site in contract_data['sites']:
        t30 = site['topography_contract']['3000']['30']
        rel = t30['relief_p95_p05_m']
        slp = t30['slope_240m_p50_deg']
        role = site['role']
        color, marker, size, rlabel = role_colors[role]
        lbl = rlabel if role not in plotted_roles else None
        plotted_roles.add(role)
        ax_topo.scatter(slp, rel, c=color, marker=marker, s=size, label=lbl, zorder=4, edgecolors='black', linewidths=0.5)
        short = site['site_id'].replace('mars-jezero-fan', 'Jezero (3 km)').replace('atacama-materiales', 'Atacama').replace('sahara-sahel', 'Sahel')
        offsets = {
            'mars-jezero-fan': (-56, -12),
            'costa': (6, 5),
            'bosque-carolina': (-34, -14),
            'bosque-oregon': (5, 5),
            'tropico': (6, -4),
            'sahara-sahel': (5, 5),
            'costa-carolina': (6, -8),
        }
        dx, dy = offsets.get(site['site_id'], (5, 4))
        ax_topo.annotate(short, (slp, rel), xytext=(dx, dy), textcoords='offset points', fontsize=7.8)

    # Also plot Jezero 1.8 km for reference
    jez = next(s for s in contract_data['sites'] if s['site_id'] == 'mars-jezero-fan')
    j18 = jez['topography_contract']['1800']['30']
    ax_topo.scatter(j18['slope_240m_p50_deg'], j18['relief_p95_p05_m'], c='#c84b31', marker='D', s=65, alpha=0.65, edgecolors='black', linewidths=0.5)
    ax_topo.annotate('Jezero (1,8 km)', (j18['slope_240m_p50_deg'], j18['relief_p95_p05_m']), xytext=(5, -9), textcoords='offset points', fontsize=7.5, color='#8a2be2')

    ax_topo.set_yscale('log')
    ax_topo.set_xlabel('Pendiente mediana a base fija de 240 m (°)')
    ax_topo.set_ylabel('Relieve P95–P05 en ventana (m, escala log)')
    ax_topo.set_title('A. Contrato topográfico común (celda 30 m)')
    ax_topo.grid(True, alpha=0.22)
    ax_topo.legend(frameon=False, fontsize=7.4, loc='lower right')

    # Panel B: Spectral absorption contract comparison (Jezero CRISM vs Atacama & Utah EMIT)
    complex_labels = [
        ('abs_fe3_oxide_0p53_0p90um', 'Fe³⁺\n0,53–0,9 µm'),
        ('abs_al_oh_2p20um', 'Al-OH\n2,20 µm'),
        ('abs_fe_mg_oh_2p30um', 'Fe/Mg-OH\n2,30 µm'),
        ('abs_carbonate_2p30_2p50um', 'CO₃²⁻\n2,3–2,5 µm'),
        ('abs_hydrated_sioh_so4_1p9_2p26um', 'Si-OH/H₂O\n1,9–2,26 µm'),
        ('abs_mafic_fe2_1p0um', 'Fe²⁺ máfico\n1,0 µm'),
    ]
    jez_spec = jez['spectral_absorption_contract']['by_window']['1800']['complexes']
    utah_spec = next(s for s in contract_data['sites'] if s['site_id'] == 'desierto')['spectral_absorption_contract']['by_window']['3000']['primary_scene']['complexes']
    atac_spec = next(s for s in contract_data['sites'] if s['site_id'] == 'atacama-materiales')['spectral_absorption_contract']['by_window']['3000']['primary_scene']['complexes']

    x = np.arange(len(complex_labels))
    w = 0.25
    j_vals = [max(0.0, (jez_spec[k]['strength_p95'] or 0.0)) for k, _ in complex_labels]
    a_vals = [max(0.0, (atac_spec[k]['strength_p95'] or 0.0)) for k, _ in complex_labels]
    u_vals = [max(0.0, (utah_spec[k]['strength_p95'] or 0.0)) for k, _ in complex_labels]

    ax_spec.bar(x - w, j_vals, width=w, color='#c84b31', label='Jezero · CRISM (p95 índice)')
    ax_spec.bar(x, a_vals, width=w, color='#d9822b', label='Atacama · EMIT L2B (p95 prof.)')
    ax_spec.bar(x + w, u_vals, width=w, color='#2b7a78', label='Utah · EMIT L2B (p95 prof.)')
    ax_spec.set_xticks(x, [lbl for _, lbl in complex_labels], fontsize=7.8)
    ax_spec.set_ylabel('Intensidad de absorción P95 en el contrato (1)')
    ax_spec.set_title('B. Contrato espectral por complejo funcional')
    ax_spec.grid(axis='y', alpha=0.22)
    ax_spec.legend(frameon=False, fontsize=7.8, loc='upper right')

    # Panel C: DEM Sensor discrepancy reduction (60 m immediate base vs 240 m fixed base)
    stab = selection_data['sensor_and_scale_stability']
    c_names = [s['control_id'].replace('desierto-utah', 'Utah\ndesierto').replace('bosque-oregon', 'Oregón\nbosque')
               .replace('bosque-carolina', 'Carolina\nbosque').replace('costa-carolina', 'Carolina\ncosta') for s in stab]
    d60 = [s['slope_60m_abs_delta_glo30_vs_3dep_deg'] for s in stab]
    d240 = [s['slope_240m_abs_delta_glo30_vs_3dep_deg'] for s in stab]
    xc = np.arange(len(c_names))
    ax_stab.bar(xc - 0.18, d60, width=0.34, color='#95a5a6', label='Base inmediata 60 m')
    ax_stab.bar(xc + 0.18, d240, width=0.34, color='#1f618d', label='Base física fija 240 m (aprobada)')
    for idx, s in enumerate(stab):
        red = s['slope_discrepancy_reduction_240m_vs_60m_pct']
        ax_stab.text(idx + 0.18, d240[idx] + 0.06, f'-{red:.0f}%', ha='center', fontsize=7.8, fontweight='bold', color='#1f618d')
    ax_stab.set_xticks(xc, c_names, fontsize=8)
    ax_stab.set_ylabel('Error absoluto mediano |GLO-30 − 3DEP| (°)')
    ax_stab.set_title('C. Estabilidad entre sensores (Paso 5)')
    ax_stab.set_ylim(0, max(d60) * 1.18)
    ax_stab.grid(axis='y', alpha=0.22)
    ax_stab.legend(frameon=False, fontsize=8, loc='upper left')

    for ax in (ax_topo, ax_spec, ax_stab):
        ax.spines[['right', 'top']].set_visible(False)

    fig.suptitle('Entrega 3: Contrato común multi-instrumento y selección de características', fontweight='bold')
    fig.savefig(OUT / 'comparabilidad-e-instrumentos.png', dpi=170)
    plt.close(fig)


def evaluate_on_demand_window_contract(lon: float, lat: float, window_m: int = 3000, mode: str = 'auto') -> dict:
    """Public helper for on-demand window query: resolves local cache or HTTP 206 range-read plan."""
    if mode not in ('auto', 'range', 'cache'):
        raise ValueError(f'Unsupported on-demand mode: {mode}')
    # Check if coordinate matches a materialized site within 0.05 deg
    for site in SITE_CATALOG:
        if site['body'] == 'Earth':
            slon, slat = site['lon_lat']
            if math.hypot(lon - slon, lat - slat) <= 0.05:
                return {
                    'query_lon_lat': [lon, lat],
                    'window_m': window_m,
                    'mode_requested': mode,
                    'resolution_strategy': 'verified_local_cache_hit',
                    'matched_site_id': site['site_id'],
                    'requires_full_globe_download': False,
                }
    if mode == 'cache':
        return {
            'query_lon_lat': [lon, lat],
            'window_m': window_m,
            'mode_requested': mode,
            'resolution_strategy': 'cache_miss_deferred',
            'matched_site_id': None,
            'requires_full_globe_download': False,
        }
    return {
        'query_lon_lat': [lon, lat],
        'window_m': window_m,
        'mode_requested': mode,
        'resolution_strategy': 'http_206_cog_range_stream',
        'matched_site_id': None,
        'estimated_range_payload_mb': 0.42,
        'requires_full_globe_download': False,
        'stages': ['glo30_cog_vsicurl', 'worldcover_cog_vsicurl', 'jrc_cog_vsicurl', 'conditional_emit_cmr_lookup'],
    }


def main() -> None:
    spec = json.loads(SPEC_PATH.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    print('1. Construyendo registros del contrato común multi-instrumento...', flush=True)
    contract_data = build_common_contract_records(spec)
    print('2. Particionando bloques espaciales (desarrollo vs. holdout) y analizando redundancia...', flush=True)
    partition = partition_spatial_blocks(spec)
    selection_data = analyze_selection_and_redundancy(spec, contract_data, partition)
    print('3. Generando figura comparativa de contrato e instrumentos...', flush=True)
    plot_contract_and_selection(contract_data, selection_data)

    print('4. Generando paquete de revisión visual a ciegas con NASA Worldview / GIBS...', flush=True)
    earth_review_inputs = [
        {
            'region_id': s['site_id'],
            'area_id': s['stratum'],
            'lon_lat': s['lon_lat'],
            'window_m': 3000,
            'cell_m': 30,
            **s['topography_contract']['3000']['30'],
        }
        for s in contract_data['sites']
        if s['body'] == 'Earth'
    ]
    blind_pkg = worldview_blind.build_blind_review_package(earth_review_inputs)

    eda.write(OUT / 'contrato-features.json', contract_data)
    eda.write(OUT / 'seleccion-y-redundancia.json', selection_data)
    eda.write(OUT / 'revision-ciegas-worldview.json', blind_pkg)

    tracked_files = [
        SPEC_PATH,
        ROOT / 'specs/sources/dimensiones-superficie-oficiales-v1.json',
        Path(__file__),
        HARMONIZATION_DIR / 'mediciones.json',
        HARMONIZATION_DIR / 'features-piloto.json',
        TOPO_VAL_PATH,
        PHASE4_CANDIDATES,
        OUT / 'contrato-features.json',
        OUT / 'seleccion-y-redundancia.json',
        OUT / 'revision-ciegas-worldview.json',
        OUT / 'comparabilidad-e-instrumentos.png',
    ]
    eda.write(OUT / 'manifest.json', {
        'schema': 1,
        'contract_id': spec['contract_id'],
        'files': [
            {
                'path': str(p.resolve().relative_to(ROOT)),
                'bytes': p.stat().st_size,
                'sha256': eda.digest(p),
            }
            for p in tracked_files
        ],
    })
    print(f'Entrega 3 completada en {OUT}: {len(contract_data["sites"])} sitios en el contrato común.', flush=True)


if __name__ == '__main__':
    main()
