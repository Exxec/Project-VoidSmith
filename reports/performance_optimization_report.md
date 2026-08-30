# Performance optimization report

## Scope

This pass optimizes VoidSmith startup and the initial lightweight scan without
changing game/mod parsing, analysis semantics, legality, recommendation
ranking, or source-file safety. Source installations remain read-only.

## Implemented

- `Scanner` now emits staged aggregate progress: `DISCOVERING`, `PARSING`,
  `RESOLVING_REFERENCES`, and `COMPLETE`.
- `ScanMetrics` records discovery, parsing, resolution, and total durations;
  scanned-source count; and relevant files/bytes hashed. The metrics appear in
  compact scan reports and the GUI's latest-scan summary.
- The GUI scan worker forwards progress snapshots from its existing worker
  thread, so the Qt UI remains responsive and shows source/entity progress.
- The large Data / Analysis view is deferred until that workspace is opened
  and uses compact `QAbstractTableModel`/`QTableView` storage rather than one
  widget item per cell. Hull browsing, generation, Retrofit, Faction, and
  normalized backend indexes are available immediately after a scan.
- Enabled-mod configuration is read once per scan rather than once for scan
  setup and again during source discovery.
- Weapon `.wpn` enrichment now touches only weapons parsed for the current
  source. The prior pass walked every already-parsed weapon for every mod,
  which grows quadratically with installed-mod count while producing the same
  normalized records.
- `tools/profile_scan.py` provides a repeatable read-only local benchmark. It
  writes aggregate timing/count telemetry only beneath a user-selected output
  directory.
- The existing scan-time report-set cache now declares and fingerprints all
  report inputs it actually consumes: normalized entity hashes, heuristic/API
  registry versions, `.ship`, `.wpn`, `.skin`, `mod_info.json`, and local Java
  source. Missing entity hashes or a prior incomplete manifest disable reuse.
- Hull mechanical/build/capability reports now have a narrower independent
  fingerprint: the hull, its applicable existing variants, and only the
  resolved weapons/hullmods those variants consume. An unrelated hull change
  therefore reuses the unaffected hull profile without widening semantics.
- Faction capability and doctrine reports likewise reuse independently from a
  source-hash-bound context of their faction, resolved known hulls, relevant
  variants, and referenced equipment. Aggregated equipment documents still
  recompute as one unit because their current output schema is global.
- Static hullmod analysis now persists source-mod fragments and aggregates them
  into the existing public document. Each fragment fingerprints its hullmod
  rows, local Java sources, heuristic set, and API-effect registry version.
- Direct weapon and parsed-hullmod classification reports use the same per-mod
  fragment approach. The established aggregate JSON documents are still written
  for compatibility, but only changed source-mod fragments are reclassified.
- Hull browser text filtering is debounced, and generic background-analysis
  results are request-token gated so stale work cannot replace a newer UI
  request without attempting unsafe forced cancellation.
- Portable packaging now relies on PyInstaller's normal dependency analysis
  cache for ordinary locked builds, with explicit `-Clean`/`-FreshAnalysis`
  escapes for reproducible fresh analysis. It no longer collects unrelated
  PySide6 optional modules; the PyInstaller PySide6 hooks deploy only imported
  Qt modules and their required runtime plugins.
- Normal application scans persist an output-local, versioned binary normalized
  snapshot per source. Every reuse is guarded by a complete deterministic
  content hash over each parsed CSV/JSON/ship/skin/weapon-spec input; an
  unreadable, incomplete, changed, or invalid snapshot is ignored and that
  source reparses. The cache never writes into a Starsector/mod directory.
- The scanner supports bounded (maximum eight) threaded per-source parsing,
  with isolated fragments, stable discovery-order merges, and serial
  cross-source skin resolution. The measured real-install default remains one
  worker: 2/8 workers did not outperform serial parsing on its disk-bound
  source tree. `tools/profile_scan.py --workers N` remains the safe way to
  measure a different local storage/CPU profile before enabling parallelism.

## Verification

The portable synthetic scanner fixture verifies the progress sequence,
aggregate metrics, existing scan results, and compact-report behavior. Full
project and GUI/release validation remain required after this pass.

## Measured local installation

On the local enabled-loadout installation (119 scanned sources; 12,637 relevant
files; 22.6 MB hashed), the cold snapshot-populating scan took 19.76 seconds.
The immediate hash-verified binary-snapshot rescan took 6.67 seconds, a 66%
reduction while still hashing every consumed input file. Cold serial parsing
measured 18.25 seconds; explicit 2-worker and 8-worker runs measured 18.57
and 19.76 seconds respectively. The default is therefore serial on this
disk-bound profile; parallel workers are supported only as a measured override.

## Intentionally deferred

- Candidate/recommendation result reuse remains disabled until each consumer
  supplies a complete dependency fingerprint and a versioned typed-result
  serialization contract. Missing context fails closed to recomputation.
- Process-based parallelism remains deferred. Python worker processes would
  require serializing the complete registry and reconciling cross-process
  result/error ordering; bounded threads already improve independent local
  file parsing without weakening deterministic behavior.
- C/C++ compiler caching (`ccache`) and header refactoring do not apply: this
  repository contains Python and Qt bindings, not native compilation units.
  The equivalent build-time reuse is PyInstaller analysis caching, kept
  deterministic by the pinned offline dependency graph.
- Deep static Java/hullmod analysis, derived profiles, and expensive candidate
  generation are not performed by `run_scan`; they remain demand-driven rather
  than delaying GUI availability.
- GUI list virtualization/lazy secondary population is a future measured UI
  optimization. It should move to Qt model/view only if a real installation
  demonstrates a startup or interaction bottleneck.

## Local measurement

```powershell
.\.venv\Scripts\python.exe tools\profile_scan.py "C:\Path\To\Starsector" --output-dir .\generated\performance --runs 3
```

Use `--cold` for a first-scan baseline or `--workers N` to compare bounded
parallel parsing against serial parsing on the same local installation.

The generated report deliberately contains counts and timing only, not shipped
Starsector/mod content.
