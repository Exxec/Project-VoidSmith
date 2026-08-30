# Pre-GUI Limitations Resolution Report

Date: 2026-08-23

## Readiness conclusion

The backend is suitable for a GUI foundation. Its public service layer is
`starsector_variant_generator.api`; the GUI should call that layer and render
its structured results. It must not reimplement scanning, validation,
generation, scoring, ranking, or explanation.

The remaining limitations are evidence boundaries, not reasons to block a GUI
shell. Each item below has a safe resolution path for a later backend slice.

## Distribution boundary

The distributable project ships no core-game or mod content. Runtime facts are
scanned from the user's installation; reports, caches, exports, locally
selected benchmark manifests, and generated benchmark fixtures remain local.
Bundled examples and tests are neutral synthetic/schema material only.

## Pre-GUI corrections completed

| Finding | Resolution |
|---|---|
| `baseline_0.7` was documented but not the normal runtime default. | `AppConfig` and the example configuration now default to `baseline_0.7`. |
| Stage-aware recommendation could not be exactly reproduced by Why-Not. | `why-not --campaign-stage` now requires `--build-archetype` and propagates the stage through the same build-path ranking. |
| GUI roadmap wording still described contracts as actively growing. | Phase 17 now records the API boundary as stable enough for GUI foundation work. |

## Evidence-driven backend backlog

| Limitation | Safe resolution | Required input / contract | Success criterion | Scope risk |
|---|---|---|---|---|
| Unknown scripted hullmod/system behavior | Expand the versioned API-effect registry and per-mod adapters from local source/config evidence; preserve unresolved remainder as `UNKNOWN_SCRIPTED_EFFECT`. | Readable local source or an explicit adapter/override with provenance. | Every modeled effect has file/class/API evidence and tests; no code is executed. | Low if adapter-isolated. |
| Incomplete capability-to-recommendation mappings | Add one mapping at a time only where `CapabilityVector` dimensions and a viable `BuildArchetypeProfile` share direct normalized evidence. | Fixture demonstrating source evidence and an explainable objective mapping. | Gap, recommendation score, and Why-Not expose the same stored dimension evidence. | Medium; avoid role-name guessing. |
| AI/player suitability unavailable | Introduce an optional typed `ControlSuitabilityEvidence` contract only for documented static signals. | Parseable source fields or adapter evidence; no combat-simulation claim. | UI shows `UNKNOWN` when absent; recommendations never fabricate AI behavior. | Medium. |
| Universal equipment availability unavailable | Parse only standardized availability fields/tags when present; add adapter/override support for mod-specific schemes. | Local metadata schema or adapter evidence. | `STANDARD`/`RARE`/etc. includes provenance; otherwise remains `UNKNOWN`. | Low. |
| Refit AI/survey/salvage improvement modes unavailable | Implement only after a normalized target metric is evidenced. Keep present modes and no-silent-rebuild behavior unchanged. | Reliable per-ship metric, not names, cargo ratios, or assumptions. | Candidate moves remain independently legal and measured against a documented metric. | Medium. |
| Calibration lacks ground truth | Build opt-in local benchmark captures and reviewer-labelled fixtures that do not commit game data. Tune only through new heuristic identifiers. | User-owned local fixtures or explicit review labels. | Before/after benchmark report, rationale, regression anchors, and no change to historical heuristic output. | Medium. |
| Result cache has no automatic reuse | Have each API operation declare its full source hashes, heuristic set, adapters, overrides, constraints, pack freshness, and dependency targets. Enable cache per operation. | Explicit dependency-context interface and invalidation tests. | Changed entity recomputes only dependent reports; missing context fails closed to recompute. | Medium. |
| Change impact is conservative | Add dependency edges for every newly supported effect/config reference and retain an `UNKNOWN_REFERENCE` edge for opaque scripts. | Parser/adapter provenance extension. | Impact report names exact invalidations plus conservative unknown impacts. | Low. |

## GUI implementation guidance

1. Start with a thin application shell and service-call adapters.
2. Render `LEGAL` / `ILLEGAL` / `NOT_DETERMINABLE` distinctly; do not turn a
   warning, score, or confidence value into legality.
3. Render unknown evidence as unknown, with provenance and reports linked.
4. Keep long scans, report writes, and export writes explicit user actions.
5. Add GUI contract tests around `api.py` result serialization before each
   workspace binds to a new backend service.

## Explicitly deferred

- Combat simulation, save-state inference, whole-fleet optimization, and
  internet/runtime AI dependencies remain out of scope.
- External research may improve an adapter or API registry during development,
  but must never become an application runtime dependency.
