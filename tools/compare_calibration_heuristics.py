"""Compare a real calibration fixture's evaluation under two heuristic sets.

ROADMAP.md Phase 39 item 5 ("per-heuristic before/after comparison"): a
reporting/regression tool only. It runs the SAME real reviewer fixture
through the SAME real, registered observers (`collect_all_observations`)
under two different, already-existing, human-authored heuristic sets, then
reports where their MATCH/MISMATCH classification differs
(`compare_calibration_reports`).

This never selects a "better" heuristic set, never blends the two, and
never writes a new heuristic set or touches `core/heuristics.py` -- it only
surfaces where two real, already-computed evaluations disagree. Whether
that disagreement justifies a new, deliberately authored `baseline_0.1x`
entry (with its own rationale citing this evidence) is a human's decision,
made after reading this report, never this tool's.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from starsector_variant_generator.analysis.calibration import (
    compare_calibration_reports,
    evaluate_calibration,
    load_calibration_labels,
)
from starsector_variant_generator.analysis.calibration_runner import (
    collect_all_observations,
)
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.scanner import Scanner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="Hash-bound reviewer label fixture")
    parser.add_argument("--starsector-path", type=Path, required=True)
    parser.add_argument("--heuristic-set-a", default="baseline_0.7")
    parser.add_argument("--heuristic-set-b", required=True)
    parser.add_argument("--all-installed-mods", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    fixture_id, labels = load_calibration_labels(args.fixture)
    scan = Scanner(args.starsector_path, include_disabled_mods=args.all_installed_mods).scan()
    registry = Registry.from_scan(scan)

    run_a = collect_all_observations(labels, scan, registry, args.heuristic_set_a)
    report_a = evaluate_calibration(fixture_id, labels, run_a.observations, args.heuristic_set_a)
    run_b = collect_all_observations(labels, scan, registry, args.heuristic_set_b)
    report_b = evaluate_calibration(fixture_id, labels, run_b.observations, args.heuristic_set_b)
    diff = compare_calibration_reports(report_a, report_b)

    payload = {
        "report_a": asdict(report_a),
        "report_b": asdict(report_b),
        "diagnostics_a": list(run_a.diagnostics),
        "diagnostics_b": list(run_b.diagnostics),
        "diff": diff,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(
        f"Compared {args.heuristic_set_a} ({report_a.matched} match/{report_a.mismatched} mismatch) vs "
        f"{args.heuristic_set_b} ({report_b.matched} match/{report_b.mismatched} mismatch): "
        f"{len(diff['changed_labels'])} label(s) changed status. Wrote {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
