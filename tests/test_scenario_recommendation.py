"""Regression tests for ROADMAP.md Phase 31 (Scenario-Aware Recommendations,
Charter Priority 9): `analysis/gap_recommendation.py`'s new
`recommend_scenario_solutions`/`explain_scenario_candidate`.

All fixtures are synthetic, invented hulls -- no real Starsector/mod data,
per this project's distribution boundary. The single-hull fixture used
throughout is deliberately built with every optional raw stat left unset
(no armor/hitpoints/speed/flux/shield), so every `MechanicalArchetypeProfile`
compatibility score is hand-computable exactly from the plain weighted
formulas in `analysis/mechanical_archetypes.py` -- this lets the tests below
assert exact `scenario_fit_score` values rather than only loose bounds.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.gap_recommendation import (
    SCENARIO_RECOMMENDATION_KIND,
    ScenarioCategory,
    explain_scenario_candidate,
    recommend_gap_solutions,
    recommend_scenario_solutions,
    scenario_fits_for_hull,
)
from starsector_variant_generator.core.models import Faction, Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


def _line_brawler_fixture() -> tuple[Faction, Registry]:
    """A 3-medium-ballistic-mount hull with no other raw stats set.

    LINE_BRAWLER capability_score = 3/8 = 0.375 (a real WEAK gap, below
    gap_adequate_threshold=0.40). Under baseline_0.4+, hand-verified the
    ranked build is deterministically LINE_ANCHOR (ranking score 0.1455,
    ahead of TANK's 0.11663 and FINISHER's 0.07875) with mechanical
    archetype scores ARMOR_BRAWLER=0.32, SHIELD_BRAWLER=0.24,
    LINE_SHIP=0.46, SKIRMISHER=0.10, STRIKER=0.20, PD_ESCORT=0.0 -- see the
    module docstring for the full by-hand derivation from
    `analysis/mechanical_archetypes.py`'s plain weighted formulas.
    """
    hull = Hull(
        "line_brawler_hull", "Line Brawler Hull", "core", SOURCE,
        weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
    )
    faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("line_brawler_hull",))
    registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
    return faction, registry


class ScenarioCategoryTests(unittest.TestCase):
    def test_the_scenario_set_is_small_and_explicitly_synthetic(self) -> None:
        # ROADMAP.md Phase 40 (user "Phase 4") extended the original four
        # (Phase 31) with nine further categories, each backed by a real,
        # distinct signal -- see ScenarioCategoryFitScoreTests below.
        self.assertEqual(
            {
                "RAIDING", "DEFENSE", "ESCORT", "PATROL",
                "ANTI_ARMOR", "ANTI_SHIELD", "LINE_HOLDING", "LONG_RANGE_PRESSURE",
                "MISSILE_STRIKE", "PD_SCREEN", "CARRIER_SUPPORT", "PURSUIT",
                "LOW_COST_REFIT_FRIENDLY",
            },
            {category.value for category in ScenarioCategory},
        )

    def test_the_recommendation_kind_constant_matches_the_charter_wording(self) -> None:
        self.assertEqual("INFERRED_SCENARIO_OPTION", SCENARIO_RECOMMENDATION_KIND)


class ScenarioRecommendationTests(unittest.TestCase):
    def test_a_well_fitting_scenario_is_labeled_and_layered_on_the_native_leg(self) -> None:
        # The native leg's build-diversity selection surfaces this one hull
        # under all 3 preferred LINE_BRAWLER builds (TANK/LINE_ANCHOR/
        # FINISHER); DEFENSE fits LINE_ANCHOR (0.511) and TANK (0.606) above
        # the signal threshold, ranked LINE_ANCHOR first since its
        # base_recommendation_score (0.1455) outweighs TANK's lower fit gap.
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        native_by_build = {rec.build_archetype_id: rec for rec in gap_result.native_recommendations["LINE_BRAWLER"]}
        self.assertEqual({"LINE_ANCHOR", "FINISHER", "TANK"}, set(native_by_build))

        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.DEFENSE, "baseline_0.4")["LINE_BRAWLER"]
        self.assertEqual(("LINE_ANCHOR", "TANK"), tuple(rec.build_archetype_id for rec in recs))
        rec = recs[0]
        self.assertEqual(SCENARIO_RECOMMENDATION_KIND, rec.kind)
        self.assertEqual("DEFENSE", rec.scenario)
        self.assertEqual("line_brawler_hull", rec.hull_id)
        self.assertEqual("NATIVE", rec.source_leg)
        self.assertIsNone(rec.source_variant_id)
        # Layered on top of, not a replacement for, the leg's own real score.
        self.assertEqual(native_by_build["LINE_ANCHOR"].recommendation_score, rec.base_recommendation_score)
        self.assertAlmostEqual(0.511, rec.scenario_fit_score, places=6)
        self.assertAlmostEqual(round(rec.base_recommendation_score * rec.scenario_fit_score, 6), rec.scenario_recommendation_score)
        self.assertEqual(1, rec.rank)
        self.assertEqual(2, recs[1].rank)
        self.assertIn("heuristic", rec.reason.lower())
        self.assertIn("not evidence-based", rec.reason.lower())

    def test_a_second_well_fitting_scenario_computes_its_own_independent_fit_score(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.PATROL, "baseline_0.4")["LINE_BRAWLER"]
        self.assertEqual(("LINE_ANCHOR", "TANK"), tuple(rec.build_archetype_id for rec in recs))
        self.assertAlmostEqual(0.613, recs[0].scenario_fit_score, places=6)

    def test_a_poorly_fitting_build_is_excluded_while_a_better_fitting_build_of_the_same_hull_still_appears(self) -> None:
        # RAIDING favors FLANK_AND_COMMIT/short-range/mobility: FINISHER
        # fits (0.495, above the signal threshold) while LINE_ANCHOR
        # (0.145) and TANK do not -- proves exclusion operates per
        # Hull + BuildArchetype unit, never fabricating a recommendation
        # for a build that doesn't genuinely fit, even when a sibling
        # build on the identical hull does.
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.RAIDING, "baseline_0.4")["LINE_BRAWLER"]
        self.assertEqual(("FINISHER",), tuple(rec.build_archetype_id for rec in recs))

    def test_a_scenario_with_no_fitting_build_at_all_is_fully_excluded(self) -> None:
        # ESCORT's heuristic fit is below the signal threshold for all 3 of
        # this hull's preferred LINE_BRAWLER builds -- the role must be
        # simply absent from the result, never padded with a low-fit option.
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.ESCORT, "baseline_0.4").get("LINE_BRAWLER", ())
        self.assertEqual((), recs)

    def test_confidence_is_bounded_below_full_certainty_even_when_the_underlying_leg_is_fully_confident(self) -> None:
        # Unlike the bare fixture above (whose missing structural fields
        # already reduce build confidence below 1.0), this hull supplies
        # every field infer_build_archetypes checks for missing-feature
        # confidence, so the underlying NATIVE leg is genuinely fully
        # confident -- isolating scenario_confidence_cap's own effect.
        hull = Hull(
            "full_stats_hull", "Full Stats Hull", "core", SOURCE,
            weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
            raw={"armor rating": 1100, "hitpoints": 9000, "shield type": "OMNI", "max speed": 50},
            flux_dissipation=800.0,
        )
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("full_stats_hull",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        native = next(rec for rec in gap_result.native_recommendations["LINE_BRAWLER"] if rec.build_archetype_id == "LINE_ANCHOR")
        self.assertEqual(1.0, native.confidence)  # the underlying leg is fully confident
        rec = next(
            rec for rec in recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.DEFENSE, "baseline_0.4")["LINE_BRAWLER"]
            if rec.build_archetype_id == "LINE_ANCHOR"
        )
        self.assertLess(rec.confidence, 1.0)  # the heuristic overlay never is
        self.assertLessEqual(rec.confidence, 0.75)  # scenario_confidence_cap default

    def test_computing_scenario_recommendations_never_mutates_or_hides_the_existing_gap_result(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        native_before = gap_result.native_recommendations
        retrofit_before = gap_result.retrofit_recommendations
        acquisition_before = gap_result.acquisition_recommendations
        recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.DEFENSE, "baseline_0.4")
        recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.RAIDING, "baseline_0.4")
        self.assertEqual(native_before, gap_result.native_recommendations)
        self.assertEqual(retrofit_before, gap_result.retrofit_recommendations)
        self.assertEqual(acquisition_before, gap_result.acquisition_recommendations)

    def test_a_role_absent_from_every_leg_produces_no_scenario_recommendations(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        self.assertNotIn("MISSILE_SUPPORT", gap_result.native_recommendations)
        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.DEFENSE, "baseline_0.4").get("MISSILE_SUPPORT", ())
        self.assertEqual((), recs)


class RetrofitLegScenarioSourceTests(unittest.TestCase):
    def test_a_retrofit_sourced_scenario_option_cites_its_real_source_variant(self) -> None:
        # Same fixture shape as test_gap_recommendation.py's own retrofit
        # test: a single under-fitted mount that a genuine Refit Assistant
        # pass can improve, isolating the retrofit search deterministically.
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20,
                    weapon_mounts=tuple({"id": mount_id, "type": "BALLISTIC", "size": "SMALL"} for mount_id in ("A", "B", "C")))
        long_ranged = Weapon("long_ranged", "Long", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        short_ranged = Weapon("short_ranged", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        variant = Variant("h_Standard", "Standard", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "long_ranged"})
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[long_ranged, short_ranged], variants=[variant], factions=[faction]))
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        self.assertTrue(gap_result.retrofit_recommendations.get("LINE_BRAWLER"))
        retrofit = gap_result.retrofit_recommendations["LINE_BRAWLER"][0]
        self.assertIsNotNone(retrofit.build_archetype_id)

        for scenario in ScenarioCategory:
            for rec in recommend_scenario_solutions(faction, registry, gap_result, scenario, "baseline_0.4").get("LINE_BRAWLER", ()):
                if rec.source_leg == "RETROFIT":
                    self.assertEqual(retrofit.variant_id, rec.source_variant_id)
                    self.assertEqual(retrofit.recommendation_score, rec.base_recommendation_score)


class ExplainScenarioCandidateTests(unittest.TestCase):
    def test_a_recommended_scenario_option_is_explained_as_recommended_and_distinct_from_direct_evidence(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        explanation = explain_scenario_candidate(
            faction, registry, gap_result, ScenarioCategory.DEFENSE, "LINE_BRAWLER", "line_brawler_hull", "LINE_ANCHOR", "baseline_0.4",
        )
        self.assertTrue(explanation.considered)
        self.assertTrue(explanation.recommended)
        self.assertEqual(1, explanation.rank)
        self.assertAlmostEqual(0.511, explanation.scenario_fit_score, places=6)
        self.assertIn("INFERRED_SCENARIO_OPTION", explanation.reason)
        self.assertIn("not evidence-based", explanation.reason.lower())
        # The underlying, direct evidence-based Why-Not is a separate,
        # clearly-labeled field -- never conflated with the scenario reason.
        self.assertIsNotNone(explanation.underlying)
        self.assertEqual("LINE_ANCHOR", explanation.underlying.build_archetype_id)
        self.assertNotEqual(explanation.reason, explanation.underlying.reason)

    def test_a_below_signal_scenario_option_is_explained_distinctly_from_not_considered(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        explanation = explain_scenario_candidate(
            faction, registry, gap_result, ScenarioCategory.RAIDING, "LINE_BRAWLER", "line_brawler_hull", "LINE_ANCHOR", "baseline_0.4",
        )
        self.assertTrue(explanation.considered)  # it IS a real native recommendation for this role
        self.assertFalse(explanation.recommended)
        self.assertAlmostEqual(0.145, explanation.scenario_fit_score, places=6)
        self.assertIn("minimum signal threshold", explanation.reason)

    def test_a_hull_build_pair_absent_from_every_leg_is_explained_as_not_considered(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        # LINE_ANCHOR is mechanically supported for this hull (so the
        # underlying Hull + BuildArchetype evidence resolves), but
        # MISSILE_SUPPORT never appears as a gap/recommendation role for
        # this hull at all -- a real "never entered any leg" case, distinct
        # from "entered a leg but scored below the scenario signal".
        explanation = explain_scenario_candidate(
            faction, registry, gap_result, ScenarioCategory.DEFENSE, "MISSILE_SUPPORT", "line_brawler_hull", "LINE_ANCHOR", "baseline_0.4",
        )
        self.assertFalse(explanation.considered)
        self.assertFalse(explanation.recommended)
        self.assertIn("does not", explanation.reason)

    def test_an_unresolved_hull_is_explained_via_the_underlying_evidence_gap(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        explanation = explain_scenario_candidate(
            faction, registry, gap_result, ScenarioCategory.DEFENSE, "LINE_BRAWLER", "not_a_real_hull", "LINE_ANCHOR", "baseline_0.4",
        )
        self.assertFalse(explanation.considered)
        self.assertFalse(explanation.recommended)
        self.assertIsNone(explanation.scenario_fit_score)
        self.assertIsNotNone(explanation.underlying)


def _weapon_evidence_fixture(hull_id: str, weapon_id: str, damage_type: str) -> tuple[Faction, Registry]:
    """Same 3-medium-ballistic-mount shape as `_line_brawler_fixture`, plus
    one real existing variant mounting one weapon of the given damage type
    on one of its three mounts -- gives `CapabilityVector.ARMOR_BREAKING`/
    `KINETIC_PRESSURE` a real, non-`None`, hand-verifiable value (a clean
    1.0 fraction: 1 resolved weapon of the target damage type out of 1
    resolved weapon total) instead of the "no evidence" `None` the bare
    `_line_brawler_fixture` produces for those two weapon-mounted-evidence
    dimensions.
    """
    hull = Hull(
        hull_id, hull_id, "core", SOURCE,
        weapon_mounts=tuple({"id": mount_id, "type": "BALLISTIC", "size": "MEDIUM"} for mount_id in ("A", "B", "C")),
    )
    weapon = Weapon(weapon_id, weapon_id, "core", SOURCE, size="MEDIUM", mount_type="BALLISTIC", ordnance_points=5, damage_type=damage_type)
    variant = Variant(f"{hull_id}_Standard", "Standard", "core", SOURCE, hull_id=hull_id, weapons_by_mount={"A": weapon_id})
    faction = Faction("f", "Faction", "core", SOURCE, known_hulls=(hull_id,))
    registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant], factions=[faction]))
    return faction, registry


class ScenarioCategoryFitScoreTests(unittest.TestCase):
    """ROADMAP.md Phase 40: proves each of the 9 new categories computes a
    real, hand-verified, fixture-data-derived `scenario_fit_score` on the
    same `_line_brawler_fixture` used throughout Phase 31's own tests --
    never a placeholder -- and that a category's exclusion (never padding a
    below-signal candidate into the recommended set) is exactly as strict
    as the original four's own established discipline.

    Every expected value below was computed by hand from
    `analysis/mechanical_archetypes.py`'s plain weighted formulas (the same
    STRIKER=0.20/SKIRMISHER=0.10/ARMOR_BRAWLER=0.32/SHIELD_BRAWLER=0.24/
    LINE_SHIP=0.46/PD_ESCORT=0.0 scores this module's own docstring already
    establishes for this fixture) and independently cross-checked against
    the real running function before being written here.
    """

    EXPECTED = {
        # (scenario, build_archetype_id): (scenario_fit_score, recommended)
        (ScenarioCategory.ANTI_ARMOR, "LINE_ANCHOR"): (0.114, False),
        (ScenarioCategory.ANTI_ARMOR, "TANK"): (0.114, False),
        (ScenarioCategory.ANTI_ARMOR, "FINISHER"): (0.114, False),
        (ScenarioCategory.ANTI_SHIELD, "LINE_ANCHOR"): (0.235, False),
        (ScenarioCategory.ANTI_SHIELD, "TANK"): (0.315, True),  # a real above-threshold edge case via CONSERVATIVE flux posture
        (ScenarioCategory.ANTI_SHIELD, "FINISHER"): (0.115, False),
        (ScenarioCategory.LINE_HOLDING, "LINE_ANCHOR"): (0.534, True),
        (ScenarioCategory.LINE_HOLDING, "TANK"): (0.514, True),
        (ScenarioCategory.LINE_HOLDING, "FINISHER"): (0.234, False),
        (ScenarioCategory.LONG_RANGE_PRESSURE, "LINE_ANCHOR"): (0.14, False),
        (ScenarioCategory.LONG_RANGE_PRESSURE, "TANK"): (0.19, False),
        (ScenarioCategory.LONG_RANGE_PRESSURE, "FINISHER"): (0.09, False),
        (ScenarioCategory.MISSILE_STRIKE, "LINE_ANCHOR"): (0.03, False),
        (ScenarioCategory.MISSILE_STRIKE, "TANK"): (0.03, False),
        (ScenarioCategory.MISSILE_STRIKE, "FINISHER"): (0.03, False),
        (ScenarioCategory.PD_SCREEN, "LINE_ANCHOR"): (0.225, False),
        (ScenarioCategory.PD_SCREEN, "TANK"): (0.3, True),  # exactly at scenario_fit_min_signal -- proves the boundary is inclusive (score < min_signal excludes, not <=)
        (ScenarioCategory.PD_SCREEN, "FINISHER"): (0.0, False),
        (ScenarioCategory.CARRIER_SUPPORT, "LINE_ANCHOR"): (0.22, False),
        (ScenarioCategory.CARRIER_SUPPORT, "TANK"): (0.22, False),
        (ScenarioCategory.CARRIER_SUPPORT, "FINISHER"): (0.22, False),
        (ScenarioCategory.PURSUIT, "LINE_ANCHOR"): (0.25, False),
        (ScenarioCategory.PURSUIT, "TANK"): (0.15, False),
        (ScenarioCategory.PURSUIT, "FINISHER"): (0.15, False),
        (ScenarioCategory.LOW_COST_REFIT_FRIENDLY, "LINE_ANCHOR"): (0.6, True),
        (ScenarioCategory.LOW_COST_REFIT_FRIENDLY, "TANK"): (0.7, True),
        (ScenarioCategory.LOW_COST_REFIT_FRIENDLY, "FINISHER"): (0.5, True),
    }

    def test_every_new_category_computes_its_documented_real_fit_score(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        for (scenario, build_id), (expected_fit, expected_recommended) in self.EXPECTED.items():
            with self.subTest(scenario=scenario.value, build=build_id):
                explanation = explain_scenario_candidate(
                    faction, registry, gap_result, scenario, "LINE_BRAWLER", "line_brawler_hull", build_id, "baseline_0.4",
                )
                self.assertTrue(explanation.considered)
                self.assertAlmostEqual(expected_fit, explanation.scenario_fit_score, places=6)
                self.assertEqual(expected_recommended, explanation.recommended)

    def test_low_cost_refit_friendly_ranks_all_three_builds_by_scenario_score_not_fit_alone(self) -> None:
        # TANK has the highest raw fit (0.7) but the lowest native
        # recommendation_score of the three -- LINE_ANCHOR (fit 0.6) still
        # ranks first because ranking uses scenario_recommendation_score
        # (base_recommendation_score * fit), never fit alone, proving this
        # heuristic overlay never simply replaces the underlying leg's own
        # evidence-based score with its own.
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.LOW_COST_REFIT_FRIENDLY, "baseline_0.4")["LINE_BRAWLER"]
        self.assertEqual(("LINE_ANCHOR", "TANK", "FINISHER"), tuple(rec.build_archetype_id for rec in recs))
        self.assertEqual((1, 2, 3), tuple(rec.rank for rec in recs))
        for rec in recs:
            self.assertEqual(SCENARIO_RECOMMENDATION_KIND, rec.kind)
            self.assertEqual("NATIVE", rec.source_leg)
            self.assertLessEqual(rec.confidence, 0.75)

    def test_line_holding_is_a_real_distinct_ranking_from_defense_on_the_same_hull(self) -> None:
        # Both DEFENSE and LINE_HOLDING select (LINE_ANCHOR, TANK) for this
        # fixture, but from genuinely different formulas (survivability- vs.
        # sustained-output-weighted) -- proves the new category is not a
        # silent relabeling of an existing one by checking the fit scores
        # actually differ.
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        defense = {rec.build_archetype_id: rec.scenario_fit_score for rec in recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.DEFENSE, "baseline_0.4")["LINE_BRAWLER"]}
        line_holding = {rec.build_archetype_id: rec.scenario_fit_score for rec in recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.LINE_HOLDING, "baseline_0.4")["LINE_BRAWLER"]}
        self.assertEqual({"LINE_ANCHOR", "TANK"}, set(defense))
        self.assertEqual({"LINE_ANCHOR", "TANK"}, set(line_holding))
        for build_id in defense:
            self.assertNotAlmostEqual(defense[build_id], line_holding[build_id], places=3)


class WeaponMountedEvidenceCategoryTests(unittest.TestCase):
    """Proves ANTI_ARMOR/ANTI_SHIELD are computed from real existing-variant
    mounted-weapon damage-type evidence (`CapabilityVector.ARMOR_BREAKING`/
    `KINETIC_PRESSURE`), not from hull structure alone -- a hull with no
    resolved weapons scores both categories the same low, structure-only
    value (see `ScenarioCategoryFitScoreTests` above), while a hull with one
    real HE-damage weapon mounted scores materially higher on ANTI_ARMOR
    specifically, and one with a real KINETIC-damage weapon scores
    materially higher on ANTI_SHIELD specifically -- each without moving the
    other category's score, proving the two real signals do not leak into
    each other.
    """

    def test_a_real_mounted_he_weapon_raises_only_anti_armor(self) -> None:
        faction, registry = _weapon_evidence_fixture("armor_hull", "he_weapon", "HE")
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        anti_armor = explain_scenario_candidate(faction, registry, gap_result, ScenarioCategory.ANTI_ARMOR, "LINE_BRAWLER", "armor_hull", "LINE_ANCHOR", "baseline_0.4")
        anti_shield = explain_scenario_candidate(faction, registry, gap_result, ScenarioCategory.ANTI_SHIELD, "LINE_BRAWLER", "armor_hull", "LINE_ANCHOR", "baseline_0.4")
        self.assertAlmostEqual(0.664, anti_armor.scenario_fit_score, places=6)
        self.assertTrue(anti_armor.recommended)
        # Same structure-only value the no-weapon fixture produces for
        # LINE_ANCHOR (ScenarioCategoryFitScoreTests) -- the HE weapon never
        # inflates the unrelated kinetic-pressure signal.
        self.assertAlmostEqual(0.235, anti_shield.scenario_fit_score, places=6)
        self.assertFalse(anti_shield.recommended)

        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.ANTI_ARMOR, "baseline_0.4")["LINE_BRAWLER"]
        rec = next(rec for rec in recs if rec.build_archetype_id == "LINE_ANCHOR")
        self.assertTrue(any("ARMOR_BREAKING" in line and "score=1.000000" in line for line in rec.scenario_fit_evidence))

    def test_a_real_mounted_kinetic_weapon_raises_only_anti_shield(self) -> None:
        faction, registry = _weapon_evidence_fixture("shield_hull", "kinetic_weapon", "KINETIC")
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        anti_shield = explain_scenario_candidate(faction, registry, gap_result, ScenarioCategory.ANTI_SHIELD, "LINE_BRAWLER", "shield_hull", "LINE_ANCHOR", "baseline_0.4")
        anti_armor = explain_scenario_candidate(faction, registry, gap_result, ScenarioCategory.ANTI_ARMOR, "LINE_BRAWLER", "shield_hull", "LINE_ANCHOR", "baseline_0.4")
        self.assertAlmostEqual(0.785, anti_shield.scenario_fit_score, places=6)
        self.assertTrue(anti_shield.recommended)
        self.assertAlmostEqual(0.114, anti_armor.scenario_fit_score, places=6)
        self.assertFalse(anti_armor.recommended)

        recs = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory.ANTI_SHIELD, "baseline_0.4")["LINE_BRAWLER"]
        rec = next(rec for rec in recs if rec.build_archetype_id == "LINE_ANCHOR")
        self.assertTrue(any("KINETIC_PRESSURE" in line and "score=1.000000" in line for line in rec.scenario_fit_evidence))


class ScenarioFitsForHullTests(unittest.TestCase):
    """ROADMAP.md Phase 40: `scenario_fits_for_hull` is a pure calling
    convenience over the unmodified `recommend_scenario_solutions` -- these
    tests prove it surfaces exactly the categories a hand-verified sweep
    (`ScenarioCategoryFitScoreTests` above) shows genuinely qualify for this
    hull, across every role `gap_result` covers, and nothing else.
    """

    def test_returns_exactly_the_categories_with_a_real_qualifying_entry_for_this_hull(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        portfolio = scenario_fits_for_hull(faction, registry, gap_result, "line_brawler_hull", "baseline_0.4")
        self.assertEqual(
            {"RAIDING", "DEFENSE", "PATROL", "LINE_HOLDING", "LOW_COST_REFIT_FRIENDLY", "ANTI_SHIELD", "PD_SCREEN"},
            set(portfolio),
        )
        # ESCORT/ANTI_ARMOR/LONG_RANGE_PRESSURE/MISSILE_STRIKE/CARRIER_SUPPORT/PURSUIT
        # never clear the signal threshold for this hull on any build -- absent, never padded in.
        for absent in ("ESCORT", "ANTI_ARMOR", "LONG_RANGE_PRESSURE", "MISSILE_STRIKE", "CARRIER_SUPPORT", "PURSUIT"):
            self.assertNotIn(absent, portfolio)
        # Every entry is a real, unmodified ScenarioRecommendation from the
        # exact same ranking recommend_scenario_solutions itself produces.
        for scenario_value, entries in portfolio.items():
            direct = recommend_scenario_solutions(faction, registry, gap_result, ScenarioCategory(scenario_value), "baseline_0.4")["LINE_BRAWLER"]
            self.assertEqual(tuple(item for item in direct if item.hull_id == "line_brawler_hull"), entries)

    def test_a_hull_with_no_qualifying_category_at_all_produces_an_empty_portfolio(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        portfolio = scenario_fits_for_hull(faction, registry, gap_result, "not_a_real_hull", "baseline_0.4")
        self.assertEqual({}, portfolio)

    def test_a_restricted_categories_argument_never_returns_a_category_outside_the_request(self) -> None:
        faction, registry = _line_brawler_fixture()
        gap_result = recommend_gap_solutions(faction, registry, "baseline_0.4")
        portfolio = scenario_fits_for_hull(
            faction, registry, gap_result, "line_brawler_hull", "baseline_0.4",
            categories=(ScenarioCategory.RAIDING, ScenarioCategory.ANTI_ARMOR),
        )
        self.assertEqual({"RAIDING"}, set(portfolio))  # RAIDING qualifies, ANTI_ARMOR does not, ESCORT was never asked for


if __name__ == "__main__":
    unittest.main()
