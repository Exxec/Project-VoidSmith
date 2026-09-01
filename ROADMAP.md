# VoidSmith Live Roadmap

This is the authoritative plan for current work. Implementation and tests are
authoritative for behavior already shipped. Historical calibration logs,
installation measurements, and local review notes are deliberately not part of
the distributable repository.

## Current scope

VoidSmith is an offline, deterministic, source-read-only assistant for:

- per-ship fitting, validation, generation, and minimal-change refit;
- faction capability analysis and Native / Retrofit / Acquisition
  recommendations;
- locked-selection Fleet Support recommendations; and
- static Scenario / Mission alignment against generic or user-declared
  capability targets.

It does not simulate combat, optimize a whole fleet, alter source game/mod
files, or make campaign-inventory or market-availability decisions.

## Completed milestones

| Milestone | Status | Result |
| --- | --- | --- |
| Scanner, normalized data, provenance, and cache | Complete with limits | Read-only parsing of installed core/mod sources; unknown and malformed data remain explicit. |
| Validation, derived state, generation, and refit | Complete with limits | Three-state legality is separate from quality; refit is bounded and preserves locks. |
| Faction capability and recommendations | Complete with limits | Data-driven capability gaps, diversity, confidence, and Why-Not paths; guidance remains advisory. |
| Desktop workspaces and export | Complete with limits | GUI calls backend services without duplicating rules; exports write only compatibility-mod output. |
| Fleet Support | Complete with limits | Selected ships stay locked; complementary individual additions are ranked with composition synergy. |
| Scenario / Mission Advisor | Complete with limits | Generic templates and custom capability targets report static alignment and can feed deficient needs to Fleet Support. |
| Scenario workflow handoff | Complete with limits | Portable snapshots, visible scenario-targeted cards, and a revalidated Scenario Fit handoff to the bounded generator; “Stop Waiting” safely discards a pending GUI result. |

## Post-RC phases

| Phase | Status | Scope and completion boundary |
| --- | --- | --- |
| 43 — Linux portable qualification | Complete with limitations | Native Linux x64 archive, checksum, license/NOTICE inclusion, and headless smoke test are implemented. The tag workflow publishes only after both native platform builds complete; the hosted Linux build has since succeeded in CI (for example tag `v0.1.0RC3`), while cross-distribution desktop runtime verification remains external evidence. |
| 44 — Campaign-save discovery boundary | Complete with limitations | `run_campaign_save_discovery()` inventories only direct metadata in an explicit user-selected directory. It has no location guessing, content parsing, mutation, inventory interpretation, or undocumented save semantics. |
| 45 — Officer and deployment-point advisory boundary | Complete with limitations | `run_fleet_advisory_boundaries()` exposes optional freshness-adjusted knowledge-pack officer guidance as presentation-only, while deployment points stay `NOT_DETERMINABLE` because the normalized hull schema has no field for them. Neither affects legality, ranking, or outcome claims. |
| 46 — Calibration and generic-mod qualification | Complete with limitations | Existing hash-bound fixture evaluation, before/after reporting, and static adapter qualification paths were re-audited; a new real-install/mod qualification run remains user-local input and cannot be fabricated from this checkout. Heuristics are never auto-tuned. |
| 47 — Release and explanation polish | Complete with limitations | Scenario cards now have origin-aware comparison and an explicit guard against using the ordinary Fleet Support generator; the separate Scenario Fit action revalidates declared targets. Release docs cover both Windows and Linux artifacts. |
| 48 — Public repository hygiene | Complete with limitations | Public README, GPL-3.0-only license/NOTICE, documentation index, issue forms, and scoped Windows/static-analysis CI have been added. Full-repository Ruff and mypy are intentionally deferred: the inherited baseline has 215 Ruff findings and broad mypy errors, so CI gates critical syntax errors plus the newly typed public advisory boundaries without masking that debt. |
| 49 — Cross-platform release publication | Complete with limitations | Tag-driven CI builds and smoke-tests Windows and Linux artifacts, then attaches both archives and checksums to one release using the repository token. Manual dispatch keeps artifacts for inspection but does not publish. Hosted tag-run success is now confirmed by multiple completed CI runs (for example `v0.1.0RC3`); broader Linux desktop runtime testing remains external verification. |

| 50 — Release verification and evidence | Complete with limitations | Settings / Export verifies a supplied ZIP/tar archive, optional adjacent checksum, and package inventory without extraction or execution. It cannot prove hosted publication success or runtime behavior. |
| 51 — Local calibration workspace | Complete with limitations | Settings / Export evaluates local hash-bound labels against the loaded read-only scan and reports match/mismatch/stale/unsupported counts. It does not write reports, labels, or heuristic values. |
| 52 — Local recommendation feedback | Complete with limitations | Faction records explicit feedback only under the configured output directory. It is never automatically applied to legality, ranking, score, confidence, or heuristics. |
| 53 — Explainability comparison | Complete with limitations | Faction compares two or more specified Hull + BuildArchetype Why-Not records using backend-generated evidence only. It does not rerank paths or make outcome claims. |
| 54 — Player-suitability semantics | Decision-gated | `player_suitability` is presently a compatibility placeholder. Define its evidence and vocabulary before changing behavior; do not infer player skill or combat outcomes from static data. |
| 55 — Linux compatibility matrix | Complete with limitations | `docs/LINUX_COMPATIBILITY_MATRIX.md` records the local qualification protocol and unverified Ubuntu/Mint/Fedora boundaries. Native archive smoke evidence is distinct from broader desktop/distribution runtime qualification. |
| 56 — Campaign-save parser preparation | Decision-gated | Keep direct metadata discovery only until a documented, read-only save format and a normalized campaign data contract exist. No content parsing or campaign inference is authorized before that gate. |

## Latest implementation note

The Scenario Advisor now saves and restores only user-declared locked
selections, capability targets, pressures, and advisor constraints. Scenario
recommendation cards feed a separate **Generate Scenario Fit** action, which
re-runs the same scenario assessment and accepts only a currently shortlisted
candidate before invoking the ordinary bounded generator. Generated variants,
not the scenario card, retain normal validation results. The GUI shows an
indeterminate progress dialog for scenario evaluation and fit generation. Its
**Stop Waiting** action safely suppresses result delivery but does not claim
to interrupt the backend: no safe cooperative checkpoints currently exist in
those deterministic analysis calls, so the read-only work finishes before its
thread is released.

## Campaign-save boundary

**Implemented:** user-selected campaign-save directory metadata enumeration
only. It does not guess locations, recurse, follow links, mutate entries, or
interpret inventory.

**Not implemented:** campaign-save content parsing. Until a documented,
read-only save format can be supported without guessing, no save contents are
interpreted. The normalized hull schema currently has no deployment-point
field, and the application has no parseable campaign officer/skill state.
Existing knowledge-pack officer notes remain presentational guidance only.
These gaps cannot be converted into recommendation or combat-outcome claims.

## Engineering constraints

- See `AGENTS.md` for repository, source-safety, and distribution boundaries.
- See `FORMAL_SPECIFICATION.md` and `DATA_SCHEMA.md` for contracts.
- See `GAP_RECOMMENDATION_ENGINE.md` for recommendation behavior and
  `docs/FLEET_SUPPORT_ADVISOR.md` for Fleet Support scope.
- New heuristic changes require a versioned heuristic set, rationale,
  documentation, and regression coverage.
- Unknown scripted or runtime-dependent behavior remains unknown; it must not
  be guessed into legality or quality.
