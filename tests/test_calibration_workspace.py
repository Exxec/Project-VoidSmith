from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starsector_variant_generator.analysis.calibration_workspace import evaluate_local_workspace
from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.core.registry import Registry


class CalibrationWorkspaceTests(unittest.TestCase):
    def test_delegates_to_existing_observers_without_writing_or_tuning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "labels.json"
            fixture.write_text(json.dumps({"schema_version": "calibration-labels-0.1", "fixture_id": "local", "labels": [{"entity_key": "hull:synthetic", "entity_hash": "hash", "label": "label", "expected": "TANK"}]}), encoding="utf-8")
            scan = ScanResult(); registry = Registry.from_scan(scan)
            with patch("starsector_variant_generator.analysis.calibration_workspace.collect_all_observations") as collect:
                collect.return_value.observations = {"hull:synthetic": {"entity_hash": "hash", "actual": "TANK"}}
                collect.return_value.diagnostics = ("observer evidence",)
                result = evaluate_local_workspace(fixture, scan, registry, "baseline_0.7")
            self.assertEqual((1, 0, ("observer evidence",)), (result.report.matched, result.report.mismatched, result.diagnostics))
            self.assertEqual([fixture], list(Path(temp).iterdir()))
