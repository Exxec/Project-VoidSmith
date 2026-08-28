# HEURISTICS.md
# Versioned Heuristic Registry Contract
Version 0.5

All tunable scoring/classification/search constants belong here or in the
machine-readable heuristic registry.

No unexplained magic numbers should be scattered through implementation code.

---

## 1. Registry Requirements

Every heuristic entry should have:

- stable key
- default value
- units
- rationale
- owner subsystem
- version introduced
- tests where practical

Every run/report should record the active heuristic-set identifier.

---

## 2. Baseline Registry

Suggested initial registry:

```text
heuristic_set = baseline_0.7
```

### Range

```text
range.no_penalty_spread = 100
range.small_penalty_spread = 250
range.moderate_penalty_spread = 400
```

### Flux

```text
flux.safe_target_ratio = 0.90
flux.balanced_target_ratio = 0.75
flux.aggressive_target_ratio = 0.55
```

### Candidate generation

```text
generation.top_n_per_mount_group = 8
generation.default_candidate_limit = 25
generation.allow_empty_mounts = true
```

### Beginner combat

```text
beginner.ai_friendliness_weight = 1.50
beginner.flux_sustainability_weight = 1.40
beginner.range_coherence_weight = 1.40
beginner.survivability_weight = 1.30
beginner.role_match_weight = 1.40
```

### Artillery

```text
artillery.range_weight = 1.50
artillery.sustained_weight = 1.30
artillery.flux_safety_weight = 1.25
artillery.ai_friendliness_weight = 1.35
artillery.range_coherence_weight = 1.50
```

### Brawler

```text
brawler.survivability_weight = 1.40
brawler.kinetic_weight = 1.25
brawler.he_weight = 1.25
brawler.sustained_weight = 1.20
```

---

## 3. Civilian Baseline Profiles

These are starting preferences, not claims of objective optimality.

### FREIGHTER

```text
civilian.freighter.cargo_utility = 1.50
civilian.freighter.maintenance_efficiency = 1.30
civilian.freighter.burn_utility = 1.20
civilian.freighter.fuel_efficiency = 1.00
civilian.freighter.survivability = 0.60
civilian.freighter.combat_utility = 0.10
```

### TANKER

```text
civilian.tanker.fuel_utility = 1.50
civilian.tanker.fuel_efficiency = 1.25
civilian.tanker.burn_utility = 1.20
civilian.tanker.maintenance_efficiency = 1.20
civilian.tanker.survivability = 0.60
civilian.tanker.combat_utility = 0.10
```

### SALVAGE

```text
civilian.salvage.salvage_utility = 1.50
civilian.salvage.maintenance_efficiency = 1.20
civilian.salvage.cargo_utility = 1.00
civilian.salvage.burn_utility = 1.00
civilian.salvage.survivability = 0.50
civilian.salvage.combat_utility = 0.05
```

### SURVEY

```text
civilian.survey.survey_utility = 1.50
civilian.survey.maintenance_efficiency = 1.20
civilian.survey.endurance = 1.15
civilian.survey.cargo_utility = 0.90
civilian.survey.fuel_utility = 0.90
civilian.survey.combat_utility = 0.05
```

---

## 4. Refit Assistant

Initial change costs:

```text
refit.change.weapon = 1.00
refit.change.hullmod = 1.50
refit.change.fighter = 1.00
refit.change.vent = 0.25
refit.change.capacitor = 0.25
refit.change.weapon_group = 0.25
```

Suggested default budgets:

```text
refit.beginner.max_total_changes = 4
refit.guided.max_total_changes = 8
refit.advanced.max_total_changes = configurable
```

The Refit Assistant should maximize improvement subject to:
- legality
- locks
- faction restrictions
- change budget

---

## 5. Hullmod Interpretation Rules

### Known effects
Apply to `DerivedShipState`.

### Unknown scripted effects
Do not assign invented bonuses.

### Fleet-support effects
Record them, but do not include them in current per-ship optimization unless the
effect has a clearly defined self component.

### Empty mounts
Empty mounts are not automatically bad.

### Civilian ships
Do not apply combat-heavy scoring defaults to civilian profiles.

---

## 6. Versioning

Any released behavior-changing update should:
- increment heuristic-set identifier
- run regression tests
- record ranking changes
- preserve old sets when practical for comparison


## 7. Faction Capability Thresholds

```text
faction_capability.strong_min = 0.75
faction_capability.adequate_min = 0.45
faction_capability.weak_min = 0.20
```

A gap must consider coverage and evidence, not only a scalar.

## 8. Doctrine Influence

```text
knowledge.doctrine_weight.loose = 0.25
knowledge.doctrine_weight.balanced = 0.60
knowledge.doctrine_weight.strict = 1.00
```

Quality only, never legality.

## 9. Native / Retrofit / Acquisition Thresholds

```text
recommendation.native_good_enough = 0.80
recommendation.retrofit_good_enough = 0.75
recommendation.foreign_advantage_required_strict = 0.15
```

## 10. Recommendation Confidence

Suggested components:
- direct mechanics: high
- existing variants: high-medium
- adapter modeled: high
- current pack: medium-high
- stale pack: reduced
- unknown scripted behavior: penalty

## 11. Recommendation Diversity

```text
recommendation.default_results = 3
recommendation.default_max_results = 5
recommendation.diversity_similarity_penalty = 0.15
recommendation.diversity_material_score_tolerance = 0.10
recommendation.diversity_role_difference_weight = 0.55
recommendation.diversity_archetype_difference_weight = 0.45
recommendation.diversity_min_archetype_compatibility = 0.20
```

Within each recommendation leg, first create the deterministic score-ranked
pool. Diversity selection may then prefer candidates with different functional
roles and inferred mechanical archetypes. It must not promote a candidate
whose recommendation score is more than
`recommendation.diversity_material_score_tolerance` below the best otherwise
eligible alternative merely to increase variety. Ties remain hull-id ordered.

Role and archetype distance are separate signals: role describes the gap-facing
function, while archetype describes the mechanically evidenced way a hull
performs it. A multi-role or multi-archetype hull therefore is not forced into
one exclusive family.

## 12. Build Archetypes and Variant Diversity

```text
build_archetype.viable_min_compatibility = 0.35
build_archetype.experimental_min_compatibility = 0.20
build_archetype.unknown_feature_confidence_penalty = 0.05
variant_diversity.near_duplicate_similarity = 0.85
knowledge.build_archetype_preference_weight = 0.10
scoring.pd_coverage_weight = 0.10
scoring.missile_pressure_weight = 0.10
```

Generation evaluates each viable `Hull + BuildArchetype` independently.
Compatibility below the viable threshold but at or above the experimental
threshold is retained only as `EXPERIMENTAL`. Within one hull, candidates that
are near-identical across build role/style, range, weapon distribution,
hullmods, flux and survivability posture are collapsed deterministically.
The global candidate cap is allocated round-robin: every viable build baseline
is considered before a second bounded alternate of any build.
An optional, freshness-adjusted knowledge-pack build preference may make a
small advisory ranking adjustment only after mechanical inference has produced
the path; it cannot create, legalize, or conceal a build archetype.

`baseline_0.5` also scores directly documented PD-tag coverage for
`PD_ESCORT` and documented missile-mount coverage for `MISSILE_SUPPORT`.
Neither component is inferred for other builds or used by legality.

`baseline_0.6` additionally applies a bounded, quality-only retrofit
disruption penalty. It normalizes a real Refit Assistant change-cost total
against `retrofit_disruption_reference_cost = 8.0`, then applies at most
`retrofit_disruption_penalty_weight = 0.20` to the retrofit recommendation
score. This does not affect legality, raw capability, or the reported
quality delta.

`baseline_0.7` adds `knowledge_progression_preference_weight = 0.05`: a
freshness-adjusted advisory adjustment for a hull named by the explicitly
user-selected pack progression tier. It applies only after mechanical
Hull + BuildArchetype eligibility, cannot filter candidates, and never affects
legality, capability evidence, or confidence outside the advisory guidance.

`baseline_0.8` adds `flux_hullmod_adjustment_enabled = 1.0`, an opt-in gate
flag (present only in this and later heuristic sets; the shipped default
`heuristic_set` stays `baseline_0.7`, so a caller must explicitly request
`baseline_0.8` to get this behavior). When present, `scoring/
candidate_score.py`'s `flux_sustainability` component sources a candidate's
`flux_dissipation`/`shield_upkeep` from `analysis/flux_stats.py::
compute_derived_flux_stats` -- the verified `fluxdistributor`/
`safetyoverrides`/`stabilizedshieldemitter` hullmod effects (`adapters/
vanilla/__init__.py::FLUX_HULLMOD_EFFECTS`) -- instead of the hull's raw,
unmodified base stats, so a candidate that installs one of those hullmods
scores its real, hullmod-adjusted flux sustainability. When 2+ verified
hullmods collide on the same stat (e.g. `fluxdistributor` and
`safetyoverrides` both targeting `flux_dissipation`), `compute_derived_flux_
stats` deliberately reports no combined effective value -- how vanilla
combines a flat additive bonus with a multiplicative factor is undocumented,
so no value is fabricated. Scoring falls back to the stat's raw base value in
that case and records the ambiguity in the score explanation instead. Absent
under `baseline_0.7` and every earlier registry entry, so their
`flux_sustainability` output is completely unaffected.

`baseline_0.9` adds `combat_hullmod_adjustment_enabled = 1.0`, an opt-in gate
flag (present only in this and later heuristic sets; the shipped default
`heuristic_set` stays `baseline_0.7`, so a caller must explicitly request
`baseline_0.9` to get this behavior). When present, `scoring/
candidate_score.py`'s `range_coherence` and `role_match` components source
each equipped BALLISTIC/ENERGY weapon's `range` from `analysis/
weapon_range_stats.py::compute_derived_combat_stats` -- the verified
`targetingunit`/`dedicated_targeting_core` hullmod effects (`adapters/
vanilla/__init__.py::COMBAT_HULLMOD_EFFECTS`) -- instead of that weapon's
raw, unmodified base range, so a candidate that installs one of those
hullmods scores its real, hullmod-adjusted range spread and range-threshold
role match. When 2+ verified hullmods collide on the same mount (installing
both `targetingunit` and `dedicated_targeting_core`, mutually illegal in
vanilla but not enforced by this adapter or its consumer),
`compute_derived_combat_stats` deliberately reports no combined effective
value -- how vanilla would combine two percent range bonuses on the same
weapon is undocumented, so no value is fabricated. Scoring falls back to that
weapon's raw base range in that case and records the ambiguity in the score
explanation instead. Absent under `baseline_0.8` and every earlier registry
entry, so their `range_coherence` and `role_match` output is completely
unaffected.

`baseline_0.10` adds `vent_hullmod_adjustment_enabled = 1.0`, an opt-in gate
flag (present only in this heuristic set; the shipped default `heuristic_set`
stays `baseline_0.7`, so a caller must explicitly request `baseline_0.10` to
get this behavior). When present, `generation/vent_cap.py::
allocate_vents_and_capacitors` sources the candidate hull's
`flux_dissipation`/`shield_upkeep` from `analysis/flux_stats.py::
compute_derived_flux_stats` -- the verified `fluxdistributor`/
`safetyoverrides`/`stabilizedshieldemitter` hullmod effects (`adapters/
vanilla/__init__.py::FLUX_HULLMOD_EFFECTS`), evaluated against the
candidate's own already-finalized selected hullmod list (`generation/
candidate.py::_build_candidate`'s `hullmod_selection.hullmod_ids`, the same
list that becomes `Variant.hullmods`) -- instead of the hull's raw,
unmodified base stats, so a candidate that installs one of those hullmods
computes its real, hullmod-adjusted vent/capacitor need toward the same
flux-sustainability target. When 2+ verified hullmods collide on the same
stat (e.g. `fluxdistributor` and `safetyoverrides` both targeting
`flux_dissipation`), `compute_derived_flux_stats` deliberately reports no
combined effective value -- how vanilla combines a flat additive bonus with
a multiplicative factor is undocumented, so no value is fabricated.
Allocation falls back to the stat's raw base value in that case and records
the ambiguity in the allocation note instead -- the same fallback discipline
`baseline_0.8` already established for scoring's own `flux_sustainability`
component. Absent under `baseline_0.9` and every earlier registry entry, so
their vent/capacitor allocation is completely unaffected. Live-verified
against a real Hammerhead hull (`flux_dissipation=250.0`, `DESTROYER`) with a
fixed 4-weapon energy loadout (520.4 sustained flux/s): 15 vents under
`baseline_0.9` regardless of `fluxdistributor`, vs. 15 vents without and 9
vents with `fluxdistributor` under `baseline_0.10` -- matching
`compute_derived_flux_stats`'s independently reported `effective_
flux_dissipation` of 310.0 (`250.0` base `+ 60.0` documented `DESTROYER`
bonus) exactly.

## 13. Reserved Recommendation Dimensions

The following names are reserved for a future heuristic-set revision once the
corresponding evidence contracts are implemented. They are not current score
inputs and must not be emulated with name/source-mod guesses.

```text
capability_gap.dimension_weight.<dimension>
capability_gap.minimum_confidence
capability_gap.minimum_confidence
role_distortion.doctrine_distance_weight
retrofit_disruption.locked_component_penalty
retrofit_disruption.max_change_budget_weight
```

Future values must be introduced in a new named heuristic set together with
their evidence source, rationale, regression coverage, and Why-Not output.

## 11.1 Mechanical Archetype Inference

```text
archetype.feature_normalization_version = mechanical_features_0.1
archetype.variant_usage_evidence_weight = 0.15
archetype.unknown_feature_confidence_penalty = 0.05
```

`HullFeatureVector` values must be derived deterministically from normalized
scanned data, with each feature accompanied by availability/evidence state.
Missing or scripted-unknown facts must not be imputed as favorable mechanics.
Existing variants are statistical evidence of faction usage patterns only;
their bounded influence may affect archetype confidence or compatibility, but
cannot make a hull belong to an archetype without structural support.

The following initial archetypes are non-exclusive compatibility targets:

```text
ARMOR_BRAWLER, SHIELD_BRAWLER, LINE_SHIP, ARTILLERY, SKIRMISHER, STRIKER,
MISSILE_SUPPORT, PD_ESCORT, LIGHT_CARRIER, HEAVY_CARRIER, BATTLECARRIER,
COMBAT_FREIGHTER, FREIGHTER, TANKER, SALVAGE_SUPPORT, SURVEY_SUPPORT
```

Knowledge packs and manual overrides may enrich or supersede inferred
non-legality archetype metadata under normal precedence rules. They may not
change the feature vector's raw evidence, hard legality, or source-mod-based
UNALIGNED classification.


## 12. Equipment Affinity Preference

Suggested FACTION_PLUS preference values:

```text
NATIVE 1.00
APPROVED 0.90
COMMON 0.75
UNALIGNED 0.70
FOREIGN 0.40
```

Quality ranking only, never legality.

## 13. Adaptive Substitution

Suggested starting weights:

```text
role_match 1.50
range_match 1.20
flux_match 1.20
damage_behavior_match 1.20
AI_friendliness 1.10
OP_efficiency 0.90
affinity 0.75
confidence 0.75
```

## 14. Gap Recommendation Thresholds

See `GAP_RECOMMENDATION_ENGINE.md` (project-authored). Implemented as
`core/heuristics.py`'s `gap_strong_threshold`/`gap_adequate_threshold`/
`gap_weak_threshold`/`gap_recommendation_count`, first-pass values
pending a benchmark suite.

## 15. Fleet Support Composition Synergy

`baseline_0.14` adds the following advisory-only values:

```text
fleet_support_composition_synergy_weight = 0.20
fleet_support_access_affinity_weight = 0.05
```

Composition synergy averages only available direct/static phase, normalized
sensor-profile, base-burn, and mobility-character matches. It is deliberately
separate from support-need coverage, doctrine cohesion, and static friction.
It can improve the ranking of an already eligible individual addition, but
cannot create a candidate, a need, a legality result, or a fleet-quantity
recommendation. Access affinity remains a small quality preference only after
the hard access-policy gate has admitted a candidate.
