"""Local-only facade for the existing hash-bound calibration workflow."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from starsector_variant_generator.analysis.calibration import CalibrationReport, evaluate_calibration, load_calibration_labels
from starsector_variant_generator.analysis.calibration_runner import collect_all_observations
from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class CalibrationWorkspaceResult:
    fixture: Path
    report: CalibrationReport
    diagnostics: tuple[str, ...]


def evaluate_local_workspace(fixture: Path, scan: ScanResult, registry: Registry, heuristic_set: str) -> CalibrationWorkspaceResult:
    """Evaluate reviewer labels against an already-loaded, read-only scan.

    This deliberately neither writes a report nor updates labels or heuristic
    values. Callers own optional output persistence below a configured output
    directory.
    """
    fixture = fixture.resolve()
    fixture_id, labels = load_calibration_labels(fixture)
    run = collect_all_observations(labels, scan, registry, heuristic_set)
    return CalibrationWorkspaceResult(fixture, evaluate_calibration(fixture_id, labels, run.observations, heuristic_set), tuple(run.diagnostics))
