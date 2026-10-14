"""Ratchet for docs/AUTOMATION_PLAN.md V0.2: bare in-place writes and tree deletes in src/ may only shrink.

Counts `.write_text(`, `.write_bytes(` and `rmtree(` per source file against tests/safeio_baseline.json. A new bare call fails the
test; removing one requires lowering the baseline in the same commit (the test fails when the baseline is higher than reality).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "starsector_variant_generator"
BASELINE = Path(__file__).with_name("safeio_baseline.json")
PATTERN = re.compile(r"\.write_text\(|\.write_bytes\(|\brmtree\(")
EXEMPT = {"core/safeio.py"}  # the module that implements the safe versions


def count_bare_calls() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative in EXEMPT:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        hits = sum(len(PATTERN.findall(line)) for line in lines if not line.lstrip().startswith("#"))
        if hits:
            counts[relative] = hits
    return counts


class SafeIoRatchetTests(unittest.TestCase):
    def test_bare_writes_and_deletes_never_grow_and_the_baseline_stays_honest(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        current = count_bare_calls()
        grown = {f: (baseline.get(f, 0), n) for f, n in current.items() if n > baseline.get(f, 0)}
        self.assertEqual({}, grown, "Use core.safeio (atomic_write_*, safe_rmtree) instead of a bare write_text/write_bytes/rmtree.")
        stale = {f: (n, current.get(f, 0)) for f, n in baseline.items() if n > current.get(f, 0)}
        self.assertEqual({}, stale, "Lower tests/safeio_baseline.json to the current counts (the baseline may only shrink).")


if __name__ == "__main__":
    unittest.main()
