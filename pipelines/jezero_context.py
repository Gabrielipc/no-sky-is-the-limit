"""Diagnostic surface observations with physical support kept explicit."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_window

from pipelines import spectral_bridge as bridge


def raster_support(path: Path | str, body: str, longitude: float, latitude: float, side_m: int) -> tuple[dict, object, object]:
    geom, local_crs = bridge.footprint(body, longitude, latitude, side_m)
    with rasterio.open(path) as raster:
        footprint = bridge.footprint_in(geom, local_crs, raster.crs)
        window = geometry_window(raster, [footprint], boundless=True)
        mask = bridge.raster_mask(footprint, raster.window_transform(window),
                                  (int(window.height), int(window.width)))
        window = window.crop(raster.height, raster.width)
        if window.width and window.height:
            data = raster.read(1, window=window, masked=True)
            inside = bridge.raster_mask(footprint, raster.window_transform(window), data.shape)
            valid = inside & ~np.ma.getmaskarray(data) & np.isfinite(data.data)
            values = data.data[valid]
        else:
            values = np.empty(0)
        fraction = values.size / mask.sum() if mask.any() else 0.0
        supported = fraction >= bridge.MIN_VALID_FRACTION and values.size >= bridge.MIN_VALID_CELLS
        result = {
            'side_m': side_m, 'native_pixel': list(raster.res), 'valid_cells': int(values.size),
            'valid_fraction': float(fraction), 'status': 'measured' if supported else 'insufficient_coverage',
            **{f'p{q}': float(np.percentile(values, q)) if supported else None for q in (10, 50, 90)},
        }
    return result, geom, local_crs


def themis(path: Path, longitude: float, latitude: float) -> dict:
    return {
        'product': 'Jezero_Thermal_Inertia_v1.tiff', 'doi': '10.5281/zenodo.4931348',
        'longitude': longitude, 'latitude': latitude, 'units': 'J m−2 K−1 s−1/2',
        'by_side': {str(side): raster_support(path, 'Mars', longitude, latitude, side)[0] for side in (1800, 3000)},
        'status': 'diagnostic', 'ranking_weight': 0,
    }


def antarctic(outcrops: Path, rema: Path | str, longitude: float, latitude: float) -> dict:
    import geopandas as gpd
    from shapely import union_all

    if not -90 <= latitude <= -60:
        raise ValueError('La huella antártica debe estar al sur de 60° S')
    dem, geom, local = raster_support(rema, 'Earth', longitude, latitude, 3000)
    polar = bridge.footprint_in(geom, local, 'EPSG:3031')
    # Read in the native ADD CRS; the source records EPSG:3031.
    data = gpd.read_file(outcrops, bbox=polar.bounds, columns=[])
    if data.crs is None or data.crs.to_epsg() != 3031:
        raise ValueError('El insumo SCAR debe estar en EPSG:3031')
    rocks = union_all(data.geometry.make_valid()).intersection(polar)
    local_rocks = bridge.footprint_in(rocks, data.crs, local) if not rocks.is_empty else rocks
    return {
        'longitude': longitude, 'latitude': latitude, 'surface_side_m': 3000, 'status': 'diagnostic',
        'rock_outcrop_fraction': local_rocks.area / geom.area, 'rema': dem,
        'sources': ['SCAR Antarctic Digital Database rock outcrop', 'Reference Elevation Model of Antarctica'],
        'note': 'SCAR aporta la fracción de afloramientos y REMA aporta la elevación superficial.',
    }
