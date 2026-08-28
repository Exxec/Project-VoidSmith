# AGENTS.md
# Starsector Variant Generator Repository Contract
Version 0.5

Read the formal specification before coding.

## Required Reading Order

1. `AGENTS.md`
2. `FORMAL_SPECIFICATION.md`
3. `DATA_SCHEMA.md`
4. `GAP_RECOMMENDATION_ENGINE.md` when changing capability gaps, recommendations, diversity, or Why-Not
5. `FACTION_KNOWLEDGE_PACKS.md` when changing faction guidance or pack data
6. `EQUIPMENT_ACCESS_AND_AUTOFIT.md` when changing access or retrofit substitution
7. `HULLMODS_CIVILIAN_AND_REFIT.md`
8. `TEST_PLAN.md`
9. `HEURISTICS.md` when changing analysis/scoring behavior
10. `GUI.md` when changing GUI code
11. `ROADMAP.md`

## Continuous Execution Rule

Treat milestones as checkpoints, not stopping points. After a completed slice:
run the relevant tests, update roadmap/status documentation, record limits or
schema/heuristic changes, and immediately continue into the next in-scope
dependency. Ask only for a genuine blocker, missing required input, source
safety concern, or material architecture/data-contract decision.

## Source Safety

Source game and mod files are read-only.

Never:
- overwrite source variants
- alter Starsector core files
- alter original mod files
- execute mod scripts merely to discover behavior
- write outside configured output/log/cache directories

Treat mod data as untrusted input and sanitize paths.

## Distribution and IP Boundary

Do not ship Starsector core data, mod data, extracted reports, sprites,
descriptions, real entity lists, mod-specific knowledge packs, or benchmarks
that name third-party game/mod entities. The distributable repository may
contain only application code, schemas, neutral synthetic fixtures, and empty
or generic templates. At runtime, all game/mod-specific facts must be read
from the user's installed core game or enabled mods and written only to local
configured output/cache directories. Local benchmark manifests selecting real
entities are user-created, ignored files.

## No AI Dependency Yet

Do not add an AI/LLM/API dependency unless explicitly requested later.

The core engine must remain:
- offline
- deterministic
- explainable
- testable without AI

## Do Not Invent Game Behavior

Use documented, parseable data and preserve raw evidence.

Unknown or scripted mechanics remain:
- `UNKNOWN`
- `UNKNOWN_SCRIPTED_EFFECT`

If an unknown effect is required to determine legality, return:

`NOT_DETERMINABLE`

rather than guessing.

## Legality and Quality Are Strictly Separate

Validation alone owns:
- `LEGAL`
- `ILLEGAL`
- `NOT_DETERMINABLE`

Legality must never depend on:
- heuristics
- faction doctrine
- role preference
- quality scores
- Beginner/Guided/Advanced mode
- user taste

Scoring may evaluate only `LEGAL` candidates.

Warnings are separate from legality.

A legal fit may have warnings such as:
- poor flux
- weak PD
- role mismatch
- low logistics efficiency

Never use a score or warning to conceal an illegal or indeterminate candidate.

## Heuristic Registry

All tunable heuristics belong to a named, versioned heuristic registry.

Reports, fixtures, and generated metadata must record:
- heuristic set identifier
- resolved values
- explicit overrides
- adapters used

New or changed released heuristics require:
- rationale
- documentation
- regression coverage
- a new heuristic-set identifier

## Adapter Layer

### Scripted-mechanic analyzer hierarchy

For a hullmod, ship system, weapon, or fighter whose effect is not fully
represented by normalized static fields, collect evidence in this order:

1. parsed static hullmod/equipment metadata;
2. local source-code static analysis (never execute scripts);
3. known Starsector API-call interpretation;
4. local mod-specific configuration;
5. existing variant/use evidence (statistical only, never hard truth);
6. adapter-derived model;
7. explicit manual override;
8. `UNKNOWN_SCRIPTED_EFFECT` when no reliable interpretation exists.

This is an evidence-acquisition ladder, not score/legality precedence.
Final non-legality metadata still follows the explicit precedence stated in
the Manual Overrides section below. Every stage used must be recorded in
provenance with source location, confidence, and unmodeled remainder.

Custom scripted mechanics must use adapters rather than scattered special cases.

Example:

```text
adapters/
    vanilla/
    hmi/
    mvs/
    progressive_smods/
```

Prefer adapter-specific modeling over:

```python
if mod_id == "some_mod":
    ...
```

throughout generic engine code.

## Manual Overrides

Manual overrides may correct or supplement inferred metadata.

Overrides may affect:
- role classification
- score inputs
- hidden/restricted classification
- doctrine affinity
- scripted-effect interpretation when explicitly supplied

Overrides may NOT bypass hard legality.

Precedence for non-legality metadata:

```text
explicit manual override
    >
adapter-derived model
    >
standard-data inference
    >
unknown/default
```

## Civilian / Logistics Scope

Civilian and logistics ships are first-class fitting targets.

Support per-ship profiles such as:
- FREIGHTER
- TANKER
- SALVAGE
- SURVEY
- TROOP_TRANSPORT
- FAST_LOGISTICS
- STEALTH_LOGISTICS
- EXPEDITION_SUPPORT
- GENERAL_SUPPORT

Do not implement whole-fleet optimization in the current scope.

Fleet-wide effects may be recorded as metadata, but do not attempt to optimize
them without an explicitly requested fleet-planning phase.

## Hullmod Modeling

Hullmods should be represented through normalized typed effects when their
behavior can be reliably determined.

Evaluate the resulting `DerivedShipState`, not the hullmod name alone.

Unknown scripted effects remain unknown until modeled by an adapter/override.

## Refit / Repair Assistant

Support a mode that improves an existing variant with minimal changes.

It must:
- preserve locked user choices
- explain each suggested change
- support a maximum-change budget
- never silently rebuild the whole ship
- distinguish legality fixes from quality improvements

## Continuous Work Policy

Phases are checkpoints, not automatic stop points.

When given broad implementation scope, continue through in-scope phases as far
as practical.

At each milestone:
1. run relevant tests
2. update `ROADMAP.md`
3. write/update completion notes
4. record limitations/schema/heuristic changes
5. continue unless genuinely blocked or the requested scope is complete

Do not ask for confirmation merely because a phase finished.

## Architectural Boundaries

Keep separate:
- parsers
- normalized data
- provenance
- adapters
- overrides
- validation
- derived ship state
- classification
- heuristics
- generation
- scoring
- explanation
- refit assistant
- export
- GUI

The GUI must not become a second rules engine.

## Testing

Add tests with parser, validator, adapter, hullmod-effect, civilian-profile, and
scoring changes.

Golden-output changes must be deliberate and documented.

## Scope Discipline

Finish the requested functionality before adding unrelated features.

Do not add decorative GUI work before backend contracts are stable enough to
support it.


## Faction Knowledge Packs

Faction-specific guidance must be implemented as optional data-driven
**Faction Doctrine & Retrofit Packs**, not hardcoded into the generic engine.

Knowledge packs may provide:
- curated faction doctrine
- preferred native hull roles
- discouraged roles
- preferred/conditional hullmods
- retrofit templates
- capability-gap interpretation
- progression-stage guidance
- officer suggestions
- thematic notes

Knowledge packs may influence recommendation quality but may never override hard
legality. The generic engine must remain useful when no pack exists.

## Automatic Faction Capability Analysis

The application must build a useful faction capability profile from installed
mod data alone using parseable hulls, weapons, fighters, variants, built-ins,
known hullmod effects, and role classifications.

Manual or AI-assisted review packs are optional enrichment, not mandatory
dependencies.

## Recommendation Categories

Capability-gap recommendations must distinguish:

- `NATIVE`
- `RETROFIT`
- `ACQUISITION`

The engine should return a small ranked shortlist, normally 3-5 useful options,
rather than only describing a missing capability.

## Recommendation Confidence

Every recommendation must separate:
- recommendation score
- confidence

High score with low confidence must remain visibly low confidence.

## Recommendation Diversity

Avoid returning several near-identical solutions when useful alternatives exist.

Prefer different solution families when practical:
- maximum capability
- practical/low-cost
- mobility-oriented
- durability-oriented
- faction-thematic
- native retrofit
- foreign acquisition

Diversity must never promote illegal or clearly poor candidates.

## Why-Not Support

Recommendation services should explain why a specific eligible hull or retrofit
failed to make the shortlist.

## Knowledge Pack Freshness

Every pack records:
- schema version
- target mod/faction
- target mod version
- relevant source hashes where available
- authored/generated date
- authorship method

Status:
- `CURRENT`
- `PARTIALLY_STALE`
- `STALE`
- `INCOMPATIBLE`

Stale guidance may remain advisory but must reduce confidence.

## Lightweight Recommendation Constraints

Support:
- allow foreign hulls
- allow hidden/secret hulls
- AI / Player / Either
- include experimental retrofits
- doctrine strictness: LOOSE / BALANCED / STRICT
- optional manually selected campaign stage

Do not require fleet inventory, save-state, or full fleet composition questions.

## GUI Workspace Separation

The desktop application should use distinct top-level workspaces/tabs so
different systems do not collapse into one overloaded screen.

Recommended top-level tabs:

1. **Ships**
   - Hull Browser
   - Ship Fitting Canvas
   - Existing Variant / Build Inspector
   - Candidate Comparison

2. **Retrofits**
   - Refit / Repair Assistant
   - Retrofit Templates
   - Native vs Retrofit comparison
   - Locked-component editing
   - Before / After comparison

3. **Faction**
   - Faction Capability Profile
   - Strengths / Weaknesses / Gaps
   - Native / Retrofit / Acquisition recommendations
   - Knowledge Pack status
   - Doctrine strictness
   - Progression-stage guidance

4. **Data / Analysis**
   - Weapons
   - Hullmods
   - Fighters
   - Existing variants
   - Doctrine evidence
   - Adapter / override provenance
   - Unknown scripted effects

5. **Settings / Export**
   - Starsector path
   - enabled mods
   - scan/cache status
   - heuristic set
   - output path
   - compatibility mod export
   - debug/logging controls

Do not put whole-fleet optimization into the Faction workspace in the current
scope. "Faction" means faction capability and recommendation context, not an
exact player fleet planner.


## Equipment Provenance vs Faction Affinity

Never equate `source_mod_id` with faction ownership. Factionless content should normally be modeled as `UNALIGNED` and may participate when access policy permits.

## Retrofit Application Modes

Support `EXACT`, `STARSECTOR_STYLE`, and `ADAPTIVE`. Adaptive is the recommended default. Exact never substitutes. Starsector-style preserves the template. Adaptive preserves role/doctrine and optimizes legal substitutions.


Continuous execution rule

Continue working through the current roadmap automatically until one of the following occurs:

you encounter a genuine blocking ambiguity that cannot be resolved from the repository, specs, tests, or existing code
required external/user input is missing
continuing would risk modifying protected/source files
you discover a fundamental architecture conflict that requires a design decision
the requested roadmap scope is complete

Do not stop merely because a phase, milestone, slice, or subtask is complete.

At each completed slice:

run the relevant tests
update the roadmap/status
record limitations or design changes
continue immediately into the next logical in-scope task

Do not ask for permission to continue after successful completion of a slice.

If a non-blocking implementation choice is needed, make the most conservative architecture-consistent choice, document it, and continue.

Ask me only when the decision would materially change scope, architecture, data contracts, safety, or expected behavior.

Partial uncertainty is not automatically a blocker. If the repository contains enough evidence to make a reasonable, reversible implementation choice, proceed and document the assumption.
