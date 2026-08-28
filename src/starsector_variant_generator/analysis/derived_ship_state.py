"""Typed aggregate of currently verified derived per-ship state."""
from __future__ import annotations
from dataclasses import dataclass
from starsector_variant_generator.analysis.civilian import DerivedCivilianStats, compute_derived_civilian_stats
from starsector_variant_generator.analysis.combat_stats import DerivedDefenseStats, compute_derived_defense_stats
from starsector_variant_generator.analysis.mobility_stats import DerivedMobilityStats, compute_derived_mobility_stats
from starsector_variant_generator.analysis.classification import classify_civilian_role
from starsector_variant_generator.core.models import Hull, Variant
from starsector_variant_generator.core.registry import Registry

@dataclass(frozen=True)
class DerivedShipState:
    hull_id: str
    selected_variant_id: str
    civilian: DerivedCivilianStats
    defense: DerivedDefenseStats
    mobility: DerivedMobilityStats
    unapplied_unknown_hullmod_ids: tuple[str, ...]
    confidence_summary: float

def derive_ship_state(variant: Variant, hull: Hull, registry: Registry) -> DerivedShipState:
    civilian = compute_derived_civilian_stats(hull, variant.hullmods, registry, classify_civilian_role(hull).is_civilian)
    defense = compute_derived_defense_stats(hull, variant.hullmods, registry)
    mobility = compute_derived_mobility_stats(hull, variant.hullmods, registry)
    known = set(civilian.applied_effect_hullmod_ids) | set(defense.applied_effect_hullmod_ids) | set(mobility.applied_effect_hullmod_ids)
    unknown = tuple(hullmod_id for hullmod_id in variant.hullmods if hullmod_id not in known)
    # Each verified slice preserves availability internally; this summary is
    # only an evidence-completeness signal, never a legality or score input.
    confidence = round(len(known) / len(variant.hullmods), 3) if variant.hullmods else 1.0
    return DerivedShipState(hull.id, variant.id, civilian, defense, mobility, unknown, confidence)
