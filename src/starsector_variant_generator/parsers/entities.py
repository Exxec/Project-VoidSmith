from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from starsector_variant_generator.core.models import Faction, FighterWing, Hull, Hullmod, Variant, Weapon
from starsector_variant_generator.parsers.common import first, json_file, optional_bool, optional_float, optional_int


def weapon_spec_fields(path: Path) -> dict[str, str]:
    """Extract safe quoted metadata from a `.wpn` spec.

    Weapon specs can contain engine constants that are not JSON. This lexical
    extraction deliberately avoids interpreting those constants. Sprite paths
    are preserved only as local resource references for the GUI; they do not
    affect fitting, legality, or scoring.
    """
    text = path.read_text(encoding="utf-8-sig")
    keys = "id|type|size|turretSprite|hardpointSprite"
    return {key: value for key, value in re.findall(rf'"({keys})"\s*:\s*"([^"]+)"', text)}


def hull_from_row(row: dict[str, str], source_mod: str, path: Path, ship_path: Path | None = None, *, numeric_warnings: list[dict[str, object]] | None = None) -> Hull:
    hull_id = first(row, "id", "hullId") or path.stem
    ship_raw: dict[str, Any] = {}
    mounts: tuple[dict[str, Any], ...] = ()
    if ship_path and ship_path.exists():
        ship_raw = json_file(ship_path)
        slots = ship_raw.get("weaponSlots", [])
        if isinstance(slots, list):
            mounts = tuple(slot for slot in slots if isinstance(slot, dict))
    launch_bays = tuple(
        str(slot["id"]) for slot in mounts
        if str(slot.get("type", "")).upper() == "LAUNCH_BAY" and slot.get("id")
    )
    built_in_weapons_raw = ship_raw.get("builtInWeapons", {})
    built_in_weapons = (
        {str(mount_id): str(weapon_id) for mount_id, weapon_id in built_in_weapons_raw.items()}
        if isinstance(built_in_weapons_raw, dict) else {}
    )
    raw = dict(row)
    if ship_raw:
        raw["ship_data"] = ship_raw
    hints_raw = first(row, "hints")
    hull_hints = tuple(hint.strip() for hint in hints_raw.split(",") if hint.strip()) if hints_raw else ()
    return Hull(id=hull_id, name=first(row, "name", "hullName") or hull_id,
                source_mod=source_mod, source_path=path, hull_size=first(row, "hullSize", "hull_size") or ship_raw.get("hullSize"),
                ordnance_points=optional_int(first(row, "ordnancePoints", "ordnance_points", "ordnance points"), warnings=numeric_warnings, field="ordnancePoints"), weapon_mounts=mounts,
                built_in_hullmods=tuple(str(item) for item in ship_raw.get("builtInMods", []) if isinstance(item, str)),
                built_in_fighter_wings=tuple(str(item) for item in ship_raw.get("builtInWings", []) if isinstance(item, str)),
                launch_bay_slots=launch_bays, built_in_weapons=built_in_weapons,
                flux_capacity=optional_float(first(row, "maxFlux", "max_flux", "max flux"), warnings=numeric_warnings, field="maxFlux"),
                flux_dissipation=optional_float(first(row, "fluxDissipation", "flux_dissipation", "flux dissipation"), warnings=numeric_warnings, field="fluxDissipation"),
                shield_upkeep=optional_float(first(row, "shieldUpkeep", "shield_upkeep", "shield upkeep"), warnings=numeric_warnings, field="shieldUpkeep"),
                fighter_bays=optional_int(first(row, "fighterBays", "fighter_bays", "fighter bays"), warnings=numeric_warnings, field="fighterBays"),
                cargo_capacity=optional_float(first(row, "cargo"), warnings=numeric_warnings, field="cargo"),
                fuel_capacity=optional_float(first(row, "fuel"), warnings=numeric_warnings, field="fuel"),
                crew_min=optional_int(first(row, "min crew", "minCrew"), warnings=numeric_warnings, field="minCrew"),
                crew_max=optional_int(first(row, "max crew", "maxCrew"), warnings=numeric_warnings, field="maxCrew"),
                supplies_per_month=optional_float(first(row, "supplies/mo", "suppliesPerMonth"), warnings=numeric_warnings, field="suppliesPerMonth"),
                max_burn=optional_float(first(row, "max burn", "maxBurn"), warnings=numeric_warnings, field="maxBurn"),
                sensor_profile=optional_float(first(row, "sensor profile", "sensorProfile", "sensor_profile"), warnings=numeric_warnings, field="sensorProfile"),
                hull_hints=hull_hints,
                raw=raw)


def _apply_id_list_override(existing: tuple[str, ...], remove: object, add: object) -> tuple[str, ...]:
    """Additive/subtractive id-list override shared by every skin id-list field.

    Verified real skin shape (`docs/BUGS.md` SVG-014): a `remove*` list plus a
    same-purpose plain list (e.g. `removeBuiltInMods` + `builtInMods`) that adds
    to what remains -- never a full replacement. Order-preserving and
    deduplicated so re-declaring an id already present is a no-op.
    """
    remove_ids = {item for item in remove if isinstance(item, str)} if isinstance(remove, list) else set()
    result = [item for item in existing if item not in remove_ids]
    seen = set(result)
    for item in add if isinstance(add, list) else ():
        if isinstance(item, str) and item not in seen:
            result.append(item)
            seen.add(item)
    return tuple(result)


def hull_from_skin(base: Hull, skin_raw: dict[str, Any], source_mod: str, skin_path: Path, *, numeric_warnings: list[dict[str, object]] | None = None) -> Hull | None:
    """Materialize a `data/hulls/skins/*.skin` file as a derived Hull entity.

    A skin is base hull + explicit, documented overrides (verified against
    66 real core `.skin` files -- see `docs/BUGS.md` SVG-014). Applies only
    the fields with unambiguous, directly-declared semantics (explicit
    remove/add id lists, or a single scalar override); every other real
    skin field this project doesn't yet model as a typed `Hull` attribute
    (`maxSpeed`, `shieldEfficiency`, `systemId`, `engineSlotChanges`,
    `restoreToBaseHull`, ...) is preserved verbatim in `raw` rather than
    guessed at or silently dropped. Returns None if the skin has no usable
    `skinHullId` -- an id-less entity cannot be created.
    """
    skin_hull_id = skin_raw.get("skinHullId")
    if not isinstance(skin_hull_id, str) or not skin_hull_id:
        return None
    remove_slot_ids = {item for item in skin_raw.get("removeWeaponSlots", []) if isinstance(item, str)} \
        if isinstance(skin_raw.get("removeWeaponSlots"), list) else set()
    slot_changes = skin_raw.get("weaponSlotChanges")
    slot_changes = slot_changes if isinstance(slot_changes, dict) else {}
    mounts: list[dict[str, Any]] = []
    for slot in base.weapon_mounts:
        slot_id = str(slot.get("id", ""))
        if slot_id in remove_slot_ids:
            continue
        override = slot_changes.get(slot_id)
        mounts.append({**slot, **override} if isinstance(override, dict) else dict(slot))
    weapon_mounts = tuple(mounts)
    launch_bay_slots = tuple(
        str(slot["id"]) for slot in weapon_mounts
        if str(slot.get("type", "")).upper() == "LAUNCH_BAY" and slot.get("id")
    )
    removed_built_in_weapon_mounts = {item for item in skin_raw.get("removeBuiltInWeapons", []) if isinstance(item, str)} \
        if isinstance(skin_raw.get("removeBuiltInWeapons"), list) else set()
    built_in_weapons = {mount_id: weapon_id for mount_id, weapon_id in base.built_in_weapons.items() if mount_id not in removed_built_in_weapon_mounts}
    skin_built_in_weapons = skin_raw.get("builtInWeapons")
    if isinstance(skin_built_in_weapons, dict):
        built_in_weapons.update({str(mount_id): str(weapon_id) for mount_id, weapon_id in skin_built_in_weapons.items()})
    return Hull(
        id=skin_hull_id,
        name=skin_raw.get("hullName") if isinstance(skin_raw.get("hullName"), str) else base.name,
        source_mod=source_mod, source_path=skin_path,
        hull_size=base.hull_size,
        ordnance_points=optional_int(skin_raw.get("ordnancePoints"), warnings=numeric_warnings, field="ordnancePoints") if "ordnancePoints" in skin_raw else base.ordnance_points,
        weapon_mounts=weapon_mounts,
        built_in_hullmods=_apply_id_list_override(base.built_in_hullmods, skin_raw.get("removeBuiltInMods"), skin_raw.get("builtInMods")),
        built_in_fighter_wings=_apply_id_list_override(base.built_in_fighter_wings, None, skin_raw.get("builtInWings")),
        launch_bay_slots=launch_bay_slots,
        built_in_weapons=built_in_weapons,
        flux_capacity=base.flux_capacity,
        flux_dissipation=base.flux_dissipation,
        shield_upkeep=base.shield_upkeep,
        fighter_bays=optional_int(skin_raw.get("fighterBays"), warnings=numeric_warnings, field="fighterBays") if "fighterBays" in skin_raw else base.fighter_bays,
        cargo_capacity=base.cargo_capacity,
        fuel_capacity=base.fuel_capacity,
        crew_min=base.crew_min,
        crew_max=base.crew_max,
        supplies_per_month=optional_float(skin_raw.get("suppliesPerMonth"), warnings=numeric_warnings, field="suppliesPerMonth") if "suppliesPerMonth" in skin_raw else base.supplies_per_month,
        max_burn=base.max_burn,
        sensor_profile=optional_float(skin_raw.get("sensorProfile"), warnings=numeric_warnings, field="sensorProfile") if "sensorProfile" in skin_raw else base.sensor_profile,
        hull_hints=_apply_id_list_override(base.hull_hints, skin_raw.get("removeHints"), skin_raw.get("addHints")),
        raw={
            "skin_data": skin_raw,
            "base_hull_id": base.id,
            "base_hull_source_mod": base.source_mod,
            # A skin normally changes loadout/stat metadata but still uses
            # the base hull's declared geometry/art. Preserve it explicitly
            # for read-only visual consumers without making the skin source
            # path pretend it owns the base mod's sprite.
            "ship_data": dict(base.raw.get("ship_data", {})) if isinstance(base.raw.get("ship_data"), dict) else {},
            "sprite_source_path": str(base.source_path),
        },
    )


def weapon_from_row(row: dict[str, str], source_mod: str, path: Path, *, numeric_warnings: list[dict[str, object]] | None = None) -> Weapon:
    return Weapon(id=first(row, "id", "weaponId") or path.stem, name=first(row, "name", "weaponName") or path.stem,
                  source_mod=source_mod, source_path=path, size=first(row, "size"), mount_type=first(row, "mountType"),
                  ordnance_points=optional_int(first(row, "OPs", "op", "ordnancePoints"), warnings=numeric_warnings, field="OPs"), range=optional_float(first(row, "range"), warnings=numeric_warnings, field="range"),
                  damage_type=first(row, "type", "damageType"),
                  flux_per_shot=optional_float(first(row, "energy/shot", "energyPerShot", "flux_per_shot"), warnings=numeric_warnings, field="energy/shot"),
                  flux_per_second=optional_float(first(row, "energy/second", "energyPerSecond", "flux_per_second"), warnings=numeric_warnings, field="energy/second"),
                  raw=dict(row))


def fighter_from_row(row: dict[str, str], source_mod: str, path: Path, *, numeric_warnings: list[dict[str, object]] | None = None) -> FighterWing:
    return FighterWing(id=first(row, "id", "wingId") or path.stem, name=first(row, "name") or path.stem, source_mod=source_mod,
                       source_path=path, role=first(row, "role"), op_cost=optional_int(first(row, "opCost", "OPs", "op cost"), warnings=numeric_warnings, field="opCost"), raw=dict(row))


def hullmod_from_row(row: dict[str, str], source_mod: str, path: Path, *, numeric_warnings: list[dict[str, object]] | None = None) -> Hullmod:
    costs = {
        "FRIGATE": optional_int(first(row, "cost_frigate"), warnings=numeric_warnings, field="cost_frigate"),
        "DESTROYER": optional_int(first(row, "cost_dest", "cost_destroyer"), warnings=numeric_warnings, field="cost_dest"),
        "CRUISER": optional_int(first(row, "cost_cruiser"), warnings=numeric_warnings, field="cost_cruiser"),
        "CAPITAL_SHIP": optional_int(first(row, "cost_capital"), warnings=numeric_warnings, field="cost_capital"),
    }
    return Hullmod(id=first(row, "id") or path.stem, name=first(row, "name") or path.stem, source_mod=source_mod,
                   source_path=path, hidden=optional_bool(first(row, "hidden")), built_in_only=optional_bool(first(row, "builtInOnly")),
                   op_cost_by_hull_size={key: value for key, value in costs.items() if value is not None}, raw=dict(row))


def variant_from_file(path: Path, source_mod: str, *, numeric_warnings: list[dict[str, object]] | None = None) -> Variant:
    raw = json_file(path)
    weapons = raw.get("weaponGroups", [])
    mount_map: dict[str, str] = {}
    if isinstance(weapons, list):
        for group in weapons:
            if isinstance(group, dict) and isinstance(group.get("weapons"), dict):
                mount_map.update({str(k): str(v) for k, v in group["weapons"].items()})
    return Variant(id=str(raw.get("variantId", path.stem)), name=str(raw.get("displayName", path.stem)), source_mod=source_mod,
                   source_path=path, hull_id=raw.get("hullId"), weapons_by_mount=mount_map,
                   hullmods=tuple(raw.get("hullMods", raw.get("mods", []))), fighter_wings=tuple(raw.get("wings", [])),
                   flux_vents=optional_int(raw.get("fluxVents"), warnings=numeric_warnings, field="fluxVents"), flux_capacitors=optional_int(raw.get("fluxCapacitors"), warnings=numeric_warnings, field="fluxCapacitors"), raw=raw)


def faction_from_file(path: Path, source_mod: str, *, numeric_warnings: list[dict[str, object]] | None = None) -> Faction:
    raw = json_file(path)
    def listed(value: Any, nested_key: str) -> tuple[str, ...]:
        if isinstance(value, list):
            return tuple(str(item) for item in value)
        if isinstance(value, dict) and isinstance(value.get(nested_key), list):
            return tuple(str(item) for item in value[nested_key])
        return ()
    return Faction(id=str(raw.get("id", path.stem)), name=str(raw.get("displayName", raw.get("name", path.stem))),
                   source_mod=source_mod, source_path=path, known_hulls=listed(raw.get("knownShips"), "hulls"),
                   known_weapons=listed(raw.get("knownWeapons"), "weapons"),
                   known_fighters=listed(raw.get("knownFighters"), "fighters"),
                   known_hullmods=listed(raw.get("knownHullMods"), "hullMods"),
                   tags=tuple(str(item) for item in raw.get("tags", [])) if isinstance(raw.get("tags"), list) else (), raw=raw)
