STARSECTOR VARIANT GENERATOR
Formal Algorithm and Implementation Specification
Version 0.5
Date: 2026-08-22

======================================================================
1. PURPOSE
======================================================================

This document defines the initial architecture and implementation contract for a local Starsector ship-variant analysis and generation tool.

The program will scan Starsector core data and enabled mods, normalize hull, weapon, fighter, hullmod, faction, and variant data, analyze existing fitting patterns, classify hulls and equipment, generate legal ship variants from rule-based profiles, score and rank those variants, explain its decisions, and export generated variants into a separate compatibility mod without modifying the original game or source mods.

The design must support three user-facing modes:

1. Beginner
   - Minimal choices.
   - Conservative, AI-friendly, legal builds.
   - Strong defaults.
   - One recommended build plus limited alternatives.

2. Guided
   - Intermediate choices.
   - Teaches fitting logic.
   - Lets the user choose role, safety/aggression, faction purity, and AI/player control assumptions.

3. Advanced / Manual
   - Full control over scoring weights, role targets, range, flux tolerance, weapon restrictions, hullmod locks, S-mod assumptions, officer skills, personality, faction restrictions, and other fitting constraints.

The first implementation must NOT use external AI or an API. The core generator must be deterministic, transparent, explainable, and usable offline.

======================================================================
2. PRIMARY DESIGN PRINCIPLES
======================================================================

2.1 Never modify source mods
----------------------------
The application must treat all Starsector and mod files as read-only.
Generated variants must be written to a separate output directory or generated compatibility mod.

Example:
    StarsectorVariantGenerator_Output/
        mod_info.json
        data/
            variants/

The tool must never overwrite Starsector core files or files inside source mods.

2.2 Explainable scoring
-----------------------
The tool must not output opaque statements such as "Weapon X is best."
It should provide a score breakdown such as:

    Weapon: Heavy Autocannon
    Range fit:           +18.0
    Kinetic role fit:    +20.0
    Flux efficiency:     +15.2
    OP efficiency:       +11.4
    Faction preference:  +10.0
    AI compatibility:    +13.5
    Range mismatch:       -3.0
    --------------------------------
    Final score:          85.1

Every generated build should be explainable in similar fashion.

2.3 Legal before optimal
------------------------
The generator must reject illegal variants before comparing their quality. No scoring should rescue a build that violates hard game constraints.

2.4 Role consistency
--------------------
A generated ship must have a coherent battlefield role. Avoid internally contradictory fits such as:
- Long-range artillery with short-range secondary weapons that pull AI forward.
- Fragile skirmishers overloaded with armor hullmods and no mobility support.
- Carriers with incompatible fighter doctrine and weapon ranges.
- Missile support ships with no meaningful missile investment.
- High-flux weapon packages with inadequate dissipation unless the profile explicitly permits overfluxing.

2.5 Faction identity matters
----------------------------
The generator must support:
    STRICT_FACTION
    FACTION_PLUS
    UNRESTRICTED

STRICT_FACTION:
    Prefer only faction-native weapons/fighters/hullmods when legal and available.

FACTION_PLUS:
    Prefer faction-native equipment, but use vanilla/common or explicitly allowed fallback equipment when the faction lacks a suitable option.

UNRESTRICTED:
    Any installed compatible equipment may be considered.

FACTION_PLUS should be the recommended default.

2.6 Existing variants are evidence, not absolute truth
------------------------------------------------------
Existing variants should be analyzed to infer doctrine and fitting tendencies, including typical range, repeated hullmods, kinetic/HE balance, missile usage, fighter preferences, weapon families, vent/cap tendencies, and intentionally empty mounts.
They should not be treated as perfect examples.

2.7 Deterministic first
-----------------------
Given the same data set, profile, faction rules, seed, and configuration, the generator should produce the same ranked results. Randomness may be added later, but deterministic mode must always exist.

======================================================================
3. INITIAL SCOPE
======================================================================

The first complete version should support:
- Starsector core data.
- Arbitrary installed mods using standard Starsector data structures.
- Hull parsing.
- Weapon parsing.
- Fighter wing parsing.
- Hullmod parsing.
- Variant parsing.
- Faction parsing.
- Existing variant analysis.
- Hull classification.
- Weapon/fighter/hullmod classification.
- Profile-based variant generation.
- OP, mount, hullmod, fighter bay, vent, and capacitor validation.
- Flux estimation.
- Range coherence scoring.
- AI-friendliness scoring.
- Faction doctrine scoring.
- Variant export.
- Human-readable reports.
- Beginner, Guided, and Advanced mode support at the engine/API layer.

A graphical UI is not required for the first usable milestone. A command-line interface is sufficient initially.

======================================================================
4. NON-GOALS FOR VERSION 1
======================================================================

Do not attempt all of the following in the first version:
- Machine learning.
- LLM/API integration.
- Automatic combat simulation.
- Automatic piloting.
- Real-time game memory access.
- Save editing.
- Weapon graphical analysis.
- Pixel-perfect firing arc reasoning from sprites.
- Dynamic tactical simulation of every possible opponent.
- Colony optimization.
- Campaign fleet composition optimization. A locked-selection Fleet Support
  Advisor may rank individual complementary additions, but must not choose a
  composition, quantities, replacements, or campaign-state actions.
- Automatic S-mod progression planning.
- Multiplayer/network features.
- Direct modification of original mods.

======================================================================
5. HIGH-LEVEL PIPELINE
======================================================================

    Locate Starsector installation
        |
        v
    Locate enabled mods
        |
        v
    Scan core + mod data
        |
        v
    Parse raw entities
        |
        v
    Normalize data into shared models
        |
        v
    Resolve cross-references
        |
        v
    Analyze existing variants
        |
        v
    Infer faction doctrine statistics
        |
        v
    Classify hull
        |
        v
    Select profile(s)
        |
        v
    Generate constrained candidate fits
        |
        v
    Reject illegal fits
        |
        v
    Optimize hullmods / vents / capacitors
        |
        v
    Build weapon groups
        |
        v
    Score legal candidates
        |
        v
    Rank candidates
        |
        v
    Explain score and warnings
        |
        v
    Export selected variant(s)
        |
        v
    Write compatibility mod + reports

======================================================================
6. PROPOSED PROJECT LAYOUT
======================================================================

    starsector_variant_generator/
        README.md
        AGENTS.md
        pyproject.toml or equivalent

        src/
            core/
                models/
                config/
                registry/
                scoring/
                generation/
                validation/
                logging/

            parsers/
                hull_parser
                weapon_parser
                fighter_parser
                hullmod_parser
                variant_parser
                faction_parser
                mod_parser

            analysis/
                hull_classifier
                weapon_classifier
                fighter_classifier
                hullmod_classifier
                faction_doctrine
                variant_analyzer
                flux_analyzer
                range_analyzer
                ai_heuristics

            profiles/
                role_profiles
                beginner_presets
                guided_presets
                advanced_schema
                faction_profiles
                fallback_profiles

            generation/
                profile_selector
                weapon_selector
                fighter_selector
                hullmod_selector
                vent_cap_allocator
                weapon_group_builder
                candidate_builder
                candidate_pruner

            output/
                variant_writer
                report_writer
                compatibility_mod_writer
                metadata_writer

            cli/
                commands
                interactive
                batch

        tests/
            fixtures/
            parser/
            analysis/
            generation/
            validation/
            regression/

        docs/
            architecture/
            data_models/
            profiles/
            scoring/
            examples/

        generated/
            reports/
            variants/
            cache/

======================================================================
7. SHARED DATA MODELS
======================================================================

All parsed content should be converted into normalized internal models. The generator should not operate directly on raw CSV/JSON text after parsing.

7.1 ModInfo
-----------
Fields:
    mod_id
    mod_name
    version
    path
    enabled
    dependencies
    load_order
    source_type: CORE | MOD

7.2 Faction
-----------
Fields:
    id
    name
    source_mod
    known_hulls
    known_weapons
    known_fighters
    known_hullmods
    doctrine_metadata
    markets_if_available
    tags

Derived:
    inferred_weapon_preferences
    inferred_range_preferences
    inferred_hullmod_preferences
    inferred_role_distribution
    inferred_fighter_preferences

7.3 Hull
--------
Fields should include at least:
    id
    name
    source_mod
    hull_size
    hull_style
    fleet_points_if_available
    deployment_points
    base_value
    supplies_per_month
    supplies_to_recover
    fuel_per_lightyear
    crew_min
    crew_max
    cargo_capacity
    fuel_capacity
    hitpoints
    armor_rating
    shield_type
    shield_arc
    shield_efficiency
    shield_upkeep
    shield_flux_per_damage
    flux_capacity
    flux_dissipation
    max_speed
    acceleration
    deceleration
    turn_rate
    turn_acceleration
    fighter_bays
    ordnance_points
    ship_system
    built_in_hullmods
    tags
    hints
    weapon_mounts[]
        mount_id
        size
        type
        arc
        angle
        x
        y
        built_in_weapon_if_any

Derived:
    durability_score
    mobility_score
    flux_score
    carrier_score
    missile_capacity_score
    ballistic_capacity_score
    energy_capacity_score
    range_potential
    likely_roles[]
    profile_compatibility_scores

7.4 Weapon
----------
Fields:
    id
    name
    source_mod
    manufacturer_or_design_type_if_available
    size
    mount_type
    ordnance_points
    range
    damage_type
    damage_per_shot
    shots_per_second
    burst_size
    burst_delay
    refire_delay
    dps
    sustained_dps
    flux_per_shot
    flux_per_second
    damage_per_flux
    projectile_speed
    projectile_count
    beam
    burst_beam
    point_defense
    ammo
    ammo_regeneration
    max_ammo
    tags
    hints
    weapon_group_behavior_if_available

Derived role tags may include:
    KINETIC_PRESSURE
    ARMOR_BREAKER
    HULL_FINISHER
    PD
    STRIKE
    ARTILLERY
    SUSTAINED
    BURST
    MISSILE_PRESSURE
    MISSILE_FINISHER
    DISABLE
    SUPPORT

Derived scores:
    range_band
    flux_efficiency_score
    op_efficiency_score
    ai_friendliness_score
    ammo_endurance_score
    burst_score
    sustained_score
    faction_affinity

7.5 FighterWing
---------------
Fields:
    id
    name
    source_mod
    role
    op_cost
    num_fighters
    replacement_time
    range
    fighter_hull_id
    tags

Derived:
    interceptor_score
    bomber_score
    support_score
    durability_score
    replacement_efficiency
    carrier_compatibility

7.6 Hullmod
-----------
Fields:
    id
    name
    source_mod
    op_cost_by_hull_size
    tags
    required_hullmods
    incompatible_hullmods
    hidden
    built_in_only
    s_mod_effect_if_parseable

Derived:
    role_tags[]
    offense_score
    defense_score
    mobility_score
    flux_score
    range_score
    carrier_score
    ai_friendliness_score

7.7 Variant
-----------
Fields:
    variant_id
    hull_id
    source_mod
    display_name
    goal_variant
    autofit_variant
    weapons_by_mount
    weapon_groups
    hullmods
    s_mods_if_available
    fighter_wings
    flux_vents
    flux_capacitors

Derived:
    total_op_spent
    total_weapon_flux
    effective_dissipation
    range_distribution
    role_guess
    doctrine_match
    legality
    warnings[]
    quality_scores

7.8 Profile
-----------
A Profile defines what kind of build the generator is trying to make.

Fields:
    id
    name
    description
    allowed_hull_sizes
    required_features
    forbidden_features
    target_range
    acceptable_range_min
    acceptable_range_max
    kinetic_weight
    he_weight
    energy_weight
    fragmentation_weight
    burst_weight
    sustained_weight
    pd_weight
    missile_weight
    mobility_weight
    survivability_weight
    flux_safety_weight
    op_efficiency_weight
    ai_friendliness_weight
    faction_match_weight
    range_coherence_weight
    max_weapon_flux_ratio
    target_weapon_flux_ratio
    min_pd_score
    min_kinetic_score
    min_armor_damage_score
    required_hullmods[]
    preferred_hullmods[]
    forbidden_hullmods[]
    personality_assumption
    control_assumption: AI | PLAYER | EITHER
    faction_mode: STRICT_FACTION | FACTION_PLUS | UNRESTRICTED

======================================================================
8. INITIAL ROLE PROFILE CATALOG
======================================================================

Start with a limited, understandable set:
    LINE_BRAWLER
    LINE_ARTILLERY
    ASSAULT
    MISSILE_SUPPORT
    ESCORT
    PD_ESCORT
    SKIRMISHER
    PURSUIT
    STRIKE
    TANK
    CARRIER
    BATTLE_CARRIER
    SUPPORT

Do not create dozens of roles until the initial set is validated.

Example LINE_BRAWLER priorities:
    Survivability             HIGH
    Kinetic pressure          HIGH
    Armor damage              HIGH
    Range                     MEDIUM
    Flux safety               HIGH
    Mobility                  LOW-MEDIUM
    PD                        MEDIUM
    Burst                     MEDIUM
    Sustained damage          HIGH
    AI friendliness           HIGH

Suggested starting weights:
    survivability_weight      1.40
    kinetic_weight            1.25
    he_weight                 1.25
    sustained_weight          1.20
    flux_safety_weight        1.20
    ai_friendliness_weight    1.30
    range_coherence_weight    1.10
    mobility_weight           0.70
    burst_weight              0.90
    op_efficiency_weight      1.00

Example LINE_ARTILLERY priorities:
    Range                     VERY HIGH
    Sustained damage          HIGH
    Flux efficiency           HIGH
    AI friendliness           HIGH
    Range coherence           VERY HIGH
    Survivability             MEDIUM
    Mobility                  LOW
    Burst                     LOW-MEDIUM

Suggested starting weights:
    range_weight              1.50
    sustained_weight          1.30
    flux_safety_weight        1.25
    ai_friendliness_weight    1.35
    range_coherence_weight    1.50
    survivability_weight      0.90
    mobility_weight           0.50
    burst_weight              0.60

Example STRIKE priorities:
    Burst                     VERY HIGH
    Mobility                  HIGH
    Finishing damage          HIGH
    Flux safety               MEDIUM-LOW
    Range coherence           MEDIUM
    Survivability             MEDIUM

Suggested starting weights:
    burst_weight              1.60
    mobility_weight           1.35
    he_weight                 1.20
    flux_safety_weight        0.75
    range_coherence_weight    0.90
    survivability_weight      0.90

======================================================================
9. BEGINNER / GUIDED / ADVANCED MODES
======================================================================

All three modes are interfaces over the same engine.

9.1 Beginner mode
-----------------
User selects:
    Hull
    Role
Optional:
    Faction mode, default FACTION_PLUS

Hidden defaults:
    AI control assumption
    high flux safety
    high AI friendliness
    high range coherence
    conservative OP allocation
    moderate PD
    standard officer assumptions

Output:
    one recommended build
    up to two alternatives
    simple explanation
    important warnings only

Beginner mode favors consistency over theoretical maximum damage.

9.2 Guided mode
---------------
User selects:
    Hull
    Role
    Combat style: SAFE | BALANCED | AGGRESSIVE
    Equipment access: STRICT_FACTION | FACTION_PLUS | UNRESTRICTED
    Control: AI | PLAYER
Optional:
    short-range / balanced / long-range preference
    defense / balanced / damage preference

Output:
    ranked builds
    moderate explanation
    educational tradeoff notes

9.3 Advanced / Manual mode
--------------------------
Expose:
    all profile weights
    minimum/maximum weapon range
    desired engagement range
    flux tolerance
    overflux allowance
    PD budget
    missile budget
    OP reserve
    damage-type weighting
    required weapons
    forbidden weapons
    required hullmods
    forbidden hullmods
    locked mounts
    empty-mount permission
    faction purity
    cross-mod allow/deny list
    S-mod assumptions
    officer skills
    officer personality
    player/AI assumption
    fighter constraints
    vent/cap priorities
    candidate count
    search depth
    deterministic seed

Advanced mode should support:
    Open Beginner Build in Advanced Mode

======================================================================
10. HULL CLASSIFICATION ALGORITHM
======================================================================

Hull classification should combine hard stats with mount layout and systems. It should produce multiple role compatibility scores rather than one hard class.

Example:
    Hull: Example Cruiser
    LINE_BRAWLER       0.91
    LINE_ARTILLERY     0.83
    ASSAULT            0.79
    MISSILE_SUPPORT    0.61
    ESCORT             0.42
    CARRIER            0.00

Features should include:
    durability
    mobility
    firepower potential
    flux support
    range potential
    carrier potential
    missile capacity
    frontal arc coherence
    existing variant evidence

Example configurable formula:
    LINE_ARTILLERY compatibility =
        0.25 * range_potential
      + 0.20 * frontal_firepower
      + 0.15 * flux_score
      + 0.15 * survivability
      + 0.10 * weapon_arc_coherence
      + 0.10 * existing_variant_evidence
      - 0.05 * excessive_mobility_dependency

======================================================================
11. WEAPON CLASSIFICATION
======================================================================

Weapon classification should derive descriptive tags from stats.

Kinetic pressure:
    kinetic damage
    sustained DPS
    useful range
    effectively sustainable ammo
    acceptable flux efficiency

Armor breaker:
    HE damage
    meaningful per-shot damage
    acceptable sustained output

Hull finisher:
    HE or energy damage
    strong burst or finishing profile
    usable accuracy/projectile behavior

PD:
    PD tag/hints
    tracking suitability
    projectile speed
    range
    OP efficiency

Strike:
    high alpha
    long reload acceptable
    ammo limitation acceptable

Artillery:
    long range
    reasonable projectile speed
    sustained accuracy
    acceptable flux/OP efficiency

AI-friendliness penalties may include:
    extreme flux burden
    severe range mismatch
    very slow projectile for intended targets
    weapons encouraging unwanted approach behavior
    unusual ammo constraints
    incompatible role tags

======================================================================
12. FACTION DOCTRINE INFERENCE
======================================================================

No AI is required.

Doctrine is inferred statistically from:
    faction-known equipment
    faction-known hulls
    existing variants
    repeated hullmods
    repeated weapon families
    typical engagement ranges
    fighter usage
    missile usage
    shield/armor bias

Calculate distributions such as:
    ballistic_mount_usage
    energy_mount_usage
    missile_mount_usage
    average_primary_range
    kinetic_share
    HE_share
    PD_share
    common_hullmods
    common_weapon_families
    fighter_role_distribution
    vents_to_caps_ratio

Doctrine values are priors, not hard restrictions. STRICT_FACTION can convert some priors into restrictions.

======================================================================
13. CANDIDATE GENERATION
======================================================================

Brute-forcing every weapon combination is prohibited. Large modpacks make the search space enormous.

13.1 Mount grouping
-------------------
Group symmetrical/equivalent mounts where possible. Treat mirrored mounts as one decision unless asymmetric fitting is explicitly allowed.

13.2 Candidate list per mount/group
-----------------------------------
For each mount/group:
    1. Filter illegal weapon types.
    2. Filter by faction access mode.
    3. Filter by hard profile requirements.
    4. Score individual weapons.
    5. Keep only top N.

Recommended initial N: 5 to 10 per mount group.

13.3 Combination generation
---------------------------
Use beam search, branch-and-bound, bounded best-first search, or another deterministic pruned search. Do not use full Cartesian products.

At each partial loadout:
    estimate remaining OP
    estimate flux
    estimate range coherence
    reject impossible branches early

13.4 Early pruning examples
---------------------------
Reject a partial build if:
    spent OP > total OP
    weapon flux already exceeds hard maximum
    required damage role can no longer be satisfied
    profile minimum PD can no longer be met
    range mismatch exceeds hard profile limit
    required hullmod OP can no longer fit

======================================================================
14. HULLMOD SELECTION
======================================================================

Select hullmods after a preliminary weapon package exists because hullmod value depends on what the weapons are trying to do.

Pipeline:
    preliminary weapon package
        |
        v
    identify deficiencies
        |
        v
    generate hullmod candidates
        |
        v
    apply required hullmods
        |
        v
    score preferred hullmods
        |
        v
    validate incompatibilities
        |
        v
    select best legal combination

Potential deficiencies:
    insufficient range
    excessive weapon flux
    poor shield endurance
    poor armor
    insufficient speed
    missile ammo limitation
    carrier replacement problems
    inadequate PD

Treat S-mod assumptions separately from ordinary OP spending.

======================================================================
15. FLUX, VENTS, AND CAPACITORS
======================================================================

Minimum transparent model:
    weapon_flux_per_second
    shield_upkeep
    base_dissipation
    vent_bonus
    capacitor_bonus

Derived:
    sustained_flux_load = weapon_flux_per_second + shield_upkeep
    dissipation_ratio = effective_dissipation / sustained_flux_load

Starting profile targets:
    SAFE:       target ratio >= 0.90 where practical
    BALANCED:   target ratio >= 0.75
    AGGRESSIVE: target ratio >= 0.55

These are starting heuristics, not universal truths. Strike ships may intentionally exceed them.

Vent/cap allocation:
    1. Reserve OP for required hullmods.
    2. Fit weapons/fighters.
    3. Add vents until target flux ratio or max vents reached.
    4. Add capacitors with remaining OP according to profile.
    5. If OP remains, reconsider optional hullmods or stronger weapon substitutions.
    6. Rescore.

======================================================================
16. RANGE COHERENCE
======================================================================

For weapons intended to fire together, calculate:
    min range
    max range
    weighted median range
    weighted range spread

Starting heuristic:
    range_spread <= 100       no penalty
    range_spread <= 250       small penalty
    range_spread <= 400       moderate penalty
    range_spread > 400        strong penalty

Exceptions:
    PD weapons
    missiles
    deliberate finishers
    rear/side defensive mounts

Do not penalize PD for being shorter range than primary artillery.

======================================================================
17. DAMAGE ROLE BALANCE
======================================================================

Most conventional loadouts should cover:
    shield pressure
    armor damage
    hull finishing
    PD as appropriate

Profiles define desired proportions as contribution targets rather than literal slot counts.

Example LINE_BRAWLER:
    kinetic pressure: 40%
    armor damage:     35%
    hull finishing:   15%
    PD/support:       10%

======================================================================
18. AI-FRIENDLINESS HEURISTICS
======================================================================

AI-friendliness is an explicit score.

Positive factors:
    coherent weapon ranges
    sustainable flux
    adequate PD
    sensible missile usage
    appropriate speed for engagement range
    role-consistent hullmods
    strong frontal weapon arc coherence

Penalties:
    primary weapon ranges differ excessively
    short-range secondary weapons on artillery profile
    excessive weapon flux
    fragile hull configured for prolonged brawling
    long-range hull given short-range weapons without mobility support
    missile package without enough ammo/endurance
    weapon groups likely to waste burst ammunition
    role conflicts

Officer personality assumption may modify tolerances:
    CAUTIOUS
    STEADY
    AGGRESSIVE
    RECKLESS

Beginner mode should generally assume STEADY or AGGRESSIVE only when appropriate.

======================================================================
19. WEAPON GROUP GENERATION
======================================================================

Suggested automatic grouping:
    Group 1: primary kinetic / main pressure weapons
    Group 2: primary HE / armor damage weapons
    Group 3: missiles / strike package
    Group 4: PD
    Group 5: utility / special

Consider:
    linked vs alternating
    burst weapons
    ammo conservation
    symmetric mounts
    player vs AI assumption

Warn when grouping confidence is low.

======================================================================
20. SCORING SYSTEM
======================================================================

Recommended initial sub-scores, each normalized 0 to 100:
    role_match
    weapon_role_balance
    flux_sustainability
    range_coherence
    survivability
    mobility
    PD_coverage
    missile_utility
    OP_efficiency
    AI_friendliness
    faction_doctrine_match
    fighter_synergy
    hullmod_synergy

Final score is a normalized weighted average based on selected profile and mode.

Example:
    final_score =
        role_match               * w_role
      + flux_sustainability      * w_flux
      + range_coherence          * w_range
      + survivability            * w_survival
      + AI_friendliness          * w_ai
      + faction_doctrine_match   * w_faction
      + OP_efficiency            * w_op
      + ...

======================================================================
21. BEGINNER DEFAULT SCORING PRIORITIES
======================================================================

Beginner mode should strongly favor:
    AI Friendliness
    Flux Safety
    Range Coherence
    Survivability
    Role Match

Example starting weights:
    ai_friendliness          1.50
    flux_sustainability      1.40
    range_coherence          1.40
    survivability            1.30
    role_match               1.40
    weapon_role_balance      1.20
    faction_doctrine_match   1.10
    op_efficiency            1.00
    raw_damage               0.90
    burst                    0.80

All weights must remain configurable.

======================================================================
22. USER FEEDBACK WITHOUT AI
======================================================================

Optional later feature:
Allow users to rate generated builds:
    LIKE
    DISLIKE
    KEEP
    FAILED
    TOO_FLUX_HUNGRY
    TOO_FRAGILE
    TOO_SHORT_RANGE
    TOO_SLOW
    AI_BAD
    PLAYER_ONLY

The application can adjust local preference weights deterministically.

Example:
    TOO_FLUX_HUNGRY:
        increase flux_sustainability preference
        decrease burst preference slightly

Store user preferences separately from source data.

======================================================================
23. VALIDATION
======================================================================

Hard validation must occur before final scoring.

Validate at least:
    hull exists
    weapon exists
    mount exists
    mount size legal
    mount type legal
    built-in weapons preserved
    OP <= available OP
    hullmods legal
    hullmod incompatibilities respected
    required hullmods present
    fighter wing legal
    fighter bay count legal
    vents within limit
    capacitors within limit
    variant identifier valid
    no duplicate invalid entries

Validation result:
    VALID
    INVALID
    VALID_WITH_WARNINGS

Warnings may include:
    high overflux
    severe range mismatch
    low PD
    low armor damage
    poor AI fit
    insufficient missile endurance

======================================================================
24. EXISTING VARIANT ANALYZER
======================================================================

The tool should scan existing variants and produce:
    parsed loadout
    legality
    role guess
    score breakdown
    faction doctrine contribution

Useful outputs:
    "This faction uses Heavy Armor in 63% of cruiser line variants."
    "Average primary weapon range is 910."
    "Missile mounts are left empty in 18% of variants."
    "Typical vents/caps ratio is 1.8:1."

Existing variants may also be ranked under the same scoring system used for generated variants. This supports regression tests asking whether generated variants are at least as coherent as source fits.

======================================================================
25. SOURCE HASHING AND UPDATE DETECTION
======================================================================

Each parsed source entity should store:
    source_mod
    source_path
    source_hash
    source_mod_version

Each generated variant should have metadata such as:
    generated_by
    generator_version
    generated_timestamp
    hull_id
    profile_id
    faction_mode
    source_hull_hash
    source_mod_version

When a mod updates, compare hashes. If hull/weapon dependencies changed, flag generated variants as potentially stale. Do not silently overwrite user-edited generated variants.

======================================================================
26. OUTPUT FORMAT
======================================================================

Primary output:
    legal .variant files

Secondary output:
    human-readable analysis reports

Suggested layout:
    generated/
        compatibility_mod/
            mod_info.json
            data/
                variants/

        reports/
            hulls/
                <hull_id>_profile.json
            weapons/
            variants/
            factions/
                <faction_id>_capability_profile.json
                <faction_id>_doctrine_inference.json
            equipment/
                weapon_profiles.json
                hullmod_profiles.json

        metadata/
            generation_manifest.json

Variant naming convention:
    <hull_id>_<profile>_<generator_tag>

Example:
    dominator_LINE_BRAWLER_svg.variant
    dominator_LINE_ARTILLERY_svg.variant

Avoid name collisions with original variants.

Scan-time reports are generated only below the configured output directory.
Each faction and hull profile records its source mod; shared equipment profile
documents group their entries by source mod. Duplicate entity IDs receive a
source-mod filename prefix so no report overwrites another mod's evidence.

======================================================================
27. COMPATIBILITY MOD GENERATION
======================================================================

The program should be able to generate a standalone Starsector mod:

    Starsector Auto Variants/
        mod_info.json
        data/
            variants/
        README.txt

The compatibility mod must:
    depend only on relevant source mods
    never package source mod assets
    never alter source mod files
    contain only generated data needed by the tool

======================================================================
28. CACHE DESIGN
======================================================================

Large modpacks should not be reparsed from scratch every run.

Cache key should include:
    core game version
    mod id
    mod version
    source hashes
    parser version

If unchanged, load normalized cache. If changed, reparse affected sources only.

Recommended storage:
    SQLite once the data model stabilizes.

======================================================================
29. ERROR HANDLING
======================================================================

The tool must fail gracefully.

Examples:
Missing mod dependency:
    warn and skip unresolved references where safe

Malformed CSV:
    report exact file and row

Malformed JSON/variant:
    report exact file and parse context

Missing weapon referenced by variant:
    mark variant invalid, continue scanning

Unknown custom data:
    preserve raw field if possible
    do not crash

Every run should produce:
    scan_summary
    warnings
    errors
    skipped_entities

======================================================================
30. LOGGING
======================================================================

Logging levels:
    ERROR
    WARNING
    INFO
    DEBUG
    TRACE

Beginner users should see only useful summaries.
Advanced/debug runs may log candidate pruning, score components, rejected combinations, parser decisions, doctrine inference, and cache usage.

Do not spam normal users with per-mount candidate logs.

======================================================================
31. TEST STRATEGY
======================================================================

Testing is required from the beginning.

31.1 Parser tests
-----------------
Test:
    vanilla hull
    modded hull
    vanilla weapon
    modded weapon
    fighter wing
    hullmod
    variant
    faction

31.2 Validation tests
---------------------
Fixtures for:
    correct variant
    oversized weapon
    wrong weapon type
    OP overspend
    incompatible hullmods
    too many fighter wings
    too many vents
    missing hull

31.3 Scoring tests
------------------
Examples:
    Long-range weapon should outscore short-range weapon for artillery profile.
    Efficient kinetic weapon should score well for shield-pressure role.
    High-flux loadout should lose points in Beginner SAFE mode.
    Same loadout may score better in Advanced STRIKE mode.

31.4 Regression tests
---------------------
Maintain known hull/loadout fixtures. When scoring rules change, compare previous rankings and require an explanation for major changes.

31.5 Golden output tests
------------------------
For deterministic seeds, a selected hull + profile + data fixture must produce the same variant, score, and explanation unless a deliberate algorithm change occurs.

======================================================================
32. PERFORMANCE REQUIREMENTS
======================================================================

The program must handle large modpacks.

Avoid:
    Cartesian product fitting
    repeated reparsing
    repeated full-database scans inside inner loops

Use:
    indexing
    caching
    mount grouping
    top-N pruning
    beam search
    memoized scoring components

Target:
    single-hull generation should feel interactive
    full-mod scans may take longer but should be cached

======================================================================
33. SECURITY / SAFETY RULES
======================================================================

The application must:
    default to read-only source scanning
    write only to configured output directories
    create backups before overwriting its own prior output
    never delete source mod files
    never modify game core files
    never execute scripts found inside mods
    treat mod data as untrusted input
    sanitize output paths
    avoid path traversal

======================================================================
34. COMMAND-LINE INTERFACE: INITIAL DESIGN
======================================================================

Possible commands:

    svg scan
    svg list-hulls
    svg analyze-hull <hull_id>
    svg analyze-variant <variant_id>
    svg generate <hull_id> --profile LINE_BRAWLER
    svg generate <hull_id> --mode beginner
    svg generate <hull_id> --mode guided
    svg generate <hull_id> --mode advanced --config profile.json
    svg export <candidate_id>
    svg doctrine <faction_id>
    svg validate <variant_file>
    svg build-mod

======================================================================
35. PHASED IMPLEMENTATION ROADMAP
======================================================================

PHASE 0 - Repository foundation
Deliverables:
    project structure
    configuration loader
    logging
    test framework
    sample fixtures
    AGENTS.md
    README.md

PHASE 1 - Scanner and parser
Deliverables:
    detect Starsector path
    read enabled mods
    parse mod_info
    parse hulls
    parse weapons
    parse fighters
    parse hullmods
    parse variants
    parse factions
    normalized models
    scan report
Success criterion:
    The tool can inspect a real modpack without modifying anything.

PHASE 2 - Database / registry
Deliverables:
    cross-reference resolver
    entity indexes
    cache
    source hashing
    update detection
Success criterion:
    Queries such as "show all medium ballistic weapons", "show all variants for hull X", and "show equipment from faction Y" work reliably.

PHASE 3 - Variant analyzer and validator
Deliverables:
    OP calculator
    mount legality
    fighter legality
    hullmod compatibility
    vent/cap validation
    flux estimate
    range analysis
    existing variant reports
Success criterion:
    Existing variants can be analyzed and explained.

PHASE 4 - Classifiers
Deliverables:
    hull role classifier
    weapon role classifier
    fighter classifier
    hullmod classifier
    faction doctrine inference
Success criterion:
    Hulls receive reasonable multi-role compatibility scores and weapons receive useful role tags.

PHASE 5 - First generator
Deliverables:
    initial profile catalog
    mount grouping
    candidate filtering
    bounded search
    weapon selection
    basic hullmod selection
    vent/cap allocation
    candidate validation
Success criterion:
    Tool generates legal variants for representative vanilla and modded hulls.

PHASE 6 - Scoring and explanation
Deliverables:
    component scores
    profile weights
    candidate ranking
    human-readable explanations
    warning system
Success criterion:
    User can see why Build A outranks Build B.

PHASE 7 - Beginner / Guided / Advanced interfaces
Deliverables:
    Beginner presets
    Guided prompts
    Advanced config schema
    Open Beginner Build in Advanced conversion
Success criterion:
    Same generator serves novice and expert users.

PHASE 8 - Export system
Deliverables:
    .variant writer
    compatibility mod generator
    manifest
    metadata
    collision-safe names
Success criterion:
    Generated builds load in Starsector without touching original mods.

PHASE 9 - Tuning and regression suite
Deliverables:
    representative hull benchmark set
    faction benchmark set
    scoring calibration
    regression tests
    documentation
Success criterion:
    Algorithm changes do not silently degrade known-good results.

======================================================================
36. RECOMMENDED FIRST DEVELOPMENT LANGUAGE
======================================================================

Python is recommended initially because Starsector data is mostly structured text, parsing and experimentation will be faster, SQLite integration is straightforward, CLI development is easy, and unit testing is mature.

Possible later options:
    Rust/C++ for performance-critical components
    Java for tighter Starsector integration

Do not prematurely optimize language choice.

======================================================================
37. CONFIGURATION FORMAT
======================================================================

Recommended:
    TOML for application config
    JSON for exported profile data
    SQLite for normalized database/cache

Example advanced profile JSON:

{
    "profile": "LINE_ARTILLERY",
    "mode": "advanced",
    "control": "AI",
    "faction_mode": "FACTION_PLUS",
    "target_range": 1100,
    "range_min": 900,
    "range_max": 1400,
    "flux_ratio_target": 0.80,
    "weights": {
        "range_coherence": 1.5,
        "flux_sustainability": 1.25,
        "ai_friendliness": 1.35,
        "survivability": 0.9,
        "burst": 0.6
    },
    "required_hullmods": [],
    "forbidden_hullmods": [],
    "required_weapons": [],
    "forbidden_weapons": [],
    "allowed_mods": [],
    "forbidden_mods": []
}

======================================================================
38. IMPORTANT STARSECTOR-SPECIFIC HEURISTICS
======================================================================

Treat these as configurable rules, not immutable truth.

38.1 Range mismatch
AI behavior can be harmed by incompatible weapon ranges. Strongly penalize mismatched primary weapon ranges unless the profile permits mixed-range behavior.

38.2 Armor damage
Per-shot damage matters against armor. Do not evaluate HE weapons using DPS alone.

38.3 Flux
Do not evaluate weapon DPS without considering flux generation. High paper DPS may be a poor AI fit.

38.4 Missiles
Missile value depends on ammo, regeneration, burst, tracking, role, and battle duration. Do not compare missiles using simple sustained DPS alone.

38.5 PD
PD requirements should scale with hull size, vulnerability, role, available mounts, and carrier presence.

38.6 Empty mounts
Allow empty mounts. Filling every mount is not automatically optimal.

38.7 Built-ins
Built-in weapons, hullmods, and systems must influence role classification and scoring.

38.8 Modded special mechanics
Unknown scripted mechanics may not be visible from standard data. Attach UNKNOWN_SCRIPTED_EFFECT when the tool does not understand a scripted weapon/system/hullmod. Beginner mode should warn rather than pretend certainty.

======================================================================
39. EXPLAINABILITY OUTPUT EXAMPLE
======================================================================

    Hull: Dominator
    Profile: LINE_ARTILLERY
    Faction Mode: FACTION_PLUS
    Control: AI

    FINAL SCORE: 88.4

    Role Match:              92
    Flux Sustainability:    84
    Range Coherence:        95
    Survivability:          91
    PD Coverage:            73
    AI Friendliness:        90
    Faction Doctrine Match: 87
    OP Efficiency:          82

    Strengths:
      - Primary weapons share a coherent long-range envelope.
      - Kinetic and HE pressure are well balanced.
      - Flux load is within the selected AI-safe target.
      - Hullmods reinforce the ship's armor and range strengths.

    Weaknesses:
      - PD coverage is only moderate.
      - Mobility remains poor.
      - Missile package is supplemental rather than decisive.

    Why candidate #2 lost:
      - 11% higher burst damage.
      - 24% worse flux sustainability.
      - 310-unit larger primary range spread.
      - Lower AI-friendliness.

======================================================================
40. FUTURE EXTENSIONS
======================================================================

Potential later features:
    Fleet composition optimizer
    Officer skill integration
    S-mod planning
    Progressive S-Mod support
    Starship Legends integration
    Campaign availability analysis
    Weapon inventory constraints
    Combat simulation integration
    Player preference learning
    Save-aware recommendations
    Retrofit template support
    GUI
    Web UI
    AI-assisted explanations
    Cross-faction comparison
    Update-aware mod compatibility reports

None of these should block the initial generator.

======================================================================
41. CODEX IMPLEMENTATION RULES
======================================================================

Codex or any implementation agent should follow these rules:

1. Read this specification before coding.
2. Do not change project scope without documenting the reason.
3. Implement in phases.
4. Add tests with every parser and validator.
5. Treat Starsector and all mods as read-only.
6. Never overwrite source variants.
7. Keep scoring weights configurable.
8. Keep engine logic independent from UI.
9. Prefer transparent heuristics over opaque magic numbers.
10. Document every heuristic and its rationale.
11. Avoid brute-force combinatorial generation.
12. Preserve deterministic generation mode.
13. Log skipped/unknown scripted effects.
14. When uncertain about Starsector file semantics, preserve raw data and flag uncertainty rather than inventing behavior.
15. Do not add AI/API dependencies to the core engine.
16. Do not optimize for one faction at the expense of generality.
17. Build vanilla fixtures first, then add modded regression fixtures.
18. Never require users to modify original game or mod files.
19. Generated output must be removable by deleting the compatibility mod.
20. Before completing a phase, run its regression tests and write a short phase completion report.

======================================================================
42. FIRST CODEX TASK
======================================================================

The first implementation task should be:

    Build Phase 0 and Phase 1 only.

Required output:
    - Repository skeleton.
    - Configuration system.
    - Logging.
    - Test framework.
    - Starsector install path discovery/manual configuration.
    - Enabled-mod discovery.
    - mod_info parsing.
    - Hull parser.
    - Weapon parser.
    - Fighter parser.
    - Hullmod parser.
    - Variant parser.
    - Faction parser.
    - Normalized data models.
    - Read-only scan report.
    - Parser tests using vanilla-style and modded fixtures.

Do NOT implement variant generation in the first task.
The first milestone is successful, accurate, repeatable data ingestion.

======================================================================
43. DEFINITION OF DONE FOR VERSION 0.1
======================================================================

Version 0.1 is complete when:
    [ ] Core and mod data can be scanned safely.
    [ ] Hulls, weapons, fighters, hullmods, factions, and variants normalize.
    [ ] Existing variants can be validated and analyzed.
    [ ] Hulls receive role compatibility scores.
    [ ] Equipment receives useful role classifications.
    [ ] Faction doctrine can be inferred from source data.
    [ ] At least five role profiles exist.
    [ ] Legal candidate variants can be generated.
    [ ] Candidate generation avoids brute-force explosion.
    [ ] Builds receive transparent component scores.
    [ ] Beginner mode generates conservative AI-friendly builds.
    [ ] Guided mode exposes meaningful choices.
    [ ] Advanced mode exposes detailed weights and restrictions.
    [ ] Generated .variant files validate.
    [ ] Output is written only to a separate compatibility mod.
    [ ] Representative vanilla and modded regression tests pass.
    [ ] All generated decisions can be explained in a report.
    [ ] No external AI/API is required.

======================================================================
44. SUMMARY
======================================================================

The project should be built as a deterministic fitting engine first and a user interface second.

Core philosophy:
    Parse accurately.
    Normalize once.
    Infer doctrine from evidence.
    Classify by mechanics.
    Generate with constraints.
    Reject illegal builds.
    Score transparently.
    Explain decisions.
    Export safely.

Keep the following concerns separate:
    DATA
    CLASSIFICATION
    PROFILES
    GENERATION
    VALIDATION
    SCORING
    EXPLANATION
    OUTPUT
    UI

Beginner, Guided, and Advanced modes should all call the same engine. This prevents duplicated logic, keeps the program testable, and allows the tool to grow from a simple offline variant generator into a broader Starsector analysis suite without rewriting its foundation.


======================================================================
45. ADAPTER / PLUGIN LAYER FOR SCRIPTED MECHANICS
======================================================================

The generic engine must not accumulate scattered mod-specific conditionals.

Create a dedicated adapter interface for mechanics that cannot be inferred
reliably from standard Starsector data.

Suggested structure:

    src/
        adapters/
            base/
            vanilla/
            modded/

An adapter may model:

    scripted weapons
    scripted hullmods
    custom ship systems
    custom fighter behavior
    custom ammo regeneration
    range/flux behavior absent from standard data
    faction-specific availability metadata
    special scoring effects

Rules:

1. Adapters are optional extensions to the core engine.
2. The core parser must remain useful without adapters.
3. Never execute a mod's scripts merely to inspect behavior.
4. Unknown behavior remains UNKNOWN_SCRIPTED_EFFECT until explicitly modeled.
5. Adapter-derived facts must record provenance.
6. Adapter logic must be independently testable.
7. Avoid scattered checks such as:

       if mod_id == "some_mod":

   outside the adapter layer.

Evidence acquisition for potentially scripted mechanics proceeds from parsed
static metadata, local source-code static analysis, known API-call
interpretation, mod-local configuration, and bounded variant-use evidence to
adapter models and explicit manual overrides. Scripts are never executed to
obtain that evidence. Any uninterpretable remainder remains
UNKNOWN_SCRIPTED_EFFECT with provenance.

======================================================================
46. MANUAL OVERRIDE LAYER
======================================================================

Provide a user-editable override layer for correcting or supplementing inferred
metadata.

Suggested files:

    config/
        overrides/
            hulls.json
            weapons.json
            fighters.json
            hullmods.json
            factions.json

Overrides may change inferred classifications or scoring metadata but must never
bypass hard Starsector legality.

Precedence:

    hard legality
        >
    explicit user override
        >
    adapter-derived values
        >
    standard-data inference
        >
    unknown/default

Overrides must be:

    schema-validated
    reversible
    source-safe
    provenance-tracked
    visible in analysis reports

======================================================================
47. VERSIONED HEURISTIC REGISTRY
======================================================================

All tunable thresholds and scoring constants must live in a versioned
configuration set rather than being scattered as magic numbers.

Example:

    heuristic_set = "baseline_0.1"

Include:

    range mismatch thresholds
    flux targets
    role weights
    classification thresholds
    PD expectations
    faction-affinity bonuses
    empty-slot behavior
    candidate pruning limits

Every analysis report should record the heuristic-set version used.

Changing a heuristic set should trigger relevant regression tests.

======================================================================
48. CONTINUOUS IMPLEMENTATION WITH CHECKPOINTS
======================================================================

Implementation phases are checkpoints, not mandatory stopping points.

An implementation agent should continue through the requested scope as far as
possible without waiting for confirmation after every phase.

At each completed phase or major milestone:

    run relevant tests
    write/update a completion report
    update ROADMAP.md
    record known limitations
    continue automatically into the next in-scope phase

Pause only when:

    a genuine blocking ambiguity cannot be resolved from project files/specs
    required external input is missing
    continuing would violate source-safety rules
    tests expose a fundamental architectural conflict
    the requested scope has been completed

Checkpoint status values:

    COMPLETE
    COMPLETE_WITH_LIMITATIONS
    BLOCKED

Do not mark a phase COMPLETE while required tests are failing.

======================================================================
49. BUILD INSPECTOR AS AN EARLY USABLE FEATURE
======================================================================

Expose the existing-variant analyzer as a Build Inspector before the automatic
generator is complete.

It should report:

    legality
    OP usage
    weapons by slot
    hullmods
    fighter wings
    vents/capacitors
    estimated weapon flux
    range distribution
    role guess
    AI-friendliness estimate
    faction-doctrine match
    warnings
    unknown scripted effects
    data provenance

This provides useful functionality during early development and becomes a
calibration tool for later generation work.

======================================================================
50. DOCUMENT SET AND OWNERSHIP
======================================================================

Maintain:

    AGENTS.md
        repository and implementation-agent rules

    GUI.md
        desktop GUI behavior and interaction contract

    FORMAL_SPECIFICATION.md
        overarching architecture and generator algorithm

    DATA_SCHEMA.md
        normalized models, enums, provenance, and state contracts

    HEURISTICS.md
        configurable heuristic ownership and interpretation

    TEST_PLAN.md
        canonical fixtures, regression tests, and acceptance gates

    ROADMAP.md
        live phase status and milestone tracking

    README.md
        human-facing project overview

Precedence when duplicated details conflict:

    AGENTS.md safety/process rules
        >
    FORMAL_SPECIFICATION.md architecture/engine rules
        >
    DATA_SCHEMA.md data contract
        >
    GUI.md presentation rules
        >
    HEURISTICS.md tunable defaults
        >
    README.md explanatory material


======================================================================
51. HULLMOD EFFECT ENGINE
======================================================================

Hullmods are first-class modeled entities.

When a hullmod's effect can be reliably determined, normalize it into one or
more typed `HullmodEffect` entries and apply them to produce a
`DerivedShipState`.

Do not score hullmods solely from names/tags.

Effect categories include combat, defense, flux, mobility, logistics,
exploration, salvage, survey, sensor, carrier, conversion, and fleet-support
metadata.

Unknown scripted effects remain UNKNOWN_SCRIPTED_EFFECT.

Fleet-support effects are recorded but not optimized in the current per-ship
scope.

======================================================================
52. CIVILIAN / LOGISTICS PROFILES
======================================================================

Civilian ships are first-class targets.

Initial profiles:

    FREIGHTER
    TANKER
    SALVAGE
    SURVEY
    TROOP_TRANSPORT
    FAST_LOGISTICS
    STEALTH_LOGISTICS
    EXPEDITION_SUPPORT
    GENERAL_SUPPORT

Civilian fits are evaluated using role-appropriate dimensions such as cargo,
fuel, maintenance, burn, endurance, sensor utility, survey utility, and salvage
utility where reliably modeled.

Combat utility may remain a low-weight secondary metric.

Do not attempt whole-fleet optimization in the current scope.

======================================================================
53. REFIT / REPAIR ASSISTANT
======================================================================

Provide a minimal-change optimization path for existing variants.

Objectives include:

    FIX_LEGALITY
    REDUCE_FLUX
    IMPROVE_AI_FIT
    IMPROVE_ROLE_MATCH
    IMPROVE_LOGISTICS
    IMPROVE_SURVEY
    IMPROVE_SALVAGE
    BALANCED_IMPROVEMENT

Users may lock components and define a maximum change budget.

Each change must be explained.

The assistant must not silently substitute a full generated rebuild.

======================================================================
54. LEGALITY RESULT STANDARDIZATION
======================================================================

Use exactly:

    LEGAL
    ILLEGAL
    NOT_DETERMINABLE

Warnings are separate from legality.

Scoring must never convert ILLEGAL or NOT_DETERMINABLE into an acceptable
candidate.

======================================================================
55. SCOPE BOUNDARY: FLEET OPTIMIZATION
======================================================================

The current system optimizes one ship/variant at a time.

Do not make recommendations requiring assumptions about:

    fleet composition
    total fleet cargo
    total fuel
    survey-stack saturation
    salvage-stack saturation
    fleet burn bottlenecks
    desired number of support ships

Known fleet-wide effects may be preserved and displayed as metadata for future
use.

======================================================================
56. RECOMMENDED IMPLEMENTATION ORDER UPDATE
======================================================================

Revised sequence:

    Phase 0  Repository foundation
    Phase 1  Scanner/parsers
    Phase 2  Registry/cache/provenance
    Phase 3  Build Inspector/validator + DerivedShipState foundation
    Phase 4  Hullmod Effect Engine
    Phase 5  Combat/civilian classifiers and doctrine
    Phase 6  Refit/Repair Assistant
    Phase 7  Full variant generator
    Phase 8  Scoring/explanation
    Phase 9  Beginner/Guided/Advanced engine modes
    Phase 10 Export
    Phase 11 Tuning/regression
    Phase 12+ GUI

This order makes the project useful earlier and gives the generator a tested
effect/validation foundation before combinatorial fitting begins.


======================================================================
57. AUTOMATIC FACTION CAPABILITY ANALYSIS
======================================================================

Build useful faction capability profiles from installed mod data alone.

======================================================================
58. FACTION DOCTRINE & RETROFIT KNOWLEDGE PACKS
======================================================================

Optional packs provide curated doctrine, hull archetypes, retrofit templates,
progression guidance, and capability-gap observations.

Packs influence quality/recommendation ranking but never legality.

======================================================================
59. KNOWLEDGE PACK FRESHNESS
======================================================================

Track pack schema version, target mod version, hashes, authorship date/method,
and status: CURRENT / PARTIALLY_STALE / STALE / INCOMPATIBLE.

======================================================================
60. CAPABILITY-GAP RECOMMENDATIONS
======================================================================

Search in order:
1. NATIVE
2. RETROFIT
3. ACQUISITION if permitted

Return a small ranked "I recommend these" shortlist.

======================================================================
61. RECOMMENDATION SCORE VS CONFIDENCE
======================================================================

Keep quality score and evidence confidence separate.

======================================================================
62. RECOMMENDATION DIVERSITY
======================================================================

Avoid redundant top-N results when meaningful alternatives exist.

======================================================================
63. WHY-NOT EXPLAINABILITY
======================================================================

Explain why an eligible hull/retrofit was not shortlisted.

======================================================================
64. DOCTRINE STRICTNESS
======================================================================

Support LOOSE / BALANCED / STRICT for recommendation ranking only.

======================================================================
65. LIGHTWEIGHT CONSTRAINTS
======================================================================

Support foreign hull toggle, hidden/secret toggle, control assumption,
experimental retrofit toggle, doctrine strictness, and optional campaign stage.

======================================================================
66. REVIEW-TO-PACK WORKFLOW
======================================================================

Human or AI-assisted faction reviews may be converted into structured packs,
then validated against current installed mechanics.

======================================================================
67. GUI WORKSPACE MODEL
======================================================================

The desktop application should use separate top-level workspaces:

    SHIPS
    RETROFITS
    FACTION
    DATA / ANALYSIS
    SETTINGS / EXPORT

The Faction workspace is not a whole-fleet planner.

Cross-workspace navigation must preserve shared selected hull/variant/faction
context.

======================================================================
68. UPDATED IMPLEMENTATION ORDER
======================================================================

    Phase 0  Repository foundation
    Phase 1  Scanner/parsers
    Phase 2  Registry/cache/provenance
    Phase 3  Build Inspector/validator
    Phase 4  Hullmod Effect Engine
    Phase 5  Combat/civilian classifiers
    Phase 6  Faction Capability Analyzer
    Phase 7  Faction Knowledge Pack Framework
    Phase 8  Refit/Repair Assistant
    Phase 9  Gap Recommendation Engine
    Phase 10 Recommendation Explainability
    Phase 11 Full Variant Generator
    Phase 12 Scoring/explanation
    Phase 13 Beginner/Guided/Advanced modes
    Phase 14 Export
    Phase 15 Tuning/regression
    Phase 16+ GUI workspaces


======================================================================
69. EQUIPMENT PROVENANCE AND FACTION AFFINITY
======================================================================

Model source mod separately from faction affinity. Support NATIVE, APPROVED, COMMON, UNALIGNED, FOREIGN, RESTRICTED, and UNKNOWN.

======================================================================
70. NON-FACTION CONTENT PACK SUPPORT
======================================================================

Weapon, fighter, hullmod, and utility packs are first-class equipment sources when legal and permitted by access policy.

======================================================================
71. RETROFIT APPLICATION MODES
======================================================================

Support EXACT, STARSECTOR_STYLE, and ADAPTIVE. Adaptive is the recommended default.

======================================================================
72. ADAPTIVE SUBSTITUTION
======================================================================

Score legal replacements using role, range, flux, damage behavior, ammo/endurance, AI friendliness, faction affinity, doctrine fit, OP efficiency, and confidence.

======================================================================
73. HULLMOD SUBSTITUTION
======================================================================

Compare known effects, not names alone. Unknown scripted effects cannot silently stand in for known effects.

======================================================================
74. OPTIONAL AVAILABLE-EQUIPMENT POOL
======================================================================

If no explicit pool is supplied, use installed legal equipment and do not claim current player inventory knowledge.

======================================================================
75. FACTION-PLUS AND UNALIGNED EQUIPMENT
======================================================================

FACTION_PLUS should normally consider NATIVE, APPROVED, COMMON, and UNALIGNED before foreign equipment.
