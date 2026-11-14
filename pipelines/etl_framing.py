"""Best-framing hypsometric integral for the densified candidate stage.

The hypsometric integral keeps its window ranking under footprint shifts up to 300 m
(Spearman 0.94) but not at 750 m (0.73); see `docs/evidencia-descriptores-forma/
sensibilidad-huella.json`. A fixed reconnaissance grid frames each landform
arbitrarily, so for preselected candidates the 3 km footprint is re-evaluated on a
local lattice (default: 300 m step, up to 600 m per axis, 25 framings) and the framing
closest to the reference in relief and integral jointly is reported, together with the range over
all framings and the other topographic descriptors at that framing.

Choosing the best of N framings favours every candidate in the same way, so the value
is comparable between candidates evaluated with the same lattice, not with a single
fixed-framing measurement.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from rasterio.warp import Resampling

from pipelines import atlas_topography as topo
from pipelines import etl_extractors as ex

DEFAULT_STEP_M = 300
DEFAULT_MAX_OFFSET_M = 600
JEZERO_REFERENCE_ID = 'jezero-hirise-3km-centered'
JEZERO_HYPSOMETRIC_INTEGRAL = 0.613
JEZERO_RELIEF_M = 120.27
# Densified-stage similarity vector: one descriptor per principal axis of the 716
# development windows (ruggedness: relief; shape: hypsometric integral), both taken at
# one framing. Each term is scaled by the median absolute change that one 300 m lattice
# step causes in the development windows (docs/evidencia-descriptores-forma/
# sensibilidad-huella.json), so both are counted in "framing steps" and the scale does
# not depend on which candidates are compared. The same distance selects the best
# framing and ranks the candidates. Equal weights are a starting point, not a
# calibration; the vector stays `pending_blind_validation` until it is evaluated on the
# reserved blocks (Paso 7).
DENSIFIED_VECTOR_ID = 'densified_relief_hi_v2'
DENSIFIED_VECTOR_STATUS = 'pending_blind_validation'
FRAMING_CRITERION = 'joint_relief_hi_v2'
LEGACY_FRAMING_CRITERION = 'hi_only_v1'
DENSIFIED_WEIGHTS = (0.5, 0.5)
DENSIFIED_SCALES = (5.81521, 0.01296)  # relief (m), integral: median |change| per 300 m step
REFERENCE_HI_TOLERANCE = 5e-4
REFERENCE_RELIEF_TOLERANCE_M = 0.05


def densified_distance(relief_m: float, hi: float, reference_relief_m: float, reference_hi: float,
                       weights: tuple[float, float] = DENSIFIED_WEIGHTS,
                       scales: tuple[float, float] = DENSIFIED_SCALES) -> float:
    """Weighted distance to the reference in framing-step units (see DENSIFIED_SCALES)."""
    return (weights[0] * abs(relief_m - reference_relief_m) / scales[0]
            + weights[1] * abs(hi - reference_hi) / scales[1])


BEST_KEYS = (
    'relief_p95_p05_m', 'slope_240m_p50_deg', 'slope_240m_p90_deg', 'aspect_240m_resultant_length',
)


def lattice(step_m: int, max_offset_m: int, cell_m: int = ex.CELL_M) -> list[tuple[int, int]]:
    """(east, north) offsets in metres, centre first, then by distance and angle."""
    if step_m <= 0 or step_m % cell_m or max_offset_m % step_m:
        raise ValueError('El paso debe ser múltiplo de la celda y el desplazamiento máximo múltiplo del paso')
    k = max_offset_m // step_m
    offsets = [(i * step_m, j * step_m) for i in range(-k, k + 1) for j in range(-k, k + 1)]
    return sorted(offsets, key=lambda o: (np.hypot(*o), np.arctan2(o[1], o[0])))


def evaluate_framings(
    z_big: np.ndarray,
    land_big: np.ndarray,
    reference_hi: float,
    step_m: int = DEFAULT_STEP_M,
    max_offset_m: int = DEFAULT_MAX_OFFSET_M,
    cell_m: int = ex.CELL_M,
    reference_relief_m: float = JEZERO_RELIEF_M,
) -> dict:
    """Evaluate the topographic contract on every lattice framing of an enlarged grid.

    `z_big` and `land_big` cover the footprint, the 720 m halo and `max_offset_m` on each
    side, with row 0 to the north.
    """
    size = (ex.WINDOW_M + 2 * ex.HALO_M) // cell_m
    margin = max_offset_m // cell_m
    if z_big.shape != (size + 2 * margin,) * 2:
        raise ValueError(f'Rejilla de {z_big.shape}; se esperaba {(size + 2 * margin,) * 2}')
    framings = []
    for east, north in lattice(step_m, max_offset_m, cell_m):
        r0, c0 = margin - north // cell_m, margin + east // cell_m
        feats = ex.compute_topography_features(z_big[r0:r0 + size, c0:c0 + size],
                                               land_big[r0:r0 + size, c0:c0 + size], cell_m=cell_m)
        framings.append({'east_m': east, 'north_m': north, **feats})

    valid = [f for f in framings
             if f['hypsometric_integral'] is not None and f['relief_p95_p05_m'] is not None]
    center = framings[0]
    record = {
        'reference_hypsometric_integral': float(reference_hi),
        'reference_relief_m': float(reference_relief_m),
        'framing_criterion': FRAMING_CRITERION,
        'lattice_step_m': step_m,
        'max_offset_m': max_offset_m,
        'framings_evaluated': len(framings),
        'framings_valid': len(valid),
        'hi_center': center['hypsometric_integral'],
        'hi_best': None,
        'hi_min': None,
        'hi_max': None,
        'best_offset_east_m': None,
        'best_offset_north_m': None,
        'best_at_lattice_edge': None,
        'best_distance_score': None,
        'center_distance_score': None,
        **{f'best_{k}': None for k in BEST_KEYS},
        'framing_status': 'insufficient_coverage',
    }
    if not valid:
        return record
    def distance(f: dict) -> float:
        return densified_distance(f['relief_p95_p05_m'], f['hypsometric_integral'], reference_relief_m, reference_hi)

    # Joint selection: a framing that matches the integral by drifting away from the
    # reference relief is penalised by the same distance that later ranks candidates.
    best = min(valid, key=distance)
    his = [f['hypsometric_integral'] for f in valid]
    record.update({
        'hi_best': best['hypsometric_integral'],
        'hi_min': float(min(his)),
        'hi_max': float(max(his)),
        'best_offset_east_m': best['east_m'],
        'best_offset_north_m': best['north_m'],
        # A best framing on the lattice edge may improve further out; widen max_offset_m to check.
        'best_at_lattice_edge': max(abs(best['east_m']), abs(best['north_m'])) == max_offset_m,
        'best_distance_score': distance(best),
        'center_distance_score': distance(center) if center in valid else None,
        **{f'best_{k}': best[k] for k in BEST_KEYS},
        'framing_status': 'measured',
    })
    return record


def extract_framing_record(
    candidate: dict,
    land: topo.Land,
    rasters: topo.Rasters,
    inventory: dict,
    reference_hi: float = JEZERO_HYPSOMETRIC_INTEGRAL,
    reference_relief_m: float = JEZERO_RELIEF_M,
    reference_id: str = JEZERO_REFERENCE_ID,
    step_m: int = DEFAULT_STEP_M,
    max_offset_m: int = DEFAULT_MAX_OFFSET_M,
    now: datetime | None = None,
) -> tuple[dict, list[dict]]:
    """Read GLO-30 around a stored candidate window and return an `enrichment_framing` row."""
    now = now or datetime.now(timezone.utc)
    zone = topo.owner(candidate['longitude'], candidate['latitude'])
    x, y = topo.projection(topo.WGS84, zone).transform(candidate['longitude'], candidate['latitude'])
    half_m = ex.WINDOW_M // 2 + ex.HALO_M + max_offset_m
    crs, bounds, affine, shape = ex.window_grid(zone, x, y, half_m)
    land_mask = land.mask(crs, bounds, affine, shape)
    entries = [inventory[k] for k in topo.tile_keys(bounds, 1) if k in inventory]
    z, dem_ids = topo.mosaic(rasters, entries, crs, bounds, affine, shape, Resampling.average)
    base = {'region_id': candidate['region_id'], 'reference_id': reference_id}
    if dem_ids:
        record = evaluate_framings(z, land_mask, reference_hi, step_m, max_offset_m,
                                   reference_relief_m=reference_relief_m)
    else:
        record = evaluate_framings(np.full(shape, np.nan), land_mask, reference_hi, step_m, max_offset_m,
                                   reference_relief_m=reference_relief_m)
    manifest_id = ex.make_manifest_id(list(dem_ids), f'framing:{rasters.mode}:{step_m}:{max_offset_m}')
    manifests = [
        {
            'source_manifest_id': manifest_id,
            'product_id': 'copernicus-glo30',
            'asset_id': aid,
            'access_mode': rasters.mode,
            'sha256_or_etag': (rasters.identities.get(aid) or {}).get('sha256')
            or (rasters.identities.get(aid) or {}).get('etag'),
            'native_resolution_m': 30.0,
            'effective_resolution_m': float(ex.CELL_M),
            'observation_period': 'static',
            'created_at': now,
        }
        for aid in sorted(set(dem_ids))
    ]
    return {**base, **record, 'source_manifest_id': manifest_id, 'updated_at': now}, manifests
