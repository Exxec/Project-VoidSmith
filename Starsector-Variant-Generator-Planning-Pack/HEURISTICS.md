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
heuristic_set = baseline_0.3
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
```

Do not elevate clearly inferior candidates for diversity.


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
