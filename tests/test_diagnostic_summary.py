from __future__ import annotations

import unittest

from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.output.diagnostic_summary import summarize_scan_issues


class DiagnosticSummaryTests(unittest.TestCase):
    def test_categories_are_conservative_and_aggregate_only(self) -> None:
        scan = ScanResult(
            errors=["x: Extra data: line 1", "y: Expecting value: line 2"],
            warnings=["x: skin's baseHullId None is unresolved; skin not materialized as a hull."],
            skipped_entities=["Enabled mod not discovered: example", "x: fighter row without a stable id skipped"],
        )
        result = summarize_scan_issues(scan)
        self.assertEqual({"MALFORMED_OR_CONCATENATED_DATA": 1, "MALFORMED_VALUE": 1}, result["error_categories"])
        self.assertEqual({"UNRESOLVED_SKIN_BASE_HULL": 1}, result["warning_categories"])
        self.assertEqual({"MISSING_STABLE_ID_ROW": 1, "STALE_ENABLED_MOD_REFERENCE": 1}, result["environment_categories"])


if __name__ == "__main__":
    unittest.main()
