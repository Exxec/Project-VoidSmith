"""Adapter-backed, static mobility hullmod analysis.

Only documented unconditional changes to normalized hull CSV mobility fields
are evaluated.  Effects sharing a stat are reported independently when their
combining rule has not been established; no combat simulation is implied.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from starsector_variant_generator.adapters import mobility_hullmod_effects
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.parsers.common import optional_float

_MOBILITY_COLUMNS = {
    "max_speed": "max speed",
    "acceleration": "acceleration",
    "deceleration": "deceleration",
    "max_turn_rate": "max turn rate",
    "turn_acceleration": "turn acceleration",
}


@dataclass(frozen=True)
class AppliedMobilityEffect:
    hullmod_id: str
    stat: str
    base_value: float
    gain: float
    op_cost: int | None
    efficiency: float | None
    # ROADMAP.md Phase 29 (Evidence/Provenance Unification): always sourced
    # from a verified adapters.mobility_hullmod_effects table entry --
    # AGENTS.md's adapter-layer ladder tier 6, ADAPTER_MODELED. Always
    # correct by construction; a hullmod without a verified entry never
    # produces one of these records.
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class DerivedMobilityStats:
    """Base/effective values plus every verified independent contribution.

    A value is ``None`` when its base source is unavailable or when multiple
    effects target it and their combination is not documented.  That is
    evidence absence, not a zero-value or a legality finding.
    """

    base_values: dict[str, float | None]
    effective_values: dict[str, float | None]
    applied_effects: tuple[AppliedMobilityEffect, ...]
    unverified_hullmod_ids: tuple[str, ...]
    stacking_notes: tuple[str, ...]

    @property
    def applied_effect_hullmod_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(effect.hullmod_id for effect in self.applied_effects))


def _base_mobility_stat(hull: Hull, registry: Registry, stat: str) -> float | None:
    value = optional_float(hull.raw.get(_MOBILITY_COLUMNS[stat]))
    if value is not None:
        return value
    base_hull_id = hull.raw.get("base_hull_id")
    if isinstance(base_hull_id, str) and (base_hull := registry.hulls.by_id.get(base_hull_id)) is not None:
        return optional_float(base_hull.raw.get(_MOBILITY_COLUMNS[stat]))
    return None


def compute_derived_mobility_stats(hull: Hull, hullmod_ids: Iterable[str], registry: Registry) -> DerivedMobilityStats:
    effects_by_hullmod: dict[str, list] = {}
    for effect in mobility_hullmod_effects(hull.source_mod):
        effects_by_hullmod.setdefault(effect.hullmod_id, []).append(effect)
    bases = {stat: _base_mobility_stat(hull, registry, stat) for stat in _MOBILITY_COLUMNS}
    applied_by_stat: dict[str, list[AppliedMobilityEffect]] = {stat: [] for stat in _MOBILITY_COLUMNS}
    unverified: list[str] = []
    for hullmod_id in hullmod_ids:
        effect_list = effects_by_hullmod.get(hullmod_id)
        if not effect_list:
            unverified.append(hullmod_id)
            continue
        applied_any = False
        for effect in effect_list:
            base = bases[effect.stat]
            if base is None:
                continue
            gain = (effect.flat_bonus_by_hull_size or {}).get(hull.hull_size or "") if effect.flat_bonus_by_hull_size is not None else base * (effect.percent_bonus or 0.0)
            if gain is None:
                continue
            hullmod = registry.hullmods.by_id.get(hullmod_id)
            op_cost = hullmod.op_cost_by_hull_size.get(hull.hull_size or "") if hullmod else None
            applied_by_stat[effect.stat].append(AppliedMobilityEffect(hullmod_id, effect.stat, base, gain, op_cost, gain / op_cost if op_cost else None))
            applied_any = True
        if not applied_any:
            unverified.append(hullmod_id)
    effective: dict[str, float | None] = {}
    notes: list[str] = []
    for stat, base in bases.items():
        effects = applied_by_stat[stat]
        if base is None:
            effective[stat] = None
        elif not effects:
            effective[stat] = base
        elif len(effects) == 1:
            effective[stat] = base + effects[0].gain
        else:
            effective[stat] = None
            notes.append(f"{stat}: {len(effects)} verified hullmods apply ({', '.join(effect.hullmod_id for effect in effects)}); combined stacking is not documented, so no effective value is computed.")
    return DerivedMobilityStats(bases, effective, tuple(effect for stat in _MOBILITY_COLUMNS for effect in applied_by_stat[stat]), tuple(unverified), tuple(notes))
