from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from starsector_variant_generator.analysis.calibration import (
    CalibrationExpectationKind,
    CalibrationLabel,
)
from starsector_variant_generator.analysis.calibration_runner import (
    collect_all_observations,
    collect_build_observations,
    collect_faction_and_scenario_observations,
)
from starsector_variant_generator.core.models import Faction, Hull, ScanResult
from starsector_variant_generator.core.registry import Registry


def hull(hull_id: str = "test", source_mod: str = "fixture", source_hash: str = "hash") -> Hull:
    return Hull(hull_id, hull_id, source_mod, Path("fixture.csv"), source_hash=source_hash)


class CalibrationRunnerTests(unittest.TestCase):
    def test_records_best_legal_build_for_source_qualified_hull(self) -> None:
        scan = ScanResult(hulls=[hull()])
        registry = Registry.from_scan(scan)
        label = CalibrationLabel("hull:fixture:test", "hash", "GOOD", "TANK")
        outcome = type("Outcome", (), {"assessed_candidates": [{"legality": "LEGAL", "build_archetype": {"build_id": "TANK"}}]})()
        with patch("starsector_variant_generator.analysis.calibration_runner.api.run_generate", return_value=outcome):
            result = collect_build_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual({"entity_hash": "hash", "actual": "TANK"}, result.observations[label.entity_key])
        self.assertEqual("OBSERVED", result.diagnostics[0]["status"])

    def test_duplicate_global_id_is_unsupported_not_cross_mod_generated(self) -> None:
        scan = ScanResult(hulls=[hull("test", "one"), hull("test", "two")])
        label = CalibrationLabel("hull:one:test", "hash", "GOOD", "TANK")
        result = collect_build_observations((label,), scan, Registry.from_scan(scan), "baseline_0.7")
        self.assertEqual({"entity_hash": "hash"}, result.observations[label.entity_key])
        self.assertEqual("hull_id_is_ambiguous_in_registry", result.diagnostics[0]["reason"])

    def test_a_second_label_for_the_same_hull_does_not_clobber_the_first_labels_actual(self) -> None:
        """Regression for a real bug found while activating this pipeline against
        real reviewer-milestone data: a fixture commonly carries several labels
        for one hull (e.g. two milestone-guide roles for the same ship -- this
        happens in the real dormant ``generated/calibration/reviewer_milestones.json``
        fixture). ``observations`` used to be reset to a bare ``{"entity_hash": ...}``
        on every label sharing an entity_key, silently discarding an
        already-recorded ``actual`` from an earlier label for the same key."""
        scan = ScanResult(hulls=[hull()])
        registry = Registry.from_scan(scan)
        first = CalibrationLabel("hull:fixture:test", "hash", "ROLE_A", "TANK")
        second = CalibrationLabel("hull:fixture:test", "hash", "ROLE_B", "ARTILLERY")
        outcome = type("Outcome", (), {"assessed_candidates": [{"legality": "LEGAL", "build_archetype": {"build_id": "TANK"}}]})()
        with patch("starsector_variant_generator.analysis.calibration_runner.api.run_generate", return_value=outcome) as mock_generate:
            result = collect_build_observations((first, second), scan, registry, "baseline_0.7")
        self.assertEqual({"entity_hash": "hash", "actual": "TANK"}, result.observations["hull:fixture:test"])
        self.assertEqual(["OBSERVED", "OBSERVED"], [entry["status"] for entry in result.diagnostics])
        # Generation is real work (a full candidate search); it must run once
        # per hull, not once per label referencing that hull.
        mock_generate.assert_called_once()

    def test_expected_top_set_records_rank_of_first_matching_legal_candidate(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
        )
        scan = ScanResult(hulls=[hull()])
        registry = Registry.from_scan(scan)
        label = CalibrationLabel("hull:fixture:test", "hash", "EXPECTED_TOP_2", "TANK", CalibrationExpectationKind.EXPECTED_TOP_SET, top_n=2)
        outcome = type("Outcome", (), {"assessed_candidates": [
            {"legality": "LEGAL", "build_archetype": {"build_id": "ARTILLERY"}},
            {"legality": "ILLEGAL", "build_archetype": {"build_id": "TANK"}},  # illegal -- must never count toward rank
            {"legality": "LEGAL", "build_archetype": {"build_id": "TANK"}},
        ]})()
        with patch("starsector_variant_generator.analysis.calibration_runner.api.run_generate", return_value=outcome):
            result = collect_build_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual(2, result.observations[label.entity_key]["actual_rank"])

    def test_expected_top_set_reports_not_in_ranked_set_sentinel_when_absent(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
        )
        from starsector_variant_generator.analysis.calibration_runner import (
            NOT_IN_RANKED_SET,
        )
        scan = ScanResult(hulls=[hull()])
        registry = Registry.from_scan(scan)
        label = CalibrationLabel("hull:fixture:test", "hash", "EXPECTED_TOP_2", "MISSILE_SUPPORT", CalibrationExpectationKind.EXPECTED_TOP_SET, top_n=2)
        outcome = type("Outcome", (), {"assessed_candidates": [{"legality": "LEGAL", "build_archetype": {"build_id": "TANK"}}]})()
        with patch("starsector_variant_generator.analysis.calibration_runner.api.run_generate", return_value=outcome):
            result = collect_build_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual(NOT_IN_RANKED_SET, result.observations[label.entity_key]["actual_rank"])

    def test_equipment_expectation_reads_the_requested_mounts_weapon(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
        )
        scan = ScanResult(hulls=[hull()])
        registry = Registry.from_scan(scan)
        label = CalibrationLabel("hull:fixture:test", "hash", "ACCEPTABLE_SUBSTITUTES", "weapon_a", CalibrationExpectationKind.EQUIPMENT_EXPECTATION, expected_any=("weapon_a", "weapon_b"), mount_id="WS0001")
        outcome = type("Outcome", (), {"assessed_candidates": [
            {"legality": "LEGAL", "build_archetype": {"build_id": "TANK"}, "variant": {"weapons_by_mount": {"WS0001": "weapon_b"}}},
        ]})()
        with patch("starsector_variant_generator.analysis.calibration_runner.api.run_generate", return_value=outcome):
            result = collect_build_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual("weapon_b", result.observations[label.entity_key]["actual"])

    def test_equipment_expectation_without_mount_id_is_unsupported(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
        )
        scan = ScanResult(hulls=[hull()])
        registry = Registry.from_scan(scan)
        label = CalibrationLabel("hull:fixture:test", "hash", "ACCEPTABLE_SUBSTITUTES", "weapon_a", CalibrationExpectationKind.EQUIPMENT_EXPECTATION)
        result = collect_build_observations((label,), scan, registry, "baseline_0.7")
        self.assertNotIn("actual", result.observations.get(label.entity_key, {}))
        self.assertEqual("equipment_expectation_missing_mount_id", result.diagnostics[0]["reason"])

    def test_a_hull_with_no_local_source_hash_never_crashes_and_stays_unsupported(self) -> None:
        """A second real latent gap found alongside the clobber bug: when a hull
        has no ``source_hash`` at all, the old code skipped creating an
        ``observations`` entry but still went on to try writing ``actual`` into
        it on a successful generation, which would have raised ``KeyError``."""
        scan = ScanResult(hulls=[hull(source_hash=None)])
        registry = Registry.from_scan(scan)
        label = CalibrationLabel("hull:fixture:test", "hash", "GOOD", "TANK")
        outcome = type("Outcome", (), {"assessed_candidates": [{"legality": "LEGAL", "build_archetype": {"build_id": "TANK"}}]})()
        with patch("starsector_variant_generator.analysis.calibration_runner.api.run_generate", return_value=outcome):
            result = collect_build_observations((label,), scan, registry, "baseline_0.7")
        self.assertNotIn(label.entity_key, result.observations)
        self.assertEqual("hull_has_no_local_source_hash", result.diagnostics[0]["reason"])


def _faction_registry() -> tuple[Faction, Registry]:
    """A real, wholly synthetic (invented ids, no copied game/mod data)
    2-hull faction: `strong_hull` has 8 medium ballistic mounts (LINE_BRAWLER
    capability_score 1.0, a real top native candidate); `weak_hull` has no
    mounts at all (capability_score 0.0 -- a real, resolved candidate that
    simply scores zero, distinct from an unresolved/unknown hull)."""
    strong = Hull("strong_hull", "Strong Hull", "core", Path("fixture.csv"),
                  weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(8)),
                  source_hash="synthetic-strong")
    weak = Hull("weak_hull", "Weak Hull", "core", Path("fixture.csv"), source_hash="synthetic-weak")
    faction = Faction("f", "Faction", "core", Path("fixture.csv"), known_hulls=("strong_hull", "weak_hull"))
    return faction, Registry.from_scan(ScanResult(hulls=[strong, weak], factions=[faction]))


class FactionAndScenarioObservationTests(unittest.TestCase):
    """Real, non-mocked coverage of `collect_faction_and_scenario_observations`
    -- exercises the actual `explain_native_candidate`/`explain_scenario_candidate`
    call path against a synthetic registry, never a mocked outcome, since
    (unlike `collect_build_observations`'s `api.run_generate` call) these are
    cheap, deterministic analysis-layer calls safe to run for real in a unit
    test."""

    def test_a_top_scoring_hull_is_observed_as_recommended(self) -> None:
        faction, registry = _faction_registry()
        scan = ScanResult(hulls=[registry.hulls.by_id["strong_hull"], registry.hulls.by_id["weak_hull"]], factions=[faction])
        label = CalibrationLabel("faction:f:LINE_BRAWLER:core:strong_hull", "synthetic-strong", "SHOULD_BE_RECOMMENDED", "RECOMMENDED", CalibrationExpectationKind.FACTION_EXPECTATION)
        result = collect_faction_and_scenario_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual("RECOMMENDED", result.observations[label.entity_key]["actual"])
        self.assertEqual("OBSERVED", result.diagnostics[0]["status"])
        self.assertIn(label.entity_key, result.confidences)

    def test_a_zero_scoring_hull_is_real_negative_evidence_not_unsupported(self) -> None:
        faction, registry = _faction_registry()
        scan = ScanResult(hulls=[registry.hulls.by_id["strong_hull"], registry.hulls.by_id["weak_hull"]], factions=[faction])
        label = CalibrationLabel("faction:f:LINE_BRAWLER:core:weak_hull", "synthetic-weak", "SHOULD_NOT_BE_RECOMMENDED", "NOT_RECOMMENDED", CalibrationExpectationKind.FACTION_EXPECTATION)
        result = collect_faction_and_scenario_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual("NOT_RECOMMENDED", result.observations[label.entity_key]["actual"])
        self.assertEqual("OBSERVED", result.diagnostics[0]["status"])

    def test_a_hull_not_known_to_the_faction_is_unsupported(self) -> None:
        faction, registry = _faction_registry()
        other = Hull("other_hull", "Other", "core", Path("fixture.csv"), source_hash="synthetic-other")
        scan = ScanResult(hulls=[registry.hulls.by_id["strong_hull"], registry.hulls.by_id["weak_hull"], other], factions=[faction])
        registry = Registry.from_scan(scan)  # rebuild so `other_hull` (known to no faction) is indexed too
        label = CalibrationLabel("faction:f:LINE_BRAWLER:core:other_hull", "synthetic-other", "L", "RECOMMENDED", CalibrationExpectationKind.FACTION_EXPECTATION)
        result = collect_faction_and_scenario_observations((label,), scan, registry, "baseline_0.7")
        self.assertNotIn("actual", result.observations.get(label.entity_key, {}))
        self.assertEqual("hull_not_a_real_candidate_for_this_role", result.diagnostics[0]["reason"])

    def test_expected_top_set_on_a_faction_key_uses_the_real_rank(self) -> None:
        faction, registry = _faction_registry()
        scan = ScanResult(hulls=[registry.hulls.by_id["strong_hull"], registry.hulls.by_id["weak_hull"]], factions=[faction])
        label = CalibrationLabel("faction:f:LINE_BRAWLER:core:strong_hull", "synthetic-strong", "TOP_1", "RECOMMENDED", CalibrationExpectationKind.EXPECTED_TOP_SET, top_n=1)
        result = collect_faction_and_scenario_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual(1, result.observations[label.entity_key]["actual_rank"])

    def test_unresolved_faction_id_is_unsupported(self) -> None:
        faction, registry = _faction_registry()
        scan = ScanResult(hulls=[registry.hulls.by_id["strong_hull"]], factions=[faction])
        label = CalibrationLabel("faction:not_a_real_faction:LINE_BRAWLER:core:strong_hull", "synthetic-strong", "L", "RECOMMENDED", CalibrationExpectationKind.FACTION_EXPECTATION)
        result = collect_faction_and_scenario_observations((label,), scan, registry, "baseline_0.7")
        self.assertEqual("faction_id_not_resolved", result.diagnostics[0]["reason"])

    def test_scenario_expectation_uses_the_real_scenario_ranking(self) -> None:
        # Reuses the exact fixture shape ROADMAP.md Phase 31's own test
        # suite (tests/test_scenario_recommendation.py::_line_brawler_fixture)
        # hand-verified: 3 medium ballistic mounts -> LINE_BRAWLER
        # capability_score 0.375 (a real WEAK gap), ranked build LINE_ANCHOR
        # under baseline_0.4, and DEFENSE is a real, above-signal scenario
        # fit for that exact build -- so `explain_scenario_candidate` here
        # is exercised against real, independently-verified evidence, not a
        # hand-picked pass-through.
        hull = Hull("line_brawler_hull", "Line Brawler Hull", "core", Path("fixture.csv"),
                    weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
                    source_hash="synthetic-brawler")
        faction = Faction("f", "Faction", "core", Path("fixture.csv"), known_hulls=("line_brawler_hull",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        scan = ScanResult(hulls=[hull], factions=[faction])
        label = CalibrationLabel(
            "scenario:f:DEFENSE:LINE_BRAWLER:core:line_brawler_hull:LINE_ANCHOR", "synthetic-brawler",
            "DEFENSE_SHOULD_RECOMMEND_LINE_ANCHOR", "RECOMMENDED", CalibrationExpectationKind.SCENARIO_EXPECTATION,
        )
        result = collect_faction_and_scenario_observations((label,), scan, registry, "baseline_0.4")
        self.assertEqual("RECOMMENDED", result.observations[label.entity_key]["actual"])

    def test_unknown_scenario_category_is_unsupported(self) -> None:
        hull = Hull("line_brawler_hull", "Line Brawler Hull", "core", Path("fixture.csv"),
                    weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(3)),
                    source_hash="synthetic-brawler")
        faction = Faction("f", "Faction", "core", Path("fixture.csv"), known_hulls=("line_brawler_hull",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        scan = ScanResult(hulls=[hull], factions=[faction])
        label = CalibrationLabel(
            "scenario:f:NOT_A_REAL_CATEGORY:LINE_BRAWLER:core:line_brawler_hull:LINE_ANCHOR", "synthetic-brawler",
            "L", "RECOMMENDED", CalibrationExpectationKind.SCENARIO_EXPECTATION,
        )
        result = collect_faction_and_scenario_observations((label,), scan, registry, "baseline_0.4")
        self.assertEqual("unknown_scenario_category", result.diagnostics[0]["reason"])

    def test_collect_all_observations_merges_hull_and_faction_keyed_labels_without_collision(self) -> None:
        faction, registry = _faction_registry()
        scan = ScanResult(hulls=[registry.hulls.by_id["strong_hull"], registry.hulls.by_id["weak_hull"]], factions=[faction])
        build_label = CalibrationLabel("hull:core:strong_hull", "synthetic-strong", "GOOD_BUILD", "TANK")
        faction_label = CalibrationLabel("faction:f:LINE_BRAWLER:core:strong_hull", "synthetic-strong", "SHOULD_BE_RECOMMENDED", "RECOMMENDED", CalibrationExpectationKind.FACTION_EXPECTATION)
        outcome = type("Outcome", (), {"assessed_candidates": [{"legality": "LEGAL", "build_archetype": {"build_id": "TANK"}}]})()
        with patch("starsector_variant_generator.analysis.calibration_runner.api.run_generate", return_value=outcome):
            result = collect_all_observations((build_label, faction_label), scan, registry, "baseline_0.7")
        self.assertEqual("TANK", result.observations["hull:core:strong_hull"]["actual"])
        self.assertEqual("RECOMMENDED", result.observations["faction:f:LINE_BRAWLER:core:strong_hull"]["actual"])
