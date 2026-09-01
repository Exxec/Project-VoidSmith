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

### EvidenceClass

`EvidenceClass` records how a fact was obtained; it is not a quality score and
does not alter hard legality. It is shared by normalized evidence records,
including source analysis, adapters, curated guidance, reviewer expectations,
mechanical inference, recommendations, and Why-Not output as each producer is
migrated.

```text
DIRECT_DATA
LOCAL_SOURCE_CODE
LOCAL_CONFIG
ADAPTER_MODELED
VIDEO_REVIEW_TRANSCRIPT
CURATED_GUIDANCE
REVIEWER_EXPECTATION
GENERIC_UNSOURCED_GUIDANCE
INFERRED_MECHANICS
UNKNOWN
CONFLICTING
```

`UNKNOWN`, `UNSUPPORTED`, and `CONFLICTING_EVIDENCE` remain distinct evidence
availability states. In particular, `EvidenceClass.UNKNOWN` says the source
class is not known; it does not mean a mechanic is safely absent.

`VIDEO_REVIEW_TRANSCRIPT` is timestamped creator evidence describing observed
gameplay. It is advisory only: local mechanical evidence (`DIRECT_DATA`, local
source/config, adapter models, and local mechanical inference) takes
precedence, while a transcript observation takes precedence over
`GENERIC_UNSOURCED_GUIDANCE`. It never changes legality or candidate scoring.
Player and AI claims remain separate in `ControlSuitabilityEvidence` and are
unresolved until a unique locally scanned hull identity and version context are
available.

The vocabulary above matches the project's eleven named evidence classes. It was
adopted by additional producers using additive fields only, with no existing
return type or behavior changed: `analysis/doctrine.py`'s
`DoctrineEvidence` (`INFERRED_MECHANICS` when variants were examined,
`UNKNOWN` with zero); `analysis/equipment_affinity.py`'s
`EquipmentAffinityClassification` (`CURATED_GUIDANCE` for a knowledge-pack
`APPROVED` result, `DIRECT_DATA` for every real faction `known_*`-list-based
tier including `UNALIGNED`); and the five adapter-effect-consumer records --
`analysis/civilian.py`'s `AppliedLogisticsEffect`/`AppliedReductionEffect`,
`analysis/combat_stats.py`'s `AppliedDefenseEffect`,
`analysis/mobility_stats.py`'s `AppliedMobilityEffect`,
`analysis/flux_stats.py`'s `AppliedFluxEffect`, and
`analysis/weapon_range_stats.py`'s `AppliedWeaponRangeEffect` -- all fixed at
`ADAPTER_MODELED`, correct by construction since each record only ever exists
when a verified `adapters/vanilla` table entry produced it. `analysis/
composite_hulls.py`'s structural records were read but deliberately left on
their own existing `ModuleResolution`/`confidence` shape rather than migrated
(see section 6A) -- they describe reference-resolution state, not acquired-
evidence provenance, so forcing `EvidenceClass` onto them would not be a
genuine fit. `analysis/classification.py`'s tag-based records were also
deliberately left alone: the tags themselves already are the citable
evidence, and the types are consumed very widely, so migrating them carried
migration risk without adding real explanatory power.

### CalibrationExpectationKind

Local hash-bound calibration labels declare what is being reviewed:

```text
BUILD_EXPECTATION
EQUIPMENT_EXPECTATION
FACTION_EXPECTATION
SCENARIO_EXPECTATION
NEGATIVE_EXPECTATION
```

For `NEGATIVE_EXPECTATION`, `expected` / `expected_any` is a forbidden result
set: the label matches only when the reviewed actual result is outside it.
Labels remain reviewer evidence, not an automatic heuristic adjustment.

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

### ScanMetrics

Read-only performance telemetry is recorded separately from gameplay data:

```text
ScanMetrics
    stage_seconds{}
    sources_scanned
    files_hashed
    bytes_hashed
    sources_reused
    sources_recomputed
    parallel_workers
```

Optional normalized source snapshots live only below the configured output
cache. They are reusable only when a complete content hash over every consumed
local input matches; incomplete, invalid, or missing context recomputes.


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
    sensor_profile_if_parseable   # direct static signature value; not fleet-wide sensor behavior

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

## 6A. Composite/Multipart Hull Structure

Complex hulls are represented as an auditable structural relationship, not a
merged combat state. These records are produced only from declared variant
module mappings and unambiguous locally scanned references.

The multipart/composite model formalized what was previously a set of ad hoc,
inconsistently-shaped representations (hull
role classification repeated as inline `hull_hints` string matching across
call sites; raw `(slot, target)` string pairs; one flat record mixing a
hull's *declared* structural role with one specific ship's *resolved*
structure) into six typed concepts. `HullDefinition`, `ShipModule`,
`CompositeHullDefinition`, and `ResolvedShipStructure` are new; `ModuleProfile`
is unchanged; `CompositeHullProfile` was renamed `CompositeShipProfile` (kept
as a backward-compatible alias in code) since the record is scoped to one
ship (variant) instance, not a hull type in the abstract.

```text
HullDefinition                # one Hull's declared composite-related role
    hull_id
    source_mod_id
    is_parent                 # declares SHIP_WITH_MODULES
    is_module                 # declares MODULE
    is_under_parent           # declares UNDER_PARENT
    is_station                # declares STATION

ShipModule                    # one raw declared slot -> child mapping,
    module_slot_id            # before resolution against the registry
    child_variant_id

ModuleProfile                 # one *resolved* module slot
    module_slot_id
    child_variant_id
    child_hull_id_optional
    resolution:
        RESOLVED
        UNRESOLVED_PARENT
        UNRESOLVED_CHILD_VARIANT
        UNRESOLVED_CHILD_HULL
    source_mod_id
    source_path

CompositeShipProfile          # one specific ship (variant) instance's
    parent_variant_id         # resolved structure
    parent_hull_id_optional
    source_mod_id
    modules[]                 # distinct declared parent-slot ModuleProfile records
    structural_features[]     # MULTIPART_PARENT_CHILD, REPEATED_MODULES,
                              # ASYMMETRIC_MODULES, STATION_STYLE_MODULES
    analysis_state: STRUCTURAL_ONLY
    confidence

CompositeHullDefinition       # hull-type-level declaration: does this hull
    hull: HullDefinition       # id declare the parent hint, and is that
    variants_with_module_maps # borne out by observed variant evidence.
    distinct_child_hull_ids[] # Distinct from CompositeShipProfile, which is
                              # scoped to one ship instance, not the type.

ResolvedShipStructure         # the fully resolved entity graph for one
    profile: CompositeShipProfile   # composite ship instance -- real Hull/
    parent_hull_optional            # Variant entities, not just ids, for the
    parent_variant_optional         # parent and every RESOLVED module, so a
    module_hulls{}                  # consumer needing the actual entities
    module_variants{}               # need not redo its own registry lookup.
                              # An unresolved module's entities stay null --
                              # never guessed at. Not embedded in the
                              # complex-hull-audit report (would duplicate
                              # raw source content the same way
                              # ScanResult.report() already avoids doing).
```

`STRUCTURAL_ONLY` is a hard scope boundary: it must not be used to aggregate
module weapons, shields, ship systems, destruction, detachment, survivability,
legality, or scoring into a parent. A material unresolved child reference or
scripted behavior remains `NOT_DETERMINABLE` / `UNKNOWN_SCRIPTED_EFFECT` for
any future composite operation. This boundary applies identically to every
type above, including `ResolvedShipStructure`'s real entity references: a
resolved module's `Hull`/`Variant` may be inspected for its own, independent
fit, never summed or merged into the parent's.

### 6B. Combat Entity Kind and Recommendation Eligibility

`CombatEntityKind` is a hull-level structural classification used only by
ordinary ship recommendation eligibility. It is separate from three-state
legality: a local fit may be `LEGAL` while still being excluded from normal
independent-ship ranking.

```text
CombatEntityKind
    SHIP | COMPOSITE_PARENT | SHIP_MODULE
    FIGHTER | INTERCEPTOR | BOMBER | ASSAULT_FIGHTER | SUPPORT_FIGHTER
    DRONE | MECH | STRIKECRAFT | STATION_MODULE | UNBOARDABLE_COMBAT_ENTITY
    UNKNOWN_SPECIAL

DeploymentModel
    INDEPENDENT | WING_BASED | BUILT_IN | SYSTEM_SPAWNED | MODULE_ATTACHED
    UNBOARDABLE_INDEPENDENT | UNKNOWN

RecommendationEligibility
    entity_kind: CombatEntityKind
    structural_support: FULL | PARTIAL | UNSUPPORTED
    eligible: bool
    reason
    confidence
```

The classifier uses only parsed `hull_size` and declared hull hints.
Fighter-sized, unboardable, module/station-module, and composite-parent hulls
are excluded from ordinary recommendation ranking. No custom AI, runtime
boardability, module combat behavior, or effective load-order behavior is
inferred.

### 6C. Combat Doctrine Profile

`CombatDoctrineProfile` describes what a normal hull's parseable static
configuration supports; it is advisory only and does not alter legality or
recommendation rank in the initial slice. Each axis is multi-valued, scored,
and carries independent confidence/evidence:

```text
battlefield_function: LINE_ANCHOR | FIRE_SUPPORT | SCREENING | FLANKING |
                      PURSUIT | STRIKE | CARRIER_SUPPORT | SUPPRESSION
engagement_position: FRONT_LINE | SECOND_LINE | BACK_LINE | FLANK | FREE_ROAM
tactical_style:      SUSTAINED_ASSAULT | STANDOFF | ARTILLERY | SKIRMISH |
                      MISSILE_ALPHA
tempo:               SUSTAINED
commitment:          LOW_COMMITMENT | HIGH_COMMITMENT
fleet_dependence:    INDEPENDENT | FORMATION_DEPENDENT | CARRIER_DEPENDENT
```

Scores derive from the existing hull feature vector: parseable defenses,
flux, mobility, mounts/arcs, bays, and observed mounted-weapon mix in existing
variants. Runtime system behavior, ammo/rearm cycles, custom AI, ramming,
reserve/sweeper behavior, and flavor-text fleet dependence remain absent.

Fighter-wing entity profiles use their parsed source role only: a source role
containing `BOMBER`, `INTERCEPTOR`/`SUPERIORITY`, `DRONE`, `ASSAULT`/`GUNSHIP`,
or support/escort/PD text produces the matching direct score. Payload,
replacement, rearm, delivery, and survivability metrics are unavailable until
the corresponding source fields are normalized. A hull becomes `MECH`,
`DRONE`, or `STRIKECRAFT` only from an explicit parsed hull hint, never from
name, slot count, custom AI, or fighter-sized geometry.

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

### 10A. Scripted-mechanic evidence ladder

Each interpreted effect records zero or more ordered evidence stages:

```text
EffectEvidence
    stage:
        PARSED_STATIC_METADATA
        LOCAL_SOURCE_STATIC_ANALYSIS
        KNOWN_API_CALL_INTERPRETATION
        MOD_LOCAL_CONFIGURATION
        VARIANT_USE_EVIDENCE
        ADAPTER_MODEL
        MANUAL_OVERRIDE
        UNKNOWN_SCRIPTED_EFFECT
    source_location
    evidence_summary
    confidence
    unmodeled_remainder[]
```

Stages describe how evidence was acquired. They do not change hard legality,
and they do not make variant-use evidence a hard mechanical fact. Explicit
manual overrides retain the repository-wide highest precedence over adapter
and inferred metadata; `UNKNOWN_SCRIPTED_EFFECT` is retained whenever the
known remainder cannot be interpreted safely.

The current local Java analyzer registry is `starsector-api-effects-0.4` and
recognizes documented `modifyFlat`, `modifyPercent`, and `modifyMult` calls
on a bounded set of ship stat accessors whose value argument resolves at one
of three confidence tiers: a bare literal/single same-file local constant
(confidence 0.9); a bounded arithmetic expression (`+`, `-`, `*`, `/`, unary
+/-) built only from numeric literals and constants declared `static final`
in that same local Java file (confidence 0.85, added in `-0.3`); or, new in
`-0.4`, an expression that resolves a `ClassName.CONSTANT`-qualified
reference to a `static final` constant declared in a *different* `.java`
file within the same mod/core source root (confidence 0.75) -- never a
constant declared in a different mod's source, a bare (unqualified) name
resolved only via a Java `import static` with no in-expression qualifier, a
method call, or any other runtime-dependent value. `starsector-api-effects
-0.4` also expanded the recognized accessor set itself from 14 to 29 real,
documented `MutableShipStatsAPI` stat-modifier methods (weapon-type rate-of-
fire and range-bonus accessors, damage-type-taken multipliers,
combat-readiness accessors, and four further single-stat accessors -- see
`analysis/hullmod_static_analysis.py`'s module docstring for the full
citation list). Its report preserves the Java file and line for every
recognized effect and every unrecognized modifier portion.
For a simple local `ShipAPI.HullSize.<SIZE>` branch, it also records the
recognized hull size and branch condition; nested or dynamic control flow
remains unmodeled rather than being inferred.

`HullmodStaticAnalysis` report records additionally preserve
`source_association` (`DECLARED_SCRIPT_CLASS`, `ID_REFERENCE_FALLBACK`, or a
no-source/no-class state) and `EvidenceRecord[]`. Since `-0.4`, unresolved
remainders are split into two distinct fields rather than one combined list:
`unsupported_scripted_portions` (`UNSUPPORTED_SCRIPTED_EFFECT:`-prefixed --
a call site that DID match a real, registered accessor but whose value
argument could not be resolved to a concrete number: a runtime variable, a
cross-mod reference, an unfoldable expression, or an argument list this
module's single-line parser could not extract) and `unknown_scripted_portions`
(`UNKNOWN_SCRIPTED_EFFECT:`-prefixed -- reserved for a call/reference this
module has no registry entry for at all, or a structural no-source/no-class
state). This is purely a re-classification of which branch an already-
computed unresolved case fell into, never new inference. The scan report
groups these records by `source_mod`; Java files are indexed in memory once
per source root for that scan, rather than treating a cached interpretation
as a source of truth across scans.

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

Current adapter-backed slices expose civilian, defense, and mobility derived
stat records independently. Mobility records preserve base/effective values,
per-effect provenance, and an unknown-stacking note when multiple verified
effects target the same stat; no combined value is fabricated in that case.

## 12A. Change Impact Report

```text
EntityKey
    category
    source_mod_id
    entity_id

EntityChange
    key
    status: UNCHANGED | CHANGED | ADDED | REMOVED | CONFLICTED
    previous_source_hash
    current_source_hash

ImpactTarget
    kind
    target_id
    certainty: EXACT | CONSERVATIVE | UNKNOWN_DEPENDENCY
    because[]
```

`ChangeImpactReport` is a read-only scan comparison. It plans selective
invalidation from explicit normalized references; it is not a cache hit, does
not recompute analyses, and does not alter source data. Canonical entity keys
include `source_mod_id` so duplicate mod-local IDs cannot be conflated.

## 12B. Analysis Result Cache

The optional SQLite cache is output-directory-only and keyed by an exact,
canonical context hash containing the cache schema version plus caller-supplied
source-manifest, heuristic, adapter, override, and pack context. A lookup with
any changed context is a miss. `ChangeImpactReport` exact targets may delete
matching entries; conservative/unknown impacts never claim an exact deletion.
The cache does not currently own automatic recomputation or result reuse until
each consumer declares its complete dependency context.

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

## 21A. CapabilityVector

```text
CapabilityVector
    subject_id
    dimensions: map<CapabilityDimension, CapabilityEvidence>

CapabilityEvidence
    score: 0.0..1.0 | null
    confidence: 0.0..1.0
    availability: AVAILABLE | UNKNOWN | NOT_DETERMINABLE
    supporting_evidence[]
    provenance[]
```

Implemented dimension vocabulary (`analysis/capability_vector.py::
CAPABILITY_DIMENSIONS`, 18 dimensions): `LONG_RANGE_PRESSURE`,
`KINETIC_PRESSURE`, `ARMOR_BREAKING`, `FINISHING_POWER`,
`SUSTAINED_PRESSURE`, `BURST_STRIKE`, `PD_SCREENING`,
`FIGHTER_INTERCEPTION`, `MISSILE_PROJECTION`, `ARMOR_TANKING`,
`SHIELD_TANKING`, `MOBILITY`, `PURSUIT`, `CARRIER_PROJECTION`, `FREIGHTER`,
`TANKER`, `SALVAGE_SUPPORT`, and `SURVEY_SUPPORT`. This is a
forward-compatible contract: the current analyzer populates only dimensions
grounded in existing normalized evidence. Missing dimensions must remain
unavailable rather than being inferred from names, source mods, or scripts.

---

## 21B. BuildArchetypeProfile

```text
BuildArchetypeProfile
    hull_id
    build_id
    role
    tactical_style
    compatibility
    confidence
    maturity                  # VIABLE | EXPERIMENTAL
    target_range
    flux_posture
    survivability_posture
    equipment_priorities[]
    ai_suitability
    player_suitability
    strengths[]
    weaknesses[]
    supporting_evidence[]
    capability_evidence[]
    mechanical_archetype_scores{}
    variant_usage_evidence[]
    scenario_objectives[]
```

`BuildArchetypeProfile` is non-exclusive. It models a viable way to fit one
specific hull and is strictly separate from hard legality. Recommendations and
generated candidates identify the `Hull + BuildArchetype` path; low-support
paths remain `EXPERIMENTAL` rather than being treated as normal fits.

### ScenarioObjective

```text
ScenarioObjective
    objective_id
    support_state: SUPPORTED | PARTIAL | UNSUPPORTED
    required_signals[]
    note
```

Objectives select only already-modeled range, PD, missile, fighter, mobility,
or defense signals. Unsupported objectives remain visible with their reason;
they must not become hidden scoring hints or invented equipment semantics.

Every Native, Retrofit, and Acquisition recommendation records both
`recommendation_score` (the score used for ordering within its own leg) and
`confidence` separately. Neither field affects legality.

---

## 21. FactionCapabilityProfile

```text
FactionCapabilityProfile
    faction_id
    known_hulls_examined
    unresolved_known_hull_ids[]
    role_capabilities[]        # RoleCapability: role, best_hull_id, best_score, hulls_examined
    civilian_role_coverage[]
    capability_vector{}        # dimension -> CapabilityEvidence, section 21A's 18 dimensions
    strengths[]
    weaknesses[]
    capability_gaps[]
```

Matches `analysis/faction_capability.py::FactionCapabilityProfile` and
`analyze_faction_capability`; `strengths`/`weaknesses`/`capability_gaps` are
derived from `capability_vector` scores against the `gap_strong_threshold`/
`gap_adequate_threshold`/`gap_weak_threshold` heuristics (`HEURISTICS.md`
section 7, `core/heuristics.py`).

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
    campaign_stage: EARLY | MID | LATE | ENDGAME | null
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
    mechanical_archetype_profile
    diversity_decision
    provenance
```

`mechanical_archetype_profile` and `diversity_decision` preserve the raw
inference and shortlist rationale; a display-only family label is insufficient
for explainability.

### HullFeatureVector

Deterministic normalized evidence extracted from a `Hull` and, where present,
aggregate existing-variant observations. Values are in `[0, 1]` unless their
named units state otherwise. Every value records whether it is `KNOWN`,
`INFERRED`, or `UNKNOWN`; unknown values are never silently treated as zero or
as a favorable trait.

```text
HullFeatureVector
    hull_id
    schema_version
    hull_size
    deployment_points
    ordnance_points
    armor
    hitpoints
    shield_presence
    shield_arc
    shield_efficiency
    flux_capacity
    flux_dissipation
    speed
    acceleration
    deceleration
    turn_rate
    turn_acceleration
    weapon_mount_composition
    weapon_mount_size_distribution
    weapon_mount_arc_distribution
    missile_mount_capacity
    fighter_bays
    built_in_weapon_evidence
    built_in_hullmod_evidence
    known_ship_system_category_evidence
    cargo_capacity
    fuel_capacity
    crew_capacity
    supplies_per_month
    fuel_per_lightyear
    max_burn_if_known
    existing_variant_usage_evidence
    feature_evidence[]
    provenance
```

`existing_variant_usage_evidence` is an aggregate, provenance-preserving
statistical observation (for example, role/loadout frequencies among resolved
variants). It is advisory only: it cannot override raw structural evidence,
legality, equipment affinity, or an explicit override.

### MechanicalArchetypeProfile

```text
MechanicalArchetypeProfile
    hull_id
    feature_vector_schema_version
    compatibility_scores:
        ARMOR_BRAWLER
        SHIELD_BRAWLER
        LINE_SHIP
        ARTILLERY
        SKIRMISHER
        STRIKER
        MISSILE_SUPPORT
        PD_ESCORT
        LIGHT_CARRIER
        HEAVY_CARRIER
        BATTLECARRIER
        COMBAT_FREIGHTER
        FREIGHTER
        TANKER
        SALVAGE_SUPPORT
        SURVEY_SUPPORT
    evidence_by_archetype[]
    confidence_by_archetype[]
    override_or_pack_enrichments[]
    provenance
```

Compatibility scores are non-exclusive normalized values. Each score must be
reproducible from recorded feature/evidence contributions, including bounded
existing-variant usage evidence. A profile may have no sufficiently supported
archetype; that is distinct from asserting a negative archetype.

### DiversityDecision

```text
DiversityDecision
    recommendation_leg: NATIVE | RETROFIT | ACQUISITION
    score_rank_before_diversity
    selected
    compared_candidate_ids[]
    functional_role_distance
    mechanical_archetype_distance
    score_tradeoff
    decision_reason
    evidence[]
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
    diversity_decision_optional
    mechanical_archetype_profile_optional
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

Availability is an evidence state independent of faction affinity. Current
local inference emits `UNOBTAINABLE` only for parsed built-in-only hullmods,
`SECRET` only for parsed hidden hullmods, and `STANDARD`/`COMMON`/`RARE`/
`DEV_ONLY` only for explicit local tags. All other entities remain `UNKNOWN`.

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

## 38. CapabilityGap / NativeRecommendation

See `GAP_RECOMMENDATION_ENGINE.md` (project-authored, not part of this
synced pack) for the full `CapabilityGap`/`NativeRecommendation` shapes
and the algorithm producing them.

## 39. ScenarioRecommendation (Phase 31)

```text
ScenarioRecommendation
    role
    scenario                      # ScenarioCategory: RAIDING | DEFENSE | ESCORT | PATROL
    hull_id
    build_archetype_id
    source_leg                    # NATIVE | RETROFIT | ACQUISITION -- which real leg's ranked candidate this reuses
    source_variant_id             # set only when source_leg == RETROFIT
    base_recommendation_score     # the cited leg's own real, unmodified recommendation_score
    scenario_fit_score            # 0.0-1.0 heuristic-only; never evidence, never legality
    scenario_recommendation_score # base_recommendation_score * scenario_fit_score
    rank
    confidence                    # bounded below the underlying leg's own confidence
    reason
    scenario_fit_evidence[]
    kind                          # always "INFERRED_SCENARIO_OPTION"
```

A `ScenarioRecommendation` is always an addition alongside, never a
replacement for, its cited leg's own `CapabilityGap`/`NativeRecommendation`/
`RetrofitRecommendation`/`AcquisitionRecommendation` record. See
`GAP_RECOMMENDATION_ENGINE.md` section 18 for the full algorithm and the
distinction from the unrelated `ScenarioObjective` in section 21B.

## 40. Fleet Support Advisor (Phase 43)

```text
FleetSelection
    hull_id
    count                         # player-declared selected instances; never a recommendation quantity

PlayerFleetProfile
    selections[]                  # locked selections
    resolved_hull_ids[]
    unresolved_hull_ids[]
    excluded_selection_hull_ids[] # structural ineligibility only
    capability_vector{}           # best selected-hull coverage, not fleet outcome prediction
    doctrine{}                    # mean six-axis per-hull posture
    support_needs[]
    evidence[]

FleetSupportNeed
    capability
    score
    confidence
    category                      # COMBAT | LOGISTICS
    evidence[]

FleetCompositionTrait
    name                            # evidence-gated composition characteristic
    score                           # count-aware prevalence or normalized aggregate
    confidence
    evidence[]

CompositionSynergyProfile
    phase_match                     # direct PHASE hint compatibility only
    sensor_match                    # normalized static sensor-profile compatibility only
    burn_match                      # static base max-burn compatibility only
    mobility_character_match        # normalized capability-character compatibility
    score
    confidence
    evidence[]

FleetSupportScoreComponents
    support_need_coverage
    doctrine_cohesion
    composition_synergy
    static_friction
    access_affinity
    recommendation_score

FleetSupportRecommendation
    hull_id
    recommendation_type           # SYNERGY | GAP_FILL | SYNERGY_AND_GAP_FILL
    category                      # COMBAT_SUPPORT | LOGISTICS_SUPPORT
    recommendation_score
    confidence
    supports[]
    support_purposes[]
    composition_synergy
    score_components
    compatibility
    friction
    access_affinity
    fit_legality_status           # NOT_EVALUATED_NO_CONCRETE_FIT
    mechanical_archetypes[]       # selected evidence-backed family labels
    diversity_reason
    shortlist_order
    evidence[]
```

This model is advisory only. It does not select fleet composition or quantities,
replace selected hulls, infer player inventory/campaign state, or determine
variant legality. Unknown campaign dimensions remain explicit rather than zero.

```text
FleetSupportWhyNotExplanation
    hull_id
    resolved
    recommended
    rank
    total_ranked_candidates
    recommendation_score
    confidence
    reason
    recommendation                 # cited only when a material ranked candidate exists
```

`FleetSupportResult.unaddressed_support_needs[]` preserves a detected need for
which no candidate cleared the advisor's structural/access/signal gates.

## 41. Scenario / Mission Advisor

```text
ScenarioObjectiveProfile
    scenario_id
    display_name
    capability_targets[]          # explicit known CapabilityVector dimensions only
    pressures[]                   # generic ScenarioPressure values; never mission-name logic
    evidence_class                # USER_DECLARED | GENERIC_TEMPLATE | curated/direct future sources
    confidence
    evidence[]

ScenarioAlignment
    capability
    target
    available                     # locked fleet coverage, not combat outcome
    gap
    confidence
    status                        # STRONG | ADEQUATE | WEAK | UNKNOWN
    evidence[]

ScenarioFleetAssessment
    scenario
    readiness                     # GOOD | MIXED | POOR | UNKNOWN
    readiness_score
    confidence
    strengths[]
    deficiencies[]
    unknowns[]
    recommendations[]             # individual FleetSupportRecommendation records
    evidence[]
```

This advisor evaluates static mechanical alignment only. It does not identify
a mission from a name, parse a save, simulate tactics, predict victory, select
quantities, replace locked ships, or change legality. Scenario-derived needs
are advisory inputs to the existing individual-addition ranking path.

```text
FleetSupportCategoryShortlist
    category                      # COMBAT_SUPPORT | LOGISTICS_SUPPORT
    support_needs[]
    recommendations[]             # exact advisor records, independently score-bounded for this category
```
