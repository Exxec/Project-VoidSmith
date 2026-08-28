"""Structural combat-entity classification and recommendation eligibility.

This module deliberately sits beside, rather than inside, legality.  A local
fit can be legal even when the hull is a fighter-like, unboardable, module, or
composite entity that the ordinary ship recommendation engine must not rank.
All conclusions use explicit parsed hull size/hints only; no scripted behavior
or runtime boardability is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from starsector_variant_generator.analysis.composite_hulls import classify_hull_definition
from starsector_variant_generator.core.models import FighterWing, Hull


class CombatEntityKind(StrEnum):
    SHIP = "SHIP"
    COMPOSITE_PARENT = "COMPOSITE_PARENT"
    SHIP_MODULE = "SHIP_MODULE"
    FIGHTER = "FIGHTER"
    INTERCEPTOR = "INTERCEPTOR"
    BOMBER = "BOMBER"
    ASSAULT_FIGHTER = "ASSAULT_FIGHTER"
    SUPPORT_FIGHTER = "SUPPORT_FIGHTER"
    DRONE = "DRONE"
    MECH = "MECH"
    STRIKECRAFT = "STRIKECRAFT"
    STATION_MODULE = "STATION_MODULE"
    UNBOARDABLE_COMBAT_ENTITY = "UNBOARDABLE_COMBAT_ENTITY"
    UNKNOWN_SPECIAL = "UNKNOWN_SPECIAL"
    # Compatibility aliases for the first structural-eligibility slice.
    NORMAL_SHIP = "SHIP"
    FIGHTER_LIKE_HULL = "FIGHTER"
    FIGHTER_WING_MEMBER = "FIGHTER"


class DeploymentModel(StrEnum):
    INDEPENDENT = "INDEPENDENT"
    WING_BASED = "WING_BASED"
    BUILT_IN = "BUILT_IN"
    SYSTEM_SPAWNED = "SYSTEM_SPAWNED"
    MODULE_ATTACHED = "MODULE_ATTACHED"
    UNBOARDABLE_INDEPENDENT = "UNBOARDABLE_INDEPENDENT"
    UNKNOWN = "UNKNOWN"


class StructuralSupport(StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class RecommendationEligibility:
    entity_kind: CombatEntityKind
    deployment_model: DeploymentModel
    structural_support: StructuralSupport
    eligible: bool
    reason: str
    confidence: float


@dataclass(frozen=True)
class FighterWingEntityProfile:
    """Direct source-role classification for a carrier-deployed wing.

    Scores are not performance predictions: only the source's role label is
    promoted to a 1.0 direct tag. Payload, replacement, and delivery metrics
    require fields the current parser does not yet normalize.
    """

    entity_kind: CombatEntityKind
    deployment_model: DeploymentModel
    role_scores: dict[str, float]
    confidence: float


def classify_combat_entity_kind(hull: Hull) -> CombatEntityKind:
    """Classify a Hull's parseable structural role without judging legality."""
    definition = classify_hull_definition(hull)
    hints = {hint.upper() for hint in hull.hull_hints}
    # These are explicit author-provided structural labels, never guesses from
    # slot count, names, or custom AI source files.
    for hint, kind in (("MECH", CombatEntityKind.MECH), ("DRONE", CombatEntityKind.DRONE), ("STRIKECRAFT", CombatEntityKind.STRIKECRAFT)):
        if hint in hints:
            return kind
    if "UNBOARDABLE" in hints:
        return CombatEntityKind.UNBOARDABLE_COMBAT_ENTITY
    if (hull.hull_size or "").upper() == "FIGHTER":
        return CombatEntityKind.FIGHTER
    if definition.is_station and (definition.is_module or definition.is_under_parent):
        return CombatEntityKind.STATION_MODULE
    if definition.is_module or definition.is_under_parent:
        return CombatEntityKind.SHIP_MODULE
    if definition.is_parent:
        return CombatEntityKind.COMPOSITE_PARENT
    return CombatEntityKind.SHIP


def classify_fighter_wing_entity(wing: FighterWing) -> FighterWingEntityProfile:
    """Classify an actual parsed wing without assuming its member hull type."""
    role = (wing.role or "").strip().upper().replace(" ", "_")
    if "BOMBER" in role:
        kind, score = CombatEntityKind.BOMBER, "BOMBER"
    elif "INTERCEPT" in role or "SUPERIORITY" in role:
        kind, score = CombatEntityKind.INTERCEPTOR, "INTERCEPTOR"
    elif "DRONE" in role:
        kind, score = CombatEntityKind.DRONE, "DRONE"
    elif "ASSAULT" in role or "GUNSHIP" in role:
        kind, score = CombatEntityKind.ASSAULT_FIGHTER, "ASSAULT_FIGHTER"
    elif "SUPPORT" in role or "ESCORT" in role or "PD" in role:
        kind, score = CombatEntityKind.SUPPORT_FIGHTER, "SUPPORT_FIGHTER"
    else:
        kind, score = CombatEntityKind.FIGHTER, "FIGHTER"
    return FighterWingEntityProfile(kind, DeploymentModel.WING_BASED, {score: 1.0}, 1.0 if wing.role else 0.0)


def deployment_model(hull: Hull) -> DeploymentModel:
    """Declared deployment facts for a Hull; fighter geometry alone is unknown."""
    definition = classify_hull_definition(hull)
    hints = {hint.upper() for hint in hull.hull_hints}
    if definition.is_module or definition.is_under_parent:
        return DeploymentModel.MODULE_ATTACHED
    if "UNBOARDABLE" in hints:
        return DeploymentModel.UNBOARDABLE_INDEPENDENT
    if (hull.hull_size or "").upper() == "FIGHTER":
        return DeploymentModel.UNKNOWN
    return DeploymentModel.INDEPENDENT


def recommendation_eligibility(hull: Hull) -> RecommendationEligibility:
    """Whether this hull may enter ordinary independently-fitted ship ranking."""
    kind = classify_combat_entity_kind(hull)
    deployment = deployment_model(hull)
    if kind is CombatEntityKind.SHIP:
        return RecommendationEligibility(kind, deployment, StructuralSupport.FULL, True, "NORMAL_INDEPENDENT_SHIP", 1.0)
    if kind is CombatEntityKind.COMPOSITE_PARENT:
        return RecommendationEligibility(kind, deployment, StructuralSupport.PARTIAL, False, "COMPOSITE_PARENT_AGGREGATE_BEHAVIOR_UNMODELED", 1.0)
    if kind in {CombatEntityKind.FIGHTER, CombatEntityKind.MECH, CombatEntityKind.DRONE, CombatEntityKind.STRIKECRAFT}:
        return RecommendationEligibility(kind, deployment, StructuralSupport.PARTIAL, False, "FIGHTER_LIKE_HULL_WITH_INDEPENDENT_FIT_SEMANTICS", 1.0)
    if kind is CombatEntityKind.UNBOARDABLE_COMBAT_ENTITY:
        return RecommendationEligibility(kind, deployment, StructuralSupport.PARTIAL, False, "UNBOARDABLE_HULL", 1.0)
    if kind in {CombatEntityKind.SHIP_MODULE, CombatEntityKind.STATION_MODULE}:
        return RecommendationEligibility(kind, deployment, StructuralSupport.UNSUPPORTED, False, "MODULE_LOCAL_FIT_NOT_ORDINARY_SHIP_RECOMMENDATION", 1.0)
    return RecommendationEligibility(kind, deployment, StructuralSupport.PARTIAL, False, "UNKNOWN_SPECIAL_ENTITY", 0.0)
