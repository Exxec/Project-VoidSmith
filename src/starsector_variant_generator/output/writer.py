from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from starsector_variant_generator.analysis.classification import classify_weapon
from starsector_variant_generator.core.models import Variant
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.validation.legality import LegalityResult, validate_variant


def _weapon_groups(variant: Variant, registry: Registry) -> list[dict[str, object]]:
    """Split PD-tagged weapons into an AUTOFIRE group, everything else LINKED.

    Grounded in classify_weapon's existing, already-tested "PD" tag
    (analysis/classification.py) rather than a new inference -- point-defense
    weapons are conventionally autofire in Starsector so the AI actually
    intercepts with them; a single LINKED group would leave the player to
    manually fire PD, which is not what a "conservative, AI-friendly" export
    should hand back. See docs/ROADMAP.md Tier 4 (weapon groups).
    """
    pd_weapons: dict[str, str] = {}
    other_weapons: dict[str, str] = {}
    for mount_id, weapon_id in variant.weapons_by_mount.items():
        weapon = registry.weapons.by_id.get(weapon_id)
        tags = classify_weapon(weapon).role_tags if weapon is not None else ()
        (pd_weapons if "PD" in tags else other_weapons)[mount_id] = weapon_id
    groups: list[dict[str, object]] = []
    if other_weapons:
        groups.append({"mode": "LINKED", "weapons": other_weapons})
    if pd_weapons:
        groups.append({"mode": "AUTOFIRE", "weapons": pd_weapons})
    return groups


class OutputCollisionError(ValueError):
    """Existing generated output differs and is preserved without overwrite."""


def _write_text_if_same_or_missing(path: Path, contents: str) -> None:
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OutputCollisionError(f"Refusing to replace existing output {path}: {exc}") from exc
        if existing != contents:
            raise OutputCollisionError(f"Refusing to overwrite differing existing output: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _write_manifest_if_compatible(path: Path, manifest: dict[str, object]) -> None:
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OutputCollisionError(f"Refusing to replace unreadable existing manifest {path}: {exc}") from exc
        if not isinstance(existing, dict):
            raise OutputCollisionError(f"Refusing to overwrite non-object manifest: {path}")
        comparable_existing = dict(existing)
        comparable_new = dict(manifest)
        comparable_existing.pop("generated_timestamp", None)
        comparable_new.pop("generated_timestamp", None)
        if comparable_existing != comparable_new:
            raise OutputCollisionError(f"Refusing to overwrite differing existing manifest: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_variant(variant: Variant, registry: Registry, output_dir: Path) -> Path:
    """Write one validated generated variant outside source game/mod directories."""
    assessment = validate_variant(variant, registry)
    if assessment.result != LegalityResult.LEGAL:
        raise ValueError(f"Refusing export: candidate legality is {assessment.result}.")
    path = output_dir / f"{variant.id}.variant"
    payload = {
        "variantId": variant.id,
        "displayName": variant.name,
        "hullId": variant.hull_id,
        "weaponGroups": _weapon_groups(variant, registry),
        "mods": list(variant.hullmods),
        "wings": list(variant.fighter_wings),
    }
    # Omit rather than write null: an explicit null in a real .variant file's
    # fluxVents/fluxCapacitors is unverified against actual game-load
    # behavior, so an unallocated candidate (flux_vents is None) writes the
    # same file it always did.
    if variant.flux_vents is not None:
        payload["fluxVents"] = variant.flux_vents
    if variant.flux_capacitors is not None:
        payload["fluxCapacitors"] = variant.flux_capacitors
    _write_text_if_same_or_missing(path, json.dumps(payload, indent=2))
    return path


def write_compatibility_mod(
    variant: Variant,
    registry: Registry,
    output_root: Path,
    heuristic_set: str = "baseline_0.1",
    profile_id: str = "LINE_BRAWLER",
    faction_mode: str = "UNRESTRICTED",
) -> Path:
    resolved_heuristics = dict(get_heuristic_set(heuristic_set).values)
    mod_root = output_root / "Starsector Auto Variants"
    variant_path = write_variant(variant, registry, mod_root / "data" / "variants")
    mod_info = {"id": "voidsmith_auto_variants", "name": "VoidSmith Auto Variants", "version": "0.1.0", "author": "VoidSmith"}
    _write_text_if_same_or_missing(mod_root / "mod_info.json", json.dumps(mod_info, indent=2))
    _write_text_if_same_or_missing(mod_root / "README.txt", "Generated variants only. Source game and mod files were not modified.\n")
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    referenced_weapons = {
        weapon_id: registry.weapons.by_id[weapon_id]
        for weapon_id in variant.weapons_by_mount.values() if weapon_id in registry.weapons.by_id
    }
    weapons = {weapon_id: weapon.source_hash for weapon_id, weapon in referenced_weapons.items()}
    # This is source provenance, not a Starsector dependency declaration.  The
    # project has no documented basis to infer launcher load order or version
    # compatibility from source-mod labels.
    source_mods = sorted({
        (entity.source_mod, entity.source_mod_version)
        for entity in ([hull] if hull else []) + list(referenced_weapons.values())
    }, key=lambda item: (item[0], item[1] or ""))
    metadata_dir = mod_root / "data" / "metadata"
    manifest = {
        "generated_by": "starsector_variant_generator",
        "generator_version": "0.1.0",
        "variant_id": variant.id,
        "generated_timestamp": datetime.now(timezone.utc).isoformat(),
        "hull_id": variant.hull_id,
        "profile_id": profile_id,
        "faction_mode": faction_mode,
        "source_hull_hash": hull.source_hash if hull else None,
        "source_weapon_hashes": weapons,
        "source_provenance_dependencies": [
            {"source_mod": source_mod, "source_mod_version": source_mod_version}
            for source_mod, source_mod_version in source_mods
        ],
        "heuristic_set": heuristic_set,
        "resolved_heuristics": resolved_heuristics,
    }
    _write_manifest_if_compatible(metadata_dir / f"generation_manifest_{variant.id}.json", manifest)
    return variant_path
