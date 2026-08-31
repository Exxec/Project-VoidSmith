"""Exercise the backend-bound GUI against a small read-only synthetic install.

This is a release acceptance helper, not a game-data fixture generator.  It
uses the checked-in neutral parser fixture, writes only under the caller's
output directory, and verifies that every fixture source hash is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from starsector_variant_generator import api
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.logging import configure_logging
from starsector_variant_generator.gui.main_window import MainWindow


def _hashes(root: Path) -> dict[Path, str]:
    return {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _materialize_neutral_fixture(destination: Path) -> Path:
    """Copy the split synthetic parser fixture into caller-owned output space."""
    fixtures = Path("tests/fixtures")
    shutil.copytree(fixtures / "game_install", destination, dirs_exist_ok=True)
    shutil.copytree(fixtures / "vanilla_mod", destination, dirs_exist_ok=True)
    shutil.copytree(fixtures / "modded_mod", destination / "mods" / "fixture_mod", dirs_exist_ok=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, help="Optional already-materialized synthetic fixture installation")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_root = args.fixture_root.resolve() if args.fixture_root is not None else _materialize_neutral_fixture(output_dir / "fixture-install").resolve()
    if not fixture_root.is_dir():
        raise SystemExit(f"Fixture installation does not exist: {fixture_root}")
    if fixture_root == output_dir or fixture_root in output_dir.parents:
        raise SystemExit("Output directory must not be inside the read-only fixture installation")

    before = _hashes(fixture_root)
    # Keep GUI preference writes local to this acceptance output rather than
    # modifying the Windows registry during automated verification.
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(output_dir / "settings"))
    app = QApplication([])
    window = MainWindow()
    window.root.setText(str(fixture_root))
    window.output.setText(str(output_dir))
    window.show()
    # Exercise the same scan result/presentation boundary as ScanWorker.  The
    # production UI executes this call in a QThread; direct execution here
    # avoids an artificial event-loop dependency in an offscreen acceptance
    # process without adding a second scanner or GUI rules implementation.
    outcome = api.run_scan(AppConfig(fixture_root, output_dir, output_dir / "logs"), configure_logging(output_dir / "logs"))
    window._scan_complete(outcome)
    QCoreApplication.processEvents()
    if window._registry is None or window.hull_list.count() < 1:
        raise RuntimeError("GUI did not load the scanned fixture data")
    if window.variant_list.count() < 1 or window.faction_list.count() < 1:
        raise RuntimeError("GUI did not populate Retrofit/Faction workspace data")

    # Visit every top-level workspace through the real QTabWidget, ensuring
    # they can render against the normalized scan state.
    for index in range(window.workspace_tabs.count()):
        window.workspace_tabs.setCurrentIndex(index)
        QCoreApplication.processEvents()
    if any(table.model() is None or table.model().rowCount() < 1 for table in window.data_tables.values()):
        raise RuntimeError("GUI did not populate Data / Analysis tables on workspace activation")

    # Exercise an allowed write through the Settings / Export workspace.
    window.workspace_tabs.setCurrentIndex(4)
    exported = api.run_export(window._registry, "baseline_0.2", output_dir, window._current_hull.id, "LINE_BRAWLER")
    window.statusBar().showMessage(f"Export complete: {exported}")
    compatibility_root = output_dir / "compatibility_mod"
    if not exported.is_file() or not any(compatibility_root.rglob("mod_info.json")):
        raise RuntimeError("GUI export did not create the expected compatibility mod")
    if _hashes(fixture_root) != before:
        raise RuntimeError("Read-only fixture source data changed during GUI acceptance")
    window.close()
    app.quit()
    print(f"GUI acceptance passed: {fixture_root} -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
