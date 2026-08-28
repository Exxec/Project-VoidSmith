"""Acceptance contract for non-simple hulls without simulated module behavior."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ComplexHullFeature(StrEnum):
    MULTIPART_PARENT_CHILD = "MULTIPART_PARENT_CHILD"
    REPEATED_MODULES = "REPEATED_MODULES"
    ASYMMETRIC_MODULES = "ASYMMETRIC_MODULES"
    INDEPENDENT_SHIELDS = "INDEPENDENT_SHIELDS"
    MODULE_LOCAL_WEAPONS = "MODULE_LOCAL_WEAPONS"
    MODULE_LOCAL_SYSTEMS = "MODULE_LOCAL_SYSTEMS"
    DESTROYABLE_SECTIONS = "DESTROYABLE_SECTIONS"
    STATION_STYLE_MODULES = "STATION_STYLE_MODULES"
    DETACHABLE_COMPONENTS = "DETACHABLE_COMPONENTS"
    SCRIPTED_MODULE_BEHAVIOR = "SCRIPTED_MODULE_BEHAVIOR"


class ComplexHullAcceptance(StrEnum):
    STRUCTURAL_MARKER_ONLY = "STRUCTURAL_MARKER_ONLY"
    STRUCTURAL_PROFILE = "STRUCTURAL_PROFILE"
    PARSED_SEPARATELY = "PARSED_SEPARATELY"
    PROVENANCE_ONLY = "PROVENANCE_ONLY"
    UNKNOWN_SCRIPTED_EFFECT = "UNKNOWN_SCRIPTED_EFFECT"
    NOT_DETERMINABLE = "NOT_DETERMINABLE"


@dataclass(frozen=True)
class ComplexHullAcceptanceEntry:
    feature: ComplexHullFeature
    acceptance: ComplexHullAcceptance
    current_scope: str
    generation_policy: str


COMPLEX_HULL_ACCEPTANCE_MATRIX: tuple[ComplexHullAcceptanceEntry, ...] = (
    ComplexHullAcceptanceEntry(ComplexHullFeature.MULTIPART_PARENT_CHILD, ComplexHullAcceptance.STRUCTURAL_PROFILE, "Declared parent slot -> child variant references are normalized into structural-only profiles.", "Do not claim a composite fit is validated; parent and child are separate analyses."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.REPEATED_MODULES, ComplexHullAcceptance.STRUCTURAL_PROFILE, "Repeated child variant mappings are retained as distinct parent-slot records.", "No aggregate score/recommendation."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.ASYMMETRIC_MODULES, ComplexHullAcceptance.STRUCTURAL_PROFILE, "Distinct child variant mappings are retained as structural asymmetry only.", "No aggregate score/recommendation."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.INDEPENDENT_SHIELDS, ComplexHullAcceptance.NOT_DETERMINABLE, "Only the currently inspected hull's parsed shield fields are known.", "No composite shield/tank conclusion."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.MODULE_LOCAL_WEAPONS, ComplexHullAcceptance.PARSED_SEPARATELY, "A module hull's own documented mounts can be parsed and validated as that hull only.", "Allow local fit analysis; never merge into a parent fit."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.MODULE_LOCAL_SYSTEMS, ComplexHullAcceptance.PROVENANCE_ONLY, "Local system identifiers may be preserved as raw evidence until a documented adapter exists.", "No system-effect scoring or composite conclusion."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.DESTROYABLE_SECTIONS, ComplexHullAcceptance.NOT_DETERMINABLE, "Section health/destruction semantics are not modeled.", "No survivability aggregation."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.STATION_STYLE_MODULES, ComplexHullAcceptance.STRUCTURAL_PROFILE, "Station parent hints are retained on structural-only composite profiles.", "No station composite generation."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.DETACHABLE_COMPONENTS, ComplexHullAcceptance.NOT_DETERMINABLE, "Detachment and post-detachment state are not modeled.", "No mobility/survivability conclusion."),
    ComplexHullAcceptanceEntry(ComplexHullFeature.SCRIPTED_MODULE_BEHAVIOR, ComplexHullAcceptance.UNKNOWN_SCRIPTED_EFFECT, "Custom module scripts are never executed; unrecognized portions remain explicit.", "Not determinable when behavior affects legality or score."),
)


def complex_hull_matrix_entry(feature: ComplexHullFeature) -> ComplexHullAcceptanceEntry:
    return next(entry for entry in COMPLEX_HULL_ACCEPTANCE_MATRIX if entry.feature == feature)
