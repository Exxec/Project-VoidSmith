from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Hull, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.candidate import (
    generate_conservative_candidate,
)
from starsector_variant_generator.scoring.candidate_score import score_candidate


class GoldenRegressionTests(unittest.TestCase):
    def test_baseline_0_1_candidate_and_score_are_stable(self) -> None:
        hull = Hull("gold", "Golden Hull", "core", Path("gold"), ordnance_points=10,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("gold_gun", "Golden Gun", "core", Path("gold"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        candidate = generate_conservative_candidate("gold", "LINE_ARTILLERY", registry)
        assessment = score_candidate(candidate.variant, registry, "LINE_ARTILLERY", "baseline_0.1")
        self.assertEqual({"A": "gold_gun"}, candidate.variant.weapons_by_mount)
        self.assertEqual(100.0, assessment.components["range_coherence"])
        self.assertEqual(90.0, assessment.final_score)
        self.assertEqual(("Primary range spread: 0.", "Weapon OP: 5/10."), assessment.explanation)


if __name__ == "__main__":
    unittest.main()
