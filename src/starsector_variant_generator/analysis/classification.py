from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.core.models import FighterWing, Hull, Hullmod, Weapon


@dataclass(frozen=True)
class WeaponClassification:
    role_tags: tuple[str, ...]
    range_band: str


@dataclass(frozen=True)
class HullClassification:
    role_compatibility: dict[str, float]


@dataclass(frozen=True)
class FighterClassification:
    role_tags: tuple[str, ...]


@dataclass(frozen=True)
class HullmodClassification:
    property_tags: tuple[str, ...]


@dataclass(frozen=True)
class CivilianRoleClassification:
    role_tags: tuple[str, ...]
    is_civilian: bool
    cargo_capacity: float | None
    fuel_capacity: float | None


def classify_weapon(weapon: Weapon) -> WeaponClassification:
    """Return directly explainable tags from normalized source fields."""
    tags: set[str] = set()
    damage = (weapon.damage_type or "").upper()
    raw_tags = str(weapon.raw.get("tags", "")).lower()
    if damage == "KINETIC":
        tags.add("KINETIC_PRESSURE")
    if damage in {"HIGH_EXPLOSIVE", "HE"}:
        tags.add("ARMOR_BREAKER")
    if "pd" in raw_tags:
        tags.add("PD")
    if weapon.mount_type == "MISSILE":
        tags.add("MISSILE_PRESSURE")
    if weapon.range is None:
        band = "UNKNOWN"
    elif weapon.range < 500:
        band = "SHORT"
    elif weapon.range < 900:
        band = "MEDIUM"
    else:
        band = "LONG"
        tags.add("ARTILLERY")
    return WeaponClassification(tuple(sorted(tags)), band)


def classify_hull(hull: Hull) -> HullClassification:
    """Produce non-exclusive compatibility scores from mount/fighter evidence."""
    mounts = hull.weapon_mounts
    total = len(mounts)
    missile_fraction = sum(str(mount.get("type", "")).upper() == "MISSILE" for mount in mounts) / total if total else 0.0
    large_fraction = sum(str(mount.get("size", "")).upper() == "LARGE" for mount in mounts) / total if total else 0.0
    has_normalized_bay_evidence = bool(hull.launch_bay_slots or hull.built_in_fighter_wings)
    carrier = 1.0 if has_normalized_bay_evidence else (1.0 if (hull.fighter_bays or 0) > 0 else 0.0)
    return HullClassification({
        "CARRIER": carrier,
        "BATTLE_CARRIER": min(1.0, carrier * 0.6 + large_fraction * 0.4),
        "MISSILE_SUPPORT": missile_fraction,
        "LINE_ARTILLERY": large_fraction,
        "LINE_BRAWLER": min(1.0, total / 8.0),
    })


def classify_fighter(wing: FighterWing) -> FighterClassification:
    """Expose parsed role text as evidence, without inferring combat performance."""
    return FighterClassification((f"SOURCE_ROLE:{wing.role.upper()}",) if wing.role else ("SOURCE_ROLE:UNKNOWN",))


def classify_civilian_role(hull: Hull) -> CivilianRoleClassification:
    """Expose the hull CSV's own documented "hints" column as evidence tags.

    Verified real values across a live install's 211 core hulls: CIVILIAN
    (17), CARRIER (9), FREIGHTER (6), COMBAT (6), LINER (4), TANKER (4),
    TRANSPORT (2), plus structural markers (UNBOARDABLE, MODULE, STATION,
    HIDE_IN_CODEX) that aren't role signals at all.

    Deliberately does NOT compute numeric role-compatibility scores across
    HULLMODS_CIVILIAN_AND_REFIT.md's full 9-role taxonomy (FREIGHTER/
    TANKER/SALVAGE/SURVEY/TROOP_TRANSPORT/FAST_LOGISTICS/
    STEALTH_LOGISTICS/EXPEDITION_SUPPORT/GENERAL_SUPPORT). A cargo/fuel
    ratio-based secondary signal for hulls without an explicit hint was
    tried and found unreliable against the same real data: civilian- and
    combat-hinted hulls have nearly identical cargo capacity medians (95
    vs 100), so a numeric threshold would misclassify freely. `hints`
    only directly covers a subset of the spec's role vocabulary (roughly
    CIVILIAN/FREIGHTER/TANKER/CARRIER/COMBAT/LINER/TRANSPORT), not all 9
    named roles -- mapping this evidence onto full per-role compatibility
    scores is a real next step (docs/ROADMAP.md), not fabricated here on
    weak grounds.
    """
    tags = tuple(hint for hint in hull.hull_hints if hint not in {"UNBOARDABLE", "MODULE", "STATION", "HIDE_IN_CODEX", "UNDER_PARENT", "SHIP_WITH_MODULES"})
    return CivilianRoleClassification(
        role_tags=tags,
        is_civilian="CIVILIAN" in tags,
        cargo_capacity=hull.cargo_capacity,
        fuel_capacity=hull.fuel_capacity,
    )


def classify_hullmod(hullmod: Hullmod) -> HullmodClassification:
    """Expose directly parsed hullmod properties; no mechanical synergy is inferred."""
    tags: set[str] = set()
    if hullmod.hidden is True:
        tags.add("HIDDEN")
    if hullmod.built_in_only is True:
        tags.add("BUILT_IN_ONLY")
    if hullmod.op_cost_by_hull_size:
        tags.add("OP_TABLE_PRESENT")
    return HullmodClassification(tuple(sorted(tags)))
