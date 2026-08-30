# Implementation status audit

This is an evidence-based status record, not a declaration of version 0.1 completion.

**Fitting-canvas coordinate and provenance polish (2026-08-26):** corrected
the shared Starsector mount transform: forward/lateral `.ship` coordinates now
map to the canvas's upright hull art rather than being drawn quarter-turned.
Conventional `.wpn` `turretSprite`/`hardpointSprite` metadata is retained as
optional local preview evidence, so selecting a weapon renders its available
static art at the mount while missing/non-standard art safely retains the slot
marker. The Ship browser now has independent **Source Mod** and **Faction**
filters; the latter uses parsed faction `knownShips` membership and visibly
labels unknown affiliation instead of equating a mod with a faction.
The normalized source-snapshot cache schema was incremented so the next scan
refreshes the new optional weapon-art metadata rather than reusing snapshots
created before that field existed.
Skin-derived hulls now retain their base hull's parsed geometry and source
provenance for the same read-only renderer, addressing a distinct blank-preview
case without assigning skin art or source ownership by guesswork.

**Carrier/decorative canvas filtering (2026-08-26):** visible fitting mounts
now exclude parsed `LAUNCH_BAY`, `HIDDEN`, and `DECORATIVE` anchors. Those
records remain available to validation and structural reporting, but no longer
appear as floating selectable weapon boxes. Canvas and Inspector counts now
separate selectable weapon mounts from launch bays.

**Carrier-bay side stack (2026-08-26):** carrier launch-bay structure is now
shown as a compact, non-selectable **Fighter bays** stack beside the hull,
with parsed bay IDs and declared capacity. This preserves the visual context
of the refit screen without treating launch-point coordinates as weapons or
claiming editable fighter-wing fitting.

**Canvas navigation/preview polish (2026-08-26):** the fitting view now hides
persistent scrollbars while retaining drag panning and zoom controls. Candidate
preview rendering now receives the normalized weapon index too, allowing
selected generated builds to show any available static weapon art just like a
manually selected fit.

**Lock-tolerant one-file build (2026-08-26):** `tools/build_gui_exe.ps1` now
stages PyInstaller output outside `dist`, publishes a non-overwriting versioned
`VoidSmith-<version>.exe` artifact (with a `-rebuildN` suffix when necessary),
and only refreshes the familiar `dist/VoidSmith.exe` path when Windows permits
it. A running legacy executable therefore no longer turns a successful rebuild
into a failed one. `-NoVersionBump` was verified by building
`VoidSmith-0.1.19.exe` from the locked dependency set and, with the legacy
file held open, publishing `VoidSmith-0.1.19-rebuild1.exe` successfully.

**Product rename (2026-08-23):** the application is now **VoidSmith**. The
distribution, desktop title, executable build output, compatibility-mod
metadata, and primary `voidsmith` / `voidsmith-gui` commands use that name.
Existing `svg` / `svg-gui` command aliases and the internal Python package
namespace remain for local workflow compatibility; GUI preferences migrate
from the former namespace.

**Authoritative latest verification:** 2026-08-23 — **342 tests passed, 1
optional local benchmark skipped** with `.venv\\Scripts\\python.exe -m unittest
discover -s tests -v`. This includes the Complex Hull Acceptance Matrix and
batch-audit checks, which use the repository's `unittest` discovery convention.
Ruff, mypy, source-level GUI smoke testing, and the packaged executable's
`--smoke-test` also pass.

**Current project verification (2026-08-23):** the full project verifier
reports **365 tests passed, 1 optional local benchmark skipped**, including
the GUI syntax, unit, and offscreen smoke checks. Static compilation and
whitespace checks also pass. This supersedes the older 342-test count above.

**Portable release automation (2026-08-23):**
`tools/build_portable_release.ps1` builds a versioned
`VoidSmith-<version>-win-x64` PyInstaller onedir directory, verifies it before
and after ZIP extraction, inventories package files in
`release-manifest.json`, and writes a ZIP SHA-256 file. It bundles only the
application plus Python/Qt runtime/dependencies: no installer, registry
change, admin requirement, Starsector installation, mod asset, scan, report,
sprite, knowledge pack, or benchmark is included. Code signing remains
optional and deferred.

**Portable release validation optimization (2026-08-23):** ordinary locked
portable builds now reuse PyInstaller dependency-analysis state; `-Clean` and
`-FreshAnalysis` retain explicit reproducible fresh-build paths. The package
collects only imported PySide6 modules and required plugins, not unrelated Qt
bindings. The isolated `dist\\release-optimized\\VoidSmith-0.1.0-win-x64.zip`
validated both in-place and extracted GUI smoke tests, manifest inventory, and
SHA-256 (`a5849d73d42da9ff88b8798bf8f772ce93646b8f8a0d50e58883d00338312dc4`),
with no game/mod content bundled. Archive retry handling now tolerates brief
post-smoke Windows file locks without changing package inputs.

**Locked release materialization (2026-08-23):** PySide6 and the pinned
`PyInstaller 6.22.2` release group are recorded in `uv.lock`. A permitted
bootstrap build materialized that exact graph and completed both release smoke
tests. Ordinary portable builds call `uv sync --locked --offline` and
`uv run --locked --offline --no-sync`; a missing cached artifact produces a
clear failure rather than a network resolution or version drift. The offline
preflight was verified after materialization.

**Complex-hull acceptance (2026-08-23):** the tested
`COMPLEX_HULL_ACCEPTANCE_MATRIX` now distinguishes structural markers and
separate local-module fitting from unsupported parent-child composition,
repetition/asymmetry, independent shields, destruction, detachment, and
scripted behavior. No composite mechanics are simulated; material unknowns
remain `NOT_DETERMINABLE` or `UNKNOWN_SCRIPTED_EFFECT`.

**Composite structural profiles (2026-08-23):** parent variants with declared
module maps now produce local-only `CompositeHullProfile` / `ModuleProfile`
records. These retain each parent slot, child reference, ambiguity state,
repetition/asymmetry, and station marker without merging module weapons,
systems, shields, destruction, legality, score, or survivability into the
parent. The complex-hull audit exposes those structural records only in its
local report. The shared `EvidenceClass` vocabulary is also now a first-class
field of `EvidenceRecord`; local Java hullmod effects are marked
`LOCAL_SOURCE_CODE`. Broader producer migration remains in progress.

**Calibration expectation kinds (2026-08-23):** hash-bound local calibration
labels now identify build, equipment, faction, scenario, or negative
expectations. A negative expectation matches only when the actual result is
outside its forbidden set, allowing regressions to express “should not normally
recommend” without overfitting an exact alternative. Labels remain reviewer
evidence and never tune heuristics automatically.

**Complex-hull batch audit (2026-08-23):**
`tools/audit_complex_hulls.py` now scans the enabled loadout and all installed
mods in separate read-only passes, writing local reports only under the chosen
output directory. A live run completed both passes without a crash or
composite-evidence leak. Its ambiguous/missing child and nonstandard-hint
findings remain warnings within the matrix boundary, never inferred gameplay
facts.

**GUI polish (2026-08-23):** the fitting canvas now resolves declared local
sprites read-only (with a geometry fallback), packs source-driven slot callouts,
supports pan/zoom/fit, and marks module-bearing hulls as non-composite. Backend
generation controls, selectable candidate previews, Retrofit-to-Hull navigation,
and compact provenance drill-down complete the current GUI polish slice.

**GUI scan workflow (2026-08-23):** Settings now presents an indeterminate
read-only scan progress dialog, an honest `Discard Results` action, and a
compact local scan/report summary. Discarding does not falsely claim to kill
the scanner; it completes safely and its outcome is simply not adopted. The
repeatable `tools/verify_gui.ps1` batch verifies GUI syntax, bridge/canvas/
presentation/session tests, and offscreen instantiation.

**Initial-scan optimization (2026-08-23):** the scanner now reports aggregate
`DISCOVERING`/`PARSING`/`RESOLVING_REFERENCES`/`COMPLETE` progress with timing,
source, and relevant-hash workload metrics. The GUI displays those worker-thread
updates without adopting scanner logic. Discovery reads enabled-mod metadata once
per run, and weapon-spec enrichment is bounded to the current source rather than
re-walking all prior weapons for every installed mod. `tools/profile_scan.py`
records repeatable local aggregate timings only under a selected output path;
normal scans now use output-local hash-verified per-source normalized snapshots
and bounded threaded parsing with stable source-order merges. Invalid, missing,
or changed snapshots fail closed to parsing; source files remain read-only.
The presentation layer uses lazy `QTableView` models rather than bulk
`QTableWidget` item creation, leaving scan adoption and main ship workflows
immediately available. Candidate/recommendation result reuse and process-based
parallelism remain deferred until their complete contracts and a measured
CPU-bound hotspot justify them.

**Measured source-snapshot optimization (2026-08-23):** against the local
119-source / 12,637-input-file installation, a cold scan measured 19.76s and
the second hash-verified binary-snapshot scan measured 6.67s (66% faster).
The scanner hashes 22.6 MB of relevant input on both passes; cached normalized
records avoid CSV/JSON/ship parsing, not source safety checks. An 18.25s serial
cold baseline outperformed two-worker (18.57s) and eight-worker (19.76s)
parsing on this disk-bound installation, so serial remains the default and
bounded parallelism is explicit benchmark/tuning infrastructure rather than a
blindly enabled setting.

**GUI control-surface completion (2026-08-23):** the Refit workspace now
exposes the actual supported quality modes, target profile, all four existing
substitution policies, and explicit mount/hullmod/fighter lock sets. Generated
candidate selection now has `Open Selected in Advanced`: it preserves the
selected candidate on the canvas and maps its backend profile into Advanced
controls without silently regenerating. No GUI control claims unsupported
AI/survey/salvage refit behavior.

**Safe report-cache consumer (2026-08-23):** scan-time analysis reports now
reuse only after a complete report-input fingerprint matches. In addition to
the normalized scan manifest and active heuristic/API-registry versions, that
fingerprint hashes `.ship`, `.wpn`, `.skin`, `mod_info.json`, and local Java
evidence under active sources. Missing entity hashes, old manifests, deleted
outputs, or any changed input force recomputation. This completes safe
whole-report-set reuse; per-entity/subgraph reuse is still intentionally
unwired until every producer declares a narrower complete context.

**Selective hull-profile reuse (2026-08-23):** hull mechanical, build, and
capability reports now declare their own narrow dependency contexts: the hull,
its existing variants, and the resolved weapons/hullmods used by those variants.
An unrelated hull modification reuses an unaffected profile; absent source
hashes, changed referenced equipment, or malformed/missing prior output force
only that profile to recompute. Aggregated equipment reports remain
whole-report recomputed pending equally explicit dependency declarations.

**Selective faction-report reuse (2026-08-23):** capability and doctrine
reports now separately fingerprint each faction, its resolved known hulls,
relevant existing variants, and referenced equipment. A change to another
faction does not invalidate both reports for an unaffected faction. Aggregate
equipment documents remain whole-report outputs because their present schema is
global by design.

**Selective hullmod-source reuse (2026-08-23):** local Java hullmod analysis
now persists one cache fragment per source mod and rebuilds the existing
aggregate report from those fragments. A fragment is reused only when its
hullmod rows, local Java hashes, heuristic set, and versioned API-effect
registry agree exactly; a changed mod does not re-analyze other mods.

**Selective equipment-profile reuse (2026-08-23):** direct weapon and parsed
hullmod classification output now persists source-mod fragments and rebuilds
the established aggregate JSON reports from them. Unchanged source mods are
reused only with complete entity hashes; the aggregate file format remains
compatible for report/UI consumers.

**GUI responsiveness (2026-08-23):** hull-name filtering is now debounced to
avoid rebuilding large browser lists on every keystroke. Background analysis
adoption is token-gated: an older immutable backend result cannot overwrite a
newer request. This complements the existing worker-thread boundary and does
not claim unsafe cancellation of a backend operation.

**GUI live-fit bridge (2026-08-23):** manual slot changes now refresh a
backend-owned fit summary in the Build Inspector, exposing legality and
weapon-OP used/remaining without a duplicate Qt legality calculation.
`tools/verify_project.ps1` batches the full regression suite with GUI syntax,
focused bridge/canvas/presentation/session tests, and the offscreen smoke test.

**GUI functional phase checkpoint (2026-08-23):** slot selection calls
backend-authoritative eligibility with explicit hidden/restricted visibility
and Strict Faction filtering; generation receives the selected faction as
well. The canvas marks selected logical weapons at parsed mounts when weapon
art metadata is unavailable, and fit preferences persist. Exact weapon-art
rendering, inline callout combo boxes, weapon-group editing, and unmodeled
flux/AI metrics remain explicit presentation/contract limitations rather than
GUI-side guesses.

**Scenario-objective build phase (2026-08-23):** `BuildArchetypeProfile`
now carries normalized `ScenarioObjective` records with `SUPPORTED`,
`PARTIAL`, or `UNSUPPORTED` state. Existing deterministic profiles support
line holding, screening, long-range pressure, missile/carrier projection, and
breakthrough where their signals are already modeled. Anti-armor and
target-class objectives remain explicitly unsupported until normalized combat
evidence exists; they do not silently bias the optimizer.

**Evidence-class migration phase (2026-08-23):** `EvidenceClass` now travels
through mechanical/build archetypes, capability-vector evidence, capability
gaps, and Native/Retrofit/Acquisition recommendation records. Local Java
hullmod evidence remains `LOCAL_SOURCE_CODE`; deterministic derived records
are `INFERRED_MECHANICS`. The machine-readable class supplements, rather than
replaces, existing textual evidence and cannot affect legality or scores.

**Cache/calibration state (2026-08-23):** selective reuse is
`FOUNDATION_COMPLETE / CONSUMER_WIRING_IN_PROGRESS`: every consumer must opt
into `CACHE_SAFE` with a complete operation fingerprint, while incomplete or
disabled contexts fail closed to recomputation. Calibration is
`FRAMEWORK_COMPLETE / LOCAL_EVALUATOR_AVAILABLE / AWAITING_REVIEWER_LABELS`:
`tools/evaluate_local_calibration.py` now scans a user-selected installation
read-only and evaluates only unambiguous source-qualified build labels against
the best legal inferred build. Ambiguous IDs, unsupported expectation kinds,
and absent legal builds are reported as `UNSUPPORTED`; the tool neither writes
labels nor tunes heuristics automatically. Superseded by the 2026-08-25
Calibration Activation entry below: the "awaiting labels" framing turned out
to already be stale -- real hash-bound labels existed on disk, unevaluated,
before this session's activation pass.

**Reviewer milestone import (2026-08-23):**
`tools/import_milestone_calibration.py` converts only unambiguous named
milestone-table hull roles into hash-bound `SOFT_EXPECTATION` labels. It keeps
unmatched or ambiguous names out of the fixture and reports them for review.

**Scenario-profile calibration resolution (2026-08-23):** the local-only
resolver now accepts both record-oriented guides and richer ship/scenario
profiles. It preserves `SOURCE_EXPLICIT` weapons, hullmods, raw loadout text,
scenario basis, review status, and mixed-fleet context separately from legal
`INFERRED_SCENARIO_OPTION` candidates generated from a local scan. Text-only
equipment matching rejects one- and two-character names to avoid accidental
prose matches; unresolved source mentions remain visible. A live local pass
resolved 44 unambiguous scenarios and conservatively skipped 236 ambiguous or
unresolved hull references. The generated report is local output, not a
distributable benchmark, and its unrestricted inference policy never asserts
faction ownership.

**Latest local verification:** 2026-08-23 — **314 tests passed, 1 optional
local benchmark skipped** with `uv run --no-project --with-editable . python
-m unittest discover -s tests -q`.

**Hullmod static-analysis integration (2026-08-23):** `svg scan` now writes
the source-mod-grouped `reports/equipment/hullmod_source_analysis.json` as a
normal scan artifact. Local Java files are indexed once per source root, and a
CSV-declared script class wins over a weak hullmod-ID reference. Recognized
effects carry shared `EvidenceRecord` file/class/line provenance; unresolved
script portions remain `UNKNOWN_SCRIPTED_EFFECT`. A read-only local Arma
Armatura scan completed successfully: 145 parsed hullmods, 120 declared-class
associations, and 24 recognized effects across 11 hullmods. This is local
audit output only and ships no game or mod content.

**All-installed-mod diagnostic (2026-08-23):** the read-only
`svg scan --all-installed-mods --summary-only` path now validates disabled as
well as enabled installed mods without writing to game data or paying for
optional per-entity reports. It scanned 148 installed mods (6,534 hulls,
7,362 weapons, 1,013 fighters, 2,846 hullmods, 8,344 variants, and 544
factions). The CP-1252 JSON fallback fixed one real legacy `.ship` parsing
failure. The final scan preserves 8 genuinely malformed/concatenated source
files as errors and 2 unresolved/ambiguous skin warnings. **Final regression
verification: 317 passed, 1 optional local benchmark skipped.**

**Compact diagnostics and report reuse (2026-08-23):** `--summary-only` now
omits raw entities and verbose change/registry records; the 148-mod local
diagnostic summary fell from approximately 123 MB to 2.9 KB, with a separate
172-byte aggregate impact file. Normal reports persist a deterministic local
manifest and are reused only after an unchanged source-hash scan, matching
heuristic set, and complete output-file check. A second enabled-mod scan
verified `REUSED_UNCHANGED`. **Latest full verification: 320 passed, 1
optional local benchmark skipped.**

**Diagnostic classification (2026-08-23):** compact scan output now reports
only conservative aggregate categories. The final all-installed scan reports
7 `MALFORMED_OR_CONCATENATED_DATA`, 1 `MALFORMED_VALUE`, 1 unresolved skin,
1 ambiguous skin, and 3 stale enabled-mod references. It does not attempt
source recovery or label malformed data as supported. **Latest full
verification: 321 passed, 1 optional local benchmark skipped.**

**Stable source keys (2026-08-23):** CSV rows lacking an actual stable ID are
recorded as skipped instead of being collapsed onto filenames such as
`wing_data`; legitimate same-ID entities at different source paths are no
longer impact conflicts. Change-impact keys now include source path. This
preserves provenance and avoids unsafe fallback identities, while leaving the
original local source unmodified. **Latest full verification: 324 passed, 1
optional local benchmark skipped.**

**Latest local verification:** 2026-08-23 — **310 tests passed, 1 optional
local benchmark skipped** with `uv run --no-project --with-editable . python
-m unittest discover -s tests -q`.

Historical verification totals below are retained as work-log context only;
the full suite above is authoritative.

**Current implementation note (2026-08-23):** knowledge-pack progression
tiers, officer guidance, and retrofit-template references are now consumed as
freshness-adjusted advisory output. `baseline_0.7` gives a selected progression
tier a small preference only after a native Hull + BuildArchetype path is
mechanically viable. Equipment query output now exposes explicit local
availability evidence while preserving `UNKNOWN` when no universal source field
exists.

**Latest local verification:** 2026-08-23 — **307 tests passed** with
`uv run --no-project --with-editable . python -m unittest discover -s tests -q`.
Adapter-backed mobility effects now appear in variant analysis and enrich
Mobility capability evidence only for verified existing-variant effects.

The read-only Change Impact Analyzer now classifies hash-based canonical entity
changes and plans direct affected analysis targets. It establishes the
invalidation contract, exports `reports/change_impact.json` during scan, and
marks knowledge-pack freshness impacts; it intentionally does not cache or
recompute results.

An output-directory SQLite analysis-result cache now requires exact versioned
context hashes and supports exact impact invalidation. It has no automatic
consumer yet, avoiding unsafe reuse before complete dependency contexts exist.

`DerivedShipState` now aggregates the verified civilian, defense, and mobility
adapter slices for variant analysis, retaining unapplied unknown hullmods and a
separate evidence-completeness summary.

The verified Insulated Engine Assembly hull-integrity bonus is now included in
the DEFENSE adapter. Its engine durability and sensor effects remain unknown to
the static model rather than becoming invented derived values.

**Current local verification:** 2026-08-23 — **290 tests passed** with
`uv run --no-project --with-editable . python -m unittest discover -s tests -q`.

## Current implementation snapshot

Complete or materially complete: deterministic scanning/normalization,
three-state legality, bounded generation, mechanical hull archetypes,
non-exclusive build archetypes, read-only scan reports, Native/Retrofit/
Acquisition recommendations, within-hull diversity collapse, build-specific
Why-Not, and Git repository hygiene.

Why-Not carries the corresponding numerical Retrofit and Acquisition
components (quality/change-cost; capability/affinity/score) in addition to the
native build trace. Ship-system IDs remain provenance-only until documented
adapter contracts can support an effect safely.

Selected build-aware recommendations now expose their exact stored per-leg
components, including retrofit disruption/role distortion and acquisition
incremental gain. Non-selected Retrofit/Acquisition paths are not simulated
solely to create explanatory evidence.

Partial: hullmod/system effect coverage, AI/player suitability, full
uncertainty coverage for unrecognized mechanics, and calibration volume. The
richer capability-vector model, role-distortion/retrofit-disruption,
campaign-stage constraints, and functional GUI workspaces are implemented.
Reviewer-label calibration infrastructure is available but has no shipped
third-party labels. Build-aware scoring currently includes directly parsed PD
coverage and missile pressure only for their matching profiles under
`baseline_0.5`. `baseline_0.6` additionally records capability-vector gap
evidence, build/posture-aware diversity, propagated build/access confidence,
and bounded retrofit disruption. Unknown/scripted mechanics remain unmodeled.

**Last local verification:** 2026-08-23 — 360 tests passed, one optional
local canonical benchmark skipped, via
`powershell -ExecutionPolicy Bypass -File tools\verify_project.ps1`.

**GUI general pass and drag-and-drop mod loading (2026-08-23):** fixed two
real crashes in the Retrofits workspace ("Improve Role Match"/"Compare
Before / After" called the backend with a non-existent refit mode/profile,
raising `ValueError: Unknown profile: LINE` on every click) and a real
staleness bug (`_generate`/`_export_current` hardcoded the literal
`"baseline_0.2"` instead of the configured `AppConfig.heuristic_set`,
silently scoring every GUI generation/export five heuristic versions behind
the CLI default). Added a disabled-button stylesheet rule and removed dead
signal-reconnect churn on the hull search field. Diagnosed and fixed a real
GUI-test isolation gap: `tests/test_gui_canvas.py` read/wrote the actual
OS-native `("VoidSmith", "Desktop")` `QSettings` store -- the same one a
real installed copy uses -- so a test leaving non-default state and calling
`window.close()` leaked into whichever test constructed the next
`MainWindow()`; now isolated to a per-class temp `.ini` file plus a
per-test clear.

Added drag-and-drop mod loading: dropping a mod folder or `.zip` archive
anywhere onto the main window adds it to the next scan's source pool
alongside the normal core + enabled-mods set
(`AppConfig.extra_mod_paths` -> `core/scanner.py::Scanner.extra_mod_paths`,
new `core/mod_import.py`), without requiring the mod to be installed under
`<starsector_path>/mods/` or listed in `enabled_mods.json` -- additive, not
exclusive, per explicit project-owner direction during implementation. A
dropped archive is extracted only into a program-controlled cache directory
under the configured output path (never beside Starsector or existing mod
sources); zip-slip path-traversal entries are rejected before any file is
written; re-dropping an archive with the same name refreshes the extraction
rather than leaving stale files. Live-verified against the real 148-mod
install: resolved and scanned a real installed mod folder as an "extra"
source end-to-end, 0 exceptions. 21 new tests.

**Scan lifecycle correctness (2026-08-24):** the GUI's background QThread
worker pattern had a real Python-level lifetime gap: `ScanWorker`/
`AnalysisWorker` instances existed only as local variables in
`_start_scan`/`_run`, with nothing keeping a strong reference to the Python
wrapper for the whole thread lifetime once the constructing method returned
-- `moveToThread` transfers the underlying Qt object's ownership but does
nothing to keep the Python side referenced. Fixed with explicit retention
(`self._scan_worker`, a thread-to-worker `self._active_workers` mapping for
the generic path), cleared only on the real terminal path
(`_scan_finished`/`_finish_thread`). Also reordered every terminal-signal
connection (`completed`/`failed`/`cancelled`) so `thread.quit` is connected
*before* the application-level handler, guaranteeing thread cleanup happens
regardless of what that handler does; added full-traceback logging
(`logger.exception(...)`) at both worker boundaries, where only the bare
exception message previously reached the log; added a stall-diagnostics
watchdog that logs last known stage/source/elapsed-time/thread-state if no
progress event arrives for 20s. A test methodology bug surfaced a genuine
PySide6 C++-level segfault (calling `_scan_finished()` manually while an
actual, still-running background `QThread` from an earlier `_start_scan()`
call was live) -- confirmed as a test artifact, not a production path
(`_scan_finished` only ever runs after a real `thread.finished`, which by
definition means the thread has already stopped), and fixed by never
racing a real background thread against manual terminal-state calls in
tests. Scan restart verified and regression-tested after success, failure,
and cancellation. Full suite: 496 passing, 1 skipped, 0 regressions, stable
across repeated runs. See `docs/WORK_LOG.md` for the detailed, dated record
of this and the many other passes since 378 (Mirror fitting, three separate
scan-progress-visibility fixes, incremental drag-and-drop, FLUX/COMBAT
hullmod modeling and their scoring/vent-cap wiring, an equipment-affinity
and a change-impact profiling win, and Gap Recommendation Engine
correctness fixes) -- this entry intentionally summarizes only the most
recent slice rather than backfilling all of them here.

**Live GUI scan reproduction (2026-08-24):** the scan lifecycle fix above was
reproduced end-to-end against the real 148-mod install, not just backend
scripts, by driving the packaged launcher with `pywinauto` (UIA backend).
Confirmed the progress dialog shows real, moving text (current directory,
recent-sources trail) rather than a static marquee, and the scan completed
cleanly: status bar read "Scan complete: 3012 hulls, 5 source errors." An
earlier apparent hang during this same investigation was root-caused as an
automation artifact, not a product bug: `voidsmith-gui.exe` is a thin
launcher stub that spawns a separate child process literally named `python`
which does the real work, so process-monitoring filtered on
`ProcessName -match 'voidsmith'` missed it entirely and made an
actively-completing scan look stalled.

**Heuristic-set consistency audit (2026-08-24):** audited every production
call path from GUI/CLI entry point through to scoring for silent reliance on
a hardcoded historical default instead of the caller's real configured
`heuristic_set`. Found and fixed 6 real gaps: `analyze_variant`/
`run_analyze_variant` and `run_faction_capability` both defaulted to
`baseline_0.2` regardless of the caller's actual setting; `_compare_refit`,
`_fix_legality`, `_improve_quality`, `_analyze_capability`, and
`_gap_recommendations` in the GUI all had the same hardcoded-default gap; and
`write_scan_analysis_reports` recorded the correct `heuristic_set` in report
provenance while computing faction-capability content under a stale one -- a
real manifest/content divergence, currently masked only because no scored
threshold has changed since `baseline_0.2`. All fixed to thread the real
configured value end-to-end, regression-tested against the real production
entry point (`test_run_analyze_variant_forwards_the_real_heuristic_set_end_to_end`).

**Portable release 0.1.10 (2026-08-24):** rebuilt and shipped, reflecting the
scan-lifecycle and heuristic-set-consistency work above. Independently
re-verified: `dist\VoidSmith-0.1.10-win-x64.zip` exists, its SHA-256
(`b57ac9c761b4f3e68761649935e35887c263edce9fd1fe4111a4b7bf2ebf6447`)
recomputed and matched byte-for-byte, `pyproject.toml` confirmed at `0.1.10`.
Packaging only; no source changed.

**GUI file overwrite incident and faction-merge bug fix (2026-08-24):** a
concurrent process sharing this repo overwrote `gui/main_window.py` and
`gui/ship_view.py` with an incomplete `PyQt6`-based rewrite -- not wired to
`app.py` (still `PySide6`), `PyQt6` not installed, so the GUI could not
import. Flagged to the user (a binding swap is also a real GPL/commercial
vs. LGPL licensing question) rather than silently reverted or continued;
user chose to restore `PySide6`. Restored from the surviving `.bak`
(verified: clean import, full suite green); the PyQt6 attempt was preserved
as `main_window.py.pyqt6-attempt.bak` rather than deleted. Separately fixed
SVG-015 (`docs/BUGS.md`): `core/registry.py::EntityIndex.build` silently
dropped any third-or-later entity sharing an already-duplicated id (verified
on the real install: the "hegemony" faction id alone has 24 real same-id
contributing mod sources, only 2 of which ever reached `duplicates`).
Rewritten to retain every claimant; `Registry.resolve_faction` now unions
same-id factions' known_* equipment lists (real declared evidence, nothing
fabricated) instead of raising "ambiguous" or silently using one incomplete
source. Live-verified via the real CLI: Hegemony's known-hulls count rose
from 37 to 108, correctly including a user-reported missing entry
(`jdp_arcubus` from `JaydeePiracy`). 14 new tests.

**Window-state persistence and a test-isolation fix (2026-08-24):** completed
the user's "remember window size / always start maximized" request --
`window/maximized` now persists alongside the existing size/paths/mode
preferences, defaulting to maximized on a genuinely first-ever launch.
Tracked via a `resizeEvent` override rather than Qt's `normalGeometry()`
(confirmed unreliable for this window). Also fixed a real, separate
pre-existing gap found while testing this: `tests/test_gui_canvas.py`'s
`QSettings` isolation had never actually worked (the 2-arg constructor
`main_window.py` uses hardcodes the real Windows registry regardless of
`setDefaultFormat`), meaning the whole test class had been silently
touching a real user's actual saved GUI preferences; fixed via a proper
constructor patch. Confirmed (not a bug): a user-reported "missing mod"
(Hazard Mining Incorporated) is correctly excluded because Starsector's own
`enabled_mods.json` has it disabled, not a scanning defect.

**Ship canvas weapon-slot redesign (2026-08-24):** per a user-supplied
reference mockup, the Fit tab's ship canvas now renders weapon mounts as
clickable, type-colored boxes directly on the hull sprite (BALLISTIC/ENERGY/
MISSILE/HYBRID-family/UNIVERSAL each a distinct color, sized by declared
mount size) instead of small uncolored dots with no interaction. Clicking a
box opens the same backend-filtered weapon picker the removed right-side
"WEAPON SLOTS" list used to trigger; built-in mounts render dashed and stay
unclickable. Visually verified by rendering a synthetic multi-type hull
off-screen and inspecting the image directly.

**Installed-mod acceptance sweep (2026-08-24):** Priority 3 of the agreed
roadmap. `analysis/mod_acceptance.py::audit_mod_acceptance(scan, registry)` is
a new pure, evidence-only diagnostic (mirrors `analysis/complex_hull_audit.py`
exactly: no legality import, no heuristic dependency) that classifies **every**
installed mod individually into `PASS`/`PASS_WITH_UNKNOWNS`/`PARTIAL`/`FAIL`
using only real scan/registry evidence -- entity counts, `EntityIndex.duplicates`
(now correctly reading the SVG-015-fixed many-contributors-per-id form),
`Registry.unresolved_references`/`missing_dependencies`, a fighter-wing
reference check filling a real gap `Registry._resolve_variants` deliberately
leaves uncovered, multipart/composite hull findings reused from
`audit_complex_hulls`, adapter usage and unknown-effect markers via
`derive_ship_state`, and free-text scan warnings/errors/skipped-entity
messages attributed by literal longest-match containment of each source's own
`ModInfo.path` (verified against `core/scanner.py`'s exact message formats,
not assumed). `tools/mod_acceptance_sweep.py` (argparse/output shape copied
from `tools/audit_complex_hulls.py`) writes one JSON report per scope plus a
stdout summary table; its output is never committed. 12 new synthetic-only
tests (`tests/test_mod_acceptance.py`) cover all four classifications, the
fighter-wing gap, both synthetic-`FAIL` recovery paths (unparseable
`mod_info.json`, enabled-but-not-discovered), and a regression guard that no
record classification ever takes a `LEGAL`/`ILLEGAL`/`NOT_DETERMINABLE` value.
Run against the real 148-mod-class install (both enabled-only and
all-installed scopes): 151 mods classified per scope (enabled-only:
87 PASS / 1 PASS_WITH_UNKNOWNS / 60 PARTIAL / 3 FAIL; all-installed, every mod
actually parsed: 61 PASS / 2 PASS_WITH_UNKNOWNS / 85 PARTIAL / 3 FAIL -- the
PASS-to-PARTIAL shift between scopes is disabled mods that were vacuously
clean with 0 parsed entities in the enabled-only scope revealing real defect
evidence once actually parsed, a documented characteristic of scope semantics,
not a bug). All 3 real FAIL mods in both scopes are the identical
`ENABLED_NOT_FOUND` case (a mod id enabled in the user's own
`enabled_mods.json` but absent on disk) -- an actionable real finding. Zero
free-text messages went unattributed in the real run.

**Ship canvas follow-up fixes from a real screenshot (2026-08-24):** the
user supplied a screenshot of their own running 0.1.12 install alongside
reference mockups. Comparing it against the code found two real bugs in the
just-shipped canvas redesign: leftover leader-line callout labels sprawled
far enough on a real 25-mount capital hull to force the view to zoom out
until the ship and its clickable mount boxes were barely visible (removed
entirely -- the boxes already carry the same information via color/size/
tooltip); and the in-canvas title text was invisible, painted over by the
sprite because it sat at the scene origin instead of above the sprite's real
top edge. Also added an `hull.name or hull.id` fallback after confirming
some modded composite-hull sub-modules genuinely declare no display name in
their real source data (not a parsing bug), which was making the hull list
show many identical, indistinguishable rows. Re-rendered the exact hull from
the screenshot off-screen after the fix and confirmed directly in the image
that all 25 mount boxes now render at a legible size with no sprawl.

**Weapon-mount coordinate fix, disabled-mods scan option, and canvas-priority
layout (2026-08-24):** fixed SVG-016 (`docs/BUGS.md`) -- weapon-mount boxes
were positioned wrong relative to the ship sprite (a real, previously
undetected bug: `location - center` was double-subtracting `center`, which
per the Starsector modding wiki's documented `.ship` convention is already
the reference point `locations` are relative to). Verified against three
real core hulls rendered off-screen (Wolf, Hammerhead, Atlas Mk.II); a new
regression test locks in the exact transform. Investigated a related user
report ("HMI faction not showing all its ships") and confirmed it's the
same root cause as an earlier finding (the mod is disabled in the user's
own `enabled_mods.json`), not a faction-merge bug -- added a real "Include
installed-but-disabled mods" checkbox to GUI Settings so this no longer
requires leaving the app. Implemented ROADMAP Phase 25: moved Generation
Controls/Generated Build Paths into a new "Generate" tab next to a renamed
"Inspector" tab, giving the ship canvas the majority of the center panel.
Added ROADMAP Phase 24 (scan-result persistence across GUI restarts,
NOT_STARTED) as the next tracked priority-list item.

**Auto-scan on launch (2026-08-24):** implemented Phase 24. Rather than a
new persisted-registry layer (a real risk against the "never trust stale
data" architecture guarantee), reused the scanner's existing per-source
hash-verified snapshot cache: a remembered, still-valid install path now
starts a real scan automatically on launch instead of waiting for a manual
click. Verified directly against the real 148-mod install before trusting
it: a warm scan (same cache, nothing changed) completes in 6.62s vs. an
18.69s cold scan, still re-verifying every source's hash. 5 new tests.

**Release/repo hygiene hardening (2026-08-24, ROADMAP Phase 36):** verified,
rather than assumed, that the release/source exclusion lists actually hold.
Every `cache/`/`logs/`/`reports/` directory produced by a real scan or
benchmark run (19 real cache dirs, 21 real logs dirs found on disk) is
nested under `generated/`, already covered by `.gitignore`. Found and fixed
a real gap: a loose repo-root `cache/` (22MB, including
`cache/analysis_results_bench.sqlite` and 148 real per-mod
`cache/source_snapshots/*.bin` files from a local benchmark run),
`scratch_out/` (42MB, the same real per-mod snapshot/manifest shape), and
`logs/svg.log` sat directly under the repo root, matched by no existing
`.gitignore` pattern -- reachable by a bare `git add -A`/`git add .`, and
exactly the "extracted scan output"/"real entity identifiers" content
`CONTRIBUTING.md`'s distribution boundary forbids committing. Fixed with new
anchored `/cache/`, `/logs/`, `/scratch_out/` patterns plus global
`*.sqlite`/`*.sqlite3`/`*.db` patterns (the latter also covering
`AnalysisResultCache`'s real file, `config.output_dir / "cache" /
"analysis_results.sqlite"` per `cli/main.py`, for any `output_dir` outside
the `generated/` convention). Confirmed `config/*.toml` already correctly
scopes only user-machine-specific TOML, leaving the committed
`config/heuristics.default.json` and `config/overrides/*.example.json`
untouched, and that the GUI's cache/log directories are always a
user-chosen path outside the repo by construction (`gui/main_window.py`'s
`_start_scan`), not a repo-tree concern. Read both packaging scripts
(`tools/build_portable_release.ps1`, `tools/build_gui_exe.ps1`): both copy
only PyInstaller's own dependency-graph output, never the source tree, so
there is no code path for a stray `__pycache__`/log/cache/DB file to enter
a release. Independently verified against the real already-built
`dist/VoidSmith-0.1.15-win-x64/` artifact: 113 files on disk (112 in
`release-manifest.json`, correctly excluding itself), zero matches for
`__pycache__`/`*.pyc`/`*.py`/`*.log`/anything containing "cache" or
"generated"/`*.sqlite`/`*.db`/`*.toml`; the packaged
`dist/VoidSmith-0.1.15-win-x64.zip` likewise (115 entries, 0 suspicious
matches outside `release-manifest.json`'s own filename). Code signing
remains explicitly deferred/optional per the charter and was not
attempted. No application code changed; `.gitignore` only.

**Complex/outlier hull acceptance stress tests (2026-08-24, ROADMAP Phase
26):** ran `tools/audit_complex_hulls.py` and `tools/mod_acceptance_sweep.py`
(`--scope both`) against the real local install
(`C:\Program Files (x86)\Fractal Softworks\Starsector`, 149 discovered mods)
targeting five structurally unusual real mods named by the charter: Hazard
Mining Incorporated (folder `Hazard Mining Incorporated-0.4.0e`, id `HMI`,
disabled in the user's own `enabled_mods.json` -- scanned via
`include_disabled_mods=True`/`--scope all`), Arma Armatura (`armaa`, enabled),
Alkemia Armoury (`alkemia-armoury`, enabled), Dassault-Mikoyan Engineering
(folder `Dassault-Mikoyan Engineering-1.9eHijacked`, id
`istl_dassaultmikoyan` -- this is the real mod behind "DME," disabled), and
Diable Avionics (`diableavionics`, disabled). All five real folder
names/ids were verified directly from each mod's own `mod_info.json` rather
than assumed. No crash, no executed mod code, and no legality claim occurred
in either tool across either scope; both are pure diagnostics
(`analysis/complex_hull_audit.py`, `analysis/mod_acceptance.py`) that never
import `validation/legality.py`. All five target mods classified `PARTIAL`
(real, attributed, evidence-cited findings -- never `FAIL`/a crash). HMI's
`hmi_locomotive` composite ship (the charter's specifically named
Locomotive/junker hull) was directly confirmed in
`complex_hull_acceptance_all_installed.json`'s `structural_profiles`: 5 real
child modules (`hmi_locomotive_fighter_left/right`,
`hmi_locomotive_gun_left/right`, `hmi_locomotive_rear`) resolved per real
variant (`armoured`/`attack`/`cs`/`std`/`lp`) at `confidence: 1.0`,
`analysis_state: STRUCTURAL_ONLY` -- composite structure fully preserved, not
flattened. The audit's own acceptance matrix confirms honest degradation by
design: `SCRIPTED_MODULE_BEHAVIOR -> UNKNOWN_SCRIPTED_EFFECT`,
`DESTROYABLE_SECTIONS`/`DETACHABLE_COMPONENTS`/`INDEPENDENT_SHIELDS ->
NOT_DETERMINABLE`, never a fabricated legality value.

Found and fixed one real, narrowly-scoped parser gap while inspecting the two
target mods that carried real parser errors (see SVG-017, `docs/BUGS.md`):
Diable Avionics 2.9.5.3's `diableavionics_IBBgulf.ship` uses a leading
unary-plus numeric literal (`"renderOrderMod":+30`), invalid JSON that the
existing HJSON-tolerance normalizer (`parsers/common.py::_relaxed_json`,
already handling bare-leading-decimals per SVG-014) did not cover, causing
that entire real hull file to fail to parse and be skipped. Fixed by
extending the same structural-character-anchored regex approach used for the
`.7`-style fix; verified against the real file (now parses, `hullId`
`diableavionics_IBBgulf` present) and against the whole 149-mod install
(exactly 1 real occurrence anywhere, confirming this was not a broader
pattern). DME's own parser error
(`6eme_bureau.faction: Extra data: line 332 column 1`) was independently
diff-verified as a genuinely malformed source file (36 `}` vs 35 `{`, a real
brace-count mismatch in the mod's own data, not a tolerable syntax
convention) -- correctly left as a reported error rather than guessed at,
consistent with SVG-014's precedent for the same distinction. 1 new
regression test (`tests/test_parsers.py::test_relaxed_json_accepts_leading_unary_plus_numbers`,
synthetic fixture only, no real mod data committed). Full suite: 540 passing
(539 + 1 new), 1 skipped, 0 regressions. See `docs/ROADMAP.md` Phase 26 for
the full charter wording and final status.

**Dependency-aware caching states (2026-08-24, ROADMAP Phase 33, charter
Priority 11):** the charter's ask was to make the result cache's existing
fail-closed reuse decision explicit and inspectable -- a real `CACHE_SAFE` /
`CACHE_UNSAFE_INCOMPLETE_CONTEXT` / `CACHE_DISABLED` status surfaced per
cache decision, not just an implicit hit/miss. Read the real cache/
fingerprint code end to end before designing anything (`core/result_cache.py`,
`generation/candidate.py`, `analysis/gap_recommendation.py`, `api.py`) and
found this was already partially built, not a from-scratch task: Phase 2's
own `CacheReadiness` enum (`CACHE_SAFE`/`CACHE_UNSAFE_INCOMPLETE_CONTEXT`/
`CACHE_DISABLED`) and `AnalysisContextFingerprint.readiness` already existed,
and the two real `AnalysisResultCache` consumers' fingerprint builders
(`candidate_alternatives_fingerprint`/`build_archetype_candidates_fingerprint`
in `generation/candidate.py`, `gap_recommendation_fingerprint` in
`analysis/gap_recommendation.py`) already computed `CACHE_SAFE` vs.
`CACHE_UNSAFE_INCOMPLETE_CONTEXT` correctly from real entity-hash
completeness. What was genuinely missing, confirmed by grepping every real
reference: `CACHE_DISABLED` was defined but never assigned anywhere, and the
`readiness` value itself was never surfaced past `AnalysisResultCache`'s own
internal `get_fingerprint`/`put_fingerprint` gating -- no caller or report
could see *why* a lookup did or didn't happen, only whether a cached value
came back. Also found the report-surfacing shape to reuse already
established in a separate, parallel mechanism: `output/analysis_reports.py`'s
scan-time report fingerprinting already writes a plain `"cache_readiness":
"CACHE_SAFE"/"CACHE_UNSAFE_INCOMPLETE_CONTEXT"` key into every report dict it
produces (9 call sites) -- confirming the target shape, though that
mechanism has no `CACHE_DISABLED` path of its own (every one of its calls is
unconditionally attempted, so that state doesn't apply there) and was left
untouched as out of scope for this phase (its report envelopes are per-scan
fragments, not `AnalysisResultCache` consumers).

Implemented the missing piece as a minimal, additive extension, not a
rewrite: `core/result_cache.py::resolve_cache_status(result_cache,
fingerprint)` is a small, directly-testable function computing the real
per-call decision (`CACHE_DISABLED` when no `AnalysisResultCache` instance
was supplied at all, otherwise the fingerprint's own already-computed
readiness). Threaded into all three real call sites named by the task:
`api.py::run_generate`'s two branches (build-archetype and plain
alternatives) and `api.py::run_gap_recommendations`. Followed this
project's established pattern for extending an existing return shape rather
than a breaking signature change (matching `GenerateOutcome`'s own prior
`build_candidates` addition and `GapRecommendationResult`'s prior
`officer_guidance`/`fully_unaddressed_gaps` additions, both trailing
default-valued dataclass fields): `GenerateOutcome` (api.py's own dataclass)
gained `cache_readiness: CacheReadiness = CacheReadiness.CACHE_DISABLED`,
always set from the real per-call decision in both branches.
`GapRecommendationResult` (`analysis/gap_recommendation.py`) gained the same
field with the same honest default -- `recommend_gap_solutions` itself never
touches a cache, so `CACHE_DISABLED` is correct for its own direct callers
without any code change there. `run_gap_recommendations` overwrites it via
`dataclasses.replace(result, cache_readiness=...)` after every lookup/store,
deliberately *not* trusting whatever value came back through the cache
payload round-trip (a stored payload reflects what was true when it was
written, not this call's real decision) -- confirmed this design requires
zero changes to `gap_recommendation_result_to_payload`/`_from_payload` or
any ranking logic in that file, staying inside this phase's stated boundary.
`cli/main.py`'s `svg generate` report gained an explicit `"cache_readiness"`
key mirroring `output/analysis_reports.py`'s established convention; `svg
recommend`'s report gets it for free via `asdict(result)` since
`GapRecommendationResult` now carries the field directly (a `StrEnum`,
confirmed via `asdict`+`json.dumps` to serialize as a plain JSON string,
same as `EvidenceClass` already does elsewhere in this file).

Verified the additive design against every existing cache-focused test
before writing anything new: all 26 tests in
`tests/test_gap_recommendation_result_cache.py` and
`tests/test_candidate_generation_result_cache.py` pass completely unchanged,
including the pre-existing `test_no_result_cache_argument_behaves_exactly_as_before`
equality assertions for both operations -- proof the new field's default
(`CACHE_DISABLED`) genuinely matches what a cache-naive direct call already
implicitly was, not a coincidence papered over by editing the test. New:
`tests/test_cache_readiness_states.py`, 14 tests, all three states produced
by real end-to-end `api.run_generate`/`api.run_gap_recommendations` calls
(covering both generation branches -- plain alternatives and multi-archetype
-- not just one), a direct unit test of `resolve_cache_status`, and an
explicit report-serialization check proving `cache_readiness` survives
`asdict`+`json.dumps` as a real string a report can state, not an opaque
Python attribute. Full suite: 560 passing, 1 skipped, 0 failures (the 14 new
tests plus several tests that landed from other concurrent work this
session per the environment's own concurrent-agent note; re-ran the
narrower cache-test slice both before and after every edit with 0 failures
throughout). `ROADMAP.md` Phase 33 marked `COMPLETE_WITH_LIMITATIONS`: the
limitation is scope, not an unresolved gap -- only the two real
`AnalysisResultCache` consumers were wired, and `output/analysis_reports.py`'s
separate scan-time mechanism intentionally keeps its own existing two-state
convention (`CACHE_DISABLED` doesn't apply to a path that's never actually
optional there).

**Change-impact graph extension (2026-08-24, ROADMAP Phase 34):** extended
`analysis/change_impact.py::_direct_impacts` with three new, additive,
evidence-only impact kinds alongside the existing Phase-2-optimized direct
reverse-indexed impacts, changing no pre-existing impact kind's output:
`faction_known_list` (a changed hull/weapon/hullmod/fighter id checked
directly against a real faction's own `known_*` tuple, independent of any
referencing variant -- closes a real gap where the pre-existing cascade only
ever produced faction evidence via a co-referencing variant, so a faction
that genuinely knows an id with zero current referencing variants, now more
common after SVG-015's same-id faction merge, produced none at all);
`knowledge_pack_reference` (a changed id checked against a pack's actual
curated content -- `hull_archetypes`/`retrofit_templates`/
`approved_equipment`/`progression_tiers`/`manifest.target_faction_id` --
deliberately distinct from the pre-existing `knowledge_pack_freshness` kind,
which only fires for ids the pack author explicitly hashed); and
`adapter_coverage` (a changed hullmod id checked for literal presence as a
`hullmod_id` field across all six real `adapters/vanilla` effect tables,
citing which table(s) matched, verified against a real table entry
`heavyarmor` rather than a synthetic placeholder). All three are
real-evidence-only, never inferred. 6 new synthetic-fixture regression tests
added; the existing golden-output regression test was additively updated
(one new `faction_known_list` entry the same fixture scenario now genuinely
produces, hand-re-derived rather than copied from the failure). Profiled a
synthetic-but-realistic stress scenario (431 factions matching the real
install's count, ~100-150 known-list entries/faction, 20 packs, 8,000
variants) before optimizing, per this session's standing discipline: found
the new `faction_known_list` check *and* a pre-existing, previously
unmeasured `_direct_impacts` hotspot predating this phase (`for faction in
scan.factions: if variant.hull_id in faction.known_hulls` inside the
variant cascade), both fixed with one reverse index per relevant category
built once per call (the same pattern as Phase 8's `_ownership_index`);
measured 1.21-1.28s -> 0.13-0.14s (~9x) on the stress scenario, output
byte-for-byte identical before/after (6,559 impacts, same per-kind counts).
`ROADMAP.md` Phase 34 marked `COMPLETE_WITH_LIMITATIONS` -- this is direct
(one-hop) evidence extension per the charter's three named categories, not
an arbitrary-depth transitive graph traversal, and `knowledge_pack_reference`
does not cover `officer_guidance`/`capability_gap_guidance`/
`build_archetype_preferences` (role- or build-id-keyed, not entity-id-keyed,
so none has a citable specific-entity reference to check). Full suite: 560
passing, 1 skipped, 0 regressions (6 of these are this phase's own new
tests; the session's confirmed 540-passing starting baseline plus Phase 33's
own concurrently-landed 14 new tests, `tests/test_cache_readiness_states.py`,
account for the rest).

**Multipart/composite hull formalization (2026-08-25, ROADMAP Phase 27,
charter Priority 5):** read `analysis/complex_hull_audit.py` and
`analysis/composite_hulls.py` fully before designing anything, per the
task's own instruction. Found the existing structural records
(`ModuleProfile`/`CompositeHullProfile`, matching `DATA_SCHEMA.md`'s prior
6A exactly) were already reasonably typed dataclasses, not the fully ad hoc
representation the charter's wording might suggest -- but real duplication
existed *around* them: hull composite-role classification
(`SHIP_WITH_MODULES`/`MODULE`/`UNDER_PARENT`/`STATION` hint matching) was
independently inline-coded in three separate places
(`complex_hull_audit.py`'s four parent/module/under_parent/station list
comprehensions, its own per-variant `MODULE_MAP_WITHOUT_PARENT_HINT` check,
and `composite_hulls.py`'s station-feature detection); module mappings were
bare, untyped `tuple[str, str]` pairs; and one flat profile record conflated
a hull's *declared* structural role with one specific ship instance's
*resolved* structure -- exactly the kind of ad hoc, inconsistently-shaped
representation Phase 27 was scoped to formalize.

Introduced all six charter-named types in `analysis/composite_hulls.py`:
`HullDefinition`/`classify_hull_definition()` (one hull's declared role,
computed once, now the single source every consumer uses instead of 3
separately duplicated inline checks); `ShipModule` (typed replacement for
the bare tuple `module_mappings()` returned); `ModuleProfile` (unchanged);
`CompositeHullDefinition`/`build_composite_hull_definitions()` (new --
hull-*type*-level: does a hull id declare the parent hint, and is that
borne out by observed variant evidence, aggregating
`variants_with_module_maps`/`distinct_child_hull_ids` across every variant
of that hull id -- e.g. a real `hmi_locomotive`-shaped fixture with 2
variants sharing overlapping module slots correctly aggregates to 2 and
`("gun_left", "gun_right")`); `ResolvedShipStructure`/`resolve_ship_structure()`
(new -- resolves a profile's ids into real `Hull`/`Variant` entities for the
parent and every `RESOLVED` module, so a future consumer needing actual
entities -- e.g. to inspect a module's own local fit -- doesn't reimplement
registry lookups; deliberately *not* wired into the audit's JSON output,
since embedding full raw entities there would duplicate local source
content the same way `ScanResult.report()` already avoids doing); and
`CompositeShipProfile`, the renamed former `CompositeHullProfile` (keyed by
`parent_variant_id`, one ship instance, not a hull type in the abstract --
"Ship" is the more precise scope word), kept as a backward-compatible alias
(`CompositeHullProfile = CompositeShipProfile`,
`build_composite_hull_profiles = build_composite_ship_profiles`) since no
field changed -- proven by a dedicated test asserting `assertIs` identity
and that both entry points return byte-equal output.

Migrated the one real internal call site with the duplicated hint-matching
(`analysis/complex_hull_audit.py`, all 3 occurrences) onto
`classify_hull_definition`, verified byte-identical existing-test output
(the pre-existing tests assert exact summary counts/values, not
implementation internals, so they only pass if the refactor changed
nothing observable). Deliberately left `complex_hull_audit.py`'s separate
`_module_targets()` helper alone rather than forcing it onto the shared
`module_mappings()`/`ShipModule` path: it has a subtly looser filter
(accepts an empty-string slot id if the target is non-empty;
`module_mappings()` requires both non-empty) that no existing test exercises
either way -- collapsing the two without a clear signal it was safe would
have risked a real, unreviewed behavior change for a vanishingly unlikely
degenerate case, so it stayed a documented, judgment-call exception rather
than a forced migration. `tools/audit_complex_hulls.py` and
`tools/mod_acceptance_sweep.py`/`analysis/mod_acceptance.py` needed zero
changes: both only ever consume `audit_complex_hulls()`'s return dict, and
every existing key/value in it is unchanged.

Added one new, purely additive top-level `composite_hull_definitions` field
to the audit dict (schema version bumped `complex-hull-audit-0.2` ->
`-0.3`) -- the one place `CompositeHullDefinition` is wired into a real
consumer today, verified end to end through the real `audit_complex_hulls()`
entry point (not just the unit-level type tests). `DATA_SCHEMA.md` section
6A rewritten to document all six types, replacing the prior
`CompositeHullProfile`/`ModuleProfile`-only version. 15 new tests: 13 in
`tests/test_complex_hulls.py` (each new type's construction, the
rename-alias identity/behavior, a synthetic `hmi_locomotive`-shaped
multi-variant fixture for `CompositeHullDefinition`'s aggregation, an
unresolved-module case proving `ResolvedShipStructure` stays `None` rather
than guessing); 2 end-to-end in `tests/test_complex_hull_audit.py` (station/
under-parent classification and the new field, both through the real audit
entry point). This phase's own delta is 15 new tests over its confirmed
560-passing/1-skipped starting baseline (re-ran before any edit, matching
Phase 33/34's recorded count exactly) -- 575 total immediately after this
phase's own edits. A final full-suite re-run before closing out showed 579
passing/1 skipped, 0 failures; the extra 4 trace via file-modification
timestamps (git itself is inaccessible in this environment, as expected) to
`tests/test_calibration_activation.py`/`tests/test_calibration_runner.py`
-- concurrent Phase 30 (Calibration Activation) work landing in
`analysis/calibration.py`/`analysis/calibration_runner.py`, both explicitly
outside this phase's constrained scope and left untouched here, not a
regression attributable to this change. `ROADMAP.md` Phase 27 marked
`COMPLETE_WITH_LIMITATIONS`: this is a
consistency/typing formalization of the existing acceptance boundary, not
new detection capability, and `ResolvedShipStructure` has no wired real
consumer yet by design (avoiding report bloat) -- it exists as a tested,
available utility for a future one. `gui/`, `pyproject.toml`,
build/release scripts, `core/cache.py`, `core/result_cache.py`,
`analysis/change_impact.py`, `analysis/calibration.py`,
`analysis/calibration_runner.py`, and `analysis/gap_recommendation.py` were
not touched, per this task's explicit constraints; no git operations were
performed (git reported inaccessible due to dubious ownership from a
separate concurrent process, as expected in this environment).

**Calibration activation (2026-08-25, ROADMAP Phase 30, charter Priority
8):** read every calibration file end to end first (`analysis/calibration.py`,
`analysis/calibration_runner.py`, `tools/evaluate_calibration.py`,
`tools/build_calibration_observations.py`,
`tools/import_milestone_calibration.py`,
`tools/resolve_scenario_calibration.py`,
`tools/evaluate_local_calibration.py`, plus their existing tests) before
changing anything, per the task's own instruction. The premise -- "built but
dormant" -- turned out to be literally, checkably true rather than assumed:
`generated/calibration/reviewer_milestones.json` already existed on disk, a
real, hash-bound, reviewer-derived fixture (12 `SOFT_EXPECTATION`
`BUILD_EXPECTATION` labels spanning real hulls across DME/Scrapyard/swp/armaa/
core, produced earlier this session by `tools/import_milestone_calibration.py`
converting the user's own milestone-guide text under `docs/*.txt`), but no
evaluation report existed anywhere for it -- the comparison had never actually
been run.

Ran `tools/evaluate_local_calibration.py` against that real fixture and the
real local Starsector installation (149 mods): a genuine activation, producing
**4 MATCH / 8 MISMATCH / 0 STALE / 0 UNSUPPORTED**
(`generated/calibration/reviewer_milestones_report.json`, an ignored local
artifact under `generated/`, not committed). This is real, human-review-worthy
divergence between milestone-guide reviewer judgment and this project's
`baseline_0.7` guided-mode build-archetype selection for several real hulls
(e.g. `sotf_respite`: reviewer expected `CARRIER_SUPPORT`, actual
`LINE_ANCHOR`; `sa_skua`: reviewer expected `ARTILLERY`/`PD_ESCORT`, actual
`CARRIER_SUPPORT` both times) -- reported only, as designed; nothing was
auto-applied or fed back into heuristics.

Exercising the real end-to-end pipeline (not just its already-tested unit
pieces) surfaced two real, previously-latent bugs in
`analysis/calibration_runner.py::collect_build_observations`, both fixed
here: (1) `observations` was keyed only by `entity_key` and unconditionally
overwritten on every label sharing that key, so a fixture with 2+ labels for
the same hull -- the real dormant fixture's own shape, `sa_skua`/`omen`/`doom`
each carry two -- could have a later label's unsupported/failed branch
silently discard an earlier label's already-computed `actual`, turning a real
MATCH/MISMATCH into a false `UNSUPPORTED` depending on label order alone; (2)
a hull with no `source_hash` skipped creating an `observations` entry but
could still reach the line writing into it, a latent `KeyError` crash path no
existing test reached (all supplied a truthy hash). Fixed both via
per-`entity_key` generation memoization (which also removes real duplicate
`api.run_generate` calls -- the real activation run above had regenerated
`sa_skua`/`omen`/`doom`'s build twice each before this fix) and an explicit
early `continue` when no hash exists. 2 new regression tests in
`tests/test_calibration_runner.py` lock in both fixes.

Added a fully synthetic, portable end-to-end activation test
(`tests/test_calibration_activation.py`,
`tests/fixtures/calibration/synthetic_capital_activation.json` -- invented
hull/entity ids over the existing `capital_heavy_broadside` benchmark
archetype, matching the established synthetic-fixture discipline, not copied
Starsector/mod data) that runs the real, non-mocked pipeline --
`load_calibration_labels` (file I/O) -> `collect_build_observations` (real
`api.run_generate` against a real synthetic `Registry`) ->
`evaluate_calibration` (comparison) -- and asserts all real outcomes (MATCH,
`NEGATIVE_EXPECTATION` MATCH, MISMATCH, STALE, and UNSUPPORTED via a
genuinely ambiguous duplicate global hull id) from one fixture in one run,
plus an explicit source-scan guard proving neither calibration module
references `core/heuristics.py`'s `REGISTRY` at all -- direct, checked
evidence for CLAUDE.md's hard rule that calibration never adjusts heuristics
automatically, not just an assumption that it doesn't.

Two real gaps are documented rather than left implicit: `EQUIPMENT_
EXPECTATION`/`FACTION_EXPECTATION`/`SCENARIO_EXPECTATION` are declared
`CalibrationExpectationKind` values with no registered runtime observer
anywhere -- only `BUILD_EXPECTATION` and `NEGATIVE_EXPECTATION` ever produce
an `actual`. This doesn't block any existing label (the real dormant fixture
uses only those two kinds), but a future observer for one of the other three
should use its own `entity_key` namespace rather than reuse a hull's bare
`hull:<mod>:<id>` key, since `evaluate_calibration` is kind-agnostic and would
otherwise silently compare an unrelated kind's expectation against a
build-archetype `actual` if the keys collided. Separately, and outside this
phase's file scope to fix: `docs/starsector_calibration_seed.provisional.json`,
`docs/starsector_ship_by_ship_calibration_profiles.provisional.json`, their
`.csv`/`.md` companions, and the five `docs/*.txt` milestone-guide source
files sit under `docs/` (not `generated/`, so not `.gitignore`d) and name real
third-party mod/faction content (Arma Armatura, HMI, Hegemony, Tri-Tachyon
Corporation, etc.) in bulk structured form -- this appears to conflict with
AGENTS.md's distribution boundary ("never commit... real entity
identifiers/lists... benchmarks that name third-party game/mod entities").
Flagged here for a maintainer decision (most likely: move under `generated/`
or otherwise exclude) rather than acted on unilaterally, since resolving it
is a real distribution-policy call outside this phase's stated scope
(`analysis/calibration.py`, `analysis/calibration_runner.py`,
`tools/*calibration*.py`, and their own tests/fixtures).

4 new tests total (2 in `tests/test_calibration_runner.py`, 2 in
`tests/test_calibration_activation.py`). Full suite: 579 passing, 1 skipped,
0 regressions -- this task's own confirmed starting baseline (re-ran before
any edit) was 560 passing/1 skipped; the +15 beyond this phase's own +4 is
Phase 27's concurrent test additions, landed in this shared repository this
session outside this phase's scope (see that entry above). No git operations
were performed (git reported inaccessible due to dubious ownership from a
separate concurrent process, as expected in this environment). `ROADMAP.md`
Phase 30 marked `COMPLETE_WITH_LIMITATIONS` rather than `COMPLETE`: real
reviewer-authored labels now flow through the real comparison machinery end
to end, both against real Starsector data and in a portable synthetic
regression, but only 12 real labels exist (all `SOFT_EXPECTATION`, none
promoted to `HARD_EXPECTATION`/reviewer-approved per
`docs/CALIBRATION_IMPORT_NOTES.md`'s own stated workflow), 3 of 5 declared
expectation kinds have no runtime observer, and the `docs/` distribution-
boundary question above remains unresolved pending a maintainer decision.

**Local hullmod/system interpretation expansion (2026-08-25, ROADMAP Phase 28,
charter Priority 6):** the charter asked to expand real, undocumented
hullmod/ship-system effect coverage following the 8-tier evidence-priority
ladder (parsed data -> local Java static analysis -> versioned API-effect
registry -> referenced local config/constants -> local descriptions/
existing-variant evidence -> `adapters/` -> manual overrides ->
`UNKNOWN_SCRIPTED_EFFECT`), and to pick the single most impactful,
well-evidenced gap rather than build all 8 tiers from scratch. Read
`analysis/hullmod_static_analysis.py`, all six `adapters/vanilla/`
effect-category tables, and `core/overrides.py` fully first, per the task's
own instruction, to determine what already existed before assuming
anything was missing.

Found the charter's own suggested starting hypothesis -- that tier 3 (a
versioned API-effect registry) was the likely gap -- was already wrong:
`hullmod_static_analysis.py` already carried a versioned registry
(`API_EFFECT_REGISTRY_VERSION = "starsector-api-effects-0.2"`) of 14 known
`MutableShipStatsAPI` accessor methods (`_CALLS`), matched against
`stats.getX().modifyFlat/Percent/Mult(id, value)` call patterns with
recorded file/line/confidence `EvidenceRecord`s -- genuinely tier 2 (local
source static analysis) and tier 3 (known-API-call interpretation) already
combined and working, not a from-scratch design. Tier 6 (`adapters/`) was
also already substantial: six real, wiki-cross-checked vanilla effect
tables (LOGISTICS/EFFICIENCY/DEFENSE/MOBILITY/FLUX/COMBAT) covering ~20
real hullmods with explicit researched-and-excluded lists for everything
ruled out. Tier 8 (`UNKNOWN_SCRIPTED_EFFECT` fallback) was already the
correct, honest terminal state.

The real, well-evidenced gap turned out to be narrower and more concrete
than the charter's own guess: the existing registry's value-argument
resolution (inside tier 3) only ever handled a bare numeric literal or a
single already-declared local constant as the modifier call's second
argument -- a compound arithmetic expression like `1f - (0.01f *
RECOIL_BONUS)` or `-HULL_PENALTY` fell straight to
`UNKNOWN_SCRIPTED_EFFECT`, even when every name in the expression was
itself a `static final` constant declared in the very same, already-
associated Java file. Measured this directly against the real local
149-mod install before deciding it was worth fixing (never assumed):
across 2,776 real `stats.get<RegisteredAccessor>().modifyFlat/Percent/
Mult(...)` calls found in installed mods' Java source (counting only the
14 already-registered accessors, not every `stats.getX()` call in the
install), the prior single-token-only logic recognized 1,144 (41%);
1,632 real compound-expression calls remained entirely unrecognized.

Implemented a bounded, safe constant-expression folder
(`_fold_constant_expression`/`_eval_constant_node` in
`analysis/hullmod_static_analysis.py`, using Python's `ast` module
restricted to `Constant`/`Name`/`UnaryOp(+/-)`/`BinOp(+,-,*,/)` nodes
only -- no calls, attribute access, comparisons, or subscripts) that
constant-folds the modifier value expression when every leaf name
resolves to a `static final` constant already declared in that same file;
any unresolvable name (a method parameter, an instance field, a constant
declared in a *different* file -- still-unimplemented tier 4) makes the
whole expression `UNKNOWN_SCRIPTED_EFFECT` rather than partially guessed,
identical in spirit to how the prior single-token path already refused to
guess at a bare unresolvable identifier. Re-measured against the same real
install with the fix in place: 491 of the 1,632 previously-unrecognized
calls (30%, an 18-point / ~43% relative increase in overall real-call
recognition) now resolve, across 247 distinct real files; the remaining
1,141 correctly stay unresolved because they genuinely reference a
runtime value. Newly recognized effects are recorded at confidence 0.85
(vs. 0.9 for the original bare-literal/single-constant path), a separate,
lower-but-still-high confidence tier reflecting that the value is
synthesized from combining local constants rather than read as one
already-declared quantity -- never silently merged into the same
confidence as before. Bumped `API_EFFECT_REGISTRY_VERSION` to
`starsector-api-effects-0.3` (already wired into the scan-report
cache-invalidation fingerprint in `output/analysis_reports.py`, so no
separate cache-plumbing change was needed -- a version bump alone
correctly invalidates any stale cached fragment). Live-verified against
one real installed hullmod end to end through the actual production
function (not a reimplementation): the "1130的蔚蓝联邦 translated" mod's
real `AF_OpenAmmoDepot` hullmod (`data.hullmods.AF_OpenAmmoDepot`, real
CSV-declared script class) declares `public static final float
HULL_PENALTY = 25f;` and applies `stats.getHullBonus().modifyPercent(id,
-HULL_PENALTY);` -- previously entirely unrecognized (a unary-minus
expression), now correctly recognized as `hull_hp PERCENT_ADD -25.0` at
confidence 0.85, citing the real file and line.

Confirmed the two remaining named-but-unimplemented tiers are genuinely
missing, not merely unexercised, rather than assumed: tier 4 (referenced
local config/constants from a *different* file, e.g. a mod's own shared
constants class or JSON settings file) has no implementation anywhere in
the codebase -- the new expression folder deliberately stays same-file-
only (proven by a dedicated regression test using a real cross-file
pattern found during the install sweep). Tier 7 (explicit manual
overrides) exists in `core/overrides.py` but only for `role_tags`/`notes`
on weapons and hulls -- AGENTS.md's own "Manual Overrides" section
explicitly lists "scripted-effect interpretation when explicitly
supplied" as a supported override category, but no field or loader
supports it today. Neither was implemented this phase (scope was one
well-evidenced gap, not all remaining tiers); both are documented here as
real, specific follow-on candidates rather than left implicit.

5 new synthetic-fixture regression tests added to
`tests/test_hullmod_static_analysis.py` (neutral invented class/constant
names, no real mod source committed, per this project's distribution
boundary): two-constant multiplicative folding, addition/division
folding, a runtime-variable expression correctly staying unresolved, a
cross-file constant reference correctly staying unresolved (proving the
same-file-only boundary structurally, not just via the evaluator), and a
regression guard that the original bare-literal/single-constant path
keeps its 0.9 confidence unchanged. Updated
`tests/test_scan_analysis_reports.py`'s hardcoded registry-version
assertion and `DATA_SCHEMA.md`'s section 10A registry description to
match the `-0.3` bump. Constraints honored: touched only
`analysis/hullmod_static_analysis.py` and its own tests plus
`DATA_SCHEMA.md`; did not touch `gui/`, `pyproject.toml`'s version, any
build/release script, `core/cache.py`, `core/result_cache.py`,
`analysis/change_impact.py`, `analysis/complex_hull_audit.py`,
`analysis/composite_hulls.py`, `analysis/calibration.py`,
`analysis/calibration_runner.py`, `tools/*calibration*.py`, or
`analysis/gap_recommendation.py`; never executed, imported, or otherwise
dynamically evaluated any mod Java source -- static text/AST parsing over
a restricted expression grammar only. No git operations were performed
(git reported inaccessible due to dubious ownership from a separate
concurrent process, as expected in this environment). `ROADMAP.md` Phase
28 marked `COMPLETE_WITH_LIMITATIONS`: the charter's suggested tier (a
versioned API-effect registry) was found already built, and this phase's
real contribution is a substantial, real-data-measured expansion of that
registry's value-resolution power within its existing same-file-only
scope -- tier 4 (cross-file/config-referenced constants) and the
scripted-effect-interpretation half of tier 7 (manual overrides) remain
genuinely unimplemented and are named above for future work, not silently
left as an unstated gap.

5 new tests. Full suite: 584 passing (579 + 5), 1 skipped, 0 regressions
-- re-confirmed the 579-passing/1-skipped starting baseline before any
edit, matching this task's own stated figure exactly.

**Local hullmod/system interpretation expansion, round 2 (2026-08-25,
ROADMAP Phase 38, user's own "Phase 2"):** the task named six candidate
axes to extend Phase 28's evidence-tier work along and explicitly
permitted picking the clearest-payoff subset rather than closing all six.
Read `analysis/hullmod_static_analysis.py` and
`tests/test_hullmod_static_analysis.py` fully first, per the task's own
instruction, before changing anything. Closed the three items the task
itself flagged as clearest: more registry coverage, cross-class constant
resolution, and an explicit `UNSUPPORTED` vs `UNKNOWN` distinction.
Deliberately left as stretch goals, not attempted: local mod-specific
config/CSV reference resolution, richer ship-system-effect
interpretation, and partial per-method extraction from a mixed
known/unknown script body -- named here rather than silently skipped.

**(1) Registry coverage.** Confirmed the local install path first
(`C:\Program Files (x86)\Fractal Softworks\Starsector`, 149 discovered
mods, 7,155 real `.java` files under `mods/`) before measuring anything.
Grepped every real `stats.get<Accessor>().modify(Flat|Percent|Mult)(`
call site across the whole local install (not just already-registered
accessors this time, to find genuinely uncovered ones) and tallied by
accessor name: `getMaxSpeed`/`getAcceleration`/etc. (the already-
registered 14) dominate as expected, but 15 further accessors also
appear at real, non-trivial frequency -- `getBallisticRoFMult` (212 real
calls), `getEnergyWeaponRangeBonus` (165), `getEnergyRoFMult` (160),
`getBallisticWeaponRangeBonus` (146), `getShieldDamageTakenMult` (152),
`getArmorDamageTakenMult` (135), `getEmpDamageTakenMult` (118),
`getPeakCRDuration` (85), `getMissileRoFMult` (73), `getVentRateMult`
(54), `getZeroFluxSpeedBoost` (50), `getMaxCombatReadiness` (48),
`getSensorProfile` (38), `getHullDamageTakenMult` (124, folded into the
damage-taken family), `getRecoilPerShotMult` (36). Verified each one's
real, documented semantics before adding it (never guessed): fetched the
official Starfarer API's own `MutableShipStatsAPI` interface method
surface (`fractalsoftworks.com/starfarer.api`, confirming every method's
real existence and `MutableStat`/`StatBonus` return type) and a
maintained third-party Starsector hullmod-modding guide
(`github.com/operator-damexius/Starsector-Modding-Guide-Creating-Custom-
Hullmods`) that gives an explicit one-line description for several of
them directly (`getBallisticWeaponRangeBonus`: "ballistic weapon
engagement distance modifier"; `getEnergyWeaponRangeBonus`:
"energy-based weapon engagement distance modifier"; `getBallisticRoFMult`:
"Fire Rate (+15%) for ballistic weapons"; `getShieldDamageTakenMult`:
"Shield Damage Taken (-20% damage taken) multiplier"; `getZeroFluxSpeedBoost`:
"speed advantage when not actively firing weapons"; `getRecoilPerShotMult`:
"Recoil (-50%) knockback reduction per shot"). `getMaxCombatReadiness`
was additionally confirmed directly against real vanilla source (the
decompiled `Automated.java`, `com.fs.starfarer.api.impl.hullmods.Automated`,
mirrored at `jaghaimo.github.io/starsector-api`): `stats.
getMaxCombatReadiness().modifyFlat(id, -MAX_CR_PENALTY, "Automated ship
penalty")`, confirming both its real existence and its real semantics (a
flat penalty to the ship's maximum combat readiness) from actual vanilla
code, the strongest evidence tier available. The remaining siblings
(`getEnergyRoFMult`/`getMissileRoFMult` alongside the guide-confirmed
`getBallisticRoFMult`; `getArmorDamageTakenMult`/`getHullDamageTakenMult`/
`getEmpDamageTakenMult` alongside the guide-confirmed
`getShieldDamageTakenMult`) were accepted on the same evidentiary basis
Phase 4's own adapter tables already use for a symmetric family (e.g. the
existing registry's own `getBallisticWeaponFluxCostMod`/
`getEnergyWeaponFluxCostMod`/`getMissileWeaponFluxCostMod` triple) --
confirmed to exist via the official API surface, self-evident from an
unambiguous, parallel method name. All 15 added to `_CALLS`
(`analysis/hullmod_static_analysis.py`), `API_EFFECT_REGISTRY_VERSION`
bumped `starsector-api-effects-0.3` -> `-0.4` (already wired into the
scan-report cache-invalidation fingerprint, confirmed by Phase 28 --
no separate cache-plumbing change needed).

Measured against the real install with the actual production function
(`analyze_hullmod_sources`, per-hullmod source association, not a
reimplementation): recognized effects rose from 742 to 1,424 (+682,
~92%) across the same 2,180 real scanned hullmods (enabled + disabled),
and hullmods with >=1 recognized effect rose from 310 to 499 (+189). This
is measured through the real per-hullmod `DECLARED_SCRIPT_CLASS`/
`ID_REFERENCE_FALLBACK` association path (the actual scope
`hullmod_source_analysis.json` reports), a narrower and more precise
number than a raw whole-install call-site grep would give -- reported
honestly as the real production-relevant figure, not the larger raw
grep count (6,854 total real call-site matches for all recognized-or-
not accessors combined, of which 1,596 are raw matches for the 15 newly
registered accessors specifically).

**(2) Cross-class constant resolution.** Phase 28 explicitly left this
open (tier 4, "referenced local config/constants"): the existing
constant-expression folder only ever resolved a `static final` constant
declared in the same `.java` file as the call site, so a real hullmod
referencing a shared `Constants`-style class declared in a different
file within the same mod (the task's own cited example,
`Constants.HULL_PENALTY`) fell straight to unresolved. Implemented
`_cross_file_constants(source_root)`, a same-source-root,
per-file-stem-as-class-name lookup table (`{class_name: {constant_name:
value}}`) built once per scan process from the same `_java_sources`
listing this module already indexes (no second file-read pass), and
extended `_eval_constant_node`'s restricted AST grammar with one new
node type, `ast.Attribute` (a `ClassName.CONSTANT`-shaped qualified
reference), resolved only against this table. The source-root boundary
is structural, not a runtime check: `_cross_file_constants` is built
exclusively from `_java_sources(source_root)`, itself already scoped to
one mod's (or the core game's) own `.java` tree, so a different mod's
class can never be reached by construction -- verified by a dedicated
regression test using a qualifier naming a class this source root never
declares at all, confirming the lookup fails closed rather than guessing.
A resolution that touches this table is recorded at a new, lower
confidence tier (0.75) than either same-file sub-tier (0.9 bare, 0.85
same-file expression), reflecting the added uncertainty of the
file-stem-as-class-name assumption -- the same simplification the
existing `DECLARED_SCRIPT_CLASS` association already relies on
(`path.stem == script_class`), reused consistently rather than invented
fresh. Deliberately stays qualified-reference-only: a bare (unqualified)
name resolved only via a Java `import static` remains a distinct,
still-unimplemented pattern (a dedicated regression test proves the
existing bare-cross-file-reference case still correctly stays
unresolved, unchanged by this addition).

Measured against the real install via a dedicated isolation script
(restricting the registry to the original 14 accessors while keeping
cross-file resolution active, then comparing against the same 14-only/
same-file-only baseline): 0 additional real resolutions for the original
14 accessors -- no real hullmod in this install happens to reference a
cross-file qualified constant through one of them -- and exactly 4 real
effects specifically through the newly-added `-0.4` accessors that would
otherwise have stayed unresolved. A small, real, honestly-measured
number rather than an inflated one: cross-class qualified references
turn out to be genuinely rare in this real install's call sites to the
registered accessor family, which is itself real evidence, not a
methodology failure -- reported as measured.

**(3) Explicit `UNSUPPORTED_SCRIPTED_EFFECT` vs `UNKNOWN_SCRIPTED_EFFECT`.**
Added `unsupported_scripted_portions: tuple[str, ...] = ()` to
`HullmodStaticAnalysis` (additive, defaulted, so every existing
positional-argument construction in the module and any external caller
keeps working unchanged). Populated only when a call site already
matched a real, registered `_CALLS` accessor (`call_match.group(1) in
_CALLS`) but its value argument could not be resolved to a concrete
number -- a runtime variable, a cross-mod reference, an unfoldable
expression, or an argument list this module's deliberately single-line
parser could not extract at all -- reclassified out of the now-narrower
`unknown_scripted_portions`, which is reserved for a call/reference this
module has no registry entry for whatsoever (or a structural
no-source/no-class state, e.g. `NO_LOCAL_SOURCE`/`NO_ASSOCIATED_CLASS`).
This is purely a re-labeling of which branch an already-computed
unresolved case fell into -- no new inference, no new value ever
synthesized to avoid the label, per the task's own explicit constraint.
The confidence formula and the "associated class contains no recognized
normalized stat modifier" terminal fallback were both updated to treat
`unsupported` the same as `unknown` for the partial-vs-full-understanding
distinction (a class with some effects and any unresolved remainder,
whether UNSUPPORTED or UNKNOWN, still lands at the existing 0.6 partial
tier, not silently upgraded).

Measured against the real install: 477 real `UNSUPPORTED` portions
(registry-recognized, value-unresolvable) across 164 real hullmods, now
distinguishable from 6,318 real `UNKNOWN` portions (no registry entry at
all, or structural) -- previously both were indistinguishable
`UNKNOWN_SCRIPTED_EFFECT` strings totaling 7,477 before this phase's
registry expansion moved some of that combined total into genuinely
resolved effects instead.

Two pre-existing tests' expected results changed as a deliberate,
documented reclassification, not a regression: both fixtures' call sites
match a registered accessor (`getAcceleration`, `getMaxSpeed`) whose
argument fails to resolve, so their asserted "not statically resolvable"
message now correctly lives in `unsupported_scripted_portions` rather
than `unknown_scripted_portions` -- updated accordingly, with the
reasoning recorded in the test's own docstring comment. 7 new tests
added (`tests/test_hullmod_static_analysis.py`, synthetic-fixture-based,
neutral invented class/constant names, no real mod source committed):
two new registry accessors resolving correctly with the right target
stat and confidence; the real vanilla `Automated.java`-mirroring pattern
for `getMaxCombatReadiness` including its optional third string-
description argument; the genuine UNKNOWN/UNSUPPORTED boundary via a
call to a wholly unregistered accessor (stays UNKNOWN); a mixed
effects-plus-unsupported class correctly landing at the existing 0.6
partial-confidence tier; a successful qualified cross-file resolution at
the new 0.75 tier; a cross-file resolution mixed with a same-file
constant in one expression staying at the lower 0.75 tier rather than
being upgraded; and a qualifier naming a class this source root never
declares failing closed. Updated
`tests/test_scan_analysis_reports.py`'s hardcoded registry-version
assertion (`-0.3` -> `-0.4`) and `DATA_SCHEMA.md`'s section 10A to
describe all three changes (the new confidence tier, the expanded
accessor count, and the two-field unresolved-remainder split).

Constraints honored: touched only `analysis/hullmod_static_analysis.py`,
its own tests, `tests/test_scan_analysis_reports.py`'s one hardcoded
version-string assertion, `DATA_SCHEMA.md`, `ROADMAP.md`, and this log;
read `adapters/vanilla/__init__.py` fully (for its established
wiki-citation rigor and format) but made no changes there -- this
phase's registry additions are `MutableShipStatsAPI` accessor-method
semantics (a different, API-surface evidence class from `adapters/
vanilla`'s per-hullmod balance-value citations) and needed no new
adapter table entries. Did not touch `gui/`, `pyproject.toml`'s version,
any build/release script, `core/scanner.py`, `core/cache.py`,
`core/result_cache.py`, `output/analysis_reports.py`,
`analysis/calibration.py`, `analysis/calibration_runner.py`,
`analysis/gap_recommendation.py`, `analysis/composite_hulls.py`,
`analysis/change_impact.py`, or `core/overrides.py`. Never executed,
imported, or otherwise dynamically evaluated any mod Java source --
static text/AST parsing over a restricted expression grammar only; all
web research was documentation lookup (the official Starfarer API pages
and a third-party modding guide), never code execution. No git
operations were performed (git reported inaccessible due to dubious
ownership from a separate concurrent process in this environment, as
expected). `ROADMAP.md` Phase 38 marked `COMPLETE_WITH_LIMITATIONS`: all
three closed items are real, measured, and regression-tested against
the real local install, but this is a genuine partial pass by the
task's own explicit permission -- local config/CSV reference resolution,
richer system-effect interpretation, and partial per-method extraction
from mixed known/unknown scripts remain unimplemented and are named here
as real follow-on candidates, not silently left as an unstated gap.

7 new tests. Full suite: 616 passing (608 confirmed starting baseline +
this phase's own 7 + 1 from concurrent Phase 37 scan-performance work
landing in `tests/test_scanner.py` this same session, confirmed via file-
modification timestamps rather than assumed, outside this phase's own
file scope), 1 skipped, 0 regressions.

**Scenario-aware recommendations (2026-08-25, ROADMAP Phase 31, charter
Priority 9):** the charter's ask was to extend the Gap Recommendation
Engine (Phase 10) beyond `Hull + BuildArchetype` ranking to
`Hull + BuildArchetype + ScenarioObjective` units, labeling any such
scenario-specific option `INFERRED_SCENARIO_OPTION` so it can never be
confused with the engine's existing direct, evidence-based ranking. Read
`analysis/gap_recommendation.py` fully (its `CapabilityGap`/
`NativeRecommendation`/`RetrofitRecommendation`/`AcquisitionRecommendation`
records, `recommend_native_solutions`/`recommend_retrofit_solutions`/
`recommend_acquisition_solutions`, `_rank_build_candidates_for_role`/
`_diverse_build_shortlist`, and the `explain_native_candidate`/
`explain_build_candidate` Why-Not machinery) plus `analysis/
build_archetypes.py`, `analysis/mechanical_archetypes.py`, and
`analysis/capability_vector.py` first, per the task's own instruction,
before designing anything.

That read surfaced a real naming collision worth resolving before writing
any code: `analysis/scenario_objectives.py::ScenarioObjective` already
exists (landed 2026-08-23, see that entry above) and is already imported
by `build_archetypes.py`/`generation/candidate.py` -- but it is an
unrelated, earlier concept (which *generation-time coverage objectives*,
e.g. `LINE_HOLD`/`BREAKTHROUGH`, a single build archetype already
supports, each tagged `SUPPORTED`/`PARTIAL`/`UNSUPPORTED`). The charter's
new ask is a different thing: a *faction-recommendation* scenario concept
(raiding/defense/escort/patrol). Named the new type `ScenarioCategory`
specifically to avoid colliding with the existing, actively-imported
`ScenarioObjective` class.

Checked for real grounding before inventing a taxonomy, per the task's own
instruction: no parseable Starsector hull/variant/faction field anywhere
in this project's schema records a documented "mission role," "deployment
points," or comparable in-game scenario tag (`DATA_SCHEMA.md` confirmed;
the closest real data, the hull CSV `hints` column, covers civilian/
logistics roles only). `ScenarioCategory` (`RAIDING`, `DEFENSE`, `ESCORT`,
`PATROL`) is therefore kept deliberately small and explicitly labeled as a
first-pass heuristic taxonomy in its own docstring -- never a documented
game mechanic, the same honest status this module's other first-pass
values (`gap_strong_threshold`, etc.) already carry.

Implemented entirely additively in `analysis/gap_recommendation.py` (the
task's required scope): `recommend_scenario_solutions(faction, registry,
gap_result, scenario, heuristic_set, roles=None)` takes an
already-computed `GapRecommendationResult` and layers a heuristic
`scenario_fit_score` (0.0-1.0, `_scenario_fit_score`) on top of the
Native/Retrofit/Acquisition legs' own already-ranked `hull_id`/
`build_archetype_id`/`recommendation_score`/`confidence` -- reading them
directly, never recomputing or reordering them, and never wired into
`recommend_gap_solutions` itself (which is completely unmodified; a caller
opts in explicitly). Every result record (`ScenarioRecommendation`) carries
`kind = SCENARIO_RECOMMENDATION_KIND` (`"INFERRED_SCENARIO_OPTION"`),
`source_leg` (which real leg's candidate it reused), and
`base_recommendation_score` (that leg's own unmodified score) so a
scenario option is structurally distinguishable from direct evidence, not
just labeled that way in prose. `scenario_fit_score` itself is a fixed
weighted combination of already-real, already-computed signals only
(`MechanicalArchetypeProfile.compatibility_scores` plus
`BuildArchetypeProfile`'s own `tactical_style`/`target_range`/
`flux_posture`/`survivability_posture`/`equipment_priorities`) -- the
combination weights are heuristic, the inputs are not.

Two new heuristics (`core/heuristics.py`, new `baseline_0.11`, additive
over `baseline_0.10`, changing nothing for any earlier registry entry):
`scenario_fit_min_signal` (default 0.30 -- a candidate below this is
simply absent, never padded in, mirroring `unaddressed_gaps`' own "no
fabricated recommendation" discipline) and `scenario_confidence_cap`
(default 0.75 -- hard-caps every `ScenarioRecommendation.confidence` below
the underlying leg's own confidence, so a heuristic overlay can never
present itself as fully certain per AGENTS.md's "high score with low
confidence must remain visibly low confidence"); plus
`scenario_recommendation_count` (default 3.0, a dedicated shortlist-size
counterpart to `gap_recommendation_count`). All three are read via
`.get()` with an explicit fallback, so `recommend_scenario_solutions` also
works correctly under every earlier heuristic_set that predates
`baseline_0.11` (verified directly: the test suite exercises it under
`baseline_0.4`).

Why-Not: `explain_scenario_candidate` answers "why wasn't
`<hull_id>`/`<build_archetype_id>` given as an `INFERRED_SCENARIO_OPTION`
for `<scenario>` on `<role>`?" using the exact same real ranking
`recommend_scenario_solutions` computes (never a second inference
mechanism, the same discipline every other Why-Not function in this module
already follows). Its result (`ScenarioWhyNotExplanation`) always carries
the underlying, direct evidence-based `BuildWhyNotExplanation`
(`explain_build_candidate`) as a separate `underlying` field, and its own
`reason` always states plainly this is a heuristic overlay, never
conflating the two into one claim.

A hand-verified synthetic fixture (a 3-medium-ballistic-mount hull with
every optional raw stat deliberately left unset, so every mechanical-
archetype score is exactly hand-computable from the plain weighted
formulas already in `analysis/mechanical_archetypes.py`) let the new tests
assert exact `scenario_fit_score` values, not just loose bounds --
e.g. `DEFENSE` fit for the `LINE_ANCHOR` build derives to exactly 0.511,
`RAIDING` fit for the same build to exactly 0.145 (correctly excluded,
below the 0.30 signal threshold), while `RAIDING` fit for a *different*
build (`FINISHER`) on the *identical* hull derives to 0.495 (correctly
included) -- proving exclusion operates per `Hull + BuildArchetype` unit,
not per hull. 14 new tests in `tests/test_scenario_recommendation.py`
prove: correct `INFERRED_SCENARIO_OPTION` labeling; a low-fit build
excluded while a sibling build of the same hull still appears; a scenario
with no fitting build at all fully absent; computing scenario
recommendations never mutates or changes the content of the underlying
`GapRecommendationResult` (asserted via equality before/after two separate
scenario calls); confidence always strictly bounded below full certainty
even when the underlying leg is fully confident (0.75 cap on a separate
full-stats fixture engineered so the underlying leg's own confidence is
genuinely 1.0); a `RETROFIT`-sourced scenario option correctly citing its
real source `variant_id`; and Why-Not distinguishing "recommended,"
"considered but below the signal threshold," and "never entered any leg at
all" as three different, honestly-labeled facts. Also added a short new
section 18 to `GAP_RECOMMENDATION_ENGINE.md` and a new `ScenarioRecommendation`
entry (section 39) to `DATA_SCHEMA.md`, explicitly cross-referencing and
distinguishing this from the unrelated `ScenarioObjective`
(`DATA_SCHEMA.md` section 21B).

Constraints honored: touched only `analysis/gap_recommendation.py`
(additive only -- the existing native/retrofit/acquisition ranking logic
is byte-for-byte unchanged, verified by the full pre-existing
`tests/test_gap_recommendation.py`/`tests/test_gap_recommendation_result_
cache.py` suites passing unmodified), `core/heuristics.py` (a new,
additive `baseline_0.11` -- every earlier baseline's `.values` dict is
unchanged), `GAP_RECOMMENDATION_ENGINE.md`, `DATA_SCHEMA.md`, and this
project's own new test file; did not touch `gui/`, `pyproject.toml`'s
version, any build/release script, `core/cache.py`,
`core/result_cache.py`, `analysis/change_impact.py`,
`analysis/complex_hull_audit.py`, `analysis/composite_hulls.py`,
`analysis/calibration.py`, `analysis/calibration_runner.py`,
`tools/*calibration*.py`, or `core/overrides.py`; read
`analysis/build_archetypes.py`/`analysis/mechanical_archetypes.py`/
`analysis/capability_vector.py` but made no changes there (no genuine
addition was needed). No git operations were performed (git reported
inaccessible due to dubious ownership from a separate concurrent process,
as expected in this environment).

14 new tests. Full suite: 598 passing (584 + 14), 1 skipped, 0 regressions
-- re-confirmed the true 584-passing/1-skipped starting baseline (the
task's own stated 579 figure was already stale by the time this phase
started, due to concurrent Phase 28 work landing in this shared repository
this session) before any edit. `ROADMAP.md` Phase 31 marked
`COMPLETE_WITH_LIMITATIONS`: the new `INFERRED_SCENARIO_OPTION` category
is real, tested, and cleanly separated from the mature ranking, but the
scenario-fit formula itself is a genuinely first-pass heuristic (like
several other thresholds this engine already carries honestly as
first-pass) rather than a benchmarked one, and it is not yet wired into
`api.py`/the CLI/GUI -- the task's own concrete scope was the analysis-
layer function plus tests, not end-to-end surface wiring, so that remains
explicit future work rather than a silent gap.

**Evidence/provenance unification (2026-08-25, ROADMAP Phase 29, charter
Priority 7):** re-confirmed the 598-passing/1-skipped starting baseline
before any edit (matching this task's own stated figure exactly). Read
`core/evidence.py` and every real usage of `EvidenceClass`/`EvidenceRecord`
across the codebase before assuming a redesign was needed: the enum's 9
values already match the charter's named vocabulary exactly (`DIRECT_DATA`,
`LOCAL_SOURCE_CODE`, `LOCAL_CONFIG`, `ADAPTER_MODELED`, `CURATED_GUIDANCE`,
`REVIEWER_EXPECTATION`, `INFERRED_MECHANICS`, `UNKNOWN`, `CONFLICTING`), so
no extension was made. Also corrected a real imprecision: this project's own
2026-08-23 "Composite structural profiles" entry above reads as if
`EvidenceClass` were already a field on those structural records; verified
directly against `analysis/composite_hulls.py` that it is not -- that
sentence describes `analysis/hullmod_static_analysis.py`'s already-real
`LOCAL_SOURCE_CODE` usage, landed the same session and discussed in the same
paragraph, not a field on the composite-hull records themselves.

Already-migrated producers found and left untouched, confirming real prior
progress beyond what the task's framing assumed: `analysis/
hullmod_static_analysis.py` (full `EvidenceRecord` tuples with file/line/
confidence) and `analysis/capability_vector.py`, `analysis/
build_archetypes.py`, `analysis/mechanical_archetypes.py`, `analysis/
calibration.py`, `generation/candidate.py` (each already carries a trailing
`evidence_class: EvidenceClass` field defaulted to `INFERRED_MECHANICS` or
`REVIEWER_EXPECTATION`, the same convention this phase's own migrations
continue). `analysis/gap_recommendation.py` also already uses it but sits
outside this phase's file scope (a separate concurrent `ScenarioCategory`
effort landed there this session) and was read, not touched.

Migrated three further, genuinely informal producers, entirely additively
(one new trailing dataclass field with a default value per record type; no
existing field, return type, or call-site signature changed anywhere):

1. `analysis/doctrine.py`'s `DoctrineEvidence` (previously only a bare
   `notes: tuple[str, ...]` string as its citation) gains `evidence_class`,
   computed per call as `INFERRED_MECHANICS` when real variants were
   examined and `UNKNOWN` when none were -- a genuine conditional, not a
   static default, since "no evidence exists" and "a real but statistical
   usage pattern exists" are different claims.
2. `analysis/equipment_affinity.py`'s `EquipmentAffinityClassification`
   (previously only `owning_faction_ids` as informal citation) gains
   `evidence_class`, computed as `CURATED_GUIDANCE` for a knowledge-pack
   `APPROVED` result and `DIRECT_DATA` for every other tier -- including the
   negative `UNALIGNED` case, itself a real fact directly read from the
   parsed data, not an inference.
3. Five adapter-effect-consumer records sharing one exact shape and
   rationale: `analysis/civilian.py`'s `AppliedLogisticsEffect`/
   `AppliedReductionEffect`, `analysis/combat_stats.py`'s
   `AppliedDefenseEffect`, `analysis/mobility_stats.py`'s
   `AppliedMobilityEffect`, `analysis/flux_stats.py`'s `AppliedFluxEffect`,
   and `analysis/weapon_range_stats.py`'s `AppliedWeaponRangeEffect` (found
   by grepping sibling test files during this phase -- not in the task's
   own suggested list, but the same family; leaving it out would have left
   the "adapter-effect consumers" theme inconsistently half-migrated). All
   five fixed at `ADAPTER_MODELED`: correct by construction, since every
   instance of each record type only ever exists when a verified
   `adapters/vanilla` effect-table entry actually produced it.

Deliberately left alone, with reasoning: `analysis/classification.py` (its
role/property tags already *are* the citable evidence, and the types are
consumed very widely across the pipeline, so migrating added real risk
without adding real explanatory power); `analysis/composite_hulls.py` and
`analysis/hullmod_static_analysis.py` (explicitly read-only per this
phase's own scope -- read fully to understand precedent, not modified).
`UNKNOWN_SCRIPTED_EFFECT` bare-string-marker migration (the task's item 4)
was not touched anywhere: it appears only in `hullmod_static_analysis.py`,
`analysis/mod_acceptance.py`, and `analysis/complex_hulls.py`, none of which
this phase's three chosen producers touch -- the task's own instruction was
to migrate it "where you touch that code path," so this is a correct
no-op, not a silent gap.

7 new regression tests, all synthetic-fixture-based (invented ids, no real
mod data), each exercising a real, non-mocked end-to-end path through its
analyzer: `tests/test_doctrine.py` (+2: `INFERRED_MECHANICS` with real
examined variants, `UNKNOWN` with zero), `tests/test_equipment_affinity.py`
(assertions added to 2 existing tests -- `CURATED_GUIDANCE` for the
already-existing `APPROVED`-via-knowledge-pack test, `DIRECT_DATA` for the
already-existing `UNALIGNED` test -- no new test count), and one new test
each in `tests/test_civilian.py`, `tests/test_combat_stats.py`, `tests/
test_mobility_stats.py`, `tests/test_flux_stats.py`, `tests/
test_weapon_range_stats.py` asserting `ADAPTER_MODELED` on a real applied
effect. `DATA_SCHEMA.md`'s `EvidenceClass` section (section 1) extended
with a paragraph naming every migrated producer and its exact evidence-class
mapping, plus the composite-hulls correction above.

`ROADMAP.md` Phase 29 marked `COMPLETE_WITH_LIMITATIONS`: the shared
`EvidenceClass` vocabulary itself required no changes and eight producers
now correctly cite it (five pre-existing, three landed this phase), but the
charter's own broader ask -- "every analyzer converges on" it -- remains a
larger, multi-phase migration surface by deliberate scope choice, not
oversight: `analysis/classification.py`, `analysis/
faction_capability.py`'s own `strengths`/`weaknesses`/`capability_gaps`
string-tuple fields (distinct from its already-migrated `CapabilityEvidence`
sub-field), and several report/output-layer producers remain unmigrated,
named here as real follow-on candidates rather than left as an unstated
gap. No git operations were performed (git reported inaccessible due to
dubious ownership from a separate concurrent process in this environment,
as expected). Constraints honored: did not touch `gui/`, `pyproject.toml`'s
version, any build/release script, `core/cache.py`, `core/result_cache.py`,
`analysis/change_impact.py`, `analysis/calibration.py`, `analysis/
calibration_runner.py`, `tools/*calibration*.py`, `analysis/
gap_recommendation.py`, or `analysis/scenario_objectives.py`; did not modify
the working logic of `analysis/composite_hulls.py` or `analysis/
hullmod_static_analysis.py`, only read them. 7 new tests. Full suite: 605
passing (598 + 7), 1 skipped, 0 regressions.

**Recommendation Audit Object / Why-Not Consistency (2026-08-25, ROADMAP
Phase 32, charter Priority 10):** resumed after a mid-session usage-limit
cutoff, not restarted -- read `analysis/gap_recommendation.py` in full
first to establish exactly what a prior pass on this same phase had
already landed on disk: `RecommendationAudit` (a frozen dataclass carrying
one real candidate's complete ranking context) already existed and was
already genuinely wired through all three legs' `recommend_*_solutions`
AND `explain_*_candidate` functions via a dedicated audit-trail builder
per leg (`_native_audit_trail`/`_retrofit_audit_trail`/
`_acquisition_audit_trail`), and `tests/test_gap_recommendation.py`
already contained `RetrofitAuditConsistencyTests`/
`AcquisitionAuditConsistencyTests` plus an identity-assertion addition to
the native leg's existing `BuildAwareWhyNotConsistencyTests` -- all three
proving exact (`assertEqual`) identity of score/rank/selection-reason
components between the ranking path and Why-Not for a structurally-varied
5-hull synthetic fixture. Full suite already stood at 607 passing (605 +
2 test classes), 1 skipped, matching the resumed task's own stated
starting figure.

Found one real, previously unexposed gap while verifying that existing
coverage actually satisfied the phase's own "score/confidence/evidence"
identity bar: none of the three Why-Not explanation types
(`WhyNotExplanation`/`RetrofitWhyNotExplanation`/
`AcquisitionWhyNotExplanation`) carried a `confidence` field at all, so no
test -- including the ones already landed -- could have proven confidence
identity even where score/rank already matched. Added `confidence: float
\| None = None` to all three, computed by a new
`_capability_gap_confidence_inputs(profile, role, heuristic_set)` helper
that mirrors `detect_capability_gaps`'s own per-role
`evidence_confidence`/`vector_confidence` formula exactly (factored out
via a new `_ROLE_CAPABILITY_DIMENSION` module constant so both call sites
share one literal table, never two that could drift), generalized to work
for a role that is not currently a detected WEAK/GAP-tier gap for the
faction -- Why-Not can legitimately be asked about any role, not only a
role the real ranking currently treats as a gap. `_recommendation_confidence`
(the existing per-`CapabilityGap` helper every ranking function already
calls) was refactored to delegate to a new raw-values sibling,
`_recommendation_confidence_from_values`, with zero call-site or behavior
change at any existing site -- confirmed by the full existing suite
passing byte-for-byte unmodified before any new assertion was added. Wired
into all three `explain_*_candidate` functions using the same audit-trail
entry (`best_hull_audit`/`best_audit`) each already resolves for its
rank/score, so the confidence value cited is provably the same
`RecommendationAudit`-adjacent `extra["build"]` reference the real ranking
used for that exact candidate, not a second lookup.

Added the identity assertions themselves to the three existing consistency
tests (`self.assertIsNotNone`/`self.assertEqual(own.confidence,
explanation.confidence)` in the native, retrofit, and acquisition test
classes). Doing so surfaced a real test-authoring gap, not a production
bug: `AcquisitionAuditConsistencyTests` had been feeding
`recommend_acquisition_solutions` a hand-built `CapabilityGap(...,
evidence_confidence=1.0)` rather than a gap derived from
`analyze_faction_capability`/`detect_capability_gaps` the way the sibling
native/retrofit tests already did -- a synthetic gap the real
`recommend_gap_solutions` pipeline would never actually construct (every
real caller only ever passes gaps `detect_capability_gaps` itself
produced), so the test's own confidence value (0.95) could never have
matched `explain_acquisition_candidate`'s independently, correctly
recomputed real value (0.75) regardless of production correctness. Fixed
by deriving the real gap the same way, which both makes the identity
assertion meaningful and confirms `explain_acquisition_candidate`'s
confidence computation is correct.

Also verified, and recorded here rather than silently assuming: the
Scenario leg (`analysis/gap_recommendation.py::recommend_scenario_solutions`/
`explain_scenario_candidate`, ROADMAP Phase 31) is correctly NOT migrated
to `RecommendationAudit` -- by design it reads the Native/Retrofit/
Acquisition legs' own already-ranked, already-audited records directly
rather than performing an independent ranking of its own, so there is no
separate "ranking vs. Why-Not" computation there to consolidate;
`explain_scenario_candidate` already reuses `recommend_scenario_solutions`'s
exact ranking by construction, unchanged by this phase. Added a new
SVG-018 entry to `docs/BUGS.md` (referenced by name throughout
`gap_recommendation.py`'s own docstrings since the earlier pass, but never
actually entered in the tracker) documenting the retrofit/acquisition
Why-Not disagreement this phase's audit-trail consolidation fixes.

Constraints honored: touched only `analysis/gap_recommendation.py`
(additive field/helper changes plus the confidence wiring inside the three
`explain_*_candidate` functions -- no ranking, selection, or legality
logic changed), `tests/test_gap_recommendation.py`, `docs/BUGS.md`,
`ROADMAP.md`, `docs/IMPLEMENTATION_STATUS.md`, and this log; did not touch
`gui/`, `pyproject.toml`'s version, any build/release script,
`core/cache.py`, `core/result_cache.py`, `analysis/change_impact.py`,
`analysis/calibration.py`, `analysis/calibration_runner.py`,
`tools/*calibration*.py`, `analysis/composite_hulls.py`, or
`analysis/hullmod_static_analysis.py`. No git operations were performed
(git reported inaccessible due to dubious ownership from a separate
concurrent process in this environment, as expected). No observable
ranking order, score, or legality outcome changed anywhere -- confirmed by
the full pre-existing suite passing unmodified before any new assertion
was added, and by every new/extended assertion asserting equality against
values the codebase already independently computed, never a new value.
`ROADMAP.md` Phase 32 marked `COMPLETE_WITH_LIMITATIONS`: all three
in-scope legs (Native/Retrofit/Acquisition) are fully consolidated on
`RecommendationAudit` and regression-tested for exact score/confidence/
evidence identity; the Scenario leg is correctly out of scope by design
(explained above, not an oversight); `RecommendationAudit` itself remains
deliberately uncached/unpersisted, matching this project's "everything is
read fresh per command" architecture. 0 new test methods this session (the
2 new test classes were already landed in the earlier, cut-off pass); this
session's own work extended those and the native leg's existing test with
new assertions rather than adding test count. Full suite: 607 passing (605
+ 2, unchanged by this session), 1 skipped, 0 regressions.

**GUI Modularization (2026-08-25, ROADMAP Phase 35, charter Priority 16,
deliberately last):** started only after confirming every other charter
phase (26-34) was already landed, per the charter's own explicit
sequencing ("only then consider incremental decomposition of
main_window.py"). Confirmed the true starting baseline before touching
anything -- 607 passing, 1 skipped, matching this task's own stated
figure exactly. Read `gui/main_window.py` in full (1169 lines, grown from
roughly 420 pre-session across this session's worker-lifetime fix, Mirror
fitting, incremental drag-and-drop, the ship-canvas redesign, and the
Phase 25 layout restructuring) plus `GUI.md` and every sibling module
(`session.py`, `resources.py`, `theme.py`, `presentation.py`, the two
workers) first, so any new module followed this project's existing flat
`gui/*.py` layout rather than inventing `views/`/`widgets/`/`controllers/`
subpackages. Also found, and correctly left alone: `gui/ship_view.py`
(plus `main_window.py.pyqt6-attempt.bak`), a dead PyQt6-based module (this
project's real GUI dependency is PySide6) with zero references anywhere
in `src/` or `tests/` confirmed by a full-repo grep -- an abandoned
prototype, not part of the live file this phase decomposes, so not
touched.

Extracted three self-contained, zero-`MainWindow`-state pieces, verifying
the full suite after each individual move rather than batching multiple
large extractions before checking, per this phase's own "extract, verify,
extract, verify" instruction:

1. `gui/canvas.py` -- `TechnicalCanvas` (the `QGraphicsView`-based Ship
   Fitting Canvas: mount-box rendering, click-to-select hit-testing,
   zoom/pan/reset, the `slot_clicked` signal) plus its module-level
   constants (`MOUNT_TYPE_COLORS`, `_MOUNT_BOX_HALF_EXTENT` and their
   fallbacks) and the two pure helpers operating on the same hull mount
   geometry the canvas already reads (`_number`, `_detect_mirror_mount_pairs`).
2. `gui/helpers.py` -- `_looks_like_starsector_install`, the one pure
   helper with no real relationship to the canvas (an install-path sanity
   check used from `MainWindow.__init__`/`_start_scan`), given its own
   small module rather than forced alongside canvas code it has nothing
   to do with.
3. `gui/models.py` -- `EntityTableModel`, the Data/Analysis workspace's
   lazy Qt table model; confirmed via a full-repo grep to have zero
   external importers anywhere before this move, so no compatibility
   re-export concern applied there the way it did for the other two.

Every move was verbatim -- no logic, docstring, or comment content
changed, only import statements. `main_window.py` re-imports
`TechnicalCanvas`/`MOUNT_TYPE_COLORS`/`_detect_mirror_mount_pairs` (from
`gui/canvas.py`), `_looks_like_starsector_install` (from `gui/helpers.py`),
and `EntityTableModel` (from `gui/models.py`) at module scope, so
`tests/test_gui_canvas.py`'s existing direct imports of `MainWindow`,
`TechnicalCanvas`, and `_SCAN_STALL_WARNING_INTERVAL_S` from
`starsector_variant_generator.gui.main_window` (plus its two further
in-file imports of `_detect_mirror_mount_pairs` and
`_looks_like_starsector_install` from the same module) keep resolving
completely unchanged -- no test file needed editing.
`_SCAN_STALL_WARNING_INTERVAL_S` deliberately stayed in `main_window.py`:
it is scan-watchdog state, unrelated to the canvas or the install check.

Deliberately left in `main_window.py`, per this phase's own documented
risk guidance rather than an oversight: the ten tab-builder methods
(`_ships`/`_browse`/`_browser`/`_center`/`_inspector`/`_inspector_tab`/
`_generate_tab`/`_retrofits`/`_faction`/`_data`/`_settings`) and every
worker-orchestration method (`_run`, `_start_scan`, `_generate`, the
refit/faction/export flows). Each of these assigns dozens of `self.xxx`
widget attributes that other `MainWindow` methods read directly by name
elsewhere in the same class -- splitting them out would require either
exposing a large, fragile cross-module shared-state surface, or converting
the file's cohesive single-object widget-attribute model into something
more brittle purely to hit a line-count target. Not attempted, matching
this phase's own explicit instruction not to force a risky restructuring
of that shape.

Result: `main_window.py` 1169 -> 921 lines (-248, -21%); three new sibling
modules (`gui/canvas.py` 226 lines, `gui/helpers.py` 27 lines, `gui/models.py`
47 lines). Full suite re-run after each of the three extractions and once
more at the end: 607 passing, 1 skipped, 0 regressions at every checkpoint
-- the exact same test count, same assertions, and same results as the
confirmed starting baseline throughout, including `tests/test_gui_canvas.py`'s
full 61-test class (the suite that exercises `TechnicalCanvas` rendering,
hit-testing, mirror-pair detection, and `_looks_like_starsector_install`
directly). Constraints honored: touched only `src/starsector_variant_generator/gui/`
(the only phase permitted to); did not touch `pyproject.toml`'s version,
any build/release script, or any backend module
(`analysis/`/`core/`/`api.py`); performed no git operations (git reported
inaccessible due to dubious ownership from a separate concurrent process
in this environment, as expected). `ROADMAP.md` Phase 35 marked
`COMPLETE_WITH_LIMITATIONS`: a genuine, fully-verified partial
decomposition, honest per this phase's own explicit charter language ("a
partial, well-verified extraction... is a legitimate... outcome; don't
force a risky, larger restructuring just to claim more progress") -- not a
full breakdown of every remaining GUI concern; the tab-builder and
worker-orchestration methods, the large majority of the remaining 921
lines, stay as one cohesive `MainWindow` class by deliberate, documented
choice rather than an unstated gap. 0 new tests (a pure file-organization
move; no new behavior to test). Full suite: 607 passing (unchanged), 1
skipped, 0 regressions.

**Scan Performance (2026-08-25, ROADMAP Phase 37, user Phase 1):** confirmed
the 608-passing/1-skipped baseline first, then worked the phase's scope in
order: the 1/2/4/8 scan-worker benchmark against the real 149-mod install had
already run earlier this session (workers=1 median 22.6s, workers=2 21.3s,
workers=4 22.4s, workers=8 24.9s, all cold-cache), reconfirming the existing
"serial PARSING is already optimal" finding, so `Scanner.max_workers` stayed
unchanged. Fingerprinting is a different shape of work (many small,
independent per-source hash reads) and was measured separately rather than
assumed to share PARSING's conclusion: an isolated microbenchmark against
every real discovered source (correctness-checked identical to serial output)
found 4 workers the consistent best (serial median 8.67s -> 4 workers median
5.53s), confirmed with a direct same-harness A/B on `Scanner.scan()` itself
(`tools/profile_scan.py`, forcing the new pool to 1 worker for "before"):
warm-cache scan total dropped from median 5.89s to 3.84s (~35%), cold from
20.72s to 17.56s. Implemented as `Scanner._source_fingerprint_isolated`, a
bounded 4-worker pool independent of `max_workers`, dispatched up front so
real hashing overlaps in the background while the coordinator still harvests
in fixed index order -- FINGERPRINTING progress events keep their existing
deterministic per-source cadence unchanged. Separately, PARSING's own
parse-future harvest switched from blocking on `futures[index].result()` in
submission order to `concurrent.futures.as_completed()`, so a
later-submitted-but-faster source's progress/cache-write is no longer
delayed behind an earlier, still-running one; the merge into `result` still
walks sources in fixed index order regardless of harvest order (new
regression test: `test_parse_futures_harvest_in_completion_order_but_merge_
stays_deterministic`, which deliberately makes `core` the slowest source and
asserts both true out-of-order progress and byte-identical merged output vs.
a plain serial scan). Considered an mtime/size staleness pre-check for an
additional warm-start win; declined it -- `Scanner` is deliberately stateless
across process invocations, so this would need a new persistent stat-cache
artifact and would weaken the real content-hash guarantee for an unmeasured,
likely-small gain, against this phase's own "never weaken a real staleness
guarantee" constraint. Re-read `output/analysis_reports.py`'s selective-reuse
system fully and found it already dependency-complete (per-hull, per-faction,
per-source-mod weapon/hullmod, per-source-mod hullmod-Java-analysis fragment
reuse all already exist from Phase 2); the one coarser boundary found
(weapon/hullmod classification fragments are per-mod, not per-entity) is a
deliberate, already-cheap pattern, reported as "no worthwhile gap found"
rather than invented scope. Added `ScanMetrics.stage_seconds["fingerprinting"]`/
`["source_parsing"]` (additive; the existing combined `"parsing"` key is
unchanged) and a new `ScanMetrics.cache_hit_rate` field, surfaced in
`tools/profile_scan.py`; read (read-only) `gui/main_window.py::_scan_
progressed` and confirmed the GUI's live dialog and post-scan summary never
show cache-hit information -- a real, found gap left unfixed since this
phase may not touch `gui/`. 6 tests added/updated in `tests/test_scanner.py`.
Full suite: 617 passing, 1 skipped, 0 regressions from this phase's own
changes (the count moved from the 608 baseline because an unrelated
concurrent process independently landed Phase 38's own tests during this
same session -- confirmed via file mtimes that none of this phase's scope
files were touched by that process). `ROADMAP.md` Phase 37 marked
`COMPLETE_WITH_LIMITATIONS`. See `docs/WORK_LOG.md`'s matching 2026-08-25
entry for full detail.

**Scenario Objective Expansion (2026-08-25, ROADMAP Phase 40, user Phase
4):** confirmed the 617-passing/1-skipped baseline first. Extended
`analysis/gap_recommendation.py::ScenarioCategory` from the Phase 31 set
(RAIDING/DEFENSE/ESCORT/PATROL) to 13 values, adding ANTI_ARMOR,
ANTI_SHIELD, LINE_HOLDING, LONG_RANGE_PRESSURE, MISSILE_STRIKE, PD_SCREEN,
CARRIER_SUPPORT, PURSUIT, and LOW_COST_REFIT_FRIENDLY -- 9 of the task's 11
suggested categories (BREAKTHROUGH and ENDURANCE deliberately omitted as
undifferentiable from ANTI_ARMOR and LINE_HOLDING/DEFENSE respectively,
documented in the enum's own docstring rather than silently dropped). Each
new category's `_scenario_fit_score` branch is backed by a real, cited
signal, most newly drawn from `analysis/capability_vector.py::
CapabilityVector` (ARMOR_BREAKING/KINETIC_PRESSURE real mounted-weapon
damage-type evidence for ANTI_ARMOR/ANTI_SHIELD; SUSTAINED_PRESSURE for
LINE_HOLDING; LONG_RANGE_PRESSURE for LONG_RANGE_PRESSURE; MISSILE_
PROJECTION+BURST_STRIKE for MISSILE_STRIKE; PD_SCREENING+FIGHTER_
INTERCEPTION for PD_SCREEN; CARRIER_PROJECTION+FIGHTER_INTERCEPTION for
CARRIER_SUPPORT; PURSUIT+MOBILITY, including verified adapter-derived
existing-variant speed, for PURSUIT) plus one purely structural economic
signal (`HullFeatureVector.ordnance_points` inverted +
`.existing_variant_count` for LOW_COST_REFIT_FRIENDLY, an axis no other
category references). `_scenario_fit_score` gained an optional
`capability: CapabilityVector | None = None` parameter threaded through
both real call sites; the original four categories are computed
byte-identically to before this phase (proven by the pre-existing test
suite passing unchanged bar one enum-membership assertion). No new
heuristic constant/baseline was needed -- every new weight is a literal
constant in the same style Phase 31 already established, and the existing
`baseline_0.11` scenario thresholds are reused unchanged.

"Multiple genuinely different best builds per hull": confirmed
`recommend_scenario_solutions` already supports this naturally (it is
parameterized by `scenario`, and each call independently ranks the same
real evidence), so the real gap was a caller convenience, not a ranking
limitation. Added `scenario_fits_for_hull(faction, registry, gap_result,
hull_id, ...)`, a pure wrapper over the unmodified `recommend_scenario_
solutions` (called once per category, filtered to one hull's own
shortlisted entries) that introduces no new ranking/scoring logic of its
own. Confirmed Phase 32's `RecommendationAudit` docstring already explains
why the scenario leg is deliberately not migrated to it (`explain_scenario_
candidate` reuses `recommend_scenario_solutions`'s exact ranking by
construction, so there is no separate ranking-vs-Why-Not computation to
drift) -- that invariant holds unchanged after this phase's additions.

22 tests in `tests/test_scenario_recommendation.py` (8 new methods over the
pre-existing 14): hand-verified fit_score/recommended values for all 9 new
categories x 3 builds against the shared Phase 31 fixture (including a real
exactly-at-threshold boundary case), two dedicated real-weapon-evidence
fixtures (HE and KINETIC damage types) proving ANTI_ARMOR/ANTI_SHIELD don't
leak into each other, and `scenario_fits_for_hull` coverage (exact
qualifying-category set, empty portfolio for an unresolved hull, restricted
`categories` argument). Full suite: 625 passing (617 baseline + 8 new), 1
skipped, 0 regressions. `ROADMAP.md` Phase 40 marked
`COMPLETE_WITH_LIMITATIONS`. Constraints honored: touched only
`analysis/gap_recommendation.py` and its own tests; `analysis/build_
archetypes.py`/`analysis/mechanical_archetypes.py`/`analysis/capability_
vector.py` read but not modified; `core/heuristics.py`, `gui/`,
`pyproject.toml`'s version, build/release scripts, `core/scanner.py`,
`core/cache.py`, `core/result_cache.py`, `output/analysis_reports.py`,
`analysis/hullmod_static_analysis.py`, `adapters/`, `analysis/calibration.py`,
`analysis/calibration_runner.py`, `analysis/composite_hulls.py`, and
`analysis/change_impact.py` all untouched. See `docs/WORK_LOG.md`'s matching
2026-08-25 entry for full detail.

**Calibration deepening and heuristic-tuning reporting (2026-08-25, ROADMAP
Phase 39, user Phase 3):** extends Phase 30 (Calibration Activation, above)
purely with new reporting/comparison capability -- the hard boundary from
CLAUDE.md and Phase 30's own `activation_requires_reviewer_approval: true`
contract is unchanged: neither `analysis/calibration.py` nor
`analysis/calibration_runner.py` reads or writes `core/heuristics.py::REGISTRY`
anywhere (still asserted directly by
`tests/test_calibration_activation.py::test_activation_never_touches_the_heuristic_registry`,
which passes unchanged against the new code). Verified what already existed
before changing anything: the 2026-08-23 "Calibration expectation kinds" entry
above (build/equipment/faction/scenario/negative expectation kinds,
`HARD_EXPECTATION`/`SOFT_EXPECTATION`/`OBSERVATION` strengths) was real and
complete at the data-model level; the real, confirmed gap (documented by
Phase 30 itself) was that only `BUILD_EXPECTATION`/`NEGATIVE_EXPECTATION` had
a registered runtime observer -- `EQUIPMENT_EXPECTATION`/`FACTION_EXPECTATION`/
`SCENARIO_EXPECTATION` labels could be loaded and validated but never
evaluated against real output.

Added, all additive to the existing model: (1) a new `EXPECTED_TOP_SET`
expectation kind (`CalibrationLabel.top_n`, default 3) -- `evaluate_calibration`
gained a rank-based comparison branch reading `actual_rank` instead of
`actual`/`expected_any`, MATCH when `1 <= actual_rank <= top_n`; every prior
kind's comparison rule, including `NEGATIVE_EXPECTATION`'s forbidden-set rule,
is byte-unchanged. (2) Runtime observers for the three previously-dormant
kinds: `collect_build_observations` (build-level `hull:<mod>:<id>` keys)
extended to also produce `actual_rank` (build_archetype rank within
`api.run_generate`'s own real, already-sorted LEGAL candidate list -- a
sentinel `NOT_IN_RANKED_SET = 10**6` when the expected candidate never
appeared, so "not found in a real search" is a genuine MISMATCH, never a
fabricated UNSUPPORTED) and mount-specific `EQUIPMENT_EXPECTATION` observation
(`CalibrationLabel.mount_id`, reading the best real candidate's
`weapons_by_mount` -- "any weapon in this documented set is an acceptable
substitute" already worked via the pre-existing generic `expected_any`
mechanism; only the observer to produce a real `actual` was missing). A new
`collect_faction_and_scenario_observations` (new `faction:<faction_id>:<role>:
<mod>:<hull_id>` and `scenario:<faction_id>:<category>:<role>:<mod>:<hull_id>:
<build_archetype_id>` entity_key schemes) reuses the real, already-audited
Why-Not functions (`explain_native_candidate`, Phase 32's `RecommendationAudit`;
`explain_scenario_candidate`, Phase 31/40) rather than re-deriving ranking --
closing item 1's stated observer gap and item 3 (scenario-specific
calibration) in one design. A hull that IS a real, resolved candidate but
scores zero, or a Hull+Build pair that IS real but never shortlisted, is
recorded as real negative evidence (`NOT_RECOMMENDED` / the top-set sentinel),
not silently folded into UNSUPPORTED -- only a genuinely unresolved
faction/hull/category/build produces UNSUPPORTED. `collect_all_observations`
combines both observers by entity_key prefix with no ranking of its own;
`tools/evaluate_local_calibration.py` now calls it instead of
`collect_build_observations` alone (identical output for an existing
BUILD_EXPECTATION-only fixture, a strict superset otherwise).

(4) Confirmed "mechanical-equivalent equipment expectations" needed no new
comparison logic -- `expected_any` already applied generically to every kind
before this phase; only the `EQUIPMENT_EXPECTATION` observer above was
missing. (5) Two new pure reporting functions, neither touching
`core/heuristics.py`: `confidence_weighted_summary(report, confidences)`
buckets already-computed MISMATCH entries by a caller-supplied confidence
(sourced from a real `WhyNotExplanation.confidence` etc., never fabricated
when absent -- reported as a separate `UNKNOWN_CONFIDENCE_MISMATCH` bucket
instead) into HIGH/MEDIUM/LOW/UNKNOWN, purely as reporting nuance;
`compare_calibration_reports(report_a, report_b)` diffs two
`CalibrationReport`s for the same fixture (e.g. the same real labels
evaluated under two different, already-existing, human-authored heuristic
sets) and reports which labels' MATCH/MISMATCH status changed, without
selecting or blending a "winner." A new `tools/compare_calibration_heuristics.py`
demonstrates the intended real-install workflow (`collect_all_observations`
run twice, under `--heuristic-set-a`/`--heuristic-set-b`, diffed and written
under `generated/`) but was not actually run against a real installation in
this session -- no local Starsector install was reachable in this
environment/session (unlike Phase 30's, which had one); its `--help` output
and a synthetic argument-parse check were verified instead, honestly
recorded as not yet live-verified rather than fabricated.

**The human decision point** (CLAUDE.md's hard rule, restated per this
phase's own explicit instruction): every new function here stops at a report
-- `evaluate_calibration`, `confidence_weighted_summary`, and
`compare_calibration_reports` all return plain data for a person to read;
none selects, writes, or returns a new heuristic value, and no new
`baseline_0.1x` registry entry was added by this phase. A source-scan guard
(pre-existing, re-verified passing against the new code) proves neither
calibration module imports `core/heuristics.py`'s `REGISTRY` at all -- the
same structural evidence Phase 30 established, now covering roughly 3x as
much calibration code.

24 new/extended regression tests, all synthetic-fixture-based (no real
mod/reviewer data): 10 in `tests/test_calibration.py` (EXPECTED_TOP_SET
match/unsupported/stale, fixture-loading of `top_n`/`mount_id`,
`confidence_weighted_summary`'s bucketing and no-fabricated-default rule,
`compare_calibration_reports`'s diff/no-diff/mismatched-fixture-id cases),
12 in `tests/test_calibration_runner.py` (4 extending
`collect_build_observations`'s new rank/equipment branches, including a
regression proving an ILLEGAL candidate never counts toward
EXPECTED_TOP_SET's rank; 8 new, entirely non-mocked
`FactionAndScenarioObservationTests` exercising the real
`explain_native_candidate`/`explain_scenario_candidate` call path against a
synthetic 2-hull faction fixture and the same `_line_brawler_fixture` shape
Phase 31's own test suite hand-verified, including the real
`collect_all_observations` merge-without-collision case). Full suite: 647
passing (625 confirmed starting baseline + this phase's own 22), 1 skipped, 0
regressions. `ROADMAP.md` Phase 39 marked `COMPLETE_WITH_LIMITATIONS`:
`FACTION_EXPECTATION`/`SCENARIO_EXPECTATION` observers hash-bind only to the
referenced hull's own `source_hash` (a rescan that changes only the
faction's OTHER known hulls, or the scenario category set, is not currently
detected as stale by that hash alone -- documented, not silently assumed);
the before/after comparison tool exists and is unit-verified but not yet
run against a real installation in this session. Constraints honored: did
not touch `gui/`, `pyproject.toml`'s version, any build/release script,
`core/scanner.py`, `core/cache.py`, `core/result_cache.py`,
`output/analysis_reports.py`, `analysis/hullmod_static_analysis.py`,
`adapters/`, `analysis/composite_hulls.py`, or `analysis/change_impact.py`;
`analysis/gap_recommendation.py` and `core/heuristics.py` were read (imported
from) but not modified. No git operations performed (git reported
inaccessible due to dubious ownership from a separate concurrent process in
this environment, as instructed/expected). See `docs/WORK_LOG.md`'s matching
2026-08-25 entry for full detail.

**Static Control-Suitability signals (2026-08-25, ROADMAP Phase 41, user
Phase 7, deliberately last):** the fifth and final phase of the second
user-specified round (Phases 37-40 above), gated by the user's own
instruction to start it "only after mechanics are strong enough" -- begun
only once Phases 37-40 all landed `COMPLETE_WITH_LIMITATIONS`. Confirmed the
647-passing/1-skipped starting baseline before touching anything (matches
this task's own stated figure). Read `AGENTS.md`/`FORMAL_SPECIFICATION.md`/
`DATA_SCHEMA.md` plus this row's own cited modules in full first --
`analysis/mobility_stats.py`, `analysis/combat_stats.py`,
`analysis/weapon_range_stats.py`, `scoring/candidate_score.py`,
`core/models.py::Weapon`/`Hull`, `analysis/variant.py`, and
`output/analysis_reports.py` -- to confirm real field names rather than
guess. Two real schema facts changed the plan from the task's own framing:
(1) `core/models.py::Weapon` has no typed ammo field anywhere, and no
`.wpn`/`weapon_data.csv` "ammo" column is parsed into it or read by any
other `analysis/` module (confirmed by repo-wide grep) -- `MISSILE` mount
type is the only real, documented proxy for ammo depletion this schema
has, so `ammo_dependence` is implemented and explicitly documented as a
mount-type-based proxy, never a fabricated ammo-count read; (2)
`core/models.py::Hull` likewise has no typed ship-system field --
`shipSystemId`/`systemId` only exist inside `Hull.raw["ship_data"]`
(`.ship` files) / `Hull.raw["skin_data"]` (`.skin` overrides), preserved
verbatim by `parsers/entities.py`, so `system_complexity` reads those raw
keys directly (with the same one-level skin-to-base-hull fallback
`mobility_stats.py`/`combat_stats.py` already establish for their own
CSV-column reads) rather than a nonexistent typed field.

New module `analysis/control_suitability.py`: a `StaticControlSuitability`
frozen dataclass with 8 independently-`None`-able, independently
`EvidenceClass`-cited signal fields -- `range_coherence` (`DIRECT_DATA`,
real equipped `Weapon.range` spread/mean, deliberately reading the raw base
range rather than `weapon_range_stats.py`'s opt-in heuristic-set-gated
COMBAT-hullmod adjustment, so this module carries no heuristic_set
dependency at all), `flux_stability` (`DIRECT_DATA`, a raw
dissipation/sustained-load ratio computed the same way
`scoring/candidate_score.py::_flux_component` computes it, but reported as
a plain number, never scored against a heuristic target), `burst_dependence`
(`DIRECT_DATA`, a real seconds-per-shot proxy from
`Weapon.flux_per_shot`/`Weapon.flux_per_second`, excluding -- never
fabricating an interval for -- a weapon with no discrete per-shot cost,
e.g. a beam), `ammo_dependence` (`DIRECT_DATA`, the `MISSILE`-mount-type
proxy described above), `mobility_vs_engagement_range` (`ADAPTER_MODELED`,
`analysis/mobility_stats.py`'s verified effective `max_speed` reported
side by side with real equipped weapon ranges -- deliberately NOT fused
into a "mismatch score", since no documented Starsector formula
establishes a "correct" speed for a given weapon range and inventing one
would be exactly the undocumented-behavior guess AGENTS.md forbids),
`system_complexity` (`DIRECT_DATA`, real ship-system presence/identity,
described above), `weapon_group_complexity` (`DIRECT_DATA`, real countable
mount count / distinct mount-type count / declared `.variant`
`weaponGroups` count from `Variant.raw`), and `survivability_posture`
(`ADAPTER_MODELED`, reusing `analysis/combat_stats.py::compute_derived_
defense_stats` unchanged -- the same verified DEFENSE-hullmod-adjusted
armor/hull-HP evidence already backing Phase 12's TANK-archetype
mechanical tie-break). No field combines multiple signals into one number,
and no aggregate "suitability score" was computed at all, per this phase's
own instruction not to invent unjustified combination weights.

Hard framing boundary held throughout: the module's own docstring states,
verbatim, that it is **not a combat outcome predictor** and never computes
a win-chance, expected-damage-traded, or other simulated/inferred outcome;
every field name and the record's own name use `STATIC_CONTROL_SUITABILITY`
exactly as required. A dedicated `ModuleBoundaryTests` guard (mirroring
`tests/test_calibration_activation.py`'s own heuristic-registry-import
guard) asserts the module's own source text never references
`validation.legality`/`validate_variant`/`LegalityResult`, and a second
test asserts both the class docstring and the module docstring literally
contain `STATIC_CONTROL_SUITABILITY` and "NOT a combat outcome predictor".

Wired into a real, low-risk consumer: not `output/analysis_reports.py`'s
hull mechanical profile (that report is hull/archetype-level, not
real-variant-level -- `infer_mechanical_archetypes`/`infer_build_
archetypes` describe non-exclusive synthetic build paths, not an actual
fitted loadout, so a per-variant signal set doesn't fit there without
restructuring the report, which this phase's own instruction says to avoid
risking). Instead wired into `analysis/variant.py::VariantAnalysis`/
`analyze_variant` -- a genuine, already-existing per-Variant analyzer
aggregator following the exact same pattern
(`compute_derived_mobility_stats`/`compute_derived_defense_stats`/etc.,
called only when `hull` resolves) this new module's own signals are built
from. Added one new, defaulted field,
`static_control_suitability: StaticControlSuitability | None = None`,
appended at the end of the dataclass and computed alongside the other
Hull-dependent slices -- purely additive, no other field changed, and
`cli/main.py`'s `analyze-variant` command already serializes the whole
`VariantAnalysis` via a generic `asdict()`, so the new signals appear in
`svg analyze-variant`'s JSON report with no CLI code change needed. `gui/`
was not touched at all, per this phase's hard constraint.

27 new tests in `tests/test_control_suitability.py`, following
`tests/test_weapon_range_stats.py`/`tests/test_mobility_stats.py`'s exact
synthetic-fixture conventions: each of the 8 signals gets a
correctly-computed-value case and a correctly-`None`-when-evidence-is-
missing case (e.g. `flux_stability` is `None` when any equipped weapon's
flux is unknown, `system_complexity` is `None` with no `ship_data`/
`skin_data` present at all but a real `has_ship_system=False` when
`ship_data` exists and simply declares no system, `weapon_group_complexity`
independently keeps its mount/type counts while `weapon_group_count` alone
goes `None` without a source `.variant` file), plus the two module-boundary
guard tests above. `tests/test_variant_analysis.py`'s existing suite passes
unchanged (the new field defaults, so no prior positional/keyword
construction broke). Full suite: 674 passing (647 confirmed starting
baseline + this phase's own 27), 1 skipped, 0 regressions. `ROADMAP.md`
Phase 41 marked `COMPLETE_WITH_LIMITATIONS`: all 8 named signals were
implemented with real, cited evidence and wired into a genuine consumer
(not left orphaned), but `ammo_dependence` is honestly a mount-type proxy
rather than a real ammo-count read (no such field exists anywhere in this
project's schema) and `mobility_vs_engagement_range` deliberately reports
two raw numbers rather than a combined mismatch judgment (no documented
combination rule exists) -- both are named, deliberate scope limits, not
silently assumed completeness. Constraints honored: did not touch `gui/`,
`pyproject.toml`'s version, any build/release script, `core/scanner.py`,
`core/cache.py`, `core/result_cache.py`,
`analysis/hullmod_static_analysis.py`, `adapters/` (read-only, for real
signal sourcing only), `analysis/composite_hulls.py`,
`analysis/change_impact.py`, `analysis/calibration.py`,
`analysis/calibration_runner.py`, or `analysis/gap_recommendation.py`;
`output/analysis_reports.py` was read but not modified (the wiring instead
went into `analysis/variant.py`, documented above). No git operations
performed (git reported inaccessible due to dubious ownership from a
separate concurrent process in this environment, as expected). This closes
out the second user-specified round of five phases (37-41). See
`docs/WORK_LOG.md`'s matching 2026-08-25 entry for full detail.

**Video-review transcript evidence (2026-08-26):** Added a portable,
advisory-only `VIDEO_REVIEW_TRANSCRIPT` source class and a local JSON loader
for timestamped player/AI observed-gameplay claims. Its typed
`ControlSuitabilityEvidence` keeps player and AI claims distinct and leaves
display-name-to-hull binding unresolved until a unique locally scanned hull and
version context are available. Shared provenance precedence places transcript
evidence below all local mechanical evidence and above generic unsourced
guidance; it cannot affect legality or candidate scoring. The supplied
provisional transcript loaded 57 explicit control claims through that path.
The consumer wiring now resolves only exact unique local hull names; the Refit
comparison displays applicable claims beside mechanical analysis, and the
Faction workspace accepts an optional resolved knowledge pack for capability
and recommendation requests. The existing bounded role-match refit sequence
already covers the known multi-weapon plateau case. Focused GUI/refit/evidence
regression: 95 passing; complete suite: 679 passing, 1 skipped.

**Numeric source-field normalization (2026-08-26):** Added shared
`parse_int`/`parse_float` utilities for parsed source data. They trim optional
values, accept integral decimal text for integer fields, reject non-finite and
non-integral values, and return a declared fallback rather than raising.
Invalid nonblank input is retained in `ScanResult.parse_warnings` as structured
`INVALID_NUMERIC_VALUE` diagnostics with field, source path, source mod, and
entity ID. CSV/skin/variant numeric fields now use this path; normalized typed
fields, rather than raw CSV text, drive hull carrier classification. The local
all-installed verification recorded seven explicit malformed numeric fields and
completed the previously blocked faction-recommendation calls without an
exception. Focused parser/classifier/scanner/generation/recommendation tests:
118 passing.

**Provenance-scoped resolution and explicit unsupported states (2026-08-26):**
The registry now retains bare duplicate IDs as ambiguous, but resolves a
**hullmod** reference against the variant source mod's declared dependency closure:
a unique local/dependency claimant wins, otherwise an unambiguous core claimant
is the base fallback. `Registry.trace_reference()` records whether this was a
normal, canonical-identical, contextual, ambiguous, or missing lookup; it does
not claim that a selected scripted effect is understood. The candidate payload
now has typed omission records: `STRUCTURAL_SLOT_OMITTED` (built-in, launch-bay,
or station-module fixtures) is distinct from `UNSUPPORTED_MOUNT_SEMANTICS`.
The source-only hullmod analyzer also reports `COMPILED_ONLY_SCRIPT` with
unavailable static coverage when a declared class has no readable local source
but its mod contains JAR artifacts. This is a reporting state, not bytecode
execution, decompilation, or mechanic inference. The analysis-report schema is
versioned to invalidate old reusable fragments. No adapter was added.
Full regression: 690 passing, 1 skipped.

**Duplicate identity versus declared-reference resolution (2026-08-26):**
Hullmod duplicate reporting now records an independent global identity state:
`DUPLICATE_IDENTICAL` or `DUPLICATE_DIVERGENT`, with every source's stable
semantic hash. Identical definitions are canonically indexed (core preferred)
with `CANONICALIZED_DUPLICATE`; divergent definitions remain globally visible
as conflicts. A declared variant reference may nevertheless resolve through a
strict provenance hierarchy: its own source definition, exactly one declared
dependency definition, then a unique core baseline. It never selects an
unrelated mod merely because it shares an ID, and multiple relevant divergent
candidates remain `AMBIGUOUS_CONFLICT`. Contextual trace output preserves the
selected source, method, global identity state, semantic hashes, and every
shadowed unrelated candidate with `NOT_CONTEXT_RELEVANT`. This is declared
reference resolution only; runtime load-order-effective definition semantics
remain intentionally unmodeled. Regression coverage includes identical,
unrelated, same-mod, dependency, and multiple-relevant-conflict cases.

**Combat entity kind and recommendation eligibility (2026-08-26):** Added a
generic `CombatEntityKind`/`RecommendationEligibility` contract, deliberately
separate from legality. Parsed fighter-sized hulls, unboardable hulls,
ship/station modules, and composite parents are classified from explicit hull
size/hints and excluded from ordinary independently-fitted ship
recommendations with a reason and structural-support state. `NORMAL_SHIP`
remains eligible; no combat mechanics, custom AI, or module aggregate behavior
was inferred, and legality was not changed. Native, retrofit, and acquisition
candidate pools now honor the same eligibility filter; hull query output
exposes the decision.
Full regression: 692 passing, 1 skipped.

**Entity kind versus deployment model (2026-08-26):** The generic combat
entity contract now distinguishes `SHIP`, modules/composite parents, fighter
and direct wing subtypes, `DRONE`, `MECH`, `STRIKECRAFT`, and unboardable
entities from a separate `DeploymentModel`. Fighter-sized hull geometry is
therefore not treated as evidence that a hull is a wing member. Actual parsed
fighter-wing role text supplies only direct subtype scores; mech/drone/
strikecraft hull classifications require explicit source hints. Payload,
replacement, carrier dependency, custom AI behavior, and system-spawned
semantics remain unavailable rather than inferred. Hull and fighter query
results expose their respective entity/deployment record.
Full regression: 694 passing, 1 skipped.

**Six-axis combat doctrine profile (2026-08-26):** Added an advisory,
multi-valued `CombatDoctrineProfile` with battlefield function, engagement
position, tactical style, tempo, commitment, and fleet-dependence axes. It
reuses the existing parseable hull feature vector and observed existing-variant
weapon mix, recording per-axis score/confidence/evidence. The initial profile
does not influence legality or recommendation ranking. It deliberately omits
ramming, reserve/sweeper behavior, runtime system/AI behavior, ammo/rearm
cycles, and flavor-text fleet claims. Hull query output exposes the profile.
Full regression: 696 passing, 1 skipped.

**Documentation pass (2026-08-26):** Added `QUICK_START.md`, `USER_GUIDE.md`,
and `DEVELOPER_GUIDE.md`, grounded in current CLI/API/GUI/config/build code and
tests. The guides label supported, partial, experimental, and unavailable
features rather than promoting roadmap scope to implemented behavior. The
developer guide records the first consistency audit and its verified/unverified
boundary; the one build-workflow mismatch found during that audit was corrected
before handoff.

**Ship-canvas geometry alignment (2026-08-26):** Fixed a generic visual
coordinate mismatch in `TechnicalCanvas`: mount locations are `.ship`
geometry units, but mod sprites may have a different native texture
resolution. Hull pixmaps are now transformed into the declared width/height
space before the existing center-relative, Y-up-to-Y-down slot transform is
applied. Missing declared dimensions retain raw sprite placement rather than
fabricating scale; missing/unloadable sprites retain the geometry-outline
fallback. The change affects only canvas rendering/hit boxes, never fit state
or legality. Added a resolution-mapping regression test. Full regression: 693
passing, 1 skipped.

**Latest local verification:** 2026-08-25 — 674 tests passed, one optional
local canonical benchmark skipped, via
`uv run --no-project --with-editable . python -m unittest discover -s tests -v`.
(Supersedes the 647-test count above; reflects Phase 41 (Static
Control-Suitability Signals, immediately above -- 27 tests added in
`tests/test_control_suitability.py`). Phase 35's GUI modularization above
changed no test count.)

See `docs/ROADMAP.md` for the detailed, traceable record of the 2026-08-22
gap-closing pass referenced in several rows below (Tier numbers refer to
that document).

**Phase numbering note:** the 0-9 phases below follow the original `Forge
formal spec.txt`. Root `ROADMAP.md` (synced from the planning pack, now at
its v0.5 refresh) uses a different, expanded 0-23 numbering that
splits/renames several of these and adds new phases -- Hullmod Effect
Engine, Refit Assistant, civilian classifiers folded into Phase 5, Faction
Capability Analyzer / Faction Knowledge Pack Framework / Gap Recommendation
Engine / Recommendation Explainability, and (new in v0.5) Equipment Access
+ Adaptive Autofit (equipment affinity/availability, `EXACT`/
`STARSECTOR_STYLE`/`ADAPTIVE` retrofit substitution), plus a GUI block
split into 7 phases matching `GUI.md`'s workspace-tab design. Both
numbering schemes describe the same underlying work; treat root
`ROADMAP.md` as authoritative for phase *names* and this file as
authoritative for the original spec's phase *evidence*, and don't assume
phase N here means the same thing as phase N there.

| Formal phase | Status | Current evidence | Material gaps |
|---|---|---|---|
| 0 Foundation | Partial | Package, CLI, config, logging, unit tests, work log, CI (`.github/workflows/tests.yml`, Tier 5); `cli/main.py`'s orchestration is now extracted into an importable service layer (`api.py`) so a future GUI can bind to it directly per `GUI.md`'s Readiness Gate, rather than shelling out to `svg` -- zero CLI-observable behavior change | No packaging/release automation beyond CI's `python -m build` check. |
| 1 Scanner/parser | Partial | Core/enabled-mod scan, CSV, `.ship`, `.wpn`, variant, relaxed JSON, legacy encodings/control characters, source hashes; live scan parses 4,736 hulls (including 306 real `.skin`-derived hulls, e.g. `onslaught_xiv` -- SVG-014) and 431 factions against a real 148-mod install with 5 parser errors, all confirmed genuinely malformed `.skin` source files, not a syntax convention; hull/weapon parsers now also capture flux fields, `fighter_bays`, and built-in-weapon mounts (Tier 2, Tier 1.3, Tier 1.4) | 3 skipped source metadata files remain queued; `data/config/settings.json` is still not scanned as a general data source (its two relevant values were verified and hardcoded into `adapters/vanilla/`, not parsed generically). |
| 2 Registry/cache | Partial | Deterministic indexes, explicit dependency-ID presence audit for string/object metadata declarations, unresolved references, SHA-256 manifest/change detection, and query reports for unambiguous weapons/variants/faction equipment | No SQLite normalized cache, dependency-version compatibility, or load-order resolution (deliberately deferred, ROADMAP.md Tier 5). |
| 3 Validator/analyzer | Partial | Three-state validation, direct hull/weapon/hullmod/fighter reference checks, size, the **full documented mount-type compatibility matrix** (`core/mount_compatibility.py` -- Ballistic/Energy/Missile plus Hybrid/Composite/Synergy/Universal combinations, not just exact-match; SVG-013), OP (including vent/capacitor cost), fighter-bay capacity, built-in-weapon preservation, per-hull-size vent/capacitor maximum, max-2-logistics-hullmods cap. All stress-tested against all 441 real core variants plus multiple random installed mods' variants with zero false positives and zero exceptions; two real false-positive bugs were found and fixed this way (fighter-bay undercounting on multi-bay-per-slot hulls; exact-match-only mount typing, which dropped `MOUNT_TYPE_MISMATCH` false positives from 299 to 4 real variants). CLI validation. | A general pairwise hullmod-incompatibility mechanic may not exist in vanilla at all (ROADMAP.md Tier 1.2); fighter-wing-internal mount semantics (`hull_size: FIGHTER`) are a distinct, still-undocumented area (4 real variants affected). |
| 4 Classifiers | Partial | Transparent hull/weapon/fighter/hullmod tags and role signals, including normalized launch-bay/built-in-wing carrier evidence and non-exclusive hull role-compatibility scores; classification now has a CLI surface across all four entity kinds (`svg query weapons`/`hulls`/`fighters`/`hullmods`); a Manual Override Layer covering weapons *and* hulls (`core/overrides.py`, additive-only, structurally excluded from legality) -- consumed by generation and export too, not just `query`: `svg generate`/`svg export --overrides-dir` affect the `PD_ESCORT` profile's `PD_FIRST` weapon sort, and `svg analyze-variant --overrides-dir` affects a hull's `civilian_role_tags` (and, through it, `compute_derived_civilian_stats`'s civilian-maintenance-penalty notes); new civilian-role evidence tags from the hull CSV's real `hints` column (`classify_civilian_role`, verified against 17 real core civilian hulls); a real faction-ownership equipment-affinity classifier (`analysis/equipment_affinity.py`, `NATIVE`/`COMMON`/`FOREIGN`/`UNALIGNED` from real `known_*` list membership, never from `source_mod_id`) surfaced on all four `query` entity kinds | Faction doctrine is now consumed by scoring (`doctrine_match`, Tier 3.1) but mechanical-synergy classifiers remain incomplete. Override layer still doesn't cover fighters/hullmods/factions (those classifiers expose structural facts, not the "supplement missing evidence" judgment weapons/hulls role tags are for). Civilian classification deliberately stops at evidence tags -- no numeric per-role compatibility scores across the newly-specified 9-role taxonomy (cargo/fuel-ratio thresholds were tried and found unreliable against real data). Equipment affinity doesn't yet produce `APPROVED`/`RESTRICTED`/`UNKNOWN` (needs knowledge-pack or override evidence) and isn't consumed by generation's faction-mode filtering. |
| 5 Generator | Partial | Bounded deterministic weapon-only alternatives, now with a configurable `--search-depth` (baseline plus up to N next-ranked documented weapons per mount, one mount changed at a time -- depth defaults to 1, the original bound, for exact backward compatibility), also selecting up to 2 evidence-bound hullmods (`generation/hullmods.py`, faction/category-preferred, cheapest-first, capped at the real median observed on 324 live vanilla variants), fighter wings up to the hull's real documented bay capacity (`generation/fighters.py`, faction-preferred), and allocating vents/capacitors toward the profile's flux target (`generation/vent_cap.py`); independent validation of every candidate; **seven** explicit role profiles (`LINE_BRAWLER`, `LINE_ARTILLERY`, `FAST_STRIKE`, `TANK`, `PD_ESCORT`, `MISSILE_SUPPORT`, `CARRIER_SUPPORT`), strict faction weapon+hullmod+fighter restriction; PD-vs-linked weapon groups on export; Guided mode exposes an explicit `--flux-mode` choice. Full weapons+hullmods+fighters+vents/caps pipeline, all 7 profiles, stress-tested across all 158 real core combat hulls (1,106 candidates): 157/158 (99.4%) LEGAL for every profile, 0 exceptions; the deeper search separately stress-tested across 60 real hulls at depth 4 (788 candidates): 100% LEGAL, 0 exceptions. Two real generator bugs (spurious `BUILT_IN`-mount weapon assignment SVG-012; exact-match-only mount typing SVG-013) were found and fixed via this stress-testing discipline. | None material -- this phase's remaining gap is upstream data (Tier 1.1/1.2), not generator logic. |
| 6 Scoring | Partial | Legal-only range/OP/role/**flux-sustainability**/**faction-doctrine-match**/**civilian-efficiency**/**survivability** scoring and explanations under `baseline_0.2`; immutable versioned heuristic metadata; `baseline_0.1` output is still reproduced byte-for-byte for backward compatibility; `svg analyze-variant` and `svg generate` both surface `faction_doctrine_match` when a faction resolves; `svg analyze-variant` surfaces derived civilian and defense stats. Civilian efficiency and survivability are effect-based gain-per-OP components, included only when a verified LOGISTICS or DEFENSE hullmod effect supplies a computable ratio; otherwise they remain absent rather than becoming a fabricated zero. | PD, AI, and missile scoring are not implemented. Real coverage of `flux_sustainability` is limited in practice: only ~15% of core weapons have a directly parsed per-second flux rate (SVG-011). Hullmod-effect coverage remains limited to the verified LOGISTICS and DEFENSE entries. |
| 7 Modes | Partial | Beginner/Guided/Advanced deterministic presets, now including a per-mode flux-sustainability target (`SAFE`/`BALANCED`/`AGGRESSIVE`); strict Advanced JSON request for implemented weapon restrictions, now also `scoring_weight_overrides` (root ROADMAP.md Phase 14): rebalances `score_candidate`'s own named component weights, restricted to a fixed allow-list of the 6 already-registered `weight_*` heuristics -- no new or unaudited heuristic can be introduced through it | No interactive guided flow beyond the flux-mode choice, or unsupported-mechanic controls. |
| 8 Export | Partial | Legal-only `.variant` and compatibility mod writer; source-hash/profile/faction/heuristic/timestamp manifest per variant; source-provenance dependency records (explicitly not game load-order claims); `check-export` stale-output audit; fail-closed collision protection; live export smoke test; `svg export --overrides-dir` now applies the weapons Manual Override Layer, matching `svg generate`; the full local suite verifies the source-provenance extension. | No game-load verification. |
| 9 Tuning/regression | Partial | Golden regression test (now verified to hold unchanged under `baseline_0.1` after the Tier 2/3 scoring rework) and scan issue queue; a canonical benchmark suite now exists in three layers -- 5 synthetic archetype hulls with an always-run portable test suite, plus 5 real named canonical hulls (Lasher/Hammerhead/Dominator/Heron/Onslaught) checked locally via `tools/build_local_benchmarks.py` and `tests/test_canonical_local.py`, with no real Starsector data committed to the repo. Hash-bound reviewer labels can now be evaluated directly against a read-only current scan with `tools/evaluate_local_calibration.py`; it cannot silently select duplicated cross-mod IDs or adjust weights. | Deliberate heuristic calibration still requires reviewer labels and a reviewed before/after report; `doctrine_match`'s weighting remains explicitly first-pass until that ground truth exists. |

## Version 0.1 completion gate

The Definition of Done in the formal specification is **not satisfied**.
Passing tests prove only the listed current behavior. The remaining work above,
plus all unchecked Definition-of-Done items, must be completed and verified
before this document can be marked complete. The GUI is implemented as an
optional backend-bound desktop workflow; visual polish and richer interactive
controls remain outside this formal gate.
