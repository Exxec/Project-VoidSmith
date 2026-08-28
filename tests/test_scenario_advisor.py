from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.analysis.fleet_support import FleetSelection, FleetSupportConstraints
from starsector_variant_generator.analysis.scenario_advisor import ScenarioCapabilityTarget, ScenarioPressure, assess_scenario_fleet, generic_scenario_profiles, user_defined_scenario
from starsector_variant_generator.core.models import Hull, ScanResult
from starsector_variant_generator.core.registry import Registry


SOURCE = Path("fixture")


def hull(hull_id: str, *, armor: int, flux: int, speed: int, mounts: int) -> Hull:
    return Hull(hull_id, hull_id, "core", SOURCE, hull_size="FRIGATE", ordnance_points=40,
                weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(mounts)),
                flux_capacity=flux * 10, flux_dissipation=flux,
                raw={"armor rating": armor, "hitpoints": armor * 8, "max speed": speed, "acceleration": speed, "max turn rate": speed})


class ScenarioAdvisorTests(unittest.TestCase):
    def test_user_defined_profile_rejects_unknown_or_out_of_range_capabilities(self) -> None:
        with self.assertRaises(ValueError):
            user_defined_scenario("x", "X", (ScenarioCapabilityTarget("NOT_A_CAPABILITY", .5),))
        with self.assertRaises(ValueError):
            user_defined_scenario("x", "X", (ScenarioCapabilityTarget("MOBILITY", 1.1),))

    def test_generic_profiles_are_generic_and_not_named_mod_missions(self) -> None:
        profiles = generic_scenario_profiles()
        self.assertEqual({"priority_target_assault", "swarm_defense", "line_breaker"}, {item.scenario_id for item in profiles})
        self.assertTrue(all(item.evidence_class == "GENERIC_TEMPLATE" for item in profiles))

    def test_assessment_reports_mechanical_alignment_and_ranks_individual_additions(self) -> None:
        selected = hull("selected", armor=100, flux=100, speed=60, mounts=1)
        candidate = hull("candidate", armor=1800, flux=1600, speed=50, mounts=7)
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate]))
        scenario = user_defined_scenario("hold", "Hold the Line", (ScenarioCapabilityTarget("ARMOR_TANKING", .80),), (ScenarioPressure.LOW_LOSS_TOLERANCE,))
        result = assess_scenario_fleet((FleetSelection("selected"),), registry, scenario, heuristic_set="baseline_0.14", constraints=FleetSupportConstraints(recommendation_count=1))
        self.assertIn(result.readiness, {"POOR", "MIXED"})
        self.assertEqual("ARMOR_TANKING", result.deficiencies[0].capability)
        self.assertEqual("candidate", result.recommendations[0].hull_id)
        self.assertIn("mechanical alignment", result.evidence[0].lower())
        self.assertNotIn("victory", result.readiness)

    def test_api_respects_the_same_locked_selection_boundary(self) -> None:
        selected = hull("selected", armor=100, flux=100, speed=60, mounts=1)
        candidate = hull("candidate", armor=1800, flux=1600, speed=50, mounts=7)
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate]))
        scenario = user_defined_scenario("hold", "Hold the Line", (ScenarioCapabilityTarget("ARMOR_TANKING", .80),))
        result = api.run_scenario_fleet_advisor(registry, (FleetSelection("selected"),), scenario, constraints=FleetSupportConstraints(recommendation_count=1))
        self.assertNotIn("selected", {item.hull_id for item in result.recommendations})


if __name__ == "__main__":
    unittest.main()
