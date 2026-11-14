"""Pydantic models for search requests and weights."""
from pydantic import BaseModel, Field


class Weights(BaseModel):
    slope_deg: float = Field(1, ge=0, le=10)
    relief_m: float = Field(1, ge=0, le=10)


class Search(BaseModel):
    reference_id: str
    weights: Weights
