"""Write deterministic, scan-time analysis reports below the configured output root.

These reports are derived from the normalized scan registry.  They never write
to a game or mod directory, and preserve unknown mechanics as unknown instead
of attempting to execute or interpret scripts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from starsector_variant_generator.analysis.build_archetypes import (
    infer_build_archetypes,
)
from starsector_variant_generator.analysis.capability_vector import (
    infer_hull_capability_vector,
)
from starsector_variant_generator.analysis.classification import (
    classify_hullmod,
    classify_weapon,
)
from starsector_variant_generator.analysis.doctrine import analyze_faction_doctrine
from starsector_variant_generator.analysis.faction_capability import (
    analyze_faction_capability,
)
from starsector_variant_generator.analysis.hullmod_static_analysis import (
    API_EFFECT_REGISTRY_VERSION,
    _java_sources,
    analyze_hullmod_sources,
    static_analysis_record,
)
from starsector_variant_generator.analysis.mechanical_archetypes import (
    infer_mechanical_archetypes,
)
from starsector_variant_generator.core.cache import build_manifest
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import (
    Entity,
    Faction,
    Hull,
    Hullmod,
    ScanResult,
    SourceType,
    Weapon,
)
from starsector_variant_generator.core.registry import Registry

# Includes explicit source-analysis availability states such as
# COMPILED_ONLY_SCRIPT.  Bump so reusable per-mod fragments cannot hide a
# newly distinguished unknown state.
REPORT_SCHEMA_VERSION = "scan-analysis-0.2"


def write_scan_analysis_reports(
    scan: ScanResult, registry: Registry, reports_dir: Path, heuristic_set: str, reuse_if_unchanged: bool = False,
) -> dict[str, object]:
    """Persist faction, hull, and equipment analysis generated during a scan.

    IDs are sanitized before becoming path segments.  Report filenames include
    the source mod only when the same entity ID appears more than once, keeping
    mod-specific output concise while preventing collisions.
    """
    # `_java_sources` (analysis/hullmod_static_analysis.py) is an
    # `lru_cache` keyed only on a mod's source-root path, with no content
    # invalidation of its own -- its own docstring calls it a "scan-local
    # cache," but that's only true because every real caller today (the CLI)
    # happens to be a fresh process per scan. Nothing enforced that
    # boundary explicitly: a second call in the same process with the same
    # source root -- e.g. a modder editing a `.java` file between two
    # `--reuse-if-unchanged` runs, which is exactly what `test_report_reuse_
    # fails_closed_when_local_java_evidence_changes` exercises -- would
    # correctly detect the change at the manifest-hash level and report
    # "RECOMPUTED", while the recomputation itself silently reused the
    # first call's stale in-memory file content. Clearing here makes the
    # "one Java read per scan" contract real regardless of caller lifetime.
    _java_sources.cache_clear()
    reports_dir.mkdir(parents=True, exist_ok=True)
    cache_path = reports_dir / "analysis_report_manifest.json"
    dependency_fingerprint = _report_dependency_fingerprint(scan, heuristic_set)
    if reuse_if_unchanged and dependency_fingerprint is not None:
        cached = _load_report_manifest(cache_path, heuristic_set, dependency_fingerprint)
        if cached is not None:
            return {**cached, "reuse_status": "REUSED_UNCHANGED"}
    faction_dir = reports_dir / "factions"
    hull_dir = reports_dir / "hulls"
    equipment_dir = reports_dir / "equipment"
    faction_dir.mkdir(exist_ok=True)
    hull_dir.mkdir(exist_ok=True)
    equipment_dir.mkdir(exist_ok=True)

    faction_names = _report_names(scan.factions)
    hull_names = _report_names(scan.hulls)
    faction_paths: list[str] = []
    hull_paths: list[str] = []
    reused_hull_profiles = 0
    reused_faction_reports = 0
    for faction in sorted(scan.factions, key=_entity_sort_key):
        base = faction_names[(faction.source_mod, faction.id)]
        capability_path = faction_dir / f"{base}_capability_profile.json"
        doctrine_path = faction_dir / f"{base}_doctrine_inference.json"
        capability_fingerprint = _faction_capability_fingerprint(faction, registry, heuristic_set)
        doctrine_fingerprint = _faction_doctrine_fingerprint(faction, registry)
        if not (reuse_if_unchanged and capability_fingerprint is not None and _reusable_faction_report(capability_path, heuristic_set, capability_fingerprint)):
            capability = _envelope(faction.source_mod, heuristic_set, asdict(analyze_faction_capability(faction, registry, heuristic_set)))
            capability["dependency_fingerprint"] = capability_fingerprint
            capability["cache_readiness"] = "CACHE_SAFE" if capability_fingerprint is not None else "CACHE_UNSAFE_INCOMPLETE_CONTEXT"
            _write_json(capability_path, capability)
        else:
            reused_faction_reports += 1
        if not (reuse_if_unchanged and doctrine_fingerprint is not None and _reusable_faction_report(doctrine_path, heuristic_set, doctrine_fingerprint)):
            doctrine = _envelope(faction.source_mod, heuristic_set, asdict(analyze_faction_doctrine(faction, registry)))
            doctrine["dependency_fingerprint"] = doctrine_fingerprint
            doctrine["cache_readiness"] = "CACHE_SAFE" if doctrine_fingerprint is not None else "CACHE_UNSAFE_INCOMPLETE_CONTEXT"
            _write_json(doctrine_path, doctrine)
        else:
            reused_faction_reports += 1
        faction_paths.extend((str(capability_path), str(doctrine_path)))
    pending_hulls: list[tuple[Hull, Path, str | None]] = []
    for hull in sorted(scan.hulls, key=_entity_sort_key):
        base = hull_names[(hull.source_mod, hull.id)]
        path = hull_dir / f"{base}_profile.json"
        hull_fingerprint = _hull_profile_fingerprint(hull, registry, heuristic_set)
        if reuse_if_unchanged and hull_fingerprint is not None and _reusable_hull_profile(path, heuristic_set, hull_fingerprint):
            hull_paths.append(str(path))
            reused_hull_profiles += 1
            continue
        pending_hulls.append((hull, path, hull_fingerprint))
    # Calculation is read-only over the finalized registry; writes happen in
    # sorted hull order below so concurrent CPU work cannot change documents.
    if pending_hulls:
        worker_count = min(8, max(1, os.cpu_count() or 1), len(pending_hulls))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="voidsmith-reports") as executor:
            records = list(executor.map(lambda item: _hull_profile_record(item[0], registry, heuristic_set, item[2]), pending_hulls))
        for (_, path, _), record in zip(pending_hulls, records):
            _write_json(path, record)
            hull_paths.append(str(path))

    weapon_path = equipment_dir / "weapon_profiles.json"
    hullmod_path = equipment_dir / "hullmod_profiles.json"
    hullmod_analysis_path = equipment_dir / "hullmod_source_analysis.json"
    weapon_document, weapon_reused, weapon_recomputed = _write_equipment_fragments(scan.weapons, equipment_dir, heuristic_set, "weapon", reuse_if_unchanged)
    hullmod_document, hullmod_reused, hullmod_recomputed = _write_equipment_fragments(scan.hullmods, equipment_dir, heuristic_set, "hullmod", reuse_if_unchanged)
    _write_json(weapon_path, weapon_document)
    _write_json(hullmod_path, hullmod_document)
    hullmod_analysis, reused_hullmod_mods, recomputed_hullmod_mods = _write_hullmod_source_fragments(
        scan.hullmods, equipment_dir, heuristic_set, reuse_if_unchanged,
    )
    _write_json(hullmod_analysis_path, hullmod_analysis)
    manifest: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "heuristic_set": heuristic_set,
        "dependency_fingerprint": dependency_fingerprint,
        "cache_readiness": "CACHE_SAFE" if dependency_fingerprint is not None else "CACHE_UNSAFE_INCOMPLETE_CONTEXT",
        "faction_reports": faction_paths,
        "hull_reports": hull_paths,
        "equipment_reports": [str(weapon_path), str(hullmod_path), str(hullmod_analysis_path)],
        "hull_profile_reuse": {"reused": reused_hull_profiles, "recomputed": len(hull_paths) - reused_hull_profiles},
        "faction_report_reuse": {"reused": reused_faction_reports, "recomputed": len(faction_paths) - reused_faction_reports},
        "hullmod_source_reuse": {"reused_mods": reused_hullmod_mods, "recomputed_mods": recomputed_hullmod_mods},
        "equipment_profile_reuse": {
            "weapon_reused_mods": weapon_reused, "weapon_recomputed_mods": weapon_recomputed,
            "hullmod_reused_mods": hullmod_reused, "hullmod_recomputed_mods": hullmod_recomputed,
        },
        "reuse_status": "RECOMPUTED",
    }
    _write_json(cache_path, manifest)
    return manifest


def _hull_profile_record(hull: Hull, registry: Registry, heuristic_set: str, hull_fingerprint: str | None) -> dict[str, object]:
    """Build one deterministic hull report; safe to call from a worker."""
    profile = infer_mechanical_archetypes(hull, registry)
    record = _envelope(hull.source_mod, heuristic_set, asdict(profile))
    record["capability_vector"] = asdict(infer_hull_capability_vector(hull, registry))
    if "build_archetype_viable_min_compatibility" in get_heuristic_set(heuristic_set).values:
        record["build_archetypes"] = [asdict(build) for build in infer_build_archetypes(hull, registry, heuristic_set)]
    else:
        record["build_archetypes"] = []
    record["hull_name"] = hull.name
    record["dependency_fingerprint"] = hull_fingerprint
    record["cache_readiness"] = "CACHE_SAFE" if hull_fingerprint is not None else "CACHE_UNSAFE_INCOMPLETE_CONTEXT"
    return record


def _write_equipment_fragments(
    entities: Sequence[Entity], equipment_dir: Path, heuristic_set: str, kind: str, reuse_if_unchanged: bool,
) -> tuple[dict[str, object], int, int]:
    """Persist direct classification fragments per mod and assemble legacy output."""
    grouped: dict[str, list[dict[str, object]]] = {}
    by_mod: dict[str, list[Entity]] = {}
    for entity in sorted(entities, key=_entity_sort_key):
        by_mod.setdefault(entity.source_mod, []).append(entity)
    reused = 0
    recomputed = 0
    for mod_id, mod_entities in sorted(by_mod.items()):
        path = equipment_dir / f"{kind}_profiles_{_safe_segment(mod_id)}.json"
        fingerprint = _entity_dependencies_hash(mod_entities, {
            "report_schema": REPORT_SCHEMA_VERSION, "operation": f"{kind}_classification", "heuristic_set": heuristic_set,
        })
        fragment = _load_reusable_fragment(path, heuristic_set, fingerprint, require_api_registry=False) if reuse_if_unchanged and fingerprint is not None else None
        if fragment is None:
            profiles: list[dict[str, object]] = []
            for entity in mod_entities:
                if kind == "weapon":
                    assert isinstance(entity, Weapon)
                    classification = asdict(classify_weapon(entity))
                else:
                    assert isinstance(entity, Hullmod)
                    classification = asdict(classify_hullmod(entity))
                profiles.append({
                    "id": entity.id, "name": entity.name, "source_mod": entity.source_mod,
                    "source_mod_version": entity.source_mod_version, "classification": classification,
                    "raw_evidence": entity.raw,
                })
            fragment = {
                "schema_version": REPORT_SCHEMA_VERSION,
                "heuristic_set": heuristic_set,
                "profile_kind": kind,
                "source_mod": mod_id,
                "profiles": profiles,
                "dependency_fingerprint": fingerprint,
                "cache_readiness": "CACHE_SAFE" if fingerprint is not None else "CACHE_UNSAFE_INCOMPLETE_CONTEXT",
            }
            _write_json(path, fragment)
            recomputed += 1
        else:
            reused += 1
        fragment_profiles = fragment.get("profiles", [])
        if isinstance(fragment_profiles, list):
            grouped[mod_id] = fragment_profiles
    return ({
        "schema_version": REPORT_SCHEMA_VERSION,
        "heuristic_set": heuristic_set,
        "profile_kind": kind,
        "profiles_by_mod": grouped,
    }, reused, recomputed)


def _write_hullmod_source_fragments(
    hullmods: Sequence[Hullmod], equipment_dir: Path, heuristic_set: str, reuse_if_unchanged: bool,
) -> tuple[dict[str, object], int, int]:
    """Cache Java-derived hullmod evidence per source mod, then aggregate it."""
    grouped: dict[str, list[dict[str, object]]] = {}
    all_records: list[dict[str, object]] = []
    by_mod: dict[str, list[Hullmod]] = {}
    for hullmod in sorted(hullmods, key=_entity_sort_key):
        by_mod.setdefault(hullmod.source_mod, []).append(hullmod)
    reused = 0
    recomputed = 0
    for mod_id, mod_hullmods in sorted(by_mod.items()):
        path = equipment_dir / f"hullmod_source_{_safe_segment(mod_id)}.json"
        fingerprint = _hullmod_source_fingerprint(mod_hullmods, heuristic_set)
        fragment = _load_reusable_fragment(path, heuristic_set, fingerprint) if reuse_if_unchanged and fingerprint is not None else None
        if fragment is None:
            records: list[dict[str, object]] = []
            for hullmod in mod_hullmods:
                record = static_analysis_record(analyze_hullmod_sources(hullmod, _source_root(hullmod.source_path)))
                record["source_mod"] = hullmod.source_mod
                record["source_mod_version"] = hullmod.source_mod_version
                records.append(record)
            fragment = {
                "schema_version": REPORT_SCHEMA_VERSION,
                "api_effect_registry": API_EFFECT_REGISTRY_VERSION,
                "heuristic_set": heuristic_set,
                "source_mod": mod_id,
                "hullmods": records,
                "dependency_fingerprint": fingerprint,
                "cache_readiness": "CACHE_SAFE" if fingerprint is not None else "CACHE_UNSAFE_INCOMPLETE_CONTEXT",
            }
            _write_json(path, fragment)
            recomputed += 1
        else:
            reused += 1
        fragment_records = fragment.get("hullmods", [])
        if isinstance(fragment_records, list):
            grouped[mod_id] = fragment_records
            all_records.extend(fragment_records)
    return ({
        "schema_version": REPORT_SCHEMA_VERSION,
        "api_effect_registry": API_EFFECT_REGISTRY_VERSION,
        "heuristic_set": heuristic_set,
        "hullmods": sorted(all_records, key=lambda item: (str(item.get("source_mod")), str(item.get("hullmod_id")))) if all(isinstance(item, dict) for item in all_records) else all_records,
        "profiles_by_mod": grouped,
    }, reused, recomputed)


def _envelope(source_mod: str, heuristic_set: str, profile: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "source_mod": source_mod,
        "heuristic_set": heuristic_set,
        "profile": profile,
    }


def _report_names(entities: Sequence[Entity]) -> dict[tuple[str, str], str]:
    counts: dict[str, int] = {}
    for entity in entities:
        counts[entity.id] = counts.get(entity.id, 0) + 1
    return {
        (entity.source_mod, entity.id): _safe_segment(entity.id if counts[entity.id] == 1 else f"{entity.source_mod}_{entity.id}")
        for entity in entities
    }


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "unknown"


def _source_root(path: Path) -> Path | None:
    """Find the mod/core root from a conventional data/... source path."""
    for parent in (path, *path.parents):
        if parent.name == "data":
            return parent.parent
    return None


def _load_report_manifest(path: Path, heuristic_set: str, dependency_fingerprint: str) -> dict[str, object] | None:
    """Reuse only a complete report set after hash-based scan equality.

    The caller supplies equality from the source-hash manifest.  This function
    additionally verifies every recorded output exists and the active heuristic
    set has not changed, so a missing/deleted report can never be reused.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or record.get("schema_version") != REPORT_SCHEMA_VERSION:
        return None
    # The manifest is written adjacent to outputs, but earlier schemas did not
    # persist the heuristic set.  Treat them as non-reusable rather than guess.
    if record.get("heuristic_set") != heuristic_set:
        return None
    # A scan manifest alone does not cover `.ship`, `.wpn`, `.skin`, or local
    # Java source consumed by these reports. Reuse only when the complete
    # report-input fingerprint matches; old manifests fail closed here.
    if record.get("dependency_fingerprint") != dependency_fingerprint:
        return None
    paths = [*record.get("faction_reports", ()), *record.get("hull_reports", ()), *record.get("equipment_reports", ())]
    if not paths or not all(Path(value).is_file() for value in paths if isinstance(value, str)):
        return None
    return record


def _report_dependency_fingerprint(scan: ScanResult, heuristic_set: str) -> str | None:
    """Return an exact report-input hash, or ``None`` when context is incomplete.

    Report reuse is deliberately more conservative than normalized scan reuse.
    Mechanical profiles consume parsed CSV/JSON entities *and* `.ship`, `.wpn`,
    `.skin`, and locally readable Java evidence. Missing entity hashes mean a
    caller cannot prove the normalized inputs, so it must recompute.
    """
    entities = [entity for category in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions") for entity in getattr(scan, category)]
    if any(entity.source_hash is None for entity in entities):
        return None
    extras: list[tuple[str, str]] = []
    for root in _active_source_roots(scan):
        for relative in (Path("mod_info.json"),):
            path = root / relative
            if path.is_file():
                extras.append((str(relative), _file_sha256(path)))
        for relative_dir, pattern in ((Path("data"), "*.ship"), (Path("data"), "*.wpn"), (Path("data"), "*.skin"), (Path("src"), "*.java")):
            directory = root / relative_dir
            if directory.is_dir():
                for path in sorted(directory.rglob(pattern)):
                    extras.append((str(path.relative_to(root)), _file_sha256(path)))
    payload = {
        "report_schema": REPORT_SCHEMA_VERSION,
        "heuristic_set": heuristic_set,
        "api_effect_registry": API_EFFECT_REGISTRY_VERSION,
        "normalized_manifest": build_manifest(scan),
        "extra_source_hashes": sorted(extras),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _active_source_roots(scan: ScanResult) -> tuple[Path, ...]:
    roots = {
        source.path for source in scan.mods
        if source.source_type is SourceType.CORE or source.enabled is not False
    }
    # Synthetic/test scan inputs may omit ModInfo records.  Recover the usual
    # source root from a conventional data/... entity path where possible.
    for category in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions"):
        for entity in getattr(scan, category):
            root = _source_root(entity.source_path)
            if root is not None:
                roots.add(root)
    return tuple(sorted(roots, key=str))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hull_profile_fingerprint(hull: Hull, registry: Registry, heuristic_set: str) -> str | None:
    """Declare the narrow, exact dependency context of one hull profile.

    Mechanical/build/capability profile inference uses the hull itself, its
    existing-variant evidence, resolved weapons on those variants, and
    adapter-backed hullmods on those variants. It does not consume unrelated
    factions, hulls, or equipment, so those changes may safely leave this one
    output intact. Any missing source hash fails closed.
    """
    variants = registry.variants_for_hull(hull.id)
    weapon_ids = {weapon_id for variant in variants for weapon_id in variant.weapons_by_mount.values()}
    hullmod_ids = {hullmod_id for variant in variants for hullmod_id in variant.hullmods}
    dependencies: list[Entity] = [hull, *variants]
    dependencies.extend(registry.weapons.by_id[item] for item in sorted(weapon_ids) if item in registry.weapons.by_id)
    dependencies.extend(registry.hullmods.by_id[item] for item in sorted(hullmod_ids) if item in registry.hullmods.by_id)
    if any(getattr(entity, "source_hash", None) is None for entity in dependencies):
        return None
    return _canonical_hash({
        "report_schema": REPORT_SCHEMA_VERSION,
        "heuristic_set": heuristic_set,
        "dependencies": [asdict(entity) for entity in dependencies],
    })


def _reusable_hull_profile(path: Path, heuristic_set: str, fingerprint: str) -> bool:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(record, dict)
        and record.get("schema_version") == REPORT_SCHEMA_VERSION
        and record.get("heuristic_set") == heuristic_set
        and record.get("dependency_fingerprint") == fingerprint
        and record.get("cache_readiness") == "CACHE_SAFE"
    )


def _faction_capability_fingerprint(faction: Faction, registry: Registry, heuristic_set: str) -> str | None:
    resolved_hulls = [registry.hulls.by_id[item] for item in faction.known_hulls if item in registry.hulls.by_id]
    dependencies: list[Entity] = [faction, *resolved_hulls]
    for hull in resolved_hulls:
        variants = registry.variants_for_hull(hull.id)
        dependencies.extend(variants)
        weapon_ids = {weapon for variant in variants for weapon in variant.weapons_by_mount.values()}
        hullmod_ids = {hullmod for variant in variants for hullmod in variant.hullmods}
        dependencies.extend(registry.weapons.by_id[item] for item in sorted(weapon_ids) if item in registry.weapons.by_id)
        dependencies.extend(registry.hullmods.by_id[item] for item in sorted(hullmod_ids) if item in registry.hullmods.by_id)
    return _entity_dependencies_hash(dependencies, {"report_schema": REPORT_SCHEMA_VERSION, "operation": "faction_capability", "heuristic_set": heuristic_set})


def _faction_doctrine_fingerprint(faction: Faction, registry: Registry) -> str | None:
    variants = [variant for variant in registry.variants.by_id.values() if variant.source_mod == faction.source_mod]
    weapon_ids = {weapon for variant in variants for weapon in variant.weapons_by_mount.values()}
    dependencies: list[Entity] = [faction, *variants]
    dependencies.extend(registry.weapons.by_id[item] for item in sorted(weapon_ids) if item in registry.weapons.by_id)
    return _entity_dependencies_hash(dependencies, {"report_schema": REPORT_SCHEMA_VERSION, "operation": "faction_doctrine"})


def _entity_dependencies_hash(dependencies: Sequence[Entity], context: dict[str, object]) -> str | None:
    if any(entity.source_hash is None for entity in dependencies):
        return None
    # Sort actual serialized dependency records to make cache identity immune
    # to collection iteration order while preserving every semantic input.
    records = sorted((asdict(entity) for entity in dependencies), key=lambda item: json.dumps(item, sort_keys=True, default=str))
    return _canonical_hash({**context, "dependencies": records})


def _hullmod_source_fingerprint(hullmods: Sequence[Hullmod], heuristic_set: str) -> str | None:
    """Include declared hullmod rows and all locally readable Java inputs."""
    if any(hullmod.source_hash is None for hullmod in hullmods):
        return None
    java_hashes: list[tuple[str, str]] = []
    roots = {root for hullmod in hullmods if (root := _source_root(hullmod.source_path)) is not None}
    for root in sorted(roots, key=str):
        source_dir = root / "src"
        if source_dir.is_dir():
            for path in sorted(source_dir.rglob("*.java")):
                java_hashes.append((str(path.relative_to(root)), _file_sha256(path)))
    return _canonical_hash({
        "report_schema": REPORT_SCHEMA_VERSION,
        "operation": "hullmod_source_analysis",
        "heuristic_set": heuristic_set,
        "api_effect_registry": API_EFFECT_REGISTRY_VERSION,
        "hullmods": sorted((asdict(hullmod) for hullmod in hullmods), key=lambda item: json.dumps(item, sort_keys=True, default=str)),
        "java_hashes": java_hashes,
    })


def _load_reusable_fragment(
    path: Path, heuristic_set: str, fingerprint: str, *, require_api_registry: bool = True,
) -> dict[str, object] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    return record if (
        record.get("schema_version") == REPORT_SCHEMA_VERSION
        and record.get("heuristic_set") == heuristic_set
        and (not require_api_registry or record.get("api_effect_registry") == API_EFFECT_REGISTRY_VERSION)
        and record.get("dependency_fingerprint") == fingerprint
        and record.get("cache_readiness") == "CACHE_SAFE"
    ) else None


def _reusable_faction_report(path: Path, heuristic_set: str, fingerprint: str) -> bool:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(record, dict)
        and record.get("schema_version") == REPORT_SCHEMA_VERSION
        and record.get("heuristic_set") == heuristic_set
        and record.get("dependency_fingerprint") == fingerprint
        and record.get("cache_readiness") == "CACHE_SAFE"
    )


def _canonical_hash(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _entity_sort_key(entity: Entity) -> tuple[str, str]:
    return (str(entity.source_mod), str(entity.id))


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")
