"""Evaluate reviewer labels directly from a current, read-only local scan.

The fixture and output are local user artifacts.  This tool does not write
into the Starsector installation or a mod directory, and it never creates or
modifies reviewer labels.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from starsector_variant_generator.analysis.calibration import (
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
    parser.add_argument("--heuristic-set", default="baseline_0.7")
    parser.add_argument("--all-installed-mods", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    fixture_id, labels = load_calibration_labels(args.fixture)
    scan = Scanner(args.starsector_path, include_disabled_mods=args.all_installed_mods).scan()
    # `collect_all_observations` dispatches each label to whichever real
    # observer its entity_key scheme names (`hull:` build/equipment/top-set
    # labels via `collect_build_observations`; `faction:`/`scenario:` labels
    # via `collect_faction_and_scenario_observations`, ROADMAP.md Phase 39)
    # -- a strict superset of what this tool evaluated before, so an
    # existing BUILD_EXPECTATION-only fixture is scored identically.
    run = collect_all_observations(labels, scan, Registry.from_scan(scan), args.heuristic_set)
    report = evaluate_calibration(fixture_id, labels, run.observations, args.heuristic_set)
    payload = {
        "report": asdict(report),
        "diagnostics": list(run.diagnostics),
        "scan_errors": list(scan.errors),
        "scan_warnings": list(scan.warnings),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"Calibration: {report.matched} match, {report.mismatched} mismatch, "
        f"{report.stale} stale, {report.unsupported} unsupported. Wrote {args.output}"
    )
    # Mismatches are useful review information, not a tool failure.  A bad
    # fixture/path remains an exception above and therefore fails loudly.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
