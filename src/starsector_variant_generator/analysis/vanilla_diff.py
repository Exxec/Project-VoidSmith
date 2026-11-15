"""Read-only "side by side" of two Starsector game builds, for what changes fitting (ROADMAP.md, "Game-build diff" 2026-11-15).

Compares the CORE data of two installs (never mods): hulls, weapons, hull mods, fighter wings (through the existing scanner and
parsers) and ship systems (`data/shipsystems/ship_systems.csv` through `csv_rows`, plus each `.system` file's scalar keys through
`json_file`). For each entity it reports added, removed, and changed fields (old -> new). It also compares the settings VoidSmith
reads or hard-codes (`data/config/settings.json`) and lists the local files that name an entity whose data changed or that was
removed, so stale cached data, knowledge packs and fixtures can be regenerated.

Read-only: both installs are only read; the report goes to stdout or a path the caller gives and quotes game stat values, so it
is local data and must not be committed (AGENTS.md section 4). Limits: Java hull-mod and ship-system scripts are not read, so a
hull mod whose numbers live in code can change without appearing here; the engine-hardcoded vent/capacitor limits are in no
parseable file and are reported as unverifiable.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from starsector_variant_generator.adapters.vanilla import FLUX_UNIT_COST, MAX_LOGISTICS_HULLMODS
from starsector_variant_generator.core.models import Entity, ScanResult
from starsector_variant_generator.core.scanner import Scanner
from starsector_variant_generator.parsers.common import csv_rows, json_file

SCHEMA_VERSION = "vanilla-diff-0.1"
KINDS = ("hulls", "weapons", "hullmods", "shipsystems", "fighters")
# Columns that only carry prose or art paths: a wording change is not a balance change.
_IGNORED_FIELDS = frozenset({"desc", "short", "sprite", "icon", "tech/manufacturer", "number", "turretSprite", "hardpointSprite", "sprite_source_path"})
_SKIP_SHIP_KEYS = frozenset({"weaponSlots", "engineSlots", "bounds", "center", "style", "spriteName"})
# Settings VoidSmith reads or hard-codes: key -> (hard-coded value in adapters/vanilla, where it is used).
HARDCODED_SETTINGS: Mapping[str, tuple[float | int, str]] = {
    "dissipationPerVent": (FLUX_UNIT_COST.dissipation_per_vent, "adapters/vanilla FLUX_UNIT_COST.dissipation_per_vent"),
    "fluxPerCapacitor": (FLUX_UNIT_COST.capacity_per_capacitor, "adapters/vanilla FLUX_UNIT_COST.capacity_per_capacitor"),
    "maxLogisticsHullmods": (MAX_LOGISTICS_HULLMODS, "adapters/vanilla MAX_LOGISTICS_HULLMODS"),
}
_SETTINGS_ALSO_LISTED = ("maxPermanentHullmods",)
_TEXT_SUFFIXES = frozenset({".json", ".csv", ".md", ".txt", ".toml", ".jsonl", ".variant", ".ship", ".wpn"})
_MAX_SCAN_BYTES = 8 * 1024 * 1024
_TOP_CHANGES = 25
_MIN_BASE = 1.0


def core_dir(install: Path) -> Path:
    """The `starsector-core` folder of an install root, or the folder itself when it already is one."""
    nested = install / "starsector-core"
    return nested if nested.is_dir() else install


def _scan_core(install: Path) -> ScanResult:
    root = core_dir(install)
    if not (root / "data").is_dir():
        raise ValueError(f"{install} has no data/ folder (expected a Starsector install or its starsector-core folder)")
    # The core folder is passed as the game root, so no mods/ folder is discovered: only vanilla data is read.
    return Scanner(root).scan()


def _scalars(mapping: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    return {f"{prefix}{key}": str(value) for key, value in mapping.items() if isinstance(value, (str, int, float, bool)) and key not in _IGNORED_FIELDS}


def _entity_fields(entity: Entity) -> dict[str, str]:
    """Comparable fields: the raw CSV row, the hull's ship-file scalars, and the parsed built-ins and mounts."""
    raw = dict(entity.raw)
    ship = raw.pop("ship_data", None)
    fields = _scalars(raw)
    if isinstance(ship, Mapping):
        fields.update(_scalars({k: v for k, v in ship.items() if k not in _SKIP_SHIP_KEYS}, "ship."))
    for attr in ("built_in_hullmods", "built_in_fighter_wings", "launch_bay_slots"):
        if hasattr(entity, attr):
            fields[attr] = ", ".join(sorted(getattr(entity, attr)))
    if hasattr(entity, "built_in_weapons"):
        fields["built_in_weapons"] = ", ".join(f"{k}={v}" for k, v in sorted(entity.built_in_weapons.items()))
    if hasattr(entity, "weapon_mounts"):
        fields["weapon_mounts"] = "; ".join(sorted(_mount_signature(m) for m in entity.weapon_mounts))
    return {key: value.strip() for key, value in fields.items()}


def _mount_signature(mount: Mapping[str, Any]) -> str:
    return f"{mount.get('id')}:{mount.get('type')}:{mount.get('size')}:{mount.get('arc')}:{mount.get('angle')}"


def read_shipsystems(install: Path) -> dict[str, dict[str, Any]]:
    """Ship systems: id -> {name, fields}. CSV row plus the `.system` file's scalar keys."""
    folder = core_dir(install) / "data" / "shipsystems"
    systems: dict[str, dict[str, Any]] = {}
    table = folder / "ship_systems.csv"
    if table.is_file():
        for row in csv_rows(table):
            system_id = (row.get("id") or "").strip()
            if system_id:
                systems[system_id] = {"name": row.get("name") or system_id, "fields": {k: v.strip() for k, v in row.items() if k not in _IGNORED_FIELDS and v is not None}}
    for path in sorted(folder.glob("*.system")) if folder.is_dir() else []:
        entry = systems.get(path.stem)
        if entry is None:
            continue
        try:
            entry["fields"].update(_scalars(json_file(path), "system."))
        except (OSError, ValueError, json.JSONDecodeError):
            entry["fields"]["system.unreadable"] = "true"
    return systems


def _entities_by_id(scan: ScanResult, kind: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entity in getattr(scan, kind):
        if entity.source_mod == "core" and entity.id not in out:
            out[entity.id] = {"name": entity.name, "fields": _entity_fields(entity)}
    return out


def _number(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


def _differs(old: str | None, new: str | None) -> bool:
    if (old or "") == (new or ""):
        return False
    a, b = _number(old), _number(new)
    return not (a is not None and b is not None and a == b)


def _field_changes(old: Mapping[str, str], new: Mapping[str, str]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        if not _differs(before, after):
            continue
        change: dict[str, Any] = {"field": key, "old": before, "new": after}
        a, b = _number(before), _number(after)
        if a is not None and b is not None and abs(a) >= _MIN_BASE:
            change["relative"] = round((b - a) / abs(a), 4)
        changes.append(change)
    return changes


def diff_kind(old: Mapping[str, Mapping[str, Any]], new: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Added, removed and changed entities between two id-keyed maps of {name, fields}."""
    changed = []
    for entity_id in sorted(set(old) & set(new)):
        changes = _field_changes(old[entity_id]["fields"], new[entity_id]["fields"])
        if changes:
            changed.append({"id": entity_id, "name": new[entity_id]["name"], "changes": changes})
    return {
        "old_count": len(old), "new_count": len(new),
        "added": [{"id": i, "name": new[i]["name"]} for i in sorted(set(new) - set(old))],
        "removed": [{"id": i, "name": old[i]["name"]} for i in sorted(set(old) - set(new))],
        "changed": changed,
    }


def _read_settings(install: Path) -> dict[str, Any]:
    path = core_dir(install) / "data" / "config" / "settings.json"
    return json_file(path) if path.is_file() else {}


def diff_settings(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in (*HARDCODED_SETTINGS, *_SETTINGS_ALSO_LISTED):
        hardcoded = HARDCODED_SETTINGS.get(key)
        rows.append({
            "key": key, "old": old.get(key), "new": new.get(key),
            "changed": _differs(_text(old.get(key)), _text(new.get(key))),
            "hardcoded": hardcoded[0] if hardcoded else None, "hardcoded_in": hardcoded[1] if hardcoded else None,
            "new_differs_from_hardcoded": hardcoded is not None and _differs(_text(new.get(key)), _text(hardcoded[0])),
        })
    rows.append({
        "key": "max vents / capacitors per hull size", "old": None, "new": None, "changed": None,
        "hardcoded": dict(FLUX_UNIT_COST.max_vents_by_hull_size), "hardcoded_in": "adapters/vanilla FLUX_UNIT_COST.max_*_by_hull_size",
        "new_differs_from_hardcoded": None, "note": "Engine-hardcoded; in no parseable file, so this diff cannot verify it. Check the wiki or a live run.",
    })
    return rows


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _affected_ids(kinds: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """id -> {kind: 'removed'|'changed'} for ids a local file might still name."""
    ids: dict[str, dict[str, str]] = {}
    for kind, section in kinds.items():
        for status in ("removed", "changed"):
            for entry in section[status]:
                ids.setdefault(entry["id"], {})[kind] = status
    return ids


def _iter_text_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*")) if root.is_dir() else []
        for path in candidates:
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in _TEXT_SUFFIXES:
                yield path


def _file_tokens(path: Path) -> set[str]:
    try:
        if path.stat().st_size > _MAX_SCAN_BYTES:
            return set()
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return set()
    return set(re.findall(r"[A-Za-z0-9_.\-]+", text))


def find_stale_references(affected: Mapping[str, Mapping[str, str]], roots: Iterable[Path]) -> list[dict[str, Any]]:
    """Files under `roots` that contain an affected id as a whole token (exact id, not a substring)."""
    hits: list[dict[str, Any]] = []
    for root in roots:
        for path in _iter_text_files([root]):
            found = sorted(_file_tokens(path) & set(affected))
            if found:
                shown = path.relative_to(root.parent) if root.is_dir() else path
                hits.append({"file": str(shown).replace("\\", "/"), "ids": [{"id": i, "kinds": dict(affected[i])} for i in found]})
    return hits


def _largest_changes(kinds: Mapping[str, Mapping[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows = [
        {"kind": kind, "id": entry["id"], "name": entry["name"], **change}
        for kind, section in kinds.items() for entry in section["changed"] for change in entry["changes"] if "relative" in change
    ]
    rows.sort(key=lambda row: (-abs(row["relative"]), row["kind"], row["id"], row["field"]))
    return rows[:limit]


def build_report(old_install: Path, new_install: Path, *, old_label: str | None = None, new_label: str | None = None, reference_roots: Iterable[Path] = (), top: int = _TOP_CHANGES) -> dict[str, Any]:
    """Diff two installs. Reads only; `reference_roots` are the local folders checked for stale references."""
    old_scan, new_scan = _scan_core(old_install), _scan_core(new_install)
    maps = {
        kind: (read_shipsystems(old_install), read_shipsystems(new_install)) if kind == "shipsystems"
        else (_entities_by_id(old_scan, kind), _entities_by_id(new_scan, kind))
        for kind in KINDS
    }
    kinds = {kind: diff_kind(*pair) for kind, pair in maps.items()}
    affected = _affected_ids(kinds)
    return {
        "schema_version": SCHEMA_VERSION, "read_only": True,
        "old": {"label": old_label or old_install.name, "path": str(old_install)},
        "new": {"label": new_label or new_install.name, "path": str(new_install)},
        "summary": {kind: {"old": s["old_count"], "new": s["new_count"], "added": len(s["added"]), "removed": len(s["removed"]), "changed": len(s["changed"])} for kind, s in kinds.items()},
        "kinds": kinds,
        "largest_changes": _largest_changes(kinds, top),
        "settings": diff_settings(_read_settings(old_install), _read_settings(new_install)),
        "affects_voidsmith": {
            "searched": [str(root) for root in reference_roots],
            "match_rule": "whole-token match of an id that was removed or changed; a short common id can match unrelated text, so review each row",
            "hits": find_stale_references(affected, list(reference_roots)),
        },
        "limits": "Core data only. Java hull-mod and ship-system code is not read; the stat columns and .system keys are compared as written.",
    }


def to_markdown(report: Mapping[str, Any], *, max_changed_per_kind: int | None = None) -> str:
    lines = [f"# Vanilla diff: {report['old']['label']} -> {report['new']['label']}", "", f"Old: `{report['old']['path']}`  ", f"New: `{report['new']['path']}`", ""]
    lines += ["## Summary", "", "| Kind | Old | New | Added | Removed | Changed |", "|---|---|---|---|---|---|"]
    for kind, row in report["summary"].items():
        lines.append(f"| {kind} | {row['old']} | {row['new']} | {row['added']} | {row['removed']} | {row['changed']} |")
    lines += ["", "## Settings VoidSmith reads or hard-codes", ""]
    lines += [_settings_line(row) for row in report["settings"]]
    lines += ["", f"## Largest numeric changes (top {len(report['largest_changes'])})", ""]
    lines += [f"- {r['kind']} `{r['id']}` {r['field']}: {r['old']} -> {r['new']} ({r['relative']:+.0%})" for r in report["largest_changes"]]
    for kind, section in report["kinds"].items():
        lines += _kind_markdown(kind, section, max_changed_per_kind)
    lines += _affects_markdown(report["affects_voidsmith"])
    lines += ["", f"_{report['limits']}_", ""]
    return "\n".join(lines)


def _settings_line(row: Mapping[str, Any]) -> str:
    if row.get("note"):
        return f"- {row['key']}: hard-coded {row['hardcoded']} ({row['hardcoded_in']}). {row['note']}"
    flags = ["CHANGED between builds" if row["changed"] else "same in both"]
    if row["new_differs_from_hardcoded"]:
        flags.append(f"DIFFERS from VoidSmith's hard-coded {row['hardcoded']}")
    where = f" ({row['hardcoded_in']})" if row["hardcoded_in"] else ""
    return f"- {row['key']}: {row['old']} -> {row['new']}; {'; '.join(flags)}{where}"


def _kind_markdown(kind: str, section: Mapping[str, Any], cap: int | None) -> list[str]:
    lines = ["", f"## {kind}", "", f"Added ({len(section['added'])}): " + (", ".join(f"`{e['id']}`" for e in section["added"]) or "none"),
             "", f"Removed ({len(section['removed'])}): " + (", ".join(f"`{e['id']}`" for e in section["removed"]) or "none"),
             "", f"Changed ({len(section['changed'])}):", ""]
    shown = section["changed"] if cap is None else section["changed"][:cap]
    for entry in shown:
        lines.append(f"- `{entry['id']}` ({entry['name']})")
        lines += [f"  - {c['field']}: {c['old'] or '(empty)'} -> {c['new'] or '(empty)'}" for c in entry["changes"]]
    if len(shown) < len(section["changed"]):
        lines.append(f"- ... {len(section['changed']) - len(shown)} more (see the JSON report)")
    return lines


def _affects_markdown(affects: Mapping[str, Any]) -> list[str]:
    lines = ["", "## Affects VoidSmith", "", "Searched: " + (", ".join(f"`{p}`" for p in affects["searched"]) or "nothing"), "", affects["match_rule"] + ".", ""]
    if not affects["hits"]:
        return lines + ["No local file names a removed or changed entity."]
    for hit in affects["hits"]:
        named = ", ".join(f"`{i['id']}` ({'/'.join(sorted(set(i['kinds'].values())))})" for i in hit["ids"])
        lines.append(f"- `{hit['file']}`: {named}")
    return lines
