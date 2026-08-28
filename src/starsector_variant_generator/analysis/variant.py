from __future__ import annotations

from dataclasses import asdict, dataclass

from starsector_variant_generator.analysis.civilian import DerivedCivilianStats, compute_derived_civilian_stats
from starsector_variant_generator.analysis.classification import classify_civilian_role
from starsector_variant_generator.analysis.combat_stats import DerivedDefenseStats, compute_derived_defense_stats
from starsector_variant_generator.analysis.control_suitability import StaticControlSuitability, compute_static_control_suitability
from starsector_variant_generator.analysis.flux_stats import DerivedFluxStats, compute_derived_flux_stats
from starsector_variant_generator.analysis.mobility_stats import DerivedMobilityStats, compute_derived_mobility_stats
from starsector_variant_generator.analysis.weapon_range_stats import DerivedWeaponRangeStats, compute_derived_combat_stats
from starsector_variant_generator.analysis.derived_ship_state import DerivedShipState, derive_ship_state
from starsector_variant_generator.core.models import Faction, Variant
from starsector_variant_generator.core.overrides import EntityOverride, apply_role_tag_override
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.scoring.candidate_score import QualityAssessment, score_candidate
from starsector_variant_generator.validation.legality import LegalityAssessment, validate_variant


@dataclass(frozen=True)
class VariantAnalysis:
    variant_id: str
    legality: LegalityAssessment
    quality: QualityAssessment
    civilian_role_tags: tuple[str, ...]
    civilian_role_tags_overridden: bool
    civilian_stats: DerivedCivilianStats | None
    defense_stats: DerivedDefenseStats | None
    mobility_stats: DerivedMobilityStats | None
    flux_stats: DerivedFluxStats | None
    weapon_range_stats: DerivedWeaponRangeStats | None
    derived_ship_state: DerivedShipState | None
    # ROADMAP.md Phase 41: a static, structural piloting-demand signal set,
    # never a legality claim or a combat-outcome prediction -- see
    # analysis/control_suitability.py's own module docstring. Populated
    # whenever `hull` resolves, exactly like the other Hull-dependent slices
    # above; None only when `hull` itself doesn't resolve.
    static_control_suitability: StaticControlSuitability | None = None


def analyze_variant(
    variant: Variant,
    registry: Registry,
    profile_id: str = "LINE_BRAWLER",
    flux_mode: str = "BALANCED",
    faction: Faction | None = None,
    hull_role_override: EntityOverride | None = None,
    heuristic_set: str = "baseline_0.2",
) -> VariantAnalysis:
    legality = validate_variant(variant, registry)
    quality = score_candidate(variant, registry, profile_id, heuristic_set=heuristic_set, flux_mode=flux_mode, faction=faction)
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    civilian_role_tags: tuple[str, ...] = ()
    civilian_role_tags_overridden = False
    civilian_stats: DerivedCivilianStats | None = None
    defense_stats: DerivedDefenseStats | None = None
    mobility_stats: DerivedMobilityStats | None = None
    flux_stats: DerivedFluxStats | None = None
    weapon_range_stats: DerivedWeaponRangeStats | None = None
    derived_ship_state: DerivedShipState | None = None
    static_control_suitability: StaticControlSuitability | None = None
    if hull is not None:
        civilian = classify_civilian_role(hull)
        civilian_role_tags = apply_role_tag_override(civilian.role_tags, hull_role_override)
        civilian_role_tags_overridden = hull_role_override is not None
        is_civilian = "CIVILIAN" in civilian_role_tags
        civilian_stats = compute_derived_civilian_stats(hull, variant.hullmods, registry, is_civilian)
        defense_stats = compute_derived_defense_stats(hull, variant.hullmods, registry)
        mobility_stats = compute_derived_mobility_stats(hull, variant.hullmods, registry)
        flux_stats = compute_derived_flux_stats(hull, variant.hullmods, registry)
        weapon_range_stats = compute_derived_combat_stats(hull, variant, registry)
        derived_ship_state = derive_ship_state(variant, hull, registry)
        static_control_suitability = compute_static_control_suitability(variant, hull, registry)
    return VariantAnalysis(
        variant.id, legality, quality, civilian_role_tags, civilian_role_tags_overridden, civilian_stats,
        defense_stats, mobility_stats, flux_stats, weapon_range_stats, derived_ship_state, static_control_suitability,
    )
