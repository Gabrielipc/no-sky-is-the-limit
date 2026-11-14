"""Pydantic models for 30m Atlas search criteria."""
from typing import Optional
from pydantic import BaseModel, Field


class AtlasSearchCriteria(BaseModel):
    version: Optional[str] = Field(None, description='Versión del índice de 30m')
    slope: float = Field(50.0, ge=0, le=100, description='Peso de pendiente')
    relief: float = Field(30.0, ge=0, le=100, description='Peso de relieve')
    roughness: float = Field(20.0, ge=0, le=100, description='Peso de rugosidad')
    bare_min: Optional[float] = Field(None, ge=0, le=1, description='Fracción mínima de suelo desnudo')
    water_max: Optional[float] = Field(None, ge=0, le=100, description='Porcentaje máximo de presencia de agua')
    limit: int = Field(25, ge=1, le=100, description='Límite de resultados')
    offset: int = Field(0, ge=0, description='Desplazamiento')
