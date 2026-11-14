"""Coordinate phase-5 stability evidence into API-ready payloads."""
from fastapi import HTTPException

from app.repositories import expansion_repository as exp_repo
from app.repositories import regional_repository as reg_repo

SCENARIO = {
    'id': exp_repo.SCENARIO_ID,
    'name': 'Reconocimiento topográfico · sensibilidad a fuente y escala',
    'question': '¿Se conservan las decisiones regionales al cambiar de producto y qué cambia con la escala?',
    'status': 'exploratory',
    'body': 'Mars',
    'view': 'stability',
    'references': [{'id': 'mars-jezero-fan', 'name': 'Jezero — abanico sedimentario'}],
    'scales_m': exp_repo.SCALES_M,
    'window_m': exp_repo.WINDOW_M,
    'scope': 'Muestra estratificada de fase 4; sensibilidad entre productos, sin validación de movilidad.',
    'comparison_route': '/api/expansion',
}


def get_release(evidence_dir=None, config_path=None, regional_evidence_dir=None) -> dict:
    """Load phase-5 release.

    The optional path arguments let callers (routers) forward patchable module-level
    constants so tests can override them without reaching into sub-layers directly.
    """
    reg_evidence = regional_evidence_dir if regional_evidence_dir is not None else reg_repo.EVIDENCE
    regional = reg_repo.load_release(reg_evidence)
    catalog_path = reg_evidence / 'candidatas.json'
    ev = evidence_dir if evidence_dir is not None else exp_repo.EVIDENCE
    cfg = config_path if config_path is not None else exp_repo.CONFIG
    return exp_repo.load_release(ev, cfg, regional['config'], catalog_path)


def get_comparison(reference_id: str, cell_m: int,
                   evidence_dir=None, config_path=None, regional_evidence_dir=None) -> dict:
    if reference_id != 'mars-jezero-fan' or cell_m not in SCENARIO['scales_m']:
        raise HTTPException(422, 'Referencia o escala no evaluada en este escenario')
    return {**get_release(evidence_dir, config_path, regional_evidence_dir), 'cell_m': cell_m}
