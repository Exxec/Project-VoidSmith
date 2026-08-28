from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.faction_capability import analyze_faction_capability
from starsector_variant_generator.analysis.gap_recommendation import (
    CapabilityGap,
    RecommendationConstraints,
    detect_capability_gaps,
    explain_acquisition_candidate,
    explain_build_candidate,
    explain_candidate,
    explain_native_candidate,
    explain_retrofit_candidate,
    recommend_acquisition_solutions,
    recommend_gap_solutions,
    recommend_native_solutions,
    recommend_retrofit_solutions,
    _rank_build_candidates_for_role,
)
from starsector_variant_generator.core.knowledge_packs import load_knowledge_pack, resolve_knowledge_pack
import json
import tempfile
from starsector_variant_generator.core.models import Faction, Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class GapDetectionTests(unittest.TestCase):
    def test_a_role_below_the_weak_threshold_is_classified_gap(self) -> None:
        # LINE_BRAWLER = min(1, mount_count/8); 1 mount -> 0.125, below the
        # default gap_weak_threshold (0.15).
        hull = Hull("h", "Hull", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        gaps = detect_capability_gaps(profile)
        brawler_gap = next(gap for gap in gaps if gap.role == "LINE_BRAWLER")
        self.assertEqual("GAP", brawler_gap.tier)

    def test_a_role_at_or_above_the_strong_threshold_is_not_a_gap(self) -> None:
        # 8+ mounts -> LINE_BRAWLER = 1.0, well above gap_strong_threshold (0.70).
        hull = Hull("h", "Hull", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        gaps = detect_capability_gaps(profile)
        self.assertFalse(any(gap.role == "LINE_BRAWLER" for gap in gaps))

    def test_capability_vector_augmentation_is_opt_in_for_newer_heuristic_sets(self) -> None:
        # The hull's structural artillery role score is zero (no large
        # mounts), while its raw long-range mechanics supply a richer vector
        # signal. Legacy baseline_0.2 must retain the old role-only result.
        hull = Hull("h", "Hull", "core", SOURCE,
                    weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},),
                    raw={"max speed": 120, "flux dissipation": 1500})
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        legacy = next(gap for gap in detect_capability_gaps(analyze_faction_capability(faction, registry, "baseline_0.2"), "baseline_0.2") if gap.role == "LINE_ARTILLERY")
        current = next(gap for gap in detect_capability_gaps(analyze_faction_capability(faction, registry, "baseline_0.5"), "baseline_0.5") if gap.role == "LINE_ARTILLERY")
        self.assertIsNone(legacy.capability_dimension)
        self.assertEqual("LONG_RANGE_PRESSURE", current.capability_dimension)

    def test_evidence_confidence_reflects_known_hull_resolution_rate(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE)
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h", "missing_1", "missing_2", "missing_3"))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        gaps = detect_capability_gaps(profile)
        self.assertTrue(gaps)
        self.assertAlmostEqual(0.25, gaps[0].evidence_confidence)

    def test_evidence_confidence_is_zero_not_a_division_error_with_no_known_hulls(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE)
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        gaps = detect_capability_gaps(profile)
        self.assertEqual((), gaps)


class NativeRecommendationTests(unittest.TestCase):
    def test_selected_progression_stage_only_biases_existing_build_paths(self) -> None:
        hulls = [
            Hull(hull_id, hull_id, "core", SOURCE,
                 weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
                 raw={"armor rating": 1100, "hitpoints": 9000, "shield type": "OMNI", "max speed": 50})
            for hull_id in ("a", "b")
        ]
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("a", "b"))
        registry = Registry.from_scan(ScanResult(hulls=hulls, factions=[faction]))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            path.write_text(json.dumps({
                "manifest": {"schema_version": "1.0", "pack_version": "1", "target_faction_id": "f", "target_mod_id": "core", "authored_date": "2026-08-23", "authorship_method": "HUMAN_AUTHORED"},
                "faction": {"traits": []},
                "progression_tiers": [{"tier": "EARLY", "recommended_hull_ids": ["b"]}],
            }), encoding="utf-8")
            pack = resolve_knowledge_pack(load_knowledge_pack(path), registry)
        ranked = _rank_build_candidates_for_role("LINE_BRAWLER", hulls, registry, "baseline_0.7", pack, "f", campaign_stage="EARLY")
        self.assertEqual("b", ranked[0][1])
        self.assertTrue(all(build.build_id in {"TANK", "LINE_ANCHOR", "FINISHER"} for _, _, build in ranked))
        explanation = explain_build_candidate(faction, registry, "LINE_BRAWLER", "b", ranked[0][2].build_id, "baseline_0.7", pack, "EARLY")
        self.assertEqual(ranked[0][0], explanation.recommendation_score)
    def test_a_role_no_known_hull_scores_above_zero_on_is_unaddressed(self) -> None:
        # An empty-mounts hull scores 0.0 on every classify_hull axis, so
        # every resulting gap has zero candidates -- a genuine "no native
        # solution" case, not the (structurally impossible) "beat your own
        # best hull" case an earlier version of this engine mistakenly
        # required.
        bare_hull = Hull("bare", "Bare", "core", SOURCE)
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("bare",))
        registry = Registry.from_scan(ScanResult(hulls=[bare_hull], factions=[faction]))
        result = recommend_native_solutions(faction, registry)
        self.assertTrue(result.gaps)
        self.assertEqual(set(gap.role for gap in result.gaps), set(result.unaddressed_gaps))
        self.assertEqual({}, result.native_recommendations)

    def test_native_recommendations_are_ranked_by_capability_score_descending(self) -> None:
        # Mount counts kept low enough that the best (3-mount, 0.375) stays
        # below gap_adequate_threshold (0.40), so LINE_BRAWLER still
        # registers as a real (WEAK) gap worth recommending against.
        one_mount = Hull("one_mount", "One", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        two_mount = Hull("two_mount", "Two", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2)))
        three_mount = Hull("three_mount", "Three", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(3)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("one_mount", "two_mount", "three_mount"))
        registry = Registry.from_scan(ScanResult(hulls=[one_mount, two_mount, three_mount], factions=[faction]))
        result = recommend_native_solutions(faction, registry)
        recommendations = result.native_recommendations["LINE_BRAWLER"]
        self.assertEqual(("three_mount", "two_mount", "one_mount"), tuple(r.hull_id for r in recommendations))
        self.assertEqual((1, 2, 3), tuple(r.rank for r in recommendations))
        self.assertAlmostEqual(0.375, recommendations[0].capability_score)
        self.assertEqual(1.0, recommendations[0].confidence)
        self.assertAlmostEqual(0.375, recommendations[0].recommendation_score)

    def test_ties_break_by_hull_id(self) -> None:
        tied_b = Hull("tied_b", "TiedB", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2)))
        tied_a = Hull("tied_a", "TiedA", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("tied_b", "tied_a"))
        registry = Registry.from_scan(ScanResult(hulls=[tied_b, tied_a], factions=[faction]))
        result = recommend_native_solutions(faction, registry)
        recommendations = result.native_recommendations["LINE_BRAWLER"]
        self.assertEqual(("tied_a", "tied_b"), tuple(r.hull_id for r in recommendations))

    def test_recommendation_count_is_capped_by_the_heuristic(self) -> None:
        hulls = []
        hull_ids = []
        for index in range(5):
            hull_id = f"mild_{index}"
            hulls.append(Hull(hull_id, hull_id, "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2))))
            hull_ids.append(hull_id)
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=tuple(hull_ids))
        registry = Registry.from_scan(ScanResult(hulls=hulls, factions=[faction]))
        result = recommend_native_solutions(faction, registry)
        self.assertEqual(3, len(result.native_recommendations["LINE_BRAWLER"]))

    def test_baseline_0_3_records_archetype_evidence_and_diversity_decisions(self) -> None:
        hulls = [
            Hull("a", "A", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(3))),
            Hull("b", "B", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2))),
            Hull("c", "C", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},)),
        ]
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("a", "b", "c"))
        registry = Registry.from_scan(ScanResult(hulls=hulls, factions=[faction]))
        result = recommend_native_solutions(faction, registry, "baseline_0.3")
        recommendation = result.native_recommendations["LINE_BRAWLER"][0]
        self.assertIn("LINE_SHIP", recommendation.archetype_scores)
        self.assertTrue(recommendation.archetype_evidence["LINE_SHIP"])
        self.assertEqual("Highest recommendation score.", recommendation.diversity_reason)
        explanation = explain_native_candidate(faction, registry, "LINE_BRAWLER", "a", "baseline_0.3")
        self.assertTrue(explanation.recommended)
        self.assertIn("LINE_SHIP", explanation.archetype_scores)

    def test_baseline_0_4_recommendation_identifies_a_hull_build_path(self) -> None:
        hull = Hull(
            "anchor", "Anchor", "core", SOURCE,
            weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
            raw={"armor rating": 1100, "hitpoints": 9000, "shield type": "OMNI", "max speed": 50},
        )
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("anchor",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        result = recommend_native_solutions(faction, registry, "baseline_0.4")
        recommendation = result.native_recommendations["LINE_BRAWLER"][0]
        self.assertIsNotNone(recommendation.build_archetype_id)
        self.assertIn(recommendation.build_maturity, {"VIABLE", "EXPERIMENTAL"})

    def test_baseline_0_4_can_surface_distinct_builds_for_one_hull(self) -> None:
        hull = Hull(
            "multi", "Multi", "core", SOURCE,
            weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
            raw={"armor rating": 1200, "hitpoints": 10000, "shield type": "OMNI", "max speed": 65},
        )
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("multi",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        recommendations = recommend_native_solutions(faction, registry, "baseline_0.4").native_recommendations["LINE_BRAWLER"]
        self.assertGreaterEqual(len(recommendations), 2)
        self.assertEqual("multi", recommendations[0].hull_id)
        self.assertGreaterEqual(len({item.build_archetype_id for item in recommendations}), 2)

    def test_newer_build_recommendation_confidence_preserves_missing_mechanics_uncertainty(self) -> None:
        hull = Hull("partial", "Partial", "core", SOURCE,
                    weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(3)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("partial",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        recommendation = recommend_native_solutions(faction, registry, "baseline_0.5").native_recommendations["LINE_BRAWLER"][0]
        self.assertLess(recommendation.confidence, 1.0)
        self.assertIsNotNone(recommendation.build_confidence)

    def test_build_aware_capability_score_is_the_raw_structural_score_not_the_build_composite(self) -> None:
        """Regression: found live against the real 148-mod install (via
        `svg recommend`), `NativeRecommendation.capability_score` in the
        build-aware path (`baseline_0.5`+, including the CLI's real default
        `baseline_0.7`) was being set to `capability * build.compatibility *
        bias` -- the same composite already stored separately in
        `recommendation_score` -- instead of this hull's own raw
        `classify_hull(...).role_compatibility[role]`, as GAP_RECOMMENDATION_
        ENGINE.md section 6 documents and as `RetrofitRecommendation`/
        `AcquisitionRecommendation` (and `explain_native_candidate`'s own,
        independent computation for the identical hull/role) already do
        correctly. That made `svg recommend`'s native leg disagree with
        `svg why-not`'s reported `capability_score` for the exact same
        (faction, role, hull), and silently double-counted build
        compatibility inside `explain_build_candidate`'s
        `leg_components["NATIVE"]["functional_capability"]`.
        """
        hull = Hull(
            "anchor", "Anchor", "core", SOURCE,
            weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
            raw={"armor rating": 1100, "hitpoints": 9000, "shield type": "OMNI", "max speed": 50},
        )
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("anchor",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        recommendation = recommend_native_solutions(faction, registry, "baseline_0.7").native_recommendations["LINE_BRAWLER"][0]
        # 3 mounts -> LINE_BRAWLER capability_score = 3/8 = 0.375 (structural,
        # unaffected by build fit -- see the identical comment elsewhere in
        # this file for the same formula).
        self.assertAlmostEqual(0.375, recommendation.capability_score)
        self.assertIsNotNone(recommendation.build_compatibility)
        # The build-weighted ranking score must still differ from the raw
        # structural score whenever build_compatibility isn't a perfect 1.0
        # -- otherwise this regression test would not actually distinguish
        # the fixed field from the bug.
        self.assertLess(recommendation.recommendation_score, recommendation.capability_score)
        self.assertAlmostEqual(recommendation.capability_score * recommendation.build_compatibility, recommendation.recommendation_score, places=6)
        # Must agree with Why-Not's own, independently-computed capability_score
        # for the identical (faction, role, hull) -- the whole point of the bug
        # was that these two real commands disagreed about the same fact.
        explanation = explain_native_candidate(faction, registry, "LINE_BRAWLER", "anchor", "baseline_0.7")
        self.assertAlmostEqual(explanation.capability_score, recommendation.capability_score)

    def test_a_faction_with_no_gaps_has_no_recommendations_or_unaddressed_gaps(self) -> None:
        # A mount can be both size LARGE and type MISSILE at once, so 8 such
        # mounts plus a launch bay push all 5 classify_hull axes to 1.0:
        # LINE_BRAWLER (mount count), MISSILE_SUPPORT and LINE_ARTILLERY
        # (missile_fraction and large_fraction both 1.0 on the same mounts),
        # CARRIER and BATTLE_CARRIER (launch_bay_slots evidence).
        strong = Hull("strong", "Strong", "core", SOURCE,
                      weapon_mounts=tuple({"type": "MISSILE", "size": "LARGE"} for _ in range(8)),
                      launch_bay_slots=("BAY",))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("strong",))
        registry = Registry.from_scan(ScanResult(hulls=[strong], factions=[faction]))
        result = recommend_native_solutions(faction, registry)
        self.assertEqual((), result.gaps)
        self.assertEqual({}, result.native_recommendations)
        self.assertEqual((), result.unaddressed_gaps)


class RetrofitRecommendationTests(unittest.TestCase):
    def test_retrofit_finds_the_real_variant_most_improvable_toward_the_mapped_profile(self) -> None:
        # 3 mounts -> LINE_BRAWLER capability_score = 3/8 = 0.375 (WEAK gap,
        # structural, unaffected by refit). Only mount A is actually
        # fitted in the real variant, so role_match's "all weapons" check
        # only ever considers that one weapon -- isolates the retrofit
        # search to a single, deterministic swap.
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20,
                    weapon_mounts=tuple({"id": mount_id, "type": "BALLISTIC", "size": "SMALL"} for mount_id in ("A", "B", "C")))
        long_ranged = Weapon("long_ranged", "Long", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        short_ranged = Weapon("short_ranged", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        variant = Variant("h_Standard", "Standard", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "long_ranged"})
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[long_ranged, short_ranged], variants=[variant], factions=[faction]))
        native = recommend_native_solutions(faction, registry)
        brawler_gap = next(gap for gap in native.gaps if gap.role == "LINE_BRAWLER")
        retrofits = recommend_retrofit_solutions(faction, registry, (brawler_gap,))
        recs = retrofits["LINE_BRAWLER"]
        self.assertEqual(1, len(recs))
        self.assertEqual("h", recs[0].hull_id)
        self.assertEqual("h_Standard", recs[0].variant_id)
        self.assertAlmostEqual(0.375, recs[0].capability_score)
        self.assertEqual(70.0, recs[0].role_match_before)
        self.assertEqual(100.0, recs[0].role_match_after)
        self.assertEqual(1, recs[0].changes)
        self.assertEqual(1, recs[0].rank)
        self.assertEqual(1.0, recs[0].confidence)
        self.assertEqual(100.0, recs[0].recommendation_score)

    def test_a_hull_with_no_real_variant_yields_no_retrofit_recommendation(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20,
                    weapon_mounts=tuple({"id": mount_id, "type": "BALLISTIC", "size": "SMALL"} for mount_id in ("A", "B", "C")))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        native = recommend_native_solutions(faction, registry)
        brawler_gap = next(gap for gap in native.gaps if gap.role == "LINE_BRAWLER")
        retrofits = recommend_retrofit_solutions(faction, registry, (brawler_gap,))
        self.assertEqual((), retrofits.get("LINE_BRAWLER", ()))

    def test_an_already_well_fit_variant_is_not_recommended_for_retrofit(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20,
                    weapon_mounts=tuple({"id": mount_id, "type": "BALLISTIC", "size": "SMALL"} for mount_id in ("A", "B", "C")))
        short_ranged = Weapon("short_ranged", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        variant = Variant("h_Standard", "Standard", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "short_ranged"})
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[short_ranged], variants=[variant], factions=[faction]))
        native = recommend_native_solutions(faction, registry)
        brawler_gap = next(gap for gap in native.gaps if gap.role == "LINE_BRAWLER")
        retrofits = recommend_retrofit_solutions(faction, registry, (brawler_gap,))
        self.assertEqual((), retrofits.get("LINE_BRAWLER", ()))


class AcquisitionRecommendationTests(unittest.TestCase):
    def test_constraint_excludes_foreign_acquisition_hulls(self) -> None:
        own = Hull("own", "Own", "core", SOURCE)
        foreign = Hull("foreign", "Foreign", "other", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(3)))
        requester = Faction("f", "Faction", "core", SOURCE, known_hulls=("own",))
        owner = Faction("other", "Other", "other", SOURCE, known_hulls=("foreign",))
        registry = Registry.from_scan(ScanResult(hulls=[own, foreign], factions=[requester, owner]))
        gap = CapabilityGap("LINE_BRAWLER", "GAP", 0.0, 1.0)
        recs = recommend_acquisition_solutions(requester, registry, (gap,), "baseline_0.5", constraints=RecommendationConstraints(allow_foreign_hulls=False))
        self.assertEqual((), recs["LINE_BRAWLER"])

    def test_a_foreign_hull_with_real_capability_is_recommended_for_acquisition(self) -> None:
        weak_own = Hull("weak_own", "WeakOwn", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        strong_foreign = Hull("strong_foreign", "StrongForeign", "core", SOURCE,
                               weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        requester = Faction("f", "Faction", "core", SOURCE, known_hulls=("weak_own",))
        owner = Faction("other", "Other", "core", SOURCE, known_hulls=("strong_foreign",))
        registry = Registry.from_scan(ScanResult(hulls=[weak_own, strong_foreign], factions=[requester, owner]))
        native = recommend_native_solutions(requester, registry)
        brawler_gap = next(gap for gap in native.gaps if gap.role == "LINE_BRAWLER")
        acquisitions = recommend_acquisition_solutions(requester, registry, (brawler_gap,))
        recs = acquisitions["LINE_BRAWLER"]
        self.assertEqual(1, len(recs))
        self.assertEqual("strong_foreign", recs[0].hull_id)
        self.assertEqual("FOREIGN", recs[0].affinity)
        self.assertEqual(("other",), recs[0].owning_faction_ids)
        self.assertEqual(0.40, recs[0].preference_weight)  # baseline_0.2 affinity_preference_foreign
        self.assertEqual(1.0, recs[0].confidence)
        self.assertAlmostEqual(0.875, recs[0].incremental_capability_gain)

    def test_a_hull_the_faction_already_knows_is_excluded_from_acquisition(self) -> None:
        own_strong = Hull("own_strong", "OwnStrong", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("own_strong",))
        registry = Registry.from_scan(ScanResult(hulls=[own_strong], factions=[faction]))
        gap = CapabilityGap("LINE_BRAWLER", "GAP", 0.0, 1.0)
        acquisitions = recommend_acquisition_solutions(faction, registry, (gap,))
        self.assertEqual((), acquisitions.get("LINE_BRAWLER", ()))

    def test_baseline_0_4_acquisition_ranks_distinct_builds_of_one_hull(self) -> None:
        own = Hull("own", "Own", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        foreign = Hull(
            "foreign", "Foreign", "other_mod", SOURCE,
            weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
            raw={"armor rating": 1200, "hitpoints": 10000, "shield type": "OMNI", "max speed": 65},
        )
        requester = Faction("f", "Faction", "core", SOURCE, known_hulls=("own",))
        owner = Faction("other", "Other", "other_mod", SOURCE, known_hulls=("foreign",))
        registry = Registry.from_scan(ScanResult(hulls=[own, foreign], factions=[requester, owner]))
        recs = recommend_acquisition_solutions(requester, registry, (CapabilityGap("LINE_BRAWLER", "GAP", 0.0, 1.0),), "baseline_0.4")["LINE_BRAWLER"]
        self.assertGreaterEqual(len(recs), 2)
        self.assertEqual({"foreign"}, {rec.hull_id for rec in recs})
        self.assertGreaterEqual(len({rec.build_archetype_id for rec in recs}), 2)


class GapSolutionsIntegrationTests(unittest.TestCase):
    def test_fully_unaddressed_gaps_excludes_a_gap_covered_by_acquisition_only(self) -> None:
        bare_own = Hull("bare_own", "BareOwn", "core", SOURCE)  # 0 mounts -> LINE_BRAWLER = 0.0
        strong_foreign = Hull("strong_foreign", "StrongForeign", "core", SOURCE,
                               weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        requester = Faction("f", "Faction", "core", SOURCE, known_hulls=("bare_own",))
        owner = Faction("other", "Other", "core", SOURCE, known_hulls=("strong_foreign",))
        registry = Registry.from_scan(ScanResult(hulls=[bare_own, strong_foreign], factions=[requester, owner]))
        result = recommend_gap_solutions(requester, registry)
        self.assertIn("LINE_BRAWLER", result.unaddressed_gaps)
        self.assertNotIn("LINE_BRAWLER", result.fully_unaddressed_gaps)
        self.assertTrue(result.acquisition_recommendations["LINE_BRAWLER"])

    def test_a_gap_with_no_solution_anywhere_is_fully_unaddressed(self) -> None:
        bare = Hull("bare", "Bare", "core", SOURCE)
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("bare",))
        registry = Registry.from_scan(ScanResult(hulls=[bare], factions=[faction]))
        result = recommend_gap_solutions(faction, registry)
        self.assertTrue(result.gaps)
        self.assertEqual(set(gap.role for gap in result.gaps), set(result.fully_unaddressed_gaps))


class BuildAwareWhyNotConsistencyTests(unittest.TestCase):
    def test_build_aware_why_not_agrees_with_the_real_native_recommendation_for_every_known_hull(self) -> None:
        """Regression: found live against the real 148-mod install, `svg
        why-not <faction> <role> <hull>` (no `--build-archetype`) used the
        legacy hull-only ranking/diversity pair unconditionally, even under
        build-aware heuristic sets (`baseline_0.4`+, including the CLI's
        real default `baseline_0.7`) where `recommend_native_solutions`
        itself ranks `Hull + BuildArchetype` combinations and always
        applies similarity-based diversity selection -- letting the two
        real commands disagree about whether the same hull was
        recommended (confirmed live: `xlu` / `MISSILE_SUPPORT` /
        `xlu_chrominus`). This asserts full agreement, hull by hull, for a
        small multi-hull fixture with real structural variety."""
        # LINE_BRAWLER = min(1, mount_count/8); every hull kept at <=3 mounts
        # (best = 3/8 = 0.375) so the best known hull stays a real WEAK gap
        # (below gap_adequate_threshold=0.40), not ADEQUATE/no-gap -- while
        # every hull still scores > 0.0, so all five are real ranked
        # candidates the build-aware leg (and its diversity selection) has
        # to choose among.
        hulls = [
            Hull("brawler_a", "Brawler A", "core", SOURCE,
                 weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
                 raw={"armor rating": 1100, "hitpoints": 9000, "shield type": "OMNI", "max speed": 50}),
            Hull("brawler_b", "Brawler B", "core", SOURCE,
                 weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
                 raw={"armor rating": 1400, "hitpoints": 11000, "shield type": "OMNI", "max speed": 45}),
            Hull("brawler_c", "Brawler C", "core", SOURCE,
                 weapon_mounts=tuple({"type": "ENERGY", "size": "SMALL"} for _ in range(2)),
                 raw={"armor rating": 300, "hitpoints": 3000, "shield type": "FRONT", "max speed": 130}),
            Hull("brawler_d", "Brawler D", "core", SOURCE,
                 weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2)),
                 raw={"armor rating": 500, "hitpoints": 4000, "shield type": "FRONT", "max speed": 90}),
            Hull("brawler_e", "Brawler E", "core", SOURCE,
                 weapon_mounts=tuple({"type": "ENERGY", "size": "MEDIUM"} for _ in range(3)),
                 raw={"armor rating": 900, "hitpoints": 7000, "shield type": "OMNI", "max speed": 60}),
        ]
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=tuple(h.id for h in hulls))
        registry = Registry.from_scan(ScanResult(hulls=hulls, factions=[faction]))
        result = recommend_native_solutions(faction, registry, "baseline_0.7")
        recommended_ids = {rec.hull_id for rec in result.native_recommendations.get("LINE_BRAWLER", ())}
        self.assertTrue(recommended_ids)
        self.assertLess(len(recommended_ids), len(hulls))  # fixture must exercise a real "not recommended" case too
        for hull in hulls:
            explanation = explain_native_candidate(faction, registry, "LINE_BRAWLER", hull.id, "baseline_0.7")
            self.assertEqual(
                hull.id in recommended_ids, explanation.recommended,
                f"{hull.id}: why-not ({explanation.recommended}) disagreed with the real "
                f"recommend_native_solutions result ({hull.id in recommended_ids})",
            )
            if explanation.recommended:
                # ROADMAP.md Phase 32: not just "agrees on recommended or
                # not" (Phase 11's own bar) but the exact cited score and
                # diversity-selection reason are the SAME real values the
                # ranking function produced for this candidate -- both now
                # read the same RecommendationAudit trail rather than each
                # computing its own.
                own = next(rec for rec in result.native_recommendations["LINE_BRAWLER"] if rec.hull_id == hull.id)
                self.assertEqual(own.capability_score, explanation.capability_score)
                self.assertEqual(own.diversity_reason, explanation.diversity_reason)
                # Confidence is computed separately from score (see
                # RecommendationAudit's own docstring); prove it is also
                # cited identically, not just score/diversity.
                self.assertIsNotNone(explanation.confidence)
                self.assertEqual(own.confidence, explanation.confidence)


def _five_brawler_hulls() -> list[Hull]:
    """Shared structurally-varied fixture (mirrors
    `BuildAwareWhyNotConsistencyTests`'s own): 5 hulls, each scoring > 0.0
    on LINE_BRAWLER but capped low enough (<=3 mounts) to stay a real WEAK
    gap, with enough real structural variety that build-aware ranking and
    diversity selection materially reorder/exclude candidates -- the same
    shape that exposed SVG-018 (docs/BUGS.md) for the retrofit/acquisition
    legs."""
    return [
        Hull("brawler_a", "Brawler A", "core", SOURCE, ordnance_points=20,
             weapon_mounts=tuple({"id": f"A{i}", "type": "BALLISTIC", "size": "MEDIUM"} for i in range(3)),
             raw={"armor rating": 1100, "hitpoints": 9000, "shield type": "OMNI", "max speed": 50}),
        Hull("brawler_b", "Brawler B", "core", SOURCE, ordnance_points=20,
             weapon_mounts=tuple({"id": f"B{i}", "type": "BALLISTIC", "size": "MEDIUM"} for i in range(3)),
             raw={"armor rating": 1400, "hitpoints": 11000, "shield type": "OMNI", "max speed": 45}),
        Hull("brawler_c", "Brawler C", "core", SOURCE, ordnance_points=20,
             weapon_mounts=tuple({"id": f"C{i}", "type": "ENERGY", "size": "SMALL"} for i in range(2)),
             raw={"armor rating": 300, "hitpoints": 3000, "shield type": "FRONT", "max speed": 130}),
        Hull("brawler_d", "Brawler D", "core", SOURCE, ordnance_points=20,
             weapon_mounts=tuple({"id": f"D{i}", "type": "BALLISTIC", "size": "SMALL"} for i in range(2)),
             raw={"armor rating": 500, "hitpoints": 4000, "shield type": "FRONT", "max speed": 90}),
        Hull("brawler_e", "Brawler E", "core", SOURCE, ordnance_points=20,
             weapon_mounts=tuple({"id": f"E{i}", "type": "ENERGY", "size": "MEDIUM"} for i in range(3)),
             raw={"armor rating": 900, "hitpoints": 7000, "shield type": "OMNI", "max speed": 60}),
    ]


class RetrofitAuditConsistencyTests(unittest.TestCase):
    """ROADMAP.md Phase 32 / SVG-018 (docs/BUGS.md): before this phase,
    `explain_retrofit_candidate` always used the legacy hull-only,
    native-top-N-truncated candidate pool regardless of heuristic set,
    disagreeing -- confirmed live via a synthetic reproduction fixture --
    with the real `recommend_retrofit_solutions` build-aware search under
    `baseline_0.4`+ (including the CLI's real default `baseline_0.7`).
    Both now read the same `_retrofit_audit_trail`.
    """

    def _registry_with_retrofit_opportunities(self):
        hulls = _five_brawler_hulls()
        long_ranged = Weapon("long_ranged", "Long", "core", SOURCE, size="MEDIUM", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        long_e = Weapon("long_e", "LongE", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=5, range=1000)
        short_e = Weapon("short_e", "ShortE", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=5, range=500)
        long_e_m = Weapon("long_e_m", "LongEM", "core", SOURCE, size="MEDIUM", mount_type="ENERGY", ordnance_points=5, range=1000)
        variants = [
            Variant("brawler_a_Standard", "Standard", "core", SOURCE, hull_id="brawler_a", weapons_by_mount={"A0": "long_ranged"}),
            Variant("brawler_b_Standard", "Standard", "core", SOURCE, hull_id="brawler_b", weapons_by_mount={"B0": "long_ranged"}),
            Variant("brawler_c_Standard", "Standard", "core", SOURCE, hull_id="brawler_c", weapons_by_mount={"C0": "long_e"}),
            Variant("brawler_d_Standard", "Standard", "core", SOURCE, hull_id="brawler_d", weapons_by_mount={"D0": "short_e"}),
            Variant("brawler_e_Standard", "Standard", "core", SOURCE, hull_id="brawler_e", weapons_by_mount={"E0": "long_e_m"}),
        ]
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=tuple(h.id for h in hulls))
        registry = Registry.from_scan(ScanResult(
            hulls=hulls, weapons=[long_ranged, long_e, short_e, long_e_m], variants=variants, factions=[faction],
        ))
        return faction, registry, hulls

    def test_build_aware_retrofit_why_not_agrees_with_the_real_recommendation_for_every_hull(self) -> None:
        faction, registry, hulls = self._registry_with_retrofit_opportunities()
        native = recommend_native_solutions(faction, registry, "baseline_0.7")
        brawler_gap = next(gap for gap in native.gaps if gap.role == "LINE_BRAWLER")
        retrofits = recommend_retrofit_solutions(faction, registry, (brawler_gap,), "baseline_0.7")
        recommended_ids = {rec.hull_id for rec in retrofits.get("LINE_BRAWLER", ())}
        self.assertTrue(recommended_ids)
        self.assertLess(len(recommended_ids), len(hulls))  # exercise a real "not recommended" case too
        for hull in hulls:
            explanation = explain_retrofit_candidate(faction, registry, "LINE_BRAWLER", hull.id, "baseline_0.7")
            self.assertEqual(
                hull.id in recommended_ids, explanation.recommended,
                f"{hull.id}: retrofit why-not ({explanation.recommended}) disagreed with the real "
                f"recommend_retrofit_solutions result ({hull.id in recommended_ids})",
            )
            if explanation.recommended:
                own = next(rec for rec in retrofits["LINE_BRAWLER"] if rec.hull_id == hull.id)
                # Not just "both say recommended" -- the exact real score,
                # confidence, and role_match components the ranking
                # function produced are IDENTICAL to what Why-Not cites,
                # because both read the same RecommendationAudit entry.
                self.assertEqual(own.recommendation_score, explanation.recommendation_score)
                self.assertEqual(own.role_match_before, explanation.role_match_before)
                self.assertEqual(own.role_match_after, explanation.role_match_after)
                self.assertEqual(own.quality_gain, explanation.quality_gain)
                self.assertEqual(own.variant_id, explanation.variant_id)
                self.assertIsNotNone(explanation.confidence)
                self.assertEqual(own.confidence, explanation.confidence)


class AcquisitionAuditConsistencyTests(unittest.TestCase):
    """ROADMAP.md Phase 32 / SVG-018 (docs/BUGS.md): before this phase,
    `explain_acquisition_candidate` always used a hull-only,
    non-build-aware ranking regardless of heuristic set, disagreeing --
    confirmed live via a synthetic reproduction fixture -- with the real
    `recommend_acquisition_solutions` build-aware search under
    `baseline_0.4`+ (including the CLI's real default `baseline_0.7`).
    Both now read the same `_acquisition_audit_trail`.
    """

    def test_build_aware_acquisition_why_not_agrees_with_the_real_recommendation_for_every_hull(self) -> None:
        foreign_hulls = [
            Hull("acq_a", "AcqA", "othermod", SOURCE, ordnance_points=20,
                 weapon_mounts=tuple({"id": f"AA{i}", "type": "BALLISTIC", "size": "MEDIUM"} for i in range(3)),
                 raw={"armor rating": 1100, "hitpoints": 9000, "shield type": "OMNI", "max speed": 50}),
            Hull("acq_b", "AcqB", "othermod", SOURCE, ordnance_points=20,
                 weapon_mounts=tuple({"id": f"AB{i}", "type": "BALLISTIC", "size": "MEDIUM"} for i in range(3)),
                 raw={"armor rating": 1400, "hitpoints": 11000, "shield type": "OMNI", "max speed": 45}),
            Hull("acq_c", "AcqC", "othermod", SOURCE, ordnance_points=20,
                 weapon_mounts=tuple({"id": f"AC{i}", "type": "ENERGY", "size": "SMALL"} for i in range(2)),
                 raw={"armor rating": 300, "hitpoints": 3000, "shield type": "FRONT", "max speed": 130}),
            Hull("acq_d", "AcqD", "othermod", SOURCE, ordnance_points=20,
                 weapon_mounts=tuple({"id": f"AD{i}", "type": "BALLISTIC", "size": "SMALL"} for i in range(2)),
                 raw={"armor rating": 500, "hitpoints": 4000, "shield type": "FRONT", "max speed": 90}),
            Hull("acq_e", "AcqE", "othermod", SOURCE, ordnance_points=20,
                 weapon_mounts=tuple({"id": f"AE{i}", "type": "ENERGY", "size": "MEDIUM"} for i in range(3)),
                 raw={"armor rating": 900, "hitpoints": 7000, "shield type": "OMNI", "max speed": 60}),
        ]
        own = Hull("own_weak", "OwnWeak", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        requester = Faction("f2", "Faction2", "core", SOURCE, known_hulls=("own_weak",))
        owner = Faction("other2", "Other2", "othermod", SOURCE, known_hulls=tuple(h.id for h in foreign_hulls))
        registry = Registry.from_scan(ScanResult(hulls=[own] + foreign_hulls, factions=[requester, owner]))
        # A real gap derived from the actual pipeline (not a hand-built
        # CapabilityGap): ROADMAP.md Phase 32's confidence-identity check
        # below only means something if this leg is fed the exact same real
        # gap `explain_acquisition_candidate` independently recomputes via
        # `_capability_gap_confidence_inputs` -- a synthetic gap with an
        # invented `evidence_confidence` would diverge from both by
        # construction, not expose a real bug.
        profile = analyze_faction_capability(requester, registry, "baseline_0.7")
        gap = next(g for g in detect_capability_gaps(profile, "baseline_0.7") if g.role == "LINE_BRAWLER")
        acquisitions = recommend_acquisition_solutions(requester, registry, (gap,), "baseline_0.7")
        recommended_ids = {rec.hull_id for rec in acquisitions.get("LINE_BRAWLER", ())}
        self.assertTrue(recommended_ids)
        self.assertLess(len(recommended_ids), len(foreign_hulls))  # exercise a real "not recommended" case too
        for hull in foreign_hulls:
            explanation = explain_acquisition_candidate(requester, registry, "LINE_BRAWLER", hull.id, "baseline_0.7")
            self.assertEqual(
                hull.id in recommended_ids, explanation.recommended,
                f"{hull.id}: acquisition why-not ({explanation.recommended}) disagreed with the real "
                f"recommend_acquisition_solutions result ({hull.id in recommended_ids})",
            )
            if explanation.recommended:
                own_rec = next(rec for rec in acquisitions["LINE_BRAWLER"] if rec.hull_id == hull.id)
                self.assertEqual(own_rec.recommendation_score, explanation.recommendation_score)
                self.assertEqual(own_rec.affinity, explanation.affinity)
                self.assertEqual(own_rec.preference_weight, explanation.preference_weight)
                self.assertIsNotNone(explanation.confidence)
                self.assertEqual(own_rec.confidence, explanation.confidence)


class WhyNotExplanationTests(unittest.TestCase):
    def test_build_specific_why_not_distinguishes_a_build_path(self) -> None:
        hull = Hull(
            "multi", "Multi", "core", SOURCE,
            weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
            raw={"armor rating": 1200, "hitpoints": 10000, "shield type": "OMNI", "max speed": 65},
        )
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("multi",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        explanation = explain_build_candidate(faction, registry, "LINE_BRAWLER", "multi", "TANK", "baseline_0.4")
        self.assertTrue(explanation.resolved)
        self.assertEqual("TANK", explanation.build_archetype_id)
        self.assertIsNotNone(explanation.build)
        self.assertIsNotNone(explanation.recommendation_score)
        self.assertIn("functional_capability", explanation.scoring_components)
        self.assertIn("build_compatibility", explanation.scoring_components)
        self.assertIn("NATIVE", explanation.leg_scoring_components)
        self.assertIn("recommendation_score", explanation.leg_scoring_components["NATIVE"])

    def test_a_hull_that_was_recommended_is_explained_as_recommended(self) -> None:
        best = Hull("best", "Best", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("best",))
        registry = Registry.from_scan(ScanResult(hulls=[best], factions=[faction]))
        explanation = explain_native_candidate(faction, registry, "LINE_BRAWLER", "best")
        self.assertTrue(explanation.resolved)
        self.assertTrue(explanation.recommended)
        self.assertEqual(1, explanation.rank)
        self.assertAlmostEqual(1.0, explanation.capability_score)

    def test_a_hull_ranked_below_the_recommendation_count_explains_the_gap_to_the_cutoff(self) -> None:
        hulls = [Hull("weak", "Weak", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))]
        hull_ids = ["weak"]
        for index in range(4):
            hull_id = f"mild_{index}"
            hulls.append(Hull(hull_id, hull_id, "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2))))
            hull_ids.append(hull_id)
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=tuple(hull_ids))
        registry = Registry.from_scan(ScanResult(hulls=hulls, factions=[faction]))
        # 5 known hulls, gap_recommendation_count defaults to 3, "weak" (lowest score) should rank last and be unrecommended.
        explanation = explain_native_candidate(faction, registry, "LINE_BRAWLER", "weak")
        self.assertTrue(explanation.resolved)
        self.assertFalse(explanation.recommended)
        self.assertEqual(5, explanation.rank)
        self.assertEqual(5, explanation.total_candidates)
        self.assertIn("below the lowest-scoring hull that was recommended", explanation.reason)

    def test_a_hull_scoring_zero_is_explained_distinctly_from_a_low_ranked_hull(self) -> None:
        zero_scoring = Hull("zero", "Zero", "core", SOURCE)  # no mounts, no bays -> every axis 0.0
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("zero",))
        registry = Registry.from_scan(ScanResult(hulls=[zero_scoring], factions=[faction]))
        explanation = explain_native_candidate(faction, registry, "LINE_BRAWLER", "zero")
        self.assertTrue(explanation.resolved)
        self.assertIsNone(explanation.rank)
        self.assertEqual(0.0, explanation.capability_score)
        self.assertIn("no real evidence", explanation.reason)

    def test_an_unresolved_hull_id_is_explained_distinctly_not_treated_as_zero_scoring(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=())
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        explanation = explain_native_candidate(faction, registry, "LINE_BRAWLER", "not_a_real_hull")
        self.assertFalse(explanation.resolved)
        self.assertIsNone(explanation.capability_score)


class RetrofitWhyNotExplanationTests(unittest.TestCase):
    def test_a_genuinely_improvable_hull_is_explained_as_recommended(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20,
                    weapon_mounts=tuple({"id": mount_id, "type": "BALLISTIC", "size": "SMALL"} for mount_id in ("A", "B", "C")))
        long_ranged = Weapon("long_ranged", "Long", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        short_ranged = Weapon("short_ranged", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        variant = Variant("h_Standard", "Standard", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "long_ranged"})
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[long_ranged, short_ranged], variants=[variant], factions=[faction]))
        explanation = explain_retrofit_candidate(faction, registry, "LINE_BRAWLER", "h")
        self.assertTrue(explanation.considered)
        self.assertTrue(explanation.has_real_variant)
        self.assertIsNotNone(explanation.recommendation_score)
        self.assertIn("quality_gain", explanation.scoring_components)
        self.assertEqual("h_Standard", explanation.variant_id)
        self.assertEqual(70.0, explanation.role_match_before)
        self.assertEqual(100.0, explanation.role_match_after)
        self.assertTrue(explanation.recommended)
        self.assertIn("Recommended", explanation.reason)

    def test_a_hull_outside_the_native_shortlist_is_not_considered(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE)  # 0 mounts -> 0.0 capability, never a positive-scoring native candidate
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        explanation = explain_retrofit_candidate(faction, registry, "LINE_BRAWLER", "h")
        self.assertFalse(explanation.considered)
        self.assertIsNone(explanation.has_real_variant)
        self.assertFalse(explanation.recommended)

    def test_a_considered_hull_with_no_real_variant_is_explained_distinctly(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20,
                    weapon_mounts=tuple({"id": mount_id, "type": "BALLISTIC", "size": "SMALL"} for mount_id in ("A", "B", "C")))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        explanation = explain_retrofit_candidate(faction, registry, "LINE_BRAWLER", "h")
        self.assertTrue(explanation.considered)
        self.assertFalse(explanation.has_real_variant)
        self.assertIn("no real, indexed variant", explanation.reason)


class AcquisitionWhyNotExplanationTests(unittest.TestCase):
    def test_a_real_foreign_candidate_is_explained_as_recommended(self) -> None:
        weak_own = Hull("weak_own", "WeakOwn", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        strong_foreign = Hull("strong_foreign", "StrongForeign", "core", SOURCE,
                               weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        requester = Faction("f", "Faction", "core", SOURCE, known_hulls=("weak_own",))
        owner = Faction("other", "Other", "core", SOURCE, known_hulls=("strong_foreign",))
        registry = Registry.from_scan(ScanResult(hulls=[weak_own, strong_foreign], factions=[requester, owner]))
        explanation = explain_acquisition_candidate(requester, registry, "LINE_BRAWLER", "strong_foreign")
        self.assertTrue(explanation.resolved)
        self.assertFalse(explanation.is_native)
        self.assertAlmostEqual(0.4, explanation.preference_weight)
        self.assertIn("recommendation_score", explanation.scoring_components)
        self.assertEqual("FOREIGN", explanation.affinity)
        self.assertEqual(1, explanation.rank)
        self.assertTrue(explanation.recommended)

    def test_a_native_hull_is_explained_distinctly_from_a_real_acquisition_candidate(self) -> None:
        own = Hull("own", "Own", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("own",))
        registry = Registry.from_scan(ScanResult(hulls=[own], factions=[faction]))
        explanation = explain_acquisition_candidate(faction, registry, "LINE_BRAWLER", "own")
        self.assertTrue(explanation.resolved)
        self.assertTrue(explanation.is_native)
        self.assertFalse(explanation.recommended)
        self.assertIn("already known natively", explanation.reason)

    def test_a_zero_scoring_hull_is_explained_distinctly(self) -> None:
        bare = Hull("bare", "Bare", "core", SOURCE)
        faction = Faction("f", "Faction", "core", SOURCE)
        registry = Registry.from_scan(ScanResult(hulls=[bare], factions=[faction]))
        explanation = explain_acquisition_candidate(faction, registry, "LINE_BRAWLER", "bare")
        self.assertTrue(explanation.resolved)
        self.assertEqual(0.0, explanation.capability_score)
        self.assertIn("no real evidence", explanation.reason)

    def test_an_unresolved_hull_id_is_explained_distinctly(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE)
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        explanation = explain_acquisition_candidate(faction, registry, "LINE_BRAWLER", "not_a_real_hull")
        self.assertFalse(explanation.resolved)


class CombinedWhyNotExplanationTests(unittest.TestCase):
    def test_all_three_legs_are_answered_together(self) -> None:
        weak_own = Hull("weak_own", "WeakOwn", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        strong_foreign = Hull("strong_foreign", "StrongForeign", "core", SOURCE,
                               weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8)))
        requester = Faction("f", "Faction", "core", SOURCE, known_hulls=("weak_own",))
        owner = Faction("other", "Other", "core", SOURCE, known_hulls=("strong_foreign",))
        registry = Registry.from_scan(ScanResult(hulls=[weak_own, strong_foreign], factions=[requester, owner]))
        combined = explain_candidate(requester, registry, "LINE_BRAWLER", "strong_foreign")
        self.assertFalse(combined.native.resolved)  # not a known hull of this faction at all
        self.assertFalse(combined.retrofit.considered)  # only native shortlist hulls are considered for retrofit
        self.assertTrue(combined.acquisition.resolved)
        self.assertTrue(combined.acquisition.recommended)


if __name__ == "__main__":
    unittest.main()
