from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.analysis.calibration import (
    evaluate_calibration,
    load_calibration_labels,
)


class CalibrationTests(unittest.TestCase):
    def test_hashes_protect_labels_and_unknown_observations_stay_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "labels.json"
            fixture.write_text(json.dumps({"schema_version": "calibration-labels-0.1", "fixture_id": "local", "labels": [
                {"entity_key": "hull:synthetic", "entity_hash": "one", "label": "GOOD_BRAWLER", "expected": "TANK"},
                {"entity_key": "hull:other", "entity_hash": "two", "label": "EXPECTED_TOP_3", "expected": "TOP_3"},
            ]}), encoding="utf-8")
            fixture_id, labels = load_calibration_labels(fixture)
            report = evaluate_calibration(fixture_id, labels, {"hull:synthetic": {"entity_hash": "one", "actual": "TANK"}, "hull:other": {"entity_hash": "changed", "actual": "TOP_3"}}, "baseline_0.7")
            self.assertEqual((1, 0, 1, 0), (report.matched, report.mismatched, report.stale, report.unsupported))

    def test_missing_actual_is_unsupported_not_a_false_failure(self) -> None:
        from starsector_variant_generator.analysis.calibration import CalibrationLabel
        report = evaluate_calibration("fixture", (CalibrationLabel("x", "h", "GOOD", "YES"),), {"x": {"entity_hash": "h"}}, "baseline_0.7")
        self.assertEqual((0, 0, 0, 1), (report.matched, report.mismatched, report.stale, report.unsupported))

    def test_soft_expectation_accepts_any_declared_reasonable_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "labels.json"
            fixture.write_text(json.dumps({"schema_version": "calibration-labels-0.1", "fixture_id": "local", "labels": [{"entity_key": "hull:test", "entity_hash": "one", "label": "EXPECTED_TOP_SET", "expected": "A", "expected_any": ["A", "B"], "strength": "SOFT_EXPECTATION"}]}), encoding="utf-8")
            fixture_id, labels = load_calibration_labels(fixture)
            report = evaluate_calibration(fixture_id, labels, {"hull:test": {"entity_hash": "one", "actual": "B"}}, "baseline_0.7")
            self.assertEqual("SOFT_EXPECTATION", report.results[0]["strength"])
            self.assertEqual(1, report.matched)

    def test_negative_expectation_fails_only_when_forbidden_result_occurs(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
            CalibrationLabel,
        )
        label = CalibrationLabel("hull:test", "one", "NOT_ARTILLERY", "ARTILLERY", CalibrationExpectationKind.NEGATIVE_EXPECTATION)
        matched = evaluate_calibration("fixture", (label,), {"hull:test": {"entity_hash": "one", "actual": "TANK"}}, "baseline_0.7")
        mismatched = evaluate_calibration("fixture", (label,), {"hull:test": {"entity_hash": "one", "actual": "ARTILLERY"}}, "baseline_0.7")
        self.assertEqual((1, 0), (matched.matched, matched.mismatched))
        self.assertEqual((0, 1), (mismatched.matched, mismatched.mismatched))

    def test_expected_top_set_matches_when_rank_is_within_top_n(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
            CalibrationLabel,
        )
        label = CalibrationLabel("hull:test", "one", "EXPECTED_TOP_3", "ARTILLERY", CalibrationExpectationKind.EXPECTED_TOP_SET, top_n=3)
        within = evaluate_calibration("fixture", (label,), {"hull:test": {"entity_hash": "one", "actual_rank": 3}}, "baseline_0.7")
        outside = evaluate_calibration("fixture", (label,), {"hull:test": {"entity_hash": "one", "actual_rank": 4}}, "baseline_0.7")
        self.assertEqual((1, 0), (within.matched, within.mismatched))
        self.assertEqual((0, 1), (outside.matched, outside.mismatched))
        self.assertEqual("rank_3", within.results[0]["actual"])
        self.assertEqual(3, within.results[0]["top_n"])

    def test_expected_top_set_missing_rank_is_unsupported(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
            CalibrationLabel,
        )
        label = CalibrationLabel("hull:test", "one", "EXPECTED_TOP_3", "ARTILLERY", CalibrationExpectationKind.EXPECTED_TOP_SET, top_n=3)
        report = evaluate_calibration("fixture", (label,), {"hull:test": {"entity_hash": "one"}}, "baseline_0.7")
        self.assertEqual((0, 0, 0, 1), (report.matched, report.mismatched, report.stale, report.unsupported))

    def test_expected_top_set_stale_hash_still_reported_as_stale_not_mismatch(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationExpectationKind,
            CalibrationLabel,
        )
        label = CalibrationLabel("hull:test", "one", "EXPECTED_TOP_3", "ARTILLERY", CalibrationExpectationKind.EXPECTED_TOP_SET, top_n=3)
        report = evaluate_calibration("fixture", (label,), {"hull:test": {"entity_hash": "changed", "actual_rank": 1}}, "baseline_0.7")
        self.assertEqual((0, 0, 1, 0), (report.matched, report.mismatched, report.stale, report.unsupported))

    def test_load_calibration_labels_parses_top_n_and_mount_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "labels.json"
            fixture.write_text(json.dumps({"schema_version": "calibration-labels-0.1", "fixture_id": "local", "labels": [
                {"entity_key": "hull:test", "entity_hash": "one", "label": "L", "expected": "A", "expectation_kind": "EXPECTED_TOP_SET", "top_n": 5},
                {"entity_key": "hull:test2", "entity_hash": "two", "label": "L2", "expected": "WEAPON_A", "expected_any": ["WEAPON_A", "WEAPON_B"], "expectation_kind": "EQUIPMENT_EXPECTATION", "mount_id": "WS0001"},
            ]}), encoding="utf-8")
            _, labels = load_calibration_labels(fixture)
            self.assertEqual(5, labels[0].top_n)
            self.assertEqual("WS0001", labels[1].mount_id)
            self.assertEqual(3, labels[1].top_n)  # default preserved when omitted

    def test_load_calibration_labels_rejects_invalid_top_n(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "labels.json"
            fixture.write_text(json.dumps({"schema_version": "calibration-labels-0.1", "fixture_id": "local", "labels": [
                {"entity_key": "hull:test", "entity_hash": "one", "label": "L", "expected": "A", "top_n": 0},
            ]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_calibration_labels(fixture)


class ConfidenceWeightedSummaryTests(unittest.TestCase):
    def test_buckets_mismatches_by_supplied_confidence_without_fabricating_missing_values(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationLabel,
            confidence_weighted_summary,
        )
        report = evaluate_calibration(
            "fixture",
            (
                CalibrationLabel("hull:a", "h", "L_A", "X"),
                CalibrationLabel("hull:b", "h", "L_B", "X"),
                CalibrationLabel("hull:c", "h", "L_C", "X"),
            ),
            {
                "hull:a": {"entity_hash": "h", "actual": "Y"},  # MISMATCH, high confidence
                "hull:b": {"entity_hash": "h", "actual": "Y"},  # MISMATCH, low confidence
                "hull:c": {"entity_hash": "h", "actual": "Y"},  # MISMATCH, unknown confidence
            },
            "baseline_0.7",
        )
        summary = confidence_weighted_summary(report, {"hull:a": 0.9, "hull:b": 0.1})
        self.assertEqual(3, summary["total_mismatches"])
        self.assertEqual(1, summary["counts_by_bucket"]["HIGH_CONFIDENCE_MISMATCH"])
        self.assertEqual(1, summary["counts_by_bucket"]["LOW_CONFIDENCE_MISMATCH"])
        self.assertEqual(1, summary["counts_by_bucket"]["UNKNOWN_CONFIDENCE_MISMATCH"])
        self.assertAlmostEqual(0.5, summary["mean_confidence_of_mismatches"])

    def test_no_mismatches_yields_empty_summary(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationLabel,
            confidence_weighted_summary,
        )
        report = evaluate_calibration("fixture", (CalibrationLabel("hull:a", "h", "L", "X"),), {"hull:a": {"entity_hash": "h", "actual": "X"}}, "baseline_0.7")
        summary = confidence_weighted_summary(report, {})
        self.assertEqual(0, summary["total_mismatches"])
        self.assertIsNone(summary["mean_confidence_of_mismatches"])


class CompareCalibrationReportsTests(unittest.TestCase):
    def test_reports_labels_whose_status_changed_between_two_heuristic_sets(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationLabel,
            compare_calibration_reports,
        )
        labels = (CalibrationLabel("hull:a", "h", "L_A", "X"), CalibrationLabel("hull:b", "h", "L_B", "Y"))
        report_a = evaluate_calibration("fixture", labels, {"hull:a": {"entity_hash": "h", "actual": "X"}, "hull:b": {"entity_hash": "h", "actual": "Z"}}, "baseline_0.7")
        report_b = evaluate_calibration("fixture", labels, {"hull:a": {"entity_hash": "h", "actual": "NOT_X"}, "hull:b": {"entity_hash": "h", "actual": "Y"}}, "baseline_0.10")
        diff = compare_calibration_reports(report_a, report_b)
        changed_keys = {entry["entity_key"] for entry in diff["changed_labels"]}
        self.assertEqual({"hull:a", "hull:b"}, changed_keys)
        self.assertEqual(1, len(diff["matches_gained_by_b"]))
        self.assertEqual(1, len(diff["matches_lost_by_b"]))

    def test_identical_reports_produce_no_changed_labels(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationLabel,
            compare_calibration_reports,
        )
        labels = (CalibrationLabel("hull:a", "h", "L_A", "X"),)
        report = evaluate_calibration("fixture", labels, {"hull:a": {"entity_hash": "h", "actual": "X"}}, "baseline_0.7")
        diff = compare_calibration_reports(report, report)
        self.assertEqual((), diff["changed_labels"])

    def test_mismatched_fixture_ids_are_rejected(self) -> None:
        from starsector_variant_generator.analysis.calibration import (
            CalibrationLabel,
            compare_calibration_reports,
        )
        labels = (CalibrationLabel("hull:a", "h", "L_A", "X"),)
        report_a = evaluate_calibration("fixture_a", labels, {"hull:a": {"entity_hash": "h", "actual": "X"}}, "baseline_0.7")
        report_b = evaluate_calibration("fixture_b", labels, {"hull:a": {"entity_hash": "h", "actual": "X"}}, "baseline_0.7")
        with self.assertRaises(ValueError):
            compare_calibration_reports(report_a, report_b)
