from __future__ import annotations

import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.core.config import AppConfig

FIXTURES = Path(__file__).parent / "fixtures"


class ScanReportParseFailureTests(unittest.TestCase):
    def test_the_scan_report_lists_a_malformed_variant_with_its_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            shutil.copytree(FIXTURES / "game_install", root)
            shutil.copytree(FIXTURES / "vanilla_mod", root, dirs_exist_ok=True)
            shutil.copytree(FIXTURES / "modded_mod", root / "mods/fixture_mod", dirs_exist_ok=True)
            bad = root / "mods/fixture_mod/data/variants/broken_fixture.variant"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text('{"variantId": "a"}\n{"variantId": "b"}\n', encoding="utf-8")
            out = Path(tmp) / "out"
            config = AppConfig(root, out, out / "logs")
            outcome = api.run_scan(config, logging.getLogger("test-parse-failures"))
            failures = outcome.report["parse_failures"]
            located = [f for f in failures if f["path"].endswith("broken_fixture.variant")]
            self.assertEqual(1, len(located))
            self.assertEqual("CONCATENATED_VALUES", located[0]["structure_issue"])
            self.assertEqual(2, located[0]["structure_line"])


if __name__ == "__main__":
    unittest.main()
