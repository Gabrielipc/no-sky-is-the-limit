"""Pydantic models for scenario comparison and metadata."""
from pydantic import BaseModel, Field


class ScenarioComparisonQuery(BaseModel):
    scenario_id: str = Field(..., description='Identificador del escenario')
    reference_id: str = Field('mars-jezero-fan', description='Referencia marciana')
    cell_m: int = Field(60, description='Escala en metros')
    candidate_id: str = Field('earth-utah', description='Candidata terrestre')
