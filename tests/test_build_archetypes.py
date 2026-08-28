from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.build_archetypes import infer_build_archetypes
from starsector_variant_generator.api import run_generate
from starsector_variant_generator.core.models import Hull, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.candidate import generate_build_archetype_candidates, variant_distance


SOURCE = Path("fixture")


class BuildArchetypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hull = Hull(
            "multi", "Multi", "core", SOURCE, ordnance_points=50, flux_dissipation=500,
            weapon_mounts=(
                {"id": "A", "type": "BALLISTIC", "size": "MEDIUM", "arc": 90},
                {"id": "B", "type": "BALLISTIC", "size": "MEDIUM", "arc": 90},
                {"id": "M", "type": "MISSILE", "size": "MEDIUM", "arc": 180},
            ),
            raw={"armor rating": 900, "hitpoints": 8000, "max speed": 60, "shield type": "OMNI"},
        )
        weapons = [
            Weapon("short", "Short", "core", SOURCE, size="MEDIUM", mount_type="BALLISTIC", ordnance_points=5, range=500),
            Weapon("missile", "Missile", "core", SOURCE, size="MEDIUM", mount_type="MISSILE", ordnance_points=5, range=700),
        ]
        self.registry = Registry.from_scan(ScanResult(hulls=[self.hull], weapons=weapons))

    def test_hull_can_expose_multiple_independent_build_paths(self) -> None:
        builds = infer_build_archetypes(self.hull, self.registry)
        self.assertGreaterEqual(len(builds), 2)
        self.assertEqual(len({build.build_id for build in builds}), len(builds))
        self.assertTrue(all(0.0 <= build.compatibility <= 1.0 for build in builds))
        self.assertTrue(all(build.supporting_evidence for build in builds))

    def test_build_paths_expose_supported_and_unknown_scenario_objectives(self) -> None:
        finisher = next(build for build in infer_build_archetypes(self.hull, self.registry) if build.build_id == "FINISHER")
        objectives = {objective.objective_id: objective.support_state for objective in finisher.scenario_objectives}
        self.assertEqual("SUPPORTED", objectives["BREAKTHROUGH"])
        self.assertEqual("UNSUPPORTED", objectives["ANTI_ARMOR"])

    def test_generation_returns_labeled_build_candidates_and_distance_is_deterministic(self) -> None:
        candidates = generate_build_archetype_candidates("multi", self.registry)
        self.assertTrue(candidates)
        self.assertTrue(all(item.candidate.variant.hull_id == "multi" for item in candidates))
        self.assertTrue(all(item.build.maturity in {"VIABLE", "EXPERIMENTAL"} for item in candidates))
        self.assertEqual(0.0, variant_distance(candidates[0], candidates[0], self.registry))

    def test_default_baseline_0_4_generation_surfaces_build_labels_and_scores(self) -> None:
        outcome = run_generate(self.registry, "baseline_0.4", "multi", "guided")
        self.assertEqual("MULTI_ARCHETYPE", outcome.selected_profile)
        self.assertTrue(outcome.assessed_candidates)
        self.assertTrue(all(item["recommendation_label"].startswith("Best ") for item in outcome.assessed_candidates))
        self.assertTrue(all("build_recommendation_score" in item for item in outcome.assessed_candidates))


if __name__ == "__main__":
    unittest.main()
