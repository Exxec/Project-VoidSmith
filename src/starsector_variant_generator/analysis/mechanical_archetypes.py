"""Deterministic, evidence-preserving mechanical hull archetype inference.

This module deliberately describes *compatibility*, not a canonical ship
class.  A hull may, for example, be both an artillery platform and a battle
carrier.  Scores are derived only from normalized hull fields, parseable raw
hull columns, mount layout, and aggregate existing-variant observations.
Existing variants are a weak statistical observation: they can increase a
score, but cannot establish an archetype without structural hull evidence.

The output is intended to be persisted alongside a recommendation so a later
``why-not`` implementation can identify the exact score and evidence used in
a diversity decision.  It has no legality implications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starsector_variant_generator.analysis.classification import classify_weapon
from starsector_variant_generator.core.models import Hull, Variant
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.parsers.common import parse_float

if TYPE_CHECKING:
    from starsector_variant_generator.core.registry import Registry


ARCHETYPES = (
    "ARMOR_BRAWLER", "SHIELD_BRAWLER", "LINE_SHIP", "ARTILLERY",
    "SKIRMISHER", "STRIKER", "MISSILE_SUPPORT", "PD_ESCORT",
    "LIGHT_CARRIER", "HEAVY_CARRIER", "BATTLECARRIER", "COMBAT_FREIGHTER",
    "FREIGHTER", "TANKER", "SALVAGE_SUPPORT", "SURVEY_SUPPORT",
)


@dataclass(frozen=True)
class HullFeatureVector:
    """Raw-or-normalized inputs used by :func:`infer_mechanical_archetypes`.

    ``None`` means that the scanned source did not provide a value.  The
    vector intentionally keeps absolute values instead of hiding them behind
    an opaque feature normalization.
    """

    hull_id: str
    hull_size: str | None
    ordnance_points: int | None
    armor_rating: float | None
    hull_hitpoints: float | None
    has_shield: bool | None
    shield_upkeep: float | None
    flux_capacity: float | None
    flux_dissipation: float | None
    max_speed: float | None
    acceleration: float | None
    deceleration: float | None
    max_turn_rate: float | None
    turn_acceleration: float | None
    mount_count: int
    small_mounts: int
    medium_mounts: int
    large_mounts: int
    ballistic_mounts: int
    energy_mounts: int
    missile_mounts: int
    composite_mounts: int
    universal_mounts: int
    mean_mount_arc: float | None
    narrow_arc_mount_fraction: float | None
    fighter_bays: int | None
    cargo_capacity: float | None
    fuel_capacity: float | None
    supplies_per_month: float | None
    max_burn: float | None
    hull_hints: tuple[str, ...]
    built_in_hullmods: tuple[str, ...]
    built_in_weapons: tuple[str, ...]
    ship_system_id: str | None
    known_ship_system_categories: tuple[str, ...]
    existing_variant_count: int
    variant_missile_mount_fraction: float | None
    variant_pd_weapon_fraction: float | None
    variant_long_range_weapon_fraction: float | None
    variant_fighter_wing_fraction: float | None


@dataclass(frozen=True)
class MechanicalArchetypeProfile:
    hull_id: str
    feature_vector: HullFeatureVector
    compatibility_scores: dict[str, float]
    evidence_by_archetype: dict[str, tuple[str, ...]]
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


def infer_hull_feature_vector(
    hull: Hull, registry: Registry | None = None, variants: tuple[Variant, ...] | None = None,
) -> HullFeatureVector:
    """Extract a stable feature vector without interpreting unknown scripts."""
    raw = hull.raw
    mounts = hull.weapon_mounts
    types = [str(mount.get("type", "")).upper() for mount in mounts]
    sizes = [str(mount.get("size", "")).upper() for mount in mounts]
    arcs = [_number(mount.get("arc")) for mount in mounts]
    known_categories = _string_tuple(_raw_value(raw, "ship system categories", "shipSystemCategories", "systemCategory", "system_category"))
    system_id = _string_value(_raw_value(raw, "ship system id", "shipSystemId", "systemId", "system"))
    # A caller may supply one explicitly selected existing variant.  That is
    # descriptive evidence about the locked player selection, not a claim
    # that the hull's other indexed fits are simultaneously equipped.
    variants = variants if variants is not None else (registry.variants_for_hull(hull.id) if registry is not None else ())
    missile_fractions: list[float] = []
    pd_fractions: list[float] = []
    long_fractions: list[float] = []
    fighter_fractions: list[float] = []
    for variant in variants:
        weapons = tuple(variant.weapons_by_mount.values())
        if weapons:
            missile_fractions.append(sum(
                registry.weapons.by_id.get(weapon_id) is not None and registry.weapons.by_id[weapon_id].mount_type == "MISSILE"
                for weapon_id in weapons) / len(weapons))
            classified = [classify_weapon(registry.weapons.by_id[weapon_id]) for weapon_id in weapons if weapon_id in registry.weapons.by_id]
            if classified:
                pd_fractions.append(sum("PD" in item.role_tags for item in classified) / len(classified))
                long_fractions.append(sum(item.range_band == "LONG" for item in classified) / len(classified))
        fighter_fractions.append(1.0 if variant.fighter_wings else 0.0)
    finite_arcs = [arc for arc in arcs if arc is not None]
    return HullFeatureVector(
        hull.id, hull.hull_size, hull.ordnance_points,
        _number(_raw_value(raw, "armor rating", "armor_rating", "armor")),
        _number(_raw_value(raw, "hitpoints", "hull hp", "hull_hp")),
        _shield_present(raw), hull.shield_upkeep, hull.flux_capacity, hull.flux_dissipation,
        _number(_raw_value(raw, "max speed", "maxSpeed", "max_speed")),
        _number(_raw_value(raw, "acceleration")), _number(_raw_value(raw, "deceleration")),
        _number(_raw_value(raw, "max turn rate", "maxTurnRate", "max_turn_rate")),
        _number(_raw_value(raw, "turn acceleration", "turnAcceleration", "turn_acceleration")),
        len(mounts), sizes.count("SMALL"), sizes.count("MEDIUM"), sizes.count("LARGE"),
        types.count("BALLISTIC"), types.count("ENERGY"), types.count("MISSILE"),
        types.count("COMPOSITE"), types.count("UNIVERSAL"),
        sum(finite_arcs) / len(finite_arcs) if finite_arcs else None,
        sum(arc <= 90.0 for arc in finite_arcs) / len(finite_arcs) if finite_arcs else None,
        hull.fighter_bays, hull.cargo_capacity, hull.fuel_capacity, hull.supplies_per_month,
        hull.max_burn, tuple(sorted({hint.upper() for hint in hull.hull_hints})),
        tuple(sorted(hull.built_in_hullmods)), tuple(sorted(hull.built_in_weapons.values())),
        system_id, known_categories, len(variants),
        _mean(missile_fractions), _mean(pd_fractions), _mean(long_fractions), _mean(fighter_fractions),
    )


def infer_mechanical_archetypes(
    hull: Hull, registry: Registry | None = None, variants: tuple[Variant, ...] | None = None,
) -> MechanicalArchetypeProfile:
    """Return all requested non-exclusive archetype scores and raw evidence.

    The simple, fixed score equations are intentionally local and auditable.
    They are compatibility heuristics only; no threshold turns an inference
    into legality or faction ownership.
    """
    f = infer_hull_feature_vector(hull, registry, variants)
    total = max(f.mount_count, 1)
    heavy_mounts = _ratio(f.medium_mounts + f.large_mounts, total)
    combat_mounts = _ratio(f.ballistic_mounts + f.energy_mounts + f.composite_mounts + f.universal_mounts, total)
    missile_mounts = _ratio(f.missile_mounts, total)
    armor = _scale(f.armor_rating, 1500.0)
    integrity = _scale(f.hull_hitpoints, 15000.0)
    op = _scale(f.ordnance_points, 200.0)
    flux = _mean((_scale(f.flux_capacity, 20000.0), _scale(f.flux_dissipation, 1500.0))) or 0.0
    speed = _scale(f.max_speed, 120.0)
    maneuver = _mean((_scale(f.acceleration, 100.0), _scale(f.max_turn_rate, 100.0), _scale(f.turn_acceleration, 100.0))) or 0.0
    bays = _clamp((f.fighter_bays or 0) / 4.0)
    cargo = _scale(f.cargo_capacity, 1000.0)
    fuel = _scale(f.fuel_capacity, 3000.0)
    civilian = _has_hint(f, "CIVILIAN")
    freighter_hint = _has_hint(f, "FREIGHTER")
    tanker_hint = _has_hint(f, "TANKER")
    salvage_hint = _has_hint(f, "SALVAGE")
    survey_hint = _has_hint(f, "SURVEY")
    combat_hint = _has_hint(f, "COMBAT")
    long_evidence = f.variant_long_range_weapon_fraction or 0.0
    missile_evidence = f.variant_missile_mount_fraction or 0.0
    pd_evidence = f.variant_pd_weapon_fraction or 0.0
    fighter_evidence = f.variant_fighter_wing_fraction or 0.0
    shield = 1.0 if f.has_shield is True else 0.0
    efficient_shield = 1.0 - _scale(f.shield_upkeep, 1.5) if f.shield_upkeep is not None else 0.0
    narrow_arc = f.narrow_arc_mount_fraction or 0.0

    scores = {
        "ARMOR_BRAWLER": _clamp(.38 * armor + .16 * integrity + .18 * heavy_mounts + .14 * op + .14 * (1.0 - speed)),
        "SHIELD_BRAWLER": _clamp(.42 * shield + .18 * efficient_shield + .16 * flux + .14 * heavy_mounts + .10 * (1.0 - speed)),
        "LINE_SHIP": _clamp(.24 * heavy_mounts + .20 * op + .18 * flux + .16 * (armor + integrity) / 2 + .12 * combat_mounts + .10 * (1.0 - speed)),
        "ARTILLERY": _clamp(.42 * _ratio(f.large_mounts, total) + .18 * heavy_mounts + .18 * long_evidence + .12 * flux + .10 * narrow_arc),
        "SKIRMISHER": _clamp(.48 * speed + .27 * maneuver + .15 * flux + .10 * (1.0 - armor)),
        "STRIKER": _clamp(.30 * speed + .20 * maneuver + .20 * heavy_mounts + .18 * narrow_arc + .12 * op),
        "MISSILE_SUPPORT": _clamp(.62 * missile_mounts + .23 * missile_evidence + .10 * _ratio(f.large_mounts, total) + .05 * op),
        "PD_ESCORT": _clamp(.40 * _ratio(f.small_mounts, total) + .34 * pd_evidence + .16 * speed + .10 * maneuver),
        "LIGHT_CARRIER": _clamp(.70 * bays + .15 * fighter_evidence + .15 * (1.0 - heavy_mounts)),
        "HEAVY_CARRIER": _clamp(.70 * bays + .15 * fighter_evidence + .15 * (armor + integrity) / 2),
        "BATTLECARRIER": _clamp(.45 * bays + .25 * combat_mounts + .15 * heavy_mounts + .15 * (armor + integrity) / 2),
        "COMBAT_FREIGHTER": _clamp(.35 * cargo + .30 * combat_mounts + .15 * civilian + .05 * freighter_hint + .15 * combat_hint),
        "FREIGHTER": _clamp(.50 * cargo + .30 * freighter_hint + .15 * civilian + .05 * (1.0 - combat_mounts)),
        "TANKER": _clamp(.50 * fuel + .30 * tanker_hint + .15 * civilian + .05 * (1.0 - combat_mounts)),
        # No ID/name substring guessing: these are only directly declared role
        # hints or parseable category data, plus non-role logistics context.
        "SALVAGE_SUPPORT": _clamp(.70 * salvage_hint + .15 * civilian + .10 * cargo + .05 * fuel),
        "SURVEY_SUPPORT": _clamp(.70 * survey_hint + .15 * civilian + .10 * cargo + .05 * fuel),
    }
    evidence = {archetype: _evidence(archetype, f, scores[archetype]) for archetype in ARCHETYPES}
    return MechanicalArchetypeProfile(hull.id, f, {key: round(scores[key], 6) for key in ARCHETYPES}, evidence)


def _evidence(archetype: str, f: HullFeatureVector, score: float) -> tuple[str, ...]:
    """Stable, deliberately plain evidence usable without recomputing state."""
    facts = [f"score={score:.6f}", f"mounts={f.mount_count} (small={f.small_mounts}, medium={f.medium_mounts}, large={f.large_mounts}; missile={f.missile_mounts})"]
    if archetype in {"ARMOR_BRAWLER", "LINE_SHIP", "HEAVY_CARRIER", "BATTLECARRIER"}:
        facts.append(f"armor_rating={f.armor_rating!r}; hull_hitpoints={f.hull_hitpoints!r}; ordnance_points={f.ordnance_points!r}")
    if archetype in {"SHIELD_BRAWLER", "SKIRMISHER", "STRIKER", "ARTILLERY"}:
        facts.append(f"shield_present={f.has_shield!r}; shield_upkeep={f.shield_upkeep!r}; speed={f.max_speed!r}; maneuver=(accel={f.acceleration!r}, turn={f.max_turn_rate!r})")
    if archetype in {"LIGHT_CARRIER", "HEAVY_CARRIER", "BATTLECARRIER"}:
        facts.append(f"fighter_bays={f.fighter_bays!r}; existing_variant_fighter_fraction={f.variant_fighter_wing_fraction!r}")
    if archetype in {"MISSILE_SUPPORT", "PD_ESCORT", "ARTILLERY"}:
        facts.append(f"existing_variant_evidence=(missile={f.variant_missile_mount_fraction!r}, pd={f.variant_pd_weapon_fraction!r}, long_range={f.variant_long_range_weapon_fraction!r}; variants={f.existing_variant_count})")
    if archetype in {"COMBAT_FREIGHTER", "FREIGHTER", "TANKER", "SALVAGE_SUPPORT", "SURVEY_SUPPORT"}:
        facts.append(f"cargo={f.cargo_capacity!r}; fuel={f.fuel_capacity!r}; hints={f.hull_hints!r}; built_in_hullmods={f.built_in_hullmods!r}")
    if f.ship_system_id or f.known_ship_system_categories:
        facts.append(f"ship_system_id={f.ship_system_id!r}; declared_system_categories={f.known_ship_system_categories!r}")
    return tuple(facts)


def _raw_value(raw: dict[str, Any], *keys: str) -> Any:
    """Look in CSV raw fields, then preserved ship/skin JSON, without coercion."""
    for source in (raw, raw.get("ship_data"), raw.get("skin_data")):
        if not isinstance(source, dict):
            continue
        normalized = {str(key).replace("_", "").replace(" ", "").lower(): value for key, value in source.items()}
        for key in keys:
            value = normalized.get(key.replace("_", "").replace(" ", "").lower())
            if value is not None:
                return value
    return None


def _number(value: Any) -> float | None:
    return parse_float(value)


def _string_value(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (tuple, list)):
        return tuple(sorted(str(item) for item in value if isinstance(item, str) and item))
    return ()


def _shield_present(raw: dict[str, Any]) -> bool | None:
    value = _raw_value(raw, "shield type", "shieldType", "shield")
    if isinstance(value, str):
        return value.upper() not in {"", "NONE", "NULL"}
    return None


def _mean(values: tuple[float | None, ...] | list[float]) -> float | None:
    known = [value for value in values if value is not None]
    return sum(known) / len(known) if known else None


def _scale(value: float | int | None, reference: float) -> float:
    return _clamp(float(value) / reference) if value is not None else 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _has_hint(vector: HullFeatureVector, hint: str) -> float:
    return 1.0 if hint in vector.hull_hints else 0.0
