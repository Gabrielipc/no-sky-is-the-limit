"""NASA Worldview / GIBS deterministic link and blind-review package generator (audit §4).

Generates equal-scale, fixed-date, fixed-layer Worldview URLs and GIBS GetSnapshot
URLs for candidate windows, plus shuffled blind review sheets that strip ranking,
distance score and site/region identifiers until unblinding.
"""
from __future__ import annotations

import hashlib
import hmac
import math
from typing import Any, Iterable
from urllib.parse import urlencode

DEFAULT_DATE = '2024-06-15'
DEFAULT_HALF_SPAN_KM = 6.0  # 12 x 12 km frame around a 3 km footprint + regional context
BLIND_EXCLUDED_LAYERS = frozenset({
    'Reference_Labels_15m',
    'Reference_Features_15m',
    'Reference_Labels',
    'Reference_Features',
    'OSM_Land_Mask',
})
DEFAULT_BLIND_LAYERS: tuple[str, ...] = (
    'VIIRS_SNPP_CorrectedReflectance_TrueColor',
    'MODIS_Terra_CorrectedReflectance_TrueColor',
    'Coastlines_15m',
)
DEFAULT_CONTEXT_LAYERS: tuple[str, ...] = (
    'VIIRS_SNPP_CorrectedReflectance_TrueColor',
    'MODIS_Terra_CorrectedReflectance_TrueColor',
    'Reference_Features_15m',
    'Reference_Labels_15m',
)

# Fields allowed into blind review sheets without leaking identity, basin or rank.
ALLOWED_REVIEW_FIELDS = frozenset({
    'window_m',
    'cell_m',
    'relief_p95_p05_m',
    'slope_240m_p50_deg',
    'slope_240m_p90_deg',
    'hypsometric_integral',
    'aspect_240m_resultant_length',
})
FORBIDDEN_BLIND_KEYS = frozenset({
    'region_id',
    'site_id',
    'area_id',
    'area',
    'rank',
    'initial_rank',
    'refined_rank',
    'distance_score',
    'distance',
    'label',
    'role',
    'split',
    'block_id',
    'utm_zone_band',
})


def _metric_bbox_wgs84(center_lon: float, center_lat: float, half_span_km: float) -> list[float]:
    if half_span_km <= 0:
        raise ValueError('half_span_km debe ser positivo')
    if not (-89.5 <= center_lat <= 89.5):
        raise ValueError(f'Latitud fuera de soporte geográfico para BBOX EPSG:4326: {center_lat}')
    dlat = half_span_km / 111.32
    cos_lat = max(math.cos(math.radians(center_lat)), 0.05)
    dlon = half_span_km / (111.32 * cos_lat)
    min_lon = round(center_lon - dlon, 5)
    max_lon = round(center_lon + dlon, 5)
    min_lat = round(max(-89.9, center_lat - dlat), 5)
    max_lat = round(min(89.9, center_lat + dlat), 5)
    return [min_lon, min_lat, max_lon, max_lat]


def build_worldview_url(
    center_lon: float,
    center_lat: float,
    *,
    half_span_km: float = DEFAULT_HALF_SPAN_KM,
    date: str = DEFAULT_DATE,
    layers: Iterable[str] | None = None,
    blind_mode: bool = True,
) -> dict[str, Any]:
    """Build deterministic NASA Worldview permalink and GIBS GetSnapshot URL for a window."""
    bbox = _metric_bbox_wgs84(float(center_lon), float(center_lat), float(half_span_km))
    min_lon, min_lat, max_lon, max_lat = bbox

    if layers is None:
        chosen = list(DEFAULT_BLIND_LAYERS if blind_mode else DEFAULT_CONTEXT_LAYERS)
    else:
        chosen = [str(layer) for layer in layers]

    if blind_mode:
        chosen = [layer for layer in chosen if layer not in BLIND_EXCLUDED_LAYERS]
        if not chosen:
            chosen = list(DEFAULT_BLIND_LAYERS)

    layers_csv = ','.join(chosen)
    wv_query = urlencode({
        'v': f'{min_lon},{min_lat},{max_lon},{max_lat}',
        't': f'{date}-T00:00:00Z',
        'l': layers_csv,
    })
    worldview_url = f'https://worldview.earthdata.nasa.gov/?{wv_query}'

    # GIBS Worldview Snapshots API uses WMS 1.3.0 EPSG:4326 axis order (lat, lon).
    snapshot_layers = ','.join(l for l in chosen if 'CorrectedReflectance' in l or l == 'Coastlines_15m') or layers_csv
    snap_query = urlencode({
        'REQUEST': 'GetSnapshot',
        'TIME': date,
        'BBOX': f'{min_lat},{min_lon},{max_lat},{max_lon}',
        'CRS': 'EPSG:4326',
        'LAYERS': snapshot_layers,
        'FORMAT': 'image/jpeg',
        'WIDTH': 512,
        'HEIGHT': 512,
    })
    gibs_snapshot_url = f'https://wvs.earthdata.nasa.gov/api/v1/snapshot?{snap_query}'

    return {
        'worldview_url': worldview_url,
        'gibs_snapshot_url': gibs_snapshot_url,
        'bbox_wgs84': bbox,
        'span_km': round(2.0 * half_span_km, 2),
        'date': date,
        'layers': chosen,
        'blind_mode': blind_mode,
    }


def _candidate_identity(cand: dict[str, Any]) -> str:
    for key in ('region_id', 'site_id', 'id'):
        if cand.get(key):
            return str(cand[key])
    raise ValueError('Cada candidata debe incluir region_id, site_id o id')


def _candidate_coords(cand: dict[str, Any]) -> tuple[float, float]:
    if 'lon_lat' in cand and len(cand['lon_lat']) == 2:
        return float(cand['lon_lat'][0]), float(cand['lon_lat'][1])
    lon = cand.get('longitude', cand.get('lon'))
    lat = cand.get('latitude', cand.get('lat'))
    if lon is None or lat is None:
        raise ValueError('Cada candidata debe incluir coordenadas (longitude/latitude o lon_lat)')
    return float(lon), float(lat)


def build_blind_review_package(
    candidates: Iterable[dict[str, Any]],
    *,
    seed: str = 'spaceapps-blind-v1',
    date: str = DEFAULT_DATE,
    half_span_km: float = DEFAULT_HALF_SPAN_KM,
    layers: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Create a rank-blind visual review sheet and a separate unblinding key."""
    key_bytes = seed.encode('utf-8')
    shuffled = sorted(
        list(candidates),
        key=lambda c: hmac.new(key_bytes, _candidate_identity(c).encode('utf-8'), hashlib.sha256).hexdigest(),
    )

    blind_sheet: list[dict[str, Any]] = []
    unblinding_key: dict[str, dict[str, Any]] = {}

    for idx, cand in enumerate(shuffled, 1):
        blind_id = f'BLIND-{idx:03d}'
        ident = _candidate_identity(cand)
        lon, lat = _candidate_coords(cand)
        wv = build_worldview_url(
            lon,
            lat,
            half_span_km=half_span_km,
            date=date,
            layers=layers,
            blind_mode=True,
        )
        review_fields = {
            k: cand[k]
            for k in sorted(ALLOWED_REVIEW_FIELDS)
            if k in cand and k not in FORBIDDEN_BLIND_KEYS
        }
        blind_sheet.append({
            'blind_id': blind_id,
            'worldview_url': wv['worldview_url'],
            'gibs_snapshot_url': wv['gibs_snapshot_url'],
            'bbox_wgs84': wv['bbox_wgs84'],
            'span_km': wv['span_km'],
            'date': wv['date'],
            'layers': wv['layers'],
            'blind_mode': True,
            'review_fields': review_fields,
            'reviewer_assessment': {'visual_class': None, 'artifact_flag': None, 'notes': ''},
        })
        unblinding_key[blind_id] = {
            'region_id': ident,
            'area_id': cand.get('area_id', cand.get('area')),
            'rank': cand.get('rank', cand.get('initial_rank')),
            'distance_score': cand.get('distance_score', cand.get('distance')),
            'split': cand.get('split'),
            'longitude': lon,
            'latitude': lat,
        }

    return {
        'protocol_id': 'nasa-worldview-blind-review-v1',
        'date': date,
        'span_km': round(2.0 * half_span_km, 2),
        'blind_count': len(blind_sheet),
        'blind_sheet': blind_sheet,
        'unblinding_key': unblinding_key,
    }
