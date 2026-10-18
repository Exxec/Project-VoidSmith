from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starsector_variant_generator.analysis.parse_diagnostics import (
    format_failure_line,
    last_good_token,
    locate_failure,
    locate_parse_failures,
    scan_structure,
)
from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.parsers.common import json_file


def failure_message(path: Path) -> str:
    try:
        json_file(path)
    except ValueError as exc:
        return f"{path}: {exc}"
    raise AssertionError("expected the synthetic file to fail parsing")


class ScanStructureTests(unittest.TestCase):
    def test_balanced_text_has_no_structural_problem(self) -> None:
        self.assertEqual("NONE", scan_structure('{"a": [1, 2], "b": {"c": "}"}}').issue)

    def test_brackets_inside_strings_and_comments_are_ignored(self) -> None:
        raw = '{\n  # } stray\n  "a": "]]",\n  /* { */ "b": 1\n}\n'
        self.assertEqual("NONE", scan_structure(raw).issue)

    def test_a_second_top_level_object_is_reported_at_its_line(self) -> None:
        problem = scan_structure('{"a": 1}\n\n{"b": 2}\n')
        self.assertEqual(("CONCATENATED_VALUES", 3), (problem.issue, problem.line))

    def test_an_extra_closer_is_reported_at_its_line(self) -> None:
        problem = scan_structure('{\n"a": 1\n}\n}\n')
        self.assertEqual(("EXTRA_CLOSER", 4), (problem.issue, problem.line))

    def test_a_wrong_kind_of_closer_names_the_opener_line(self) -> None:
        problem = scan_structure('{\n"a": [1, 2}\n')
        self.assertEqual(("MISMATCHED_CLOSER", 2), (problem.issue, problem.line))
        self.assertIn("'['", problem.detail)

    def test_an_unclosed_opener_reports_the_innermost_open_line(self) -> None:
        problem = scan_structure('{\n"a": {\n"b": 1\n')
        self.assertEqual(("UNCLOSED_OPENER", 2), (problem.issue, problem.line))


class LocateFailureTests(unittest.TestCase):
    def test_concatenated_objects_carry_parser_position_token_and_structure_line(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.skin"
            path.write_text('{\n  "id": "a",\n  "n": 1\n}\n{\n  "id": "b"\n}\n', encoding="utf-8")
            failure = locate_failure(failure_message(path))
            assert failure is not None
            self.assertEqual("MALFORMED_OR_CONCATENATED_DATA", failure.category)
            self.assertEqual("Extra data", failure.parser_reason)
            self.assertEqual(5, failure.parser_line)
            self.assertEqual("}", failure.last_good_token)
            self.assertEqual(("CONCATENATED_VALUES", 5), (failure.structure_issue, failure.structure_line))
            self.assertIn("x.skin", format_failure_line(failure))

    def test_a_missing_value_is_a_value_fault_with_balanced_nesting(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "y.ship"
            path.write_text('{\n  "id": ,\n  "n": 1\n}\n', encoding="utf-8")
            failure = locate_failure(failure_message(path))
            assert failure is not None
            self.assertEqual("MALFORMED_VALUE", failure.category)
            self.assertEqual(("NONE", None), (failure.structure_issue, failure.structure_line))
            self.assertEqual(":", failure.last_good_token)

    def test_other_error_kinds_and_unparsable_messages_are_not_located(self) -> None:
        self.assertIsNone(locate_failure("C:\\m\\a.csv: 'utf-8' codec can't decode byte 0xff"))
        self.assertIsNone(locate_failure("no location in this message"))

    def test_a_vanished_file_is_reported_unreadable_not_a_crash(self) -> None:
        message = "gone.skin: Extra data: line 2 column 1 (char 9)"
        failure = locate_failure(message)
        assert failure is not None
        self.assertEqual("UNREADABLE", failure.structure_issue)
        self.assertIsNone(failure.last_good_token)

    def test_locating_a_scan_keeps_scan_order_and_skips_other_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.skin"
            first.write_text('{"a": 1}\n{"b": 2}', encoding="utf-8")
            scan = ScanResult(errors=["x: 'utf-8' codec can't decode byte", failure_message(first)])
            located = locate_parse_failures(scan)
            self.assertEqual([str(first)], [item.path for item in located])

    def test_last_good_token_is_none_without_an_offset_or_tokens(self) -> None:
        self.assertIsNone(last_good_token("{}", None))
        self.assertIsNone(last_good_token("   ", 3))


if __name__ == "__main__":
    unittest.main()
