# AGENTS.md
# VoidSmith repository contract
Version 0.7 (2026-10-14). Replaces 0.6: same rules, consolidated (the continuous-execution rule appeared three times), the Save
Workshop clause updated to the capacity evidence now on record, and sections added for hygiene, evidence, automation direction
and the sister projects. The Python package keeps its original name, `starsector_variant_generator`.

VoidSmith is an offline, deterministic, explainable desktop tool for Starsector 0.98a-RC8: it reads the installed game and
enabled mods, builds legal ship fits, explains them, analyses faction capability, advises fleet support, and edits copies of
saves within strict limits. It never changes game or mod files.

## 1. Required reading order

1. `AGENTS.md`
2. `FORMAL_SPECIFICATION.md`
3. `DATA_SCHEMA.md`
4. `GAP_RECOMMENDATION_ENGINE.md` when changing capability gaps, recommendations, diversity or Why-Not
5. `FACTION_KNOWLEDGE_PACKS.md` when changing faction guidance or pack data
6. `EQUIPMENT_ACCESS_AND_AUTOFIT.md` when changing access or retrofit substitution
7. `HULLMODS_CIVILIAN_AND_REFIT.md`
8. `TEST_PLAN.md`
9. `HEURISTICS.md` when changing analysis or scoring behaviour
10. `GUI.md` when changing GUI code
11. `docs/SAVE_WORKSHOP_DESIGN.md` and `docs/CAMPAIGN_SAVE_PARSER_GATE.md` when touching `campaign/` or the Save Workshop
12. `ROADMAP.md`, and `docs/AUTOMATION_PLAN.md` for checks, tooling and automation work

## 2. Direction

What the project is working toward, in order (details in `ROADMAP.md` and `docs/AUTOMATION_PLAN.md`):

1. **Safe to publish:** nothing in git names third-party game or mod entities; every write is atomic; untrusted archives are read
   with limits; lint and type checks are enforced in CI, not only run once.
2. **Checks that run themselves** instead of hand-run stress tests: every shipped variant validated in one command, mod
   acceptance compared against a baseline, parse failures reported with locations.
3. **Finish the Save Workshop** (phase 57) on recorded evidence.
4. **Calibration a person can finish:** the tool resolves, pre-checks and sorts review rows; people approve; people release
   heuristic sets.
5. **Useful to the sister projects** (section 13) through read-only verdicts, never by sharing data in git.

The engine stays useful with no knowledge pack, no calibration data and no network.

## 3. Source safety

Source game and mod files are read-only. Never overwrite source variants, alter Starsector core files or original mod files,
execute mod scripts to discover behaviour, or write outside the configured output, log and cache directories. Treat mod data as
untrusted input: sanitize paths, bound archive sizes, refuse links and junctions where a write or delete could follow them.

### Save Workshop

`docs/SAVE_WORKSHOP_DESIGN.md`, roadmap phase 57. The player's original save is source data and is never modified. The only
permitted write is a new copy of a user-selected save below the configured output directory, never into the game's saves folder,
and never before every gate in `docs/CAMPAIGN_SAVE_PARSER_GATE.md` is met. The writer (S3, owner decision 2026-10-06) writes only
changes the plan ACCEPTED within the saved capacity, re-reads and verifies the copy, and refuses over-capacity or unprovable changes.

Capacity overage is now measured (BridgeForge `docs/RC8_BEHAVIOUR.md` RC8-34 to RC8-36, live runs 2026-10-12): each unit over
cargo, fuel or personnel capacity costs 0.1 supplies per day (cap 50 per resource), speed falls with the worst ratio, and a save
stores its capacity figures as of save time. These rows may be **shown** as consequences, cited by row id. Over-capacity
**writes stay refused**: whether a load recomputes an edited `mC`/`mF`/`mP` is still unmeasured. No other overage effect may be
computed or claimed.

## 4. Distribution and IP boundary

Do not ship Starsector core data, mod data, extracted reports, sprites, descriptions, real entity lists, mod-specific knowledge
packs, calibration packs, review sheets or benchmarks that name third-party game or mod entities. The repository may contain only
application code, schemas, neutral synthetic fixtures, and empty or generic templates. At runtime, every game- or mod-specific
fact is read from the user's installed core and enabled mods and written only to local configured output or cache directories,
or to the gitignored `generated/` tree. Local benchmark manifests selecting real entities are user-created, ignored files.

`tests/test_distribution_boundary.py` enforces this for tracked files (added 2026-10-14, when six real-entity calibration files
and a curated guide were moved out of git into `generated/`). Do not weaken it to make a file fit.

## 5. No AI dependency

Do not add an AI, LLM or API dependency unless the owner explicitly asks. The core engine stays offline, deterministic,
explainable and testable without AI. AI-assisted review packs are optional input data, never a runtime dependency.

## 6. Do not invent game behaviour

Use documented, parseable data and preserve raw evidence. Unknown or scripted mechanics stay `UNKNOWN` or
`UNKNOWN_SCRIPTED_EFFECT`. If an unknown effect is needed to decide legality, return `NOT_DETERMINABLE` rather than guessing.

A claim about how the game behaves at runtime needs evidence with a date: a parsed core file, a javap line, a log line or a
recorded live run. Cite BridgeForge's `docs/RC8_BEHAVIOUR.md` row ids where one exists. Label forecasts PREDICTED and observed
facts OBSERVED.

## 7. Legality and quality are strictly separate

Validation alone owns `LEGAL`, `ILLEGAL` and `NOT_DETERMINABLE`. Legality never depends on heuristics, faction doctrine, role
preference, quality scores, Beginner/Guided/Advanced mode or user taste. Scoring evaluates only `LEGAL` candidates. Warnings
(poor flux, weak PD, role mismatch, low logistics efficiency) are separate from legality; never use a score or warning to conceal
an illegal or indeterminate candidate.

Severity of an illegal shipped variant follows recorded runtime evidence (BridgeForge, 2026-09-27): a variant naming a missing
weapon is a Fatal error at New Game; a missing hull mod is dropped silently. Report both; do not invent other severities.

## 8. Heuristics, calibration and overrides

### Heuristic registry

All tunable heuristics belong to a named, versioned registry. Reports, fixtures and generated metadata record the heuristic set
identifier, resolved values, explicit overrides and adapters used. A new or changed released heuristic needs a rationale,
documentation, regression coverage and a new set identifier.

**Heuristics are never tuned automatically.** Tools may measure sets against approved calibration rows and write a *proposed* set
under `generated/`; a person reviews and registers it.

### Calibration

Calibration rows are evidence about real ships and live only under `generated/`. Tools may resolve names to ids, run pre-checks
and sort rows; only a named person marks a row APPROVED (batch approval of rows that passed every pre-check is allowed, owner
decision 2026-10-14). Unapproved rows never influence released behaviour.

### Manual overrides

Overrides may correct or supplement inferred metadata: role classification, score inputs, hidden/restricted classification,
doctrine affinity, scripted-effect interpretation when explicitly supplied. Overrides may NOT bypass hard legality.

Precedence for non-legality metadata: explicit manual override > adapter-derived model > standard-data inference > unknown/default.

## 9. Engine design rules

### Adapter layer and scripted-mechanic evidence ladder

For a hullmod, ship system, weapon or fighter whose effect is not fully represented by normalized static fields, collect evidence
in this order: (1) parsed static metadata; (2) local source-code static analysis, never executing scripts; (3) known Starsector
API-call interpretation; (4) local mod-specific configuration; (5) existing variant or use evidence (statistical only, never hard
truth); (6) adapter-derived model; (7) explicit manual override; (8) `UNKNOWN_SCRIPTED_EFFECT`. This is an evidence-acquisition
ladder, not score or legality precedence. Every stage used is recorded in provenance with source location, confidence and
unmodelled remainder. Custom scripted mechanics use adapters (`adapters/vanilla/`, `adapters/<mod>/`), not `if mod_id == ...`
branches in generic engine code.

### Hullmod modelling

Represent hullmods through normalized typed effects when their behaviour can be reliably determined; evaluate the resulting
`DerivedShipState`, not the hullmod name. Unknown scripted effects stay unknown until an adapter or override models them.

### Civilian and logistics scope

Civilian and logistics ships are first-class fitting targets, with per-ship profiles (FREIGHTER, TANKER, SALVAGE, SURVEY,
TROOP_TRANSPORT, FAST_LOGISTICS, STEALTH_LOGISTICS, EXPEDITION_SUPPORT, GENERAL_SUPPORT). Fleet-wide effects may be recorded
as metadata. Fleet Support and Scenario advice is advisory; whole-fleet optimization is out of scope without an explicitly
requested fleet-planning phase.

### Refit / repair assistant

Improves an existing variant with minimal changes: preserves locked user choices, explains each change, supports a
maximum-change budget, never silently rebuilds the whole ship, and distinguishes legality fixes from quality improvements.
Retrofit modes: `EXACT` (never substitutes), `STARSECTOR_STYLE` (preserves the template), `ADAPTIVE` (default; preserves role and
doctrine and optimizes legal substitutions).

### Equipment provenance vs faction affinity

Never equate `source_mod_id` with faction ownership. Factionless content is normally `UNALIGNED` and may participate when access
policy permits.

### Architectural boundaries

Keep separate: parsers, normalized data, provenance, adapters, overrides, validation, derived ship state, classification,
heuristics, generation, scoring, explanation, refit assistant, export, campaign (save) handling, GUI. The GUI never becomes a
second rules engine: it calls `api.py` and presents results.

## 10. Faction knowledge and recommendations

- Faction-specific guidance is optional, data-driven **Faction Doctrine & Retrofit Packs**, never hardcoded. Packs may provide
  doctrine, preferred and discouraged roles, hullmods, retrofit templates, gap interpretation, progression guidance, officer
  suggestions and thematic notes. They influence recommendation quality, never hard legality.
- The engine builds a useful faction capability profile from installed mod data alone; packs are enrichment.
- Packs record schema version, target mod/faction and version, source hashes, authored or generated date and authorship method;
  status `CURRENT`, `PARTIALLY_STALE`, `STALE` or `INCOMPATIBLE`. Stale guidance stays advisory with reduced confidence.
- Gap recommendations distinguish `NATIVE`, `RETROFIT` and `ACQUISITION`, return a ranked shortlist of normally 3-5 options, keep
  score and confidence separate (high score with low confidence stays visibly low confidence), prefer different solution
  families, and never promote illegal or clearly poor candidates for diversity. Why-Not explains why an eligible option missed.
- Lightweight constraints: foreign hulls, hidden/secret hulls, AI / Player / Either, experimental retrofits, doctrine strictness
  LOOSE / BALANCED / STRICT, optional campaign stage. Do not require fleet inventory or full fleet composition.
- `player_suitability` (phase 54) is decision-gated: do not change its behaviour or infer player skill or combat outcomes.

## 11. GUI

Top-level workspaces: **Ships** (browser, fitting canvas, inspector, comparison, generate), **Retrofits** (refit/repair
assistant, templates, before/after), **Faction** (capability, gaps, recommendations, pack status, Why-Not, feedback), **Data /
Analysis** (weapons, hullmods, fighters, variants, doctrine evidence, provenance, unknown effects), **Settings / Export** (paths,
mods, scan/cache, heuristic set, output, export, release verification, debug), and the **Save Workshop** behind a default-off
setting. Fleet Support and Scenario stay advisory. No decorative GUI work before the backend contract is stable; GUI changes
follow `GUI.md` and keep `tools/gui_smoke_test.py` passing.

## 12. Engineering hygiene

- Write files atomically (temp file in the same folder, then `os.replace`); delete trees only inside an allowed root and never
  through a link or junction. (`core/safeio.py`, `docs/AUTOMATION_PLAN.md` V0.2; `tests/test_safeio_ratchet.py` keeps bare writes and deletes from growing.)
- Read untrusted archives with per-entry, total and compression-ratio limits before extracting anything.
- Tests with every parser, validator, adapter, hullmod-effect, civilian-profile, scoring and campaign change. Fixtures are neutral
  and synthetic. Golden-output changes are deliberate and documented in the commit.
- Before committing, run the suite and the checks CI runs (`CLAUDE.md` lists the commands). Full-source mypy reached zero on
  2026-08-31: keep it there.
- One logical change per commit; update `ROADMAP.md` and `docs/WORK_LOG.md` with what was built, its limits and its tests.
- Before merging another agent's branch, review its diff for deleted files and files cut by more than a fifth, and rerun the full
  suite on the merged tree.

## 13. Sister projects

VoidSmith is published; its siblings are local projects of the same owner. Read their contracts before editing them.

| Project | Relationship |
|---|---|
| BridgeForge (`Documents/Project BridgeForge`) | revives legacy mods; owns `docs/RC8_BEHAVIOUR.md`, the runtime facts VoidSmith cites. `voidsmith check-mod` (built 2026-10-18) gives it a read-only verdict on a revived mod |
| Salvor (`Documents/Project Salvor`) | save rescue (diagnose, repair a copy). The save editor lives here, in the Save Workshop, not in Salvor |
| Project Go (`Documents/Starsector project go`) | mod translator |
| SPW | inventory source; a synthetic round trip is tested (`tests/test_spw_round_trip.py`); the round trip on a real install is still to be proven |

Exchange happens through files the user selects or commands the user runs. Never copy a sibling's mod or game data into this
repository.

## 14. How to work

Treat milestones as checkpoints, not stopping points. Continue through the current roadmap automatically until one of these
happens: a genuine blocking ambiguity the repository, specs, tests or code cannot resolve; required user input is missing;
continuing would risk modifying protected or source files; a fundamental architecture conflict needs a design decision; or the
requested scope is complete.

At each completed slice: run the relevant tests, update the roadmap and status, record limits and design changes, and continue
into the next logical in-scope task without asking. For a non-blocking implementation choice, make the most conservative
architecture-consistent choice, document it and continue. Partial uncertainty is not a blocker when the repository gives enough
evidence for a reasonable, reversible choice: proceed and record the assumption.

Ask the owner only when a decision would materially change scope, architecture, data contracts, safety or expected behaviour,
or before anything irreversible or outward-facing (publishing a release, rewriting history, pushing). Finish the requested work
before adding unrelated features.
