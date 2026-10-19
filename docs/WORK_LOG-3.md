<!-- page-nav:start -->
> Page 3 of 3 of the VoidSmith work log. Previous: [WORK_LOG-2.md](WORK_LOG-2.md). Newest entries: [WORK_LOG-3.md](WORK_LOG-3.md).
<!-- page-nav:end -->

## 2026-08-21 — Foundation and live scan (continued)

  After all of the above, ran `ruff check --fix` (safe fixes only, no `--unsafe-fixes`) for the remaining bulk-cosmetic majority: 125 `I001` unsorted-imports, 19 `UP035` deprecated `typing` imports, 13 `UP037` unnecessary quoted annotations, 10 `F401` unused imports, 4 `PYI041` redundant numeric unions, 4 `RUF100` unused `noqa` comments, plus one each of `UP017`/`SIM114`/`RET501`/`B009`x2 -- 200 fixed automatically. This surfaced one real regression, caught immediately by re-running `mypy` rather than assuming a lint-only tool couldn't break typing: `output/analysis_reports.py`'s import-sorting fix landed on top of an in-progress edit already on disk from the concurrent process sharing this repo (their own `object` -> `Hull`/`Entity`/`Sequence[Entity]` type-tightening pass through this same file, evidently mid-flight -- confirmed via `git diff`, not reverted), which had tightened several function signatures but left one helper, `_entity_sort_key(entity: object)`, still `object`-typed; once its 4 real callers were more precisely typed, mypy could see `entity.source_mod`/`entity.id` weren't provable on a bare `object`. Fixed by widening its parameter to `Entity` -- the same base class the concurrent process's own edit had already imported into this file for exactly this purpose, and the type every one of its 4 real call sites already passes.

  Final Ruff count: 222 -> 22 (12 `TRY004` + 10 `B008`, both deliberately left with the reasoning above -- not unreviewed). `mypy src/` re-confirmed clean (0 errors) after the `analysis_reports.py` fix. Full suite: 764 passing, 1 skipped, 0 regressions. `from starsector_variant_generator.gui.main_window import MainWindow` re-confirmed importable after the import-sorting pass touched `gui/` files. New `docs/BUGS.md` entry: SVG-023 (Open, awaiting a human decision on `player_suitability` semantics).

## Post-1.0 phase log

| Phase | Status | Evidence and limit |
| --- | --- | --- |
| 50–56 | Complete with limitations / decision gates retained | Added offline portable archive verification (GUI and CLI; ZIP/tar inventory plus optional SHA-256, no extraction/execution), a local hash-bound calibration workspace, explicit local feedback capture, and backend-only Build Why-Not comparison. Added Linux qualification, player-suitability decision, and campaign-parser evidence-gate documents. Full suite: 772 passing, 1 skipped; GUI acceptance passed after correcting its `QTableView`/model row-count check. Hosted release success, real Linux desktop qualification, player-suitability semantics, and campaign content parsing remain explicitly external or decision-gated. |
| 57 (S3) | Implemented; over-capacity writing refused | Owner decision 2026-10-06: `voidsmith save write` / `api.run_save_edit_write` write one verified new copy below `OUTPUT_DIR/save_workshop/` for changes the plan ACCEPTED within the saved capacity (cargo space across all edited stacks, fuel, crew plus marines); over-capacity or unprovable changes are NOT_DETERMINABLE and never written. `campaign/writer.py` patches only planned byte spans; `campaign/verify.py` independently re-hashes the original, walks the copy against the spans and re-reads it. Gate `OPEN_WITHIN_CAPACITY`. Tests: `tests/test_campaign_writer.py` (25) plus updated planner/GUI tests; suite 847 passing, 3 skipped; ruff clean on new files; mypy clean for `campaign/` and `cli/`. Limits: saved capacity is not runtime-verified; the saved space-used figure is not rewritten and whether the game recalculates it is untested; edited copies are not game-load tested (S5/S6); GUI write controls (S4) unbuilt; symlink refusal test skips without symlink rights. One real save copy was written and verified through the CLI locally (not committed). |

## Traceability rules

- Every scan records source errors, warnings, and heuristic provenance.
- Every observed defect receives an ID in `BUGS.md`.
- Generated inventories are derived from the scan report; source files remain untouched.
- Later phases must add an entry here with tests run and report locations.

## 2026-10-18 - Automation plan V0.2 to V1.4

- Built `core/safeio.py` and moved all writes in `src/` onto it; the ratchet test counts bare writes and deletes (baseline now empty). Campaign copy cleanup uses `safe_rmtree`.
- Bounded zip import (entry, total, ratio, symlink entries, link targets) with crafted in-memory zips as tests; the extraction reads real byte counts so a lying zip directory cannot bypass the caps.
- CI: ruff E9,F,B and full mypy; fixed 10 B905, 2 B007, 3 unused imports and the `CalibrationWorkspaceResult.diagnostics` annotation (it is a tuple of dicts). `cli/main.py` now exposes `build_parser()`; the golden test hashes parser structure rather than rendered `--help` because argparse output differs between Python 3.11, 3.12 and 3.13+. `.gitattributes` added (LF, CRLF for batch and PowerShell).
- `validate-all`, `acceptance`, parse-failure locations and the stale-enabled-mod report; all unit-tested on synthetic data (`tests/test_validate_all.py`, `test_acceptance_baseline.py`, `test_parse_diagnostics.py`, `test_scan_parse_failures.py`, `test_stale_enabled_mods.py`). Parser offsets refer to the normalised text, so the structure line (raw file) is reported beside them. The first real-install runs are local steps (see ROADMAP).

## 2026-10-18 - Automation plan V1 GUI, V2, V3, V4

- GUI Diagnostics tab for located parse failures and stale enabled mods, through `api.scan_diagnostic_lines`; offscreen tests in `tests/test_gui_canvas.py`.
- Calibration review tooling (`calibration resolve|approve|propose`) with tests in `tests/test_calibration_review.py` (synthetic hulls only; the heuristic measurement is mocked). Heuristic sets are never registered or tuned; the candidate is an unchanged copy with a TODO rationale.
- Save Workshop: docs cite RC8-34..36; `campaign/overage.py` preview; GUI "Write edited copy" with `api.run_save_verify_copy` (tests with the writer mocked plus one real end-to-end write on a synthetic save). Found while wiring it: `MainWindow._finish_thread` re-enables a finished control, which would have re-armed the write button after a write, so write controls carry a `saveWriteControl` property that keeps them disabled until the widget refreshes them.
- `check-mod` and the SPW round-trip test (`tests/test_check_mod.py`, `tests/test_spw_round_trip.py`).
- Writing Python edits through a bash heredoc corrupted backslash-n escape sequences more than once; edits containing them were redone with chr(92) or the Edit tool.

## 2026-10-18 documentation refresh (branch docs-refresh-2026-10-18)

- Re-checked every tracked guide against `voidsmith --help`, per-command `--help` and the code after the automation plan landed. Updated README, QUICK_START, USER_GUIDE (new "Automated checks" section), DEVELOPER_GUIDE (automation commands, safeio, CI gates), GUI.md (Diagnostics tab, Workshop label, overage preview), TEST_PLAN (sections 26 and 27), DATA_SCHEMA (`overage_preview`), the Save Workshop documents (GUI write built, config flag is a session-only checkbox), BUGS (SVG-004 now reported by `scan`, still open), MOD_REVIEW, CALIBRATION_IMPORT_NOTES, SISTER_REPO design, IMPLEMENTATION_STATUS, ROADMAP (branch merged, S4 built) and AUTOMATION_PLAN (a status line per item). AGENTS.md: three fact fixes only (check-mod built, safeio exists, SPW synthetic round trip); rules and version unchanged.
- Not verified here (needs the real install or the game): the real-install runs listed in ROADMAP, the local untracked `generated/capacity-evidence/RESUME.md`, and any game-load behaviour of a written copy.

<!-- page-nav:start -->
> End of the last page.
<!-- page-nav:end -->
