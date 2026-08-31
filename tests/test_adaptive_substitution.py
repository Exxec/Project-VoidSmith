from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.analysis.adaptive_substitution import (
    rank_substitution_candidates,
    score_substitution_candidate,
)
from starsector_variant_generator.core.knowledge_packs import (
    load_knowledge_pack,
    resolve_knowledge_pack,
)
from starsector_variant_generator.core.models import Faction, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class AdaptiveSubstitutionTests(unittest.TestCase):
    def test_an_identical_weapon_scores_a_perfect_match_on_every_computable_component(self) -> None:
        target = Weapon("target", "Target", "core", SOURCE, mount_type="BALLISTIC", range=700, flux_per_shot=20, damage_type="KINETIC", ordnance_points=8)
        identical = Weapon("identical", "Identical", "core", SOURCE, mount_type="BALLISTIC", range=700, flux_per_shot=20, damage_type="KINETIC", ordnance_points=8)
        registry = Registry.from_scan(ScanResult(weapons=[target, identical]))
        score = score_substitution_candidate(target, identical, registry)
        self.assertAlmostEqual(1.0, score.component_scores["range_match"])
        self.assertAlmostEqual(1.0, score.component_scores["flux_match"])
        self.assertEqual(1.0, score.component_scores["damage_behavior_match"])
        self.assertEqual(1.0, score.component_scores["op_efficiency"])
        self.assertGreater(score.overall_score, 0.9)

    def test_a_worse_range_match_scores_lower_than_a_close_one(self) -> None:
        target = Weapon("target", "Target", "core", SOURCE, mount_type="BALLISTIC", range=1000, ordnance_points=8)
        close = Weapon("close", "Close", "core", SOURCE, mount_type="BALLISTIC", range=950, ordnance_points=8)
        far = Weapon("far", "Far", "core", SOURCE, mount_type="BALLISTIC", range=200, ordnance_points=8)
        registry = Registry.from_scan(ScanResult(weapons=[target, close, far]))
        close_score = score_substitution_candidate(target, close, registry)
        far_score = score_substitution_candidate(target, far, registry)
        self.assertGreater(close_score.overall_score, far_score.overall_score)

    def test_op_efficiency_rewards_cheaper_or_equal_never_penalizes_below_target(self) -> None:
        target = Weapon("target", "Target", "core", SOURCE, ordnance_points=10)
        cheaper = Weapon("cheaper", "Cheaper", "core", SOURCE, ordnance_points=2)
        pricier = Weapon("pricier", "Pricier", "core", SOURCE, ordnance_points=20)
        registry = Registry.from_scan(ScanResult(weapons=[target, cheaper, pricier]))
        cheaper_score = score_substitution_candidate(target, cheaper, registry)
        pricier_score = score_substitution_candidate(target, pricier, registry)
        self.assertEqual(1.0, cheaper_score.component_scores["op_efficiency"])
        self.assertLess(pricier_score.component_scores["op_efficiency"], 1.0)

    def test_affinity_component_uses_the_heuristic_preference_table(self) -> None:
        native_weapon = Weapon("native_gun", "NativeGun", "core", SOURCE)
        unaligned_weapon = Weapon("unaligned_gun", "UnalignedGun", "core", SOURCE)
        faction = Faction("hegemony", "Hegemony", "core", SOURCE, known_weapons=("native_gun",))
        target = Weapon("target", "Target", "core", SOURCE)
        registry = Registry.from_scan(ScanResult(weapons=[target, native_weapon, unaligned_weapon], factions=[faction]))
        native_score = score_substitution_candidate(target, native_weapon, registry, requesting_faction_id="hegemony")
        unaligned_score = score_substitution_candidate(target, unaligned_weapon, registry, requesting_faction_id="hegemony")
        self.assertEqual(1.00, native_score.component_scores["affinity"])
        self.assertEqual(0.70, unaligned_score.component_scores["affinity"])

    def test_missing_data_lowers_confidence_and_is_excluded_not_zeroed(self) -> None:
        target = Weapon("target", "Target", "core", SOURCE, range=700)  # no flux/damage/OP data
        candidate = Weapon("candidate", "Candidate", "core", SOURCE, range=700)
        registry = Registry.from_scan(ScanResult(weapons=[target, candidate]))
        score = score_substitution_candidate(target, candidate, registry)
        self.assertNotIn("flux_match", score.component_scores)
        self.assertNotIn("damage_behavior_match", score.component_scores)
        self.assertNotIn("op_efficiency", score.component_scores)
        self.assertLess(score.confidence, 1.0)
        self.assertIn("affinity", score.component_scores)  # always computable

    def test_rank_substitution_candidates_sorts_best_first_ties_by_id(self) -> None:
        target = Weapon("target", "Target", "core", SOURCE, range=700, ordnance_points=8)
        best = Weapon("best", "Best", "core", SOURCE, range=700, ordnance_points=8)
        worst = Weapon("worst", "Worst", "core", SOURCE, range=100, ordnance_points=8)
        registry = Registry.from_scan(ScanResult(weapons=[target, best, worst]))
        ranked = rank_substitution_candidates(target, [worst, best], registry)
        self.assertEqual(("best", "worst"), tuple(score.candidate_id for score in ranked))

    def test_stale_pack_approval_uses_approved_affinity_but_lowers_score_confidence(self) -> None:
        target = Weapon("target", "Target", "core", SOURCE, range=700, ordnance_points=8)
        foreign = Weapon("foreign", "Foreign", "other", SOURCE, range=700, ordnance_points=8)
        owner = Faction("owner", "Owner", "other", SOURCE, known_weapons=("foreign",))
        requester = Faction("f", "Faction", "core", SOURCE, source_hash="new")
        registry = Registry.from_scan(ScanResult(weapons=[target, foreign], factions=[owner, requester]))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            path.write_text(json.dumps({
                "manifest": {"schema_version": "1.0", "pack_version": "1", "target_faction_id": "f", "target_mod_id": "core", "source_hashes": {"faction:f": "old"}, "authored_date": "2026-08-23", "authorship_method": "HUMAN_AUTHORED"},
                "faction": {"traits": []},
                "approved_equipment": [{"id": "foreign", "kind": "weapons", "confidence": 0.8}],
            }), encoding="utf-8")
            pack = resolve_knowledge_pack(load_knowledge_pack(path), registry)
        without_pack = score_substitution_candidate(target, foreign, registry, "f")
        with_pack = score_substitution_candidate(target, foreign, registry, "f", knowledge_pack=pack)
        self.assertEqual(0.40, without_pack.component_scores["affinity"])
        self.assertEqual(0.90, with_pack.component_scores["affinity"])
        self.assertAlmostEqual(without_pack.confidence * 0.4, with_pack.confidence)


if __name__ == "__main__":
    unittest.main()
