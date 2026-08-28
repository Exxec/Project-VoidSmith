from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class StalenessReport:
    stale: bool
    reasons: tuple[str, ...]


def check_generation_manifest(path: Path, registry: Registry) -> StalenessReport:
    reasons: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return StalenessReport(True, (f"Generation manifest cannot be read: {exc}",))
    if not isinstance(manifest, dict):
        return StalenessReport(True, ("Generation manifest must be a JSON object.",))
    for field in ("generated_by", "generator_version", "variant_id", "generated_timestamp", "hull_id", "profile_id", "faction_mode", "source_hull_hash", "source_weapon_hashes", "source_provenance_dependencies", "heuristic_set", "resolved_heuristics"):
        if field not in manifest:
            reasons.append(f"Generation manifest is missing required field: {field}.")
    if not isinstance(manifest.get("source_weapon_hashes", {}), dict):
        reasons.append("Generation manifest source_weapon_hashes must be an object.")
        return StalenessReport(True, tuple(reasons))
    if not isinstance(manifest.get("resolved_heuristics", {}), dict):
        reasons.append("Generation manifest resolved_heuristics must be an object.")
        return StalenessReport(True, tuple(reasons))
    dependencies = manifest.get("source_provenance_dependencies", [])
    if not isinstance(dependencies, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("source_mod"), str)
        for item in dependencies
    ):
        reasons.append("Generation manifest source_provenance_dependencies must be a list of source-mod records.")
        return StalenessReport(True, tuple(reasons))
    hull = registry.hulls.by_id.get(manifest.get("hull_id", ""))
    if hull is None:
        reasons.append("Source hull is missing or ambiguous.")
    elif hull.source_hash != manifest.get("source_hull_hash"):
        reasons.append("Source hull hash changed.")
    for weapon_id, source_hash in manifest.get("source_weapon_hashes", {}).items():
        weapon = registry.weapons.by_id.get(weapon_id)
        if weapon is None:
            reasons.append(f"Source weapon {weapon_id} is missing or ambiguous.")
        elif weapon.source_hash != source_hash:
            reasons.append(f"Source weapon {weapon_id} hash changed.")
    current_dependencies = sorted({
        (entity.source_mod, entity.source_mod_version)
        for entity in ([hull] if hull else [])
        + [registry.weapons.by_id[weapon_id] for weapon_id in manifest.get("source_weapon_hashes", {}) if weapon_id in registry.weapons.by_id]
    }, key=lambda item: (item[0], item[1] or ""))
    recorded_dependencies = sorted(
        ((item.get("source_mod"), item.get("source_mod_version")) for item in dependencies),
        key=lambda item: (item[0], item[1] or ""),
    )
    if current_dependencies != recorded_dependencies:
        reasons.append("Source provenance dependency records changed.")
    return StalenessReport(bool(reasons), tuple(reasons))
