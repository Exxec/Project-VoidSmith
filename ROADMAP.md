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

## Next priorities

1. Finish the scenario workflow with clear diagnostics, cancellation/progress
   feedback, and an explicit scenario-fit handoff. Portable Scenario Advisor
   request snapshots now preserve only user-declared locked selections,
   capability targets, pressures, and advisor constraints; they never embed
   scanned game/mod data.
2. Define a safe, read-only campaign-save discovery boundary. Do not add
   campaign mutation, inventory planning, or undocumented save semantics.
3. Evaluate bounded officer and deployment-point advisory views only where
   parseable evidence supports them; keep them separate from legality and
   combat-outcome claims.
4. Continue calibration and generic mod qualification using local,
   hash-bound, ignored fixtures. Add adapters only for supported, genuinely
   mod-specific static semantics.
5. Improve release clarity, portable-build verification, and GUI explanation
   paths without broadening into whole-fleet optimization.

## Engineering constraints

- See `AGENTS.md` for repository, source-safety, and distribution boundaries.
- See `FORMAL_SPECIFICATION.md` and `DATA_SCHEMA.md` for contracts.
- See `GAP_RECOMMENDATION_ENGINE.md` for recommendation behavior and
  `docs/FLEET_SUPPORT_ADVISOR.md` for Fleet Support scope.
- New heuristic changes require a versioned heuristic set, rationale,
  documentation, and regression coverage.
- Unknown scripted or runtime-dependent behavior remains unknown; it must not
  be guessed into legality or quality.
