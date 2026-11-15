"""Pydantic models of the similarity API (`specs/api/similitud-api-v1.schema.json`)."""
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PROFILE = 'arid_mars_surface_v2'
PROFILES = ('arid_mars_surface_v2', 'paleolake_margin_v1', 'polar_cold_v1')


class ReferenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Optional[str] = Field(None, max_length=96)
    name: Optional[str] = Field(None, max_length=200)
    body: Literal['Mars', 'Moon', 'Earth']
    features: Dict[str, Optional[float]] = Field(default_factory=dict, max_length=64)
    percentiles: Dict[str, float] = Field(default_factory=dict, max_length=64)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reference: Union[str, ReferenceInput]
    weights: Optional[Dict[str, float]] = None
    profile: Literal['arid_mars_surface_v2', 'paleolake_margin_v1', 'polar_cold_v1'] = DEFAULT_PROFILE
    only_eligible: bool = True
    limit: int = Field(25, ge=1, le=1000)
    missing_policy: Optional[Literal['neutral', 'renormalize', 'require']] = None
    fusion: Optional[Literal['weighted', 'rrf']] = None
    bbox: Optional[List[float]] = Field(None, min_length=4, max_length=4)
