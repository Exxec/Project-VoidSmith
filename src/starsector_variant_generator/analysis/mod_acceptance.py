"""Read-only, per-mod acceptance sweep over an already-completed scan.

Classifies EACH installed mod (never the whole install in aggregate) into
PASS / PASS_WITH_UNKNOWNS / PARTIAL / FAIL using only evidence the scanner
and registry already produced -- no new inference, no legality claim (see
`validation/legality.py`, the sole legality source; this module never
imports it and never emits LEGAL/ILLEGAL/NOT_DETERMINABLE). Mirrors
`analysis/complex_hull_audit.py`'s shape: one pure function taking a
`ScanResult`/`Registry`, returning a JSON-serializable dict.

Attribution strategy (see module docstring notes inline below for why):
  - Entity counts, duplicate IDs, unresolved hull/weapon/hullmod references,
    and missing dependencies are attributed via each record's own typed
    `source_mod` field (`Entity.source_mod`, `MissingDependency.mod_id`) --
    exact, never guessed.
  - `ScanResult.warnings` / `.errors` / `.skipped_entities` are free-text
    strings (see `core/scanner.py`), not structured per-mod records. Every
    message the scanner emits embeds the exact `Path` of the mod source
    that produced it (`f"{file_path}: {exc}"` etc., where `file_path`
    always descends from that source's own `ModInfo.path`). Attribution
    here matches a message against the *longest* (most specific) installed
    source path that is a literal substring of it -- exact literal
    containment against paths the scanner itself constructed, not a fuzzy
    guess. A message matching no known source path is reported separately
    as unattributed rather than dropped or force-assigned.
  - A mod whose `mod_info.json` failed to parse never gets a `ModInfo` at
    all (see `Scanner._mod_info_from_dir`), so it cannot appear in
    `scan.mods`; such mods are recovered here as synthetic FAIL records
    from the exact `discovery_skipped`-derived message the scanner already
    produced (folded into `ScanResult.skipped_entities`), labelled by
    directory name since no real mod id could be parsed. Likewise for a
    mod id present in `enabled_mods.json` but never discovered on disk at
    all.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from starsector_variant_generator.analysis.complex_hull_audit import audit_complex_hulls
from starsector_variant_generator.analysis.derived_ship_state import derive_ship_state
from starsector_variant_generator.core.models import ModInfo, ScanResult, SourceType
from starsector_variant_generator.core.registry import Registry

SCHEMA_VERSION = "mod-acceptance-audit-0.1"

PASS = "PASS"
PASS_WITH_UNKNOWNS = "PASS_WITH_UNKNOWNS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"

_ENTITY_KINDS: tuple[str, ...] = ("hulls", "weapons", "fighters", "hullmods", "variants", "factions")

# The only populated adapter today (see AGENTS.md's adapter-layer section
# and adapters/__init__.py's `_ADAPTERS_BY_SOURCE_MOD = {"core": vanilla}`)
# is keyed by source_mod "core". This sweep reports adapter usage the same
# way every real consumer (analysis/civilian.py, combat_stats.py,
# mobility_stats.py, flux_stats.py, weapon_range_stats.py) already looks
# adapter tables up -- by the *hull's* source_mod, via adapters/__init__.py's
# public per-category lookup functions, never by importing the private
# `_ADAPTERS_BY_SOURCE_MOD` mapping directly. If a second adapter is ever
# registered for a specific mod id, this name map is the only place that
# needs a new entry to keep `adapters_applied` human-readable.
_ADAPTER_HUMAN_NAME_BY_SOURCE_MOD = {"core": "vanilla"}

_MALFORMED_MOD_INFO_RE = re.compile(r"^Malformed mod metadata skipped: (.*mod_info\.json): (.*)$")
_ENABLED_NOT_FOUND_RE = re.compile(r"^Enabled mod not discovered: (.+)$")


@dataclass(frozen=True)
class ModAcceptanceFinding:
    """A compact, local-only summary observation -- never a legality claim."""

    severity: str  # INFO | WARNING | ERROR
    code: str
    detail: str


@dataclass(frozen=True)
class ModAcceptanceRecord:
    mod_id: str
    mod_name: str
    version: str | None
    enabled: bool | None
    source_type: str
    mod_info_status: str  # OK | METADATA_UNREADABLE | ENABLED_NOT_FOUND
    classification: str
    entity_counts: dict[str, int]
    duplicate_entity_ids: dict[str, list[str]]
    unresolved_references: list[dict[str, str]]
    unresolved_fighter_wing_references: list[dict[str, str]]
    missing_dependencies: list[str]
    unknown_effect_hullmod_ids: list[str]
    multipart_hull_findings: list[dict[str, Any]]
    adapters_applied: list[str]
    adapter_modeled_hullmod_ids_used: list[str]
    warnings: list[str]
    errors: list[str]
    skipped_entities: list[str]
    findings: list[ModAcceptanceFinding] = field(default_factory=list)


def _adapter_modeled_hullmod_ids(source_mod: str) -> frozenset[str]:
    # Imported lazily to avoid a hard import-order dependency at module load
    # time; these are the same six public lookup functions every real
    # consumer already uses (see this module's docstring).
    from starsector_variant_generator.adapters import (
        combat_hullmod_effects, defense_hullmod_effects, efficiency_hullmod_effects,
        flux_hullmod_effects, logistics_hullmod_effects, mobility_hullmod_effects,
    )
    ids: set[str] = set()
    ids.update(effect.hullmod_id for effect in logistics_hullmod_effects(source_mod))
    ids.update(effect.hullmod_id for effect in efficiency_hullmod_effects(source_mod))
    ids.update(effect.hullmod_id for effect in defense_hullmod_effects(source_mod))
    ids.update(effect.hullmod_id for effect in mobility_hullmod_effects(source_mod))
    ids.update(effect.hullmod_id for effect in flux_hullmod_effects(source_mod))
    ids.update(effect.hullmod_id for effect in combat_hullmod_effects(source_mod))
    return frozenset(ids)


def _attribute_message(message: str, ordered_sources: list[ModInfo]) -> str | None:
    """Return the mod_id of the most specific (longest-path) installed
    source whose own path literally appears in `message`, or None."""
    for source in ordered_sources:
        if str(source.path) in message:
            return source.mod_id
    return None


def audit_mod_acceptance(scan: ScanResult, registry: Registry) -> dict[str, Any]:
    ordered_sources = sorted(scan.mods, key=lambda source: len(str(source.path)), reverse=True)
    mod_sources = [source for source in scan.mods if source.source_type is SourceType.MOD]

    # --- exact, typed attribution (never string matching) ---
    counts_by_mod: dict[str, dict[str, int]] = defaultdict(lambda: {kind: 0 for kind in _ENTITY_KINDS})
    for kind in _ENTITY_KINDS:
        for entity in getattr(scan, kind):
            counts_by_mod[entity.source_mod][kind] += 1

    duplicates_by_mod: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    index_by_kind = {
        "hulls": registry.hulls, "weapons": registry.weapons, "fighters": registry.fighters,
        "hullmods": registry.hullmods, "variants": registry.variants, "factions": registry.factions,
    }
    for kind, index in index_by_kind.items():
        for duplicate_id, entities in index.duplicates.items():
            for entity in entities:
                duplicates_by_mod[entity.source_mod][kind].add(duplicate_id)

    variant_source_mod: dict[str, str] = {}
    for variant in scan.variants:
        variant_source_mod.setdefault(variant.id, variant.source_mod)

    unresolved_by_mod: dict[str, list[dict[str, str]]] = defaultdict(list)
    for reference in registry.unresolved_references:
        owner = variant_source_mod.get(reference.variant_id)
        if owner is not None:
            unresolved_by_mod[owner].append({
                "variant_id": reference.variant_id, "reference_type": reference.reference_type,
                "reference_id": reference.reference_id,
            })

    missing_deps_by_mod: dict[str, list[str]] = defaultdict(list)
    for dependency in registry.missing_dependencies:
        missing_deps_by_mod[dependency.mod_id].append(dependency.dependency_id)

    # Fighter-wing anomalies: Registry._resolve_variants deliberately checks
    # only hull/weapon/hullmod references (see core/registry.py), never
    # variant.fighter_wings or Hull.built_in_fighter_wings -- this is a real
    # coverage gap this sweep fills, using the same "look it up in the
    # unambiguous index, never guess" discipline Registry itself uses.
    fighter_anomalies_by_mod: dict[str, list[dict[str, str]]] = defaultdict(list)
    for variant in scan.variants:
        for fighter_id in variant.fighter_wings:
            if fighter_id not in registry.fighters.by_id:
                fighter_anomalies_by_mod[variant.source_mod].append({
                    "context": "variant_fighter_wing", "id": variant.id, "reference_id": fighter_id,
                })
    for hull in scan.hulls:
        for fighter_id in hull.built_in_fighter_wings:
            if fighter_id not in registry.fighters.by_id:
                fighter_anomalies_by_mod[hull.source_mod].append({
                    "context": "hull_built_in_fighter_wing", "id": hull.id, "reference_id": fighter_id,
                })

    # Multipart/composite hull findings: reuse complex_hull_audit outright
    # rather than re-deriving the same evidence -- each finding already
    # carries its own source_mod.
    complex_audit = audit_complex_hulls(scan, registry)
    complex_by_mod: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in complex_audit["findings"]:
        complex_by_mod[finding["source_mod"]].append(finding)

    # Adapter usage + unknown-effect markers: computed together per variant
    # via derive_ship_state, the same typed aggregate every other consumer
    # of DerivedShipState uses. `unapplied_unknown_hullmod_ids` is this
    # project's real, already-tracked "we have no modeled effect for this
    # hullmod" signal -- the ship-state-level analog of
    # hullmod_static_analysis.py's UNKNOWN_SCRIPTED_EFFECT marker, without
    # paying for a Java-source static-analysis pass this sweep does not need.
    adapter_ids_cache: dict[str, frozenset[str]] = {}
    adapter_usage_by_mod: dict[str, set[str]] = defaultdict(set)
    unknown_effects_by_mod: dict[str, set[str]] = defaultdict(set)
    for variant in scan.variants:
        if not variant.hull_id:
            continue
        hull = registry.hulls.by_id.get(variant.hull_id)
        if hull is None:
            continue
        modeled_ids = adapter_ids_cache.setdefault(hull.source_mod, _adapter_modeled_hullmod_ids(hull.source_mod))
        used = set(variant.hullmods) & modeled_ids
        if used:
            adapter_usage_by_mod[variant.source_mod] |= used
        state = derive_ship_state(variant, hull, registry)
        if state.unapplied_unknown_hullmod_ids:
            unknown_effects_by_mod[variant.source_mod] |= set(state.unapplied_unknown_hullmod_ids)

    # --- free-text message attribution ---
    consumed_messages: set[str] = set()
    warnings_by_mod: dict[str, list[str]] = defaultdict(list)
    errors_by_mod: dict[str, list[str]] = defaultdict(list)
    skipped_by_mod: dict[str, list[str]] = defaultdict(list)
    unattributed_warnings: list[str] = []
    unattributed_errors: list[str] = []
    unattributed_skipped: list[str] = []
    for message in scan.warnings:
        owner = _attribute_message(message, ordered_sources)
        if owner:
            warnings_by_mod[owner].append(message)
        else:
            unattributed_warnings.append(message)
    for message in scan.errors:
        owner = _attribute_message(message, ordered_sources)
        if owner:
            errors_by_mod[owner].append(message)
        else:
            unattributed_errors.append(message)
    for message in scan.skipped_entities:
        malformed = _MALFORMED_MOD_INFO_RE.match(message)
        enabled_missing = _ENABLED_NOT_FOUND_RE.match(message)
        if malformed or enabled_missing:
            consumed_messages.add(message)
            continue
        owner = _attribute_message(message, ordered_sources)
        if owner:
            skipped_by_mod[owner].append(message)
        else:
            unattributed_skipped.append(message)

    # --- synthetic FAIL records for mods that never got a real ModInfo ---
    synthetic_records: list[ModAcceptanceRecord] = []
    for message in scan.skipped_entities:
        if message not in consumed_messages:
            continue
        malformed = _MALFORMED_MOD_INFO_RE.match(message)
        if malformed:
            info_path, reason = malformed.group(1), malformed.group(2)
            # directory holding mod_info.json is the path with the filename stripped
            parent = info_path.rsplit("mod_info.json", 1)[0].rstrip("\\/")
            label = parent.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] or parent
            synthetic_records.append(_empty_record(
                mod_id=f"UNPARSEABLE:{label}", mod_name=f"<unparseable mod_info.json: {label}>",
                version=None, enabled=None, source_type="MOD", mod_info_status="METADATA_UNREADABLE",
                classification=FAIL,
                findings=[ModAcceptanceFinding("ERROR", "MOD_METADATA_UNREADABLE", f"{info_path}: {reason}")],
            ))
            continue
        enabled_missing = _ENABLED_NOT_FOUND_RE.match(message)
        if enabled_missing:
            declared_id = enabled_missing.group(1)
            synthetic_records.append(_empty_record(
                mod_id=declared_id, mod_name=declared_id, version=None, enabled=True,
                source_type="MOD", mod_info_status="ENABLED_NOT_FOUND", classification=FAIL,
                findings=[ModAcceptanceFinding("ERROR", "MOD_ENABLED_NOT_FOUND", message)],
            ))

    # --- classify every real, ModInfo-backed installed mod ---
    records: list[ModAcceptanceRecord] = []
    for source in mod_sources:
        counts = counts_by_mod.get(source.mod_id, {kind: 0 for kind in _ENTITY_KINDS})
        total_entities = sum(counts.values())
        mod_errors = sorted(errors_by_mod.get(source.mod_id, []))
        mod_warnings = sorted(warnings_by_mod.get(source.mod_id, []))
        mod_skipped = sorted(skipped_by_mod.get(source.mod_id, []))
        duplicates = {kind: sorted(ids) for kind, ids in duplicates_by_mod.get(source.mod_id, {}).items() if ids}
        unresolved = unresolved_by_mod.get(source.mod_id, [])
        fighter_anomalies = fighter_anomalies_by_mod.get(source.mod_id, [])
        missing_deps = sorted(missing_deps_by_mod.get(source.mod_id, []))
        complex_findings = complex_by_mod.get(source.mod_id, [])
        adapter_usage = sorted(adapter_usage_by_mod.get(source.mod_id, set()))
        unknown_effects = sorted(unknown_effects_by_mod.get(source.mod_id, set()))
        complex_warning_count = sum(1 for finding in complex_findings if finding.get("severity") == "WARNING")

        has_defect_signal = bool(
            mod_errors or mod_skipped or mod_warnings or unresolved or fighter_anomalies
            or missing_deps or duplicates or complex_warning_count
        )
        findings: list[ModAcceptanceFinding] = []
        if mod_errors:
            findings.append(ModAcceptanceFinding("WARNING", "PARSER_ERRORS", f"{len(mod_errors)} parser error(s) attributed to this mod's own source files."))
        if mod_skipped:
            findings.append(ModAcceptanceFinding("WARNING", "SKIPPED_ENTITIES", f"{len(mod_skipped)} entity/entities skipped while parsing this mod."))
        if unresolved:
            findings.append(ModAcceptanceFinding("WARNING", "UNRESOLVED_REFERENCES", f"{len(unresolved)} unresolved hull/weapon/hullmod reference(s) from this mod's own variants."))
        if fighter_anomalies:
            findings.append(ModAcceptanceFinding("WARNING", "UNRESOLVED_FIGHTER_WING_REFERENCES", f"{len(fighter_anomalies)} fighter-wing reference(s) that do not resolve to an unambiguous parsed wing."))
        if missing_deps:
            findings.append(ModAcceptanceFinding("WARNING", "MISSING_DEPENDENCIES", f"Declared dependency not present among discovered sources: {', '.join(missing_deps)}."))
        if duplicates:
            findings.append(ModAcceptanceFinding("WARNING", "DUPLICATE_ENTITY_IDS", f"This mod's entities collide with another installed source's IDs in: {', '.join(sorted(duplicates))}."))
        if complex_warning_count:
            findings.append(ModAcceptanceFinding("WARNING", "COMPLEX_HULL_AMBIGUITY", f"{complex_warning_count} complex/composite-hull audit warning(s) attributed to this mod."))
        if unknown_effects:
            findings.append(ModAcceptanceFinding("INFO", "UNKNOWN_HULLMOD_EFFECTS", f"{len(unknown_effects)} hullmod id(s) on this mod's variants have no modeled effect table entry (expected for most modded content)."))
        if adapter_usage:
            findings.append(ModAcceptanceFinding("INFO", "ADAPTER_MODELED_HULLMODS_USED", f"This mod's variants use {len(adapter_usage)} adapter-modeled hullmod id(s)."))

        if total_entities == 0 and (mod_errors or mod_skipped):
            classification = FAIL
        elif has_defect_signal:
            classification = PARTIAL
        elif unknown_effects:
            classification = PASS_WITH_UNKNOWNS
        else:
            classification = PASS

        adapters_applied = sorted({
            _ADAPTER_HUMAN_NAME_BY_SOURCE_MOD.get(hull_source_mod)
            for variant in scan.variants if variant.source_mod == source.mod_id and variant.hull_id
            for hull_source_mod in [getattr(registry.hulls.by_id.get(variant.hull_id), "source_mod", None)]
            if hull_source_mod in _ADAPTER_HUMAN_NAME_BY_SOURCE_MOD and set(variant.hullmods) & adapter_ids_cache.get(hull_source_mod, frozenset())
        })

        records.append(ModAcceptanceRecord(
            mod_id=source.mod_id, mod_name=source.mod_name, version=source.version, enabled=source.enabled,
            source_type=str(source.source_type), mod_info_status="OK", classification=classification,
            entity_counts=counts, duplicate_entity_ids=duplicates, unresolved_references=unresolved,
            unresolved_fighter_wing_references=fighter_anomalies, missing_dependencies=missing_deps,
            unknown_effect_hullmod_ids=unknown_effects, multipart_hull_findings=complex_findings,
            adapters_applied=adapters_applied, adapter_modeled_hullmod_ids_used=adapter_usage,
            warnings=mod_warnings, errors=mod_errors, skipped_entities=mod_skipped, findings=findings,
        ))

    records.extend(synthetic_records)
    records.sort(key=lambda record: record.mod_id.lower())

    summary = {classification: 0 for classification in (PASS, PASS_WITH_UNKNOWNS, PARTIAL, FAIL)}
    for record in records:
        summary[record.classification] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "summary": {"mods_classified": len(records), "by_classification": summary},
        "records": [_record_to_dict(record) for record in records],
        "unattributed": {
            "warnings": unattributed_warnings, "errors": unattributed_errors, "skipped_entities": unattributed_skipped,
        },
        "scope_note": (
            "This is a diagnostic acceptance sweep, not a legality result -- validation/legality.py remains the sole "
            "source of LEGAL/ILLEGAL/NOT_DETERMINABLE. Free-text scan warnings/errors/skipped-entity messages are "
            "attributed to a mod by literal containment of that mod's own source path (the most specific match), "
            "never fuzzy matching. A mod whose mod_info.json failed to parse, or whose id was declared enabled but "
            "never discovered on disk, appears as a synthetic FAIL record (mod_id prefixed UNPARSEABLE: for the "
            "former) since no real ModInfo/source_mod could be attributed for it. `unknown_effect_hullmod_ids` "
            "reuses DerivedShipState.unapplied_unknown_hullmod_ids (civilian/defense/mobility categories only); it "
            "is expected to be non-empty for most modded content, since only vanilla ('core') hullmods have a "
            "populated adapter table today -- this drives PASS_WITH_UNKNOWNS, not a defect."
        ),
    }


def _empty_record(
    *, mod_id: str, mod_name: str, version: str | None, enabled: bool | None, source_type: str,
    mod_info_status: str, classification: str, findings: list[ModAcceptanceFinding],
) -> ModAcceptanceRecord:
    return ModAcceptanceRecord(
        mod_id=mod_id, mod_name=mod_name, version=version, enabled=enabled, source_type=source_type,
        mod_info_status=mod_info_status, classification=classification,
        entity_counts={kind: 0 for kind in _ENTITY_KINDS}, duplicate_entity_ids={}, unresolved_references=[],
        unresolved_fighter_wing_references=[], missing_dependencies=[], unknown_effect_hullmod_ids=[],
        multipart_hull_findings=[], adapters_applied=[], adapter_modeled_hullmod_ids_used=[],
        warnings=[], errors=[], skipped_entities=[], findings=findings,
    )


def _record_to_dict(record: ModAcceptanceRecord) -> dict[str, Any]:
    data = asdict(record)
    return data
