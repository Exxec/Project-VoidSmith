"""Small, MainWindow-state-free GUI helper functions.

Extracted from `gui/main_window.py` (Phase 35, GUI modularization) with no
behavior change. `_looks_like_starsector_install` has no relationship to the
Ship Fitting Canvas (see `gui/canvas.py`) or any other existing sibling
module, so it gets its own small module rather than being forced into one;
`main_window.py` re-imports it so external references keep working.
"""
from __future__ import annotations

from pathlib import Path


def _looks_like_starsector_install(root: Path) -> bool:
    """Cheap, local-only sanity check before starting a background scan.

    `core/scanner.py::discover_sources` is deliberately lenient -- if
    `starsector-core` isn't present under the chosen root it silently
    treats the root itself as the core source rather than failing, so it
    never rejects a wrong path on its own. Pointing a scan at an unrelated
    folder (a parent directory, a totally different drive, ...) wouldn't
    error quickly; it would scan whatever real files happen to be there,
    slowly, with a source list that supports no conclusion. Catching an
    obviously-wrong folder here, before any scan starts, is cheap (a few
    filesystem stat calls) and avoids that entirely rather than relying on
    a user cancelling out of it after the fact."""
    return (root / "starsector-core").is_dir() or (root / "starsector.exe").exists() or (root / "starsector.sh").exists()
