"""Guard for the AGENTS.md Distribution and IP Boundary.

Real-entity calibration packs, review sheets and notes were tracked in git until 2026-10-14 (docs/AUTOMATION_PLAN.md V0.1);
they belong under the gitignored generated/ tree. This test fails if such a file is tracked again.
"""
from __future__ import annotations

import fnmatch
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Under knowledge_packs/ only the schema and neutral examples may be tracked.
ALLOWED_PACK_PREFIXES = ("knowledge_packs/schema/", "knowledge_packs/examples/")
FORBIDDEN_ANYWHERE = ("*.provisional.json", "*_review.csv", "*_calibration_review.csv")


def tracked_files() -> list[str] | None:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        return None
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False)
    if result.returncode != 0:
        return None
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def boundary_violations(files: list[str]) -> list[str]:
    violations = []
    for name in files:
        if name.startswith("knowledge_packs/") and not name.startswith(ALLOWED_PACK_PREFIXES):
            violations.append(name)
        elif any(fnmatch.fnmatch(Path(name).name, pattern) for pattern in FORBIDDEN_ANYWHERE):
            violations.append(name)
    return violations


class DistributionBoundaryTests(unittest.TestCase):
    def test_rules_flag_real_entity_packs_and_allow_schema_and_examples(self) -> None:
        files = [
            "knowledge_packs/schema/faction_pack.schema.json",
            "knowledge_packs/examples/faction.example.json",
            "knowledge_packs/someone_tierlist.provisional.json",
            "knowledge_packs/SOMEONE_NOTES.md",
            "generated/calibration/starsector_calibration_review.csv",
            "src/starsector_variant_generator/api.py",
        ]
        self.assertEqual(
            boundary_violations(files),
            [
                "knowledge_packs/someone_tierlist.provisional.json",
                "knowledge_packs/SOMEONE_NOTES.md",
                "generated/calibration/starsector_calibration_review.csv",
            ],
        )

    def test_no_tracked_file_crosses_the_boundary(self) -> None:
        files = tracked_files()
        if files is None:
            self.skipTest("not a git checkout")
        self.assertEqual(boundary_violations(files), [], "move these to generated/ (AGENTS.md Distribution and IP Boundary)")


if __name__ == "__main__":
    unittest.main()
