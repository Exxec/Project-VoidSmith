"""Read-only catalog query services; re-exported by api.py."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from starsector_variant_generator.analysis.classification import classify_civilian_role, classify_fighter, classify_hullmod, classify_weapon
from starsector_variant_generator.analysis.combat_doctrine import infer_combat_doctrine
from starsector_variant_generator.analysis.combat_entity import classify_fighter_wing_entity, recommendation_eligibility
from starsector_variant_generator.analysis.equipment_affinity import classify_equipment_affinity, classify_equipment_availability
from starsector_variant_generator.core.models import Weapon
from starsector_variant_generator.core.mount_compatibility import MOUNT_TYPE_COMPATIBILITY
from starsector_variant_generator.core.overrides import apply_role_tag_override, load_overrides
from starsector_variant_generator.core.registry import Registry


def run_query_weapons(registry: Registry, size: str | None, mount_type: str | None, overrides_dir: Path, requesting_faction_id: str | None = None) -> list[dict]:
    weapon_overrides = load_overrides(overrides_dir, "weapons")
    records = []
    for weapon in registry.weapons_matching(size, mount_type):
        record = asdict(weapon)
        classification = classify_weapon(weapon)
        override = weapon_overrides.get(weapon.id)
        record["role_tags"] = list(apply_role_tag_override(classification.role_tags, override))
        record["range_band"] = classification.range_band
        record["role_tags_overridden"] = override is not None
        affinity = classify_equipment_affinity(weapon.id, "weapons", registry, requesting_faction_id)
        record["faction_affinity"] = affinity.affinity
        record["owning_faction_ids"] = list(affinity.owning_faction_ids)
        record["availability_class"] = classify_equipment_availability(weapon)
        records.append(record)
    return records


def run_slot_eligible_weapons(
    registry: Registry,
    hull_id: str,
    mount_id: str,
    *,
    include_hidden: bool = False,
    faction_id: str | None = None,
    faction_mode: str = "UNRESTRICTED",
) -> list[Weapon]:
    """Return backend-authoritative mount-compatible weapons for GUI selectors.

    This is intentionally mount compatibility only; full variant OP and other
    legality are evaluated by `run_validate` after a user changes a fit.
    """
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None:
        raise ValueError(f"Hull not found or ambiguous: {hull_id}")
    mount = next((item for item in hull.weapon_mounts if str(item.get("id")) == mount_id), None)
    if mount is None:
        raise ValueError(f"Mount {mount_id!r} is not defined by hull {hull_id}")
    if mount_id in hull.built_in_weapons:
        return []
    order = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}
    mount_size = order.get(str(mount.get("size", "")).upper())
    allowed_types = MOUNT_TYPE_COMPATIBILITY.get(str(mount.get("type", "")).upper(), frozenset())
    if faction_mode not in {"STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"}:
        raise ValueError(f"Unknown faction mode: {faction_mode}")
    if faction_mode == "STRICT_FACTION" and faction_id is None:
        raise ValueError("STRICT_FACTION slot filtering requires a resolved faction")
    return sorted((weapon for weapon in registry.weapons.by_id.values()
                   if mount_size is not None and order.get((weapon.size or "").upper()) is not None
                   and order[(weapon.size or "").upper()] <= mount_size
                   and weapon.mount_type is not None and weapon.mount_type.upper() in allowed_types
                   and (include_hidden or classify_equipment_availability(weapon) not in {"SECRET", "DEV_ONLY", "UNOBTAINABLE"})
                   and (faction_mode != "STRICT_FACTION" or classify_equipment_affinity(weapon.id, "weapons", registry, faction_id).affinity in {"NATIVE", "APPROVED"})),
                  key=lambda weapon: (weapon.name.casefold(), weapon.source_mod, weapon.id))


def run_query_hulls(registry: Registry, hull_size: str | None, civilian_only: bool, overrides_dir: Path | None = None) -> list[dict]:
    hull_overrides = load_overrides(overrides_dir, "hulls") if overrides_dir else {}
    records = []
    for hull in registry.hulls_matching(hull_size):
        civilian = classify_civilian_role(hull)
        override = hull_overrides.get(hull.id)
        role_tags = apply_role_tag_override(civilian.role_tags, override)
        is_civilian = "CIVILIAN" in role_tags
        if civilian_only and not is_civilian:
            continue
        record = asdict(hull)
        record["civilian_role_tags"] = list(role_tags)
        record["is_civilian"] = is_civilian
        record["civilian_role_tags_overridden"] = override is not None
        record["recommendation_eligibility"] = asdict(recommendation_eligibility(hull))
        record["combat_doctrine"] = asdict(infer_combat_doctrine(hull, registry))
        records.append(record)
    return records


def run_query_fighters(registry: Registry, role: str | None, requesting_faction_id: str | None = None) -> list[dict]:
    records = []
    for fighter in registry.fighters_matching(role):
        record = asdict(fighter)
        record["role_tags"] = list(classify_fighter(fighter).role_tags)
        affinity = classify_equipment_affinity(fighter.id, "fighters", registry, requesting_faction_id)
        record["faction_affinity"] = affinity.affinity
        record["owning_faction_ids"] = list(affinity.owning_faction_ids)
        record["availability_class"] = classify_equipment_availability(fighter)
        record["combat_entity_profile"] = asdict(classify_fighter_wing_entity(fighter))
        records.append(record)
    return records


def run_query_hullmods(registry: Registry, hidden: bool | None, requesting_faction_id: str | None = None) -> list[dict]:
    records = []
    for hullmod in registry.hullmods_matching(hidden):
        record = asdict(hullmod)
        record["property_tags"] = list(classify_hullmod(hullmod).property_tags)
        affinity = classify_equipment_affinity(hullmod.id, "hullmods", registry, requesting_faction_id)
        record["faction_affinity"] = affinity.affinity
        record["owning_faction_ids"] = list(affinity.owning_faction_ids)
        record["availability_class"] = classify_equipment_availability(hullmod)
        records.append(record)
    return records


def run_query_variants(registry: Registry, hull_id: str | None) -> list[dict]:
    if not hull_id:
        raise ValueError("query variants requires --hull-id")
    return [asdict(variant) for variant in registry.variants_for_hull(hull_id)]


def run_query_faction_equipment(registry: Registry, faction_id: str | None, source_mod: str | None) -> dict[str, tuple[str, ...]]:
    if not faction_id:
        raise ValueError("query faction-equipment requires --faction-id")
    return registry.faction_equipment(faction_id, source_mod)
