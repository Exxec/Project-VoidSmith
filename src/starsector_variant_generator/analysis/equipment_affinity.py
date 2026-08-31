"""Equipment affinity classification: EQUIPMENT_ACCESS_AND_AUTOFIT.md sections 2, 5-6, 8, first slice.

Real per-faction `known_weapons`/`known_fighters`/`known_hullmods`/
`known_hulls` lists are the "faction data references" and "broad usage
across factions" evidence tiers section 8 names -- all already parsed
and indexed by `Registry`. `APPROVED` is produced only from a resolved,
target-faction knowledge-pack approval; `RESTRICTED` and `UNKNOWN` still
need their respective evidence layers. Never infers affinity from
`source_mod_id` alone (section 8's explicit warning): only real
faction-list membership is consulted.

`entity_kind="hulls"` (root ROADMAP.md Phase 10's acquisition search)
reuses this exact same mechanism against `Faction.known_hulls` -- a hull
is real faction-ownership evidence in precisely the same shape as a
weapon/fighter/hullmod, so no separate classifier was warranted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.knowledge_packs import (
    ResolvedKnowledgePack,
    approved_equipment_ids,
    equipment_guidance_confidence,
)
from starsector_variant_generator.core.models import Entity, Faction, Hullmod
from starsector_variant_generator.core.registry import Registry

# Cache attribute name for the per-registry reverse ownership index built by
# `_ownership_index` below. Stored directly on the `Registry` instance
# (a plain, unfrozen dataclass with no `__slots__`) rather than in a
# module-level dict keyed by `id(registry)`, so its lifetime is tied
# exactly to the registry object's own lifetime -- no separate cache to
# leak or go stale. Safe because nothing in this codebase ever mutates
# `registry.factions` after `Registry.from_scan()` returns (verified by
# grep across `src/`); `run_incremental_mod_scan` always builds a fresh
# `Registry` rather than mutating an existing one.
_OWNERSHIP_INDEX_ATTR = "_equipment_ownership_index_cache"

EntityKind = str  # "weapons" | "fighters" | "hullmods" | "hulls"

_KNOWN_ID_SELECTORS: dict[str, Callable[[Faction], tuple[str, ...]]] = {
    "weapons": lambda faction: faction.known_weapons,
    "fighters": lambda faction: faction.known_fighters,
    "hullmods": lambda faction: faction.known_hullmods,
    "hulls": lambda faction: faction.known_hulls,
}


@dataclass(frozen=True)
class EquipmentAffinityClassification:
    entity_id: str
    entity_kind: str
    affinity: str  # "NATIVE" | "APPROVED" | "COMMON" | "FOREIGN" | "UNALIGNED"
    owning_faction_ids: tuple[str, ...]
    guidance_confidence: float | None = None
    # ROADMAP.md Phase 29 (Evidence/Provenance Unification): every tier
    # here (NATIVE/COMMON/FOREIGN/UNALIGNED) is real faction `known_*`-list
    # membership -- a fact read directly from already-parsed source data,
    # so `DIRECT_DATA` -- except `APPROVED`, which comes from a resolved,
    # human-authored knowledge-pack entry (`approved_equipment_ids`), the
    # shared vocabulary's `CURATED_GUIDANCE` class. Set explicitly per
    # classification below rather than left at a single static default,
    # since the two real evidence shapes genuinely differ.
    evidence_class: EvidenceClass = EvidenceClass.DIRECT_DATA


def classify_equipment_availability(entity: Entity) -> str:
    """Classify only explicit local availability evidence.

    Standard Starsector data does not offer a universal availability field,
    so absence of a recognized local tag is deliberately `UNKNOWN`, not
    `STANDARD`.  The scanner never promotes source-mod ownership, UI names,
    or unrecognized tags into an availability claim.
    """
    tags = {str(tag).upper() for tag in entity.raw.get("tags", ())} if isinstance(entity.raw, dict) else set()
    if isinstance(entity, Hullmod) and entity.built_in_only:
        return "UNOBTAINABLE"
    if "UNOBTAINABLE" in tags:
        return "UNOBTAINABLE"
    if "DEV_ONLY" in tags or "DEV" in tags:
        return "DEV_ONLY"
    if isinstance(entity, Hullmod) and entity.hidden:
        return "SECRET"
    if "SECRET" in tags or "HIDDEN" in tags:
        return "SECRET"
    if "RARE" in tags:
        return "RARE"
    if "COMMON" in tags:
        return "COMMON"
    if "STANDARD" in tags:
        return "STANDARD"
    return "UNKNOWN"


def _all_factions(registry: Registry) -> list[Faction]:
    factions = list(registry.factions.by_id.values())
    for duplicate_group in registry.factions.duplicates.values():
        factions.extend(duplicate_group)
    return factions


def _ownership_index(registry: Registry) -> dict[str, dict[str, tuple[str, ...]]]:
    """Reverse index: entity_kind -> {entity_id: sorted tuple of owning faction ids}.

    `classify_equipment_affinity` used to call `_all_factions(registry)`
    and linear-scan every faction's `known_*` tuple on EVERY call --
    O(entities x factions) across a whole `svg query weapons/fighters/
    hullmods` pass, `run_slot_eligible_weapons`'s STRICT_FACTION filter,
    or `gap_recommendation.py::recommend_acquisition_solutions`'s single
    pass over every indexed hull. Measured on the real 148-mod install
    (2996 hulls, 120 factions): profiling `run_gap_recommendations` for a
    real faction (ttc_arkgneisis, 33 known hulls) showed
    `classify_equipment_affinity` plus its `_all_factions` rebuild costing
    0.090s of that call's 0.206s cProfile time from 1938 calls, each
    re-scanning all 120 factions' known-id tuples from scratch.

    Built once per `Registry` (O(factions x known-id count) total) and
    cached on that instance -- see `_OWNERSHIP_INDEX_ATTR` above for why
    instance-lifetime caching is safe here. A faction that appears more
    than once for the same id (an unresolved duplicate-id collision, see
    `core/registry.py::EntityIndex`) still contributes its own known-id
    evidence to the union, exactly as the original per-call scan over
    `_all_factions(registry)` did -- multiple faction instances sharing an
    id simply collapse to one entry in the owning-id set below, same as
    the original set-comprehension did.
    """
    cached = getattr(registry, _OWNERSHIP_INDEX_ATTR, None)
    if cached is not None:
        return cached
    index: dict[str, dict[str, set[str]]] = {kind: {} for kind in _KNOWN_ID_SELECTORS}
    for faction in _all_factions(registry):
        for kind, selector in _KNOWN_ID_SELECTORS.items():
            for entity_id in selector(faction):
                index[kind].setdefault(entity_id, set()).add(faction.id)
    built: dict[str, dict[str, tuple[str, ...]]] = {
        kind: {entity_id: tuple(sorted(owner_ids)) for entity_id, owner_ids in entity_map.items()}
        for kind, entity_map in index.items()
    }
    setattr(registry, _OWNERSHIP_INDEX_ATTR, built)
    return built


def classify_equipment_affinity(
    entity_id: str,
    entity_kind: EntityKind,
    registry: Registry,
    requesting_faction_id: str | None = None,
    common_threshold: int = 4,
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> EquipmentAffinityClassification:
    """Classify one weapon/fighter/hullmod's real faction ownership evidence.

    `common_threshold` (how many distinct factions' known_* lists must
    reference an item before it's COMMON rather than FOREIGN) is a
    judgment call, not a documented game mechanic -- there is no vanilla
    "commonality" concept to verify against. Kept as a caller-overridable
    parameter rather than a versioned heuristic, since it classifies
    provenance evidence, not a quality/legality outcome the
    `core/heuristics.py` registry is scoped to.
    """
    if entity_kind not in _KNOWN_ID_SELECTORS:
        raise ValueError(f"Unknown entity_kind for affinity classification: {entity_kind!r}")
    owners = _ownership_index(registry)[entity_kind].get(entity_id, ())
    approved = requesting_faction_id is not None and entity_id in approved_equipment_ids(knowledge_pack, requesting_faction_id, entity_kind)
    if requesting_faction_id is not None and requesting_faction_id in owners:
        affinity = "NATIVE"
    elif approved:
        affinity = "APPROVED"
    elif not owners:
        affinity = "UNALIGNED"
    elif len(owners) >= common_threshold:
        affinity = "COMMON"
    else:
        affinity = "FOREIGN"
    # `approved`'s own definition above already requires
    # `requesting_faction_id is not None`; restated directly here (rather
    # than branching on `approved` alone) so the type checker can narrow
    # `requesting_faction_id` for this call too.
    confidence = (
        equipment_guidance_confidence(knowledge_pack, requesting_faction_id, entity_kind, entity_id)
        if approved and requesting_faction_id is not None else None
    )
    return EquipmentAffinityClassification(
        entity_id, entity_kind, affinity, owners,
        confidence,
        evidence_class=EvidenceClass.CURATED_GUIDANCE if approved else EvidenceClass.DIRECT_DATA,
    )
