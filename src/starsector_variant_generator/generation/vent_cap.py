from __future__ import annotations

import math
from dataclasses import dataclass

from starsector_variant_generator.adapters import flux_unit_cost
from starsector_variant_generator.analysis.flux_stats import compute_derived_flux_stats
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Hull, Weapon
from starsector_variant_generator.core.registry import Registry

_FLUX_TARGET_KEY = {"SAFE": "beginner_flux_target", "BALANCED": "balanced_flux_target", "AGGRESSIVE": "aggressive_flux_target"}


@dataclass(frozen=True)
class VentCapAllocation:
    vents: int
    capacitors: int
    op_spent: int
    note: str


def _hullmod_adjusted_flux_stat(
    stat_name: str, base_value: float | None, effective_value: float | None,
    applied_effects: tuple, stacking_notes: tuple[str, ...],
) -> tuple[float | None, str | None]:
    """Resolve one FLUX stat under baseline_0.10's opt-in hullmod-adjusted
    vent/capacitor allocation, given `analysis/flux_stats.py::
    DerivedFluxStats` output for it.

    Deliberately an independent local copy of the same fallback discipline
    `scoring/candidate_score.py::_hullmod_adjusted_stat` already established
    for baseline_0.8's flux_sustainability scoring, rather than importing
    that (private) helper across the generation/scoring boundary -- the two
    modules are independent siblings in the pipeline (see CLAUDE.md's
    architecture diagram) and each already computes its own FLUX-adjusted
    view from the same `compute_derived_flux_stats` evidence.

    `effective_value` is None either because `base_value` itself is None
    (nothing to adjust) or because 2+ verified hullmods collided on this
    stat (`compute_derived_flux_stats` refuses to fabricate a combined
    number in that case -- see its own docstring). Both leave the raw base
    value in place; only the stacking case additionally explains why in the
    returned note: fall back to the raw value, never guess a number between
    the two verified ones.
    """
    if base_value is None:
        return base_value, None
    if effective_value is None:
        stacking_note = next((note for note in stacking_notes if note.startswith(stat_name)), None)
        if stacking_note is None:
            return base_value, None
        return base_value, f"{stat_name} hullmod stacking is unrepresentable, using unmodified base value: {stacking_note}"
    if effective_value == base_value:
        return base_value, None
    hullmod_ids = ", ".join(effect.hullmod_id for effect in applied_effects if effect.stat == stat_name)
    return effective_value, f"{stat_name} hullmod-adjusted for vent/capacitor allocation: {base_value:.2f} -> {effective_value:.2f} via {hullmod_ids}."


def allocate_vents_and_capacitors(
    hull: Hull,
    weapons: list[Weapon],
    remaining_op: int,
    flux_mode: str,
    heuristic_set: str = "baseline_0.2",
    hullmod_ids: tuple[str, ...] = (),
    registry: Registry | None = None,
) -> VentCapAllocation:
    """Deterministically spend remaining OP toward a flux-sustainability target, then capacitors.

    Step 3/4 of the formal spec's generation pipeline ("Add vents until
    target flux ratio or max vents reached. Add capacitors with remaining OP
    according to profile."). Only allocates anything when the hull's source
    mod has a documented flux-unit-cost table (adapters.flux_unit_cost) and
    hull/weapon flux data is complete -- an allocation built on undocumented
    or incomplete data could hand back a candidate that then fails Tier
    1.1's own legality check for reasons this function could have predicted
    and avoided. See docs/ROADMAP.md Tier 4.

    Capacitors receive whatever OP is left after vents, up to the documented
    maximum: nothing else in the generator currently consumes OP after
    weapon selection, and capacity is not yet a scored dimension (only
    dissipation_ratio is), so there is no profile-specific capacitor
    allocation rule to apply yet beyond "don't leave it unspent."

    `hullmod_ids`/`registry` are the candidate's own already-finalized
    selected hullmod list (see generation/candidate.py::_build_candidate --
    hullmod selection completes before this function is called) plus the
    Registry needed to look up each hullmod's OP cost. Both are optional and
    ignored unless `heuristic_set` carries baseline_0.10's opt-in
    `vent_hullmod_adjustment_enabled` flag, in which case the hull's
    flux_dissipation/shield_upkeep are sourced from
    analysis/flux_stats.py::compute_derived_flux_stats (verified
    fluxdistributor/safetyoverrides/stabilizedshieldemitter hullmod effects)
    instead of the hull's raw base stats -- see that heuristic's own
    core/heuristics.py metadata and HEURISTICS.md entry for the full
    rationale and the same-stat-stacking fallback.
    """
    cost = flux_unit_cost(hull.source_mod)
    if cost is None:
        return VentCapAllocation(0, 0, 0, f"No documented flux-unit cost for source mod {hull.source_mod!r}; no vents/capacitors allocated.")
    if remaining_op <= 0:
        return VentCapAllocation(0, 0, 0, "No OP remaining after weapons; no vents/capacitors allocated.")
    if hull.flux_dissipation is None or any(weapon.flux_per_second is None for weapon in weapons):
        return VentCapAllocation(0, 0, 0, "Incomplete flux data (hull dissipation or a mounted weapon's flux-per-second); no vents/capacitors allocated.")
    max_vents = cost.max_vents_by_hull_size.get(hull.hull_size or "")
    max_capacitors = cost.max_capacitors_by_hull_size.get(hull.hull_size or "")
    if max_vents is None or max_capacitors is None:
        return VentCapAllocation(0, 0, 0, f"No documented vent/capacitor maximum for hull size {hull.hull_size!r}; no allocation.")

    heuristics = get_heuristic_set(heuristic_set).values
    target = heuristics.get(_FLUX_TARGET_KEY.get(flux_mode, ""))

    flux_dissipation = hull.flux_dissipation
    shield_upkeep = hull.shield_upkeep or 0.0
    adjustment_notes: list[str] = []
    if "vent_hullmod_adjustment_enabled" in heuristics and registry is not None:
        # Opt-in only (baseline_0.10+); absent under baseline_0.9 and
        # earlier, so their vent/capacitor allocation is untouched -- the
        # hull's raw, unmodified stats are used exactly as before.
        derived = compute_derived_flux_stats(hull, hullmod_ids, registry)
        adjusted_dissipation, fd_note = _hullmod_adjusted_flux_stat(
            "flux_dissipation", hull.flux_dissipation, derived.effective_flux_dissipation,
            derived.applied_effects, derived.stacking_notes,
        )
        # `_hullmod_adjusted_flux_stat` only returns `None` when its
        # `base_value` argument (here `hull.flux_dissipation`) is itself
        # `None` -- already ruled out by the flux-completeness guard above.
        assert adjusted_dissipation is not None
        flux_dissipation = adjusted_dissipation
        if fd_note:
            adjustment_notes.append(fd_note)
        if hull.shield_upkeep is not None:
            adjusted_upkeep, su_note = _hullmod_adjusted_flux_stat(
                "shield_upkeep", hull.shield_upkeep, derived.effective_shield_upkeep,
                derived.applied_effects, derived.stacking_notes,
            )
            shield_upkeep = adjusted_upkeep if adjusted_upkeep is not None else shield_upkeep
            if su_note:
                adjustment_notes.append(su_note)

    weapon_flux_per_second = sum(weapon.flux_per_second or 0.0 for weapon in weapons)
    sustained_flux_load = weapon_flux_per_second + shield_upkeep

    vents = 0
    if target is not None and sustained_flux_load > 0:
        needed_dissipation = target * sustained_flux_load - (flux_dissipation if flux_dissipation is not None else hull.flux_dissipation)
        if needed_dissipation > 0:
            vents_needed = math.ceil(needed_dissipation / cost.dissipation_per_vent)
            vents = max(0, min(vents_needed, max_vents, remaining_op // cost.op_cost_per_unit))

    op_after_vents = remaining_op - vents * cost.op_cost_per_unit
    capacitors = max(0, min(max_capacitors, op_after_vents // cost.op_cost_per_unit))
    op_spent = (vents + capacitors) * cost.op_cost_per_unit
    note = f"Allocated {vents} vent(s) toward the {flux_mode} flux target and {capacitors} capacitor(s) with the remaining OP."
    if adjustment_notes:
        note = note + " " + " ".join(adjustment_notes)
    return VentCapAllocation(vents, capacitors, op_spent, note)
