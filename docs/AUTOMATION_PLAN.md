# VoidSmith automation plan: fewer hand-run checks and hand-filled sheets

Owner request 2026-10-14 (made in a BridgeForge session): a roadmap plan for further automation, fixes, checks and anything that
reduces hand work, written so any AI can implement it. **Status 2026-10-18: V0.1 to V4.2 are built and merged to master (see ROADMAP.md for the limits and the local steps that need the real install). Each item below carries a `Status` line saying what exists; sections 1 and 2's evidence is the 2026-10-14 starting point, not the current state.** Each item names the modules to touch, the behaviour,
the tests and when it is done. An implementer needs this file, `AGENTS.md` (and its reading order), `ROADMAP.md` and the code.

The repository contract is unchanged and binds every item: no AI/LLM dependency; offline, deterministic, explainable; unknown
mechanics stay `UNKNOWN`/`NOT_DETERMINABLE`; heuristics live in the versioned registry and are **never auto-tuned** (a tool may
measure and propose a new set; a person releases it); no game or mod data in the distributable repository.

## 1. Evidence (measured 2026-10-14 on `1f5d803`, working tree clean)

| Fact | Value |
|---|---|
| Version | `voidsmith` 1.0.0, Python 3.11+, GPL-3.0-only |
| Tests | 851 `def test_` in 85 files (last recorded run 847 passed, 3 skipped) |
| CI | `tests.yml`: Ubuntu 3.11/3.12, Windows + GUI smoke; ruff `--select E9` only; mypy on two files only |
| Open roadmap | phase 54 decision-gated; phase 57 Save Workshop S4 (GUI write), S5 (overage rule), S6 (release) pending; sister-repo items 1-2; 2026-10-06 proposals 2-4; BridgeForge lessons (none started) |
| Open bugs | SVG-004 (three enabled-but-missing mods), SVG-011 (flux coverage about 15%), SVG-023 (`player_suitability` dead ternary) |

Hand work and gaps, with locations (`src/starsector_variant_generator/` abbreviated `svg/`):

- **IP boundary breach (needs the owner first).** `AGENTS.md` "Distribution and IP Boundary" (line 49) forbids mod-specific
  knowledge packs and lists naming real entities in the repository, and `docs/CALIBRATION_IMPORT_NOTES.md` (line 21) says they must
  stay under the gitignored `generated/`. Yet git tracks `knowledge_packs/duckie0012_ship_tierlist_v098_calibration.provisional.json`,
  `..._review.csv`, `grievous69_reddit_098a_calibration_source_pack.provisional.json`, `grievous69_reddit_098a_source_review.csv` and
  the two `*_CALIBRATION_NOTES.md`; `docs/Chatgpt mod curated guide` is also tracked. No guard test prevents this.
- **Review sheets nobody can finish.** 726 calibration rows, all `PROVISIONAL_REVIEW_REQUIRED`, 0 APPROVED, across the two
  knowledge-pack CSVs and `generated/calibration/*_review.csv`. Activation is six manual steps (`docs/CALIBRATION_IMPORT_NOTES.md`):
  resolve display names to hull ids, validate equipment, set APPROVED.
- **No bulk variant validation.** `validate` takes one variant (`svg/api.py` around line 468); the 441-variant stress runs of
  SVG-012/013 were done by hand. Roadmap proposal 3 asks for it.
- **Mod acceptance by hand.** `tools/mod_acceptance_sweep.py` (PASS / PASS_WITH_UNKNOWNS / PARTIAL / FAIL) exists but is not wired
  into a command, CI or a baseline; `docs/MOD_REVIEW.md` was written by hand. `generated/` holds one-off validation runs with no
  repeatable baseline diff.
- **Static parse failures known but not reported as fix hints**: 5 malformed `.skin` files (SVG-014), DME's `6eme_bureau.faction`
  (SVG-017); last full scan: 7 MALFORMED_OR_CONCATENATED_DATA, 1 MALFORMED_VALUE, 1 unresolved and 1 ambiguous skin, 3 stale enabled refs.
- **Safety gaps from BridgeForge's lessons.** No atomic write anywhere in `svg/` (no `os.replace`); `svg/core/mod_import.py` 71-95
  removes the target tree with `rmtree` and calls `extractall` with a zip-slip check but no per-entry size cap or junction guard;
  `svg/campaign/writer.py` 140, 144 clean up with `rmtree(ignore_errors=True)`.
- **Lint and types not enforced.** Full mypy reached 0 on 2026-08-31 but CI checks two files; a new error exists at
  `svg/analysis/calibration_workspace.py:30` (`generated/capacity-evidence/RESUME.md`). Ruff in CI is `E9` only. No `--help` golden test.
- **Save Workshop S5 is stale.** BridgeForge recorded the capacity-overage evidence (RC8-34..36, BridgeForge `docs/RC8_BEHAVIOUR.md`);
  `generated/capacity-evidence/RESUME.md` still says `CLOSED_CAPACITY_EVIDENCE` and the S5 text and its "three fleets" rule do not cite
  the rows. One S3-written copy loaded in game and the game replaced a stale `sU` with the stack sum on its next save.

## 2. Rules for the implementer

1. Read `AGENTS.md` in its reading order before coding; the contract above overrides anything in this plan.
2. Tests with every parser, validator, adapter and scoring change (`AGENTS.md` Testing). Fixtures are neutral and synthetic; real
   game or mod facts appear only in local, gitignored `generated/` output.
3. A golden-output change is deliberate and documented in the commit body.
4. Run `python -m unittest` (or the repository's documented test command in `TEST_PLAN.md`) and the CI lint/type steps locally
   before each commit. One item per commit; update `ROADMAP.md` and `docs/WORK_LOG.md` with what was built and the tests.
5. Work needing the real install or a game run is built and unit-tested, then recorded in the roadmap as a local step with what
   "done" looks like.

## 3. Work items

### Phase V0: boundary and hygiene (first; about a day)

**V0.1 Repository boundary guard.** After the owner's decision (section 5, item 1): move the tracked real-entity calibration packs,
review CSVs, notes and the curated guide out of git into `generated/` (local copy kept), and add `tests/test_distribution_boundary.py`
that fails when a tracked file under `knowledge_packs/` other than `schema/` and `examples/`, or any tracked `*.provisional.json` /
`*_review.csv`, exists (read `git ls-files` when available, skip otherwise). Whether history is rewritten is the owner's call.
- Status: Done 2026-10-14 (owner decision 1); guard `tests/test_distribution_boundary.py`.

**V0.2 Atomic writes and guarded deletes.** New `svg/core/safeio.py` with `atomic_write_text/bytes/json` (temp file in the same folder,
`os.replace`) and `safe_rmtree(path, allowed_roots)` that refuses junctions/symlinks and paths outside the roots (port BridgeForge's
`bridgeforge/safeio.py` semantics). Convert `mod_import.py`, `campaign/writer.py` and every `write_text` in `svg/output/`; a ratchet
test counts bare `write_text`/`rmtree` per file against a baseline that may only shrink.
- Status: Built: `core/safeio.py`, `tests/test_safeio.py`, `tests/test_safeio_ratchet.py` with an empty, shrink-only `tests/safeio_baseline.json`.

**V0.3 Bounded archive import.** In `mod_import._safe_extract`, refuse an entry over 200 MB uncompressed, a total over 2 GB, or a
compression ratio over 100, before extracting anything; refuse a target that is a junction. Tests with crafted in-memory zips.
- Status: Built: `core/mod_import.py`, `tests/test_mod_import.py` (crafted in-memory zips).

**V0.4 Enforce lint and types.** CI runs full `mypy src` (fix the one new error) and ruff with `E9,F,B` minus the rules
`docs/WORK_LOG.md` 2026-08-31 left deliberately (TRY004, B008); a golden `--help` hash test for every CLI command with a rewrite
mode; `.gitattributes` (LF, batch CRLF).
- Status: Built: `.github/workflows/tests.yml` job `static-analysis` (ruff `E9,F,B` with B008 off, over `src tests tools`; full `mypy src`), `tests/test_cli_golden.py` with `tests/cli_golden.json` (a hash of each command's grammar), `.gitattributes`.

### Phase V1: checks that run themselves (about three days)

**V1.1 `validate-all`** (roadmap proposal 3). New CLI command and `api.run_validate_all(scan, *, source=core|mod:<id>|all)`:
every shipped `.variant` through `validation/legality.py`; output a table grouped by code (`WEAPON_NOT_FOUND`,
`HULLMOD_NOT_FOUND`, `OP_EXCEEDED`, ...) and by mod, JSON and Markdown under the output dir. Severity column follows
BridgeForge's live evidence: a variant naming a missing weapon is fatal at New Game, a missing hull mod is dropped silently
(BridgeForge `CLAUDE.md`, RC8 behaviour 2026-09-27); cite it as evidence, do not invent more.
- Tests: synthetic core with three variants (legal, missing weapon, OP exceeded).
- Done when: it reproduces SVG-012/013's 441-variant run in one command on the local install.
- Status: Built: `voidsmith validate-all`, `analysis/validate_all.py`, `tests/test_validate_all.py`. The 441-variant done condition still needs a run on the local install.

**V1.2 Mod acceptance as a command with a baseline.** Move `tools/mod_acceptance_sweep.py` logic into
`svg/analysis/mod_acceptance.py` (already the module) behind `voidsmith acceptance --baseline FILE`: per enabled mod the verdict and its
diagnostic codes, compared with the previous baseline; prints only changes; progress line per mod; checkpoint so it resumes.
Replaces hand-written `docs/MOD_REVIEW.md` entries for new mods.
- Status: Built: `voidsmith acceptance`, `analysis/acceptance_baseline.py`, `tests/test_acceptance_baseline.py`. The first real baseline is a person-run `--write-baseline`.

**V1.3 Parse failures with locations and hints.** For MALFORMED_OR_CONCATENATED_DATA and MALFORMED_VALUE, record file, line, column
and the parser's last good token; for brace mismatches (SVG-014, SVG-017) the line where depth first goes wrong. Shown in
`scan` output and the GUI diagnostics. Read-only: VoidSmith does not edit mod files (point to BridgeForge for fixes).
- Status: Built: `analysis/parse_diagnostics.py`; in `scan` output and in the GUI Data / Analysis > Diagnostics tab.

**V1.4 Stale enabled mods (SVG-004).** `scan` reports each enabled id with no folder, with the closest installed folder by mod id and
name, as information. `enabled_mods.json` is never edited (`docs/MOD_REVIEW.md`).
- Status: Built: `analysis/stale_enabled_mods.py`; in `scan` output and the Diagnostics tab. SVG-004 stays open in `docs/BUGS.md`: the report names the problem, the stale ids are still in the user's launcher list.

### Phase V2: calibration review that a person can finish (about three days)

All of this measures and proposes; nothing changes a released heuristic set or marks a row APPROVED by itself.

**V2.1 Auto-resolve names to ids.** `tools/import_milestone_calibration.py` step 1 becomes `voidsmith calibration resolve SHEET`:
match each row's display name to hull ids in the loaded scan (exact, then case/punctuation-insensitive, then skin and `(D)` variants).
Unique matches are filled with the rule used; ambiguous rows list candidates; misses stay blank. Output is a new sheet under
`generated/`.
- Status: Built: `voidsmith calibration resolve`, `analysis/calibration_review.py`. Needs a run on the real review sheets.

**V2.2 Pre-checks per row.** For each resolved row run the equipment validation of CALIBRATION_IMPORT_NOTES step 2 and the
legality of any named loadout; add columns `resolve_rule`, `equipment_ok`, `legality`, `ready_for_review` (true only when all pass).
The person approves only `ready_for_review` rows; the sheet sorts them first.
- Status: Built, with limits: equipment text is matched item by item and free text fails it; legality runs only for rows that name an existing variant.

**V2.3 Batch approve with provenance.** `voidsmith calibration approve SHEET --rows ...|--all-ready --reviewer NAME`: sets APPROVED on the
listed rows with reviewer and date. A person runs it; nothing runs it automatically.
- Status: Built: `voidsmith calibration approve`; a person runs it with `--reviewer`, only `ready_for_review` rows are eligible, approvals are appended to a `.approvals.jsonl` file beside the sheet.

**V2.4 Heuristic-set proposal report.** `tools/compare_calibration_heuristics.py` and `evaluate_local_calibration.py` merge into
`voidsmith calibration propose`: against APPROVED rows only, report each heuristic set's match/mismatch counts and the rows that
move, and write a candidate set file (new identifier, rationale stub) under `generated/` for a person to review and register.
Registration stays manual per the Heuristic Registry section.
- Status: Built: `voidsmith calibration propose`, `analysis/calibration_propose.py`; writes an unregistered candidate stub, registration stays manual. The older `tools/` scripts are still present.

### Phase V3: Save Workshop to done (about three days)

**V3.1 S5 from the RC8 rows.** Update `docs/SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md` S5 and `generated/capacity-evidence/RESUME.md` to cite
BridgeForge RC8-34..36 (cost 0.1 supplies per day per unit over, cap 50 per resource; speed from the worst ratio; capacity stored at
save time). Keep over-capacity writes refused until the one open fact is measured: whether a load recomputes an edited `mC`/`mF`/`mP`.
Write that as the one remaining live check (with BridgeForge's rig capacity mod, BridgeForge item 57) instead of the 36-run matrix.
- Status: Done in the tracked docs (they cite RC8-34..36); the one remaining live check (does a load recompute an edited `mC`/`mF`/`mP`) is open. The local, untracked `generated/capacity-evidence/RESUME.md` was not part of this documentation pass.

**V3.2 Overage preview.** `save plan` shows, for an edit that would exceed capacity, the computed daily cost and speed effect from
those rows, labelled with the row ids; the write stays refused (tier 1 boundary).
- Status: Built: `campaign/overage.py`; `overage_preview` in `save plan` JSON and the GUI plan view; `tests/test_overage_preview.py`.

**V3.3 S4 GUI write.** Enable "Write edited copy" behind the existing default-off checkbox, calling `api.run_save_edit_write`; after
writing, run `campaign/verify.py` and show VERIFIED / FAILED_VERIFICATION. GUI tests in `tests/test_gui_save_workshop.py` with the
writer mocked. Release readiness (S6) stays the owner's flag decision.
- Status: Built: "Write edited copy" in `gui/save_workshop.py`, then `api.run_save_verify_copy`; `tests/test_gui_save_workshop.py`. Not yet run against a real game load. S6 is the owner's decision.

**V3.4 Fix the plan's stale test requirement.** `SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md` 136-141 asks for "opt-in" over-capacity
tests for a path S3 does not implement; change it to "refusal" tests, which exist.
- Status: Done in `SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md`.

### Phase V4: sister-repo checks (about two days)

**V4.1 BridgeForge revival check.** `voidsmith check-mod PATH`: run V1.1 and V1.3 on one mod folder (a BridgeForge `working/` copy)
against the core, and write a JSON verdict BridgeForge can read before archiving (roadmap proposal 3 and the sister-repo design
`docs/SISTER_REPO_INTEROPERABILITY_DESIGN.md`). VoidSmith reads only; it never edits the mod.
- Status: Built: `voidsmith check-mod`, `analysis/check_mod.py`, `tests/test_check_mod.py`; exit code 0 PASS, 1 REVIEW, 2 FAIL.

**V4.2 SPW inventory round trip** (sister item 2): a synthetic round-trip test plus a recorded local run on the real install.
- Status: Synthetic round trip built (`tests/test_spw_round_trip.py`); the recorded run on the real install is still to do.

## 4. Order

| Step | Items | Why |
|---|---|---|
| 1 | V0.1 (after the owner's answer), V0.2, V0.3 | published repository: boundary and data safety first |
| 2 | V0.4 | stops silent lint/type regressions |
| 3 | V1.1, V1.2, V1.3, V1.4 | largest hand-run checks |
| 4 | V3.1, V3.4, V3.2, V3.3 | evidence is in; finish phase 57 |
| 5 | V2.1-V2.4 | 726 rows waiting for review |
| 6 | V4.1, V4.2 | interop |

## 5. Owner decisions (2026-10-14, owner: "follow your recommendations")

| # | Decision | Answer |
|---|---|---|
| 1 | V0.1: move the real-entity packs to `generated/` only, or also rewrite git history? | **Move only**; no history rewrite (irreversible, and the files stay in earlier commits of a public repository either way). **Done 2026-10-14**: six files from `knowledge_packs/` and `docs/Chatgpt mod curated guide` untracked and kept locally under `generated/calibration-sources/moved-from-git-2026-10-14/`; guard `tests/test_distribution_boundary.py`; a UTF-16 `claude.md` line at the end of `.gitignore` (no effect as written) rewritten in ASCII |
| 2 | V3.3: enable the write button behind the default-off checkbox before S6? | **Yes, after V3.1**, still behind the default-off checkbox and the existing verify step |
| 3 | V2.3: batch approval of `ready_for_review` rows by a named reviewer? | **Yes**: a person runs it, names themselves, and only rows that passed every pre-check are eligible |
