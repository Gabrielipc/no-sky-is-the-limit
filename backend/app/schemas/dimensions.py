"""Pydantic models for multidimensional surface comparison."""
from pydantic import BaseModel, Field


class DimensionsComparisonQuery(BaseModel):
    cell_m: int = Field(60, description='Escala espacial en metros (60 o 120)')
    candidate_id: str = Field('earth-utah', description='Identificador del sitio terrestre')
    reference_id: str = Field('mars-jezero-fan', description='Identificador del sitio marciano de referencia')

