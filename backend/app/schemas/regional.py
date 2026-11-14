"""Pydantic models for regional search validation and parameters."""
from typing import Literal
from pydantic import BaseModel, Field

RegionalProfile = Literal['strict', 'baseline', 'relaxed']


class RegionalCandidatesQuery(BaseModel):
    area_id: str = Field('utah', description='Identificador del área geográfica')
    cell_m: int = Field(300, description='Tamaño de celda en metros')
    profile: RegionalProfile = Field('baseline', description='Perfil de filtros de similitud')
    include_excluded: bool = Field(False, description='Incluir candidatas que no superan los filtros')
    offset: int = Field(0, ge=0, description='Desplazamiento para paginación')
    limit: int = Field(20, ge=1, le=100, description='Cantidad máxima de resultados por página')


class RegionalExportQuery(BaseModel):
    area_id: str = Field('utah', description='Identificador del área geográfica')
    cell_m: int = Field(300, description='Tamaño de celda en metros')
    profile: RegionalProfile = Field('baseline', description='Perfil de filtros de similitud')
    include_excluded: bool = Field(False, description='Incluir candidatas que no superan los filtros')

