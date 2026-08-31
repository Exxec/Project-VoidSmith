from __future__ import annotations

import unittest

from starsector_variant_generator.analysis.gap_recommendation import (
    AcquisitionWhyNotExplanation,
    BuildWhyNotExplanation,
    CombinedWhyNotExplanation,
    RetrofitWhyNotExplanation,
    WhyNotExplanation,
)
from starsector_variant_generator.cli.main import _why_not_report_lines


class WhyNotReportLinesTests(unittest.TestCase):
    """Regression coverage for docs/BUGS.md SVG-019.

    `api.run_why_not` returns `BuildWhyNotExplanation` (a flat `.reason`,
    no `.native`/`.retrofit`/`.acquisition`) when the caller passes
    `--build-archetype`, and only returns the legacy hull-level
    `CombinedWhyNotExplanation` otherwise. `cli/main.py`'s `why-not` command
    previously accessed `.native.reason`/`.retrofit.reason`/
    `.acquisition.reason` unconditionally, which raised `AttributeError`
    for every real `why-not --build-archetype` invocation.
    """

    def test_build_archetype_explanation_reports_its_own_flat_reason(self) -> None:
        explanation = BuildWhyNotExplanation(
            role="LINE_BRAWLER", hull_id="hull_a", build_archetype_id="TANK",
            resolved=True, build=None, recommended_legs=(), reason="Not mechanically viable.",
        )
        self.assertEqual(("build: Not mechanically viable.",), _why_not_report_lines(explanation))

    def test_combined_explanation_reports_all_three_legs(self) -> None:
        native = WhyNotExplanation(
            role="LINE_BRAWLER", hull_id="hull_a", resolved=True, capability_score=1.0,
            rank=1, total_candidates=1, recommended=True, best_score=1.0, reason="native reason",
        )
        retrofit = RetrofitWhyNotExplanation(
            role="LINE_BRAWLER", hull_id="hull_a", considered=True, has_real_variant=True,
            variant_id="variant_a", role_match_before=0.5, role_match_after=0.8,
            quality_gain=0.3, recommended=True, reason="retrofit reason",
        )
        acquisition = AcquisitionWhyNotExplanation(
            role="LINE_BRAWLER", hull_id="hull_a", resolved=True, is_native=False,
            capability_score=1.0, affinity="NATIVE", rank=1, total_candidates=1,
            recommended=True, reason="acquisition reason",
        )
        explanation = CombinedWhyNotExplanation(native=native, retrofit=retrofit, acquisition=acquisition)
        self.assertEqual(
            ("native: native reason", "retrofit: retrofit reason", "acquisition: acquisition reason"),
            _why_not_report_lines(explanation),
        )


if __name__ == "__main__":
    unittest.main()
