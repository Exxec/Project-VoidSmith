"""Deterministic build-archetype inference for a specific hull.

Mechanical archetypes describe what a hull is; build archetypes describe a
viable way to fit and operate it.  They are deliberately non-exclusive and
quality-only: this module never contributes to legality.
"""

from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.analysis.mechanical_archetypes import MechanicalArchetypeProfile, infer_mechanical_archetypes
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Hull
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.analysis.scenario_objectives import ScenarioObjective, scenario_objectives_for_build
from starsector_variant_generator.core.evidence import EvidenceClass


@dataclass(frozen=True)
class BuildArchetypeProfile:
    hull_id: str
    build_id: str
    role: str
    tactical_style: str
    compatibility: float
    confidence: float
    maturity: str  # VIABLE | EXPERIMENTAL
    target_range: str
    flux_posture: str
    survivability_posture: str
    equipment_priorities: tuple[str, ...]
    ai_suitability: str
    player_suitability: str
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    scenario_objectives: tuple[ScenarioObjective, ...] = ()
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


_SPECS = (
    ("TANK", "Tank", "HOLD_LINE", "SHORT", "CONSERVATIVE", "MAXIMUM", "LINE_BRAWLER", "ARMOR_BRAWLER", "SHIELD_BRAWLER", ("DEFENSES", "SHORT_RANGE", "FLUX_STABILITY")),
    ("LINE_ANCHOR", "Line Anchor", "HOLD_LINE", "MEDIUM", "BALANCED", "HIGH", "LINE_BRAWLER", "LINE_SHIP", "SHIELD_BRAWLER", ("BALANCED_BATTERY", "DEFENSES", "PD")),
    ("FINISHER", "Finisher", "FLANK_AND_COMMIT", "SHORT", "AGGRESSIVE", "MEDIUM", "LINE_BRAWLER", "STRIKER", "SKIRMISHER", ("BURST_DAMAGE", "MOBILITY", "FLUX_CAPACITY")),
    ("PD_ESCORT", "PD Escort", "SCREEN_ALLIES", "SHORT", "BALANCED", "MEDIUM", "MISSILE_SUPPORT", "PD_ESCORT", "SKIRMISHER", ("PD", "MOBILITY", "FLUX_STABILITY")),
    ("ARTILLERY", "Artillery", "STAND_OFF", "LONG", "CONSERVATIVE", "MEDIUM", "LINE_ARTILLERY", "ARTILLERY", "LINE_SHIP", ("LONG_RANGE", "FLUX_STABILITY", "PD")),
    ("MISSILE_SUPPORT", "Missile Support", "SALVO_SUPPORT", "MEDIUM", "BALANCED", "MEDIUM", "MISSILE_SUPPORT", "MISSILE_SUPPORT", "LINE_SHIP", ("MISSILES", "PD", "FLUX_STABILITY")),
    ("CARRIER_SUPPORT", "Carrier Support", "STAND_OFF", "MEDIUM", "CONSERVATIVE", "MEDIUM", "CARRIER", "LIGHT_CARRIER", "HEAVY_CARRIER", ("FIGHTERS", "PD", "FLUX_STABILITY")),
    ("BATTLECARRIER", "Battlecarrier", "HOLD_LINE", "MEDIUM", "BALANCED", "HIGH", "BATTLE_CARRIER", "BATTLECARRIER", "HEAVY_CARRIER", ("FIGHTERS", "BALANCED_BATTERY", "DEFENSES")),
)

_PROFILE_BY_BUILD = {
    "TANK": "TANK", "LINE_ANCHOR": "LINE_BRAWLER", "FINISHER": "FAST_STRIKE",
    "PD_ESCORT": "PD_ESCORT", "ARTILLERY": "LINE_ARTILLERY", "MISSILE_SUPPORT": "MISSILE_SUPPORT",
    "CARRIER_SUPPORT": "CARRIER_SUPPORT", "BATTLECARRIER": "CARRIER_SUPPORT",
}


def profile_id_for_build(build_id: str) -> str:
    return _PROFILE_BY_BUILD[build_id]


def infer_build_archetypes(hull: Hull, registry: Registry, heuristic_set: str = "baseline_0.4") -> tuple[BuildArchetypeProfile, ...]:
    """Return every mechanically supported build path, deterministically.

    A path above the viable threshold is ``VIABLE``.  A path above the lower
    experimental threshold is retained as ``EXPERIMENTAL`` rather than being
    represented as equally certain.  Paths below both thresholds are omitted.
    """
    values = get_heuristic_set(heuristic_set).values
    mechanical = infer_mechanical_archetypes(hull, registry)
    functional = classify_hull(hull).role_compatibility
    profiles: list[BuildArchetypeProfile] = []
    missing = sum(value is None for value in (
        mechanical.feature_vector.armor_rating, mechanical.feature_vector.hull_hitpoints,
        mechanical.feature_vector.has_shield, mechanical.feature_vector.max_speed,
        mechanical.feature_vector.flux_dissipation,
    ))
    confidence = max(0.0, 1.0 - missing * values["build_archetype_unknown_feature_confidence_penalty"])
    for build_id, role, style, target_range, flux, survival, function_axis, primary, secondary, priorities in _SPECS:
        structural = mechanical.compatibility_scores[primary]
        secondary_score = mechanical.compatibility_scores[secondary]
        function_score = functional.get(function_axis, 0.0)
        compatibility = round(min(1.0, .55 * structural + .25 * secondary_score + .20 * function_score), 6)
        if compatibility < values["build_archetype_experimental_min_compatibility"]:
            continue
        maturity = "VIABLE" if compatibility >= values["build_archetype_viable_min_compatibility"] else "EXPERIMENTAL"
        evidence = _evidence(build_id, mechanical, function_axis, function_score, compatibility, maturity)
        profiles.append(BuildArchetypeProfile(
            hull.id, build_id, role, style, compatibility, round(confidence, 3), maturity,
            target_range, flux, survival, priorities,
            "GOOD" if maturity == "VIABLE" and style != "FLANK_AND_COMMIT" else "CONDITIONAL",
            "GOOD" if style == "FLANK_AND_COMMIT" else "GOOD",
            _strengths(primary, secondary), _weaknesses(maturity, target_range, flux), evidence,
            scenario_objectives_for_build(build_id),
        ))
    return tuple(sorted(profiles, key=lambda profile: (-profile.compatibility, profile.build_id)))


def _evidence(build_id: str, mechanical: MechanicalArchetypeProfile, function_axis: str, function_score: float, compatibility: float, maturity: str) -> tuple[str, ...]:
    return (
        f"build={build_id}; compatibility={compatibility:.6f}; maturity={maturity}",
        f"functional_role[{function_axis}]={function_score:.6f}",
        *mechanical.evidence_by_archetype[build_id if build_id in mechanical.evidence_by_archetype else _primary_for_build(build_id)],
    )


def _primary_for_build(build_id: str) -> str:
    return next(spec[7] for spec in _SPECS if spec[0] == build_id)


def _strengths(primary: str, secondary: str) -> tuple[str, ...]:
    return (f"Mechanically compatible with {primary}.", f"Secondary evidence supports {secondary}.")


def _weaknesses(maturity: str, target_range: str, flux: str) -> tuple[str, ...]:
    notes = [f"Target range posture: {target_range}.", f"Flux posture: {flux}."]
    if maturity == "EXPERIMENTAL":
        notes.append("Compatibility is below the normal viable threshold; verify this build in context.")
    return tuple(notes)
