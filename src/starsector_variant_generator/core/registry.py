from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import re
from typing import Generic, Iterable, TypeVar

from starsector_variant_generator.core.models import Entity, Faction, ModInfo, ScanResult, Variant


T = TypeVar("T", bound=Entity)


@dataclass
class EntityIndex(Generic[T]):
    """Deterministic ID index that never resolves duplicate IDs by guessing."""

    by_id: dict[str, T] = field(default_factory=dict)
    duplicates: dict[str, list[T]] = field(default_factory=dict)

    @classmethod
    def build(cls, entities: Iterable[T]) -> "EntityIndex[T]":
        index = cls()
        for entity in entities:
            if entity.id in index.duplicates:
                # A third-or-later claimant of an already-ambiguous id. The
                # original two-branch version only ever populated
                # `duplicates` from the `by_id` branch below, so this case
                # (id already fully moved into `duplicates`, `by_id` no
                # longer holding it) matched neither branch and silently
                # dropped every claimant past the second -- verified against
                # a real install where "hegemony" has three real sources
                # (core, plus two unrelated mods each shipping a same-id
                # `hegemony.faction` patch file).
                index.duplicates[entity.id].append(entity)
            elif entity.id in index.by_id:
                index.duplicates[entity.id] = [index.by_id.pop(entity.id), entity]
            else:
                index.by_id[entity.id] = entity
        return index


@dataclass(frozen=True)
class UnresolvedReference:
    variant_id: str
    reference_type: str
    reference_id: str


@dataclass(frozen=True)
class MissingDependency:
    mod_id: str
    dependency_id: str


@dataclass(frozen=True)
class CanonicalDuplicateResolution:
    """A duplicate ID safely collapsed only after semantic equality succeeds."""

    entity_type: str
    entity_id: str
    canonical_source_mod: str
    equivalent_source_mods: tuple[str, ...]
    semantic_hash: str
    resolution_reason: str = "CANONICALIZED_DUPLICATE"


@dataclass(frozen=True)
class DuplicateIdentity:
    """Global duplicate state, independent of any individual reference."""

    entity_type: str
    entity_id: str
    identity_status: str  # DUPLICATE_IDENTICAL | DUPLICATE_DIVERGENT
    sources: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ContextualReferenceResolution:
    variant_id: str
    reference_type: str
    reference_id: str
    selected_source_mod: str
    resolution_method: str
    identity_status: str
    shadowed_contextual_candidates: tuple[dict[str, str], ...]


@dataclass
class Registry:
    hulls: EntityIndex = field(default_factory=EntityIndex)
    weapons: EntityIndex = field(default_factory=EntityIndex)
    fighters: EntityIndex = field(default_factory=EntityIndex)
    hullmods: EntityIndex = field(default_factory=EntityIndex)
    variants: EntityIndex = field(default_factory=EntityIndex)
    factions: EntityIndex = field(default_factory=EntityIndex)
    unresolved_references: list[UnresolvedReference] = field(default_factory=list)
    missing_dependencies: list[MissingDependency] = field(default_factory=list)
    canonical_duplicate_resolutions: list[CanonicalDuplicateResolution] = field(default_factory=list)
    duplicate_identities: list[DuplicateIdentity] = field(default_factory=list)
    contextual_reference_resolutions: list[ContextualReferenceResolution] = field(default_factory=list)
    mod_dependencies: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_scan(cls, scan: ScanResult) -> "Registry":
        registry = cls(
            hulls=EntityIndex.build(scan.hulls), weapons=EntityIndex.build(scan.weapons),
            fighters=EntityIndex.build(scan.fighters), hullmods=EntityIndex.build(scan.hullmods),
            variants=EntityIndex.build(scan.variants), factions=EntityIndex.build(scan.factions),
            mod_dependencies={mod.mod_id: tuple(mod.dependencies) for mod in scan.mods},
        )
        registry._canonicalize_equivalent_hullmods()
        registry._resolve_variants(scan.variants)
        registry._resolve_dependencies(scan.mods)
        return registry

    @staticmethod
    def _semantic_hullmod_payload(entity: Entity) -> dict:
        """Compare parsed hullmod meaning, never source provenance.

        A mod can carry a byte-for-byte-compatible copy of a core hullmod
        table. Treating that as an ambiguous reference makes ordinary variants
        fail resolution. This deliberately applies only when every parsed
        semantic field, including the preserved raw row, agrees exactly.
        """
        payload = asdict(entity)
        for field_name in ("source_mod", "source_path", "source_hash", "source_mod_version"):
            payload.pop(field_name, None)
        return Registry._normalize_semantic_value(payload)

    @staticmethod
    def _normalize_semantic_value(value: object) -> object:
        """Make harmless source formatting differences non-semantic."""
        if isinstance(value, str):
            return re.sub(r"\s+", " ", value).strip()
        if isinstance(value, dict):
            return {str(key): Registry._normalize_semantic_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
        if isinstance(value, (list, tuple)):
            return [Registry._normalize_semantic_value(item) for item in value]
        return value

    @classmethod
    def _semantic_hullmod_hash(cls, entity: Entity) -> str:
        payload = cls._semantic_hullmod_payload(entity)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _canonicalize_equivalent_hullmods(self) -> None:
        for entity_id, candidates in list(self.hullmods.duplicates.items()):
            payloads = [self._semantic_hullmod_payload(candidate) for candidate in candidates]
            semantic_hashes = tuple(self._semantic_hullmod_hash(candidate) for candidate in candidates)
            identical = bool(payloads) and all(payload == payloads[0] for payload in payloads[1:])
            self.duplicate_identities.append(DuplicateIdentity(
                "hullmod", entity_id,
                "DUPLICATE_IDENTICAL" if identical else "DUPLICATE_DIVERGENT",
                tuple({"source_mod": candidate.source_mod, "semantic_hash": semantic_hash}
                      for candidate, semantic_hash in sorted(zip(candidates, semantic_hashes), key=lambda pair: pair[0].source_mod)),
            ))
            if not identical:
                continue
            canonical = min(candidates, key=lambda item: (item.source_mod != "core", item.source_mod, str(item.source_path)))
            self.hullmods.by_id[entity_id] = canonical
            del self.hullmods.duplicates[entity_id]
            self.canonical_duplicate_resolutions.append(CanonicalDuplicateResolution(
                "hullmod", entity_id, canonical.source_mod,
                tuple(sorted(candidate.source_mod for candidate in candidates)),
                semantic_hashes[candidates.index(canonical)],
            ))

    def _dependency_closure(self, mod_id: str) -> set[str]:
        """The requesting mod and its declared dependencies, recursively."""
        closure: set[str] = {mod_id}
        pending = list(self.mod_dependencies.get(mod_id, ()))
        while pending:
            dependency = pending.pop()
            if dependency in closure:
                continue
            closure.add(dependency)
            pending.extend(self.mod_dependencies.get(dependency, ()))
        return closure

    def _contextual_duplicate_candidate(self, candidates: list[Entity], requesting_mod: str | None) -> tuple[Entity | None, str | None]:
        """Resolve a duplicate only in the requesting mod's declared scope.

        A bare duplicate remains ambiguous.  A variant, however, has source
        provenance: an unrelated mod's replacement table must not make that
        variant's core/dependency reference unresolved.  This selects an
        explicit local/dependency claimant when unique, then core as the
        game's base fallback; ties remain ambiguous.
        """
        if not requesting_mod:
            return None, None
        scope = self._dependency_closure(requesting_mod)
        same_mod = [item for item in candidates if item.source_mod == requesting_mod]
        if len(same_mod) == 1:
            return same_mod[0], "SAME_MOD"
        if len(same_mod) > 1:
            return None, None
        dependencies = [item for item in candidates if item.source_mod in scope and item.source_mod not in {requesting_mod, "core"}]
        if len(dependencies) == 1:
            return dependencies[0], "DEPENDENCY"
        if len(dependencies) > 1:
            return None, None
        core = [item for item in candidates if item.source_mod == "core"]
        return (core[0], "CONTEXTUAL_CORE_FALLBACK") if len(core) == 1 else (None, None)

    def trace_reference(self, reference_type: str, reference_id: str, requesting_mod: str | None = None) -> dict[str, object]:
        """Return an explicit generic index trace for diagnostics/qualification."""
        indexes = {"hull": self.hulls, "weapon": self.weapons, "fighter": self.fighters, "hullmod": self.hullmods}
        index = indexes.get(reference_type)
        if index is None:
            raise ValueError(f"Unsupported reference type: {reference_type}")
        resolved = index.by_id.get(reference_id)
        duplicates = index.duplicates.get(reference_id, [])
        # Only hullmods use provenance-scoped fallback today. Their script
        # implementation is separately surfaced as modeled/unknown, while a
        # hull or weapon choice changes concrete fit legality and must retain
        # the existing strict ambiguity diagnostic until load-order semantics
        # are explicitly modeled.
        contextual, resolution_method = (
            self._contextual_duplicate_candidate(duplicates, requesting_mod)
            if resolved is None and reference_type == "hullmod" else (None, None)
        )
        if contextual is not None:
            resolved = contextual
        duplicate_sources = tuple(sorted(item.source_mod for item in duplicates))
        canonical = next((item for item in self.canonical_duplicate_resolutions
                          if item.entity_type == reference_type and item.entity_id == reference_id), None)
        identity = next((item for item in self.duplicate_identities
                         if item.entity_type == reference_type and item.entity_id == reference_id), None)
        shadowed = tuple(
            {"source_mod": item.source_mod, "semantic_hash": self._semantic_hullmod_hash(item), "exclusion_reason": "NOT_CONTEXT_RELEVANT"}
            for item in duplicates if contextual is not None and item != contextual
        ) if reference_type == "hullmod" else ()
        return {
            "reference_type": reference_type, "reference_id": reference_id,
            "requesting_mod": requesting_mod,
            "status": ("RESOLVED_CONTEXTUAL" if contextual is not None else "RESOLVED") if resolved is not None else ("AMBIGUOUS_CONFLICT" if duplicate_sources else "MISSING"),
            "resolved_source_mod": resolved.source_mod if resolved else None,
            "resolution_method": resolution_method or ("CANONICALIZED_DUPLICATE" if canonical else "EXACT_SOURCE" if resolved else "AMBIGUOUS" if duplicate_sources else "UNRESOLVED"),
            "identity_status": identity.identity_status if identity else "UNIQUE",
            "duplicate_source_mods": duplicate_sources,
            "canonical_duplicate_resolution": asdict(canonical) if canonical else None,
            "shadowed_contextual_candidates": shadowed,
        }

    def _resolve_variants(self, variants: Iterable[Variant]) -> None:
        for variant in variants:
            if variant.hull_id:
                self._resolve_variant_reference(variant, "hull", variant.hull_id)
            for weapon_id in variant.weapons_by_mount.values():
                self._resolve_variant_reference(variant, "weapon", weapon_id)
            for hullmod_id in variant.hullmods:
                self._resolve_variant_reference(variant, "hullmod", hullmod_id)

    def _resolve_variant_reference(self, variant: Variant, reference_type: str, reference_id: str) -> None:
        trace = self.trace_reference(reference_type, reference_id, variant.source_mod)
        if trace["status"] not in {"RESOLVED", "RESOLVED_CONTEXTUAL"}:
            self.unresolved_references.append(UnresolvedReference(variant.id, reference_type, reference_id))
            return
        if trace["status"] == "RESOLVED_CONTEXTUAL":
            self.contextual_reference_resolutions.append(ContextualReferenceResolution(
                variant.id, reference_type, reference_id, str(trace["resolved_source_mod"]),
                str(trace["resolution_method"]), str(trace["identity_status"]),
                tuple(trace["shadowed_contextual_candidates"]),
            ))

    def _resolve_dependencies(self, mods: Iterable[ModInfo]) -> None:
        mod_list = list(mods)
        available = {mod.mod_id for mod in mod_list}
        for mod in mod_list:
            for dependency in mod.dependencies:
                if dependency not in available:
                    self.missing_dependencies.append(MissingDependency(mod.mod_id, dependency))

    def weapons_matching(self, size: str | None = None, mount_type: str | None = None) -> tuple[Entity, ...]:
        """Return only unambiguous indexed weapons matching explicit fields."""
        normalized_size = size.upper() if size else None
        normalized_type = mount_type.upper() if mount_type else None
        return tuple(
            weapon for weapon in sorted(self.weapons.by_id.values(), key=lambda item: item.id)
            if (normalized_size is None or (getattr(weapon, "size", "") or "").upper() == normalized_size)
            and (normalized_type is None or (getattr(weapon, "mount_type", "") or "").upper() == normalized_type)
        )

    def fighters_matching(self, role: str | None = None) -> tuple[Entity, ...]:
        """Return only unambiguous indexed fighter wings matching explicit fields."""
        normalized_role = role.upper() if role else None
        return tuple(
            fighter for fighter in sorted(self.fighters.by_id.values(), key=lambda item: item.id)
            if normalized_role is None or (getattr(fighter, "role", "") or "").upper() == normalized_role
        )

    def hullmods_matching(self, hidden: bool | None = None) -> tuple[Entity, ...]:
        """Return only unambiguous indexed hullmods matching explicit fields."""
        return tuple(
            hullmod for hullmod in sorted(self.hullmods.by_id.values(), key=lambda item: item.id)
            if hidden is None or bool(getattr(hullmod, "hidden", False)) == hidden
        )

    def hulls_matching(self, hull_size: str | None = None) -> tuple[Entity, ...]:
        """Return only unambiguous indexed hulls matching explicit fields."""
        normalized_size = hull_size.upper() if hull_size else None
        return tuple(
            hull for hull in sorted(self.hulls.by_id.values(), key=lambda item: item.id)
            if normalized_size is None or (getattr(hull, "hull_size", "") or "").upper() == normalized_size
        )

    def variants_for_hull(self, hull_id: str) -> tuple[Variant, ...]:
        return tuple(sorted((variant for variant in self.variants.by_id.values() if variant.hull_id == hull_id), key=lambda item: item.id))

    def _faction_candidates(self, faction_id: str) -> list[Faction]:
        return ([self.factions.by_id[faction_id]] if faction_id in self.factions.by_id
                else list(self.factions.duplicates.get(faction_id, [])))

    def resolve_faction(self, faction_id: str, source_mod: str | None = None) -> Faction | None:
        """Resolve a faction id to a single `Faction`, merging same-id sources.

        Starsector mods commonly ship a partial `<id>.faction` file that
        patches an existing faction (for example adding new hulls to
        Hegemony's `knownShips`) rather than redefining it from scratch --
        these collide on id under `EntityIndex.build`'s duplicate handling,
        which would otherwise make the whole faction id unresolvable and
        silently drop every known_* entry a patch file contributes (see
        docs/BUGS.md). When `source_mod` is not given, same-id candidates
        are merged: known_hulls/known_weapons/known_fighters/known_hullmods
        are unioned -- each entry is real, independently declared evidence
        from its own source file, so unioning never fabricates a claim --
        and identity fields (name/tags/etc.) are taken from whichever
        candidate declares the most complete identity evidence (a real name
        distinct from the bare id, more tags, more known equipment already).
        Passing `source_mod` still selects exactly one raw, unmerged source,
        for callers that need one mod's literal declared faction data.
        """
        candidates = self._faction_candidates(faction_id)
        if source_mod is not None:
            candidates = [faction for faction in candidates if faction.source_mod == source_mod]
            return candidates[0] if len(candidates) == 1 else None
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        base = max(candidates, key=lambda faction: (
            faction.name != faction.id and bool(faction.name), len(faction.tags),
            len(faction.known_hulls) + len(faction.known_weapons) + len(faction.known_fighters) + len(faction.known_hullmods),
        ))
        return replace(
            base,
            known_hulls=tuple(sorted({item for faction in candidates for item in faction.known_hulls})),
            known_weapons=tuple(sorted({item for faction in candidates for item in faction.known_weapons})),
            known_fighters=tuple(sorted({item for faction in candidates for item in faction.known_fighters})),
            known_hullmods=tuple(sorted({item for faction in candidates for item in faction.known_hullmods})),
        )

    def faction_contributing_sources(self, faction_id: str) -> tuple[str, ...]:
        """Every `source_mod` that declares a faction file for this id, sorted."""
        return tuple(sorted({faction.source_mod for faction in self._faction_candidates(faction_id)}))

    def faction_equipment(self, faction_id: str, source_mod: str | None = None) -> dict[str, tuple[str, ...]]:
        faction = self.resolve_faction(faction_id, source_mod)
        if faction is None:
            provided = "; provide source_mod for overrides" if source_mod is None else ""
            raise ValueError(f"Faction not found or ambiguous: {faction_id}{provided}")
        return {
            "known_hulls": tuple(sorted(faction.known_hulls)),
            "known_weapons": tuple(sorted(faction.known_weapons)),
            "known_fighters": tuple(sorted(faction.known_fighters)),
            "known_hullmods": tuple(sorted(faction.known_hullmods)),
        }
