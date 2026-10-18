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
| 56 — Campaign-save parser preparation | Complete with limitations | S0/S1: explicit read-only XML inspection for game 0.98a-RC8 / save 0.6, a separate fact schema, SHA-256 evidence and bounded refusal tests. `docs/CAMPAIGN_SAVE_FORMAT.md` closes the six inputs for this inspection scope only; explicit resource interpretation is separately qualified by S2. |
| 57 — Save Workshop (minor edits to a save copy) | S0–S3 implemented; over-capacity writes refused; GUI write controls and release readiness pending | Owner-approved design 2026-10-06 in `docs/SAVE_WORKSHOP_DESIGN.md`: tier 1 edits credits, cargo commodities (supplies, fuel, crew, marines, machinery) and story points on a copy written below the configured output directory. Read-only resource inspection and tier-1 edit planning are implemented from qualified static storage evidence. Owner decision 2026-10-06: S3 writes verified copies for changes within the saved capacity only; over-capacity changes are refused and consequences remain `UNKNOWN`. The original save is never modified. Implementation plan, module layout, GUI design and slices S0-S6: `docs/SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md`. |

## Save Workshop checkpoint — 2026-10-06

S0/S1 now qualify a single observed save profile using 81 owner-supplied game and isolated-rig campaigns (81 READABLE, 81 hash-identical originals); synthetic tests cover unsafe inputs, limits, source changes and non-mutation. The independently supplied AC8 research has a different format and contributes verification practices only. S2 is implemented: referenced player cargo/credits and character story points, exact byte spans, float32/int32 checks, installed commodity membership, explicit capacity-uncertainty planning opt-in and `save plan`. Static alias/type evidence is documented in `docs/CAMPAIGN_SAVE_RESOURCES.md`. S3 remains blocked by the additional write gate requiring controlled capacity evidence. S4 has an independent read-only preview: an opt-in top-level Save Workshop tab, editable resource table, backend plan checks, pure presentation and retained worker. Save writing and its verification UI remain disabled and unimplemented. S5 requires controlled runtime capacity observations; effects remain UNKNOWN. Edit plans write nothing. Validation (before S3): 822 unittest tests successful (two skipped), 81/81 resource inspections READABLE with credits/story points resolved, exact spans verified and unchanged independent hashes; clean diff checks. Ruff is unavailable. Detailed limits are recorded in `docs/CAMPAIGN_SAVE_FORMAT.md` and `docs/CAMPAIGN_SAVE_RESOURCES.md`.

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

**Implemented in source (2026-10-06):** `run_save_inspect` and `voidsmith save inspect SAVE_DIR` validate bounded XML and read direct descriptor facts for one qualified version. Default inspection reads descriptor/XML facts only; explicit `--resources` resolves qualified resources, and `save plan` validates requested numeric changes without writing files. Existing packaged binaries have not been rebuilt. See `docs/CAMPAIGN_SAVE_FORMAT.md` and `docs/CAMPAIGN_SAVE_RESOURCES.md`.

**Implemented (S3, 2026-10-06):** `voidsmith save write` writes one verified new copy below the output directory when every change is ACCEPTED within the saved capacity; `campaign/verify.py` re-reads it independently; failures remove the copy; the 847-test suite passes (three skipped); ruff is clean on the new files. **Not implemented:** over-capacity writing, GUI write controls, game-load acceptance of an edited copy, and release readiness. Source builds have a default-off Save Workshop read-only preview under Settings / Export; no write action is enabled. The normalized hull schema currently has no deployment-point
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

## Sister repository interoperability (proposed 2026-09-27)

Design and acceptance gates: [docs/SISTER_REPO_INTEROPERABILITY_DESIGN.md](docs/SISTER_REPO_INTEROPERABILITY_DESIGN.md).

1. [ ] Extend existing release verification to trace exact source, build inputs, archive, native acceptance, and separately observed published asset, with per-gate evidence states. Adapt BridgeForge's evidence contract; keep VoidSmith's own implementation.
2. [ ] Optionally ingest SPW's versioned mod identity inventory as provenance context. Match by unambiguous ID and hash, keep native scanning authoritative, and never infer fit legality or recommendation quality from inventory alone.

**Implementation checkpoint 2026-09-27:** Portable builders now emit hash-bound `*.release-chain.json` sidecars, which the release workflow uploads beside archives and checksums. `tools/verify_portable_release.py` accepts optional release-chain evidence and a separately supplied asset; `tools/review_spw_inventory.py` checks SPW identity evidence against selected local metadata/JAR hashes. `api.run_scan(..., spw_inventory=PATH)` adds that context to the ordinary scan report without changing registry or fit results. Synthetic tests cover the parsers, and a direct SPW-export-to-VoidSmith synthetic round trip returned `MATCH` then `UNKNOWN` after metadata changed. A real-install round trip and independently verified remote publication remain open; publication authenticity is still `UNKNOWN` from local bytes alone.

## Proposed ideas (2026-10-06, owner asked for per-project ideas; proposed, not approved)

1. [ ] **Save Workshop (phase 57).** Build slices S0-S6 from `docs/SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md`, starting with the
   format description (S0) and a read-only inspect (S1). Benefit: the first-ever way for players to top up supplies, fuel, crew
   or credits in a safe copy without Console Commands or an in-game mod.
2. [ ] **Fleet logistics summary (read-only).** From hull data, show a fleet's cargo, fuel and crew capacity and its supplies
   per month. Benefit: it is the missing context for the capacity overage question, it cross-checks the capacity figures the
   Workshop reads from a save, and it needs no save access.
3. [ ] **Check a revived mod's shipped variants.** A report that validates every variant a mod ships against hull slots,
   weapons and hullmods. BridgeForge finds a variant that names a missing weapon (a fatal at New Game); VoidSmith has the full
   slot legality. Benefit: catches fit errors before a live run, using the existing validator unchanged.
4. [ ] **Evidence record for edits.** A dated, per-fact record (method, game version, result) for anything the Workshop proves,
   in the style of BridgeForge's `RC8_BEHAVIOUR.md`. Benefit: keeps unknowns, such as overage effects, honest and citable.
5. [x] **GUI contract update.** Add the Save Workshop workspace rules to `GUI.md` when S4 starts (opt-in flag, safety banner,
   refuse and opt-in paths). Benefit: keeps the GUI contract and the backend gate in step.

## Lessons carried over from BridgeForge's hardening (item 70) and regression pass (2026-10-12; proposed, not approved)

Source: BridgeForge `ROADMAP.md` item 70, `docs/HARDENING_PLAN.md`, `docs/RC8_BEHAVIOUR.md` (RC8-30 to RC8-33). Each line says what it would change here and what it buys; none is started.

- **Atomic writes and guarded deletes.** Write through a temp file and `os.replace`; delete a tree only inside an allowed root and never through a junction (BridgeForge `safeio.py`, with a ratchet test whose baseline may only shrink). Benefit: an interrupted write or a wrong path cannot leave a half-written or vanished file.
- **Bounded reads of untrusted archives.** Cap a zip or jar entry (200 MB; class files 32 MB) before reading it (`zipsafe.read_limited`); a hostile or corrupt archive then fails that entry instead of exhausting memory.
- **Parse structured files with a real (lenient) parser, never a regex for the first field.** BridgeForge's master log took the first `"name"` and `"version"` in each `mod_info.json` and listed 17 mods as "LazyLib" with LazyLib's version, because those files list dependencies first. Benefit: wrong labels and versions stop appearing in reports.
- **Guard the contract, not just the code.** A hash of every command's `--help` (a golden test) let agents split a 4,100-line `cli.py` and an 8,800-line `scanner.py` with the interface unchanged; a known-failure file with an expiry keeps an environmental failure from hiding new ones; baselines of accepted findings expire when the mod version changes.
- **Check an agent's branch before merging it** (`agent-diff-check`: files deleted or cut by more than a fifth) and rerun the whole suite on the merged tree; do not edit tracked files while the suite runs (its hermeticity check reports the checkout as changed).
- **Line endings and backups.** LF everywhere (`.gitattributes`; batch files CRLF). An append-only snapshot of the irreplaceable state is taken after each major new revision, not on a weekly clock (owner rule 2026-10-12).
- **Say PREDICTED or OBSERVED.** BridgeForge keeps a prediction ledger: of two forecasts about a mod pair, one held live and one was refuted. Record the method, date and run id with each fact.
- **Capacity-overage evidence run (BridgeForge item 57) is being done** for Save Workshop S5: fleet speed and daily supplies at, below and above capacity for cargo, fuel and crew on three fleets, plus whether a save's cargo container stores or derives its capacity figures. S5 should wait for those dated `RC8_BEHAVIOUR.md` rows and cite their ids; until then overage stays "unknown" in the Workshop.
- **A missing weapon in a variant is fatal at New Game and a missing hull mod is dropped silently** (RC8, live 2026-09-27); a mission naming a missing variant is fatal when that mission starts (found 2026-10-12 in three archived mods). Benefit: the variant-fit validator idea can rank these correctly.
- **GUI contract by hash.** Pin the Save Workshop workspace rules and flags the way BridgeForge pins `--help` (a golden hash per command); a rule change then shows up as a reviewed diff.
- **Evidence record for edits** (idea 4 below) can reuse BridgeForge's row format: id, fact, evidence with date, and what relies on it.
- **Update 2026-10-12: the capacity-overage evidence (BridgeForge item 57) is in.** Over capacity costs 0.1 supplies per day per unit for cargo, fuel and personnel each (capped at 50 per resource, costs add) and slows the fleet to max(1, round(base burn x (2 - r))) for the worst resource's ratio r (BridgeForge `RC8_BEHAVIOUR.md` RC8-34 and RC8-35); a save's capacity figures (`mC`, `mF`, `mP`, `sU` on the player's `<cargo>`) are written from the fleet at save time and a space used above capacity is stored as is (RC8-36). S5 can cite those rows. Still unknown: whether loading recomputes an edited `mC`; one load test would settle it before the Workshop edits capacity fields.

## Automation plan (2026-10-14; plan only, not started)

Owner request 2026-10-14: further automation, fixes, checks and less hand work, written so any AI can implement it. Spec:
`docs/AUTOMATION_PLAN.md`; the repository contract (no AI dependency, no invented behaviour, heuristics never auto-tuned, IP
boundary) binds every item. Phases: V0 boundary and hygiene (real-entity calibration packs are tracked in git against `AGENTS.md`;
owner decision first; atomic writes, bounded archive import, full mypy and ruff in CI, golden `--help`); V1 checks that run
themselves (`validate-all` over every shipped variant, mod acceptance with a baseline, parse failures with locations, stale enabled
mods); V2 calibration review a person can finish (auto-resolve names to ids, per-row pre-checks, batch approve by a named reviewer,
heuristic-set proposal report); V3 Save Workshop S4/S5 from BridgeForge's RC8-34..36 rows; V4 a `check-mod` verdict BridgeForge can
read and the SPW round trip. Owner decisions 2026-10-14 ('follow your recommendations') are recorded in the plan. **V0.1 done 2026-10-14:** six real-entity calibration files and `docs/Chatgpt mod curated guide` untracked (kept locally under `generated/calibration-sources/moved-from-git-2026-10-14/`), no history rewrite; guard `tests/test_distribution_boundary.py`; a non-working UTF-16 line in `.gitignore` rewritten in ASCII. Full suite: 849 tests, OK (skipped=3). `AGENTS.md` rewritten as version 0.7 (consolidated, Save Workshop clause updated to RC8-34..36, hygiene, evidence, direction and sister-project sections).

**V0.2-V1.4 built 2026-10-18 (branch `automation-plan`, not merged).** V0.2 `core/safeio.py` (atomic writes, `safe_rmtree`/`safe_unlink` that refuse roots, outside paths, links and junctions); every bare `write_text`/`write_bytes` in `src/` converted, `tests/test_safeio_ratchet.py` against an empty, shrink-only `tests/safeio_baseline.json`. V0.3 `core/mod_import.py` refuses an entry over 200 MB, a total over 2 GB, a compression ratio over 100 (entries over 1 MB), symlink entries and link or junction targets, before extracting, and counts real bytes while extracting; crafted-zip tests. V0.4 CI runs ruff `E9,F,B` (B008 off) over `src tests tools` and full `mypy src` (0 errors; the one known error was a wrong annotation in `calibration_workspace.py`), `build_parser()` plus `tests/test_cli_golden.py` (hash of each command's grammar, structure-based because argparse renders differently across Python versions), `.gitattributes`. V1.1 `voidsmith validate-all [--source all|core|mod:<id>]`. V1.2 `voidsmith acceptance --baseline FILE [--write-baseline]` with chunked progress lines and a resumable checkpoint. V1.3 `analysis/parse_diagnostics.py`: `parse_failures` in the scan report and CLI. V1.4 `analysis/stale_enabled_mods.py`: `stale_enabled_mods` in the scan report and CLI. Limits: the GUI diagnostics view does not show parse failures or stale mods yet; the two V1 sweeps are unit-tested on synthetic data only. Local steps on the real install: run `validate-all` and compare with the SVG-012/013 441-variant total (V1.1 done condition); run `acceptance --write-baseline` once to record the first baseline, and `scan` to see the real SVG-004 and SVG-014/017 lines.

