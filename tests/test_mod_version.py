from __future__ import annotations

import unittest

from starsector_variant_generator.core.mod_version import normalize_mod_version


class NormalizeModVersionTests(unittest.TestCase):
    def test_object_with_all_parts_joins_as_dotted_version(self) -> None:
        self.assertEqual("1.7.1", normalize_mod_version({"major": 1, "minor": 7, "patch": 1}))

    def test_object_with_string_parts_joins_as_dotted_version(self) -> None:
        self.assertEqual("2.0.3", normalize_mod_version({"major": "2", "minor": " 0 ", "patch": "3"}))

    def test_object_with_mixed_number_and_string_parts(self) -> None:
        self.assertEqual("3.10.0", normalize_mod_version({"major": 3, "minor": "10"}))

    def test_object_with_missing_parts_counts_them_as_zero(self) -> None:
        self.assertEqual("1.7.0", normalize_mod_version({"major": 1, "minor": 7}))
        self.assertEqual("4.0.0", normalize_mod_version({"major": 4}))

    def test_object_with_unusable_part_values_counts_them_as_zero(self) -> None:
        self.assertEqual("1.0.0", normalize_mod_version({"major": 1, "minor": None, "patch": True}))
        self.assertEqual("1.0.2", normalize_mod_version({"major": 1, "minor": "", "patch": 2}))

    def test_object_without_any_usable_part_is_absent(self) -> None:
        self.assertIsNone(normalize_mod_version({}))
        self.assertIsNone(normalize_mod_version({"build": 9}))
        self.assertIsNone(normalize_mod_version({"major": None, "minor": "  "}))

    def test_string_version_is_returned_trimmed(self) -> None:
        self.assertEqual("1.7.1", normalize_mod_version("  1.7.1 "))
        self.assertIsNone(normalize_mod_version("   "))

    def test_number_version_is_returned_as_text(self) -> None:
        self.assertEqual("2", normalize_mod_version(2))
        self.assertEqual("1.5", normalize_mod_version(1.5))

    def test_absent_version_is_none(self) -> None:
        self.assertIsNone(normalize_mod_version(None))

    def test_list_version_keeps_stable_json_text(self) -> None:
        self.assertEqual("[1,2]", normalize_mod_version([1, 2]))

    def test_boolean_version_is_not_mistaken_for_a_number(self) -> None:
        self.assertEqual("true", normalize_mod_version(True))


if __name__ == "__main__":
    unittest.main()
