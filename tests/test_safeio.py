from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from starsector_variant_generator.core import safeio
from starsector_variant_generator.core.safeio import (
    UnsafePathError,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    safe_rmtree,
    safe_unlink,
)
from tests.link_support import make_link


class AtomicWriteTests(unittest.TestCase):
    def test_text_json_and_bytes_land_complete_and_create_parent_folders(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_write_text(root / "a" / "t.txt", "hello", newline="")
            atomic_write_json(root / "j.json", {"k": [1, 2]})
            atomic_write_bytes(root / "b.bin", b"\x00\x01")
            self.assertEqual("hello", (root / "a" / "t.txt").read_text(encoding="utf-8"))
            self.assertEqual({"k": [1, 2]}, json.loads((root / "j.json").read_text(encoding="utf-8")))
            self.assertEqual(b"\x00\x01", (root / "b.bin").read_bytes())

    def test_a_failed_swap_keeps_the_old_file_and_leaves_no_temp_file(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "keep.txt"
            target.write_text("old", encoding="utf-8")
            with mock.patch.object(safeio.os, "replace", side_effect=OSError("boom")), self.assertRaises(OSError):
                atomic_write_text(target, "new")
            self.assertEqual("old", target.read_text(encoding="utf-8"))
            self.assertEqual(["keep.txt"], sorted(p.name for p in Path(tmp).iterdir()))

    def test_it_replaces_an_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "f.txt"
            target.write_text("old", encoding="utf-8")
            atomic_write_text(target, "new", newline="")
            self.assertEqual("new", target.read_text(encoding="utf-8"))


class GuardedDeleteTests(unittest.TestCase):
    def test_a_tree_inside_the_root_is_removed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "t" / "d").mkdir(parents=True)
            (root / "t" / "d" / "f").write_text("x", encoding="utf-8")
            self.assertTrue(safe_rmtree(root / "t", [root]))
            self.assertFalse((root / "t").exists())

    def test_the_root_itself_and_outside_paths_are_refused(self) -> None:
        with TemporaryDirectory() as tmp, TemporaryDirectory() as other:
            root = Path(tmp).resolve()
            with self.assertRaises(UnsafePathError):
                safe_rmtree(root, [root])
            with self.assertRaises(UnsafePathError):
                safe_rmtree(other, [root])
            self.assertTrue(Path(other).exists())

    def test_a_missing_path_is_a_quiet_false_unless_asked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.assertFalse(safe_rmtree(root / "gone", [root]))
            with self.assertRaises(FileNotFoundError):
                safe_rmtree(root / "gone", [root], missing_ok=False)

    def test_a_link_inside_the_tree_is_removed_as_a_link_and_its_target_survives(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            outside = root / "outside"
            outside.mkdir()
            (outside / "keep.txt").write_text("keep", encoding="utf-8")
            (root / "tree").mkdir()
            if not make_link(root / "tree" / "ln", outside):
                self.skipTest("links cannot be created here")
            safe_rmtree(root / "tree", [root])
            self.assertFalse((root / "tree").exists())
            self.assertTrue((outside / "keep.txt").exists())

    def test_a_link_leading_outside_the_roots_is_removed_as_a_link_only(self) -> None:
        with TemporaryDirectory() as tmp, TemporaryDirectory() as other:
            root = Path(tmp).resolve()
            (Path(other) / "keep.txt").write_text("keep", encoding="utf-8")
            if not make_link(root / "ln", Path(other)):
                self.skipTest("links cannot be created here")
            safe_rmtree(root / "ln", [root])
            self.assertFalse((root / "ln").exists())
            self.assertTrue((Path(other) / "keep.txt").exists())

    def test_unlink_refuses_folders_and_outside_files(self) -> None:
        with TemporaryDirectory() as tmp, TemporaryDirectory() as other:
            root = Path(tmp).resolve()
            (root / "d").mkdir()
            (root / "f").write_text("x", encoding="utf-8")
            (Path(other) / "o").write_text("x", encoding="utf-8")
            with self.assertRaises(UnsafePathError):
                safe_unlink(root / "d", [root])
            with self.assertRaises(UnsafePathError):
                safe_unlink(Path(other) / "o", [root])
            self.assertTrue(safe_unlink(root / "f", [root]))
            self.assertEqual(os.listdir(root), ["d"])


def short_alias(path: Path) -> Path | None:
    """The Windows 8.3 short-name form of an existing path, or None where short names do not exist or are disabled."""
    if os.name != "nt":
        return None
    import ctypes
    buffer = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, 1024):
        return None
    alias = Path(buffer.value)
    return alias if str(alias).lower() != str(path).lower() else None


class ShortNameAliasTests(unittest.TestCase):
    def long_named_root(self, tmp: str) -> Path:
        root = Path(tmp).resolve() / "a rather long folder name"
        (root / "child dir").mkdir(parents=True)
        return root

    def test_an_8_3_alias_of_the_allowed_root_is_accepted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self.long_named_root(tmp)
            alias = short_alias(root)
            if alias is None:
                self.skipTest("8.3 short names are unavailable here")
            (root / "child dir" / "run.partial.jsonl").write_text("x", encoding="utf-8")
            self.assertTrue(safe_unlink(alias / "child dir" / "run.partial.jsonl", [root]))
            self.assertTrue(safe_rmtree(alias / "child dir", [root]))
            self.assertFalse((root / "child dir").exists())

    def test_an_alias_given_as_the_root_and_a_missing_path_inside_it_are_accepted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self.long_named_root(tmp)
            alias = short_alias(root)
            if alias is None:
                self.skipTest("8.3 short names are unavailable here")
            self.assertFalse(safe_rmtree(root / "never created", [alias]))
            self.assertTrue(safe_rmtree(root / "child dir", [alias]))

    def test_the_alias_does_not_let_a_sibling_folder_in(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self.long_named_root(tmp)
            sibling = Path(tmp).resolve() / "another folder"
            sibling.mkdir()
            alias = short_alias(root)
            if alias is None:
                self.skipTest("8.3 short names are unavailable here")
            with self.assertRaises(UnsafePathError):
                safe_rmtree(sibling, [alias])
            self.assertTrue(sibling.exists())

    def test_deleting_through_a_link_that_leaves_the_root_is_still_refused(self) -> None:
        with TemporaryDirectory() as tmp, TemporaryDirectory() as other:
            root = Path(tmp).resolve()
            (Path(other) / "sub").mkdir()
            (Path(other) / "sub" / "keep.txt").write_text("keep", encoding="utf-8")
            if not make_link(root / "ln", Path(other)):
                self.skipTest("links cannot be created here")
            with self.assertRaises(UnsafePathError):
                safe_rmtree(root / "ln" / "sub", [root])
            with self.assertRaises(UnsafePathError):
                safe_unlink(root / "ln" / "sub" / "keep.txt", [root])
            self.assertTrue((Path(other) / "sub" / "keep.txt").exists())


if __name__ == "__main__":
    unittest.main()
