"""Faction Knowledge Pack loader: root ROADMAP.md Phase 7, first slice.

See `knowledge_packs/schema/faction_pack.schema.json` (machine contract),
`FACTION_KNOWLEDGE_PACKS.md` (field semantics), and
`knowledge_packs/examples/faction.example.json` (a neutral, non-canonical
example) -- the three-artifact split this module implements against.

A pack is optional, curated guidance. It can bias the Gap Recommendation
Engine (`analysis/gap_recommendation.py`, `GAP_RECOMMENDATION_ENGINE.md`)
toward faction-thematic solutions once that engine's retrofit/acquisition
legs exist; it can never affect `validation/legality.py`, matching every
other optional-input layer in this project (`core/overrides.py`).

Malformed input is treated as absent, never a crash (this project's
standing "log unknown/skipped inputs without crashing" rule): a missing
file, invalid JSON, or a pack missing required top-level/manifest fields
makes `load_knowledge_pack` return `None`, not raise.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starsector_variant_generator.core.registry import Registry

_REQUIRED_TOP_LEVEL = ("manifest", "faction")
_REQUIRED_MANIFEST_FIELDS = (
    "schema_version", "pack_version", "target_faction_id",
    "target_mod_id", "authored_date", "authorship_method",
)
_AUTHORSHIP_METHODS = frozenset({"HUMAN_AUTHORED", "AI_ASSISTED_REVIEW", "AI_GENERATED"})

# entity-kind prefix in a source_hashes key -> the Registry index it resolves against.
_HASH_KEY_KINDS = ("faction", "hull", "weapon", "hullmod", "fighter")


@dataclass(frozen=True)
class ManifestInfo:
    schema_version: str
    pack_version: str
    target_faction_id: str
    target_mod_id: str
    target_mod_version: str | None
    source_hashes: dict[str, str]
    authored_date: str
    authorship_method: str


@dataclass(frozen=True)
class KnowledgePack:
    path: Path
    example_only: bool
    manifest: ManifestInfo
    raw: dict[str, Any]  # full parsed JSON; hull_archetypes/retrofit_templates/etc. read from here directly rather than typed ahead of a real consumer


def load_knowledge_pack(path: Path) -> KnowledgePack | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or any(key not in raw for key in _REQUIRED_TOP_LEVEL):
        return None
    manifest_raw = raw.get("manifest")
    if not isinstance(manifest_raw, dict) or any(field not in manifest_raw for field in _REQUIRED_MANIFEST_FIELDS):
        return None
    if manifest_raw["authorship_method"] not in _AUTHORSHIP_METHODS:
        return None
    source_hashes = manifest_raw.get("source_hashes", {})
    if not isinstance(source_hashes, dict):
        source_hashes = {}
    manifest = ManifestInfo(
        schema_version=str(manifest_raw["schema_version"]),
        pack_version=str(manifest_raw["pack_version"]),
        target_faction_id=str(manifest_raw["target_faction_id"]),
        target_mod_id=str(manifest_raw["target_mod_id"]),
        target_mod_version=str(manifest_raw["target_mod_version"]) if manifest_raw.get("target_mod_version") is not None else None,
        source_hashes={str(key): str(value) for key, value in source_hashes.items()},
        authored_date=str(manifest_raw["authored_date"]),
        authorship_method=str(manifest_raw["authorship_method"]),
    )
    return KnowledgePack(path=path, example_only=bool(raw.get("example_only", False)), manifest=manifest, raw=raw)


@dataclass(frozen=True)
class PackFreshness:
    status: str  # "CURRENT" | "PARTIALLY_STALE" | "STALE" | "INCOMPATIBLE"
    reasons: tuple[str, ...]


def _current_source_hash(key: str, registry: Registry) -> str | None:
    """Resolve one `manifest.source_hashes` key ("<kind>:<entity_id>") against the live registry."""
    kind, _, entity_id = key.partition(":")
    if kind not in _HASH_KEY_KINDS or not entity_id:
        return None
    index = {
        "faction": registry.factions, "hull": registry.hulls, "weapon": registry.weapons,
        "hullmod": registry.hullmods, "fighter": registry.fighters,
    }[kind]
    entity = index.by_id.get(entity_id)
    return entity.source_hash if entity is not None else None


def _mod_has_any_scanned_entity(mod_id: str, registry: Registry) -> bool:
    """Registry has no direct mod list (only entity indexes -- ScanResult.mods
    is discarded once Registry.from_scan builds them), so mod presence is
    derived from real evidence instead: does anything real carry this
    source_mod? The scanner only ever indexes enabled mods, so any hit here
    means the mod was both installed and enabled at scan time."""
    for index in (registry.factions, registry.hulls, registry.weapons, registry.hullmods, registry.fighters):
        if any(entity.source_mod == mod_id for entity in index.by_id.values()):
            return True
        if any(entity.source_mod == mod_id for group in index.duplicates.values() for entity in group):
            return True
    return False


def assess_pack_freshness(pack: KnowledgePack, registry: Registry) -> PackFreshness:
    """CURRENT/PARTIALLY_STALE/STALE/INCOMPATIBLE per FACTION_KNOWLEDGE_PACKS.md section 12.

    INCOMPATIBLE: the pack's target mod isn't present (installed+enabled)
    in this scan at all, or its target faction doesn't resolve anywhere in
    this install's real data -- the pack cannot apply to this install
    regardless of hashes. Otherwise, judged by how many of the pack's own
    recorded `source_hashes` still match the corresponding entity's real,
    current `source_hash`: all match (or none were recorded) -> CURRENT;
    some match -> PARTIALLY_STALE; none match (but at least one was
    recorded) -> STALE.
    """
    faction_resolves = pack.manifest.target_faction_id in registry.factions.by_id or pack.manifest.target_faction_id in registry.factions.duplicates
    if not faction_resolves:
        return PackFreshness("INCOMPATIBLE", (f"target_faction_id {pack.manifest.target_faction_id!r} does not resolve in this install",))
    if not _mod_has_any_scanned_entity(pack.manifest.target_mod_id, registry):
        return PackFreshness("INCOMPATIBLE", (f"target_mod_id {pack.manifest.target_mod_id!r} is not installed/enabled in this install",))
    if not pack.manifest.source_hashes:
        return PackFreshness("CURRENT", ())
    matched, stale = [], []
    for key, recorded_hash in pack.manifest.source_hashes.items():
        current_hash = _current_source_hash(key, registry)
        if current_hash == recorded_hash:
            matched.append(key)
        else:
            stale.append(key)
    if not stale:
        return PackFreshness("CURRENT", ())
    if not matched:
        return PackFreshness("STALE", tuple(f"{key}: source has changed or no longer resolves" for key in stale))
    return PackFreshness("PARTIALLY_STALE", tuple(f"{key}: source has changed or no longer resolves" for key in stale))


@dataclass(frozen=True)
class ResolvedKnowledgePack:
    pack: KnowledgePack
    freshness: PackFreshness
    hull_archetypes: tuple[dict[str, Any], ...]
    retrofit_templates: tuple[dict[str, Any], ...]
    approved_equipment: tuple[dict[str, Any], ...]
    unresolved_references: tuple[str, ...]


def resolve_knowledge_pack(pack: KnowledgePack, registry: Registry) -> ResolvedKnowledgePack:
    """Degrade gracefully around entries whose hull_id no longer resolves.

    A pack referencing a hull id the current install doesn't have (a mod
    update removed it, or the target mod isn't installed at all) must not
    be rejected wholesale -- only the affected entries are dropped, and
    every drop is recorded in `unresolved_references` rather than
    silently disappearing.
    """
    freshness = assess_pack_freshness(pack, registry)
    unresolved: list[str] = []
    hull_archetypes = []
    for index, entry in enumerate(pack.raw.get("hull_archetypes", []) if isinstance(pack.raw.get("hull_archetypes"), list) else []):
        hull_id = entry.get("hull_id") if isinstance(entry, dict) else None
        if isinstance(hull_id, str) and hull_id in registry.hulls.by_id:
            hull_archetypes.append(entry)
        else:
            unresolved.append(f"hull_archetypes[{index}].hull_id={hull_id!r}")
    retrofit_templates = []
    for index, entry in enumerate(pack.raw.get("retrofit_templates", []) if isinstance(pack.raw.get("retrofit_templates"), list) else []):
        hull_id = entry.get("hull_id") if isinstance(entry, dict) else None
        if isinstance(hull_id, str) and hull_id in registry.hulls.by_id:
            retrofit_templates.append(entry)
        else:
            unresolved.append(f"retrofit_templates[{index}].hull_id={hull_id!r}")
    approved_equipment = []
    indexes = {
        "weapons": registry.weapons, "fighters": registry.fighters,
        "hullmods": registry.hullmods, "hulls": registry.hulls,
    }
    for index, entry in enumerate(pack.raw.get("approved_equipment", []) if isinstance(pack.raw.get("approved_equipment"), list) else []):
        kind = entry.get("kind") if isinstance(entry, dict) else None
        entity_id = entry.get("id") if isinstance(entry, dict) else None
        confidence = entry.get("confidence") if isinstance(entry, dict) else None
        valid_confidence = isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and math.isfinite(confidence) and 0.0 <= confidence <= 1.0
        if kind in indexes and isinstance(entity_id, str) and entity_id in indexes[kind].by_id and valid_confidence:
            approved_equipment.append(entry)
        else:
            unresolved.append(f"approved_equipment[{index}]={entity_id!r} ({kind!r})")
    return ResolvedKnowledgePack(pack, freshness, tuple(hull_archetypes), tuple(retrofit_templates), tuple(approved_equipment), tuple(unresolved))


def progression_hull_ids(pack: ResolvedKnowledgePack | None, faction_id: str, stage: str | None) -> tuple[str, ...]:
    """Return resolved, advisory progression hull IDs for a selected stage.

    This never supplies access or legality. Stale packs remain advisory but
    incompatible packs and unrecognized stages return no preference.
    """
    if pack is None or pack.pack.manifest.target_faction_id != faction_id or pack.freshness.status == "INCOMPATIBLE" or stage is None:
        return ()
    for entry in pack.pack.raw.get("progression_tiers", []) if isinstance(pack.pack.raw.get("progression_tiers"), list) else []:
        if isinstance(entry, dict) and entry.get("tier") == stage:
            return tuple(sorted({str(hull_id) for hull_id in entry.get("recommended_hull_ids", []) if isinstance(hull_id, str) and hull_id}))
    return ()


def progression_guidance_confidence(pack: ResolvedKnowledgePack | None, faction_id: str, stage: str | None) -> float | None:
    """Freshness-adjusted confidence for a resolved user-selected stage.

    Progression tiers intentionally contain no fabricated save-state or
    market-availability claim.  Their only confidence is therefore the pack
    freshness state, and only when the selected tier actually resolves to at
    least one current hull.  Consumers use this as advisory ranking evidence,
    never as a filter or legality input.
    """
    if not progression_hull_ids(pack, faction_id, stage):
        return None
    assert pack is not None
    return {"CURRENT": 1.0, "PARTIALLY_STALE": 0.75, "STALE": 0.5}.get(pack.freshness.status, 0.0)


def retrofit_template_ids(
    pack: ResolvedKnowledgePack | None,
    faction_id: str,
    hull_id: str,
    role: str,
) -> tuple[tuple[str, float], ...]:
    """Return resolved advisory retrofit-template references for one path.

    A v0.5 template names a hull and target role but does *not* contain a
    loadout.  It must therefore be surfaced as audit guidance alongside a
    mechanically generated Refit Assistant result, not applied as if it were
    executable fitting data.
    """
    if pack is None or pack.pack.manifest.target_faction_id != faction_id or pack.freshness.status == "INCOMPATIBLE":
        return ()
    multiplier = {"CURRENT": 1.0, "PARTIALLY_STALE": 0.75, "STALE": 0.5}.get(pack.freshness.status, 0.0)
    matches: list[tuple[str, float]] = []
    for entry in pack.retrofit_templates:
        if entry.get("hull_id") != hull_id or entry.get("target_role") != role or entry.get("category") != "RETROFIT":
            continue
        template_id, confidence = entry.get("id"), entry.get("confidence")
        if isinstance(template_id, str) and isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and math.isfinite(confidence):
            matches.append((template_id, max(0.0, min(1.0, float(confidence))) * multiplier))
    return tuple(sorted(matches))


def officer_guidance(pack: ResolvedKnowledgePack | None, faction_id: str) -> tuple[dict[str, Any], ...]:
    """Return validated, freshness-labelled advisory officer guidance.

    Packs describe officer suggestions for presentation; this project does
    not model officer skills as simulated ship stats.  Returning them
    separately prevents curated prose from becoming hidden score input.
    """
    if pack is None or pack.pack.manifest.target_faction_id != faction_id or pack.freshness.status == "INCOMPATIBLE":
        return ()
    multiplier = {"CURRENT": 1.0, "PARTIALLY_STALE": 0.75, "STALE": 0.5}.get(pack.freshness.status, 0.0)
    entries = pack.pack.raw.get("officer_guidance")
    if not isinstance(entries, list):
        return ()
    resolved: list[dict[str, Any]] = []
    for entry in entries:
        confidence = entry.get("confidence") if isinstance(entry, dict) else None
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not math.isfinite(confidence):
            continue
        copy = dict(entry)
        copy["guidance_confidence"] = max(0.0, min(1.0, float(confidence))) * multiplier
        resolved.append(copy)
    return tuple(resolved)


def approved_equipment_ids(pack: ResolvedKnowledgePack | None, faction_id: str, entity_kind: str) -> frozenset[str]:
    """Resolved advisory approvals for one faction and equipment kind.

    A pack applies only to its target faction and never if incompatible.  A
    stale pack remains advisory (per FACTION_KNOWLEDGE_PACKS.md section 12),
    so its explicitly resolved IDs remain available; consumers must expose
    its reduced guidance confidence separately.
    """
    if pack is None or pack.pack.manifest.target_faction_id != faction_id or pack.freshness.status == "INCOMPATIBLE":
        return frozenset()
    return frozenset(
        entry["id"] for entry in pack.approved_equipment
        if entry.get("kind") == entity_kind and isinstance(entry.get("id"), str)
    )


def equipment_guidance_confidence(pack: ResolvedKnowledgePack | None, faction_id: str, entity_kind: str, entity_id: str) -> float | None:
    """Return pack evidence confidence, reduced when its source is stale."""
    if entity_id not in approved_equipment_ids(pack, faction_id, entity_kind):
        return None
    assert pack is not None
    freshness_multiplier = {"CURRENT": 1.0, "PARTIALLY_STALE": 0.75, "STALE": 0.5}.get(pack.freshness.status, 0.0)
    for entry in pack.approved_equipment:
        if entry.get("kind") == entity_kind and entry.get("id") == entity_id:
            return float(entry["confidence"]) * freshness_multiplier
    return None


def capability_gap_guidance(pack: ResolvedKnowledgePack | None, faction_id: str, role: str) -> tuple[tuple[str, float], ...]:
    """Resolved advisory notes for one detected capability gap.

    The notes explain a curated doctrine context; they do not alter gap
    detection, legality, or ranking.  Returned confidence is the entry's
    declared confidence reduced by the same freshness policy used for
    approved equipment, so stale guidance stays visible but never appears
    equally certain as current evidence.
    """
    if pack is None or pack.pack.manifest.target_faction_id != faction_id or pack.freshness.status == "INCOMPATIBLE":
        return ()
    multiplier = {"CURRENT": 1.0, "PARTIALLY_STALE": 0.75, "STALE": 0.5}.get(pack.freshness.status, 0.0)
    entries = pack.pack.raw.get("capability_gap_guidance")
    if not isinstance(entries, list):
        return ()
    resolved: list[tuple[str, float]] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("role") != role:
            continue
        note, confidence = entry.get("notes"), entry.get("confidence")
        if not isinstance(note, str) or not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            continue
        confidence = float(confidence)
        if math.isfinite(confidence) and 0.0 <= confidence <= 1.0:
            resolved.append((note, confidence * multiplier))
    return tuple(resolved)


def build_archetype_preference(pack: ResolvedKnowledgePack | None, faction_id: str, build_id: str) -> tuple[float, float] | None:
    """Optional pack preference for an already mechanically inferred build.

    The first value is a 0..1 preference; the second is its freshness-adjusted
    evidence confidence.  This does not validate or create build paths.
    """
    if pack is None or pack.pack.manifest.target_faction_id != faction_id or pack.freshness.status == "INCOMPATIBLE":
        return None
    entries = pack.pack.raw.get("build_archetype_preferences")
    if not isinstance(entries, list):
        return None
    multiplier = {"CURRENT": 1.0, "PARTIALLY_STALE": 0.75, "STALE": 0.5}.get(pack.freshness.status, 0.0)
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("build_id") != build_id:
            continue
        preference, confidence = entry.get("preference"), entry.get("confidence")
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0.0 <= value <= 1.0 for value in (preference, confidence)):
            return float(preference), float(confidence) * multiplier
    return None
