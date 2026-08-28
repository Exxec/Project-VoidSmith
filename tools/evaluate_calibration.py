"""Evaluate a local reviewer-label calibration fixture without source data."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from starsector_variant_generator.analysis.calibration import (
    evaluate_calibration,
    load_calibration_labels,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("observations", type=Path, help="Local normalized observation JSON keyed by entity_key")
    parser.add_argument("--heuristic-set", default="baseline_0.7")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture_id, labels = load_calibration_labels(args.fixture)
    observations = json.loads(args.observations.read_text(encoding="utf-8"))
    if not isinstance(observations, dict):
        raise SystemExit("observations must be a JSON object keyed by entity_key")
    report = evaluate_calibration(fixture_id, labels, observations, args.heuristic_set)
    text = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if report.mismatched == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
