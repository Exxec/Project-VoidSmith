from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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


def _zip_bytes(entries: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


class ArchiveLimitTests(unittest.TestCase):
    def _drop(self, tmp: str, payload: bytes) -> tuple[object, Path]:
        archive = Path(tmp) / "limited.zip"
        archive.write_bytes(payload)
        cache = Path(tmp) / "cache"
        return resolve_dropped_mod(archive, cache), cache

    def test_a_high_compression_ratio_entry_is_refused_before_anything_is_extracted(self) -> None:
        payload = _zip_bytes({"mod_info.json": b'{"id": "x"}', "pad.bin": bytes(8 * 1024 * 1024)})
        with TemporaryDirectory() as tmp:
            result, cache = self._drop(tmp, payload)
            self.assertIsNone(result.mod_root)
            self.assertIn("compression ratio", result.error or "")
            self.assertFalse((cache / "limited" / "mod_info.json").exists())

    def test_an_entry_over_the_per_entry_cap_is_refused(self) -> None:
        import os

        from starsector_variant_generator.core import mod_import
        payload = _zip_bytes({"mod_info.json": b'{"id": "x"}', "big.bin": os.urandom(4096)}, zipfile.ZIP_STORED)
        with TemporaryDirectory() as tmp, mock.patch.object(mod_import, "MAX_ENTRY_BYTES", 1024):
            result, cache = self._drop(tmp, payload)
            self.assertIsNone(result.mod_root)
            self.assertIn("uncompressed", result.error or "")
            self.assertFalse((cache / "limited" / "mod_info.json").exists())

    def test_a_total_over_the_cap_is_refused(self) -> None:
        from starsector_variant_generator.core import mod_import
        payload = _zip_bytes({"a.txt": b"a" * 600, "b.txt": b"b" * 600, "mod_info.json": b'{"id": "x"}'}, zipfile.ZIP_STORED)
        with TemporaryDirectory() as tmp, mock.patch.object(mod_import, "MAX_TOTAL_BYTES", 1000):
            result, _cache = self._drop(tmp, payload)
            self.assertIn("total limit", result.error or "")

    def test_an_archive_within_the_limits_still_extracts(self) -> None:
        payload = _zip_bytes({"mod_info.json": b'{"id": "fine"}', "data/notes.txt": b"x" * 5000})
        with TemporaryDirectory() as tmp:
            result, _cache = self._drop(tmp, payload)
            self.assertIsNone(result.error)
            self.assertEqual("fine", result.mod_id)

    def test_a_declared_size_that_lies_is_caught_while_reading(self) -> None:
        from starsector_variant_generator.core import mod_import
        payload = _zip_bytes({"mod_info.json": b'{"id": "x"}', "grow.bin": b"z" * 5000}, zipfile.ZIP_STORED)
        with TemporaryDirectory() as tmp, mock.patch.object(mod_import, "check_archive_limits"), \
                mock.patch.object(mod_import, "MAX_ENTRY_BYTES", 1000):
            result, _cache = self._drop(tmp, payload)
            self.assertIsNone(result.mod_root)
            self.assertIn("while reading", result.error or "")

    def test_a_symlink_entry_is_refused(self) -> None:
        import io
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "target")
        with TemporaryDirectory() as tmp:
            result, _cache = self._drop(tmp, buffer.getvalue())
            self.assertIn("symbolic link", result.error or "")

    def test_an_extraction_target_that_is_a_link_is_refused_and_its_target_kept(self) -> None:
        from tests.link_support import make_link
        payload = _zip_bytes({"mod_info.json": b'{"id": "x"}'})
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            cache.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "keep.txt").write_text("keep", encoding="utf-8")
            if not make_link(cache / "limited", outside):
                self.skipTest("links cannot be created here")
            archive = Path(tmp) / "limited.zip"
            archive.write_bytes(payload)
            result = resolve_dropped_mod(archive, cache)
            self.assertIsNone(result.mod_root)
            self.assertIn("link", result.error or "")
            self.assertTrue((outside / "keep.txt").exists())
