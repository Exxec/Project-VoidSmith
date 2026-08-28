"""End-to-end calibration-activation regression test.

Runs the real, non-mocked calibration pipeline -- ``load_calibration_labels``
(file I/O) -> ``collect_build_observations`` (real candidate generation via
``api.run_generate`` against a real synthetic ``Registry``) ->
``evaluate_calibration`` (comparison) -- against a hand-authored, clearly
synthetic fixture (``tests/fixtures/calibration/synthetic_capital_activation.json``,
invented hull/entity ids, not copied Starsector/mod data). This is the
portable demonstration that the "built but dormant" calibration machinery
(ROADMAP.md Phase 30) genuinely produces MATCH/MISMATCH/STALE/UNSUPPORTED
from real data flowing through the real comparison code -- it never adjusts
heuristics, and this test asserts that nothing here touches
``core/heuristics.py``'s registry.

See tests/test_calibration.py and tests/test_calibration_runner.py for the
narrower unit-level coverage of ``evaluate_calibration`` and
``collect_build_observations`` individually; this file is the seam between
them, run against a fixture on disk exactly the way
``tools/evaluate_local_calibration.py`` consumes one against a real
installation.
"""
from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from starsector_variant_generator.analysis.calibration import (
    evaluate_calibration,
    load_calibration_labels,
)
from starsector_variant_generator.analysis.calibration_runner import (
    collect_build_observations,
)
from starsector_variant_generator.core.models import Hull, ScanResult
from starsector_variant_generator.core.registry import Registry
from tests.benchmark_support import load_synthetic_archetype

FIXTURE = Path(__file__).parent / "fixtures" / "calibration" / "synthetic_capital_activation.json"


class CalibrationActivationEndToEndTests(unittest.TestCase):
    def _scan(self) -> ScanResult:
        hull, weapons = load_synthetic_archetype("capital_heavy_broadside")
        # Pin a stable, invented hash so the fixture's entity_hash values are
        # meaningful (the archetype fixture itself carries no source_hash).
        hull = dataclasses.replace(hull, source_hash="synthetic-hash-capital-1")
        ambiguous_a = Hull("ambiguous_test_hull", "Ambiguous A", "duplicate_source", Path("synthetic.json"), source_hash="also-synthetic")
        ambiguous_b = Hull("ambiguous_test_hull", "Ambiguous B", "other_source", Path("synthetic.json"), source_hash="also-synthetic")
        return ScanResult(hulls=[hull, *([ambiguous_a, ambiguous_b])], weapons=weapons)

    def test_real_synthetic_data_flows_through_the_full_pipeline_with_every_status(self) -> None:
        fixture_id, labels = load_calibration_labels(FIXTURE)
        self.assertEqual("synthetic-capital-activation-demo", fixture_id)
        self.assertEqual(5, len(labels))

        scan = self._scan()
        registry = Registry.from_scan(scan)
        run = collect_build_observations(labels, scan, registry, "baseline_0.7")

        # The real, independently generated best-legal build for this
        # synthetic capital archetype is LINE_ANCHOR under baseline_0.7 --
        # not asserted as a hardcoded truth here, only used to interpret the
        # per-label statuses below (locked in by the assertions that follow).
        capital_key = "hull:benchmark:benchmark_capital_multimount"
        self.assertEqual("LINE_ANCHOR", run.observations[capital_key]["actual"])

        report = evaluate_calibration(fixture_id, labels, run.observations, "baseline_0.7")
        statuses = {result["label"]: result["status"] for result in report.results}
        self.assertEqual(
            {
                "EXPECTED_LINE_ANCHOR": "MATCH",
                "EXPECTED_NOT_MISSILE_SUPPORT": "MATCH",
                "DELIBERATE_MISMATCH_DEMO": "MISMATCH",
                "STALE_HASH_DEMO": "STALE",
                "AMBIGUOUS_GLOBAL_ID_DEMO": "UNSUPPORTED",
            },
            statuses,
        )
        self.assertEqual((5, 2, 1, 1, 1), (report.evaluated, report.matched, report.mismatched, report.stale, report.unsupported))

    def test_activation_never_touches_the_heuristic_registry(self) -> None:
        """Explicit guard for CLAUDE.md's hard rule: calibration is a
        comparison/reporting mechanism only and must never adjust heuristics
        automatically. Neither calibration module imports the heuristic
        registry at all."""
        import starsector_variant_generator.analysis.calibration as calibration_module
        import starsector_variant_generator.analysis.calibration_runner as calibration_runner_module

        for module in (calibration_module, calibration_runner_module):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertNotIn("REGISTRY", source)
            self.assertNotIn("core.heuristics", source)
            self.assertNotIn("core import heuristics", source)


if __name__ == "__main__":
    unittest.main()
