"""Evidence-gated player-fleet alignment for explicitly declared scenarios.

This is not the existing faction-gap ScenarioCategory overlay and not a combat
simulator. A scenario describes generic pressures and desired capabilities;
the advisor compares them to a locked player selection and can reuse Fleet
Support Advisor's individual-addition ranking.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from starsector_variant_generator.analysis.capability_vector import CAPABILITY_DIMENSIONS, CapabilityEvidence
from starsector_variant_generator.analysis.fleet_support import FleetSelection, FleetSupportConstraints, FleetSupportNeed, FleetSupportRecommendation, analyze_player_fleet, recommend_fleet_support
from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import Registry


class ScenarioPressure(StrEnum):
    BURST_REQUIRED = "BURST_REQUIRED"; SUSTAINED_ENDURANCE = "SUSTAINED_ENDURANCE"; PRIORITY_TARGET_REMOVAL = "PRIORITY_TARGET_REMOVAL"; SWARM_CONTROL = "SWARM_CONTROL"; FIGHTER_SUPPRESSION = "FIGHTER_SUPPRESSION"; MISSILE_DEFENSE = "MISSILE_DEFENSE"; CAPITAL_BREAKING = "CAPITAL_BREAKING"; ARMOR_BREAKING = "ARMOR_BREAKING"; SHIELD_BREAKING = "SHIELD_BREAKING"; PURSUIT = "PURSUIT"; OBJECTIVE_CAPTURE = "OBJECTIVE_CAPTURE"; AREA_CONTROL = "AREA_CONTROL"; ALLY_PROTECTION = "ALLY_PROTECTION"; FLAGSHIP_SURVIVAL = "FLAGSHIP_SURVIVAL"; LOW_LOSS_TOLERANCE = "LOW_LOSS_TOLERANCE"; TIME_PRESSURE = "TIME_PRESSURE"; RANGE_CONTROL = "RANGE_CONTROL"; MOBILITY_CHECK = "MOBILITY_CHECK"


@dataclass(frozen=True)
class ScenarioCapabilityTarget:
    capability: str
    target: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioObjectiveProfile:
    scenario_id: str
    display_name: str
    capability_targets: tuple[ScenarioCapabilityTarget, ...]
    pressures: tuple[ScenarioPressure, ...] = ()
    evidence_class: str = "USER_DECLARED"
    confidence: float = .60
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioAlignment:
    capability: str
    target: float
    available: float | None
    gap: float | None
    confidence: float
    status: str  # STRONG | ADEQUATE | WEAK | UNKNOWN
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioFleetAssessment:
    scenario: ScenarioObjectiveProfile
    readiness: str  # GOOD | MIXED | POOR | UNKNOWN
    readiness_score: float | None
    confidence: float
    strengths: tuple[ScenarioAlignment, ...]
    deficiencies: tuple[ScenarioAlignment, ...]
    unknowns: tuple[ScenarioAlignment, ...]
    recommendations: tuple[FleetSupportRecommendation, ...]
    evidence: tuple[str, ...]


def user_defined_scenario(scenario_id: str, display_name: str, targets: tuple[ScenarioCapabilityTarget, ...], pressures: tuple[ScenarioPressure, ...] = ()) -> ScenarioObjectiveProfile:
    if not scenario_id.strip() or not display_name.strip() or not targets:
        raise ValueError("A user-defined scenario requires an id, display name, and at least one capability target")
    for target in targets:
        if target.capability not in CAPABILITY_DIMENSIONS:
            raise ValueError(f"Unknown scenario capability: {target.capability}")
        if not 0.0 <= target.target <= 1.0:
            raise ValueError(f"Scenario target for {target.capability} must be between 0 and 1")
    return ScenarioObjectiveProfile(scenario_id, display_name, targets, pressures, "USER_DECLARED", .60, ("Scenario pressures and targets were explicitly supplied by the user; no encounter behavior was inferred.",))


def generic_scenario_profiles() -> tuple[ScenarioObjectiveProfile, ...]:
    """Non-mod-specific templates built solely from existing dimensions."""
    return (
        ScenarioObjectiveProfile("priority_target_assault", "Priority Target Assault", (ScenarioCapabilityTarget("BURST_STRIKE", .75), ScenarioCapabilityTarget("FINISHING_POWER", .75), ScenarioCapabilityTarget("MOBILITY", .55), ScenarioCapabilityTarget("ARMOR_BREAKING", .55)), (ScenarioPressure.BURST_REQUIRED, ScenarioPressure.PRIORITY_TARGET_REMOVAL, ScenarioPressure.TIME_PRESSURE), "GENERIC_TEMPLATE", .50, ("Generic declared scenario template; it is not a prediction of any named encounter.",)),
        ScenarioObjectiveProfile("swarm_defense", "Swarm Defense", (ScenarioCapabilityTarget("PD_SCREENING", .75), ScenarioCapabilityTarget("FIGHTER_INTERCEPTION", .60), ScenarioCapabilityTarget("SUSTAINED_PRESSURE", .50)), (ScenarioPressure.SWARM_CONTROL, ScenarioPressure.FIGHTER_SUPPRESSION, ScenarioPressure.MISSILE_DEFENSE), "GENERIC_TEMPLATE", .50, ("Generic declared scenario template; it is not a prediction of any named encounter.",)),
        ScenarioObjectiveProfile("line_breaker", "Capital / Line Breaker", (ScenarioCapabilityTarget("ARMOR_BREAKING", .70), ScenarioCapabilityTarget("KINETIC_PRESSURE", .65), ScenarioCapabilityTarget("FINISHING_POWER", .55), ScenarioCapabilityTarget("ARMOR_TANKING", .45)), (ScenarioPressure.CAPITAL_BREAKING, ScenarioPressure.ARMOR_BREAKING, ScenarioPressure.SHIELD_BREAKING), "GENERIC_TEMPLATE", .50, ("Generic declared scenario template; it is not a prediction of any named encounter.",)),
    )


def assess_scenario_fleet(selections: tuple[FleetSelection, ...], registry: Registry, scenario: ScenarioObjectiveProfile, faction: Faction | None = None, heuristic_set: str = "baseline_0.14", constraints: FleetSupportConstraints = FleetSupportConstraints()) -> ScenarioFleetAssessment:
    fleet = analyze_player_fleet(selections, registry, heuristic_set, constraints.focus)
    alignments = tuple(_alignment(target, fleet.capability_vector.get(target.capability), scenario.confidence) for target in scenario.capability_targets)
    known = [item for item in alignments if item.available is not None]
    score = sum(min((item.available or 0.0) / item.target, 1.0) for item in known) / len(known) if known else None
    confidence = sum(item.confidence for item in known) / len(known) if known else 0.0
    readiness = "UNKNOWN" if score is None else "GOOD" if score >= .75 else "MIXED" if score >= .45 else "POOR"
    deficiencies = tuple(sorted((item for item in alignments if item.status == "WEAK"), key=lambda item: (-float(item.gap or 0.0), item.capability)))
    needs = tuple(FleetSupportNeed(item.capability, float(item.gap or 0.0), item.confidence, "COMBAT", item.evidence) for item in deficiencies)
    recommendations = recommend_fleet_support(selections, registry, faction, heuristic_set, constraints, needs, replace_support_needs=True).recommendations if needs else ()
    return ScenarioFleetAssessment(scenario, readiness, round(score, 6) if score is not None else None, round(confidence, 6), tuple(item for item in alignments if item.status in {"STRONG", "ADEQUATE"}), deficiencies, tuple(item for item in alignments if item.status == "UNKNOWN"), recommendations, ("Mechanical alignment only: this assessment does not simulate the encounter, scripted behavior, AI, deployment points, campaign state, or victory probability.", *scenario.evidence))


def _alignment(target: ScenarioCapabilityTarget, evidence: CapabilityEvidence | None, scenario_confidence: float) -> ScenarioAlignment:
    if evidence is None or evidence.score is None:
        return ScenarioAlignment(target.capability, target.target, None, None, 0.0, "UNKNOWN", (*target.evidence, "Fleet capability evidence is unavailable."))
    gap = max(0.0, target.target - evidence.score)
    status = "STRONG" if evidence.score >= target.target else "ADEQUATE" if evidence.score >= target.target * .70 else "WEAK"
    return ScenarioAlignment(target.capability, target.target, evidence.score, round(gap, 6), round(evidence.confidence * scenario_confidence, 6), status, (*target.evidence, *evidence.supporting_evidence))
