# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

`AGENTS.md` is the canonical contributor and agent contract. Read and follow
its required document order before changing code. This short file exists only
for tools that automatically discover `CLAUDE.md`; it intentionally does not
duplicate implementation history or local review notes.

VoidSmith is offline, deterministic, explainable, and source-read-only. Keep
legality separate from quality, preserve unknown scripted behavior, and do not
commit Starsector/mod data, reports, entity lists, or local calibration output.

For the current project plan, use `ROADMAP.md`. For commands, packaging, and
user-facing behavior, use `README.md`, `docs/QUICK_START.md`, and
`docs/DEVELOPER_GUIDE.md`, which also covers architecture and data flow in
depth. Run the portable suite after behavior changes:

```powershell
uv run --no-project --with-editable . python -m unittest discover -s tests -v
```

Run a single test module or case the same way, e.g.:

```powershell
uv run --no-project --with-editable . python -m unittest tests.test_scanner -v
uv run --no-project --with-editable . python -m unittest tests.test_scanner.ScannerTests.test_scan_emits_staged_progress_and_records_workload_metrics -v
```

Lint (not pinned as a project dependency; run ad hoc via `uv run --with`):

```powershell
uv run --no-project --with ruff ruff check src/ tests/ tools/
uv run --no-project --with mypy mypy src/
```
