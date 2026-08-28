"""Typed structural model for parent/module hull variants.

This module deliberately models references, not composite combat behavior.  A
module's fitting and raw mechanics remain local to its own hull/variant.  No
consumer may sum or otherwise merge those facts into the parent without a
separate, documented composite-mechanics contract.

ROADMAP.md Phase 27 (Multipart/Composite Hull Formalization) formalizes what
was previously a set of ad hoc, inconsistently-shaped representations
(hull_hints string matching repeated in multiple call sites; bare
``tuple[str, str]`` module mappings; a single flat profile mixing a hull's
*declared* structural role with one specific variant's *resolved* structure)
into six explicit typed concepts, matching the charter's own naming:

- :class:`HullDefinition` -- one Hull's declared composite-related role
  (parent/module/under-parent/station), replacing the repeated inline
  ``"SHIP_WITH_MODULES" in {hint.upper() for hint in hull.hull_hints}``-style
  checks that previously lived independently in
  :mod:`analysis.complex_hull_audit` and in this module's own station-hint
  detection.
- :class:`ShipModule` -- one raw declared parent-slot -> child-variant
  mapping, *before* resolution against the registry. Replaces the bare
  ``tuple[str, str]`` pairs :func:`module_mappings` previously returned.
- :class:`ModuleProfile` -- one *resolved* module slot (unchanged from the
  prior ad hoc version; matches ``DATA_SCHEMA.md`` section 6A exactly).
- :class:`CompositeHullDefinition` -- hull-*type*-level composite
  declaration: does this Hull id declare the parent structural hint, and is
  that borne out by any of its own variants' observed module maps. Distinct
  from :class:`CompositeShipProfile`, which is scoped to one specific ship
  (variant) instance, not the hull type in the abstract.
- :class:`ResolvedShipStructure` -- the fully resolved object graph for one
  composite ship instance (real ``Hull``/``Variant`` entities for the parent
  and every resolved module), so a consumer that needs the actual entities
  does not have to re-implement its own registry lookups. Deliberately kept
  out of :func:`analysis.complex_hull_audit.audit_complex_hulls`'s JSON
  output -- embedding full raw entities there would duplicate local source
  content the same way ``ScanResult.report()`` already avoids doing.
- :class:`CompositeShipProfile` -- the renamed former ``CompositeHullProfile``.
  The record is keyed by ``parent_variant_id`` (one ship instance), not a
  hull type, so "Ship" is the more precise scope word; ``CompositeHullProfile``
  is kept as a backward-compatible alias since nothing about its fields
  changed. See ``docs/WORK_LOG.md``'s Phase 27 entry for the full rationale.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from starsector_variant_generator.analysis.complex_hulls import ComplexHullFeature
from starsector_variant_generator.core.models import Hull, ScanResult, Variant
from starsector_variant_generator.core.registry import Registry


class ModuleResolution(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED_PARENT = "UNRESOLVED_PARENT"
    UNRESOLVED_CHILD_VARIANT = "UNRESOLVED_CHILD_VARIANT"
    UNRESOLVED_CHILD_HULL = "UNRESOLVED_CHILD_HULL"


@dataclass(frozen=True)
class HullDefinition:
    """One Hull entity's declared composite/module-related structural role.

    Purely a classification of ``Hull.hull_hints``; never a legality or
    quality claim, and never inferred beyond the hint strings actually
    present on the parsed hull.
    """

    hull_id: str
    source_mod: str
    is_parent: bool  # declares SHIP_WITH_MODULES
    is_module: bool  # declares MODULE
    is_under_parent: bool  # declares UNDER_PARENT
    is_station: bool  # declares STATION


def classify_hull_definition(hull: Hull) -> HullDefinition:
    """Classify one Hull's declared structural hints, once, consistently."""
    hints = {hint.upper() for hint in hull.hull_hints}
    return HullDefinition(
        hull_id=hull.id,
        source_mod=hull.source_mod,
        is_parent="SHIP_WITH_MODULES" in hints,
        is_module="MODULE" in hints,
        is_under_parent="UNDER_PARENT" in hints,
        is_station="STATION" in hints,
    )


@dataclass(frozen=True)
class ShipModule:
    """One raw declared parent-slot -> child-variant mapping, unresolved."""

    module_slot_id: str
    child_variant_id: str


@dataclass(frozen=True)
class ModuleProfile:
    """One declared parent slot -> child-variant reference, never an aggregate."""

    module_slot_id: str
    child_variant_id: str
    child_hull_id: str | None
    resolution: ModuleResolution
    source_mod: str
    source_path: str


@dataclass(frozen=True)
class CompositeShipProfile:
    """Parseable structure for one specific ship (variant) with module mappings.

    ``analysis_state`` is intentionally fixed to ``STRUCTURAL_ONLY``.  It is
    a guard against accidentally using this profile as proof of composite
    legality, firepower, shielding, system behavior, or survivability.
    """

    parent_variant_id: str
    parent_hull_id: str | None
    source_mod: str
    modules: tuple[ModuleProfile, ...]
    structural_features: tuple[ComplexHullFeature, ...]
    analysis_state: str = "STRUCTURAL_ONLY"
    confidence: float = 1.0


# Backward-compatible alias: this record was previously named
# CompositeHullProfile. Renamed for Phase 27 since it is scoped to one ship
# (variant) instance, not a hull type -- see the module docstring. Fields are
# unchanged, so the alias is a pure name compatibility shim.
CompositeHullProfile = CompositeShipProfile


@dataclass(frozen=True)
class CompositeHullDefinition:
    """Hull-*type*-level composite declaration, distinct from one ship's profile.

    Combines a Hull's own declared structural hint (``hull.is_parent``) with
    whether any of its own variants actually carry observed module maps, and
    the distinct set of child hull ids referenced across all of them. A hull
    can have one without the other (declares the hint with no variant ever
    using it, or a variant with module maps on a hull missing the hint) --
    both conditions are already separately flagged as audit warnings/info
    elsewhere; this record only carries the counted evidence, it does not
    itself judge either case.
    """

    hull: HullDefinition
    variants_with_module_maps: int
    distinct_child_hull_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedShipStructure:
    """The fully resolved entity graph for one composite ship instance.

    Unlike :class:`CompositeShipProfile` (ids and a resolution enum only),
    this carries the real resolved ``Hull``/``Variant`` objects for the
    parent and for every module whose resolution is ``RESOLVED`` -- so a
    consumer that needs the actual entities (e.g. to inspect a module's own
    mounts/hullmods for its own, non-merged local fit) does not have to
    re-implement its own registry lookup. An unresolved module's entity
    fields stay ``None``, exactly mirroring ``ModuleProfile.resolution`` --
    never guessed at.
    """

    profile: CompositeShipProfile
    parent_hull: Hull | None
    parent_variant: Variant | None
    module_hulls: dict[str, Hull | None]  # module_slot_id -> resolved child Hull
    module_variants: dict[str, Variant | None]  # module_slot_id -> resolved child Variant


def module_mappings(variant: Variant) -> tuple[ShipModule, ...]:
    """Return actual slot mappings only; empty module arrays have no meaning."""
    raw_modules = variant.raw.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        return ()
    mappings: list[ShipModule] = []
    for mapping in raw_modules:
        if not isinstance(mapping, dict):
            continue
        for slot, target in mapping.items():
            if isinstance(slot, str) and slot and isinstance(target, str) and target:
                mappings.append(ShipModule(slot, target))
    return tuple(mappings)


def build_composite_ship_profiles(scan: ScanResult, registry: Registry) -> tuple[CompositeShipProfile, ...]:
    """Resolve declared module references without guessing duplicate IDs."""
    profiles: list[CompositeShipProfile] = []
    for parent_variant in sorted(scan.variants, key=lambda item: (item.source_mod, item.id, str(item.source_path))):
        mappings = module_mappings(parent_variant)
        if not mappings:
            continue
        parent = registry.hulls.by_id.get(parent_variant.hull_id or "")
        modules: list[ModuleProfile] = []
        for module in mappings:
            slot, child_variant_id = module.module_slot_id, module.child_variant_id
            child_variant = registry.variants.by_id.get(child_variant_id)
            if parent is None:
                resolution = ModuleResolution.UNRESOLVED_PARENT
                child_hull_id = None
            elif child_variant is None:
                resolution = ModuleResolution.UNRESOLVED_CHILD_VARIANT
                child_hull_id = None
            elif not child_variant.hull_id or child_variant.hull_id not in registry.hulls.by_id:
                resolution = ModuleResolution.UNRESOLVED_CHILD_HULL
                child_hull_id = child_variant.hull_id
            else:
                resolution = ModuleResolution.RESOLVED
                child_hull_id = child_variant.hull_id
            modules.append(ModuleProfile(slot, child_variant_id, child_hull_id, resolution, parent_variant.source_mod, str(parent_variant.source_path)))
        targets = [module.child_variant_id for module in modules]
        features = [ComplexHullFeature.MULTIPART_PARENT_CHILD]
        if len(targets) != len(set(targets)):
            features.append(ComplexHullFeature.REPEATED_MODULES)
        if len(set(targets)) > 1:
            features.append(ComplexHullFeature.ASYMMETRIC_MODULES)
        if parent is not None and "STATION" in {hint.upper() for hint in parent.hull_hints}:
            features.append(ComplexHullFeature.STATION_STYLE_MODULES)
        confidence = 1.0 if all(module.resolution is ModuleResolution.RESOLVED for module in modules) else 0.5
        profiles.append(CompositeShipProfile(parent_variant.id, parent_variant.hull_id, parent_variant.source_mod, tuple(modules), tuple(features), confidence=confidence))
    return tuple(profiles)


# Backward-compatible alias: previously named build_composite_hull_profiles.
build_composite_hull_profiles = build_composite_ship_profiles


def build_composite_hull_definitions(scan: ScanResult, registry: Registry) -> tuple[CompositeHullDefinition, ...]:
    """One CompositeHullDefinition per Hull id that is a declared parent or
    has at least one variant with observed module maps.

    Formalizes the ad hoc per-hull hint classification that previously lived
    only as inline list comprehensions inside
    :func:`analysis.complex_hull_audit.audit_complex_hulls`.
    """
    ship_profiles = build_composite_ship_profiles(scan, registry)
    profiles_by_parent_hull: dict[str, list[CompositeShipProfile]] = defaultdict(list)
    for profile in ship_profiles:
        if profile.parent_hull_id:
            profiles_by_parent_hull[profile.parent_hull_id].append(profile)

    definitions: list[CompositeHullDefinition] = []
    seen: set[str] = set()
    for hull in sorted(scan.hulls, key=lambda item: (item.source_mod, item.id)):
        if hull.id in seen:
            continue
        definition = classify_hull_definition(hull)
        profiles = profiles_by_parent_hull.get(hull.id, [])
        if not definition.is_parent and not profiles:
            continue
        seen.add(hull.id)
        child_hull_ids: set[str] = set()
        for profile in profiles:
            for module in profile.modules:
                if module.child_hull_id:
                    child_hull_ids.add(module.child_hull_id)
        definitions.append(CompositeHullDefinition(definition, len(profiles), tuple(sorted(child_hull_ids))))
    return tuple(definitions)


def resolve_ship_structure(scan: ScanResult, registry: Registry, profile: CompositeShipProfile) -> ResolvedShipStructure:
    """Resolve a CompositeShipProfile's ids into real Hull/Variant entities.

    Never guesses: a module whose ``resolution`` is not ``RESOLVED`` gets
    ``None`` entity fields, exactly mirroring the profile's own resolution
    state rather than attempting a best-effort lookup.
    """
    parent_hull = registry.hulls.by_id.get(profile.parent_hull_id or "")
    parent_variant = registry.variants.by_id.get(profile.parent_variant_id)
    module_hulls: dict[str, Hull | None] = {}
    module_variants: dict[str, Variant | None] = {}
    for module in profile.modules:
        if module.resolution is ModuleResolution.RESOLVED:
            module_variants[module.module_slot_id] = registry.variants.by_id.get(module.child_variant_id)
            module_hulls[module.module_slot_id] = registry.hulls.by_id.get(module.child_hull_id or "")
        else:
            module_variants[module.module_slot_id] = None
            module_hulls[module.module_slot_id] = None
    return ResolvedShipStructure(profile, parent_hull, parent_variant, module_hulls, module_variants)
