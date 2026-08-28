from __future__ import annotations

import csv
import io
import json
import re
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator


def _relaxed_json(text: str) -> str:
    """Accept comments and trailing commas without changing JSON string content.

    Some Starsector mods use these syntax conveniences. This is a format-level
    compatibility step only; it does not interpret mod mechanics.
    """
    def strip_comments(source: str) -> str:
        output: list[str] = []
        index = 0
        in_string = False
        escaped = False
        while index < len(source):
            char = source[index]
            following = source[index + 1] if index + 1 < len(source) else ""
            if in_string:
                output.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
                output.append(char)
                index += 1
            elif (char == "/" and following == "/") or char == "#":
                index = source.find("\n", index)
                if index == -1:
                    break
                output.append("\n")
                index += 1
            elif char == "/" and following == "*":
                end = source.find("*/", index + 2)
                if end == -1:
                    raise ValueError("Unterminated block comment")
                index = end + 2
            else:
                output.append(char)
                index += 1
        return "".join(output)

    def quote_bare_keys(source: str) -> str:
        output: list[str] = []
        index = 0
        in_string = False
        escaped = False
        expects_key = False
        while index < len(source):
            char = source[index]
            if in_string:
                output.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
                expects_key = False
                output.append(char)
                index += 1
                continue
            if char == "{":
                expects_key = True
            elif char == ",":
                expects_key = True
            elif expects_key and (char.isalpha() or char == "_"):
                end = index + 1
                while end < len(source) and (source[end].isalnum() or source[end] in "_-$"):
                    end += 1
                colon = end
                while colon < len(source) and source[colon].isspace():
                    colon += 1
                if colon < len(source) and source[colon] == ":":
                    output.extend(('"', source[index:end], '"'))
                    index = end
                    expects_key = False
                    continue
                expects_key = False
            elif not char.isspace():
                expects_key = False
            output.append(char)
            index += 1
        return "".join(output)

    def convert_single_quoted_strings(source: str) -> str:
        output: list[str] = []
        index = 0
        in_double = False
        escaped = False
        while index < len(source):
            char = source[index]
            if in_double:
                output.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_double = False
                index += 1
                continue
            if char == '"':
                in_double = True
                output.append(char)
                index += 1
                continue
            if char == "'":
                end = index + 1
                escaped_single = False
                while end < len(source):
                    if source[end] == "'" and not escaped_single:
                        break
                    escaped_single = source[end] == "\\" and not escaped_single
                    if source[end] != "\\":
                        escaped_single = False
                    end += 1
                if end == len(source):
                    raise ValueError("Unterminated single-quoted string")
                value = source[index + 1:end].replace("\\'", "'")
                output.append(json.dumps(value))
                index = end + 1
                continue
            output.append(char)
            index += 1
        return "".join(output)

    source = quote_bare_keys(convert_single_quoted_strings(strip_comments(text)))
    def normalize_bare_values(source: str) -> str:
        output: list[str] = []
        index = 0
        in_string = False
        escaped = False
        while index < len(source):
            char = source[index]
            if in_string:
                output.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
                output.append(char)
                index += 1
                continue
            output.append(char)
            if char not in ":[,":
                index += 1
                continue
            start = index + 1
            while start < len(source) and source[start].isspace():
                start += 1
            if start >= len(source) or not (source[start].isalpha() or source[start] == "_"):
                index += 1
                continue
            end = start + 1
            while end < len(source) and (source[end].isalnum() or source[end] in "_.-"):
                end += 1
            following = end
            while following < len(source) and source[following].isspace():
                following += 1
            if following >= len(source) or source[following] == ":":
                index += 1
                continue
            value = source[start:end]
            output.append(source[index + 1:start])
            output.append(value.lower() if value.lower() in {"true", "false", "null"} else json.dumps(value))
            index = end
        return "".join(output)

    def escape_control_chars_in_strings(source: str) -> str:
        output: list[str] = []
        in_string = False
        escaped = False
        for char in source:
            if in_string and ord(char) < 32 and char not in "\t\r\n":
                output.append(f"\\u{ord(char):04x}")
                continue
            output.append(char)
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
        return "".join(output)

    def normalize_semicolon_delimiters(source: str) -> str:
        output: list[str] = []
        in_string = False
        escaped = False
        for char in source:
            if in_string:
                output.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                output.append("," if char == ";" else char)
                if char == '"':
                    in_string = True
        return "".join(output)

    source = escape_control_chars_in_strings(normalize_semicolon_delimiters(normalize_bare_values(quote_bare_keys(convert_single_quoted_strings(strip_comments(text))))))
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        char = source[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
        elif char == ",":
            lookahead = index + 1
            while lookahead < len(source) and source[lookahead].isspace():
                lookahead += 1
            if lookahead < len(source) and source[lookahead] in "}]":
                output.append(source[index + 1:lookahead])
                index = lookahead
                continue
        output.append(char)
        index += 1
    normalized = "".join(output)
    # HJSON-style numeric float suffixes (for example 1f) are syntax only.
    normalized = re.sub(r'(?<![A-Za-z0-9_\"])(-?(?:\d+\.\d*|\d*\.\d+|\d+))[fFdD](?=\s*[,}\]])', r'\1', normalized)
    # Bare leading-decimal numeric literals (e.g. ".7") are invalid JSON but
    # common in real Starsector skin files (verified: 20 of the live
    # install's own core `.skin` files use `"baseValueMult":.7`-style
    # values). Only matches immediately after a JSON structural character,
    # so it cannot touch a digit sequence already inside a string literal.
    normalized = re.sub(r'([:,\[]\s*-?)\.(\d)', r'\g<1>0.\2', normalized)
    # Leading unary-plus numeric literals (e.g. "renderOrderMod":+30) are
    # invalid JSON but occur in real Starsector mod files (verified: Diable
    # Avionics 2.9.5.3's `diableavionics_IBBgulf.ship`, `"renderOrderMod":+30`).
    # Only matches immediately after a JSON structural character (optionally
    # with whitespace), so it cannot touch a digit sequence already inside a
    # string literal.
    normalized = re.sub(r'([:,\[]\s*)\+(?=\d)', r'\g<1>', normalized)
    trailing = len(normalized)
    while trailing and normalized[trailing - 1].isspace():
        trailing -= 1
    if trailing and normalized[trailing - 1] == ",":
        normalized = normalized[:trailing - 1] + normalized[trailing:]
    return normalized


def json_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        # Match CSV handling: legacy mod JSON-like files are sometimes
        # Windows-1252 encoded. This changes decoding only, never syntax or
        # mechanics interpretation.
        text = path.read_text(encoding="cp1252")
    value = json.loads(_relaxed_json(text))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def csv_rows(path: Path) -> Iterator[dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Legacy Starsector mods may use Windows-1252 text; this is an
        # encoding fallback, not a reinterpretation of their data semantics.
        text = path.read_text(encoding="cp1252")
    # Filter comments after CSV record parsing, not by physical line. A
    # commented record may contain a quoted multi-line description; dropping
    # only its first line would turn later continuation lines into fake rows.
    reader = csv.reader(io.StringIO(text))
    headers: list[str] | None = None
    for candidate in reader:
        if not candidate or not any(candidate) or candidate[0].lstrip().startswith("#"):
            continue
        headers = candidate
        break
    if headers is None:
        return
    for values in reader:
        if not values or not any(values):
            continue
        if values[0].lstrip().startswith("#"):
            continue
        row = dict(zip(headers, values))
        # Some legacy wing tables spell an empty optional field as two literal
        # single quotes. Normalize only that unambiguous empty sentinel; do not
        # reinterpret arbitrary quoted source text.
        yield {key: "" if value == "''" else value for key, value in row.items()}


def first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


@dataclass(frozen=True)
class NumericParseWarning:
    """Machine-readable record for an invalid numeric source value.

    Blank values are normal optional-field absence and do not produce a warning.
    Invalid values fall back safely; callers may attach an entity field/path via
    ``field`` and retain the record in a scan report.
    """

    code: str
    expected_type: str
    value: str
    field: str | None = None


def _numeric_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _numeric_warning(warnings: list[dict[str, object]] | None, expected_type: str, value: Any, field: str | None) -> None:
    if warnings is not None:
        warnings.append(asdict(NumericParseWarning("INVALID_NUMERIC_VALUE", expected_type, str(value), field)))


def parse_int(value: Any, default: int | None = None, *, warnings: list[dict[str, object]] | None = None, field: str | None = None) -> int | None:
    """Safely normalize a source integer, accepting integral decimal text.

    ``" 2 "`` and ``"2.0"`` become ``2``; blank/missing input returns the
    default without noise. Fractional, non-finite, boolean, and non-numeric
    input returns the default and emits a structured warning when requested.
    """
    if isinstance(value, bool):
        _numeric_warning(warnings, "int", value, field)
        return default
    text = _numeric_text(value)
    if text is None:
        return default
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        _numeric_warning(warnings, "int", value, field)
        return default
    if not math.isfinite(number) or not number.is_integer():
        _numeric_warning(warnings, "int", value, field)
        return default
    return int(number)


def parse_float(value: Any, default: float | None = None, *, warnings: list[dict[str, object]] | None = None, field: str | None = None) -> float | None:
    """Safely normalize a finite source float, recording invalid input."""
    if isinstance(value, bool):
        _numeric_warning(warnings, "float", value, field)
        return default
    text = _numeric_text(value)
    if text is None:
        return default
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        _numeric_warning(warnings, "float", value, field)
        return default
    if not math.isfinite(number):
        _numeric_warning(warnings, "float", value, field)
        return default
    return number


def optional_int(value: Any, default: int | None = None, *, warnings: list[dict[str, object]] | None = None, field: str | None = None) -> int | None:
    """Backward-compatible optional parser; new parser code should use parse_int."""
    return parse_int(value, default, warnings=warnings, field=field)


def optional_float(value: Any, default: float | None = None, *, warnings: list[dict[str, object]] | None = None, field: str | None = None) -> float | None:
    """Backward-compatible optional parser; new parser code should use parse_float."""
    return parse_float(value, default, warnings=warnings, field=field)


def optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    return str(value).strip().lower() in {"true", "1", "yes"}
