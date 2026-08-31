"""STATIC_CONTROL_SUITABILITY: static, structural piloting-demand signals.

ROADMAP.md Phase 41 (the user's own "Phase 7", deliberately last in that
round -- gated on "only after mechanics are strong enough").

**This module is NOT a combat outcome predictor.** It never estimates win
chance, expected damage traded, time-to-kill, or any other simulated or
inferred gameplay outcome. Every field it produces is a static, structural
reading of a build's own already-parsed/adapter-modeled stats -- e.g. "these
mounted weapons have a 1400-unit range spread" or "this hull's real armor
hullmods add 40% effective armor" -- describing how demanding a build is
*to fly well* (how much the pilot has to manage range bands, flux margin,
burst timing, ammo, weapon groups, and a ship system), never how well it
*performs* in a fight. This matches AGENTS.md's "No AI Dependency" rule and
the project charter's own explicit non-goal: "no speculative AI combat
prediction."

Same discipline as every other `analysis/` module: describes evidence only,
never legality (never imports `validation/legality.py`), and never
contributes to `scoring/candidate_score.py`'s ranking. A signal is `None`
when its underlying evidence is genuinely unavailable -- never a fabricated
default. No field here combines multiple signals into one number; each
signal stays independently computed and independently cited, per this
phase's own instruction not to invent an unjustified combined weighting.

Evidence backing each signal:
- `range_coherence` -- each equipped weapon's own real, parsed `Weapon.range`
  (`core/models.py`), the same field `scoring/candidate_score.py`'s
  `range_coherence` component reads. Deliberately reads the raw base range,
  not `analysis/weapon_range_stats.py`'s opt-in COMBAT-hullmod-adjusted
  range (that adjustment is heuristic_set-gated quality scoring machinery;
  a caller who wants the hullmod-adjusted number already has direct access
  to `weapon_range_stats.py`), so this signal has no heuristic_set
  dependency at all. `DIRECT_DATA`.
- `flux_stability` -- `Hull.flux_dissipation`/`Hull.shield_upkeep` and each
  equipped weapon's `Weapon.flux_per_second` (all real parsed fields),
  combined the same way `scoring/candidate_score.py::_flux_component`
  combines them (dissipation / sustained load) but reported as a raw ratio,
  never scored against a heuristic target. `DIRECT_DATA`.
- `burst_dependence` -- `Weapon.flux_per_shot` / `Weapon.flux_per_second`
  (both real parsed fields, Starsector's own "energy/shot" and
  "energy/second" weapon_data.csv columns). Their ratio is seconds-per-shot
  at sustained fire -- a real, directly computable quantity, not a guessed
  rate-of-fire. A weapon with no discrete per-shot cost (e.g. a continuous
  beam; `flux_per_shot` absent or 0) is excluded from the average rather
  than assigned a fabricated interval. `DIRECT_DATA`.
- `ammo_dependence` -- `Weapon.mount_type`. This project's schema has no
  typed ammunition-count field anywhere (verified: no `.wpn`/weapon_data.csv
  "ammo" or "max ammo" column is parsed into `Weapon` or read by any other
  `analysis/` module). `MISSILE` is the only mount type in this schema
  associated with a depleting ammo pool in vanilla Starsector; `BALLISTIC`/
  `ENERGY` weapons draw flux instead. This signal is therefore an honest,
  documented mount-type-based proxy for ammo dependence (the OP-weighted
  fraction of mounted firepower on `MISSILE` mounts), not a real ammo-count
  read -- the docstring says so explicitly so it is never mistaken for one.
  `DIRECT_DATA`.
- `mobility_vs_engagement_range` -- `analysis/mobility_stats.py`'s verified
  adapter-modeled effective `max_speed` alongside the same real equipped
  weapon ranges `range_coherence` uses. Reports both numbers side by side;
  deliberately does not compute a combined "mismatch score", since no
  documented Starsector formula establishes a "correct" speed for a given
  weapon range -- inventing one would be exactly the undocumented-behavior
  guess AGENTS.md forbids. `ADAPTER_MODELED` (gated by the mobility slice,
  which is the harder-to-satisfy half of this signal).
- `system_complexity` -- the hull's own real `shipSystemId` (`.ship` file)
  or `systemId` (`.skin` override), preserved verbatim under
  `Hull.raw["ship_data"]`/`Hull.raw["skin_data"]` (see
  `parsers/entities.py::hull_from_row`/`hull_from_skin`) since
  `core/models.py::Hull` has no typed system field. Reports only presence
  and identity of a ship system -- this project has no per-system mechanical
  complexity metadata to grade "how complex" a given system is, so it does
  not attempt to. `DIRECT_DATA`.
- `weapon_group_complexity` -- countable structural facts about the build's
  own mounts: how many equipped mounts, how many distinct `mount_type`
  values among them, and (when the source `.variant` file is available) how
  many `weaponGroups` it declares (`Variant.raw["weaponGroups"]`, preserved
  verbatim by `parsers/entities.py::variant_from_file`). A real, countable
  "how much does the pilot have to juggle" signal, never an inferred
  difficulty rating. `DIRECT_DATA`.
- `survivability_posture` -- `analysis/combat_stats.py::compute_derived_defense_stats`,
  the same verified DEFENSE-hullmod-adjusted armor/hull-HP evidence already
  used for Phase 12's TANK-archetype mechanical tie-break
  (`analysis/mechanical_archetypes.py`). `ADAPTER_MODELED`.
"""

from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.analysis.combat_stats import (
    compute_derived_defense_stats,
)
from starsector_variant_generator.analysis.mobility_stats import (
    compute_derived_mobility_stats,
)
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Variant, Weapon
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class RangeCoherenceSignal:
    """Real base `Weapon.range` spread across this build's equipped weapons."""

    weapon_ranges: tuple[float, ...]
    range_spread: float
    mean_range: float
    evidence_class: EvidenceClass = EvidenceClass.DIRECT_DATA


@dataclass(frozen=True)
class FluxStabilitySignal:
    """Raw dissipation-vs-sustained-load ratio; not scored against a heuristic target."""

    flux_dissipation: float
    sustained_flux_load: float
    # None only when sustained_flux_load <= 0 (e.g. an unarmed loadout with
    # no shield upkeep known) -- the ratio is undefined, not zero.
    dissipation_ratio: float | None
    evidence_class: EvidenceClass = EvidenceClass.DIRECT_DATA


@dataclass(frozen=True)
class BurstDependenceSignal:
    """Seconds-per-shot proxy (flux_per_shot / flux_per_second) per mount."""

    per_mount_shot_intervals: tuple[tuple[str, float], ...]
    mean_shot_interval: float
    # Equipped weapon ids with no discrete per-shot flux cost (e.g. beams) --
    # excluded from the average, not assigned a fabricated interval.
    excluded_weapon_ids: tuple[str, ...]
    evidence_class: EvidenceClass = EvidenceClass.DIRECT_DATA


@dataclass(frozen=True)
class AmmoDependenceSignal:
    """`MISSILE`-mount fraction, this schema's only real ammo-depletion proxy."""

    missile_mount_count: int
    total_mount_count: int
    # None only when no resolved weapon in this build has known ordnance_points.
    missile_op_fraction: float | None
    evidence_class: EvidenceClass = EvidenceClass.DIRECT_DATA


@dataclass(frozen=True)
class MobilityEngagementSignal:
    """Real effective mobility alongside real equipped weapon ranges, unfused."""

    effective_max_speed: float | None
    mean_weapon_range: float | None
    max_weapon_range: float | None
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class SystemComplexitySignal:
    """Real, parsed ship-system presence/identity -- not a graded difficulty."""

    has_ship_system: bool
    ship_system_id: str | None
    evidence_class: EvidenceClass = EvidenceClass.DIRECT_DATA


@dataclass(frozen=True)
class WeaponGroupComplexitySignal:
    """Countable mount/group facts -- never an inferred difficulty rating."""

    equipped_mount_count: int
    distinct_mount_type_count: int
    # None only when the source `.variant` file's own "weaponGroups" list
    # isn't available (e.g. a synthetically constructed Variant in tests).
    weapon_group_count: int | None
    evidence_class: EvidenceClass = EvidenceClass.DIRECT_DATA


@dataclass(frozen=True)
class SurvivabilityPostureSignal:
    """Verified DEFENSE-hullmod-adjusted armor/hull-HP, mirroring the Phase 12 TANK tie-break."""

    armor_rating_base: float | None
    hull_hp_base: float | None
    effective_armor_rating: float | None
    effective_hull_hp: float | None
    applied_defense_hullmod_ids: tuple[str, ...]
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class StaticControlSuitability:
    """STATIC_CONTROL_SUITABILITY for one variant.

    A static, structural signal set describing how demanding this build is
    to fly well (range-band discipline, flux margin, burst timing, ammo
    management, ship-system/weapon-group juggling, survivability posture)
    -- **never** a prediction of combat performance, win chance, or any
    other simulated/inferred outcome. Each field is independently cited and
    independently `None`-able; there is deliberately no combined score.
    """

    variant_id: str
    hull_id: str
    range_coherence: RangeCoherenceSignal | None
    flux_stability: FluxStabilitySignal | None
    burst_dependence: BurstDependenceSignal | None
    ammo_dependence: AmmoDependenceSignal | None
    mobility_vs_engagement_range: MobilityEngagementSignal | None
    system_complexity: SystemComplexitySignal | None
    weapon_group_complexity: WeaponGroupComplexitySignal | None
    survivability_posture: SurvivabilityPostureSignal | None


def _resolve_weapons(variant: Variant, registry: Registry) -> list[tuple[str, Weapon]]:
    """Equipped (mount_id, Weapon) pairs whose weapon id resolves in the registry.

    A mount referencing an unresolved/missing weapon id is silently excluded
    from every downstream signal below (structural absence of evidence, not
    a fabricated zero) -- the same discipline `weapon_range_stats.py` uses.
    """
    resolved: list[tuple[str, Weapon]] = []
    for mount_id, weapon_id in variant.weapons_by_mount.items():
        weapon = registry.weapons.by_id.get(weapon_id)
        if weapon is not None:
            resolved.append((mount_id, weapon))
    return resolved


def _range_coherence(resolved: list[tuple[str, Weapon]]) -> RangeCoherenceSignal | None:
    ranges = [weapon.range for _, weapon in resolved if weapon.range is not None]
    if not ranges:
        return None
    return RangeCoherenceSignal(tuple(ranges), max(ranges) - min(ranges), sum(ranges) / len(ranges))


def _flux_stability(hull: Hull, resolved: list[tuple[str, Weapon]]) -> FluxStabilitySignal | None:
    if hull.flux_dissipation is None:
        return None
    if any(weapon.flux_per_second is None for _, weapon in resolved):
        return None
    sustained_flux_load = sum(weapon.flux_per_second or 0.0 for _, weapon in resolved) + (hull.shield_upkeep or 0.0)
    ratio = (hull.flux_dissipation / sustained_flux_load) if sustained_flux_load > 0 else None
    return FluxStabilitySignal(hull.flux_dissipation, sustained_flux_load, ratio)


def _burst_dependence(resolved: list[tuple[str, Weapon]]) -> BurstDependenceSignal | None:
    intervals: list[tuple[str, float]] = []
    excluded: list[str] = []
    for mount_id, weapon in resolved:
        if weapon.flux_per_shot and weapon.flux_per_second and weapon.flux_per_second > 0:
            intervals.append((mount_id, weapon.flux_per_shot / weapon.flux_per_second))
        else:
            excluded.append(weapon.id)
    if not intervals:
        return None
    mean_interval = sum(value for _, value in intervals) / len(intervals)
    return BurstDependenceSignal(tuple(intervals), mean_interval, tuple(dict.fromkeys(excluded)))


def _ammo_dependence(resolved: list[tuple[str, Weapon]]) -> AmmoDependenceSignal | None:
    if not resolved:
        return None
    missile_count = sum(1 for _, weapon in resolved if (weapon.mount_type or "").upper() == "MISSILE")
    op_values = [(weapon.ordnance_points or 0, (weapon.mount_type or "").upper() == "MISSILE") for _, weapon in resolved if weapon.ordnance_points is not None]
    total_op = sum(op for op, _ in op_values)
    fraction = (sum(op for op, is_missile in op_values if is_missile) / total_op) if total_op > 0 else None
    return AmmoDependenceSignal(missile_count, len(resolved), fraction)


def _mobility_vs_engagement_range(hull: Hull, variant: Variant, resolved: list[tuple[str, Weapon]], registry: Registry) -> MobilityEngagementSignal | None:
    mobility = compute_derived_mobility_stats(hull, variant.hullmods, registry)
    # Fall back to the unmodified base value when 2+ verified mobility
    # hullmods collided on max_speed (compute_derived_mobility_stats refuses
    # to fabricate a combined number there) -- same discipline as
    # scoring/candidate_score.py::_hullmod_adjusted_stat.
    effective_speed = mobility.effective_values.get("max_speed")
    if effective_speed is None:
        effective_speed = mobility.base_values.get("max_speed")
    ranges = [weapon.range for _, weapon in resolved if weapon.range is not None]
    mean_range = (sum(ranges) / len(ranges)) if ranges else None
    max_range = max(ranges) if ranges else None
    if effective_speed is None and mean_range is None:
        return None
    return MobilityEngagementSignal(effective_speed, mean_range, max_range)


def _system_complexity(hull: Hull, registry: Registry) -> SystemComplexitySignal | None:
    skin_data = hull.raw.get("skin_data")
    if isinstance(skin_data, dict) and "systemId" in skin_data:
        value = skin_data.get("systemId")
        system_id = value if isinstance(value, str) and value else None
        return SystemComplexitySignal(system_id is not None, system_id)
    ship_data = hull.raw.get("ship_data")
    if isinstance(ship_data, dict):
        value = ship_data.get("shipSystemId")
        system_id = value if isinstance(value, str) and value else None
        return SystemComplexitySignal(system_id is not None, system_id)
    # A skin whose own skin_data doesn't override systemId at all: fall back
    # one level to the resolved base hull's ship_data, the same single-level
    # fallback discipline as _base_mobility_stat/_base_defense_stat.
    base_hull_id = hull.raw.get("base_hull_id")
    if isinstance(base_hull_id, str):
        base_hull = registry.hulls.by_id.get(base_hull_id)
        if base_hull is not None:
            base_ship_data = base_hull.raw.get("ship_data")
            if isinstance(base_ship_data, dict):
                value = base_ship_data.get("shipSystemId")
                system_id = value if isinstance(value, str) and value else None
                return SystemComplexitySignal(system_id is not None, system_id)
    return None


def _weapon_group_complexity(variant: Variant, resolved: list[tuple[str, Weapon]]) -> WeaponGroupComplexitySignal | None:
    mount_types = {(weapon.mount_type or "").upper() for _, weapon in resolved if weapon.mount_type}
    weapon_groups = variant.raw.get("weaponGroups")
    group_count = len(weapon_groups) if isinstance(weapon_groups, list) else None
    return WeaponGroupComplexitySignal(len(variant.weapons_by_mount), len(mount_types), group_count)


def _survivability_posture(hull: Hull, variant: Variant, registry: Registry) -> SurvivabilityPostureSignal | None:
    stats = compute_derived_defense_stats(hull, variant.hullmods, registry)
    if stats.armor_rating_base is None and stats.hull_hp_base is None:
        return None
    return SurvivabilityPostureSignal(
        stats.armor_rating_base, stats.hull_hp_base,
        stats.effective_armor_rating, stats.effective_hull_hp,
        stats.applied_effect_hullmod_ids,
    )


def compute_static_control_suitability(variant: Variant, hull: Hull, registry: Registry) -> StaticControlSuitability:
    """Compute STATIC_CONTROL_SUITABILITY for `variant` (equipped on `hull`).

    Pure and read-only, matching every other `analysis/` module: never
    touches `validation/legality.py`, never influences `scoring/`, and never
    fabricates a value when the underlying evidence is unavailable -- see
    this module's own docstring for the exact evidence backing each signal.
    """
    resolved = _resolve_weapons(variant, registry)
    return StaticControlSuitability(
        variant_id=variant.id,
        hull_id=hull.id,
        range_coherence=_range_coherence(resolved),
        flux_stability=_flux_stability(hull, resolved),
        burst_dependence=_burst_dependence(resolved),
        ammo_dependence=_ammo_dependence(resolved),
        mobility_vs_engagement_range=_mobility_vs_engagement_range(hull, variant, resolved, registry),
        system_complexity=_system_complexity(hull, registry),
        weapon_group_complexity=_weapon_group_complexity(variant, resolved),
        survivability_posture=_survivability_posture(hull, variant, registry),
    )
