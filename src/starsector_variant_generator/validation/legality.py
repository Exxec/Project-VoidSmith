from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from starsector_variant_generator.adapters import (
    flux_unit_cost,
    hullmod_incompatibility_pairs,
    max_logistics_hullmods,
)
from starsector_variant_generator.core.models import Variant
from starsector_variant_generator.core.mount_compatibility import (
    MOUNT_TYPE_COMPATIBILITY,
)
from starsector_variant_generator.core.registry import Registry


class LegalityResult(StrEnum):
    LEGAL = "LEGAL"
    ILLEGAL = "ILLEGAL"
    NOT_DETERMINABLE = "NOT_DETERMINABLE"


@dataclass(frozen=True)
class LegalityFinding:
    code: str
    message: str


@dataclass(frozen=True)
class LegalityAssessment:
    result: LegalityResult
    failures: tuple[LegalityFinding, ...] = ()
    uncertainties: tuple[LegalityFinding, ...] = ()
    evidence: tuple[LegalityFinding, ...] = ()


_SIZE_ORDER = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}


def validate_variant(variant: Variant, registry: Registry) -> LegalityAssessment:
    """Validate only documented data relationships; never apply quality heuristics."""
    failures: list[LegalityFinding] = []
    uncertainties: list[LegalityFinding] = []
    evidence: list[LegalityFinding] = []
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None:
        failures.append(LegalityFinding("HULL_NOT_FOUND", f"Hull {variant.hull_id!r} is not indexed."))
        return LegalityAssessment(LegalityResult.ILLEGAL, tuple(failures))
    evidence.append(LegalityFinding("HULL_FOUND", f"Hull {hull.id} is indexed."))
    mounts = {str(mount.get("id")): mount for mount in hull.weapon_mounts if mount.get("id")}
    total_weapon_op = 0
    total_non_weapon_op = 0
    op_is_complete = hull.ordnance_points is not None
    for mount_id, weapon_id in variant.weapons_by_mount.items():
        weapon = registry.weapons.by_id.get(weapon_id)
        mount = mounts.get(mount_id)
        if mount is None:
            failures.append(LegalityFinding("MOUNT_NOT_FOUND", f"Mount {mount_id!r} is not defined by hull {hull.id}."))
            continue
        if weapon is None:
            failures.append(LegalityFinding("WEAPON_NOT_FOUND", f"Weapon {weapon_id!r} is not indexed."))
            continue
        if mount_id in hull.built_in_weapons:
            # A hull-fixed mount's own "size"/"type" describe the fixed
            # slot, not a normal player-assignable compatibility category
            # (real weapons never declare mount_type "BUILT_IN" themselves,
            # so the generic checks below would always misfire here even
            # for the hull's own correct weapon). Legality for this mount
            # is governed entirely by BUILT_IN_WEAPON_OVERRIDDEN below.
            pass
        else:
            mount_size = _SIZE_ORDER.get(str(mount.get("size", "")).upper())
            weapon_size = _SIZE_ORDER.get((weapon.size or "").upper())
            if mount_size is None or weapon_size is None:
                uncertainties.append(LegalityFinding("SIZE_NOT_DETERMINABLE", f"Cannot compare {weapon.id} with mount {mount_id}."))
            elif weapon_size > mount_size:
                failures.append(LegalityFinding("WEAPON_TOO_LARGE", f"{weapon.id} exceeds {mount_id}'s size."))
            if weapon.mount_type is None:
                uncertainties.append(LegalityFinding("MOUNT_TYPE_NOT_DETERMINABLE", f"No parsed mount compatibility type for {weapon.id}."))
            else:
                mount_type_upper = str(mount.get("type", "")).upper()
                compatible_weapon_types = MOUNT_TYPE_COMPATIBILITY.get(mount_type_upper)
                if compatible_weapon_types is None:
                    uncertainties.append(LegalityFinding("MOUNT_TYPE_COMPATIBILITY_UNKNOWN", f"No documented compatibility rule for mount type {mount_type_upper!r} ({mount_id})."))
                elif weapon.mount_type.upper() not in compatible_weapon_types:
                    failures.append(LegalityFinding("MOUNT_TYPE_MISMATCH", f"{weapon.id} is incompatible with {mount_id}."))
        if weapon.ordnance_points is None:
            op_is_complete = False
            uncertainties.append(LegalityFinding("WEAPON_OP_UNKNOWN", f"No OP value for {weapon.id}."))
        else:
            total_weapon_op += weapon.ordnance_points
    for mount_id, fixed_weapon_id in hull.built_in_weapons.items():
        assigned = variant.weapons_by_mount.get(mount_id)
        if assigned is not None and assigned != fixed_weapon_id:
            failures.append(LegalityFinding(
                "BUILT_IN_WEAPON_OVERRIDDEN",
                f"Mount {mount_id!r} is hardwired to {fixed_weapon_id!r} and cannot carry {assigned!r}.",
            ))
    hullmod_set = set(variant.hullmods)
    for pair in hullmod_incompatibility_pairs(hull.source_mod):
        if pair.a in hullmod_set and pair.b in hullmod_set:
            failures.append(LegalityFinding(
                "HULLMOD_INCOMPATIBLE",
                f"{pair.a} and {pair.b} are documented as mutually exclusive ({pair.citation}).",
            ))
    logistics_hullmod_count = 0
    for hullmod_id in variant.hullmods:
        if hullmod_id in hull.built_in_hullmods:
            continue
        hullmod = registry.hullmods.by_id.get(hullmod_id)
        if hullmod is None:
            failures.append(LegalityFinding("HULLMOD_NOT_FOUND", f"Hullmod {hullmod_id!r} is not indexed."))
            continue
        cost = hullmod.op_cost_by_hull_size.get(hull.hull_size or "")
        if cost is None:
            op_is_complete = False
            uncertainties.append(LegalityFinding("HULLMOD_OP_UNKNOWN", f"No OP cost for hullmod {hullmod_id}."))
        else:
            total_non_weapon_op += cost
        # Positive-evidence-only: a hullmod whose parsed uiTags don't
        # mention "Logistics" is never assumed non-logistics, only left
        # uncounted. See adapters/vanilla MAX_LOGISTICS_HULLMODS.
        if "Logistics" in str(hullmod.raw.get("uiTags", "")):
            logistics_hullmod_count += 1
    if logistics_hullmod_count > max_logistics_hullmods():
        failures.append(LegalityFinding(
            "LOGISTICS_HULLMOD_LIMIT_EXCEEDED",
            f"{logistics_hullmod_count} logistics hullmods exceed the documented maximum of {max_logistics_hullmods()}.",
        ))
    for wing_id in variant.fighter_wings:
        wing = registry.fighters.by_id.get(wing_id)
        if wing is None:
            failures.append(LegalityFinding("FIGHTER_WING_NOT_FOUND", f"Fighter wing {wing_id!r} is not indexed."))
        elif wing.op_cost is None:
            op_is_complete = False
            uncertainties.append(LegalityFinding("FIGHTER_OP_UNKNOWN", f"No OP cost for fighter wing {wing_id}."))
        else:
            total_non_weapon_op += wing.op_cost
    if variant.fighter_wings:
        # hull.fighter_bays (the CSV "fighter bays" column) is the
        # authoritative capacity -- not len(hull.launch_bay_slots), which
        # undercounts hulls where one LAUNCH_BAY weaponSlot's multi-pair
        # "locations" array represents several physical bays (verified
        # against the real Condor-class hull: one LAUNCH_BAY slot, but a
        # documented "fighter bays" count of 2).
        if hull.fighter_bays is None:
            uncertainties.append(LegalityFinding(
                "FIGHTER_BAY_CAPACITY_UNKNOWN",
                f"No documented fighter-bay count for hull {hull.id}.",
            ))
        elif len(variant.fighter_wings) > hull.fighter_bays:
            failures.append(LegalityFinding(
                "FIGHTER_BAY_CAPACITY_EXCEEDED",
                f"{len(variant.fighter_wings)} fighter wing(s) assigned but hull {hull.id} has {hull.fighter_bays} documented fighter bay(s).",
            ))
    flux_cost = flux_unit_cost(hull.source_mod)
    vents = variant.flux_vents or 0
    capacitors = variant.flux_capacitors or 0
    if flux_cost is None:
        if vents or capacitors:
            op_is_complete = False
            uncertainties.append(LegalityFinding("VENT_CAP_OP_UNKNOWN", f"Vent/capacitor OP cost is not documented for source mod {hull.source_mod!r}."))
    elif vents or capacitors:
        max_vents = flux_cost.max_vents_by_hull_size.get(hull.hull_size or "")
        max_capacitors = flux_cost.max_capacitors_by_hull_size.get(hull.hull_size or "")
        if max_vents is not None and vents > max_vents:
            failures.append(LegalityFinding("FLUX_VENTS_EXCEED_HULL_MAXIMUM", f"{vents} vents exceed the documented maximum of {max_vents} for hull size {hull.hull_size} ({flux_cost.citation})."))
        if max_capacitors is not None and capacitors > max_capacitors:
            failures.append(LegalityFinding("FLUX_CAPACITORS_EXCEED_HULL_MAXIMUM", f"{capacitors} capacitors exceed the documented maximum of {max_capacitors} for hull size {hull.hull_size} ({flux_cost.citation})."))
        if max_vents is None or max_capacitors is None:
            op_is_complete = False
            uncertainties.append(LegalityFinding("FLUX_MAXIMUM_UNKNOWN_FOR_HULL_SIZE", f"No documented vent/capacitor maximum for hull size {hull.hull_size!r}."))
        total_non_weapon_op += (vents + capacitors) * flux_cost.op_cost_per_unit
    if op_is_complete and hull.ordnance_points is not None:
        total_op = total_weapon_op + total_non_weapon_op
        if total_op > hull.ordnance_points:
            failures.append(LegalityFinding("OP_EXCEEDED", f"Total OP {total_op} exceeds hull OP {hull.ordnance_points}."))
        else:
            evidence.append(LegalityFinding("OP_WITHIN_LIMIT", f"Total OP {total_op}/{hull.ordnance_points}."))
    if failures:
        return LegalityAssessment(LegalityResult.ILLEGAL, tuple(failures), tuple(uncertainties), tuple(evidence))
    if uncertainties:
        return LegalityAssessment(LegalityResult.NOT_DETERMINABLE, (), tuple(uncertainties), tuple(evidence))
    return LegalityAssessment(LegalityResult.LEGAL, (), (), tuple(evidence))
