from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.fleet_support import (
    FleetSelection,
    explain_fleet_support_candidate,
    recommend_fleet_support,
)
from starsector_variant_generator.analysis.scenario_advisor import (
    ScenarioCapabilityTarget,
    assess_scenario_fleet,
    user_defined_scenario,
)
from starsector_variant_generator.core.models import Hull, ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.gui.presentation import (
    format_build_why_not_comparison,
    format_fleet_support_result,
    format_fleet_support_why_not,
    format_generation_results,
    format_scenario_fleet_assessment,
)
from starsector_variant_generator.analysis.gap_recommendation import BuildWhyNotExplanation


class GuiPresentationTests(unittest.TestCase):
    def test_build_why_not_comparison_keeps_scores_and_confidence_as_backend_fields(self) -> None:
        first = BuildWhyNotExplanation("LINE_BRAWLER", "first", "TANK", True, None, (), "No viable path.", .4, 4, .6, {"functional_capability": .4})
        second = BuildWhyNotExplanation("LINE_BRAWLER", "second", "FINISHER", False, None, (), "Not resolved.")
        rendered = format_build_why_not_comparison((first, second))
        self.assertIn("first / TANK", rendered)
        self.assertIn("functional_capability=0.400", rendered)
        self.assertIn("second / FINISHER", rendered)
    def test_generation_presentation_surfaces_backend_score_and_confidence(self) -> None:
        rendered = format_generation_results([{
            "legality": "LEGAL", "recommendation_label": "Best Tank",
            "build_recommendation_score": 82.5,
            "build_archetype": {"compatibility": 0.9, "confidence": 0.8},
            "variant": {"id": "generated_test"}, "omissions": (),
        }], "MULTI_ARCHETYPE", "BALANCED")
        self.assertIn("Best Tank", rendered)
        self.assertIn("82.5", rendered)
        self.assertIn("0.8", rendered)

    def test_fleet_support_presentation_only_formats_backend_result(self) -> None:
        selected = Hull("selected", "Selected", "core", Path("selected"), hull_size="FRIGATE", flux_dissipation=100, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},), raw={"armor rating": 100, "hitpoints": 800, "max speed": 120})
        candidate = Hull("candidate", "Candidate", "core", Path("candidate"), hull_size="CRUISER", flux_dissipation=1400, weapon_mounts=tuple({"type": "BALLISTIC", "size": "LARGE"} for _ in range(6)), raw={"armor rating": 1800, "hitpoints": 14000, "max speed": 45})
        result = recommend_fleet_support((FleetSelection("selected"),), Registry.from_scan(ScanResult(hulls=[selected, candidate])), heuristic_set="baseline_0.13")
        rendered = format_fleet_support_result(result)
        self.assertIn("FLEET SUPPORT ADVISOR", rendered)
        self.assertIn("Locked: selected ×1", rendered)
        self.assertIn("Limits:", rendered)

    def test_fleet_support_why_not_presentation_only_formats_backend_record(self) -> None:
        selected = Hull("selected", "Selected", "core", Path("selected"), hull_size="FRIGATE")
        registry = Registry.from_scan(ScanResult(hulls=[selected]))
        explanation = explain_fleet_support_candidate((FleetSelection("selected"),), registry, "selected", heuristic_set="baseline_0.12")
        rendered = format_fleet_support_why_not(explanation)
        self.assertIn("FLEET SUPPORT WHY-NOT", rendered)
        self.assertIn("LOCKED_PLAYER_SELECTION", rendered)

    def test_scenario_presentation_only_formats_backend_assessment(self) -> None:
        selected = Hull("selected", "Selected", "core", Path("selected"), hull_size="FRIGATE", flux_dissipation=100, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},), raw={"armor rating": 100, "hitpoints": 800, "max speed": 120})
        scenario = user_defined_scenario("custom", "Custom", (ScenarioCapabilityTarget("ARMOR_TANKING", .8),))
        result = assess_scenario_fleet((FleetSelection("selected"),), Registry.from_scan(ScanResult(hulls=[selected])), scenario)
        rendered = format_scenario_fleet_assessment(result)
        self.assertIn("SCENARIO ADVISOR", rendered)
        self.assertIn("Mechanical alignment", rendered)
        self.assertIn("does not simulate", rendered)
