# V1 structural refactor evidence

Checkpoint: 2026-10-22; baseline master `f0fdb4c`. Pending owner review and merge.
This implements V1 of BridgeForge's [cross-repository refactor plan](https://github.com/Exxec/Project-BridgeForge/blob/main/docs/REFACTOR_PLAN_2026-10.md).

## Responsibilities and compatibility

- `analysis/gap_recommendation.py` (2,416 -> 31 lines) remains the compatible import facade.
  `analysis/gap/` separates models, shared ranking, native/retrofit/acquisition search, orchestration, cache payloads/fingerprints,
  Why-Not explanations and scenario options. Dependencies are acyclic; the largest module is 587 lines.
- `gui/main_window.py` (1,794 -> 611 lines) keeps `MainWindow`, initialization, worker ownership/lifecycle and its existing
  callback methods. Their bodies move to layout, scanning, fitting, retrofit, faction and advisor modules. Helpers accept
  the same window; no new GUI inheritance or backend rules are introduced. Existing canvas/helper re-exports remain.
  Attribute annotations stay on the window; the watchdog constant has one authoritative definition.
- `api.py` (1,196 -> 966 lines) keeps its public service surface. Only seven independent read-only catalog-query functions
  move to `api_queries.py`; this is the trivial seam allowed by V1.
- Existing function signatures, dataclass fields/defaults, ranking and search order, cache version markers and payload schemas
  are preserved. No heuristic, legality, confidence, source-writing, approval or unknown-evidence rule changed.
- The sole pre-existing test edit points its formatter mock at the function's moved module; assertions are unchanged.
  Three new facade guards pin original API/recommendation signatures and models, and window callback signatures without Qt.

## Before/after evidence

| Check | Before | After |
|---|---:|---:|
| Full unittest suite | 998 | 1,001 |
| Skips | 3 | 3 |
| Ruff (E9/F/B) | PASS | PASS |
| Full-source mypy | 122 files, clean | 139 files, clean |
| Root CLI help/version | captured | byte-identical |

All 171 moved definitions, constants and callback bodies compare equal as ASTs, normalizing only helper docstring indentation
and the relocation of window attribute type annotations. Function implementations and runtime assignments are unchanged.
The new signature guards use the pre-refactor baseline captured before moves. `tools/gui_smoke_test.py` passes offscreen.
The safe-write ratchet, distribution-boundary checks and existing CLI goldens pass without baseline relaxation.
Golden JSON SHA-256: `87bc4a6f8a3d5ba12c8fd1e7a6f37543a87f6766605b785bd1b8523afb5088ae`.

## Portable candidate

`tools/build_portable_release.ps1` builds using the unchanged locked dependency graph/offline build path. In-place and
post-archive-extraction GUI smoke tests pass. `tools/verify_portable_cli.py` passes against both the final executable and the
extracted copy: version 0.2.0 and all 31 golden command paths are present, including root and acceptance help.
Local validation candidates and receipts stay in ignored `build/` and `dist/`; none are committed or published.
The exact-commit portable receipt and hosted CI state are recorded in the PR. This is validation, not a release.

The original three source paths remain; extracted definitions retain their baseline history there. No whole-file rename
is claimed. No game/mod/save data or local calibration artifacts were introduced. LIVE TEST NOT PERFORMED.
Owner, rights, live, calibration and publication gates remain unchanged. Review/merge is still pending.
