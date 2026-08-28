from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from starsector_variant_generator.core.models import ScanResult


@dataclass(frozen=True)
class CacheComparison:
    status: str
    added: int
    changed: int
    removed: int


def build_manifest(scan: ScanResult) -> dict[str, Any]:
    entries: list[dict[str, str | None]] = []
    for category in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions"):
        for entity in getattr(scan, category):
            entries.append({
                "category": category,
                "id": entity.id,
                "source_path": str(entity.source_path),
                "source_hash": entity.source_hash,
                "source_mod": entity.source_mod,
                "source_mod_version": entity.source_mod_version,
            })
    return {"schema_version": 1, "entries": sorted(entries, key=lambda item: (item["category"], item["id"], item["source_path"]))}


def load_manifest(path: Path) -> dict[str, Any] | None:
    """Read a prior manifest for preview; malformed data is not trusted."""
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def update_manifest(path: Path, scan: ScanResult) -> CacheComparison:
    current = build_manifest(scan)
    previous: dict[str, Any] | None = None
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
    key = lambda item: (item["category"], item["id"], item["source_path"])
    old_entries = {key(item): item for item in (previous or {}).get("entries", [])}
    new_entries = {key(item): item for item in current["entries"]}
    added = len(new_entries.keys() - old_entries.keys())
    removed = len(old_entries.keys() - new_entries.keys())
    changed = sum(old_entries[item] != new_entries[item] for item in old_entries.keys() & new_entries.keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    status = "CREATED" if previous is None else ("UNCHANGED" if not (added or changed or removed) else "CHANGED")
    return CacheComparison(status, added, changed, removed)
