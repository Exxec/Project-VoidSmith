# TEST_PLAN.md
# Starsector Variant Generator Test Plan
Version 0.5

## 1. Goals

Tests protect:
- parser accuracy
- source safety
- legality
- deterministic behavior
- hullmod-effect application
- civilian/logistics role scoring
- Refit Assistant constraints
- heuristic regressions
- GUI/backend separation

---

## 2. Canonical Vanilla Hull Benchmarks

Initial benchmark hulls:

- Lasher: frigate / ballistic
- Hammerhead: destroyer / mixed combat fitting
- Dominator: cruiser / armor / ballistic + missile
- Heron: carrier
- Onslaught: capital / many mounts / built-ins

Add civilian/logistics fixtures representing:
- freighter
- tanker
- salvage/support
- survey/support

Use real game data only when licensing/local-test setup permits; otherwise keep
minimal synthetic fixtures matching parser format.

---

## 3. Parser Tests

Include:
- valid hull
- valid weapon
- valid fighter wing
- valid hullmod
- valid variant
- valid faction
- malformed CSV
- malformed JSON
- missing referenced entity
- unknown extra fields
- built-in hullmods
- civilian/logistics fields
- hidden/restricted equipment metadata

---

## 4. Legality Tests

Expected results must be one of:

```text
LEGAL
ILLEGAL
NOT_DETERMINABLE
```

Fixtures:
- legal variant
- wrong weapon size
- wrong mount type
- OP overspend
- illegal hullmod combination
- too many fighter wings
- too many vents/capacitors
- missing hull
- immutable built-in replacement attempt
- legality depending on unknown scripted behavior

Warnings must not alter the legality result.

---

## 5. Hullmod Effect Tests

Required:
- flat effect
- percentage effect
- multiplicative effect
- conditional effect represented without false certainty
- unknown scripted effect
- adapter-modeled effect
- manual override
- precedence ordering
- unknown fleet-support effect recorded but not optimized

Verify `DerivedShipState` after every effect application.

---

## 6. Civilian Profile Tests

Examples:
- FREIGHTER prefers meaningful cargo utility over irrelevant combat DPS
- TANKER prefers fuel utility
- SALVAGE only scores known salvage effects
- SURVEY only scores known survey effects
- combat hull is not accidentally classified as freighter from small cargo value
- logistics hull may receive multiple compatible civilian roles
- civilian profile can still value survivability without becoming a combat build

---

## 7. Combat Scoring Regression Tests

Examples:
- artillery favors coherent long-range primaries
- Beginner penalizes severe overflux
- Advanced strike may tolerate more overflux
- PD does not poison primary range-coherence score
- HE armor-break score considers per-shot damage
- empty slots may improve a fit when OP/flux constraints justify them

---

## 8. Faction Filtering Tests

Verify:
- Strict Faction never silently broadens
- Faction+ admits only approved fallback equipment
- Unrestricted admits any installed legal equipment
- hidden equipment is excluded by default
- Show Hidden exposes but marks restricted equipment

---

## 9. Refit Assistant Tests

Required:
- locks are honored
- maximum change budget is honored
- FIX_LEGALITY minimizes unnecessary changes
- REDUCE_FLUX preserves locked range-critical weapons
- IMPROVE_LOGISTICS uses civilian metrics
- equal-quality alternatives prefer lower change cost
- suggestion report explains every modification
- assistant never silently invokes a full rebuild

---

## 10. Golden Outputs

For deterministic fixtures, persist:
- candidate selection
- legality result
- score components
- warnings
- generated variant
- applied heuristic set
- adapters/overrides used

Document intentional golden-output changes.

---

## 11. Source Safety

Attempt writes to:
- Starsector core
- source mod folder
- original variant path

All must be rejected.

Writes to approved generated-output roots must succeed.

---

## 12. GUI Contract Tests

Where practical:
- clicking a mount box on the canvas and updating fitting state stay
  consistent (the separate Callout/List views this originally described were
  removed; the canvas is the single fitting-state surface now)
- changing a weapon updates OP and legality
- illegal choices do not appear normally
- missing sprite does not invalidate a legal fit
- civilian profile switches primary metrics appropriately
- Build Inspector can display Refit suggestions
- long-running analysis stays off the main UI thread


## 13. Faction Capability Tests

- strong ballistic faction recognized
- single excellent hull prevents false gap where appropriate
- several weak hulls do not falsely create strong coverage
- unknown scripts reduce confidence
- useful output exists with no pack

## 14. Knowledge Pack Tests

- valid pack loads
- bad schema rejected
- stale version lowers confidence
- changed hashes flag staleness
- pack cannot override legality
- pack provenance visible
- disabling pack leaves automatic analysis functional

## 15. Recommendation Tests

- Native / Retrofit / Acquisition remain distinct
- foreign candidates disappear when disabled
- hidden/secret constraints work
- AI/Player assumptions can change ranking
- STRICT doctrine favors thematic/native options
- LOOSE allows mechanically superior foreign options
- score and confidence remain separate

## 16. Diversity Tests

- deterministic `HullFeatureVector` values are produced from normalized hull
  data and retain per-feature evidence/missingness
- feature extraction covers hull size, DP/OP, defense/shield/flux/mobility,
  mounts (size/type/arcs), missiles, bays, built-ins, known ship-system
  categories, logistics statistics, and aggregate existing-variant evidence
- each initial archetype can be supported by positive structural fixtures;
  multi-role hulls may receive multiple non-zero archetype compatibilities
- missing or unknown scripted evidence does not invent favorable archetypes and
  reduces confidence only through documented evidence rules
- existing variants affect faction usage statistics only; a contrary or sparse
  variant set cannot override structural mechanics or legality
- redundant mechanically similar candidates are reduced within each individual
  Native, Retrofit, and Acquisition leg
- competitive candidates differing in functional role or mechanical archetype
  are preferred where score tradeoff is within the configured tolerance
- materially lower-scoring candidates are not promoted merely for diversity
- ties and shortlist order are deterministic
- knowledge-pack/manual enrichment follows normal precedence and remains
  visible, while never changing raw evidence or legality
- Why-Not reports inferred archetype scores/evidence and whether selection or
  exclusion resulted from diversity, score, or eligibility

## 17. Why-Not Tests

- eligible non-shortlisted hull explains penalties
- ineligible hull explains exclusion
- low-confidence candidate explains uncertainty
- role-overlap candidate explains weak capability gain


## 18. Non-Faction Equipment Tests

- factionless source produces UNALIGNED equipment
- source mod does not imply faction ownership
- Faction+ can admit legal unaligned gear
- Strict Faction rejects unapproved unaligned gear
- Unrestricted admits legal non-restricted unaligned gear
- hidden/secret policy still applies

## 19. Retrofit Application Mode Tests

- Exact never substitutes
- Starsector-style selects close template substitutes
- Adaptive can prefer a better semantic match
- range/flux/AI fit affect Adaptive ranking
- unknown scripted hullmods are not treated as known equivalents
- deterministic inputs produce deterministic substitutions

## 20. Gap Recommendation Engine Tests

See `GAP_RECOMMENDATION_ENGINE.md` (project-authored) section 16 for the
full deterministic test list.

## 21. Calibration Tests

- changed source hashes report `STALE`, never a heuristic mismatch
- missing or unmodeled observation types report `UNSUPPORTED`
- hard, soft, negative, and acceptable-set expectations preserve their stated
  semantics
- direct local evaluation resolves only a unique `hull:<source_mod>:<id>` key
- a globally duplicated hull ID never selects a cross-mod entity to create an
  observation
- calibration evaluation writes reports only to a caller-selected output path
  and never changes labels, heuristics, Starsector, or source mods

## 22. Fleet Support Advisor Tests

- player-declared duplicate counts alter composition-trait prevalence but never
  become recommended quantities
- sensor-profile aliases normalize into `Hull.sensor_profile`; analysis never
  reads source spelling from `raw`
- phase/sensor/base-burn/mobility composition evidence is separately reported
  from doctrine cohesion and unavailable evidence is ignored
- phase-compatible logistics candidates can receive composition synergy without
  fabricating a `PHASE_SUPPORT` gap
- support-purpose labels derive only from existing capability dimensions
- Why-Not exposes the backend score-component decomposition without reranking
- support-fit generation first revalidates a current shortlist candidate, then
  returns the normal generator's concrete legality result without writing files
- logistics-only recommendations decline support-fit generation until an
  explicit logistics fitting profile is modeled

## 23. Scenario / Mission Advisor Tests

- generic scenario templates contain only generic pressures and existing
  capability dimensions, never mission-name behavior
- user-declared scenario targets reject unknown dimensions and out-of-range
  values
- assessments report mechanical alignment and evidence confidence separately
- unknown fleet capability remains `UNKNOWN`, not weak or favorable
- scenario deficiencies feed the existing locked-selection addition path while
  selected hulls remain excluded
- scenario output explicitly disclaims simulation and victory prediction
