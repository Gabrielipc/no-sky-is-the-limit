"""Imagen de detalle para los globos del visor unificado (solo derivados visuales).

Prioriza las zonas marcadas: parches anidados (de amplio a fino) alrededor de cada
referencia fija de Marte y de la Luna, y bases globales de 4096 x 2048 para los tres
cuerpos. Las candidatas terrestres son dinámicas: el navegador las detalla en vivo
(Esri World Imagery), no se hornean aquí.

- Marte: luminancia del mosaico CTX beta01 de Caltech Murray Lab (~5 m/píxel, servicio
  Esri OnMars) teñida con el color de elevación MOLA (NASA Trek, mismo estilo que la
  textura global). Sin CTX (huecos del mosaico) se conserva la luminancia MOLA.
- Luna: relieve sombreado LOLA polar sur (NASA Trek, estereográfica polar; 5 m/píxel
  al sur de 87,5° S y 30 m/píxel hasta 75° S) reproyectado a rejilla geográfica y
  teñido con el color LROC del CGI Moon Kit.
- Bases: MOLA ClrShade (Trek), CGI Moon Kit 4k (SVS), Blue Marble NG (GIBS).

Los bordes de cada parche se funden con alfa para no dibujar cajas sobre la base.
Las teselas originales quedan en data/raw/frontend-detail (ignorado por Git).
Ejecutar desde la raíz: .pixi/envs/default/bin/python frontend/scripts/prepare-detail-imagery.py
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageFile
from scipy.ndimage import map_coordinates

Image.MAX_IMAGE_PIXELS = None
# Some OnMars CTX tiles arrive with their last PNG rows cut by the server (the size
# matches Content-Length). Decode what exists; missing rows read as 0 and are filled
# from coarser CTX levels in mars_patch.
ImageFile.LOAD_TRUNCATED_IMAGES = True
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/frontend-detail"
OUT = ROOT / "frontend/public/surface/detail"
UA = {"User-Agent": "regolith-visual-derivatives/1.0"}

CTX = "https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile/{z}/{y}/{x}"
MOLA_CLR = "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg"
LOLA_875 = "https://trek.nasa.gov/tiles/Moon/SP/LRO_LOLA_Shade_SPole875_5mp_v04/1.0.0//default/default028mm/{z}/{y}/{x}.png"
LOLA_75 = "https://trek.nasa.gov/tiles/Moon/SP/LRO_LOLA_Shade_SPole75_30mp_v04/1.0.0//default/default028mm/{z}/{y}/{x}.png"
MOON_4K = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_poles_4k.tif"
EARTH_4K = (
    "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap"
    "&VERSION=1.1.1&LAYERS=BlueMarble_NextGeneration&STYLES=&SRS=EPSG:4326"
    "&BBOX=-180,-90,180,90&WIDTH=4096&HEIGHT=2048&FORMAT=image/jpeg"
)
MOON_R, MARS_R = 1737400.0, 3396190.0
# Trek SP tile matrix: 8561.95 m/px at level 0, origin (-1095930, 1095930).
SP_ORIGIN, SP_RES0 = 1095930.0, 30578404.017857101 * 0.00028


def fetch(url: str, cache: Path) -> bytes | None:
    """Cached download. Missing tiles (404) are remembered as empty files."""
    if cache.exists():
        data = cache.read_bytes()
        return data or None
    cache.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
                expected = r.headers.get("Content-Length")
            if expected and int(expected) != len(data):
                raise IOError("descarga truncada")
            if not url.endswith(".tif"):
                Image.open(io.BytesIO(data))  # header check: never cache an HTML error page
            tmp = cache.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(cache)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                cache.write_bytes(b"")
                return None
            time.sleep(1 + attempt * 2)
        except Exception:
            time.sleep(1 + attempt * 2)
    raise RuntimeError(f"No se pudo descargar {url}")


def tiles(template: str, name: str, keys: list[tuple[int, int, int]], mode: str):
    """Download (z, y, x) tiles in parallel; returns {key: float array or None}."""
    def one(k):
        z, y, x = k
        data = fetch(template.format(z=z, y=y, x=x), RAW / name / str(z) / str(y) / f"{x}.img")
        if not data:
            return k, None
        try:
            im = Image.open(io.BytesIO(data))
            if mode == "LA":
                a = np.asarray(im.convert("LA"), dtype=np.float32)
                return k, np.where(a[..., 1:2] > 0, a[..., :1], np.nan)[..., 0]
            return k, np.asarray(im.convert(mode), dtype=np.float32)
        except OSError:
            return k, None  # served damaged: a coarser level fills it
    with ThreadPoolExecutor(4) as pool:
        return dict(pool.map(one, keys))


# ---------- geographic (equirectangular) tiled sources ----------
def eq_mosaic(template, name, level, rect, tile_px, res0, mode):
    """Mosaic of an EQ pyramid (origin -180, 90) covering rect=[w,s,e,n]."""
    res = res0 / 2**level
    span = tile_px * res
    w, s, e, n = rect
    x0, x1 = int((w + 180) // span), int(math.ceil((e + 180) / span)) - 1
    y0, y1 = int((90 - n) // span), int(math.ceil((90 - s) / span)) - 1
    got = tiles(template, name, [(level, y, x) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)], mode)
    bands = 3 if mode == "RGB" else 1
    if mode == "L":
        # The CTX service answers some missing tiles with one repeated placeholder
        # (different bytes, identical pixels). Repeated content is never real terrain.
        seen: dict[bytes, int] = {}
        for a in got.values():
            if a is not None:
                key = a[::37, ::37].tobytes()
                seen[key] = seen.get(key, 0) + 1
        got = {k: (None if a is None or seen[a[::37, ::37].tobytes()] > 1 else a) for k, a in got.items()}
    out = np.full(((y1 - y0 + 1) * tile_px, (x1 - x0 + 1) * tile_px, bands), np.nan, np.float32)
    for (z, y, x), a in got.items():
        if a is None:
            continue
        a = a.reshape(a.shape[0], a.shape[1], -1)
        if mode == "L":
            a = np.where(a == 0, np.nan, a)  # CTX gaps are black
        out[(y - y0) * tile_px:(y - y0 + 1) * tile_px, (x - x0) * tile_px:(x - x0 + 1) * tile_px] = a
    # Pixel centers: lon = -180 + (col + 0.5) * res relative to this mosaic origin.
    return out, (-180 + x0 * span, 90 - y0 * span, res)


def grid(rect, width, height):
    w, s, e, n = rect
    lon = w + (np.arange(width) + 0.5) * (e - w) / width
    lat = n - (np.arange(height) + 0.5) * (n - s) / height
    return np.meshgrid(lon, lat)


def sample(img, cols, rows):
    """Bilinear sampling with NaN propagation per band."""
    out = []
    for b in range(img.shape[2]):
        band = img[..., b]
        valid = np.isfinite(band)
        v = map_coordinates(np.where(valid, band, 0), [rows, cols], order=1, mode="nearest")
        m = map_coordinates(valid.astype(np.float32), [rows, cols], order=1, mode="nearest")
        out.append(np.where(m > 0.5, v / np.maximum(m, 1e-6), np.nan))
    return np.stack(out, -1)


def sample_eq(mosaic, origin, lon, lat):
    ox, oy, res = origin
    step = abs(lon[0, 1] - lon[0, 0]) / res if lon.shape[1] > 1 else 1
    if step > 1.5:  # downsampling: average first so bilinear does not alias
        k = int(round(step))
        h, w = (mosaic.shape[0] // k) * k, (mosaic.shape[1] // k) * k
        mosaic = np.nanmean(mosaic[:h, :w].reshape(h // k, k, w // k, k, -1), axis=(1, 3))
        res *= k
    return sample(mosaic, (lon - ox) / res - 0.5, (oy - lat) / res - 0.5)


def pick_level(target_deg, res0, top):
    """Coarsest level whose pixel is not larger than the output pixel."""
    for level in range(top + 1):
        if res0 / 2**level <= target_deg * 1.05:
            return level
    return top


# ---------- south polar stereographic (Trek SP) ----------
def sp_xy(lon, lat):
    rho = 2 * MOON_R * np.tan(np.pi / 4 + np.radians(lat) / 2)
    return rho * np.sin(np.radians(lon)), rho * np.cos(np.radians(lon))


def sp_sample(template, name, level, lon, lat, extent_m):
    """Sample a Trek SP layer whose data lies within +/- extent_m of the pole."""
    res = SP_RES0 / 2**level
    x, y = sp_xy(lon, lat)
    col, row = (x + SP_ORIGIN) / res, (SP_ORIGIN - y) / res
    lo, hi = (SP_ORIGIN - extent_m) / res, (SP_ORIGIN + extent_m) / res
    tx0, tx1 = int(max(col.min(), lo) // 256), int(min(col.max(), hi) // 256)
    ty0, ty1 = int(max(row.min(), lo) // 256), int(min(row.max(), hi) // 256)
    got = tiles(template, name, [(level, ty, tx) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)], "LA")
    mosaic = np.full(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 1), np.nan, np.float32)
    for (z, ty, tx), a in got.items():
        if a is not None:
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256, 0] = a
    return sample(mosaic, col - tx0 * 256 - 0.5, row - ty0 * 256 - 0.5)[..., 0], res


# ---------- composition ----------
def luma(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def tint(detail, color, min_spread):
    """Replace the luminance of `color` with `detail`, matched to its statistics.

    `min_spread` keeps relief legible where the coarse image is flat (lunar polar fill).
    """
    base_y = luma(color)
    valid = np.isfinite(detail)
    if valid.sum() > 100:
        d = detail[valid]
        b = base_y[valid]
        lo, hi = np.percentile(d, [1, 99])
        blo, bhi = np.percentile(b, [1, 99])
        if bhi - blo < min_spread:
            mid = float(np.median(b))
            blo, bhi = max(8, mid - min_spread / 2), min(250, mid + min_spread / 2)
        scaled = blo + (detail - lo) * (bhi - blo) / max(hi - lo, 1e-3)
        # Keep some of the coarse brightness so wide albedo patterns survive.
        y = np.where(valid, 0.8 * scaled + 0.2 * base_y, base_y)
    else:
        y = base_y
    ratio = (y + 8) / (base_y + 8)
    return np.clip(color * ratio[..., None], 0, 255)


def feather(height, width, edges="nsew", fraction=0.08):
    ramp = max(4, int(min(height, width) * fraction))
    a = np.ones((height, width), np.float32)
    def edge(n):
        t = np.clip((np.arange(n) + 0.5) / ramp, 0, 1)
        return t * t * (3 - 2 * t)
    if "n" in edges: a *= edge(height)[:, None]
    if "s" in edges: a *= edge(height)[::-1, None]
    if "w" in edges: a *= edge(width)[None, :]
    if "e" in edges: a *= edge(width)[None, ::-1]
    return a


def save_webp(rgb, alpha, file):
    OUT.mkdir(parents=True, exist_ok=True)
    rgba = np.dstack([np.clip(np.nan_to_num(rgb), 0, 255), alpha * 255]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(OUT / file, "WEBP", quality=82, method=6, alpha_quality=60)
    return digest(OUT / file)


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def meters(rect, width, height, radius):
    w, s, e, n = rect
    lat_m = (n - s) / height * math.pi / 180 * radius
    mid = math.cos(math.radians((s + n) / 2))
    return round(lat_m, 1), round((e - w) / width * math.pi / 180 * radius * mid, 1)


def box(lon, lat, half_lon, half_lat):
    return [round(lon - half_lon, 6), round(lat - half_lat, 6), round(lon + half_lon, 6), round(lat + half_lat, 6)]


# ---------- Mars ----------
def mars_patch(ident, mark, rect, size, level=None):
    lon, lat = grid(rect, size, size)
    deg = (rect[2] - rect[0]) / size
    level = level or pick_level(deg, 0.3515625, 12)
    ctx, origin = eq_mosaic(CTX, "ctx", level, rect, 512, 0.3515625, "L")
    detail = sample_eq(ctx, origin, lon, lat)[..., 0]
    for coarser in range(level - 1, max(level - 4, 0), -1):
        if np.isfinite(detail).all():
            break
        fill, forigin = eq_mosaic(CTX, "ctx", coarser, rect, 512, 0.3515625, "L")
        detail = np.where(np.isfinite(detail), detail, sample_eq(fill, forigin, lon, lat)[..., 0])
    clr_level = 6
    clr, corigin = eq_mosaic(MOLA_CLR, "mola-clrshade", clr_level, rect, 256, 0.703125, "RGB")
    color = sample_eq(clr, corigin, lon, lat)
    rgb = tint(detail, color, 90)
    sha = save_webp(rgb, feather(size, size), f"{ident}.webp")
    lat_m, lon_m = meters(rect, size, size, MARS_R)
    return dict(id=ident, mark=mark, file=f"detail/{ident}.webp", rectangle=rect, width=size, height=size,
                pixel_m={"latitude": lat_m, "longitude_center": lon_m},
                ctx_coverage=round(float(np.isfinite(detail).mean()), 4),
                source=f"CTX beta01 nivel {level} + MOLA ClrShade nivel {clr_level}",
                credit="NASA/JPL/MSSS/Caltech Murray Lab/Esri · MOLA (NASA Trek)", sha256=sha)


# ---------- Moon ----------
_moon_color = None


def moon_color(lon, lat):
    global _moon_color
    if _moon_color is None:
        data = fetch(MOON_4K, RAW / "moon" / "lroc_color_poles_4k.tif")
        _moon_color = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), np.float32)
    h, w, _ = _moon_color.shape
    cols = ((lon + 180) % 360) / 360 * w - 0.5
    rows = (90 - lat) / 180 * h - 0.5
    # Wrap longitude by padding one column on each side.
    padded = np.concatenate([_moon_color[:, -1:], _moon_color, _moon_color[:, :1]], 1)
    return sample(padded, cols + 1, rows)


def moon_patch(ident, mark, rect, width, height, edges="nsew"):
    lon, lat = grid(rect, width, height)
    lat_m, _ = meters(rect, width, height, MOON_R)
    coarse, _ = sp_sample(LOLA_75, "lola-75", 6, lon, lat, 457440)
    fine_level = 9 if lat_m < 25 else 8 if lat_m < 60 else 7
    fine, _ = sp_sample(LOLA_875, "lola-875", fine_level, lon, lat, 75840) if rect[3] <= -84 else (np.full_like(coarse, np.nan), 0)
    # Blend the 5 m product (poleward of 87.5 S) into the 30 m one over a ramp, after
    # matching its brightness where both exist, so the boundary leaves no seam.
    both = np.isfinite(fine) & np.isfinite(coarse)
    if both.sum() > 100:
        f, c = fine[both], coarse[both]
        fine = (fine - f.mean()) / max(f.std(), 1e-3) * c.std() + c.mean()
    ramp = np.clip((-87.5 - lat - 0.03) / 0.2, 0, 1)
    ramp = ramp * ramp * (3 - 2 * ramp)
    w = np.where(np.isfinite(fine), ramp, 0)
    detail = np.where(np.isfinite(coarse), np.nan_to_num(coarse) * (1 - w) + np.nan_to_num(fine) * w, fine)
    rgb = tint(detail, moon_color(lon, lat), 170)
    sha = save_webp(rgb, feather(height, width, edges), f"{ident}.webp")
    lat_m, lon_m = meters(rect, width, height, MOON_R)
    return dict(id=ident, mark=mark, file=f"detail/{ident}.webp", rectangle=rect, width=width, height=height,
                pixel_m={"latitude": lat_m, "longitude_center": lon_m},
                source=f"LOLA sombreado polar sur 5 m (nivel {fine_level}) + 30 m (nivel 6), color CGI Moon Kit",
                credit="NASA LRO LOLA (NASA Trek) · LROC CGI Moon Kit", sha256=sha)


# ---------- global bases ----------
def mars_base():
    level = 4  # 32 x 16 tiles of 256 px -> 8192 x 4096, reduced to 4096 x 2048
    mosaic, _ = eq_mosaic(MOLA_CLR, "mola-clrshade", level, [-180, -90, 180, 90], 256, 0.703125, "RGB")
    im = Image.fromarray(np.nan_to_num(mosaic).astype(np.uint8)).resize((4096, 2048), Image.LANCZOS)
    im.save(OUT / "mars-base-4k.jpg", quality=86, optimize=True, progressive=True)
    return dict(file="detail/mars-base-4k.jpg", width=4096, height=2048, source=f"MOLA ClrShade 463 m, nivel {level}",
                credit="NASA MGS MOLA (NASA Trek)", sha256=digest(OUT / "mars-base-4k.jpg"))


def moon_base():
    data = fetch(MOON_4K, RAW / "moon" / "lroc_color_poles_4k.tif")
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.save(OUT / "moon-base-4k.jpg", quality=88, optimize=True, progressive=True)
    return dict(file="detail/moon-base-4k.jpg", width=im.width, height=im.height, source="CGI Moon Kit lroc_color_poles_4k",
                source_url=MOON_4K, source_sha256=hashlib.sha256(data).hexdigest(),
                credit="NASA SVS CGI Moon Kit · LROC + LOLA", sha256=digest(OUT / "moon-base-4k.jpg"))


def earth_base():
    data = fetch(EARTH_4K, RAW / "earth" / "blue-marble-4096.jpg")
    (OUT / "earth-base-4k.jpg").write_bytes(data)  # keep the GIBS bytes, no recompression
    return dict(file="detail/earth-base-4k.jpg", width=4096, height=2048, source="Blue Marble Next Generation (agosto 2004), GIBS",
                source_url=EARTH_4K, credit="NASA Earth Observatory / Reto Stöckli · GIBS", sha256=digest(OUT / "earth-base-4k.jpg"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jz = (77.41, 18.49)
    mars = [
        mars_patch("mars-jezero-region", "jezero", box(*jz, 2.0, 2.0), 2048),
        mars_patch("mars-jezero-crater", "jezero", box(*jz, 0.8, 0.8), 2048),
        mars_patch("mars-jezero-window", "jezero", box(*jz, 0.3, 0.3), 2048, level=12),
        mars_patch("mars-jezero-local", "jezero", box(*jz, 0.065, 0.065), 1536),
    ]
    moon = [
        # The whole south cap holds both references; skip feathering where it wraps or meets the pole.
        moon_patch("moon-south-cap", "haworth-fondo,de-gerlache-cresta", [-180, -90, 180, -84], 4096, 1024, edges="n"),
        moon_patch("moon-haworth", "haworth-fondo", [-31, -88.6, 21, -86.3], 2048, 1536),
        moon_patch("moon-de-gerlache", "de-gerlache-cresta", [-106, -89.5, -32, -87.9], 1536, 1536),
    ]
    catalog = {
        "version": 1,
        "description": "Imagen de visualización, no mediciones. Parches anidados de amplio a fino alrededor de las referencias marcadas; bordes fundidos con alfa.",
        "generator": "frontend/scripts/prepare-detail-imagery.py",
        "bodies": {
            "Mars": {"base": mars_base(), "patches": mars},
            "Moon": {"base": moon_base(), "patches": moon},
            "Earth": {
                "base": earth_base(),
                "patches": [],
                "live": {
                    "note": "Candidatas dinámicas: el visor añade Esri World Imagery alrededor de cada candidata con retraso y precarga las primeras.",
                    "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
                    "credit": "Esri, Maxar, Earthstar Geographics y la comunidad GIS",
                },
            },
        },
    }
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    for body, entry in catalog["bodies"].items():
        for p in [entry["base"], *entry["patches"]]:
            print(body, p["file"], f"{(ROOT / 'frontend/public/surface' / p['file']).stat().st_size / 1e6:.2f} MB", p.get("pixel_m", ""))


if __name__ == "__main__":
    main()
