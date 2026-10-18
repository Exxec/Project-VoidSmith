"""Locate scan parse failures in their source files (docs/AUTOMATION_PLAN.md V1.3).

The scanner already records a free-text message per unreadable data file. For the two syntax categories that need hand repair
(`MALFORMED_OR_CONCATENATED_DATA`, `MALFORMED_VALUE`, see `output/diagnostic_summary.py`) this module adds where to look:

- the parser's own line, column and character offset (these refer to the text *after* the relaxed-JSON normalisation, which removes
  block comments, so they can sit a few lines away from the raw file);
- the last good token the parser accepted before the failure, taken from that same normalised text;
- a structural pass over the RAW file (string- and comment-aware) that finds where bracket depth first goes wrong: an extra
  closer, a closer of the wrong kind, a second top-level value after the first one closed (concatenated objects), or an opener
  that is never closed.

Read-only: files are read with a size cap, never written. VoidSmith does not repair mod files; the hint says what to look at.
Nothing here interprets game mechanics, and a file that cannot be read stays reported with `structure_issue` `UNREADABLE`.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.output.diagnostic_summary import _error_category
from starsector_variant_generator.parsers.common import _relaxed_json

LOCATED_CATEGORIES = frozenset({"MALFORMED_OR_CONCATENATED_DATA", "MALFORMED_VALUE"})
MAX_READ_BYTES = 4 * 1024 * 1024
_MESSAGE_RE = re.compile(r"^(?P<path>.+?): (?P<reason>[^:]+): line (?P<line>\d+) column (?P<column>\d+) \(char (?P<char>\d+)\)\s*$")
_OPENERS = {"{": "}", "[": "]"}
_CLOSERS = {"}": "{", "]": "["}
_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|[{}\[\],:]|[^\s{}\[\],:"\']+')


@dataclass(frozen=True)
class StructureProblem:
    issue: str  # EXTRA_CLOSER | MISMATCHED_CLOSER | CONCATENATED_VALUES | UNCLOSED_OPENER | NONE
    line: int | None
    column: int | None
    detail: str


@dataclass(frozen=True)
class ParseFailure:
    path: str
    category: str
    parser_reason: str
    parser_line: int | None
    parser_column: int | None
    parser_char: int | None
    last_good_token: str | None
    structure_issue: str
    structure_line: int | None
    structure_column: int | None
    structure_detail: str
    hint: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def scan_structure(raw: str) -> StructureProblem:
    """Find the first place bracket depth goes wrong in raw relaxed-JSON text (strings and comments are skipped)."""
    stack: list[tuple[str, int, int]] = []
    closed_top_level_at: tuple[int, int] | None = None
    line, column, index, length = 1, 0, 0, len(raw)
    while index < length:
        char = raw[index]
        column += 1
        if char == "\n":
            line, column = line + 1, 0
        elif char in "\"'":
            quote, index, start = char, index + 1, (line, column)
            while index < length and raw[index] != quote:
                if raw[index] == "\\":
                    index += 1
                elif raw[index] == "\n":
                    line, column = line + 1, 0
                index += 1
            if closed_top_level_at is not None and not stack:
                return StructureProblem("CONCATENATED_VALUES", start[0], start[1], f"A second top-level value starts after the first closed at line {closed_top_level_at[0]}.")
        elif char == "#" or raw.startswith("//", index):
            end = raw.find("\n", index)
            index = length if end == -1 else end - 1
        elif raw.startswith("/*", index):
            end = raw.find("*/", index + 2)
            block = raw[index:length if end == -1 else end + 2]
            lines_inside = block.count("\n")
            if lines_inside:
                line, column = line + lines_inside, len(block) - block.rfind("\n") - 1
            index = length if end == -1 else end + 1
        elif char in _OPENERS:
            if closed_top_level_at is not None and not stack:
                return StructureProblem("CONCATENATED_VALUES", line, column, f"A second top-level value starts after the first closed at line {closed_top_level_at[0]}.")
            stack.append((char, line, column))
        elif char in _CLOSERS:
            if not stack:
                return StructureProblem("EXTRA_CLOSER", line, column, f"'{char}' closes nothing: bracket depth would go below zero.")
            opener, open_line, _open_column = stack.pop()
            if opener != _CLOSERS[char]:
                return StructureProblem("MISMATCHED_CLOSER", line, column, f"'{char}' does not match the '{opener}' opened at line {open_line}.")
            if not stack:
                closed_top_level_at = (line, column)
        elif not char.isspace() and char != "," and closed_top_level_at is not None and not stack:
            return StructureProblem("CONCATENATED_VALUES", line, column, f"Content follows the top-level value that closed at line {closed_top_level_at[0]}.")
        index += 1
    if stack:
        opener, open_line, open_column = stack[-1]
        return StructureProblem("UNCLOSED_OPENER", open_line, open_column, f"'{opener}' opened here is never closed ({len(stack)} opener(s) open at end of file).")
    return StructureProblem("NONE", None, None, "Brackets balance; the fault is inside a value, not in the nesting.")


def last_good_token(text: str, char_offset: int | None) -> str | None:
    """The last complete token that ends at or before the parser's failing character offset."""
    if char_offset is None:
        return None
    last: str | None = None
    for match in _TOKEN_RE.finditer(text[:char_offset]):
        last = match.group(0)
    if last is None:
        return None
    return last if len(last) <= 60 else last[:57] + "..."


_HINTS = {
    "CONCATENATED_VALUES": "Two top-level values in one file (often two objects pasted together or a stray closing brace); look at the structure line.",
    "EXTRA_CLOSER": "A closing bracket with nothing open; remove it or find the missing opener above it.",
    "MISMATCHED_CLOSER": "A closing bracket of the wrong kind; check the nesting at and above the structure line.",
    "UNCLOSED_OPENER": "An opening bracket is never closed; check from the structure line to the end of the file.",
    "NONE": "Nesting is balanced; check the value at the parser position (a missing value, a stray comma or an unquoted token).",
    "UNREADABLE": "The file could not be read for a structural check.",
}


def _read_raw(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_READ_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    # Path.read_text (used by the parser) applies universal newlines; mirror it so the parser's offsets line up.
    return re.sub(r"\r\n?", "\n", text)


def locate_failure(message: str) -> ParseFailure | None:
    """Locate one scan error message, or None when it is not a located-category parse error."""
    category = _error_category(message)
    if category not in LOCATED_CATEGORIES:
        return None
    match = _MESSAGE_RE.match(message)
    if match is None:
        return None
    path = Path(match.group("path"))
    char_offset = int(match.group("char"))
    raw = _read_raw(path)
    if raw is None:
        problem, token = StructureProblem("UNREADABLE", None, None, "File missing, too large or unreadable."), None
    else:
        problem = scan_structure(raw)
        try:
            normalised = _relaxed_json(raw)
        except ValueError:
            normalised = raw
        token = last_good_token(normalised, char_offset)
    return ParseFailure(
        path=str(path), category=category, parser_reason=match.group("reason"),
        parser_line=int(match.group("line")), parser_column=int(match.group("column")), parser_char=char_offset,
        last_good_token=token, structure_issue=problem.issue, structure_line=problem.line, structure_column=problem.column,
        structure_detail=problem.detail, hint=_HINTS[problem.issue], message=message,
    )


def locate_parse_failures(scan: ScanResult) -> list[ParseFailure]:
    """Every located-category parse error of a scan, in scan order."""
    failures = (locate_failure(message) for message in scan.errors)
    return [failure for failure in failures if failure is not None]


def format_failure_line(failure: ParseFailure) -> str:
    where = f"parser line {failure.parser_line} col {failure.parser_column}"
    if failure.structure_line is not None:
        where += f"; structure {failure.structure_issue} at raw line {failure.structure_line}"
    token = f"; after token {failure.last_good_token}" if failure.last_good_token else ""
    return f"{failure.path}: {failure.parser_reason} ({where}{token})"
