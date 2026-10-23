"""Window retrofits helpers for MainWindow; GUI rules stay in the backend."""
from __future__ import annotations

from typing import TYPE_CHECKING
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QListWidgetItem, QMessageBox
from starsector_variant_generator import api
from starsector_variant_generator.core.config import DEFAULT_HEURISTIC_SET
from starsector_variant_generator.core.models import Variant

if TYPE_CHECKING:
    from .main_window import MainWindow


def _show_refit_result(self: MainWindow, result: Any) -> None:
    self._last_refit_result = result
    self.apply_refit_result_button.setEnabled(hasattr(result, "refitted_variant"))
    self.refit_detail.setPlainText(str(result))


def _apply_last_refit_result(self: MainWindow) -> None:
    result = getattr(self, "_last_refit_result", None)
    variant = getattr(result, "refitted_variant", None)
    if not isinstance(variant, Variant):
        self.refit_detail.setPlainText("Run a Refit Assistant operation that returns a variant first."); return
    self._open_retrofit_variant(dataclass_replace(variant, source_mod="USER_EDITABLE"))
    self.statusBar().showMessage("Loaded Refit Assistant result into the editable canvas; save to create a local working copy.")


def _compare_refit(self: MainWindow) -> None:
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    transcript = self.video_review_path.text().strip()
    loaded_local = self._loaded_retrofit_variant if self._loaded_retrofit_variant is not None and self._loaded_retrofit_variant.source_mod == "USER_EDITABLE" else None
    try:
        current_local = self._editable_canvas_variant(loaded_local.id, loaded_local.name) if loaded_local is not None else None
    except ValueError as exc:
        self.refit_detail.setPlainText(str(exc)); return
    def compare(item: str) -> dict[str, object]:
        analysis = api.run_analyze_variant_record(self._registry, current_local, "LINE_BRAWLER", "BALANCED", heuristic_set) if current_local is not None else api.run_analyze_variant(self._registry, item, "LINE_BRAWLER", "BALANCED", heuristic_set)
        result: dict[str, object] = {"mechanical_analysis": analysis}
        if loaded_local is not None and current_local is not None:
            result["editable_changes"] = self._editable_change_summary(loaded_local, current_local)
        if transcript:
            result["video_review_evidence"] = api.run_variant_control_evidence(self._registry, item, Path(transcript))
        return result
    if loaded_local is not None:
        self._run("Analyzing editable local variant…", lambda: compare(loaded_local.id), lambda result: self.refit_detail.setPlainText(str(result)), self.compare_refit_button)
    else:
        self._refit(compare, self.compare_refit_button, "Analyzing existing variant…")


def _editable_change_summary(before: Variant, after: Variant) -> tuple[str, ...]:
    changes = []
    for mount in sorted(set(before.weapons_by_mount) | set(after.weapons_by_mount)):
        if before.weapons_by_mount.get(mount) != after.weapons_by_mount.get(mount):
            changes.append(f"mount {mount}: {before.weapons_by_mount.get(mount, '<empty>')} → {after.weapons_by_mount.get(mount, '<empty>')}")
    for label, old, new in (("hullmods", before.hullmods, after.hullmods), ("fighter wings", before.fighter_wings, after.fighter_wings), ("flux vents", before.flux_vents, after.flux_vents), ("flux capacitors", before.flux_capacitors, after.flux_capacitors)):
        if old != new: changes.append(f"{label}: {old!r} → {new!r}")
    return tuple(changes) or ("No editable differences from the loaded local copy.",)


def _choose_video_review(self: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Choose video review transcript", self.video_review_path.text(), "JSON files (*.json)")
    if path:
        self.video_review_path.setText(path)
        self._preferences.setValue("paths/video_review_transcript", path)


def _refit_lock_ids(field: QLineEdit) -> frozenset[str]:
    return frozenset(item.strip() for item in field.text().split(",") if item.strip())


def _fix_legality(self: MainWindow) -> None:
    mounts, hullmods, wings = self._refit_lock_ids(self.refit_locked_mounts), self._refit_lock_ids(self.refit_locked_hullmods), self._refit_lock_ids(self.refit_locked_wings)
    mode = str(self.refit_substitution_selector.currentData())
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    self._refit(lambda item: api.run_fix_legality(self._registry, item, heuristic_set, locked_mount_ids=mounts, locked_hullmod_ids=hullmods, locked_wing_ids=wings, substitution_mode=mode), self.fix_button, "Finding minimal legality fixes", self._show_refit_result)


def _improve_quality(self: MainWindow) -> None:
    mounts, hullmods, wings = self._refit_lock_ids(self.refit_locked_mounts), self._refit_lock_ids(self.refit_locked_hullmods), self._refit_lock_ids(self.refit_locked_wings)
    mode, profile = str(self.refit_mode_selector.currentData()), str(self.refit_profile_selector.currentData())
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    self._refit(lambda item: api.run_improve_quality(self._registry, item, mode, profile, heuristic_set, locked_mount_ids=mounts, locked_hullmod_ids=hullmods, locked_wing_ids=wings), self.improve_button, "Improving existing variant", self._show_refit_result)


def _retrofit_output_root(self: MainWindow) -> Path | None:
    value = self.output.text().strip()
    if not value:
        self.refit_detail.setPlainText("Choose an output directory before creating editable retrofit copies.")
        return None
    return Path(value)


def _copy_retrofit_to_library(self: MainWindow) -> None:
    if self._registry is None or (variant_id := self._variant_id()) is None or (output := self._retrofit_output_root()) is None:
        return
    target = output / "editable_retrofits" / f"{variant_id}.variant"
    replace = False
    if target.exists():
        decision = QMessageBox.question(
            self, "Replace editable copy?",
            f"Replace the local working copy?\n{target}\n\nThe scanned game/mod source will not be changed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if decision != QMessageBox.Yes:
            return
        replace = True
    try:
        path = api.save_editable_retrofit_copy(self._registry, variant_id, output, replace=replace)
    except ValueError as exc:
        self.refit_detail.setPlainText(str(exc)); return
    self.refit_detail.setPlainText(f"Editable local copy: {path}\nOriginal game/mod variant remains unchanged.")


def _load_editable_retrofit(self: MainWindow) -> None:
    output = self._retrofit_output_root()
    if output is None:
        return
    path, _ = QFileDialog.getOpenFileName(self, "Load editable retrofit", str(output / "editable_retrofits"), "Variant files (*.variant)")
    if not path:
        return
    try:
        variant = api.load_editable_retrofit_variant(output, Path(path))
    except ValueError as exc:
        self.refit_detail.setPlainText(str(exc)); return
    self._open_retrofit_variant(variant)


def _refresh_editable_retrofit_library(self: MainWindow) -> None:
    output = self._retrofit_output_root()
    if output is None:
        return
    library = output / "editable_retrofits"
    self.editable_retrofit_list.clear()
    files = sorted(library.glob("*.variant")) if library.is_dir() else []
    for path in files:
        record = api.inspect_editable_retrofit_variant(self._registry, output, path) if self._registry is not None else None
        status = record.legality if record and record.legality is not None else "UNREADABLE" if record else "UNSCANNED"
        item = QListWidgetItem(f"[{status}] {path.name}"); item.setData(Qt.UserRole, str(path)); item.setToolTip(record.message or "No validator message." if record else "Scan installation to validate local editable retrofits."); self.editable_retrofit_list.addItem(item)
    if not files:
        self.editable_retrofit_list.addItem("No local editable retrofit files found.")


def _open_editable_retrofit_item(self: MainWindow, item: QListWidgetItem) -> None:
    value = item.data(Qt.UserRole)
    if not isinstance(value, str):
        return
    output = self._retrofit_output_root()
    if output is None:
        return
    try:
        self._open_retrofit_variant(api.load_editable_retrofit_variant(output, Path(value)))
    except ValueError as exc:
        self.refit_detail.setPlainText(str(exc))


def _show_editable_retrofit_history(self: MainWindow) -> None:
    item = self.editable_retrofit_list.currentItem()
    value = item.data(Qt.UserRole) if item is not None else None
    if not isinstance(value, str):
        self.refit_detail.setPlainText("Select a local editable retrofit first."); return
    path = Path(value); history = path.parent / ".history" / path.stem
    entries = sorted(history.glob("*.variant")) if history.is_dir() else []
    self.refit_detail.setPlainText("Replacement history is recoverable local output only.\n" + ("\n".join(str(entry) for entry in entries) if entries else "No prior local replacement versions."))


def _publish_editable_retrofit(self: MainWindow) -> None:
    item = self.editable_retrofit_list.currentItem(); value = item.data(Qt.UserRole) if item is not None else None
    if not isinstance(value, str):
        self.refit_detail.setPlainText("Select a local editable retrofit first."); return
    output = self._retrofit_output_root()
    if output is None:
        return
    try:
        path = api.publish_editable_retrofit_variant(output, Path(value), replace=False)
    except FileExistsError:
        if QMessageBox.question(self, "Replace published retrofit?", "The published output differs. Replace that output-only compatibility-mod variant? The editable source copy will not be changed.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        path = api.publish_editable_retrofit_variant(output, Path(value), replace=True)
    except ValueError as exc:
        self.refit_detail.setPlainText(str(exc)); return
    self.refit_detail.setPlainText(f"Published: {path}\nEnable the generated ‘VoidSmith Editable Retrofits’ mod in Starsector. No source files were changed.")


def _restore_editable_retrofit_history(self: MainWindow) -> None:
    item = self.editable_retrofit_list.currentItem()
    value = item.data(Qt.UserRole) if item is not None else None
    if not isinstance(value, str):
        self.refit_detail.setPlainText("Select a local editable retrofit first."); return
    output = self._retrofit_output_root()
    if output is None:
        return
    path = Path(value); entries = sorted((path.parent / ".history" / path.stem).glob("*.variant"))
    if not entries:
        self.refit_detail.setPlainText("No prior local replacement versions are available."); return
    labels = [entry.name for entry in entries]
    selected, accepted = QInputDialog.getItem(self, "Restore local history", "History version", labels, len(labels) - 1, False)
    if not accepted:
        return
    history_path = entries[labels.index(selected)]
    if QMessageBox.question(self, "Restore local version?", "Restore this local history version? The current editable file will first be preserved in history.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
        return
    try:
        restored = api.restore_editable_retrofit_variant_history(output, history_path)
    except ValueError as exc:
        self.refit_detail.setPlainText(str(exc)); return
    self._refresh_editable_retrofit_library(); self.refit_detail.setPlainText(f"Restored local editable retrofit: {restored}\nThe prior current file was preserved in local history.")


def _populate_missing_retrofits(self: MainWindow) -> None:
    if self._registry is None or self._current_hull is None or (output := self._retrofit_output_root()) is None:
        self.refit_detail.setPlainText("Select a hull in Ships, then choose an output directory."); return
    # Captured now, not read inside the background lambda: `_run`'s
    # operation only actually executes once its worker thread starts,
    # by which point the user may have changed or cleared the hull
    # selection -- the same race `_generate`'s own `hull_id = self.
    # _current_hull.id` capture (above) exists to avoid. See
    # docs/BUGS.md SVG-021.
    hull_id = self._current_hull.id
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    self._run(
        "Checking existing retrofits and creating local starter variations when absent…",
        lambda: api.load_or_populate_retrofits(self._registry, hull_id, output, heuristic_set),
        self._apply_populate_missing_retrofits_result,
        self.populate_retrofits_button,
    )


def _apply_populate_missing_retrofits_result(self: MainWindow, result: Any) -> None:
    self.refit_detail.setPlainText(result.note + (
        "\nExisting scanned variants:\n" + "\n".join(item.id for item in result.existing_variants)
        if result.existing_variants else
        "\nProfiles considered: " + ", ".join(result.attempted_profiles)
        + "\nProfiles generated: " + (", ".join(result.generated_profiles) or "None")
        + ("\nEditable local files:\n" + "\n".join(map(str, result.generated_paths)) if result.generated_paths else "")
    ))
    self._refresh_editable_retrofit_library()
