"""Deterministic JSON writer for read-only ChangeImpactReport audit data."""
from __future__ import annotations
from dataclasses import asdict
from collections import Counter
import json
from pathlib import Path
from starsector_variant_generator.analysis.change_impact import ChangeImpactReport

def write_change_impact_report(report: ChangeImpactReport, path: Path) -> None:
    """Write only under a caller-selected output path; never game/mod data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")


def compact_change_impact(report: ChangeImpactReport) -> dict[str, object]:
    """Return a source-content-free change overview for diagnostic scans."""
    return {
        "schema_version": report.schema_version,
        "changes_by_status": dict(sorted(Counter(change.status for change in report.changes).items())),
        "impact_count": len(report.impacts),
        "warning_count": len(report.warnings),
    }


def write_compact_change_impact_report(report: ChangeImpactReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compact_change_impact(report), indent=2, sort_keys=True), encoding="utf-8")
