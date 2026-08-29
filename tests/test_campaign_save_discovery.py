from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starsector_variant_generator import api
from starsector_variant_generator.analysis.campaign_save_discovery import discover_campaign_directory


class CampaignSaveDiscoveryTests(unittest.TestCase):
    def test_requires_an_existing_user_selected_directory(self) -> None:
        with self.assertRaisesRegex(ValueError, "existing directory"):
            discover_campaign_directory(Path("does-not-exist"))

    def test_lists_direct_metadata_without_opening_or_classifying_entries(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "zeta.bin").write_bytes(b"unparsed")
            (root / "Alpha").mkdir()
            (root / "nested").mkdir(); (root / "nested" / "hidden.bin").write_bytes(b"not traversed")
            result = api.run_campaign_save_discovery(root)
        self.assertEqual("DIRECTORY_ENTRIES_FOUND", result.status)
        self.assertEqual(("Alpha", "nested", "zeta.bin"), tuple(item.name for item in result.entries))
        self.assertEqual(("DIRECTORY", "DIRECTORY", "FILE"), tuple(item.kind for item in result.entries))
        self.assertEqual(8, result.entries[-1].bytes)
        self.assertIn("CAMPAIGN_SAVE_UNINSPECTED", result.notes[0])
        self.assertNotIn("hidden.bin", tuple(item.name for item in result.entries))

    def test_empty_directory_is_explicit_not_a_missing_save_claim(self) -> None:
        with TemporaryDirectory() as temporary:
            result = discover_campaign_directory(Path(temporary))
        self.assertEqual("DIRECTORY_EMPTY", result.status)
        self.assertEqual((), result.entries)
        self.assertIn("No save file format", result.notes[1])


if __name__ == "__main__":
    unittest.main()
