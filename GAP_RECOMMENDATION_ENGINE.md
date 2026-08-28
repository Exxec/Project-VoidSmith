# GAP_RECOMMENDATION_ENGINE.md
# Gap Recommendation Engine: Algorithm and Data Model
Project-authored, Version 1.0 -- extends Planning Pack v0.5

This document is not part of the synced planning pack (it is not
overwritten by `Starsector-Variant-Generator-Planning-Pack/` refreshes).
It specifies the *algorithm* behind `FACTION_KNOWLEDGE_PACKS.md` sections
4-8 ("Recommendation Classes" / "I Recommend These" / "Diversity" / "Why
Not?"), which name the shape of the feature but not its mechanics. Small
cross-references to this document were added to `DATA_SCHEMA.md`,
`HEURISTICS.md`, `TEST_PLAN.md`, and root `ROADMAP.md`.

## 1. Relationship to other documents

- `FACTION_KNOWLEDGE_PACKS.md` sections 1-2, 9-17: scope, doctrine
  strictness, knowledge pack structure, GUI workspace. Unchanged by this
  document.
- `EQUIPMENT_ACCESS_AND_AUTOFIT.md`: the equipment-affinity and
  `EXACT`/`STARSECTOR_STYLE`/`ADAPTIVE` substitution model that section 4
  ("Then ask whether native ships can be retrofitted") and section 5
  ("Only then search acquisitions") below depend on.
- Root `ROADMAP.md` Phase 10 (Gap Recommendation Engine): tracks
  implementation status against this spec.

## 2. Implementation status (read this before the rest)

This document specifies the full target design. Only a fraction of it is
implemented; the rest lists real, currently-missing prerequisites, not
just unstarted work:

| Section | Status |
|---|---|
| 3 (Capability vs role) | Partial -- a normalized 18-dimension `CapabilityVector` now aggregates mechanical, existing-variant weapon, carrier, and civilian evidence, while recommendation mappings remain limited to unambiguous current role counterparts. |
| 4 (Define the gap) | **Implemented** -- `analysis/gap_recommendation.py::detect_capability_gaps`; `baseline_0.5+` may augment matching role coverage with available vector evidence and retains vector confidence/evidence on the gap. |
| 6 (Native search) | **Implemented** -- `analysis/gap_recommendation.py::recommend_native_solutions` |
| 5 (Adaptive retrofit search) | **Implemented, narrower than the full design** -- `analysis/gap_recommendation.py::recommend_retrofit_solutions`. Reuses the native leg's own top-ranked structurally-capable hulls and `generation/refit.py::improve_quality`'s `IMPROVE_ROLE_MATCH` mode to find real, under-realized existing variants. Inherits `IMPROVE_ROLE_MATCH`'s own limitation: its greedy single-step search can't fix `role_match`'s all-or-nothing formula once more than one mounted weapon already violates it, so real multi-weapon combat variants rarely retrofit today (confirmed live against real Pirates data) -- single/near-single-weapon variants work reliably. |
| 7 (Acquisition search) | **Implemented** -- `analysis/gap_recommendation.py::recommend_acquisition_solutions`, using `analysis/equipment_affinity.py::classify_equipment_affinity` (now extended to `entity_kind="hulls"`) and the existing `affinity_preference_<tier>` heuristic table. |
| 8 (Retrofit cost) | Partially implemented -- `baseline_0.6` records a normalized real change-cost disruption and applies a bounded quality-only penalty to build-aware retrofit score. |
| 9 (Role distortion) | Partially implemented -- build compatibility supplies an explicit structural role-distortion metric for build-aware retrofit paths. Doctrine-distance distortion remains unavailable without supported pack evidence. |
| 10 (Recommendation score) | Partial: all legs rank `Hull + BuildArchetype` combinations where supported. Native stays raw structural/build score; acquisition includes affinity; retrofit includes real quality and bounded disruption. A single cross-leg utility score is deliberately not fabricated. |
| 11 (Confidence) | Partial: known-hull coverage, available vector evidence, build inference confidence, and access-pack confidence propagate conservatively into build-aware recommendations. Unknown scripted effects remain unavailable rather than numerically invented. |
| 12 (Knowledge-pack doctrine bias) | Not implemented -- requires Phase 7 (Faction Knowledge Pack Framework), which doesn't exist yet |
| 13 (Why Not) | Implemented across current legs; diversity decisions must additionally preserve and report the mechanical-profile evidence and score tradeoff that led to selection or exclusion. |
| 14 (GUI) | Not implemented -- no GUI exists yet at all (`GUI.md` section 50's Readiness Gate) |
| 15 (No Recommendation) | **Implemented, now to full-maturity's own definition** -- `unaddressed_gaps` (no native solution, unchanged) plus a new `fully_unaddressed_gaps` (no solution across native, retrofit, AND acquisition, exactly this section's own "full maturity" framing). |
| 18 (Scenario-Aware Recommendations, Phase 31) | **Implemented as a separate, additive `INFERRED_SCENARIO_OPTION` category** -- `recommend_scenario_solutions`/`explain_scenario_candidate` layer a heuristic scenario-fit score on top of the already-ranked Native/Retrofit/Acquisition legs; never wired into `recommend_gap_solutions` itself, never affects those legs' own ranking or confidence. |

**Do not read "implemented" sections as the final target shape** -- they
are the parts of this design buildable today without guessing at
prerequisites that don't exist. Sections 8 (partially), 9, 12, 13
(partially), and 14 describe real future work, most now gated on Phase 7
(knowledge packs) rather than Phases 8/9, which have landed.

## 3. Capability vs role

A role (`LINE_BRAWLER`, `LINE_ARTILLERY`, `PD_ESCORT`, `CARRIER`, ...) is
a *profile* -- a generation/quality intent (`profiles/catalog.py`). A
capability is more granular (`FACTION_KNOWLEDGE_PACKS.md` section 3 names
15: armor, shields, ballistic, energy, missile, carrier, phase, mobility,
long range, brawling, skirmishing, PD, logistics, salvage, survey).

This project currently computes only 5 of those, as non-exclusive
0.0-1.0 scores (`analysis/classification.py::classify_hull`):
`CARRIER`, `BATTLE_CARRIER`, `MISSILE_SUPPORT`, `LINE_ARTILLERY`,
`LINE_BRAWLER`. The Gap Recommendation Engine v1 treats these 5 as the
capability set. Extending toward the full 15-dimension taxonomy needs new
classifiers with the same real-evidence discipline `classify_hull`
already follows (see `docs/ROADMAP.md`'s civilian-classification section
for an example of a taxonomy dimension -- cargo/fuel-ratio thresholds --
that was tried and rejected for lacking real support), not added here on
weak grounds.

## 4. Define the gap

### 4.1 Richer capability-vector direction

The current engine uses five directly evidenced structural axes. The next
compatible extension is a non-exclusive `CapabilityVector`: armor, shields,
ballistic, energy, missile, carrier, mobility, long-range, brawling,
skirmishing, PD, logistics, salvage, and survey dimensions, each retaining a
score, confidence, availability state, and supporting evidence. A missing or
scripted-unknown dimension remains unavailable; it is never treated as zero
or favorable evidence.

The recommendation unit is `Hull + BuildArchetype`, not hull identity. A
single hull may therefore appear as independent Tank, Line Anchor, and
Finisher candidates when their inferred build compatibilities clear the
registered thresholds. Each leg first ranks its own recommendation score,
then applies diversity only among materially competitive combinations.

For a faction, each of the 5 capability axes is classified into a tier
using its `FactionCapabilityProfile.role_capabilities` best score
(`analysis/faction_capability.py`, already built):

```text
STRONG    score >= gap_strong_threshold
ADEQUATE  gap_adequate_threshold <= score < gap_strong_threshold
WEAK      gap_weak_threshold <= score < gap_adequate_threshold
GAP       score < gap_weak_threshold
```

Thresholds are named, versioned heuristic values (`core/heuristics.py`,
`baseline_0.2`: `gap_strong_threshold`, `gap_adequate_threshold`,
`gap_weak_threshold`), per Agent.md's rule that all tunable heuristics
live in the registry. They are a first-pass heuristic, not tuned against
a benchmark -- the same honest status `doctrine_match`'s weights carry.

Only `WEAK` and `GAP` tiers are returned as `CapabilityGap` records --
`STRONG`/`ADEQUATE` axes are not "meaningful" gaps per the design's own
framing ("detect meaningful capability gap," not merely a low number).

```text
CapabilityGap
    role: str                       # one of the 5 capability axes
    tier: "WEAK" | "GAP"
    faction_existing_coverage: float # best known-hull score for this role
    evidence_confidence: float       # see section 11
```

Deliberately not implemented (would be fabrication, not evidence):
`desired_traits`, `secondary_preferences`, `severity` beyond the tier
itself -- these need the fuller capability taxonomy from section 3 to
mean anything real.

## 5. Adaptive retrofit search (not implemented -- see section 2)

## 6. Native search -- implemented

For each `CapabilityGap`, score every resolved hull in the faction's real
`known_hulls` (the same set `analyze_faction_capability` already
resolves) against that role via `classify_hull`, then rank by raw
`capability_score` -- **not** a "capability gain over existing coverage."

**Correction (found while writing this engine's own tests, before any
release):** the original draft of this section defined
`capability_gain = max(0.0, candidate_score - faction_existing_coverage)`
and excluded non-positive-gain hulls, mirroring section 10's later
composite-score idea. That formula is only meaningful for retrofit or
acquisition candidates, which sit *outside* the pool that produced
`faction_existing_coverage`. For native search specifically, the
candidate pool *is* the same known-hull set `faction_existing_coverage`
was computed from (`analyze_faction_capability`'s own best score) -- so
no native hull can ever exceed a baseline defined as that same set's own
maximum. The very first test written against this formula (three hulls
scoring 0.125/0.25/0.375, expecting all three to rank) could not pass:
every one of them showed `capability_gain <= 0` by construction, because
the highest of the three necessarily *was* the baseline. Traced the
root cause instead of patching the test to fit a broken formula, and
fixed the design here to match reality: native recommendations rank by
plain `capability_score`, and the faction's own best-known hull is
correctly rank 1 (it already was, per `svg faction-capability` -- this
engine's value-add over that command is showing ranks 2/3 as
alternatives, and filtering to only the roles that are actually gaps).

Ties break by hull id for determinism. Top `gap_recommendation_count`
(heuristic, `baseline_0.2`, default 3) candidates with
`capability_score > 0` are returned per gap; a gap where *no* known hull
scores above zero is recorded as `unaddressed` (section 15) -- a genuine
"no native solution exists" case, never a fabricated recommendation.

```text
NativeRecommendation
    role: str
    hull_id: str
    capability_score: float   # this hull's own role_compatibility[role]
    rank: int                 # 1-based, within this role's list
```

## 7. Acquisition search (not implemented -- see section 2)

## 8. Retrofit cost (not implemented -- see section 2)

## 9. Role distortion (not implemented -- see section 2)

## 9.1 Mechanical-family diversity

Recommendation diversity must not depend on curated mod-specific hull-family
metadata. For every resolved hull, derive a deterministic `HullFeatureVector`
from normalized scan data, then calculate a non-exclusive
`MechanicalArchetypeProfile`. Initial targets are: armor brawler, shield
brawler, line ship, artillery, skirmisher, striker, missile support, PD
escort, light/heavy carrier, battlecarrier, combat freighter, freighter,
tanker, salvage support, and survey support.

Inputs are hull size; DP/OP; armor/hull; shields; flux; mobility; weapon mount
composition, sizes, and arcs; missile capacity; bays; built-ins; known
ship-system categories; logistics stats; and aggregate existing-variant
evidence. Existing variants are usage statistics, never hard truth: they may
have bounded influence but cannot create structural evidence, alter legality,
or imply faction ownership. Factionless equipment remains mechanically
classified but `UNALIGNED` unless real faction/pack/override access evidence
says otherwise.

Within each Native, Retrofit, and Acquisition leg independently: rank all
eligible candidates by recommendation score with deterministic ties; then
select a shortlist that prefers meaningfully different functional role and
mechanical-archetype profiles among candidates that remain competitively close.
It must not elevate a materially worse candidate for variety. Each candidate's
stored profile, feature contributions, comparison set, score tradeoff, and
final diversity decision must be available to Why-Not.

## 10. Recommendation score (v1, native-only)

The full target formula (capability_gain x severity, plus role fit,
mechanical quality, AI/player suitability, equipment support, doctrine
fit, minus retrofit cost, role distortion, uncertainty, access penalty)
cannot be honestly computed yet -- most terms need sections 5, 7, 8, 9,
or 12, and (per section 6's correction) `capability_gain` itself is only
a meaningful term once retrofit/acquisition candidates exist outside the
native pool. For v1, a native recommendation's rank *is* its raw
`capability_score`, descending. No composite score beyond that is
fabricated. When the prerequisite sections land, this section should be
revised to the fuller formula, not before.

## 11. Confidence (v1: evidence completeness only)

Full scripted-mechanic confidence propagation (`UNKNOWN_SHIP_SYSTEM`,
`UNKNOWN_SCRIPTED_HULLMOD`, `INFERRED_WEAPON_BEHAVIOR`,
`STALE_KNOWLEDGE_PACK`, `LIMITED_VARIANT_EVIDENCE`) needs machinery this
project doesn't have yet: `validate_variant`'s legality findings aren't
threaded into a numeric confidence score anywhere, and there is no
knowledge-pack staleness concept (Phase 7). Implementing a full
confidence figure now would mean inventing most of its inputs.

v1's `evidence_confidence` is honest but narrow: the fraction of the
faction's `known_hulls` that actually resolved in the registry --

```text
evidence_confidence = hulls_examined / (hulls_examined + len(unresolved_known_hull_ids))
```

-- directly from `FactionCapabilityProfile` (already computed). This
answers only "how much of the faction's real hull list could we even
look at," not "how mechanically certain is this specific
recommendation." Both matter; only the first is implemented.

## 12. Knowledge-pack doctrine bias (not implemented -- see section 2)

## 13. Why Not? -- implemented for the native leg

`analysis/gap_recommendation.py::explain_native_candidate(faction,
registry, role, hull_id)` answers "why wasn't this hull recommended for
this role?" using the exact same real ranking `recommend_native_solutions`
already computes for that gap -- `_rank_candidates_for_role` is now a
shared helper rather than logic private to the recommendation path, so
this isn't a second inference mechanism that could disagree with the
actual recommendations.

Distinguishes three real, materially different situations rather than
collapsing them into "ranked lower":

- **Recommended** -- was inside the top `gap_recommendation_count`. Reports its rank.
- **Ranked, but below the cutoff** -- has a real positive score, but not
  high enough. Reports its rank, the total candidate count, and the exact
  score gap to the lowest-scoring hull that *was* recommended.
- **Zero real evidence** -- scores `0.0` on this role entirely. Reported
  distinctly ("no real evidence of this capability at all"), not as
  "ranked last," since a hull with some real but modest signal and a hull
  with no signal for a role are different facts worth saying differently.

An unresolved `hull_id` (not a real, resolved known hull of this faction)
is reported as `resolved=False` rather than silently scored as 0.0 --
"we don't know this hull" and "we know this hull and it scores zero" are
different claims.

Not yet extended to retrofit/acquisition candidates, since those legs
don't exist (section 5/7 above) -- this is Phase 11 wiring against what
Phase 10 already has, not new recommendation-search work.

## 14. GUI layout (not implemented -- see section 2)

## 15. No Recommendation -- implemented

A gap with zero known hulls scoring above zero on that role is
listed in `GapRecommendationResult.unaddressed_gaps` rather than the
engine inventing a low-quality recommendation to fill a slot. This is
the honest v1 form of the full design's "No Recommendation" case (which,
at full maturity, only fires after native, retrofit, *and* acquisition
have all failed -- v1 can only speak to the native leg).

## 16. Deterministic testing

- a role where the faction's best known hull scores below
  `gap_weak_threshold` is classified `GAP`; at or above
  `gap_strong_threshold` is `STRONG` and not returned as a gap
- native recommendations are ranked by raw `capability_score` descending,
  ties broken by hull id (not by a gain-over-existing-coverage formula --
  see section 6's correction for why that's structurally wrong for
  native search specifically)
- a gap where no known hull scores above zero appears in
  `unaddressed_gaps`, never as a fabricated recommendation
- `evidence_confidence` reflects real known-hull resolution rate,
  including the 0-known-hulls edge case (defined as confidence 0.0, not
  a division error)
- gap-severity/count thresholds come from the named heuristic set, not
  literal constants in the engine module

## 17. API and CLI surface

`api.py::run_gap_recommendations(registry, faction_id, source_mod, heuristic_set) -> GapRecommendationResult`,
`svg recommend <faction_id> [--source-mod ...]`. Mirrors the existing
`svg faction-capability` command's faction-resolution pattern exactly.

`api.py::run_why_not(registry, faction_id, role, hull_id, source_mod, heuristic_set) -> WhyNotExplanation`,
`svg why-not <faction_id> <role> <hull_id> [--source-mod ...]`.

## 18. Scenario-Aware Recommendations (Phase 31, Charter Priority 9)

Extends ranking from `Hull + BuildArchetype` (sections 4-13 above) to
`Hull + BuildArchetype + ScenarioObjective` units, e.g. "this hull/build is
a good pick specifically for a RAIDING scenario," not just "this hull/build
is a good LINE_ARTILLERY pick." Implemented in
`analysis/gap_recommendation.py::recommend_scenario_solutions`/
`explain_scenario_candidate`.

**Scenario taxonomy.** `ScenarioCategory` is a deliberately small,
explicitly synthetic set: `RAIDING`, `DEFENSE`, `ESCORT`, `PATROL`. Checked
against real data before inventing it: no parseable Starsector hull/
variant/faction field in this project's schema records a documented
"mission role," "deployment points," or comparable in-game scenario tag
(the closest real data, the hull CSV `hints` column, covers civilian/
logistics roles only). This is therefore a first-pass heuristic taxonomy,
never a documented game mechanic -- the same honest status this document's
other first-pass thresholds already carry (e.g. `gap_strong_threshold`,
section 4). Not to be confused with the unrelated, earlier-landed
`analysis/scenario_objectives.py::ScenarioObjective` (which generation-time
coverage objectives, e.g. `LINE_HOLD`/`BREAKTHROUGH`, a single build
archetype already supports) -- that is a generation-presentation concept;
this section's `ScenarioCategory` is a faction-recommendation concept, and
deliberately uses a different type name to avoid confusion between them.

**Strictly additive and separately labeled.** `recommend_scenario_solutions`
takes an already-computed `GapRecommendationResult` (i.e. an existing
`recommend_gap_solutions` call) and a `ScenarioCategory`, and layers a
heuristic scenario-fit score on top of the Native/Retrofit/Acquisition
legs' own already-ranked `hull_id`/`build_archetype_id`/
`recommendation_score`/`confidence` -- it never recomputes or reorders
those legs, and `recommend_gap_solutions` itself is completely unmodified
(nothing calls the new function automatically). Every record it produces
carries `kind = SCENARIO_RECOMMENDATION_KIND` ("INFERRED_SCENARIO_OPTION"),
a `source_leg` citing exactly which real leg's ranked candidate it reused,
and `base_recommendation_score` citing that leg's own unmodified score, so
a scenario option is structurally distinguishable from -- and never
mistaken for -- the direct role-gap evidence the rest of this engine
produces.

**Scenario-fit heuristic.** `scenario_fit_score` (0.0-1.0) is a fixed,
first-pass weighted combination of already-computed, real signals: the
hull's `MechanicalArchetypeProfile.compatibility_scores` and the specific
`BuildArchetypeProfile`'s own `tactical_style`/`target_range`/
`flux_posture`/`survivability_posture`/`equipment_priorities` fields. The
combination *weights* are heuristic and undocumented as game mechanics
(same status as `gap_strong_threshold`); the *inputs* are all real,
already-verified evidence -- nothing here invents a new game fact. A
candidate below `scenario_fit_min_signal` (`baseline_0.11`, default 0.30)
is simply absent from the result, never padded in, mirroring
`unaddressed_gaps`' "no fabricated recommendation" discipline (section 15).
`scenario_recommendation_score = base_recommendation_score *
scenario_fit_score`; ranking is local to one `(role, scenario)` shortlist
only and is never compared across legs or across scenarios.

**Confidence is always visibly bounded.** `scenario_confidence_cap`
(`baseline_0.11`, default 0.75) hard-caps every `ScenarioRecommendation`'s
`confidence` below the underlying leg's own confidence
(`min(leg_confidence, build.confidence, scenario_confidence_cap)`) -- a
heuristic overlay must never present itself as fully certain the way a
direct evidence-based recommendation can (AGENTS.md's "High score with low
confidence must remain visibly low confidence").

**Why-Not.** `explain_scenario_candidate` answers "why wasn't
`<hull_id>`/`<build_archetype_id>` given as an `INFERRED_SCENARIO_OPTION`
for `<scenario>` on `<role>`?" using the exact same real ranking
`recommend_scenario_solutions` computes (never a second inference
mechanism). Its result (`ScenarioWhyNotExplanation`) always carries the
underlying, direct evidence-based `BuildWhyNotExplanation` (section 13,
`explain_build_candidate`) as a separate `underlying` field, and its own
`reason` text always states plainly that this is a heuristic overlay, not
evidence -- the two explanations are never conflated into one claim.

**Deterministic testing** (`tests/test_scenario_recommendation.py`): a
scenario recommendation is always labeled `INFERRED_SCENARIO_OPTION`; a
low-fit `Hull + BuildArchetype` unit is excluded even when a sibling build
on the identical hull passes; computing scenario recommendations never
mutates or changes the content of the underlying `GapRecommendationResult`;
confidence is always strictly bounded below full certainty even when the
underlying leg is fully confident; and Why-Not distinguishes "recommended,"
"considered but below the signal threshold," and "never entered any leg at
all" as three different, honestly-labeled facts.
