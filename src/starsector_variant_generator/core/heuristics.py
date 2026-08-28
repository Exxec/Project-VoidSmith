from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class HeuristicSet:
    """Versioned quality values only; legality code must not depend on this type."""

    identifier: str
    values: Mapping[str, float]
    metadata: Mapping[str, "HeuristicMetadata"]


@dataclass(frozen=True)
class HeuristicMetadata:
    rationale: str
    units: str
    affected_profiles_or_modes: tuple[str, ...]
    kind: str


BASELINE_0_1 = HeuristicSet(
    identifier="baseline_0.1",
    values=MappingProxyType({
        "range_mismatch_minor": 100.0,
        "range_mismatch_moderate": 250.0,
        "range_mismatch_severe": 400.0,
        "beginner_flux_target": 0.90,
        "balanced_flux_target": 0.75,
        "aggressive_flux_target": 0.55,
        "artillery_range_weight": 1.50,
        "artillery_min_range": 900.0,
        "brawler_max_range": 700.0,
    }),
    metadata=MappingProxyType({
        "range_mismatch_minor": HeuristicMetadata("Baseline tolerance before a range-coherence penalty.", "game range units", ("all scored profiles",), "threshold"),
        "range_mismatch_moderate": HeuristicMetadata("Moderate range-spread penalty boundary.", "game range units", ("all scored profiles",), "threshold"),
        "range_mismatch_severe": HeuristicMetadata("Severe range-spread penalty boundary.", "game range units", ("all scored profiles",), "threshold"),
        "beginner_flux_target": HeuristicMetadata("Conservative future flux target for Beginner presentation.", "ratio", ("BEGINNER",), "target"),
        "balanced_flux_target": HeuristicMetadata("Future balanced-mode flux target.", "ratio", ("GUIDED",), "target"),
        "aggressive_flux_target": HeuristicMetadata("Future aggressive-mode flux target.", "ratio", ("ADVANCED",), "target"),
        "artillery_range_weight": HeuristicMetadata("Relative quality emphasis for artillery range preferences.", "multiplier", ("LINE_ARTILLERY",), "score weight"),
        "artillery_min_range": HeuristicMetadata("Minimum range for the current artillery role-match heuristic.", "game range units", ("LINE_ARTILLERY",), "threshold"),
        "brawler_max_range": HeuristicMetadata("Maximum range for the current brawler/strike role-match heuristic.", "game range units", ("LINE_BRAWLER", "FAST_STRIKE"), "threshold"),
    }),
)


BASELINE_0_2 = HeuristicSet(
    identifier="baseline_0.2",
    values=MappingProxyType({
        "range_mismatch_minor": 100.0,
        "range_mismatch_moderate": 250.0,
        "range_mismatch_severe": 400.0,
        "beginner_flux_target": 0.90,
        "balanced_flux_target": 0.75,
        "aggressive_flux_target": 0.55,
        "artillery_range_weight": 1.50,
        "artillery_min_range": 900.0,
        "brawler_max_range": 700.0,
        "weight_range_coherence": 0.30,
        "weight_op_efficiency": 0.15,
        "weight_role_match": 0.25,
        "weight_flux_sustainability": 0.20,
        "weight_faction_doctrine": 0.10,
        "weight_civilian_efficiency": 0.15,
        "civilian_efficiency_reference": 6.0,
        "weight_survivability": 0.15,
        "survivability_reference": 100.0,
        "doctrine_range_tolerance_fraction": 0.25,
        "doctrine_range_weight": 0.5,
        "doctrine_hullmod_overlap_weight": 0.5,
        "gap_strong_threshold": 0.70,
        "gap_adequate_threshold": 0.40,
        "gap_weak_threshold": 0.15,
        "gap_recommendation_count": 3.0,
        "refit_cost_weapon_change": 1.0,
        "refit_cost_hullmod_change": 1.5,
        "refit_cost_fighter_change": 1.0,
        "refit_cost_vent_cap_change": 0.25,
        "refit_max_changes": 20.0,
        "refit_min_quality_gain": 0.5,
        "affinity_preference_native": 1.00,
        "affinity_preference_approved": 0.90,
        "affinity_preference_common": 0.75,
        "affinity_preference_unaligned": 0.70,
        "affinity_preference_foreign": 0.40,
        "substitution_weight_role_match": 1.50,
        "substitution_weight_range_match": 1.20,
        "substitution_weight_flux_match": 1.20,
        "substitution_weight_damage_behavior_match": 1.20,
        "substitution_weight_op_efficiency": 0.90,
        "substitution_weight_affinity": 0.75,
    }),
    metadata=MappingProxyType({
        "range_mismatch_minor": HeuristicMetadata("Baseline tolerance before a range-coherence penalty.", "game range units", ("all scored profiles",), "threshold"),
        "range_mismatch_moderate": HeuristicMetadata("Moderate range-spread penalty boundary.", "game range units", ("all scored profiles",), "threshold"),
        "range_mismatch_severe": HeuristicMetadata("Severe range-spread penalty boundary.", "game range units", ("all scored profiles",), "threshold"),
        "beginner_flux_target": HeuristicMetadata("Minimum dissipation_ratio for a full flux_sustainability score under --flux-mode SAFE. Consumed by scoring as of baseline_0.2; unused (documented-only) under baseline_0.1.", "ratio", ("BEGINNER",), "target"),
        "balanced_flux_target": HeuristicMetadata("Minimum dissipation_ratio for a full flux_sustainability score under --flux-mode BALANCED. Consumed by scoring as of baseline_0.2; unused (documented-only) under baseline_0.1.", "ratio", ("GUIDED",), "target"),
        "aggressive_flux_target": HeuristicMetadata("Minimum dissipation_ratio for a full flux_sustainability score under --flux-mode AGGRESSIVE. Consumed by scoring as of baseline_0.2; unused (documented-only) under baseline_0.1.", "ratio", ("ADVANCED",), "target"),
        "artillery_range_weight": HeuristicMetadata("Relative quality emphasis for artillery range preferences.", "multiplier", ("LINE_ARTILLERY",), "score weight"),
        "artillery_min_range": HeuristicMetadata("Minimum range for the current artillery role-match heuristic.", "game range units", ("LINE_ARTILLERY",), "threshold"),
        "brawler_max_range": HeuristicMetadata("Maximum range for the current brawler/strike role-match heuristic.", "game range units", ("LINE_BRAWLER", "FAST_STRIKE"), "threshold"),
        "weight_range_coherence": HeuristicMetadata("Final-score weight for the range_coherence component. Replaces the baseline_0.1 hardcoded 0.45.", "relative weight", ("all scored profiles",), "score weight"),
        "weight_op_efficiency": HeuristicMetadata("Final-score weight for the op_efficiency component. Replaces the baseline_0.1 hardcoded 0.20.", "relative weight", ("all scored profiles",), "score weight"),
        "weight_role_match": HeuristicMetadata("Final-score weight for the role_match component. Replaces the baseline_0.1 hardcoded 0.35.", "relative weight", ("all scored profiles",), "score weight"),
        "weight_flux_sustainability": HeuristicMetadata("Final-score weight for the flux_sustainability component (new in baseline_0.2).", "relative weight", ("all scored profiles",), "score weight"),
        "weight_faction_doctrine": HeuristicMetadata("Final-score weight for the faction_doctrine_match component (new in baseline_0.2); only applied when a resolved faction is supplied.", "relative weight", ("all scored profiles",), "score weight"),
        "weight_civilian_efficiency": HeuristicMetadata("Final-score weight for the civilian_efficiency component; only applied when the variant has at least one verified LOGISTICS hullmod effect with a computable OP-efficiency ratio (analysis/civilian.py::AppliedLogisticsEffect.efficiency). Silently absent for variants with no logistics hullmods -- not a penalty, just not applicable.", "relative weight", ("all scored profiles",), "score weight"),
        "civilian_efficiency_reference": HeuristicMetadata("A gain-per-OP-spent value treated as a full civilian_efficiency score of 100. First-pass value grounded in real efficiency figures observed this session (e.g. auxiliary_fuel_tanks on phantom, expanded_cargo_holds on a frigate test case both computed to 6.0), not a documented game constant -- there is no such thing to verify this against. Pending a benchmark suite, same status as doctrine_match's weights.", "gain per OP", ("all scored profiles",), "reference value"),
        "weight_survivability": HeuristicMetadata("Final-score weight for the survivability component; only applied when the variant has at least one verified DEFENSE hullmod effect with a computable OP-efficiency ratio (analysis/combat_stats.py::AppliedDefenseEffect.efficiency). Silently absent for variants with none of heavyarmor/armoredweapons/reinforcedhull/blast_doors equipped -- not a penalty, just not applicable.", "relative weight", ("all scored profiles",), "score weight"),
        "survivability_reference": HeuristicMetadata("A gain-per-OP-spent value (armor_rating or hull_hp gain per OP) treated as a full survivability score of 100. First-pass value grounded in real efficiency figures computed this session against the live install: applying all 4 verified DEFENSE hullmods (heavyarmor, armoredweapons, reinforcedhull, blast_doors) to 6 real hulls -- lasher 64.06, wolf 54.69, hammerhead 88.33, enforcer 106.25, dominator 160.83, onslaught 122.71 -- and averaging those 6 real per-hull means gives 99.48, rounded to 100.0. Not a documented game constant -- there is no such thing to verify this against. Individual hullmods vary widely in efficiency (heavyarmor alone converges near 20 armor/OP on destroyer/cruiser hulls; reinforcedhull alone is far higher, 120-373 HP/OP, and will often saturate the score at the 100 cap on its own) -- this reference reflects a representative multi-hullmod combined build, not any single hullmod's efficiency. Pending a benchmark suite, same status as civilian_efficiency_reference.", "gain per OP", ("all scored profiles",), "reference value"),
        "doctrine_range_tolerance_fraction": HeuristicMetadata("Fraction of a faction's observed average weapon range treated as full doctrine match before the range component tapers.", "fraction", ("all scored profiles",), "threshold"),
        "doctrine_range_weight": HeuristicMetadata("Weight of the range-alignment term inside doctrine_match.", "relative weight", ("all scored profiles",), "score weight"),
        "doctrine_hullmod_overlap_weight": HeuristicMetadata("Weight of the repeated-hullmod-overlap term inside doctrine_match.", "relative weight", ("all scored profiles",), "score weight"),
        "gap_strong_threshold": HeuristicMetadata("Minimum classify_hull role_compatibility score classified STRONG (not a gap). First-pass value, not tuned against a benchmark. See GAP_RECOMMENDATION_ENGINE.md section 4.", "ratio", ("gap recommendation",), "threshold"),
        "gap_adequate_threshold": HeuristicMetadata("Minimum score classified ADEQUATE (not a gap); below this and above gap_weak_threshold is WEAK.", "ratio", ("gap recommendation",), "threshold"),
        "gap_weak_threshold": HeuristicMetadata("Minimum score classified WEAK; below this is GAP. Both WEAK and GAP are returned as CapabilityGap records.", "ratio", ("gap recommendation",), "threshold"),
        "gap_recommendation_count": HeuristicMetadata("Maximum native recommendations returned per capability gap.", "count", ("gap recommendation",), "cap"),
        "refit_cost_weapon_change": HeuristicMetadata("Change-cost weight for one weapon add/replace/remove. HULLMODS_CIVILIAN_AND_REFIT.md section 14's suggested default.", "relative cost", ("refit",), "weight"),
        "refit_cost_hullmod_change": HeuristicMetadata("Change-cost weight for one hullmod add/remove. HULLMODS_CIVILIAN_AND_REFIT.md section 14's suggested default.", "relative cost", ("refit",), "weight"),
        "refit_cost_fighter_change": HeuristicMetadata("Change-cost weight for one fighter wing add/replace/remove. HULLMODS_CIVILIAN_AND_REFIT.md section 14's suggested default.", "relative cost", ("refit",), "weight"),
        "refit_cost_vent_cap_change": HeuristicMetadata("Change-cost weight for one vent/capacitor count adjustment. HULLMODS_CIVILIAN_AND_REFIT.md section 14's suggested default.", "relative cost", ("refit",), "weight"),
        "refit_max_changes": HeuristicMetadata("Maximum number of individual changes FIX_LEGALITY will apply before giving up and recommending a full rebuild instead (HULLMODS_CIVILIAN_AND_REFIT.md section 17's 'No Silent Rebuild' rule). Also caps the quality-improvement modes' greedy search (generation/refit.py::improve_quality).", "count", ("refit",), "cap"),
        "refit_min_quality_gain": HeuristicMetadata("Minimum score-point improvement (on the quality mode's own 0-100 metric) a single candidate change must produce to be worth its change_cost. Below this, a change is treated as noise rather than genuine improvement, preventing the greedy quality-improvement search from thrashing on negligible gains.", "score points", ("refit quality modes",), "threshold"),
        "affinity_preference_native": HeuristicMetadata("Quality-ranking preference value for NATIVE-affinity equipment, from HEURISTICS.md section 12's suggested FACTION_PLUS preference table verbatim. Never consulted by legality.", "preference score", ("adaptive substitution",), "score weight"),
        "affinity_preference_approved": HeuristicMetadata("Preference value for APPROVED-affinity equipment. Not currently producible by classify_equipment_affinity (needs knowledge-pack evidence, Phase 7) -- kept for when it is.", "preference score", ("adaptive substitution",), "score weight"),
        "affinity_preference_common": HeuristicMetadata("Preference value for COMMON-affinity equipment.", "preference score", ("adaptive substitution",), "score weight"),
        "affinity_preference_unaligned": HeuristicMetadata("Preference value for UNALIGNED-affinity equipment.", "preference score", ("adaptive substitution",), "score weight"),
        "affinity_preference_foreign": HeuristicMetadata("Preference value for FOREIGN-affinity equipment.", "preference score", ("adaptive substitution",), "score weight"),
        "substitution_weight_role_match": HeuristicMetadata("Weighted-average weight for the role_match component of adaptive substitution scoring, from HEURISTICS.md section 13's suggested starting weights verbatim.", "relative weight", ("adaptive substitution",), "score weight"),
        "substitution_weight_range_match": HeuristicMetadata("Weight for the range_match component.", "relative weight", ("adaptive substitution",), "score weight"),
        "substitution_weight_flux_match": HeuristicMetadata("Weight for the flux_match component.", "relative weight", ("adaptive substitution",), "score weight"),
        "substitution_weight_damage_behavior_match": HeuristicMetadata("Weight for the damage_behavior_match component.", "relative weight", ("adaptive substitution",), "score weight"),
        "substitution_weight_op_efficiency": HeuristicMetadata("Weight for the OP_efficiency component.", "relative weight", ("adaptive substitution",), "score weight"),
        "substitution_weight_affinity": HeuristicMetadata("Weight for the affinity component.", "relative weight", ("adaptive substitution",), "score weight"),
    }),
)


BASELINE_0_3 = HeuristicSet(
    identifier="baseline_0.3",
    values=MappingProxyType({
        **BASELINE_0_2.values,
        "recommendation_diversity_similarity_penalty": 0.15,
        "recommendation_diversity_material_score_tolerance": 0.10,
        "recommendation_diversity_role_difference_weight": 0.55,
        "recommendation_diversity_archetype_difference_weight": 0.45,
        "recommendation_diversity_min_archetype_compatibility": 0.20,
        "archetype_variant_usage_evidence_weight": 0.15,
        "archetype_unknown_feature_confidence_penalty": 0.05,
    }),
    metadata=MappingProxyType({
        **BASELINE_0_2.metadata,
        "recommendation_diversity_similarity_penalty": HeuristicMetadata("Penalty applied only among score-competitive candidates with similar inferred mechanical archetypes.", "score fraction", ("gap recommendation",), "score weight"),
        "recommendation_diversity_material_score_tolerance": HeuristicMetadata("Maximum score loss tolerated when selecting a mechanically distinct alternative; prevents diversity from promoting materially worse candidates.", "score fraction", ("gap recommendation",), "threshold"),
        "recommendation_diversity_role_difference_weight": HeuristicMetadata("Relative diversity distance contribution from the requested functional role.", "relative weight", ("gap recommendation",), "score weight"),
        "recommendation_diversity_archetype_difference_weight": HeuristicMetadata("Relative diversity distance contribution from inferred archetype profiles.", "relative weight", ("gap recommendation",), "score weight"),
        "recommendation_diversity_min_archetype_compatibility": HeuristicMetadata("Minimum inferred archetype score retained when comparing mechanical profiles.", "compatibility", ("gap recommendation",), "threshold"),
        "archetype_variant_usage_evidence_weight": HeuristicMetadata("Bounded influence of existing variants as statistical archetype evidence; structural evidence remains required.", "relative weight", ("mechanical archetypes",), "score weight"),
        "archetype_unknown_feature_confidence_penalty": HeuristicMetadata("Confidence reduction per unavailable archetype input; unknown data never becomes favorable evidence.", "confidence fraction", ("mechanical archetypes",), "penalty"),
    }),
)

BASELINE_0_4 = HeuristicSet(
    identifier="baseline_0.4",
    values=MappingProxyType({
        **BASELINE_0_3.values,
        "build_archetype_viable_min_compatibility": 0.35,
        "build_archetype_experimental_min_compatibility": 0.20,
        "build_archetype_unknown_feature_confidence_penalty": 0.05,
        "variant_diversity_near_duplicate_threshold": 0.85,
        "knowledge_build_archetype_preference_weight": 0.10,
    }),
    metadata=MappingProxyType({
        **BASELINE_0_3.metadata,
        "build_archetype_viable_min_compatibility": HeuristicMetadata("Minimum structural compatibility for normal independent build generation.", "compatibility", ("build archetypes",), "threshold"),
        "build_archetype_experimental_min_compatibility": HeuristicMetadata("Minimum compatibility retained as an explicitly Experimental build path.", "compatibility", ("build archetypes",), "threshold"),
        "build_archetype_unknown_feature_confidence_penalty": HeuristicMetadata("Confidence reduction per unavailable build-archetype input; missing data never improves a build path.", "confidence fraction", ("build archetypes",), "penalty"),
        "variant_diversity_near_duplicate_threshold": HeuristicMetadata("Similarity at or above which two same-hull generated variants collapse to one representative.", "similarity", ("candidate generation",), "threshold"),
        "knowledge_build_archetype_preference_weight": HeuristicMetadata("Maximum advisory score adjustment from a current knowledge-pack build preference; cannot create an inferred build path.", "score fraction", ("build archetypes", "gap recommendation"), "score weight"),
    }),
)

BASELINE_0_5 = HeuristicSet(
    identifier="baseline_0.5",
    values=MappingProxyType({
        **BASELINE_0_4.values,
        "weight_pd_coverage": 0.10,
        "weight_missile_pressure": 0.10,
    }),
    metadata=MappingProxyType({
        **BASELINE_0_4.metadata,
        "weight_pd_coverage": HeuristicMetadata("Final-score weight for directly classified PD weapon coverage; applicable only to PD_ESCORT.", "relative weight", ("PD_ESCORT",), "score weight"),
        "weight_missile_pressure": HeuristicMetadata("Final-score weight for documented missile-mount weapon coverage; applicable only to MISSILE_SUPPORT.", "relative weight", ("MISSILE_SUPPORT",), "score weight"),
    }),
)

BASELINE_0_6 = HeuristicSet(
    identifier="baseline_0.6",
    values=MappingProxyType({**BASELINE_0_5.values, "retrofit_disruption_reference_cost": 8.0, "retrofit_disruption_penalty_weight": 0.20}),
    metadata=MappingProxyType({**BASELINE_0_5.metadata,
        "retrofit_disruption_reference_cost": HeuristicMetadata("Change-cost total treated as maximum normalized retrofit disruption.", "change cost", ("retrofit recommendations",), "reference value"),
        "retrofit_disruption_penalty_weight": HeuristicMetadata("Maximum quality-only retrofit recommendation-score penalty from normalized disruption.", "score fraction", ("retrofit recommendations",), "score weight"),
    }),
)

BASELINE_0_7 = HeuristicSet(
    identifier="baseline_0.7",
    values=MappingProxyType({**BASELINE_0_6.values, "knowledge_progression_preference_weight": 0.05}),
    metadata=MappingProxyType({**BASELINE_0_6.metadata,
        "knowledge_progression_preference_weight": HeuristicMetadata(
            "Maximum freshness-adjusted advisory ranking adjustment for a hull explicitly listed in the user-selected progression tier of a resolved Faction Knowledge Pack. It cannot admit a hull/build path, alter capability evidence, or affect legality.",
            "score fraction", ("gap recommendation", "faction knowledge packs"), "score weight",
        ),
    }),
)


BASELINE_0_8 = HeuristicSet(
    identifier="baseline_0.8",
    values=MappingProxyType({**BASELINE_0_7.values, "flux_hullmod_adjustment_enabled": 1.0}),
    metadata=MappingProxyType({**BASELINE_0_7.metadata,
        "flux_hullmod_adjustment_enabled": HeuristicMetadata(
            "Gate flag (new in baseline_0.8, not on by default -- available but opt-in): when present, "
            "scoring/candidate_score.py's flux_sustainability component sources a candidate's "
            "flux_dissipation/shield_upkeep from analysis/flux_stats.py::compute_derived_flux_stats "
            "(verified fluxdistributor/safetyoverrides/stabilizedshieldemitter hullmod effects) instead "
            "of the hull's raw, unmodified base stats. When 2+ verified hullmods collide on the same "
            "stat, compute_derived_flux_stats deliberately reports no combined effective value (the "
            "combination rule is undocumented); scoring falls back to the stat's raw base value in that "
            "case and records the ambiguity in the explanation rather than fabricating a stacked number. "
            "Absent under baseline_0.7 and every earlier registry entry, so flux_sustainability there is "
            "completely unaffected -- byte-for-byte reproducible.",
            "flag (1.0 = enabled)", ("all scored profiles",), "flag",
        ),
    }),
)


BASELINE_0_9 = HeuristicSet(
    identifier="baseline_0.9",
    values=MappingProxyType({**BASELINE_0_8.values, "combat_hullmod_adjustment_enabled": 1.0}),
    metadata=MappingProxyType({**BASELINE_0_8.metadata,
        "combat_hullmod_adjustment_enabled": HeuristicMetadata(
            "Gate flag (new in baseline_0.9, not on by default -- available but opt-in): when present, "
            "scoring/candidate_score.py's range_coherence and role_match components source each equipped "
            "BALLISTIC/ENERGY weapon's range from analysis/weapon_range_stats.py::compute_derived_combat_stats "
            "(verified targetingunit/dedicated_targeting_core hullmod effects) instead of that weapon's raw, "
            "unmodified base range. When 2+ verified hullmods collide on the same mount, "
            "compute_derived_combat_stats deliberately reports no combined effective value (the combination "
            "rule is undocumented -- and the two hullmods are mutually illegal in vanilla in the first place); "
            "scoring falls back to that weapon's raw base range in that case and records the ambiguity in the "
            "explanation rather than fabricating a stacked number. Absent under baseline_0.8 and every earlier "
            "registry entry, so range_coherence and role_match there are completely unaffected -- byte-for-byte "
            "reproducible.",
            "flag (1.0 = enabled)", ("all scored profiles",), "flag",
        ),
    }),
)


BASELINE_0_10 = HeuristicSet(
    identifier="baseline_0.10",
    values=MappingProxyType({**BASELINE_0_9.values, "vent_hullmod_adjustment_enabled": 1.0}),
    metadata=MappingProxyType({**BASELINE_0_9.metadata,
        "vent_hullmod_adjustment_enabled": HeuristicMetadata(
            "Gate flag (new in baseline_0.10, not on by default -- available but opt-in): when present, "
            "generation/vent_cap.py's allocate_vents_and_capacitors sources a candidate's "
            "flux_dissipation/shield_upkeep from analysis/flux_stats.py::compute_derived_flux_stats "
            "(verified fluxdistributor/safetyoverrides/stabilizedshieldemitter hullmod effects, evaluated "
            "against the candidate's own selected hullmod list) instead of the hull's raw, unmodified base "
            "stats, so a candidate that installs one of those hullmods computes its real, hullmod-adjusted "
            "vent/capacitor need -- e.g. fewer vents toward the same flux-sustainability target when "
            "fluxdistributor is installed. When 2+ verified hullmods collide on the same stat, "
            "compute_derived_flux_stats deliberately reports no combined effective value (the combination "
            "rule is undocumented); allocation falls back to the stat's raw base value in that case and "
            "records the ambiguity in the allocation note rather than fabricating a stacked number -- the "
            "same fallback discipline baseline_0.8 already established for scoring's own flux_sustainability "
            "component. Absent under baseline_0.9 and every earlier registry entry, so their vent/capacitor "
            "allocation is completely unaffected -- byte-for-byte reproducible.",
            "flag (1.0 = enabled)", ("candidate generation",), "flag",
        ),
    }),
)


BASELINE_0_11 = HeuristicSet(
    identifier="baseline_0.11",
    values=MappingProxyType({
        **BASELINE_0_10.values,
        "scenario_fit_min_signal": 0.30,
        "scenario_confidence_cap": 0.75,
        "scenario_recommendation_count": 3.0,
    }),
    metadata=MappingProxyType({**BASELINE_0_10.metadata,
        "scenario_fit_min_signal": HeuristicMetadata(
            "Minimum heuristic scenario_fit_score (analysis/gap_recommendation.py::recommend_scenario_solutions, "
            "ROADMAP.md Phase 31 / Charter Priority 9) required before a Hull + BuildArchetype candidate already "
            "ranked by the Native/Retrofit/Acquisition legs is surfaced as an INFERRED_SCENARIO_OPTION for a "
            "RAIDING/DEFENSE/ESCORT/PATROL scenario. First-pass value, not tuned against a benchmark -- same "
            "honest status as gap_weak_threshold. Read via `.get()` with this exact fallback, so it also applies "
            "under every earlier heuristic_set that predates this key.",
            "ratio", ("gap recommendation",), "threshold",
        ),
        "scenario_confidence_cap": HeuristicMetadata(
            "Hard ceiling on a ScenarioRecommendation's reported confidence, always applied on top of the "
            "underlying leg's own confidence (min(), never additive). A heuristic scenario-fit overlay must "
            "never present itself as fully certain the way a direct evidence-based Native/Retrofit/Acquisition "
            "recommendation can (AGENTS.md's 'High score with low confidence must remain visibly low "
            "confidence'). Read via `.get()` with this exact fallback.",
            "ratio", ("gap recommendation",), "cap",
        ),
        "scenario_recommendation_count": HeuristicMetadata(
            "Maximum INFERRED_SCENARIO_OPTION recommendations returned per (role, scenario) pair -- a dedicated "
            "counterpart to gap_recommendation_count kept separate so the two shortlist sizes can be tuned "
            "independently. Read via `.get()`, falling back to gap_recommendation_count itself under an earlier "
            "heuristic_set that predates this key.",
            "count", ("gap recommendation",), "cap",
        ),
    }),
)

BASELINE_0_12 = HeuristicSet(
    identifier="baseline_0.12",
    values=MappingProxyType({
        **BASELINE_0_11.values,
        "fleet_support_need_threshold": 0.35,
        "fleet_support_min_signal": 0.15,
        "fleet_support_recommendation_count": 3.0,
        "fleet_support_complement_weight": 0.65,
        "fleet_support_cohesion_weight": 0.35,
        "fleet_support_friction_weight": 0.15,
    }),
    metadata=MappingProxyType({**BASELINE_0_11.metadata,
        "fleet_support_need_threshold": HeuristicMetadata("Minimum uncovered per-ship capability evidence that Fleet Support Advisor exposes as an advisory support need. This is not a fleet outcome or legality threshold.", "ratio", ("fleet support advisor",), "threshold"),
        "fleet_support_min_signal": HeuristicMetadata("Minimum weighted need coverage a candidate addition must provide before Fleet Support Advisor ranks it. Prevents padded recommendations.", "ratio", ("fleet support advisor",), "threshold"),
        "fleet_support_recommendation_count": HeuristicMetadata("Default maximum number of individually ranked additions Fleet Support Advisor presents. It never implies quantities.", "count", ("fleet support advisor",), "cap"),
        "fleet_support_complement_weight": HeuristicMetadata("Relative advisory weight for filling a selected fleet's uncovered evidence.", "relative weight", ("fleet support advisor",), "score weight"),
        "fleet_support_cohesion_weight": HeuristicMetadata("Relative advisory weight for matching selected ships' observable doctrine posture.", "relative weight", ("fleet support advisor",), "score weight"),
        "fleet_support_friction_weight": HeuristicMetadata("Maximum advisory deduction for static speed/position/tempo mismatch. Unsupported campaign friction remains unscored.", "relative weight", ("fleet support advisor",), "score weight"),
    }),
)

BASELINE_0_13 = HeuristicSet(
    identifier="baseline_0.13",
    values=MappingProxyType({**BASELINE_0_12.values, "fleet_support_diversity_enabled": 1.0}),
    metadata=MappingProxyType({**BASELINE_0_12.metadata,
        "fleet_support_diversity_enabled": HeuristicMetadata("Enables score-bounded mechanical-family diversity for Fleet Support Advisor shortlists. It only considers candidates already admitted by structural/access/support-signal gates and never affects legality.", "flag (1.0 = enabled)", ("fleet support advisor",), "flag"),
    }),
)

BASELINE_0_14 = HeuristicSet(
    identifier="baseline_0.14",
    values=MappingProxyType({
        **BASELINE_0_13.values,
        "fleet_support_composition_synergy_weight": 0.20,
        "fleet_support_access_affinity_weight": 0.05,
    }),
    metadata=MappingProxyType({
        **BASELINE_0_13.metadata,
        "fleet_support_composition_synergy_weight": HeuristicMetadata("Relative advisory reward for available direct/static composition-preservation matches (phase hint, normalized sensor profile, base burn, and mobility character). It is separate from doctrine cohesion, does not create support needs, and never affects legality.", "relative weight", ("fleet support advisor",), "score weight"),
        "fleet_support_access_affinity_weight": HeuristicMetadata("Small advisory preference for the existing normalized access-affinity classification after a candidate has already passed access policy. It never changes eligibility or legality.", "relative weight", ("fleet support advisor",), "score weight"),
    }),
)


REGISTRY = MappingProxyType({BASELINE_0_1.identifier: BASELINE_0_1, BASELINE_0_2.identifier: BASELINE_0_2, BASELINE_0_3.identifier: BASELINE_0_3, BASELINE_0_4.identifier: BASELINE_0_4, BASELINE_0_5.identifier: BASELINE_0_5, BASELINE_0_6.identifier: BASELINE_0_6, BASELINE_0_7.identifier: BASELINE_0_7, BASELINE_0_8.identifier: BASELINE_0_8, BASELINE_0_9.identifier: BASELINE_0_9, BASELINE_0_10.identifier: BASELINE_0_10, BASELINE_0_11.identifier: BASELINE_0_11, BASELINE_0_12.identifier: BASELINE_0_12, BASELINE_0_13.identifier: BASELINE_0_13, BASELINE_0_14.identifier: BASELINE_0_14})


def get_heuristic_set(identifier: str) -> HeuristicSet:
    try:
        return REGISTRY[identifier]
    except KeyError as exc:
        raise ValueError(f"Unknown heuristic set: {identifier}") from exc
