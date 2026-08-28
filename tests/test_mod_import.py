from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from starsector_variant_generator.core.mod_import import resolve_dropped_mod


def _write_mod_info(directory: Path, mod_id: str = "dropped_mod", name: str = "Dropped Mod") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "mod_info.json").write_text(json.dumps({"id": mod_id, "name": name}), encoding="utf-8")


class ResolveDroppedFolderTests(unittest.TestCase):
    def test_a_folder_with_mod_info_json_at_its_root_resolves_directly(self) -> None:
        with TemporaryDirectory() as tmp:
            mod_dir = Path(tmp) / "my_mod"
            _write_mod_info(mod_dir)
            result = resolve_dropped_mod(mod_dir, Path(tmp) / "cache")
            self.assertIsNone(result.error)
            self.assertEqual(mod_dir, result.mod_root)
            self.assertEqual("dropped_mod", result.mod_id)
            self.assertEqual("Dropped Mod", result.mod_name)

    def test_a_folder_wrapping_the_mod_one_level_down_is_found(self) -> None:
        with TemporaryDirectory() as tmp:
            outer = Path(tmp) / "extracted"
            inner = outer / "ActualMod"
            _write_mod_info(inner)
            result = resolve_dropped_mod(outer, Path(tmp) / "cache")
            self.assertIsNone(result.error)
            self.assertEqual(inner, result.mod_root)

    def test_multiple_nested_mod_info_files_are_rejected_as_ambiguous(self) -> None:
        with TemporaryDirectory() as tmp:
            outer = Path(tmp) / "extracted"
            _write_mod_info(outer / "ModA", mod_id="mod_a")
            _write_mod_info(outer / "ModB", mod_id="mod_b")
            result = resolve_dropped_mod(outer, Path(tmp) / "cache")
            self.assertIsNone(result.mod_root)
            self.assertIn("Multiple", result.error or "")

    def test_a_folder_with_no_mod_info_json_anywhere_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            plain = Path(tmp) / "not_a_mod"
            plain.mkdir()
            (plain / "readme.txt").write_text("hello", encoding="utf-8")
            result = resolve_dropped_mod(plain, Path(tmp) / "cache")
            self.assertIsNone(result.mod_root)
            self.assertIn("No mod_info.json", result.error or "")

    def test_an_unsupported_file_type_is_rejected_cleanly(self) -> None:
        with TemporaryDirectory() as tmp:
            stray = Path(tmp) / "notes.txt"
            stray.write_text("hello", encoding="utf-8")
            result = resolve_dropped_mod(stray, Path(tmp) / "cache")
            self.assertIsNone(result.mod_root)
            self.assertIn("Unsupported drop", result.error or "")


class ResolveDroppedArchiveTests(unittest.TestCase):
    def test_a_zip_archive_is_extracted_and_resolved(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "cool_mod.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("mod_info.json", json.dumps({"id": "cool_mod", "name": "Cool Mod"}))
                zf.writestr("data/hulls/ship_data.csv", "id,name\n")
            cache = Path(tmp) / "cache"
            result = resolve_dropped_mod(archive, cache)
            self.assertIsNone(result.error)
            self.assertEqual("cool_mod", result.mod_id)
            self.assertTrue((result.mod_root / "data" / "hulls" / "ship_data.csv").is_file())

    def test_a_zip_wrapping_the_mod_in_one_extra_folder_is_resolved(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "wrapped_mod.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("WrappedMod/mod_info.json", json.dumps({"id": "wrapped_mod"}))
            result = resolve_dropped_mod(archive, Path(tmp) / "cache")
            self.assertIsNone(result.error)
            self.assertEqual("wrapped_mod", result.mod_id)
            self.assertEqual("WrappedMod", result.mod_root.name)

    def test_a_malformed_zip_file_is_rejected_cleanly_not_a_crash(self) -> None:
        with TemporaryDirectory() as tmp:
            fake_archive = Path(tmp) / "broken.zip"
            fake_archive.write_bytes(b"not actually a zip file")
            result = resolve_dropped_mod(fake_archive, Path(tmp) / "cache")
            self.assertIsNone(result.mod_root)
            self.assertIn("Could not read", result.error or "")

    def test_a_zip_slip_entry_is_rejected_and_nothing_is_written_outside_the_target(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "malicious.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../../escaped.txt", "should never land here")
            cache = Path(tmp) / "cache"
            result = resolve_dropped_mod(archive, cache)
            self.assertIsNone(result.mod_root)
            self.assertIn("escapes", result.error or "")
            self.assertFalse((Path(tmp) / "escaped.txt").exists())

    def test_re_dropping_an_updated_archive_with_the_same_name_refreshes_the_extraction(self) -> None:
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            archive = Path(tmp) / "evolving_mod.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("mod_info.json", json.dumps({"id": "evolving_mod"}))
                zf.writestr("old_only_file.txt", "v1")
            first = resolve_dropped_mod(archive, cache)
            self.assertTrue((first.mod_root / "old_only_file.txt").is_file())
            archive.unlink()
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("mod_info.json", json.dumps({"id": "evolving_mod"}))
            second = resolve_dropped_mod(archive, cache)
            self.assertEqual(first.mod_root, second.mod_root)
            self.assertFalse((second.mod_root / "old_only_file.txt").exists())


if __name__ == "__main__":
    unittest.main()
