"""Read-only scan reconciliation and direct analysis-impact planning.

This deliberately plans invalidation only.  It neither caches nor recomputes
analysis, and cannot write game/mod sources.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from starsector_variant_generator.adapters import (
    combat_hullmod_effects,
    defense_hullmod_effects,
    efficiency_hullmod_effects,
    flux_hullmod_effects,
    logistics_hullmod_effects,
    mobility_hullmod_effects,
)
from starsector_variant_generator.core.cache import build_manifest
from starsector_variant_generator.core.knowledge_packs import KnowledgePack
from starsector_variant_generator.core.models import ScanResult


@dataclass(frozen=True)
class EntityChange:
    category: str
    source_mod: str
    entity_id: str
    source_path: str
    status: str
    previous_hash: str | None
    current_hash: str | None


@dataclass(frozen=True)
class ImpactTarget:
    kind: str
    target_id: str
    certainty: str  # EXACT | CONSERVATIVE
    because: tuple[str, ...]


@dataclass(frozen=True)
class ChangeImpactReport:
    schema_version: str
    changes: tuple[EntityChange, ...]
    impacts: tuple[ImpactTarget, ...]
    warnings: tuple[str, ...]


def analyze_change_impact(previous_manifest: dict[str, Any] | None, current: ScanResult, knowledge_packs: tuple[KnowledgePack, ...] = ()) -> ChangeImpactReport:
    """Compare a prior cache manifest to a scan and plan direct invalidation."""
    prior = (previous_manifest or {}).get("entries", [])
    now = build_manifest(current)["entries"]
    # IDs are game-facing identifiers, not globally unique source records:
    # modules and alternate variants may deliberately share one within a mod.
    # A normalized source path makes the impact key stable without pretending
    # those legitimate duplicates are a parser conflict.
    key = lambda entry: (str(entry["category"]), str(entry["source_mod"]), str(entry["id"]), str(entry["source_path"]))
    old_groups: dict[tuple[str, str, str, str], list[dict]] = {}
    new_groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for entry in prior:
        old_groups.setdefault(key(entry), []).append(entry)
    for entry in now:
        new_groups.setdefault(key(entry), []).append(entry)
    changes: list[EntityChange] = []
    for entity_key in sorted(set(old_groups) | set(new_groups)):
        old, new = old_groups.get(entity_key, []), new_groups.get(entity_key, [])
        category, mod, entity_id, source_path = entity_key
        if len(old) > 1 or len(new) > 1:
            status = "CONFLICTED"
        elif not old:
            status = "ADDED"
        elif not new:
            status = "REMOVED"
        elif old[0] == new[0]:
            status = "UNCHANGED"
        else:
            status = "CHANGED"
        changes.append(EntityChange(category, mod, entity_id, source_path, status,
                                    old[0].get("source_hash") if len(old) == 1 else None,
                                    new[0].get("source_hash") if len(new) == 1 else None))
    impacts = _direct_impacts(tuple(changes), current, knowledge_packs)
    warnings = tuple(
        [f"Ambiguous canonical entity key: {change.category}:{change.source_mod}:{change.entity_id}:{change.source_path}" for change in changes if change.status == "CONFLICTED"]
        + [f"Removed {change.category}:{change.source_mod}:{change.entity_id}:{change.source_path} has no current reverse-reference evidence; dependent stale results require conservative review." for change in changes if change.status == "REMOVED"]
    )
    return ChangeImpactReport("change-impact-0.1", tuple(changes), impacts, warnings)


# --- Transitive-impact extensions (ROADMAP Phase 34, charter Priority 12) ---
#
# The reverse-index direct-variant impacts above (weapon/hullmod/fighter/hull
# id -> referencing variants -> hull/faction cascade) answer "which existing
# variants/hulls/factions equip this id". These three additions are
# deliberately separate, additive evidence categories rather than a
# restructuring of that system: each answers a different, independently
# citable "does X really depend on this id" question that the variant-based
# cascade cannot see at all, since none of the three requires a variant to
# exist.

# A changed hull/weapon/hullmod/fighter id may be evidenced as impacting a
# faction directly through that faction's own declared known_* tuple, with
# no dependency on any variant referencing it. This closes a real gap in the
# existing cascade: today, a faction's known_hulls/known_weapons/etc. entry
# only produces a faction_capability_profile/gap_recommendations impact when
# some variant *also* happens to reference the same hull -- so a faction
# that lists a hull/weapon/hullmod/fighter with zero referencing variants
# (a real, legal state; `Registry.resolve_faction`'s SVG-015 merge fix, see
# ROADMAP Phase 2, makes a faction's real known-equipment set larger and
# more accurate than before, increasing how often this happens) produced no
# faction impact evidence at all. Kept as a new "faction_known_list" kind
# rather than folded into the existing "faction_capability_profile"/
# "gap_recommendations" kinds so this evidence is never conflated with the
# pre-existing, separately golden-tested variant-cascade evidence.
_CATEGORY_TO_FACTION_KNOWN_ATTR: dict[str, str] = {
    "hulls": "known_hulls",
    "weapons": "known_weapons",
    "hullmods": "known_hullmods",
    "fighters": "known_fighters",
}


def _pack_references_entity(pack: KnowledgePack, category: str, entity_id: str) -> bool:
    """True if `pack.raw`'s own curated content cites `entity_id`.

    Distinct from the existing `knowledge_pack_freshness` impact below:
    freshness compares the pack's *recorded* `manifest.source_hashes` entry
    for an id against the id's current source hash, which only ever fires
    for ids the pack author explicitly chose to hash. This instead reads the
    pack's actual guidance content -- `hull_archetypes`, `retrofit_templates`,
    `approved_equipment`, `progression_tiers` -- for a live reference to the
    id, so a real content dependency is evidenced even when the author never
    recorded a source hash for it. Mirrors the same defensive,
    isinstance-checked parsing `core/knowledge_packs.py::resolve_knowledge_pack`
    already uses for this exact raw shape; kept read-only and Registry-free
    here since this module only cites identifiers, never resolves them.
    """
    raw = pack.raw
    if category == "factions":
        return pack.manifest.target_faction_id == entity_id
    if category == "hulls":
        for entry in raw.get("hull_archetypes", []) if isinstance(raw.get("hull_archetypes"), list) else []:
            if isinstance(entry, dict) and entry.get("hull_id") == entity_id:
                return True
        for entry in raw.get("retrofit_templates", []) if isinstance(raw.get("retrofit_templates"), list) else []:
            if isinstance(entry, dict) and entry.get("hull_id") == entity_id:
                return True
        for entry in raw.get("progression_tiers", []) if isinstance(raw.get("progression_tiers"), list) else []:
            if isinstance(entry, dict):
                recommended = entry.get("recommended_hull_ids")
                if isinstance(recommended, list) and entity_id in recommended:
                    return True
    if category in ("weapons", "fighters", "hullmods", "hulls"):
        for entry in raw.get("approved_equipment", []) if isinstance(raw.get("approved_equipment"), list) else []:
            if isinstance(entry, dict) and entry.get("kind") == category and entry.get("id") == entity_id:
                return True
    return False


# A changed hullmod id may be evidenced as adapter-modeled: it literally
# appears as a `hullmod_id` field in one of the citable, hand-researched
# `adapters/vanilla` effect tables (ROADMAP Phase 4). A covered hullmod's
# change has a materially larger, precisely-citable blast radius than an
# uncovered one -- every derived-stat consumer that reads that table
# (analysis/civilian.py, combat_stats.py, flux_stats.py, mobility_stats.py,
# weapon_range_stats.py, generation/vent_cap.py, generation/refit.py)
# recomputes a different concrete number, not just a generic "this hullmod
# exists" fact. An uncovered hullmod produces no adapter_coverage impact at
# all -- never inferred, only reported when the id is genuinely present.
_HULLMOD_ADAPTER_EFFECT_TABLES: tuple[tuple[str, Callable[[str], tuple[Any, ...]]], ...] = (
    ("LOGISTICS_HULLMOD_EFFECTS", logistics_hullmod_effects),
    ("EFFICIENCY_HULLMOD_EFFECTS", efficiency_hullmod_effects),
    ("DEFENSE_HULLMOD_EFFECTS", defense_hullmod_effects),
    ("MOBILITY_HULLMOD_EFFECTS", mobility_hullmod_effects),
    ("FLUX_HULLMOD_EFFECTS", flux_hullmod_effects),
    ("COMBAT_HULLMOD_EFFECTS", combat_hullmod_effects),
)


def _adapter_tables_covering(source_mod: str, hullmod_id: str) -> tuple[str, ...]:
    """Return which of `source_mod`'s adapter effect tables model `hullmod_id`."""
    return tuple(
        table_name
        for table_name, lookup in _HULLMOD_ADAPTER_EFFECT_TABLES
        if any(getattr(effect, "hullmod_id", None) == hullmod_id for effect in lookup(source_mod))
    )


def _direct_impacts(changes: tuple[EntityChange, ...], scan: ScanResult, knowledge_packs: tuple[KnowledgePack, ...]) -> tuple[ImpactTarget, ...]:
    targets: dict[tuple[str, str, str], set[str]] = {}
    def add(kind: str, target_id: str, because: str, certainty: str = "EXACT") -> None:
        targets.setdefault((kind, target_id, certainty), set()).add(because)
    changed = [change for change in changes if change.status != "UNCHANGED"]
    # Reverse-index which variants reference each weapon/hullmod/fighter/hull
    # id, built once up front instead of re-scanning every variant per
    # changed entity. Measured on the real 148-mod install (~14k entities,
    # ~6.6k variants): the old per-change `[v for v in scan.variants if ...]`
    # scans made this function O(changed_entities x variants) -- 6.98s of a
    # cold scan's real 8.5s total, ~17.9M `dict.values()` calls alone from
    # the weapons branch. This makes it O(variants x mounts + changed_entities).
    # A variant referencing the same weapon/hullmod/fighter id more than once
    # (e.g. two mounts with the same weapon) may be appended more than once
    # here; `add()` below is a set-union per (kind, target_id, certainty), so
    # duplicate entries are idempotent and do not change the result -- same
    # as the original `in variant.weapons_by_mount.values()` membership test,
    # which also collapsed duplicates to a single inclusion.
    categories_present = {change.category for change in changed}

    # Reverse-index for the faction_known_list extension (see its module-level
    # comment above), mirroring the exact same "measure before optimizing"
    # precedent as ROADMAP Phase 8's `_ownership_index`: an initial version
    # of this loop did `for faction in scan.factions: if entity_id in
    # getattr(faction, known_attr)` once per changed entity -- a real,
    # profiled hotspot at realistic scale (431 factions x ~100-150 known
    # entries). Building one id -> [faction_id] index per relevant known_*
    # category up front, instead of rescanning every faction's tuple per
    # changed entity, makes each per-change lookup O(1) average.
    #
    # This also feeds the *pre-existing* variant-cascade loop below (`for
    # faction in scan.factions: if variant.hull_id in faction.known_hulls`,
    # from before Phase 34), which profiling of the same stress scenario
    # showed was the real dominant cost -- an existing O(matched_variants x
    # factions) scan that a burst of weapon/hullmod/fighter changes (each
    # cascading through many variants) can reach even when no hull entity
    # itself changed. So the "hulls" known-list index is built whenever the
    # variant cascade can run at all (any of weapons/hullmods/fighters/hulls
    # changed), not only when a hull itself did; the resulting hull ->
    # faction lookup is reused for both purposes below, replacing that inner
    # per-variant faction scan with the same O(1)-average lookup. This is
    # confirmed output-identical against the golden-output regression test
    # (`tests/test_change_impact.py`) -- a performance fix only, no change
    # to which impacts are produced.
    known_index: dict[str, dict[str, list[str]]] = {}
    _needs_variant_cascade = bool(categories_present & {"weapons", "hullmods", "fighters", "hulls"})
    _known_categories_to_index = categories_present & set(_CATEGORY_TO_FACTION_KNOWN_ATTR)
    if _needs_variant_cascade:
        _known_categories_to_index = _known_categories_to_index | {"hulls"}
    for category in _known_categories_to_index:
        attr = _CATEGORY_TO_FACTION_KNOWN_ATTR[category]
        index: dict[str, list[str]] = {}
        for faction in scan.factions:
            for entity_id in getattr(faction, attr):
                index.setdefault(entity_id, []).append(faction.id)
        known_index[category] = index
    hull_to_factions = known_index.get("hulls", {})

    weapon_to_variants: dict[str, list] = {}
    hullmod_to_variants: dict[str, list] = {}
    fighter_to_variants: dict[str, list] = {}
    hull_to_variants: dict[str, list] = {}
    if categories_present & {"weapons", "hullmods", "fighters", "hulls"}:
        need_weapons = "weapons" in categories_present
        need_hullmods = "hullmods" in categories_present
        need_fighters = "fighters" in categories_present
        need_hulls = "hulls" in categories_present
        for variant in scan.variants:
            if need_weapons:
                for weapon_id in variant.weapons_by_mount.values():
                    weapon_to_variants.setdefault(weapon_id, []).append(variant)
            if need_hullmods:
                for hullmod_id in variant.hullmods:
                    hullmod_to_variants.setdefault(hullmod_id, []).append(variant)
            if need_fighters:
                for fighter_id in variant.fighter_wings:
                    fighter_to_variants.setdefault(fighter_id, []).append(variant)
            if need_hulls and variant.hull_id:
                hull_to_variants.setdefault(variant.hull_id, []).append(variant)
    for change in changed:
        token = f"{change.status}:{change.category}:{change.source_mod}:{change.entity_id}:{change.source_path}"

        # Transitive extension 1: faction known-list impact (evaluated for
        # every change regardless of category, so it still fires for the
        # "factions" category's own early `continue` below). Looked up
        # against the reverse index built above, not a per-faction scan.
        for faction_id in known_index.get(change.category, {}).get(change.entity_id, ()):
            add("faction_known_list", faction_id, token)

        # Transitive extension 2: knowledge-pack content-reference impact.
        for pack in knowledge_packs:
            if _pack_references_entity(pack, change.category, change.entity_id):
                add("knowledge_pack_reference", str(pack.path), token)

        # Transitive extension 3: adapter-table coverage impact (hullmods only
        # -- LOGISTICS/EFFICIENCY/DEFENSE/MOBILITY/FLUX/COMBAT effect tables
        # are all keyed on hullmod_id; no other category has an adapter table).
        if change.category == "hullmods":
            for table_name in _adapter_tables_covering(change.source_mod, change.entity_id):
                add("adapter_coverage", change.entity_id, f"{token} (adapter_table={table_name})")

        if change.category == "weapons":
            add("weapon_profile", change.entity_id, token)
            variants = weapon_to_variants.get(change.entity_id, [])
        elif change.category == "hullmods":
            variants = hullmod_to_variants.get(change.entity_id, [])
        elif change.category == "fighters":
            variants = fighter_to_variants.get(change.entity_id, [])
        elif change.category == "hulls":
            add("mechanical_profile", change.entity_id, token); add("build_archetype_profile", change.entity_id, token)
            variants = hull_to_variants.get(change.entity_id, [])
        elif change.category == "factions":
            add("faction_capability_profile", change.entity_id, token); add("gap_recommendations", change.entity_id, token)
            continue
        else:
            variants = []
        pack_kind = {"factions": "faction", "hulls": "hull", "weapons": "weapon", "hullmods": "hullmod", "fighters": "fighter"}.get(change.category)
        if pack_kind:
            for pack in knowledge_packs:
                if f"{pack_kind}:{change.entity_id}" in pack.manifest.source_hashes:
                    add("knowledge_pack_freshness", str(pack.path), token)
        if change.status == "REMOVED":
            add("scan_analysis_review", f"{change.category}:{change.source_mod}:{change.entity_id}:{change.source_path}", token, "CONSERVATIVE")
        for variant in variants:
            add("variant_analysis", variant.id, token)
            if variant.hull_id:
                add("mechanical_profile", variant.hull_id, token); add("build_archetype_profile", variant.hull_id, token)
                for faction_id in hull_to_factions.get(variant.hull_id, ()):
                    add("faction_capability_profile", faction_id, token); add("gap_recommendations", faction_id, token)
    return tuple(ImpactTarget(kind, target_id, certainty, tuple(sorted(reasons))) for (kind, target_id, certainty), reasons in sorted(targets.items()))
