"""`calibration triage` (ROADMAP calibration item 3): group a resolved review sheet by what keeps each row from being ready.

Not-ready rows are grouped by reason code and exact key (an unresolved or ambiguous ship name, an unmatched loadout token, a
legality result, a variant_id that is not on the hull). Each group carries its count, example rows and the one fix that would
clear it. Ready rows are grouped by hull and faction, each with a `calibration approve` line for a person to run.

Read-only over the resolved sheet. Every command printed is for a person to run: `calibration alias add` writes only the sidecar
beside the raw sheets, and `calibration approve` stays person-run with --reviewer. Nothing here approves or registers anything.
"""
from __future__ import annotations

import json
from pathlib import Path

from starsector_variant_generator.analysis.calibration_review import PENDING_STATUS, read_sheet, require_under
from starsector_variant_generator.core.safeio import atomic_write_text

COMMAND_PREFIX = "voidsmith calibration"
REVIEWER_PLACEHOLDER = "<your name>"
TRIAGE_FILE = "calibration-triage.json"
EXAMPLES_PER_GROUP = 3
TOP_GROUPS_SHOWN = 10
PASSING_LEGALITY = ("LEGAL", "NOT_APPLICABLE", "")

REASON_UNRESOLVED = "UNRESOLVED_NAME"
REASON_AMBIGUOUS = "AMBIGUOUS_NAME"
REASON_LOADOUT = "UNMATCHED_LOADOUT"
REASON_NO_VARIANT = "NO_SUCH_VARIANT"
REASON_LEGALITY = "LEGALITY_FAILED"
REASON_OTHER = "UNEXPLAINED"


def compact_ids(ids: list[int]) -> str:
    """[3, 5, 6, 7] -> '3,5-7', the form `calibration approve --rows` reads."""
    unique = sorted(set(ids))
    parts: list[str] = []
    start = 0
    while start < len(unique):
        end = start
        while end + 1 < len(unique) and unique[end + 1] == unique[end] + 1:
            end += 1
        parts.append(str(unique[start]) if start == end else f"{unique[start]}-{unique[end]}")
        start = end + 1
    return ",".join(parts)


def reasons_for(row: dict[str, str]) -> list[tuple[str, str]]:
    """(reason code, group key) pairs that keep one not-ready row out of review, from the resolver's own columns."""
    found: list[tuple[str, str]] = []
    rule = row.get("resolve_rule", "")
    if rule in ("UNRESOLVED", "AMBIGUOUS"):
        found.append((REASON_UNRESOLVED if rule == "UNRESOLVED" else REASON_AMBIGUOUS, row.get("ship_display", "").strip()))
    if row.get("equipment_ok") == "FALSE":
        found.extend((REASON_LOADOUT, token) for token in row.get("equipment_unresolved", "").split(";") if token.strip())
    legality = row.get("legality", "")
    if legality == "NO_SUCH_VARIANT":
        found.append((REASON_NO_VARIANT, row.get("variant_id", "").strip()))
    elif legality not in PASSING_LEGALITY:
        found.append((REASON_LEGALITY, legality))
    return found or [(REASON_OTHER, "")]


def _fix_for(reason: str, key: str, sheet_dir: str, candidates: list[str]) -> tuple[str, str | None]:
    """The one fix that clears a group, as (text, command or None when no alias can clear it)."""
    alias = f'{COMMAND_PREFIX} alias add "{sheet_dir}" "{key}"'
    if reason == REASON_UNRESOLVED:
        return f"add alias '{key}' -> the hull id it means", f'{alias} <hull id>'
    if reason == REASON_AMBIGUOUS:
        choices = ", ".join(candidates) or "a hull key"
        return f"add alias '{key}' -> one of: {choices}", f'{alias} <hull key>'
    if reason == REASON_LOADOUT:
        return f"map loadout token '{key}' to a scanned weapon, hullmod or fighter id", f'{alias} <equipment id> --equipment'
    if reason == REASON_NO_VARIANT:
        return "correct the variant_id column or clear it (no such variant on that hull)", None
    if reason == REASON_LEGALITY:
        return f"review the variant named in variant_id (legality {key}); no alias clears it", None
    return "inspect the row; no reason code matched", None


def _not_ready_group(reason: str, key: str, members: list[dict[str, str]], sheet_dir: str) -> dict[str, object]:
    ids = sorted({int(row["row_id"]) for row in members})
    candidates = [c for c in members[0].get("resolve_candidates", "").split(";") if c]
    fix, command = _fix_for(reason, key, sheet_dir, candidates)
    return {
        "reason": reason, "key": key, "count": len(ids), "rows": compact_ids(ids),
        "examples": [f"{row['row_id']} {row.get('ship_display', '')}".strip() for row in members[:EXAMPLES_PER_GROUP]],
        "fix": fix, "fix_command": command,
    }


def _not_ready_groups(not_ready: list[dict[str, str]], sheet_dir: str) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in not_ready:
        for pair in reasons_for(row):
            buckets.setdefault(pair, []).append(row)
    groups = [_not_ready_group(reason, key, members, sheet_dir) for (reason, key), members in buckets.items()]
    return sorted(groups, key=lambda group: (-int(group["count"]), str(group["reason"]), str(group["key"])))


def _ready_groups(ready: list[dict[str, str]], sheet: str) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str], list[int]] = {}
    for row in ready:
        buckets.setdefault((row.get("resolved_hull_key", ""), row.get("faction_context", "")), []).append(int(row["row_id"]))
    groups = []
    for (hull, faction), ids in buckets.items():
        spec = compact_ids(ids)
        groups.append({
            "hull": hull, "faction": faction, "count": len(set(ids)), "rows": spec,
            "approve_command": f'{COMMAND_PREFIX} approve "{sheet}" --reviewer "{REVIEWER_PLACEHOLDER}" --rows {spec}',
        })
    return sorted(groups, key=lambda group: (-int(group["count"]), str(group["hull"]), str(group["faction"])))


def triage_sheet(sheet: Path, generated_root: Path) -> dict[str, object]:
    """Triage one resolved sheet under generated/. Reviewed rows (not PROVISIONAL) are counted, not grouped."""
    source = require_under(sheet, generated_root)
    fields, rows = read_sheet(source)
    if "ready_for_review" not in fields or "row_id" not in fields:
        raise ValueError(f"{sheet} has no pre-check columns; run `{COMMAND_PREFIX} resolve` on the raw sheet first.")
    open_rows = [row for row in rows if row.get("review_status", PENDING_STATUS) == PENDING_STATUS]
    ready = [row for row in open_rows if row["ready_for_review"] == "TRUE"]
    not_ready = [row for row in open_rows if row["ready_for_review"] != "TRUE"]
    return {
        "sheet": str(sheet), "rows": len(rows), "reviewed": len(rows) - len(open_rows),
        "ready": len(ready), "not_ready": len(not_ready),
        "not_ready_groups": _not_ready_groups(not_ready, str(sheet.parent)),
        "ready_groups": _ready_groups(ready, str(sheet)),
    }


def _combined(per_sheet: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for summary in per_sheet:
        for group in summary["not_ready_groups"]:  # type: ignore[attr-defined]
            key = (str(group["reason"]), str(group["key"]))
            entry = merged.setdefault(key, {"reason": key[0], "key": key[1], "count": 0, "sheets": 0,
                                            "fix": group["fix"], "fix_command": group["fix_command"]})
            entry["count"] = int(entry["count"]) + int(group["count"])  # type: ignore[arg-type]
            entry["sheets"] = int(entry["sheets"]) + 1  # type: ignore[arg-type]
    return sorted(merged.values(), key=lambda group: (-int(group["count"]), str(group["reason"]), str(group["key"])))  # type: ignore[arg-type]


def triage_sheets(sheets: list[Path], generated_root: Path, write_dir: Path | None = None) -> dict[str, object]:
    """Triage every sheet, merge the not-ready groups across them, and optionally write the JSON under generated/."""
    per_sheet = [triage_sheet(sheet, generated_root) for sheet in sheets]
    summary: dict[str, object] = {"sheets": per_sheet, "combined_not_ready_groups": _combined(per_sheet)}
    if write_dir is not None:
        target = require_under(write_dir / TRIAGE_FILE, generated_root)
        summary["written"] = str(target)
        atomic_write_text(target, json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n")
    return summary


def render_text(summary: dict[str, object]) -> str:
    lines: list[str] = []
    for sheet in summary["sheets"]:  # type: ignore[attr-defined]
        lines.append(f"{sheet['sheet']}: {sheet['rows']} rows, {sheet['reviewed']} reviewed, "  # type: ignore[index]
                     f"{sheet['ready']} ready, {sheet['not_ready']} not ready")  # type: ignore[index]
        lines.append("  Not ready (a row can sit under more than one reason):")
        for group in sheet["not_ready_groups"]:  # type: ignore[index]
            lines.append(f"    {group['count']:>4}  {group['reason']}  {group['key'] or '(blank)'}  rows {group['rows']}")
            lines.append(f"          fix: {group['fix']}")
            if group["fix_command"]:
                lines.append(f"          run: {group['fix_command']}")
        lines.append("  Ready, by hull and faction (person-run approval, one line per group):")
        for group in sheet["ready_groups"]:  # type: ignore[index]
            lines.append(f"    {group['count']:>4}  {group['hull']} | {group['faction'] or '(no faction)'}")
            lines.append(f"          {group['approve_command']}")
    lines.append(f"Top not-ready groups across {len(summary['sheets'])} sheet(s):")  # type: ignore[arg-type]
    for group in summary["combined_not_ready_groups"][:TOP_GROUPS_SHOWN]:  # type: ignore[index]
        lines.append(f"    {group['count']:>4}  {group['reason']}  {group['key'] or '(blank)'}  ({group['sheets']} sheet(s))")
    if "written" in summary:
        lines.append(f"Written: {summary['written']}")
    return "\n".join(lines)
