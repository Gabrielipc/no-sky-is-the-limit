#!/usr/bin/env python3
"""Build a natural-tone Mars globe map from the committed MOLA elevation tiles."""
from array import array
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / 'frontend/public/surface'
OUTPUT = SURFACE / 'mars-globe.png'


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (abs(estimate - left), abs(estimate - above), abs(estimate - upper_left))
    return (left, above, upper_left)[distances.index(min(distances))]


def read_rgb_png(path: Path) -> tuple[int, int, bytearray]:
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'Invalid PNG: {path}')
    width = height = color_type = bit_depth = None
    compressed = bytearray()
    pos = 8
    while pos < len(data):
        length = struct.unpack_from('>I', data, pos)[0]
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += length + 12
        if kind == b'IHDR':
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack('>IIBBBBB', chunk)
            if bit_depth != 8 or color_type != 2 or compression or filtering or interlace:
                raise ValueError(f'Unsupported PNG encoding: {path}')
        elif kind == b'IDAT':
            compressed.extend(chunk)
        elif kind == b'IEND':
            break
    if width is None or height is None:
        raise ValueError(f'Missing PNG header: {path}')
    raw = zlib.decompress(compressed)
    stride = width * 3
    pixels = bytearray(height * stride)
    source_pos = 0
    for y in range(height):
        filter_type = raw[source_pos]
        source_pos += 1
        row = raw[source_pos:source_pos + stride]
        source_pos += stride
        start = y * stride
        for i in range(stride):
            left = row[i - 3] if i >= 3 else 0
            above = pixels[start - stride + i] if y else 0
            upper_left = pixels[start - stride + i - 3] if y and i >= 3 else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            elif filter_type == 0:
                predictor = 0
            else:
                raise ValueError(f'Unsupported PNG filter {filter_type}: {path}')
            pixels[start + i] = (row[i] + predictor) & 255
    return width, height, pixels


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)


def write_rgb_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    stride = width * 3
    raw = b''.join(b'\0' + pixels[y * stride:(y + 1) * stride] for y in range(height))
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b''))


def _ramp(height_m: int) -> tuple[int, int, int]:
    stops = ((-8000, (91, 48, 39)), (-1000, (133, 59, 39)), (8000, (177, 99, 60)), (21000, (215, 164, 119)))
    value = max(stops[0][0], min(stops[-1][0], height_m))
    for (low, a), (high, b) in zip(stops, stops[1:]):
        if value <= high:
            t = (value - low) / (high - low)
            return tuple(round(x + (y - x) * t) for x, y in zip(a, b))
    return stops[-1][1]


def build() -> None:
    manifest_path = SURFACE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    mola = manifest['mola']
    level = mola['max_level']
    tile_size = mola['tile_size']
    nx, ny = 2 ** (level + 1), 2 ** level
    width, height = nx * (tile_size - 1), ny * (tile_size - 1)
    recorded = {entry['file']: entry for entry in manifest['files']}
    heights = array('i', [0]) * (width * height)

    for tile_y in range(ny):
        for tile_x in range(nx):
            relative = f'mola/{level}/{tile_x}/{tile_y}.png'
            path = SURFACE / relative
            entry = recorded.get(relative)
            if entry is None or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError(f'MOLA tile is missing or changed: {relative}')
            tw, th, rgb = read_rgb_png(path)
            if tw != tile_size or th != tile_size:
                raise ValueError(f'Unexpected MOLA tile dimensions: {relative}')
            copy_width = tile_size - 1
            copy_height = tile_size - 1
            for row in range(copy_height):
                dst = (tile_y * (tile_size - 1) + row) * width + tile_x * (tile_size - 1)
                src = row * tile_size * 3
                for col in range(copy_width):
                    heights[dst + col] = ((rgb[src + col * 3] << 8) | rgb[src + col * 3 + 1]) - 32768

    pixels = bytearray(width * height * 3)
    for y in range(height):
        latitude = 90.0 - (y + 0.5) * 180.0 / height
        ice = max(0.0, min(1.0, (abs(latitude) - 83.0) / 6.0))
        row = y * width
        for x in range(width):
            index = row + x
            elev = heights[index]
            left = heights[index - 1] if x else heights[index]
            right = heights[index + 1] if x + 1 < width else heights[index]
            north = heights[index - width] if y else elev
            south = heights[index + width] if y + 1 < height else elev
            nxv, nyv = -(right - left) / 5000.0, -(north - south) / 5000.0
            length = math.sqrt(nxv * nxv + nyv * nyv + 1.0)
            illumination = max(0.0, (nxv * 0.38 + nyv * 0.28 + 0.88) / length)
            shade = 0.62 + 0.42 * illumination
            base = _ramp(elev)
            offset = index * 3
            for channel, component in enumerate(base):
                lit = component * shade
                pixels[offset + channel] = round(lit * (1.0 - ice) + (214, 208, 192)[channel] * ice)

    write_rgb_png(OUTPUT, width, height, pixels)
    manifest['mars_globe'] = {
        'file': OUTPUT.name,
        'source': 'NASA MGS MOLA MEGR90N000CB elevation tiles',
        'display': 'Natural-tone shaded elevation; not a natural-colour photograph',
        'width': width,
        'height': height,
    }
    manifest['files'] = [entry for entry in manifest['files'] if entry['file'] != OUTPUT.name]
    manifest['files'].append({
        'file': OUTPUT.name,
        'sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        'bytes': OUTPUT.stat().st_size,
    })
    manifest['files'].sort(key=lambda entry: entry['file'])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(f'Wrote {OUTPUT.relative_to(ROOT)} ({width}x{height})')


if __name__ == '__main__':
    build()
