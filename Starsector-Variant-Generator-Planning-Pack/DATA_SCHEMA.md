# DATA_SCHEMA.md
# Starsector Variant Generator Normalized Data Contract
Version 0.5

This document defines the shared internal models used by parsers, validation,
analysis, generation, the Refit Assistant, and the GUI.

Raw Starsector CSV/JSON/variant structures should not leak beyond parser
boundaries except as explicitly preserved `raw_fields`.

---

## 1. Provenance

Every normalized entity should carry provenance.

```text
Provenance
    source_kind: CORE | MOD | GENERATED | USER_OVERRIDE
    source_mod_id
    source_mod_version
    source_path
    source_hash
    parser_version
    confidence_state
    adapter_ids[]
    override_ids[]
```

### ConfidenceState

```text
KNOWN
INFERRED
OVERRIDDEN
ADAPTER_MODELED
UNKNOWN
```

---

## 2. LegalityResult

Hard legality is independent from quality.

```text
LEGAL
ILLEGAL
NOT_DETERMINABLE
```

A separate warnings collection may exist on any legal candidate.

Do not create `LEGAL_WITH_WARNINGS`; warnings are not legality.

---

## 3. ModInfo

```text
ModInfo
    id
    name
    version
    path
    enabled
    dependencies[]
    load_order
    provenance
```

---

## 4. Faction

```text
Faction
    id
    name
    source_mod_id
    known_hulls[]
    known_weapons[]
    known_fighters[]
    known_hullmods[]
    raw_doctrine
    inferred_doctrine
    equipment_access_metadata
    tags[]
    provenance
```

---

## 5. WeaponSlot

```text
WeaponSlot
    id
    size
    type
    mount_style
    x
    y
    angle
    arc
    built_in_weapon_id
    is_decorative
    replacement_locked
    provenance
```

Legality of weapon-to-slot compatibility belongs to the validation/rules layer.

---

## 6. Hull

```text
Hull
    id
    name
    source_mod_id
    hull_size
    hull_style
    deployment_points
    ordnance_points

    hitpoints
    armor_rating

    shield_type
    shield_arc
    shield_efficiency
    shield_upkeep

    flux_capacity
    flux_dissipation

    max_speed
    acceleration
    deceleration
    turn_rate
    turn_acceleration

    cargo_capacity
    fuel_capacity
    min_crew
    max_crew
    supplies_per_month
    fuel_per_lightyear
    max_burn_if_parseable

    fighter_bays
    ship_system_id

    built_in_hullmods[]
    weapon_slots[]

    civilian_flags[]
    logistics_flags[]
    sprite_ref
    tags[]
    raw_fields
    provenance
```

---

## 7. Weapon

```text
Weapon
    id
    name
    source_mod_id
    size
    mount_type
    ordnance_points
    range

    damage_type
    damage_per_shot
    burst_size
    shots_per_second
    sustained_dps

    flux_per_shot
    flux_per_second

    projectile_speed
    ammo
    ammo_regeneration

    point_defense
    beam

    hidden_state
    role_tags[]
    sprite_ref

    derived_scores
    raw_fields
    provenance
```

### HiddenState

```text
VISIBLE
HIDDEN
SECRET
DEV_ONLY
UNOBTAINABLE
UNKNOWN_RESTRICTED
```

---

## 8. FighterWing

```text
FighterWing
    id
    name
    source_mod_id
    role
    op_cost
    num_fighters
    replacement_time
    range
    fighter_hull_id
    hidden_state
    tags[]
    derived_scores
    provenance
```

---

## 9. Hullmod

```text
Hullmod
    id
    name
    source_mod_id

    op_cost_by_hull_size
    tags[]
    required_hullmods[]
    incompatible_hullmods[]

    hidden_state
    built_in_only
    s_mod_effect_state

    effects[]
    scripted_effect_state

    role_tags[]
    raw_fields
    provenance
```

---

## 10. HullmodEffect

Hullmods should be modeled as typed effects when reliably parseable or explicitly
provided by an adapter/override.

```text
HullmodEffect
    effect_id

    category:
        COMBAT
        DEFENSE
        FLUX
        MOBILITY
        LOGISTICS
        EXPLORATION
        SALVAGE
        SURVEY
        SENSOR
        CARRIER
        CONVERSION
        FLEET_SUPPORT
        OTHER

    stat

    operation:
        FLAT_ADD
        FLAT_SUBTRACT
        MULTIPLY
        PERCENT_ADD
        PERCENT_SUBTRACT
        SET
        BOOLEAN_ENABLE
        BOOLEAN_DISABLE
        CONDITIONAL
        UNKNOWN

    value
    units

    applicability:
        SELF
        FLEET_METADATA_ONLY
        CONDITIONAL_SELF
        UNKNOWN

    condition_description
    stack_behavior_if_known
    confidence_state
    provenance
```

`FLEET_METADATA_ONLY` effects may be recorded but are not optimized in the
current project scope.

---

## 11. BaseShipState

Represents parseable stats before optional fitting changes.

```text
BaseShipState
    hull_id
    base_stats
    built_in_weapon_state
    built_in_hullmods
    built_in_effects[]
```

---

## 12. DerivedShipState

This is the primary scoring input after known selected effects are applied.

```text
DerivedShipState
    hull_id
    selected_variant_id

    effective_stats:
        hitpoints
        armor
        shield_efficiency
        shield_upkeep
        flux_capacity
        flux_dissipation
        speed
        maneuverability

        cargo_capacity
        fuel_capacity
        crew_capacity
        supplies_per_month
        fuel_per_lightyear
        max_burn
        sensor_profile_if_known
        sensor_strength_if_known
        survey_effect_if_known
        salvage_effect_if_known

    weapon_metrics
    fighter_metrics
    selected_hullmods[]
    applied_effects[]
    unapplied_unknown_effects[]

    legality_result
    warnings[]
    confidence_summary
```

The scoring engine should evaluate this state, not raw hullmod names.

---

## 13. Variant

```text
Variant
    id
    hull_id
    source_mod_id
    display_name

    weapons_by_slot
    weapon_groups

    hullmods[]
    s_mods[]
    fighter_wings[]
    vents
    capacitors

    legality_result
    legality_reasons[]
    warnings[]

    quality_scores
    provenance
```

---

## 14. Profile

```text
Profile
    id
    name
    domain:
        COMBAT
        CIVILIAN
        HYBRID

    role

    control_assumption
    faction_mode

    weights

    target_range
    acceptable_range_min
    acceptable_range_max

    target_weapon_flux_ratio
    max_weapon_flux_ratio

    logistics_targets
    exploration_targets

    required_weapons[]
    forbidden_weapons[]

    required_hullmods[]
    forbidden_hullmods[]

    locked_slots
    allow_empty_slots

    allowed_mods[]
    forbidden_mods[]

    deterministic_seed
```

---

## 15. CivilianRole

Initial supported roles:

```text
FREIGHTER
TANKER
SALVAGE
SURVEY
TROOP_TRANSPORT
FAST_LOGISTICS
STEALTH_LOGISTICS
EXPEDITION_SUPPORT
GENERAL_SUPPORT
```

A hull may receive compatibility scores for multiple civilian roles.

---

## 16. CurrentFitState

Single authoritative state shared by GUI views.

```text
CurrentFitState
    hull_id
    base_variant_id
    profile

    selected_weapons_by_slot
    selected_hullmods[]
    selected_smods[]
    selected_fighters[]

    vents
    capacitors
    officer_assumption

    locked_slots[]
    locked_hullmods[]
    locked_fighters[]

    legality_result
    legality_reasons[]
    warnings[]

    dirty
```

---

## 17. RefitConstraintSet

Used by the Refit/Repair Assistant.

```text
RefitConstraintSet
    preserve_current_role
    preserve_faction_mode

    locked_slots[]
    locked_weapons[]
    locked_hullmods[]
    locked_fighters[]

    maximum_weapon_changes
    maximum_hullmod_changes
    maximum_total_changes

    allow_empty_slot_changes
    allow_role_change
    allow_faction_fallback

    objective:
        FIX_LEGALITY
        REDUCE_FLUX
        IMPROVE_AI_FIT
        IMPROVE_ROLE_MATCH
        IMPROVE_LOGISTICS
        IMPROVE_SURVEY
        IMPROVE_SALVAGE
        BALANCED_IMPROVEMENT
```

---

## 18. RefitSuggestion

```text
RefitSuggestion
    source_variant_id
    target_profile_id

    changes[]
        type
        target
        old_value
        new_value
        reason

    legality_before
    legality_after

    score_before
    score_after
    metric_deltas

    warnings_added[]
    warnings_resolved[]

    confidence_summary
```

---

## 19. EquipmentAccessMode

```text
STRICT_FACTION
FACTION_PLUS
UNRESTRICTED
```

---

## 20. Override Precedence

Hard legality cannot be overridden.

For non-legality metadata:

```text
manual override
    >
adapter model
    >
standard inference
    >
default/unknown
```

All override use must be visible in reports.


---

## 21. FactionCapabilityProfile

```text
FactionCapabilityProfile
    faction_id
    dimensions:
        armor_strength
        shield_strength
        ballistic_strength
        energy_strength
        missile_strength
        carrier_strength
        phase_strength
        mobility_strength
        long_range_strength
        brawler_strength
        skirmisher_strength
        pd_strength
        logistics_strength
        salvage_strength
        survey_strength
    role_coverage[]
    strengths[]
    adequate[]
    weaknesses[]
    gaps[]
    evidence_summary
    confidence_summary
    provenance
```

---

## 22. KnowledgePackManifest

```text
KnowledgePackManifest
    pack_id
    schema_version
    target_faction_id
    target_mod_id
    target_mod_version
    source_hashes[]
    authored_date
    authoring_method:
        HUMAN_CURATED
        AI_ASSISTED_REVIEW
        IMPORTED_GUIDE
        MIXED
    status:
        CURRENT
        PARTIALLY_STALE
        STALE
        INCOMPATIBLE
    notes
    provenance
```

---

## 23. FactionKnowledgePack

```text
FactionKnowledgePack
    manifest
    doctrine_profile
    hull_archetypes[]
    retrofit_templates[]
    progression_tiers[]
    capability_gap_guidance[]
    officer_guidance[]
    thematic_notes
    confidence
```

---

## 24. HullArchetypeGuidance

```text
HullArchetypeGuidance
    hull_id
    preferred_roles[]
    discouraged_roles[]
    preferred_hullmods[]
    discouraged_hullmods[]
    conditional_rules[]
    native_fit_notes
    basis[]
    confidence
```

---

## 25. RetrofitTemplate

```text
RetrofitTemplate
    id
    hull_id
    name
    target_role
    category:
        NATIVE
        RETROFIT
        EXPERIMENTAL
    required_constraints
    preferred_weapons
    preferred_hullmods
    discouraged_weapons
    discouraged_hullmods
    profile_overrides
    AI_control_suitability
    player_control_suitability
    basis[]
    confidence
    notes
```

---

## 26. ProgressionTier

```text
ProgressionTier
    id
    label
    order
    recommended_hulls[]
    recommended_roles[]
    suggested_retrofits[]
    notes
```

---

## 27. DoctrineStrictness

```text
LOOSE
BALANCED
STRICT
```

---

## 28. RecommendationConstraints

```text
RecommendationConstraints
    allow_foreign_hulls
    allow_hidden_or_secret
    control_assumption: AI | PLAYER | EITHER
    include_experimental_retrofits
    doctrine_strictness
    campaign_stage_id_optional
    max_results
```

---

## 29. RecommendationCandidate

```text
RecommendationCandidate
    candidate_type:
        NATIVE
        RETROFIT
        ACQUISITION
    hull_id
    retrofit_template_id_optional
    target_role
    capability_gap_id
    recommendation_score
    confidence_score
    component_scores:
        role_fit
        capability_gain
        equipment_compatibility
        AI_or_player_fit
        doctrine_fit
        availability_policy_fit
        retrofit_cost_if_applicable
    basis[]
    strengths[]
    weaknesses[]
    warnings[]
    diversity_family
    provenance
```

---

## 30. CapabilityGapRecommendation

```text
CapabilityGapRecommendation
    faction_id
    gap_id
    gap_description
    native_candidates[]
    retrofit_candidates[]
    acquisition_candidates[]
    recommended_shortlist[]
    why_not_index
    constraints_used
    heuristic_set
    knowledge_pack_status
```

---

## 31. WhyNotExplanation

```text
WhyNotExplanation
    candidate_id
    considered_for_gap
    eligibility
    final_score
    confidence_score
    largest_positive_factors[]
    largest_negative_factors[]
    excluded_reason_optional
    shortlist_cutoff_score_optional
```


---

## 32. EquipmentAffinity

```text
NATIVE
APPROVED
COMMON
UNALIGNED
FOREIGN
RESTRICTED
UNKNOWN
```

## 33. AvailabilityClass

```text
STANDARD
COMMON
RARE
SECRET
DEV_ONLY
UNOBTAINABLE
UNKNOWN
```

## 34. EquipmentAccessMetadata

```text
EquipmentAccessMetadata
    entity_id
    source_mod_id
    source_mod_name
    faction_affinity[]
    availability_class
    hidden_state
    evidence[]
    confidence_state
    provenance
```

## 35. RetrofitApplicationMode

```text
EXACT
STARSECTOR_STYLE
ADAPTIVE
```

## 36. AvailableEquipmentPool

```text
AvailableEquipmentPool
    weapons[]
    fighters[]
    hullmods[]
    source: INSTALLED_DATA | USER_SUPPLIED | FUTURE_SAVE_IMPORT
```

## 37. SubstitutionCandidate

```text
SubstitutionCandidate
    target_item_id
    replacement_item_id
    legality_result
    affinity
    source_mod_id
    component_scores
    confidence
    explanation[]
```
