# HULLMODS_CIVILIAN_AND_REFIT.md
# Hullmod Effects, Civilian Profiles, and Refit Assistant
Version 0.5

This document defines three closely related systems:

1. typed hullmod-effect modeling
2. per-ship civilian/logistics fitting
3. minimal-change refit assistance

Whole-fleet optimization is explicitly deferred.

---

# 1. Why Hullmods Need an Effect Model

A hullmod name or generic tag is not sufficient.

Examples of useful distinctions:

- a combat range bonus
- a flux bonus
- a cargo increase
- a fuel-use reduction
- a survey-cost change
- a salvage benefit
- a speed/burn improvement
- a conversion that changes fitting rules

The engine should ask:

> What known effect does this hullmod apply to this ship?

rather than:

> Does this hullmod have the tag LOGISTICS?

The scoring unit is the resulting `DerivedShipState`.

---

# 2. Effect Sources

Hullmod effects may come from:

### 2.1 Standard parseable data

Highest confidence when the effect is directly represented in data the project
has explicitly learned to parse.

### 2.2 Vanilla adapter

Used where vanilla behavior is reliable but not represented conveniently in the
standard data files.

### 2.3 Mod adapter

Used for a specific mod's custom scripted behavior.

### 2.4 Manual override

Used when the user explicitly supplies a known interpretation.

### 2.5 Unknown

If behavior cannot be established safely:

`UNKNOWN_SCRIPTED_EFFECT`

Do not invent a numeric benefit.

---

# 3. Effect Categories

Initial categories:

## COMBAT
- weapon range
- damage
- rate of fire
- armor interaction
- missile behavior

## DEFENSE
- armor
- hull
- shields
- damage mitigation

## FLUX
- capacity
- dissipation
- weapon flux
- shield flux

## MOBILITY
- speed
- acceleration
- turn rate
- maneuverability

## LOGISTICS
- cargo
- fuel
- crew
- maintenance
- fuel consumption
- burn speed

## EXPLORATION
- expedition endurance
- terrain/travel utility
- survey utility

## SALVAGE
- salvage-related self contribution if reliably modelable

## SURVEY
- survey-related self contribution if reliably modelable

## SENSOR
- sensor strength
- sensor profile

## CARRIER
- fighter-bay and replacement behavior

## CONVERSION
- rule-changing or capacity-conversion behavior

## FLEET_SUPPORT
Record only as metadata in the current scope.

---

# 4. Effect Application

The pipeline should be:

```text
Base hull
    ↓
Apply immutable built-ins
    ↓
Apply selected known hullmod effects
    ↓
Apply known S-mod-specific effects if enabled
    ↓
Apply other explicitly modeled selected effects
    ↓
Create DerivedShipState
    ↓
Validate
    ↓
Score
```

Unknown effects remain attached to the state as uncertainty metadata.

They are not silently converted into zero-confidence numerical bonuses.

### Current deterministic DEFENSE integration

The current vanilla adapter models only armor-rating and hull-HP effects it
can cite and compute against a parsed base hull stat. Those effects may feed
the `baseline_0.2` survivability score. For generation, the TANK profile may
use such an effect as a `Defenses` tie-break after faction preference; it does
not select an effect based only on a name or `uiTags`. For refit,
`BALANCED_IMPROVEMENT` may add an unlocked, verified, applicable DEFENSE
hullmod when it improves the existing legal score. Every proposed candidate
is still passed through hard legality validation.

If the base stat is unavailable, the effect is not used for selection,
scoring, or refit. If multiple effects target the same stat, their individual
contributions remain visible but no combined effective total is inferred until
the stacking rule is documented.

---

# 5. Stacking

Do not assume stacking behavior.

Each effect should record stacking semantics only when known.

Possible states:

```text
ADDITIVE
MULTIPLICATIVE
UNIQUE
CAPPED
CONDITIONAL
UNKNOWN
```

If exact stacking affects legality and cannot be determined:

`NOT_DETERMINABLE`

If it affects only quality scoring:

score known portions and add an uncertainty warning.

---

# 6. Civilian / Logistics Profiles

Civilian ships should not be scored primarily as combat vessels.

Initial profiles:

## FREIGHTER
Primary goals:
- cargo capacity
- low maintenance burden
- acceptable fuel use
- acceptable burn
- survivability sufficient for intended role

Combat score should carry very little weight.

## TANKER
Primary goals:
- fuel capacity
- fuel efficiency
- burn
- maintenance
- survivability

## SALVAGE
Primary goals:
- reliably known salvage utility
- maintenance
- cargo
- endurance
- burn

If salvage effects are scripted/uncertain, expose uncertainty instead of
guessing.

## SURVEY
Primary goals:
- known survey utility
- maintenance
- cargo/fuel support
- burn
- expedition endurance

## TROOP_TRANSPORT
Primary goals:
- crew/marine capacity where represented
- cargo
- burn
- survivability
- operating cost

## FAST_LOGISTICS
Primary goals:
- burn/speed-related campaign mobility
- useful cargo/fuel capacity
- low maintenance
- low sensor burden when relevant

## STEALTH_LOGISTICS
Primary goals:
- sensor profile
- adequate cargo/fuel
- burn
- maintenance

## EXPEDITION_SUPPORT
Balanced exploration-support role:
- cargo
- fuel
- survey/salvage utility where known
- maintenance
- endurance
- burn

## GENERAL_SUPPORT
Fallback civilian profile when a more specific role is not strongly indicated.

---

# 7. Civilian Role Detection

Use multiple role compatibility scores rather than one hard label.

Inputs may include:

- civilian tags
- cargo capacity
- fuel capacity
- crew capacity
- maintenance
- fuel use
- burn
- fighter bays
- built-in logistics hullmods
- built-in survey/salvage effects
- existing variants
- weapon capacity
- ship system where relevant

Example:

```text
Example Hull

FREIGHTER             0.94
FAST_LOGISTICS        0.71
EXPEDITION_SUPPORT    0.60
SALVAGE               0.15
LINE_BRAWLER          0.04
```

Role thresholds belong in the heuristic registry.

---

# 8. Civilian Scoring Dimensions

Possible normalized 0–100 dimensions:

```text
cargo_utility
fuel_utility
crew_utility
maintenance_efficiency
fuel_efficiency
burn_utility
sensor_utility
survey_utility
salvage_utility
endurance
survivability
role_match
op_efficiency
```

Do not force every profile to use every dimension.

---

# 9. Efficiency Metrics

Where meaningful and safely calculable, consider ratios such as:

```text
cargo / monthly_supply_cost
fuel_capacity / monthly_supply_cost
cargo / OP_spent_on_logistics
fuel_capacity / OP_spent_on_logistics
```

These are quality metrics only.

They do not establish legality.

Avoid creating one universal "best logistics ship" formula.

---

# 10. Combat-Civilian Hybrids

Some ships legitimately support mixed roles.

Allow `HYBRID` profiles.

Examples:

```text
ARMORED_FREIGHTER
ESCORT_FREIGHTER
COMBAT_SUPPORT
BATTLE_CARRIER
```

A hybrid profile can reserve minimum utility requirements before spending
remaining OP on combat.

Example:

```text
minimum cargo target satisfied
    ↓
minimum burn target satisfied
    ↓
remaining fitting budget may improve defense/combat
```

Do not automatically transform every armed civilian ship into a combat ship.

---

# 11. What Is Explicitly Out of Scope

Do not optimize:

- total fleet cargo
- total fleet fuel
- fleet-wide salvage stacks
- fleet-wide survey stacks
- fleet burn bottlenecks
- fleet composition
- redundant support hulls
- best number of salvage/survey ships

Fleet-wide effects may be displayed as:

`Fleet-support effect detected; not included in current single-ship optimization.`

This avoids pretending the program knows the user's fleet goals.

---

# 12. Refit / Repair Assistant

The Refit Assistant is a recommended first-class feature.

Its purpose is different from full generation.

Full generator:

> Build a good variant for this role.

Refit Assistant:

> Improve this existing variant while changing as little as possible.

This is useful for:
- vanilla variants
- mod-authored variants
- player-created variants
- generated variants
- civilian fits
- fixing legality after mod updates

---

# 13. Refit Modes

## FIX_LEGALITY
Change only what is needed to reach `LEGAL` where possible.

## REDUCE_FLUX
Prefer changes that reduce excessive weapon flux while preserving role/range.

## IMPROVE_AI_FIT
Reduce range conflicts, bad weapon-group interactions, and severe role
contradictions.

## IMPROVE_ROLE_MATCH
Improve the current selected role without unnecessarily rebuilding everything.

## IMPROVE_LOGISTICS
Improve the selected civilian/logistics role.

## IMPROVE_SURVEY
Prioritize known survey utility.

## IMPROVE_SALVAGE
Prioritize known salvage utility.

## BALANCED_IMPROVEMENT
Seek the best score gain per fitting change.

---

# 14. Minimal-Change Search

Treat change count as a cost.

Example:

```text
change_cost =
    weapon replacement          1.0
    hullmod add/remove          1.5
    fighter replacement        1.0
    vent/cap adjustment         0.25
    weapon-group adjustment     0.25
```

Actual defaults belong in `HEURISTICS.md`.

Candidate refits can then optimize:

```text
quality_gain / change_cost
```

while honoring a maximum-change budget.

---

# 15. Locks

Users must be able to lock:

- weapon slots
- specific weapons
- hullmods
- S-mods
- fighters
- role
- faction mode

Locked items are immutable during refit search.

If a locked item makes legality impossible:

return `NOT_DETERMINABLE` or a clearly explained unsatisfied constraint rather
than silently unlocking it.

---

# 16. Refit Explanation

Every suggested change should state:

```text
Old:
Heavy Blaster

New:
Pulse Laser

Reason:
- reduces weapon flux/sec
- improves range coherence
- preserves Energy mount legality
- current profile favors sustained AI use

Metric changes:
Flux sustainability: 61 -> 78
Range coherence:     72 -> 87
AI friendliness:     65 -> 82
```

Civilian example:

```text
Add:
Expanded Cargo Holds

Reason:
- increases FREIGHTER role utility
- remains within OP budget
- no selected locked equipment displaced
```

---

# 17. No Silent Rebuild

The Refit Assistant must not silently call the full generator and present the
result as a "repair."

If the best solution exceeds the user's change budget:

report:

`A larger rebuild may improve the fit further.`

and optionally offer the full generator separately.

---

# 18. GUI Implications

The Build Inspector should eventually expose:

- Analyze
- Suggest Fix
- Improve Build
- Lock Selection
- Compare Before/After

For civilian profiles, the primary metrics panel should switch from combat-heavy
metrics to logistics/exploration metrics.

Combat metrics remain available in a secondary panel.

---

# 19. Tests

Required tests include:

- known flat hullmod effect applies correctly
- known multiplicative effect applies correctly
- unknown scripted effect remains unknown
- manual override takes precedence over inference
- hard legality cannot be overridden
- freighter profile prefers cargo/logistics improvements
- combat profile does not incorrectly reward cargo expansion
- Refit Assistant respects locked slots
- Refit Assistant respects maximum-change count
- legality fix is prioritized in FIX_LEGALITY mode
- minimal-change solution beats larger equivalent rebuild
