"""Heuristic-set proposal report from APPROVED calibration rows only (docs/AUTOMATION_PLAN.md V2.4).

Measures every registered heuristic set against the approved rows of a resolved review sheet, reports match and mismatch counts
and the rows whose status moves between sets, and writes a CANDIDATE stub for a person to review. It never changes a registered
set, never registers one, and never edits a value: the candidate copies the best-measured set's values unchanged under a new
identifier with a rationale stub (AGENTS.md section 8, "Heuristics are never tuned automatically"). Output goes under generated/.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from starsector_variant_generator.analysis.calibration import (
    CalibrationExpectationKind,
    CalibrationLabel,
    CalibrationReport,
    CalibrationStrength,
    compare_calibration_reports,
    evaluate_calibration,
)
from starsector_variant_generator.analysis.calibration_review import (
    APPROVED_STATUS,
    hull_key,
    read_sheet,
    require_under,
)
from starsector_variant_generator.analysis.calibration_runner import collect_all_observations
from starsector_variant_generator.core.heuristics import REGISTRY, get_heuristic_set
from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.safeio import atomic_write_json

HINTS_COLUMN = "normalized_archetype_hints"
FIXTURE_ID = "approved-review-rows"


def labels_from_approved_rows(sheet: Path, scan: ScanResult, generated_root: Path) -> tuple[tuple[CalibrationLabel, ...], list[dict[str, str]]]:
    """One SOFT build expectation per APPROVED row with a resolved hull and archetype hints; skipped rows are listed with a reason."""
    fields, rows = read_sheet(require_under(sheet, generated_root))
    if HINTS_COLUMN not in fields or "resolved_hull_key" not in fields:
        raise ValueError(f"The sheet needs {HINTS_COLUMN!r} and the resolve columns; run `calibration resolve` first.")
    hulls = {hull_key(hull): hull for hull in scan.hulls}
    labels: list[CalibrationLabel] = []
    skipped: list[dict[str, str]] = []
    for row in rows:
        if row.get("review_status") != APPROVED_STATUS:
            continue
        hull = hulls.get(row.get("resolved_hull_key", ""))
        hints = tuple(hint.strip() for hint in row.get(HINTS_COLUMN, "").split(";") if hint.strip())
        if hull is None or not hull.source_hash or not hints:
            skipped.append({"row_id": row.get("row_id", "?"), "reason": "NOT_IN_SCAN_OR_NO_HASH_OR_NO_HINTS"})
            continue
        labels.append(CalibrationLabel(
            entity_key=hull_key(hull), entity_hash=hull.source_hash, label=f"APPROVED_ROW:{row.get('row_id', '?')}",
            expected=hints[0], expected_any=hints, strength=CalibrationStrength.SOFT_EXPECTATION,
            expectation_kind=CalibrationExpectationKind.BUILD_EXPECTATION, note=f"Approved by {row.get('approved_by', '?')}",
        ))
    return tuple(labels), skipped


def _measure(labels: tuple[CalibrationLabel, ...], scan: ScanResult, registry: Registry, set_id: str) -> CalibrationReport:
    run = collect_all_observations(labels, scan, registry, set_id)
    return evaluate_calibration(FIXTURE_ID, labels, run.observations, set_id)


def _best(reports: dict[str, CalibrationReport]) -> str:
    order = {identifier: index for index, identifier in enumerate(REGISTRY)}
    return min(reports, key=lambda s: (-reports[s].matched, reports[s].mismatched, -order.get(s, 0)))


def propose(
    sheet: Path, scan: ScanResult, registry: Registry, generated_root: Path, output_dir: Path, *,
    set_ids: list[str] | None = None, base_set: str = "baseline_0.7", today: date | None = None,
) -> dict[str, object]:
    """Measure the sets against approved rows; write the report and (when there is evidence) a candidate stub under generated/."""
    destination = require_under(output_dir / "x", generated_root).parent
    labels, skipped = labels_from_approved_rows(sheet, scan, generated_root)
    ids = set_ids or list(REGISTRY)
    for identifier in [*ids, base_set]:
        get_heuristic_set(identifier)  # unknown set: ValueError before any work
    report: dict[str, object] = {"approved_rows_used": len(labels), "skipped_rows": skipped, "sets": {}, "moves": {}, "candidate": None}
    if not labels:
        report["note"] = "No APPROVED rows with a resolved hull and hints; nothing was measured and no candidate was written."
        atomic_write_json(destination / "calibration_proposal.json", report, sort_keys=True)
        return report
    reports = {identifier: _measure(labels, scan, registry, identifier) for identifier in dict.fromkeys([base_set, *ids])}
    report["sets"] = {i: {"matched": r.matched, "mismatched": r.mismatched, "stale": r.stale, "unsupported": r.unsupported} for i, r in reports.items()}
    report["moves"] = {i: compare_calibration_reports(reports[base_set], r)["changed_labels"] for i, r in reports.items() if i != base_set}
    best = _best(reports)
    stamp = (today or date.today()).isoformat()
    candidate = {
        "identifier": f"candidate_{stamp}", "status": "PROPOSED_NOT_REGISTERED", "based_on": best,
        "values": dict(get_heuristic_set(best).values),
        "rationale_stub": (f"TODO (person): {best} matched {reports[best].matched} of {len(labels)} approved rows "
                           f"({reports[best].mismatched} mismatched). Values are an unchanged copy; edit and justify before registering."),
        "registration": "Manual only: add to core/heuristics.py with rationale, docs and regression coverage (AGENTS.md section 8).",
    }
    candidate_path = destination / f"candidate_heuristic_set_{stamp}.json"
    atomic_write_json(candidate_path, candidate, sort_keys=True)
    report["candidate"] = str(candidate_path)
    report["best_measured_set"] = best
    atomic_write_json(destination / "calibration_proposal.json", report, sort_keys=True, default=str)
    return json.loads(json.dumps(report, default=str))
