"""Canonical benchmark checks against real named hulls -- local-only, opt-in.

Skips cleanly (the whole module) when no local benchmark data has been
generated, so `python -m unittest discover` stays green and portable with
no Starsector install present -- see tests/test_benchmark_portable.py for
the suite that always runs. To generate local data:

    python tools/build_local_benchmarks.py --starsector-path "C:\\...\\Starsector"

That writes tests/local_fixtures/<benchmark_id>.generated.json (structural
data only: hull size, mount id/type/size, fighter bay count, hull hints --
no names, descriptions, sprites, or other copyrighted content) and
tests/local_results/<benchmark_id>_baseline.json (this project's own
computed classifier/legality output, not copied game data). Both are
gitignored; see docs/ROADMAP.md's "Canonical benchmark suite" section for
why this split exists.
"""

from __future__ import annotations

import json
import unittest

from tests.benchmark_support import LOCAL_RESULTS_DIR, load_canonical_manifest, load_local_fixture


def _mount_classes_from_fixture(fixture: dict) -> set[str]:
    return {
        f"{str(mount.get('size', '')).upper()}_{str(mount.get('type', '')).upper()}"
        for mount in fixture.get("weapon_mounts", [])
    }


def _load_baseline(benchmark_id: str) -> dict | None:
    path = LOCAL_RESULTS_DIR / f"{benchmark_id}_baseline.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class CanonicalLocalBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_canonical_manifest()
        cls.fixtures = {entry["benchmark_id"]: load_local_fixture(entry["benchmark_id"]) for entry in cls.manifest}
        cls.baselines = {entry["benchmark_id"]: _load_baseline(entry["benchmark_id"]) for entry in cls.manifest}
        if not any(cls.fixtures.values()):
            raise unittest.SkipTest(
                "No local canonical benchmark data found. Run: "
                "python tools/build_local_benchmarks.py --starsector-path <path-to-Starsector>"
            )

    def test_canonical_hulls_match_their_manifest_expectations(self) -> None:
        for entry in self.manifest:
            benchmark_id = entry["benchmark_id"]
            fixture = self.fixtures.get(benchmark_id)
            baseline = self.baselines.get(benchmark_id)
            with self.subTest(benchmark=benchmark_id):
                if fixture is None:
                    self.skipTest("no local fixture generated (hull not resolved in this install, or extractor not yet run)")
                for case in entry["required_test_cases"]:
                    with self.subTest(case=case):
                        self._run_case(case, entry, fixture, baseline)

    def _run_case(self, case: str, entry: dict, fixture: dict, baseline: dict | None) -> None:
        if case == "hull_size_matches":
            self.assertEqual(entry["expected_hull_size"], fixture.get("hull_size"))
        elif case == "mount_classes_present":
            missing = set(entry.get("expected_mount_classes", [])) - _mount_classes_from_fixture(fixture)
            self.assertEqual(set(), missing, f"expected mount classes not found: {missing}")
        elif case == "has_fighter_bays":
            minimum = entry.get("expected_fighter_bays_at_least", 1)
            self.assertIsNotNone(fixture.get("fighter_bays"))
            self.assertGreaterEqual(fixture["fighter_bays"], minimum)
        elif case == "role_scores_present":
            self.assertIsNotNone(baseline, "no local baseline result generated")
            role_compatibility = baseline["role_compatibility"]
            for role in entry["expected_role_tests"]:
                self.assertIn(role, role_compatibility)
                self.assertGreater(role_compatibility[role], 0.0, f"expected {role} > 0")
        elif case == "conservative_candidate_legal":
            self.assertIsNotNone(baseline, "no local baseline result generated")
            candidate = baseline.get("conservative_candidate")
            self.assertIsNotNone(candidate, "no conservative candidate computed")
            self.assertEqual("LEGAL", candidate["legality"])
            self.assertEqual("LEGAL", candidate["revalidated_legality"])
        else:
            self.fail(f"Unknown required_test_case: {case!r}")


if __name__ == "__main__":
    unittest.main()
