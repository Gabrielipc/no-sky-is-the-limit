"""Spectral bridge with one operator on three bodies (audit 2026-11-14, section 1.2, priority 6).

The Tercera entrega compared CRISM summary parameters (continuous band parameters over the
whole footprint) with EMIT L2B library-fit depths (only over identified samples). Here every
instrument goes through the same steps:

1. Reflectance over the same square footprint (1.8 or 3 km side, local azimuthal equidistant
   grid on the body's sphere/ellipsoid), keeping only cells that pass the product's own mask.
2. CRISM summary parameters computed by `pipelines.spectral_params` (CAT reference, July 2026).
3. Per absorption complex: P50/P95 of the primary and secondary parameter over valid cells, and
   the active fraction = share of valid cells whose primary parameter exceeds the complex's
   fixed floor (`crism_adapter.positive_floor` of contrato-comun-superficie-v1).

So magnitude, operator, threshold and denominator are shared. What still differs is the pixel
support (CRISM 18 m, EMIT 60 m, M3 140-280 m) and the atmospheric/photometric correction of each
product, which the evidence reports next to every value.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from shapely.geometry import Polygon, box, mapping
from shapely.ops import transform as shp_transform

from pipelines import spectral_params as sp

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SPEC = ROOT / 'specs/analysis/contrato-comun-entrega3.json'
BRIDGE_SPEC = ROOT / 'specs/analysis/puente-espectral-v1.json'
MIN_VALID_FRACTION = 0.8      # quality_thresholds.min_window_valid_fraction
MIN_VALID_CELLS = 30          # same minimum sample as the EMIT complexes
MEASURED_STATUSES = ('measured', 'measured_absent')

BODY_SHAPES = {
    'Earth': '+ellps=WGS84',
    'Mars': '+R=3394839.8133163',   # CRISM MTRDR sphere (IAU 2000, as in the product label)
    'Moon': '+R=1737400',
}


def load_complexes(path: Path = CONTRACT_SPEC) -> list[dict]:
    spec = json.loads(path.read_text(encoding='utf-8'))
    return spec['spectral_absorption_complexes']


def load_bridge_spec(path: Path = BRIDGE_SPEC) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def bridge_parameter_names(spec: dict | None = None) -> list[str]:
    """Ordered unique list of summary parameters referenced in `puente-espectral-v1.json`."""
    spec = load_bridge_spec() if spec is None else spec
    seen: set[str] = set()
    names: list[str] = []
    for cdef in spec['complexes'].values():
        for ind in cdef['indicators']:
            param = ind['parameter']
            if param not in seen:
                seen.add(param)
                names.append(param)
    return names


def footprint(body: str, longitude: float, latitude: float, side_m: float) -> tuple[Polygon, CRS]:
    """Square of `side_m` centred on the site in a local azimuthal equidistant CRS of `body`."""
    crs = CRS.from_proj4(f'+proj=aeqd +lat_0={latitude} +lon_0={longitude} {BODY_SHAPES[body]} +units=m +no_defs')
    half = side_m / 2
    return box(-half, -half, half, half), crs


def footprint_in(geom: Polygon, src: CRS, dst, densify_m: float = 30.0) -> Polygon:
    """Footprint reprojected to `dst`, densified so curved edges survive the projection."""
    densified = geom.segmentize(densify_m)
    t = Transformer.from_crs(src, dst, always_xy=True)
    return shp_transform(t.transform, densified)


def raster_mask(geom: Polygon, transform, shape: tuple[int, int]) -> np.ndarray:
    """True for cells whose centre lies inside `geom` (in the raster's CRS)."""
    return geometry_mask([mapping(geom)], out_shape=shape, transform=transform, invert=True)


@dataclass
class FootprintSample:
    """Reflectance of the valid cells of a footprint and its support."""
    instrument: str
    product_id: str
    wavelengths: np.ndarray
    reflectance: np.ndarray          # (bands, 1, n_valid)
    footprint_cells: int
    in_coverage_cells: int
    valid_cells: int
    pixel_m: float
    kernel_mode: str
    notes: list[str]

    @property
    def valid_fraction(self) -> float:
        return self.valid_cells / self.footprint_cells if self.footprint_cells else 0.0


def summarize(sample: FootprintSample, complexes: list[dict]) -> dict:
    """Per-complex record with the shared operator, floor and denominator."""
    cube = sp.Cube(sample.reflectance, sample.wavelengths, sample.kernel_mode)
    enough = sample.valid_fraction >= MIN_VALID_FRACTION and sample.valid_cells >= MIN_VALID_CELLS
    out = {}
    for comp in complexes:
        cad = comp['crism_adapter']
        prim, sec, floor = cad['primary_parameter'], cad['secondary_parameter'], float(cad['positive_floor'])
        rec = {
            'primary_parameter': prim, 'secondary_parameter': sec, 'positive_floor': floor,
            'primary_p50': None, 'primary_p95': None, 'secondary_p50': None, 'secondary_p95': None,
            'active_fraction': None, 'n_valid': sample.valid_cells,
        }
        if sample.valid_cells == 0:
            rec['status'] = 'insufficient_coverage'
            rec['reason'] = 'Sin celdas válidas en la huella'
            out[comp['complex_id']] = rec
            continue
        if not (sp.covered(cube, prim) and sp.covered(cube, sec)):
            missing = [p for p in (prim, sec) if not sp.covered(cube, p)]
            rec['status'] = 'unobserved_by_product'
            rec['reason'] = f'Rango espectral o bandas válidas insuficientes para {", ".join(missing)}'
            out[comp['complex_id']] = rec
            continue
        pv = sp.compute(cube, prim).ravel()
        sv = sp.compute(cube, sec).ravel()
        good = np.isfinite(pv) & np.isfinite(sv)
        rec['n_valid'] = int(good.sum())
        if not enough or good.sum() < MIN_VALID_CELLS:
            rec['status'] = 'insufficient_coverage'
            out[comp['complex_id']] = rec
            continue
        pv, sv = pv[good], sv[good]
        rec.update(
            primary_p50=float(np.median(pv)), primary_p95=float(np.percentile(pv, 95)),
            secondary_p50=float(np.median(sv)), secondary_p95=float(np.percentile(sv, 95)),
            active_fraction=float((pv > floor).mean()),
            status='measured' if (pv > floor).any() else 'measured_absent',
        )
        out[comp['complex_id']] = rec
    return out


def sample_record(sample: FootprintSample) -> dict:
    return {
        'instrument': sample.instrument, 'product_id': sample.product_id,
        'footprint_cells': sample.footprint_cells, 'in_coverage_cells': sample.in_coverage_cells,
        'valid_cells': sample.valid_cells, 'valid_fraction': sample.valid_fraction,
        'pixel_m': sample.pixel_m, 'kernel_mode': sample.kernel_mode,
        'wavelength_range_nm': [float(np.nanmin(sample.wavelengths)), float(np.nanmax(sample.wavelengths))],
        'notes': sample.notes,
    }


def summarize_indicator(cube: sp.Cube, sample: FootprintSample, parameter: str,
                        floor: float, floor_origin: str = '') -> dict:
    """Evaluate a single CRISM summary parameter over `sample` with shared threshold and denominator."""
    rec = {
        'parameter': parameter,
        'floor': float(floor),
        'floor_origin': floor_origin,
        'p50': None,
        'p95': None,
        'active_fraction': None,
        'n_valid': sample.valid_cells,
    }
    if sample.valid_cells == 0:
        rec['status'] = 'insufficient_coverage'
        rec['reason'] = 'Sin celdas válidas en la huella'
        return rec
    if not sp.covered(cube, parameter):
        rec['status'] = 'unobserved_by_product'
        rec['reason'] = f'Rango espectral o bandas válidas insuficientes para {parameter}'
        return rec
    vals = sp.compute(cube, parameter).ravel()
    good = np.isfinite(vals)
    n_valid = int(good.sum())
    rec['n_valid'] = n_valid
    enough = sample.valid_fraction >= MIN_VALID_FRACTION and sample.valid_cells >= MIN_VALID_CELLS
    if not enough or n_valid < MIN_VALID_CELLS:
        rec['status'] = 'insufficient_coverage'
        rec['reason'] = 'Soporte válido insuficiente en la huella (< 80 % o < 30 celdas)'
        return rec
    v = vals[good]
    rec.update(
        p50=float(np.median(v)),
        p95=float(np.percentile(v, 95)),
        active_fraction=float((v > floor).mean()),
        status='measured' if (v > floor).any() else 'measured_absent',
    )
    return rec


def summarize_bridge(sample: FootprintSample, spec: dict | None = None) -> dict:
    """Evaluate every complex and its ranked fallback indicators for `sample`."""
    spec = load_bridge_spec() if spec is None else spec
    cube = sp.Cube(sample.reflectance, sample.wavelengths, sample.kernel_mode)
    out: dict = {}
    for complex_id, cdef in spec['complexes'].items():
        indicators = [
            summarize_indicator(cube, sample, ind['parameter'], float(ind['floor']), ind.get('floor_origin', ''))
            for ind in cdef['indicators']
        ]
        chosen = next((ind for ind in indicators if ind['status'] in MEASURED_STATUSES), None)
        if chosen is None:
            chosen = next((ind for ind in indicators if ind['status'] == 'insufficient_coverage'), indicators[0])
        out[complex_id] = {
            **chosen,
            'indicators': indicators,
            'by_parameter': {ind['parameter']: ind for ind in indicators},
        }
    return out


def _indicator_map(complex_entry: dict) -> dict[str, dict]:
    if 'by_parameter' in complex_entry:
        return complex_entry['by_parameter']
    return {ind['parameter']: ind for ind in complex_entry.get('indicators', [])}


def pair_comparison(summary_a: dict, summary_b: dict, spec: dict | None = None) -> dict:
    """Compare two site summaries per complex using `pairing_rule`.

    Selects the first indicator in the complex's ranked list measured by both instruments
    (`measured` or `measured_absent`). Differences are reported as `delta_* = site_b - site_a`.
    """
    spec = load_bridge_spec() if spec is None else spec
    out: dict = {}
    for complex_id, cdef in spec['complexes'].items():
        inds_a = _indicator_map(summary_a.get(complex_id, {}))
        inds_b = _indicator_map(summary_b.get(complex_id, {}))
        bridged = None
        pair_statuses: list[tuple[str, str, str]] = []
        for rank, ind_spec in enumerate(cdef['indicators'], 1):
            param = ind_spec['parameter']
            ra = inds_a.get(param, {'status': 'unobserved_by_product'})
            rb = inds_b.get(param, {'status': 'unobserved_by_product'})
            sa, sb = ra.get('status', 'unobserved_by_product'), rb.get('status', 'unobserved_by_product')
            pair_statuses.append((param, sa, sb))
            if sa in MEASURED_STATUSES and sb in MEASURED_STATUSES:
                bridged = {
                    'status': 'bridged',
                    'parameter': param,
                    'indicator_rank': rank,
                    'floor': float(ind_spec['floor']),
                    'floor_origin': ind_spec.get('floor_origin', ''),
                    'site_a': {k: ra.get(k) for k in ('status', 'p50', 'p95', 'active_fraction', 'n_valid')},
                    'site_b': {k: rb.get(k) for k in ('status', 'p50', 'p95', 'active_fraction', 'n_valid')},
                    'delta_p50': float(rb['p50'] - ra['p50']),
                    'delta_p95': float(rb['p95'] - ra['p95']),
                    'delta_active_fraction': float(rb['active_fraction'] - ra['active_fraction']),
                }
                break
        if bridged is not None:
            out[complex_id] = bridged
            continue
        candidate_pairs = [(p, sa, sb) for p, sa, sb in pair_statuses
                           if sa != 'unobserved_by_product' and sb != 'unobserved_by_product']
        if any('on_demand_fetchable' in (sa, sb) for _, sa, sb in candidate_pairs):
            status = 'pending_remote_fetch'
        elif any('insufficient_coverage' in (sa, sb) for _, sa, sb in candidate_pairs):
            status = 'unbridged_insufficient_coverage'
        else:
            status = 'unbridged_unobserved'
        out[complex_id] = {
            'status': status,
            'parameter': None,
            'indicator_rank': None,
            'site_a_status': summary_a.get(complex_id, {}).get('status'),
            'site_b_status': summary_b.get(complex_id, {}).get('status'),
            'evaluated_indicators': [
                {'parameter': p, 'site_a_status': sa, 'site_b_status': sb}
                for p, sa, sb in pair_statuses
            ],
        }
    return out
