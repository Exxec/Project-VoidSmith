"""Adapter-backed, static FLUX hullmod analysis.

Targets the same two typed `Hull` dataclass fields (`flux_dissipation`,
`shield_upkeep` -- see core/models.py) that scoring/candidate_score.py's
`_flux_component` already reads for the existing `flux_sustainability`
score. Unlike `combat_stats.py`/`mobility_stats.py`, these two fields are
already resolved onto every `Hull` at parse time -- including for a
skin-derived hull, which inherits them directly from its base hull in
`parsers/entities.py::hull_from_skin` -- so no raw-CSV-column lookup or
base-hull fallback is needed here.

Only documented, unconditional per-ship effects are evaluated. FLUX is the
first category where verified entries use more than one real operation
shape (flat additive, multiplicative factor, percent reduction -- see
adapters/vanilla/__init__.py's `HullmodFluxEffect` docstring), so this
module never assumes two effects on the same stat combine via a single
arithmetic rule: each verified hullmod's effect is always computed against
the stat's true, unmodified base value in isolation, and reported
individually. Whenever 2+ verified hullmods target the same stat (e.g.
`fluxdistributor` flat-adds and `safetyoverrides` multiplies
`flux_dissipation`), no combined value is fabricated -- the ambiguity is
recorded in `stacking_notes`, exactly like `DerivedDefenseStats`/
`DerivedMobilityStats` already do for their own same-stat collisions.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from starsector_variant_generator.adapters import flux_hullmod_effects
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull
from starsector_variant_generator.core.registry import Registry

_FLUX_STATS = ("flux_dissipation", "shield_upkeep")


@dataclass(frozen=True)
class AppliedFluxEffect:
    """One verified FLUX hullmod effect, applied to the stat's true base
    value in isolation -- never against a running total updated by another
    hullmod, so the order hullmod_ids are supplied in never changes the
    result (same discipline as AppliedDefenseEffect/AppliedMobilityEffect).

    Unlike those two (whose effects are all flat-by-size XOR additive-
    percent, so a bare `gain` field is unambiguous), FLUX_HULLMOD_EFFECTS
    mixes three real operation shapes. `operation` records which shape
    produced this entry so a caller never has to guess how `delta` was
    derived:
      - "flat_add": resulting_value_alone = base_value + a flat, per-hull-
        size bonus (fluxdistributor).
      - "multiply": resulting_value_alone = base_value * a documented
        factor (safetyoverrides: "increased by a factor of 2").
      - "percent_reduce": resulting_value_alone = base_value * (1 - a
        documented fraction) (stabilizedshieldemitter: "reduced by 50%").
    `delta` is always `resulting_value_alone - base_value` regardless of
    operation, so all three remain directly comparable.
    """

    hullmod_id: str
    stat: str
    base_value: float
    operation: str
    resulting_value_alone: float
    delta: float
    op_cost: int | None
    efficiency: float | None
    # ROADMAP.md Phase 29 (Evidence/Provenance Unification): always sourced
    # from a verified adapters.flux_hullmod_effects table entry -- AGENTS.md's
    # adapter-layer ladder tier 6, ADAPTER_MODELED. Always correct by
    # construction; a hullmod without a verified entry never produces one
    # of these records.
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class DerivedFluxStats:
    """A FLUX-category slice of derived per-ship state: a hull's base
    `flux_dissipation`/`shield_upkeep`, as modified by verified FLUX
    hullmods (adapters.flux_hullmod_effects).

    A hullmod without a verified entry contributes nothing here -- absence
    of verified data is never treated as absence of effect; it is reported
    in `unverified_hullmod_ids` instead. `effective_flux_dissipation`/
    `effective_shield_upkeep` are None whenever the base value itself is
    unknown (hull.flux_dissipation/shield_upkeep not parsed) OR whenever
    more than one verified hullmod targets that stat (see `stacking_notes`)
    -- in the latter case each contribution is still available individually
    in `applied_effects`.
    """

    flux_dissipation_base: float | None
    shield_upkeep_base: float | None
    effective_flux_dissipation: float | None
    effective_shield_upkeep: float | None
    applied_effects: tuple[AppliedFluxEffect, ...]
    unverified_hullmod_ids: tuple[str, ...]
    stacking_notes: tuple[str, ...]

    @property
    def applied_effect_hullmod_ids(self) -> tuple[str, ...]:
        """Unique hullmod ids with at least one applied effect, in first-seen order."""
        seen: dict[str, None] = {}
        for effect in self.applied_effects:
            seen.setdefault(effect.hullmod_id, None)
        return tuple(seen)


def compute_derived_flux_stats(hull: Hull, hullmod_ids: Iterable[str], registry: Registry) -> DerivedFluxStats:
    """Apply verified FLUX hullmod effects to a hull's base flux_dissipation and shield_upkeep.

    Deliberately does not compute a single combined effective value when
    more than one applied hullmod targets the same stat -- whether vanilla
    combines a flat additive bonus (fluxdistributor) with a multiplicative
    factor (safetyoverrides) by add-then-multiply, multiply-then-add, or
    something else entirely is not documented anywhere this project can
    verify, so guessing would violate Agent.md's "do not infer undocumented
    behavior" rule. Each contribution is reported individually in
    `applied_effects` instead, exactly like compute_derived_defense_stats/
    compute_derived_mobility_stats already do for their own collisions.
    """
    effects_by_hullmod: dict[str, list] = {}
    for effect in flux_hullmod_effects(hull.source_mod):
        effects_by_hullmod.setdefault(effect.hullmod_id, []).append(effect)

    base_values: dict[str, float | None] = {
        "flux_dissipation": hull.flux_dissipation,
        "shield_upkeep": hull.shield_upkeep,
    }
    applied_by_stat: dict[str, list[AppliedFluxEffect]] = {stat: [] for stat in _FLUX_STATS}
    unverified: list[str] = []

    for hullmod_id in hullmod_ids:
        effect_list = effects_by_hullmod.get(hullmod_id)
        if not effect_list:
            unverified.append(hullmod_id)
            continue
        any_applied = False
        for effect in effect_list:
            base = base_values.get(effect.stat)
            if base is None or (hull.hull_size or "") in effect.excluded_hull_sizes:
                continue
            if effect.flat_bonus_by_hull_size is not None:
                bonus = effect.flat_bonus_by_hull_size.get(hull.hull_size or "")
                if bonus is None:
                    continue
                operation = "flat_add"
                resulting_value_alone = base + bonus
            elif effect.multiplicative_factor is not None:
                operation = "multiply"
                resulting_value_alone = base * effect.multiplicative_factor
            elif effect.percent_reduction is not None:
                operation = "percent_reduce"
                resulting_value_alone = base * (1.0 - effect.percent_reduction)
            else:
                continue
            delta = resulting_value_alone - base
            registry_hullmod = registry.hullmods.by_id.get(hullmod_id)
            op_cost = registry_hullmod.op_cost_by_hull_size.get(hull.hull_size or "") if registry_hullmod else None
            efficiency = (delta / op_cost) if op_cost else None
            applied_by_stat[effect.stat].append(
                AppliedFluxEffect(hullmod_id, effect.stat, base, operation, resulting_value_alone, delta, op_cost, efficiency)
            )
            any_applied = True
        if not any_applied:
            unverified.append(hullmod_id)

    effective: dict[str, float | None] = {}
    stacking_notes: list[str] = []
    for stat, base in base_values.items():
        appliers = applied_by_stat[stat]
        if base is None:
            effective[stat] = None
        elif not appliers:
            effective[stat] = base
        elif len(appliers) == 1:
            effective[stat] = appliers[0].resulting_value_alone
        else:
            effective[stat] = None
            ids = ", ".join(effect.hullmod_id for effect in appliers)
            ops = ", ".join(sorted({effect.operation for effect in appliers}))
            stacking_notes.append(
                f"{stat}: {len(appliers)} verified hullmods apply ({ids}), using different operations ({ops}) -- "
                "combined stacking behavior across multiple hullmods on the same stat is not documented, so no "
                "combined effective value is computed; see applied_effects for each hullmod's individual "
                "contribution against the base value."
            )

    return DerivedFluxStats(
        flux_dissipation_base=base_values["flux_dissipation"], shield_upkeep_base=base_values["shield_upkeep"],
        effective_flux_dissipation=effective["flux_dissipation"], effective_shield_upkeep=effective["shield_upkeep"],
        applied_effects=tuple(effect for stat in _FLUX_STATS for effect in applied_by_stat[stat]),
        unverified_hullmod_ids=tuple(unverified),
        stacking_notes=tuple(stacking_notes),
    )
