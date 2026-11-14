"""Access region reference data from JSON."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / 'data' / 'regions.json'


def load_regions() -> list[dict]:
    return json.loads(DATA.read_text(encoding='utf-8'))
