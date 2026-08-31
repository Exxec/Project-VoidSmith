from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from starsector_variant_generator.adapters import (
    efficiency_hullmod_effects,
    logistics_hullmod_effects,
)
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class AppliedLogisticsEffect:
    """One verified hullmod effect actually applied, with its OP cost.

    `efficiency` (gain per OP spent) is HULLMODS_CIVILIAN_AND_REFIT.md
    section 9's own suggested metric ("cargo / OP_spent_on_logistics") --
    deliberately used instead of a 0-100 "civilian quality score" for the
    same reason survivability scoring was rejected earlier this session:
    an absolute scale needs a normalization reference this project has no
    documented basis for, while a per-OP ratio is self-normalizing and
    reflects the *fitting choice*, not the hull's fixed base stats.
    """

    hullmod_id: str
    stat: str
    base_value: float
    gain: float
    op_cost: int | None
    efficiency: float | None
    # ROADMAP.md Phase 29 (Evidence/Provenance Unification): every instance
    # of this record is, by construction, sourced from a verified
    # `adapters.logistics_hullmod_effects` table entry -- AGENTS.md's
    # adapter-layer ladder tier 6, the shared vocabulary's `ADAPTER_MODELED`.
    # A hullmod without such an entry never produces one of these records
    # (it lands in `unverified_hullmod_ids` instead), so this default is
    # always correct, not a placeholder.
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class AppliedReductionEffect:
    """One verified percent-reduction hullmod effect actually applied.

    Distinct from AppliedLogisticsEffect (which always describes a gain):
    `HullmodPercentReductionEffect` (adapters/vanilla) reduces a stat, so
    `reduced_value` is always <= `base_value`. Kept as its own dataclass
    rather than reusing AppliedLogisticsEffect with a negative `gain`,
    since `efficiency = gain / op_cost` is meaningless for a reduction.
    """

    hullmod_id: str
    stat: str
    base_value: float
    reduced_value: float
    percent_reduction: float
    # See AppliedLogisticsEffect above: always sourced from a verified
    # adapters.efficiency_hullmod_effects table entry -- ADAPTER_MODELED.
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class DerivedCivilianStats:
    """A first, narrow slice of DATA_SCHEMA.md v0.3's DerivedShipState.

    Only cargo/fuel/crew/burn/supplies, and only reflects hullmods with a
    verified entry in adapters.logistics_hullmod_effects (flat-or-percent
    increases) or adapters.efficiency_hullmod_effects (percent reductions)
    -- a hullmod without a verified entry in either table contributes
    nothing here, exactly like the flux/vent-cap engine: absence of
    verified data is never treated as absence of effect. Base (unmodified)
    values remain available on the Hull itself.
    """

    cargo_capacity: float | None
    fuel_capacity: float | None
    crew_max: float | None
    max_burn: float | None
    supplies_per_month: float | None
    crew_min: float | None
    applied_effects: tuple[AppliedLogisticsEffect, ...]
    applied_reduction_effects: tuple[AppliedReductionEffect, ...]
    unverified_hullmod_ids: tuple[str, ...]
    civilian_maintenance_penalty_notes: tuple[str, ...]

    @property
    def applied_effect_hullmod_ids(self) -> tuple[str, ...]:
        """Unique hullmod ids with at least one applied effect, in first-seen order.

        Deduplicated because a single hullmod (e.g. `efficiency_overhaul`,
        which reduces two stats at once) can appear in `applied_effects`/
        `applied_reduction_effects` more than once.
        """
        seen: dict[str, None] = {}
        effects: tuple[AppliedLogisticsEffect | AppliedReductionEffect, ...] = (
            *self.applied_effects, *self.applied_reduction_effects,
        )
        for effect in effects:
            seen.setdefault(effect.hullmod_id, None)
        return tuple(seen)


def compute_derived_civilian_stats(hull: Hull, hullmod_ids: Iterable[str], registry: Registry, is_civilian: bool) -> DerivedCivilianStats:
    """Apply verified LOGISTICS hullmod effects to base hull stats.

    Deliberately does not attempt to compute a single combined
    "effective supplies_per_month" when more than one applied hullmod
    carries a civilian maintenance penalty: DATA_SCHEMA.md v0.3's own
    stacking rules say not to assume stacking behavior (ADDITIVE vs
    MULTIPLICATIVE vs ...) without evidence, and no such evidence has been
    verified for *combined* civilian-hullmod maintenance penalties here.
    Each applicable penalty is reported as a separate, unresolved note
    instead of a fabricated combined number.
    """
    increase_effects_by_hullmod: dict[str, list] = {}
    for effect in logistics_hullmod_effects(hull.source_mod):
        increase_effects_by_hullmod.setdefault(effect.hullmod_id, []).append(effect)
    reduction_effects_by_hullmod = {effect.hullmod_id: effect for effect in efficiency_hullmod_effects(hull.source_mod)}
    stats: dict[str, float | None] = {
        "cargo_capacity": hull.cargo_capacity,
        "fuel_capacity": hull.fuel_capacity,
        "crew_max": float(hull.crew_max) if hull.crew_max is not None else None,
        "max_burn": hull.max_burn,
        "supplies_per_month": hull.supplies_per_month,
        "crew_min": float(hull.crew_min) if hull.crew_min is not None else None,
    }
    applied: list[AppliedLogisticsEffect] = []
    applied_reductions: list[AppliedReductionEffect] = []
    unverified: list[str] = []
    maintenance_notes: list[str] = []
    for hullmod_id in hullmod_ids:
        increase_effect_list = increase_effects_by_hullmod.get(hullmod_id)
        reduction_effect = reduction_effects_by_hullmod.get(hullmod_id)
        if increase_effect_list:
            # A hullmod can affect more than one independent stat (e.g.
            # militarized_subsystems: flat max_burn plus a separate
            # percent crew_min increase) -- apply every matching entry,
            # not just the first, before deciding the id is unverified.
            any_applied = False
            for increase_effect in increase_effect_list:
                base = stats.get(increase_effect.stat)
                flat = increase_effect.flat_bonus_by_hull_size.get(hull.hull_size or "")
                if base is None or flat is None:
                    continue
                percent_component = base * increase_effect.percent_bonus if increase_effect.percent_bonus else 0.0
                gain = max(flat, percent_component)
                stats[increase_effect.stat] = base + gain
                hullmod = registry.hullmods.by_id.get(hullmod_id)
                op_cost = hullmod.op_cost_by_hull_size.get(hull.hull_size or "") if hullmod else None
                efficiency = (gain / op_cost) if op_cost else None
                applied.append(AppliedLogisticsEffect(hullmod_id, increase_effect.stat, base, gain, op_cost, efficiency))
                if is_civilian and increase_effect.civilian_maintenance_penalty_percent:
                    maintenance_notes.append(f"{hullmod_id}: +{increase_effect.civilian_maintenance_penalty_percent:.0%} maintenance supply use on civilian-grade hulls ({increase_effect.citation})")
                any_applied = True
            if not any_applied:
                unverified.append(hullmod_id)
        elif reduction_effect is not None:
            any_applied = False
            for stat in reduction_effect.stats:
                base = stats.get(stat)
                if base is None:
                    continue
                reduced_value = base * (1 - reduction_effect.percent_reduction)
                stats[stat] = reduced_value
                applied_reductions.append(AppliedReductionEffect(hullmod_id, stat, base, reduced_value, reduction_effect.percent_reduction))
                any_applied = True
            if not any_applied:
                unverified.append(hullmod_id)
        else:
            unverified.append(hullmod_id)
    return DerivedCivilianStats(
        cargo_capacity=stats["cargo_capacity"], fuel_capacity=stats["fuel_capacity"],
        crew_max=stats["crew_max"], max_burn=stats["max_burn"],
        supplies_per_month=stats["supplies_per_month"], crew_min=stats["crew_min"],
        applied_effects=tuple(applied), applied_reduction_effects=tuple(applied_reductions),
        unverified_hullmod_ids=tuple(unverified),
        civilian_maintenance_penalty_notes=tuple(maintenance_notes),
    )
