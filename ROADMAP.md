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
| 57 — Save Workshop (minor edits to a save copy) | S0–S4 implemented (the GUI "Write edited copy" sits behind a default-off setting); over-capacity writes refused; release readiness (S6) and one live capacity check pending | Owner-approved design 2026-10-06 in `docs/SAVE_WORKSHOP_DESIGN.md`: tier 1 edits credits, cargo commodities (supplies, fuel, crew, marines, machinery) and story points on a copy written below the configured output directory. Read-only resource inspection and tier-1 edit planning are implemented from qualified static storage evidence. Owner decision 2026-10-06: S3 writes verified copies for changes within the saved capacity only; over-capacity changes are refused and consequences remain `UNKNOWN`. The original save is never modified. Implementation plan, module layout, GUI design and slices S0-S6: `docs/SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md`. |

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

**Implemented (S3, 2026-10-06):** `voidsmith save write` writes one verified new copy below the output directory when every change is ACCEPTED within the saved capacity; `campaign/verify.py` re-reads it independently; failures remove the copy; the 847-test suite passes (three skipped); ruff is clean on the new files. **Not implemented:** over-capacity writing, game-load acceptance of an edited copy, and release readiness. Source builds have a default-off Save Workshop under Settings / Export; since 2026-10-18 its "Write edited copy" button (S4) writes and re-verifies a copy for a fully ACCEPTED plan. The normalized hull schema currently has no deployment-point
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

## Automation plan (2026-10-14; V0 to V4 built 2026-10-18, merged to master)

Owner request 2026-10-14: further automation, fixes, checks and less hand work, written so any AI can implement it. Spec:
`docs/AUTOMATION_PLAN.md`; the repository contract (no AI dependency, no invented behaviour, heuristics never auto-tuned, IP
boundary) binds every item. Phases: V0 boundary and hygiene (real-entity calibration packs are tracked in git against `AGENTS.md`;
owner decision first; atomic writes, bounded archive import, full mypy and ruff in CI, golden `--help`); V1 checks that run
themselves (`validate-all` over every shipped variant, mod acceptance with a baseline, parse failures with locations, stale enabled
mods); V2 calibration review a person can finish (auto-resolve names to ids, per-row pre-checks, batch approve by a named reviewer,
heuristic-set proposal report); V3 Save Workshop S4/S5 from BridgeForge's RC8-34..36 rows; V4 a `check-mod` verdict BridgeForge can
read and the SPW round trip. Owner decisions 2026-10-14 ('follow your recommendations') are recorded in the plan. **V0.1 done 2026-10-14:** six real-entity calibration files and `docs/Chatgpt mod curated guide` untracked (kept locally under `generated/calibration-sources/moved-from-git-2026-10-14/`), no history rewrite; guard `tests/test_distribution_boundary.py`; a non-working UTF-16 line in `.gitignore` rewritten in ASCII. Full suite: 849 tests, OK (skipped=3). `AGENTS.md` rewritten as version 0.7 (consolidated, Save Workshop clause updated to RC8-34..36, hygiene, evidence, direction and sister-project sections).

**V0.2-V1.4 built 2026-10-18 (branch `automation-plan`, since merged to master).** V0.2 `core/safeio.py` (atomic writes, `safe_rmtree`/`safe_unlink` that refuse roots, outside paths, links and junctions); every bare `write_text`/`write_bytes` in `src/` converted, `tests/test_safeio_ratchet.py` against an empty, shrink-only `tests/safeio_baseline.json`. V0.3 `core/mod_import.py` refuses an entry over 200 MB, a total over 2 GB, a compression ratio over 100 (entries over 1 MB), symlink entries and link or junction targets, before extracting, and counts real bytes while extracting; crafted-zip tests. V0.4 CI runs ruff `E9,F,B` (B008 off) over `src tests tools` and full `mypy src` (0 errors; the one known error was a wrong annotation in `calibration_workspace.py`), `build_parser()` plus `tests/test_cli_golden.py` (hash of each command's grammar, structure-based because argparse renders differently across Python versions), `.gitattributes`. V1.1 `voidsmith validate-all [--source all|core|mod:<id>]`. V1.2 `voidsmith acceptance --baseline FILE [--write-baseline]` with chunked progress lines and a resumable checkpoint. V1.3 `analysis/parse_diagnostics.py`: `parse_failures` in the scan report and CLI. V1.4 `analysis/stale_enabled_mods.py`: `stale_enabled_mods` in the scan report and CLI. Limits: the two V1 sweeps are unit-tested on synthetic data only. Local steps on the real install: run `validate-all` and compare with the SVG-012/013 441-variant total (V1.1 done condition); run `acceptance --write-baseline` once to record the first baseline, and `scan` to see the real SVG-004 and SVG-014/017 lines.

**V1 GUI, V2, V3, V4 built 2026-10-18 (same branch, since merged to master).** V1.3/V1.4 GUI: `api.scan_diagnostic_lines` feeds a read-only Data / Analysis > Diagnostics tab. V2.1-V2.4 `voidsmith calibration resolve|approve|propose` (`analysis/calibration_review.py`, `calibration_propose.py`): names resolved by EXACT_NAME, NORMALISED_NAME, QUALIFIER_STRIPPED; pre-check columns `equipment_ok`, `legality`, `ready_for_review`; approval only for a named reviewer and only ready rows (logged in an `.approvals.jsonl`); `propose` measures registered sets against APPROVED rows and writes an unregistered candidate stub (an unchanged copy of the best set's values), never registering or tuning; every sheet path is checked to be under `generated/`. Limits: the equipment pre-check matches loadout text item by item against scanned weapon, hullmod and fighter names, and free text fails it (so the row is not ready); legality runs only for rows that name an existing variant (`variant_id` column), because mapping loadout text to mounts would invent a loadout. V3.1/V3.4 Save Workshop docs cite RC8-34..36; over-capacity writes stay refused. V3.2 `overage_preview` in `save plan` and the GUI plan view (0.1 supplies per day per unit over, cap 50 per resource; speed shown as the worst ratio and the burn-level formula, because the base burn is not read from a save). V3.3 "Write edited copy" is enabled behind the default-off Workshop setting for a fully ACCEPTED current plan, then `api.run_save_verify_copy` re-verifies. V4.1 `voidsmith check-mod PATH` (PASS/REVIEW/FAIL JSON, exit 0/1/2). V4.2 synthetic SPW round trip test.

Local steps that need the real install or the game: run `scan` and read the Diagnostics tab and CLI lines (SVG-004, SVG-014, SVG-017); `validate-all` and compare with the SVG-012/013 441-variant total; `acceptance --write-baseline` once; `calibration resolve` on the real review sheets (the 726 rows) and read how many are ready, then a person runs `calibration approve`; `calibration propose` after rows are approved; one write of a copy from the GUI and a load of it in the game; the one remaining capacity check (does a load recompute an edited `mC`/`mF`/`mP`) in BridgeForge's capacity rig; `check-mod` on a BridgeForge `working/` copy; the SPW inventory round trip on the real install. S6 (shipping the flag on) stays the owner's decision.


## Execution checkpoint — 2026-10-19

Owner request: check the roadmap and implement its phases as a goal. V0–V4 are already built; this pass executes available near-term qualification and adds the proposed Python 3.13 CI matrix entry. It does not authorize human calibration approval, a default-on Workshop, or publication.

- **Near-term item 1: local checks run, with limits.** Read-only scan and validation completed against the currently enabled installation. All discovered mod metadata was readable on the final run. The variant count differs from the historical 441 baseline because the current installation is a different snapshot; no equivalence is claimed. Scan/validation reported findings, so their nonzero exits are retained as diagnostic outcomes rather than called clean passes. Acceptance was run without creating or approving a baseline; the first `--write-baseline` remains a person-run step.
- **Calibration resolution run.** The three ship-review sheets total 726 rows. New resolved copies are under the ignored local output directory; no input sheet was changed and no row was approved. The separate source-catalog CSV is not a ship-review sheet and was correctly refused by the resolver. Pre-check readiness is not approval or live evidence.
- **Near-term item 5: implemented.** The Ubuntu test/build matrix now includes Python 3.13 alongside 3.11 and 3.12. Hosted 3.13 execution is NOT_RUN until CI runs; the local suite ran under the existing Python 3.14.7 environment.
- **Validation:** 943 tests passed (3 skipped); Ruff passed; full-source mypy passed (119 files). Detailed real-entity results and logs stay only under `generated/roadmap-2026-10-19/`.
- **Remaining gates:** person-run acceptance baseline and calibration approval; user-selected real SPW export; bounded GUI write/load acceptance and BridgeForge capacity observation; phase 54 semantics and S6/release decisions. These are not completed by static tests. Broader long-term recommendations need their own bounded design and evidence inputs.
- **SPW inventory round trip on the real install (2026-10-20, OBSERVED).** `spw inventory` on `C:\Program Files (x86)\Fractal Softworks\Starsector` (160 mods) fed to `tools/review_spw_inventory.py`: 151 MATCH, 9 UNKNOWN (missing, changed or ambiguous metadata: CFT x2, DDSCache and others), 0 mismatches. Local output `generated/spw-review-2026-10-20/review.json`. Package version aligned to 0.2.0 (PR #1). The acceptance baseline and calibration approvals remain person-run.
- **First acceptance baseline (2026-10-20, owner-requested run).** The owner's attempt from the portable `VoidSmith.exe` did nothing: that build is from 2026-08-28 and predates the `acceptance` command, so the baseline was written from source (`voidsmith acceptance --baseline generated/reports/acceptance_baseline.json --write-baseline --starsector-path "C:\Program Files (x86)\Fractal Softworks\Starsector" --output-dir generated`). 155 enabled mods: 152 PASS, 2 PARTIAL (Nightcross, Nexerelin: adapter-modeled and unknown hullmod effects, duplicate entity ids), 1 FAIL (`second_in_command`: enabled but not installed). Follow-ups: (1) 27 mods record their version as a raw JSON string because `mod_info.json` versions given as `{"major":..}` objects are not normalized; normalize them (the baseline compares strings, so a fix changes those rows once). (2) The portable build is seven weeks behind source; rebuild it or say in the Quick Start that `acceptance`, `validate-all` and `check-mod` need a source build or a newer portable release.
- **Proposed 2026-10-20 (hand-work reduction).** (1) Portable parity check: the release workflow runs the built `VoidSmith.exe --version` and `--help` and fails when its version or command list differs from the source CLI golden, so a stale portable cannot be mistaken for the current tool. (2) `acceptance` reads `enabled_mods.json` drift before judging: an enabled-but-missing mod (`second_in_command` today) is reported once as a stale entry with the exact line to remove, instead of only as a FAIL row. (3) Calibration triage: `calibration resolve` groups the 726 rows by the reason they are not ready (free-text loadout, unknown variant, legality), so a person fixes a group at a time rather than row by row.
- **Calibration triage built 2026-10-21 (item 3).** `voidsmith calibration triage SHEET... [--json] [--write DIR]` groups a resolved sheet's not-ready rows by reason code (unresolved or ambiguous name, unmatched loadout token, legality, no such variant) with a count, examples and one fix each, and ready rows by hull and faction with a person-run `calibration approve --rows ...` line. `calibration alias add SHEET_DIR TOKEN ID [--equipment]` writes a sidecar `calibration_aliases.json` beside the raw sheets; the next `resolve` applies it (resolve rule ALIAS). Input sheets are never edited. Synthetic tests only; real run on the three 726-row resolved sheets (385 + 61 + 280 rows, 249 ready, 477 not ready) was read-only. Nothing was approved.

## Recommendations (2026-10-18; proposed, not approved)

Written after the automation plan (V0-V4) merged and CI went green on Python 3.11, 3.12 and the Windows smoke job. The owner
asked for recommendations and long-term recommendations. None is scheduled until the owner picks it; the contract in
`AGENTS.md` (no AI dependency, no invented behaviour, heuristics never auto-tuned, IP boundary) binds all of them.

### Near term: real-install evidence for what was just built

1. **Run the real-install checks once and record them** (the list in the Automation plan section above): `validate-all`
   against the SVG-012/013 total, the first `acceptance --write-baseline`, `scan` for SVG-004/014/017, and `calibration
   resolve` over the 726 review rows. Benefit: every new command gets its first real number, and the ready-for-review count
   tells the owner how much calibration work is actually left.
2. **Close the last capacity unknown** with BridgeForge's capacity rig: does loading a save recompute an edited
   `mC`/`mF`/`mP`? It is the only fact standing between the Save Workshop and a decision on over-capacity edits.
3. **Write one copy from the GUI and load it in the game**, then record it as the first Save Workshop live acceptance. S6
   (shipping the setting on by default) is the owner's call after that run, not before.
   **2026-10-20 (item 79.3):** one rig session closes both gates 2 and 3. Write the copy with the Workshop (it now also writes `voidsmith_expected_fingerprint.json` beside the copy: expected `cargo` text and FNV-1a digest, the sections the edit changes and those it must leave unchanged), load it in the game with the BridgeForge probe's save-reload stage, then run `voidsmith save verify-ingame COPY_DIR PROBE_LOG` (exit 0 match, 1 review, 2 fail). The load is the GUI-copy acceptance; the per-section report says whether the game kept or recomputed the cargo figures. `player` and the other sections are not reproducible from the Workshop's readers and are checked only as unchanged against the probe's stored digest. The Workshop does not edit `mC`/`mF`/`mP`, so the capacity question itself is answered only for a copy whose capacity was edited by hand.
4. **Release decision.** Decided 2026-10-21: VoidSmith stays on the 0.x line. `v0.2.0` is tagged from master and published by the
   tag workflow (Windows and Linux portable archives); it supersedes `v0.1.0RC*` and the stray `v1.0.0rc2`.
5. **CI on Python 3.13** as well: implemented 2026-10-19, then superseded: the project now requires Python 3.15 (`requires-python >=3.15`) and CI runs 3.15 only. The 3.11 golden failure showed version differences surface only in CI.

### Long term: what VoidSmith should become

1. **The fitting and fleet tool that understands revived mods.** BridgeForge revives a mod; `check-mod` already gives it a
   read-only verdict. Extend that into a standing link: every BridgeForge archive gets a VoidSmith verdict (legal variants,
   missing weapons, stale references) before release, and VoidSmith's registry reads revived mods as first-class sources.
2. **Calibration as a curated, local evidence base.** Keep calibration data local under `generated/`, but make it durable:
   approved rows versioned with the game and mod versions they were judged on, expiring when either changes (the same idea
   as BridgeForge's version-stamped baselines). Heuristic sets stay human-released, with the `propose` report as their
   measured justification.
3. **Save Workshop beyond tier 1, one evidenced rule at a time.** Fleet repair state, then blueprints, then relations, each
   only after a live run proves how the game reads the edited field. The capacity work is the pattern to repeat.
4. **Scripted-effect coverage through adapters.** The largest quality gap is still UNKNOWN_SCRIPTED_EFFECT hull mods and
   flux coverage (SVG-011). Grow adapters per widely used library or mod family, with evidence for each modelled effect,
   rather than special cases in the engine.
5. **Stay offline and deterministic.** The value of VoidSmith is that its answers are explainable and repeatable; keep any
   future assistance optional and outside the engine, as the contract says.
