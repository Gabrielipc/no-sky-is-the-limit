"""Versioned, scenario-specific surface eligibility gates (WorldCover 2021 + JRC GSW).

Each profile states which surfaces count as "exposed" for one analog scenario and
which covers exclude a window. The same thresholds drive the Python classifier used
at extraction time and the SQL expression used to re-gate stored windows in DuckDB,
so a profile can be evaluated over the Parquet store without re-reading rasters.

Only one exclusion cause is reported per window, checked in a fixed order:
land support, cover support, water, trees, built-up, snow/ice, exposure, then climate.

Cover alone cannot tell a polar window from a subtropical desert: bare ground looks the same
in the Arctic and in Arabia. Profiles that stand for a cold scenario therefore also require a
cold climate, read from the coarse global layers (`enrichment_global`): months with snow
and permafrost fraction. A window with neither layer measured stays `pending_climate_check`
instead of being declared eligible without evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_LAND_FRACTION = 0.80
MIN_COVER_SUPPORT = 0.80
MAX_TREES_FOR_ROUGHNESS = 0.05

# WorldCover v200 class codes grouped by the fractions stored in base_windows.
WORLDCOVER_CLASSES = {
    'trees_fraction': (10,),
    'built_fraction': (50,),
    'bare_or_sparse_fraction': (60,),
    'snow_ice_fraction': (70,),
    'permanent_water_fraction': (80,),
    'moss_lichen_fraction': (100,),
}
WORLDCOVER_VALID = (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100)


@dataclass(frozen=True)
class EligibilityProfile:
    profile_id: str
    eligible_status: str
    exposed_fractions: tuple[str, ...]
    min_exposed: float
    max_water: float
    max_trees: float
    max_built: float
    max_snow_ice: float | None
    exposed_over_land_only: bool
    description: str
    # (min snow months fraction, min permafrost fraction); a window is cold when it meets either.
    cold_climate: tuple[float, float] | None = None


PROFILES: dict[str, EligibilityProfile] = {
    p.profile_id: p
    for p in (
        EligibilityProfile(
            profile_id='arid_mars_surface_v2',
            eligible_status='eligible_arid_exposed',
            exposed_fractions=('bare_or_sparse_fraction',),
            min_exposed=0.85,
            max_water=0.02,
            max_trees=0.05,
            max_built=0.02,
            max_snow_ice=0.05,
            exposed_over_land_only=False,
            description=(
                'Superficie árida expuesta análoga a Marte. Tolera hasta 2 % de agua '
                '(WorldCover permanente u ocurrencia JRC >= 50 %) en lugar de excluir por un píxel.'
            ),
        ),
        EligibilityProfile(
            profile_id='paleolake_margin_v1',
            eligible_status='eligible_paleolake_margin',
            exposed_fractions=('bare_or_sparse_fraction',),
            min_exposed=0.85,
            max_water=0.30,
            max_trees=0.05,
            max_built=0.02,
            max_snow_ice=0.05,
            exposed_over_land_only=True,
            description=(
                'Márgenes de playas, salares y lagos efímeros (análogos de paleolago/delta). '
                'Admite agua hasta 30 % y mide la exposición sobre la tierra no acuática.'
            ),
        ),
        EligibilityProfile(
            profile_id='polar_cold_v1',
            eligible_status='eligible_polar_cold_exposed',
            exposed_fractions=('bare_or_sparse_fraction', 'snow_ice_fraction', 'moss_lichen_fraction'),
            min_exposed=0.85,
            max_water=0.05,
            max_trees=0.05,
            max_built=0.02,
            max_snow_ice=None,
            exposed_over_land_only=False,
            description=(
                'Terreno frío expuesto para analogías lunares polares. Suelo desnudo, nieve/hielo '
                'y musgo/líquenes cuentan como superficie expuesta, y el clima debe ser frío: nieve al '
                'menos 3 de cada 12 meses o permafrost en al menos el 10 % de la huella.'
            ),
            cold_climate=(0.25, 0.10),
        ),
    )
}
DEFAULT_PROFILE = 'arid_mars_surface_v2'
ELIGIBLE_STATUSES = tuple(p.eligible_status for p in PROFILES.values())
EXCLUSION_STATUSES = (
    'excluded_insufficient_land',
    'pending_on_demand_cover_check',
    'excluded_permanent_water',
    'excluded_dense_canopy',
    'excluded_built',
    'excluded_snow_ice',
    'excluded_vegetated_non_tree',
    'excluded_warm_climate',
    'pending_climate_check',
)
SNOW_MONTHS_COLUMN = 'snow_months_fraction_cmg'
PERMAFROST_COLUMN = 'permafrost_fraction_cmg'


def get_profile(profile_id: str) -> EligibilityProfile:
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f'Perfil de elegibilidad desconocido: {profile_id}') from exc


def water_fraction(permanent_water: float | None, occurrence_ge50: float | None) -> float:
    """Larger of mapped permanent water (WorldCover) and historically frequent water (JRC >= 50 %)."""
    return max((v for v in (permanent_water, occurrence_ge50) if v is not None), default=0.0)


def classify(
    fractions: dict,
    land_fraction: float,
    cover_valid_fraction: float | None,
    profile_id: str = DEFAULT_PROFILE,
) -> str:
    """Return the eligibility status of one window under `profile_id`.

    `fractions` holds the WorldCover fractions named in `WORLDCOVER_CLASSES` plus the
    optional `water_occurrence_ge50_fraction` from JRC and, for profiles with a cold-climate
    gate, `snow_months_fraction_cmg` and `permafrost_fraction_cmg` from the global layers.
    """
    p = get_profile(profile_id)
    if land_fraction < MIN_LAND_FRACTION:
        return 'excluded_insufficient_land'
    if cover_valid_fraction is None or cover_valid_fraction < MIN_COVER_SUPPORT:
        return 'pending_on_demand_cover_check'

    def f(name: str) -> float:
        return fractions.get(name) or 0.0

    perm_water = f('permanent_water_fraction')
    if water_fraction(perm_water, fractions.get('water_occurrence_ge50_fraction')) > p.max_water:
        return 'excluded_permanent_water'
    if f('trees_fraction') > p.max_trees:
        return 'excluded_dense_canopy'
    if f('built_fraction') > p.max_built:
        return 'excluded_built'
    if p.max_snow_ice is not None and f('snow_ice_fraction') > p.max_snow_ice:
        return 'excluded_snow_ice'
    exposed = sum(f(name) for name in p.exposed_fractions)
    if p.exposed_over_land_only:
        land = 1.0 - perm_water
        exposed = exposed / land if land > 0 else 0.0
    if exposed < p.min_exposed:
        return 'excluded_vegetated_non_tree'
    if p.cold_climate is not None:
        snow, permafrost = fractions.get(SNOW_MONTHS_COLUMN), fractions.get(PERMAFROST_COLUMN)
        if snow is None and permafrost is None:
            return 'pending_climate_check'
        if (snow or 0.0) < p.cold_climate[0] and (permafrost or 0.0) < p.cold_climate[1]:
            return 'excluded_warm_climate'
    return p.eligible_status


def sql_case(profile_id: str = DEFAULT_PROFILE, climate: bool = True) -> str:
    """DuckDB CASE expression equivalent to `classify` over `base_windows` columns.

    Rows written before the scenario profiles existed (`cover_valid_fraction IS NULL`)
    lack the snow/ice, moss and JRC >= 50 % fractions, so they resolve to
    `pending_on_demand_cover_check` until they are re-extracted.

    A profile with a cold-climate gate reads `snow_months_fraction_cmg` and
    `permafrost_fraction_cmg`, which exist in `features_unified`. Pass `climate=False` over
    a table without them: the gate then sees both as unmeasured (`pending_climate_check`).
    """
    p = get_profile(profile_id)

    def c(name: str) -> str:
        return f'COALESCE({name}, 0.0)'

    water = (
        f"GREATEST({c('permanent_water_fraction')}, {c('water_occurrence_ge50_fraction')})"
    )
    exposed = ' + '.join(c(name) for name in p.exposed_fractions)
    if p.exposed_over_land_only:
        land = f"(1.0 - {c('permanent_water_fraction')})"
        exposed = f'CASE WHEN {land} > 0 THEN ({exposed}) / {land} ELSE 0.0 END'
    snow = (
        f"WHEN {c('snow_ice_fraction')} > {p.max_snow_ice!r} THEN 'excluded_snow_ice'"
        if p.max_snow_ice is not None else ''
    )
    if p.cold_climate is None:
        exposed_then = f"'{p.eligible_status}'"
    else:
        snow_col, perm_col = (SNOW_MONTHS_COLUMN, PERMAFROST_COLUMN) if climate else ('NULL', 'NULL')
        exposed_then = (
            f"CASE WHEN {snow_col} IS NULL AND {perm_col} IS NULL THEN 'pending_climate_check' "
            f"WHEN COALESCE({snow_col}, 0.0) < {p.cold_climate[0]!r} "
            f"AND COALESCE({perm_col}, 0.0) < {p.cold_climate[1]!r} THEN 'excluded_warm_climate' "
            f"ELSE '{p.eligible_status}' END"
        )
    return f"""CASE
        WHEN land_fraction < {MIN_LAND_FRACTION!r} THEN 'excluded_insufficient_land'
        WHEN cover_valid_fraction IS NULL OR cover_valid_fraction < {MIN_COVER_SUPPORT!r}
            THEN 'pending_on_demand_cover_check'
        WHEN {water} > {p.max_water!r} THEN 'excluded_permanent_water'
        WHEN {c('trees_fraction')} > {p.max_trees!r} THEN 'excluded_dense_canopy'
        WHEN {c('built_fraction')} > {p.max_built!r} THEN 'excluded_built'
        {snow}
        WHEN {exposed} >= {p.min_exposed!r} THEN {exposed_then}
        ELSE 'excluded_vegetated_non_tree'
    END"""


def eligibility_expression(profile_id: str, climate: bool = True) -> str:
    """Eligibility of each stored window under `profile_id`.

    Rows already gated with that profile keep their stored label (computed in float64
    at extraction); other rows are re-gated in SQL from their stored cover fractions.
    A profile with a cold-climate gate is always re-gated, because the label stored at
    extraction cannot know the global layers. `climate=False` is for queries over
    `base_windows`, which has no global columns.
    """
    profile = get_profile(profile_id)
    sql = sql_case(profile_id, climate)
    if profile.cold_climate is not None:
        return sql
    return f"CASE WHEN eligibility_profile = '{profile_id}' THEN analog_surface_eligibility ELSE {sql} END"
