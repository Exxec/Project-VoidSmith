"""Bounded scenario objectives for build-archetype presentation and generation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioObjective:
    objective_id: str
    support_state: str  # SUPPORTED | PARTIAL | UNSUPPORTED
    required_signals: tuple[str, ...]
    note: str


_OBJECTIVES: dict[str, tuple[ScenarioObjective, ...]] = {
    "TANK": (ScenarioObjective("LINE_HOLD", "SUPPORTED", ("DEFENSE_POSTURE", "SHORT_RANGE_PROFILE"), "Uses the existing Tank profile and verified defense tie-breaks."),),
    "LINE_ANCHOR": (ScenarioObjective("LINE_HOLD", "SUPPORTED", ("MEDIUM_RANGE_PROFILE", "RANGE_COHERENCE"), "Uses the existing Line Brawler profile."),),
    "FINISHER": (
        ScenarioObjective("BREAKTHROUGH", "SUPPORTED", ("SHORT_RANGE_PROFILE", "MOBILITY_POSTURE"), "Uses the existing Fast Strike profile."),
        ScenarioObjective("ANTI_ARMOR", "UNSUPPORTED", (), "Weapon armor-breaking behavior is not normalized sufficiently for objective scoring."),
        ScenarioObjective("ANTI_FRIGATE", "UNSUPPORTED", (), "Target-class engagement behavior is not modeled."),
        ScenarioObjective("PURSUIT", "PARTIAL", ("MOBILITY_POSTURE",), "Hull mobility is known; campaign/combat pursuit behavior is not simulated."),
    ),
    "PD_ESCORT": (ScenarioObjective("SCREEN_ALLIES", "SUPPORTED", ("PD_WEAPON_TAGS",), "Uses documented PD weapon tags."),),
    "ARTILLERY": (ScenarioObjective("LONG_RANGE_PRESSURE", "SUPPORTED", ("LONG_RANGE_PROFILE", "WEAPON_RANGE"), "Uses documented weapon range and artillery threshold."),),
    "MISSILE_SUPPORT": (ScenarioObjective("MISSILE_PROJECTION", "SUPPORTED", ("MISSILE_MOUNTS",), "Uses documented missile mount composition."),),
    "CARRIER_SUPPORT": (ScenarioObjective("CARRIER_PROJECTION", "SUPPORTED", ("FIGHTER_BAYS", "FIGHTER_WINGS"), "Uses parsed bay capacity and fighter-wing selection."),),
    "BATTLECARRIER": (ScenarioObjective("CARRIER_LINE_SUPPORT", "PARTIAL", ("FIGHTER_BAYS", "MEDIUM_RANGE_PROFILE"), "Carrier and line evidence are independent; their interaction is not simulated."),),
}


def scenario_objectives_for_build(build_id: str) -> tuple[ScenarioObjective, ...]:
    return _OBJECTIVES.get(build_id, ())
