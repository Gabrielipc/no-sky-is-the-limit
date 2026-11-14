"""Pydantic models for mineral analysis and CRISM/EMIT parameters."""
from pydantic import BaseModel, Field


class MineralQuery(BaseModel):
    candidate_id: str = Field('earth-utah', description='Identificador del sitio terrestre (earth-utah o earth-atacama)')
