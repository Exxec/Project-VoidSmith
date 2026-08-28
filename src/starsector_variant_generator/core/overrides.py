from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EntityOverride:
    entity_id: str
    role_tags: tuple[str, ...]
    notes: str | None


def load_overrides(overrides_dir: Path, entity_kind: str) -> dict[str, EntityOverride]:
    """Load user-editable classification overrides for one entity kind.

    Implements FORMAL_SPECIFICATION.md section 46's "Manual Override
    Layer" (`config/overrides/{hulls,weapons,fighters,hullmods,
    factions}.json`). That section names the files but doesn't pin an
    exact per-file JSON schema -- only a single-entity example
    (config/overrides/weapons.example.json) showing one entry's shape.
    This picks a concrete, defensible shape: a JSON object keyed by entity
    id (a lookup table, not a list, so a duplicate id can't silently
    shadow an earlier entry):

        {"<entity_id>": {"role_tags": ["..."], "notes": "..."}, ...}

    Source safety and legality are structurally guaranteed by scope, not
    by a runtime check: this module is read-only over the (already
    read-only) `overrides_dir`, never writes anywhere, and is never
    imported by validation/legality.py -- an override can change what
    role tags a report shows, never what is LEGAL/ILLEGAL/NOT_DETERMINABLE.

    A missing file, unreadable JSON, or a malformed entry is treated as
    "no override" rather than raising, matching this project's "log
    skipped/unknown inputs without crashing" rule -- a broken override
    file must not take down a scan.
    """
    path = overrides_dir / f"{entity_kind}.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    overrides: dict[str, EntityOverride] = {}
    for entity_id, fields in raw.items():
        if not isinstance(fields, dict):
            continue
        tags = fields.get("role_tags", [])
        if not isinstance(tags, list):
            continue
        notes = fields.get("notes")
        overrides[str(entity_id)] = EntityOverride(
            entity_id=str(entity_id),
            role_tags=tuple(str(tag) for tag in tags),
            notes=str(notes) if isinstance(notes, str) else None,
        )
    return overrides


def apply_role_tag_override(base_tags: tuple[str, ...], override: EntityOverride | None) -> tuple[str, ...]:
    """Union an override's role_tags into base_tags.

    Additive only: an override can supplement what the classifier already
    found from parsed data, never remove or replace it. A pure-removal or
    replace mode would let a user's override silently hide real parsed
    evidence, which cuts against this project's "preserve raw evidence"
    principle -- if that's ever needed, it should be a distinct, explicitly
    named override mode, not the default behavior.
    """
    if override is None:
        return base_tags
    return tuple(sorted(set(base_tags) | set(override.role_tags)))
