"""Adapter-backed, static COMBAT hullmod analysis.

Targets `Weapon.range` (core/models.py) via the two verified vanilla
COMBAT hullmods in `adapters.vanilla.COMBAT_HULLMOD_EFFECTS`
(`targetingunit`, `dedicated_targeting_core`) -- see that table's own
docstring/comment for the full research trail.

Unlike `flux_stats.py`/`combat_stats.py`/`mobility_stats.py`, this is the
first category whose verified effect lives on `Weapon`, not `Hull`: the
hullmod is installed on the hull, but the percent range bonus it grants
applies individually to each *equipped* weapon (via `Variant.weapons_by_mount`)
whose `mount_type` matches the hullmod's documented weapon types. So this
module's entry point takes the whole `Variant`, not a bare `hullmod_ids`
iterable, and evaluates one `AppliedWeaponRangeEffect` per (hullmod, mount)
pair rather than per (hullmod, hull-stat) pair.

Same discipline as every other verified category: a hullmod with no
verified entry, or whose hull_size/mount_type/weapon-range data doesn't
match, contributes nothing and is reported in `unverified_hullmod_ids`
rather than silently ignored; when 2+ verified hullmods apply to the SAME
mount (both `targetingunit` and `dedicated_targeting_core` grant a percent
range bonus, and vanilla does not document how two percent bonuses on the
same stat combine), no combined value is fabricated -- each contribution
stays individually visible in `applied_effects`, and the collision is
recorded in `stacking_notes`.
"""

from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.adapters import combat_hullmod_effects
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Variant
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class AppliedWeaponRangeEffect:
    """One verified COMBAT hullmod effect, applied to one equipped weapon's
    true base `range` in isolation -- never against a running total updated
    by another hullmod, so the order hullmod_ids are supplied in never
    changes the result (same discipline as AppliedFluxEffect/
    AppliedDefenseEffect/AppliedMobilityEffect).
    """

    hullmod_id: str
    mount_id: str
    weapon_id: str
    stat: str
    base_range: float
    operation: str
    percent_bonus: float
    resulting_range_alone: float
    delta: float
    op_cost: int | None
    efficiency: float | None
    # ROADMAP.md Phase 29 (Evidence/Provenance Unification): always sourced
    # from a verified adapters.combat_hullmod_effects table entry --
    # AGENTS.md's adapter-layer ladder tier 6, ADAPTER_MODELED. Always
    # correct by construction; a hullmod without a verified entry never
    # produces one of these records.
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class DerivedWeaponRangeStats:
    """A COMBAT-category slice of derived per-variant state: each equipped
    weapon's base `range`, as modified by verified COMBAT hullmods
    (`adapters.combat_hullmod_effects`).

    A hullmod without a verified entry, or whose `percent_bonus_by_hull_size`
    doesn't cover this hull's `hull_size`, or whose `applies_to_mount_types`
    doesn't match a given equipped weapon's `mount_type`, contributes
    nothing to that weapon -- absence of verified data is never treated as
    absence of effect. `effective_range_by_mount` gives the resolved range
    for a mount only when exactly one verified hullmod applies to it; a
    mount with zero applicable hullmods is simply absent from this mapping
    (its range is unchanged from the weapon's own base value, already
    available via the registry), and a mount with 2+ applicable hullmods
    maps to `None` (see `stacking_notes`) with each contribution still
    available individually in `applied_effects`.
    """

    applied_effects: tuple[AppliedWeaponRangeEffect, ...]
    effective_range_by_mount: dict[str, float | None]
    unverified_hullmod_ids: tuple[str, ...]
    stacking_notes: tuple[str, ...]

    @property
    def applied_effect_hullmod_ids(self) -> tuple[str, ...]:
        """Unique hullmod ids with at least one applied effect, in first-seen order."""
        seen: dict[str, None] = {}
        for effect in self.applied_effects:
            seen.setdefault(effect.hullmod_id, None)
        return tuple(seen)


def compute_derived_combat_stats(hull: Hull, variant: Variant, registry: Registry) -> DerivedWeaponRangeStats:
    """Apply verified COMBAT hullmod effects to each weapon equipped on `variant`.

    Deliberately does not compute a single combined effective range when
    more than one applied hullmod targets the same mount -- whether
    vanilla combines two percent range bonuses by summing the percentages,
    multiplying the factors, or something else entirely is not documented
    anywhere this project can verify (and this combination is illegal in
    vanilla in the first place -- see `adapters.vanilla.HullmodCombatEffect`'s
    own docstring), so guessing would violate Agent.md's "do not infer
    undocumented behavior" rule. Each contribution is reported individually
    in `applied_effects` instead, exactly like
    compute_derived_flux_stats/_defense_stats/_mobility_stats already do
    for their own same-stat collisions.
    """
    effects_by_hullmod: dict[str, list] = {}
    for effect in combat_hullmod_effects(hull.source_mod):
        effects_by_hullmod.setdefault(effect.hullmod_id, []).append(effect)

    applied_by_mount: dict[str, list[AppliedWeaponRangeEffect]] = {}
    unverified: list[str] = []

    for hullmod_id in variant.hullmods:
        effect_list = effects_by_hullmod.get(hullmod_id)
        if not effect_list:
            unverified.append(hullmod_id)
            continue
        any_applied = False
        for effect in effect_list:
            bonus = effect.percent_bonus_by_hull_size.get(hull.hull_size or "")
            if bonus is None:
                continue
            for mount_id, weapon_id in variant.weapons_by_mount.items():
                weapon = registry.weapons.by_id.get(weapon_id)
                if weapon is None or weapon.mount_type not in effect.applies_to_mount_types:
                    continue
                base_range = weapon.range
                if base_range is None:
                    continue
                resulting_range_alone = base_range * (1.0 + bonus)
                delta = resulting_range_alone - base_range
                registry_hullmod = registry.hullmods.by_id.get(hullmod_id)
                op_cost = registry_hullmod.op_cost_by_hull_size.get(hull.hull_size or "") if registry_hullmod else None
                efficiency = (delta / op_cost) if op_cost else None
                applied_by_mount.setdefault(mount_id, []).append(
                    AppliedWeaponRangeEffect(
                        hullmod_id, mount_id, weapon_id, effect.stat, base_range, "percent_add",
                        bonus, resulting_range_alone, delta, op_cost, efficiency,
                    )
                )
                any_applied = True
        if not any_applied:
            unverified.append(hullmod_id)

    effective_range_by_mount: dict[str, float | None] = {}
    stacking_notes: list[str] = []
    for mount_id, appliers in applied_by_mount.items():
        if len(appliers) == 1:
            effective_range_by_mount[mount_id] = appliers[0].resulting_range_alone
        else:
            effective_range_by_mount[mount_id] = None
            ids = ", ".join(effect.hullmod_id for effect in appliers)
            stacking_notes.append(
                f"mount {mount_id} (weapon {appliers[0].weapon_id}): {len(appliers)} verified hullmods apply ({ids}) -- "
                "combined stacking behavior across multiple hullmods on the same weapon's range is not documented, so "
                "no combined effective value is computed; see applied_effects for each hullmod's individual "
                "contribution against the base value."
            )

    applied_effects = tuple(effect for mount_id in variant.weapons_by_mount for effect in applied_by_mount.get(mount_id, ()))
    return DerivedWeaponRangeStats(
        applied_effects=applied_effects,
        effective_range_by_mount=effective_range_by_mount,
        unverified_hullmod_ids=tuple(unverified),
        stacking_notes=tuple(stacking_notes),
    )
