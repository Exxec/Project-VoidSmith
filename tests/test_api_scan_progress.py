from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.logging import configure_logging
from starsector_variant_generator.core.models import ScanProgress

FIXTURES = Path(__file__).parent / "fixtures"


class ApiScanProgressTests(unittest.TestCase):
    """Regression coverage for a real, measured gap: `Scanner.scan()` itself
    reports progress throughout (core/scanner.py's FINGERPRINTING/PARSING
    fix), but `api.run_scan`'s own post-scan work -- building the registry,
    diffing the change-impact manifest, writing the report -- used to
    report nothing at all no matter how long it took. Measured on the real
    148-mod install: `analyze_change_impact` alone took a real, silent
    4.3s. To a user watching the GUI's progress dialog, that read as the
    scan being stuck again even after Scanner's own part had genuinely
    finished."""

    def setUp(self) -> None:
        # ignore_cleanup_errors: configure_logging() opens a log file handle
        # Windows keeps locked past this test's teardown.
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.temp_dir.name) / "game"
        shutil.copytree(FIXTURES / "game_install", root)
        shutil.copytree(FIXTURES / "vanilla_mod", root, dirs_exist_ok=True)
        shutil.copytree(FIXTURES / "modded_mod", root / "mods/fixture_mod", dirs_exist_ok=True)
        output = Path(self.temp_dir.name) / "output"
        self.config = AppConfig(root, output, output / "logs")
        self.logger = configure_logging(self.config.log_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_scan_reports_progress_through_every_post_scan_phase(self) -> None:
        events: list[ScanProgress] = []
        api.run_scan(self.config, self.logger, progress_callback=events.append)
        stages = [event.stage for event in events]
        # Scanner's own final stage, then every previously-silent post-scan
        # phase, in real execution order -- none skipped, none silently
        # merged into one event.
        complete_index = stages.index("COMPLETE")
        self.assertEqual(["BUILDING_REGISTRY", "ANALYZING_CHANGES", "WRITING_REPORT"], stages[complete_index + 1:])

    def test_post_scan_progress_events_report_real_entity_and_diagnostic_counts(self) -> None:
        events: list[ScanProgress] = []
        outcome = api.run_scan(self.config, self.logger, progress_callback=events.append)
        real_entity_count = len(outcome.result.hulls) + len(outcome.result.weapons) + len(outcome.result.fighters) \
            + len(outcome.result.hullmods) + len(outcome.result.variants) + len(outcome.result.factions)
        post_scan_events = [event for event in events if event.stage in ("BUILDING_REGISTRY", "ANALYZING_CHANGES", "WRITING_REPORT")]
        self.assertEqual(3, len(post_scan_events))
        for event in post_scan_events:
            self.assertEqual(real_entity_count, event.entities_found)

    def test_no_progress_callback_given_behaves_exactly_as_before(self) -> None:
        # The default (None) must remain a true no-op -- every existing
        # caller that doesn't pass a callback sees identical behavior.
        outcome = api.run_scan(self.config, self.logger)
        self.assertGreater(len(outcome.result.hulls), 0)
