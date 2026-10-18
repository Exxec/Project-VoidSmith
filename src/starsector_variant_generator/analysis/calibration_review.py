"""Calibration review sheets a person can finish (docs/AUTOMATION_PLAN.md V2.1 to V2.3).

A review sheet is a CSV of reviewer judgments about real ships. It stays under the gitignored `generated/` tree (AGENTS.md section
4); every read and write of a sheet here is checked against that root.

- `resolve_sheet` (V2.1, V2.2) fills in which scanned hull each display name means and why (`resolve_rule`), checks the named
  equipment against the scan, validates a named existing variant, and marks `ready_for_review`. Ready rows sort first.
- `approve_rows` (V2.3) sets APPROVED on listed or all ready rows for a NAMED reviewer. It refuses any row that is not ready, and
  nothing calls it automatically. Heuristics are never changed (AGENTS.md section 8).

Nothing here interprets game mechanics: names are matched as text, and legality comes only from `validation/legality.py`.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from starsector_variant_generator.core.models import Hull, ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.safeio import atomic_write_text
from starsector_variant_generator.validation.legality import validate_variant

PENDING_STATUS = "PROVISIONAL_REVIEW_REQUIRED"
APPROVED_STATUS = "APPROVED"
ADDED_COLUMNS = (
    "row_id", "resolved_hull_key", "resolve_rule", "resolve_candidates", "equipment_ok", "equipment_unresolved",
    "legality", "ready_for_review", "approved_by", "approved_on",
)
RESOLVED_RULES = ("EXACT_NAME", "NORMALISED_NAME", "QUALIFIER_STRIPPED")
MAX_CANDIDATES_LISTED = 10
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_QUALIFIER = re.compile(r"\([^)]*\)")
_QUANTITY = re.compile(r"^\s*(?:\d+\s*x|x\s*\d+)\s+", re.IGNORECASE)
_ROW_SPEC = re.compile(r"^(\d+)(?:-(\d+))?$")


@dataclass(frozen=True)
class Resolution:
    rule: str  # one of RESOLVED_RULES, AMBIGUOUS or UNRESOLVED
    hull: Hull | None
    candidates: tuple[str, ...]


def require_under(path: Path, root: Path) -> Path:
    """The resolved path if it lies strictly inside `root` (the gitignored generated tree), else ValueError."""
    resolved, resolved_root = path.resolve(), root.resolve()
    if resolved_root not in resolved.parents:
        raise ValueError(f"{path} is outside {root}; calibration sheets are read and written only under that folder.")
    return resolved


def _norm(text: str) -> str:
    return _NON_ALNUM.sub("", text.casefold())


def _norm_stripped(text: str) -> str:
    return _norm(_QUALIFIER.sub(" ", text))


def hull_key(hull: Hull) -> str:
    return f"hull:{hull.source_mod}:{hull.id}"


def _candidate_labels(hulls: list[Hull]) -> tuple[str, ...]:
    return tuple(sorted(hull_key(hull) for hull in hulls))[:MAX_CANDIDATES_LISTED]


def _outcome(rule: str, hulls: list[Hull]) -> Resolution | None:
    if not hulls:
        return None
    if len(hulls) == 1:
        return Resolution(rule, hulls[0], (hull_key(hulls[0]),))
    return Resolution("AMBIGUOUS", None, _candidate_labels(hulls))


def _prefer_base(display: str, hulls: list[Hull]) -> list[Hull]:
    """Narrow same-name candidates with facts the sheet itself states: (D) suffix, 'Vanilla', skin versus base hull."""
    wants_damaged = "(d)" in display.casefold()
    narrowed = [hull for hull in hulls if wants_damaged == ("(d)" in hull.name.casefold())] or hulls
    if "(vanilla)" in display.casefold():
        narrowed = [hull for hull in narrowed if hull.source_mod == "core"] or narrowed
    if len(narrowed) > 1:
        narrowed = [hull for hull in narrowed if hull.source_path.suffix.lower() != ".skin"] or narrowed
    return narrowed


def resolve_name(display: str, hulls: list[Hull]) -> Resolution:
    """EXACT_NAME, then NORMALISED_NAME (case/punctuation), then QUALIFIER_STRIPPED (also (D), skin and Vanilla); first hit wins."""
    stages = (
        ("EXACT_NAME", [hull for hull in hulls if hull.name == display]),
        ("NORMALISED_NAME", [hull for hull in hulls if _norm(hull.name) == _norm(display)]),
        ("QUALIFIER_STRIPPED", _prefer_base(display, [hull for hull in hulls if _norm_stripped(hull.name) == _norm_stripped(display)])
         if _norm_stripped(display) else []),
    )
    for rule, matches in stages:
        outcome = _outcome(rule, matches)
        if outcome is not None:
            return outcome
    return Resolution("UNRESOLVED", None, ())


def equipment_index(scan: ScanResult) -> set[str]:
    names: set[str] = set()
    for group in (scan.weapons, scan.hullmods, scan.fighters):
        for entity in group:
            names.update((_norm(entity.name), _norm(entity.id)))
    names.discard("")
    return names


def check_equipment(loadout_text: str, known: set[str]) -> tuple[str, tuple[str, ...]]:
    """TRUE when every comma/semicolon separated item names scanned equipment; FALSE lists the others; NOT_APPLICABLE when empty."""
    items = [_QUANTITY.sub("", item).strip() for item in re.split(r"[;,]", loadout_text)]
    items = [item for item in items if item]
    if not items:
        return "NOT_APPLICABLE", ()
    missing = tuple(item for item in items if _norm(item) not in known)
    return ("FALSE", missing) if missing else ("TRUE", ())


def check_variant(variant_id: str, hull: Hull | None, scan: ScanResult, registry: Registry) -> str:
    """Legality of an existing variant the row names; NOT_APPLICABLE when none is named; NO_SUCH_VARIANT when it is not on that hull."""
    if not variant_id or hull is None:
        return "NOT_APPLICABLE"
    matches = [v for v in scan.variants if v.id == variant_id and v.hull_id == hull.id]
    if len(matches) != 1:
        return "NO_SUCH_VARIANT"
    return str(validate_variant(matches[0], registry).result.value)


def read_sheet(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def write_sheet(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, "﻿" + buffer.getvalue(), newline="")


def _resolve_row(row: dict[str, str], hulls: list[Hull], known: set[str], scan: ScanResult, registry: Registry,
                 name_column: str, loadout_column: str, variant_column: str) -> dict[str, str]:
    resolution = resolve_name(row.get(name_column, ""), hulls)
    equipment, unresolved = check_equipment(row.get(loadout_column, ""), known) if resolution.hull else ("NOT_APPLICABLE", ())
    legality = check_variant(row.get(variant_column, "").strip(), resolution.hull, scan, registry)
    ready = (
        resolution.hull is not None and equipment != "FALSE" and legality in ("LEGAL", "NOT_APPLICABLE")
        and row.get("review_status", PENDING_STATUS) == PENDING_STATUS
    )
    return {
        "resolved_hull_key": hull_key(resolution.hull) if resolution.hull else "",
        "resolve_rule": resolution.rule, "resolve_candidates": ";".join(resolution.candidates) if resolution.hull is None else "",
        "equipment_ok": equipment, "equipment_unresolved": ";".join(unresolved), "legality": legality,
        "ready_for_review": "TRUE" if ready else "FALSE",
    }


def resolve_sheet(
    sheet: Path, output: Path, scan: ScanResult, registry: Registry, generated_root: Path, *,
    name_column: str = "ship_display", loadout_column: str = "loadout_text", variant_column: str = "variant_id",
) -> dict[str, object]:
    """Write `output` (a new sheet under generated/) with resolution, pre-check columns and ready rows first."""
    source, destination = require_under(sheet, generated_root), require_under(output, generated_root)
    fields, rows = read_sheet(source)
    if name_column not in fields or "review_status" not in fields:
        raise ValueError(f"The sheet has no {name_column!r} or review_status column (columns: {', '.join(fields)}).")
    hulls, known = list(scan.hulls), equipment_index(scan)
    resolved_rows = []
    for index, row in enumerate(rows, start=1):
        extra = _resolve_row(row, hulls, known, scan, registry, name_column, loadout_column, variant_column)
        resolved_rows.append({**row, **extra, "row_id": row.get("row_id") or str(index),
                              "approved_by": row.get("approved_by", ""), "approved_on": row.get("approved_on", "")})
    resolved_rows.sort(key=lambda row: (row["ready_for_review"] != "TRUE", int(row["row_id"])))
    write_sheet(destination, [*fields, *[c for c in ADDED_COLUMNS if c not in fields]], resolved_rows)
    rules: dict[str, int] = {}
    for row in resolved_rows:
        rules[row["resolve_rule"]] = rules.get(row["resolve_rule"], 0) + 1
    return {"rows": len(rows), "ready": sum(r["ready_for_review"] == "TRUE" for r in resolved_rows),
            "by_rule": dict(sorted(rules.items())), "output": str(destination)}


def parse_row_spec(spec: str) -> list[int]:
    """'3,5-7' -> [3, 5, 6, 7]; anything else is a ValueError."""
    ids: list[int] = []
    for part in (piece.strip() for piece in spec.split(",") if piece.strip()):
        match = _ROW_SPEC.match(part)
        if match is None:
            raise ValueError(f"Bad row list {spec!r}; use numbers and ranges such as 3,5-7.")
        low, high = int(match.group(1)), int(match.group(2) or match.group(1))
        if high < low:
            raise ValueError(f"Bad range {part!r}.")
        ids.extend(range(low, high + 1))
    return sorted(set(ids))


def approve_rows(
    sheet: Path, generated_root: Path, reviewer: str, *, rows: list[int] | None = None, all_ready: bool = False,
    today: date | None = None,
) -> dict[str, object]:
    """Mark ready rows APPROVED by `reviewer`; every other listed row is refused with a reason and left untouched."""
    name = reviewer.strip()
    if not any(ch.isalpha() for ch in name) or len(name) > 80:
        raise ValueError("Approval needs the reviewer's own name (--reviewer).")
    if bool(rows) == all_ready:
        raise ValueError("Give either a row list or --all-ready, not both and not neither.")
    path = require_under(sheet, generated_root)
    fields, data = read_sheet(path)
    if "ready_for_review" not in fields or "row_id" not in fields:
        raise ValueError("Run `calibration resolve` first: the sheet has no pre-check columns.")
    by_id = {row["row_id"]: row for row in data}
    targets = [str(i) for i in rows] if rows else [row["row_id"] for row in data if row["ready_for_review"] == "TRUE"]
    stamp = (today or date.today()).isoformat()
    approved: list[str] = []
    refused: list[dict[str, str]] = []
    for row_id in targets:
        row = by_id.get(row_id)
        if row is None:
            refused.append({"row_id": row_id, "reason": "NO_SUCH_ROW"})
        elif row.get("review_status") != PENDING_STATUS:
            refused.append({"row_id": row_id, "reason": "ALREADY_REVIEWED"})
        elif row["ready_for_review"] != "TRUE":
            refused.append({"row_id": row_id, "reason": "NOT_READY: failed a pre-check"})
        else:
            row.update({"review_status": APPROVED_STATUS, "approved_by": name, "approved_on": stamp})
            approved.append(row_id)
    if approved:
        write_sheet(path, fields, data)
        with path.with_suffix(".approvals.jsonl").open("a", encoding="utf-8", newline="\n") as log:
            log.write(json.dumps({"reviewer": name, "date": stamp, "rows": approved}) + "\n")
    return {"approved": approved, "refused": refused, "reviewer": name}
