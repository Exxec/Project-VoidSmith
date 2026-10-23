"""Window scan helpers for MainWindow; GUI rules stay in the backend."""
from __future__ import annotations

from typing import TYPE_CHECKING
import logging
import threading
from pathlib import Path
from time import monotonic
from typing import Any
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox, QProgressDialog
from starsector_variant_generator import api
from starsector_variant_generator.core.config import DEFAULT_HEURISTIC_SET, AppConfig
from starsector_variant_generator.core.mod_import import ModImportResult, resolve_dropped_mod
from starsector_variant_generator.gui.helpers import _looks_like_starsector_install
from starsector_variant_generator.gui.models import EntityTableModel
from starsector_variant_generator.gui.session import HullCatalog
from starsector_variant_generator.gui.workers.scan_worker import ScanWorker

if TYPE_CHECKING:
    from .main_window import MainWindow

_SCAN_STALL_WARNING_INTERVAL_S = 20.0


def dragEnterEvent(self: MainWindow, event: QDragEnterEvent) -> None:  # type: ignore[override]
    if event.mimeData().hasUrls():
        event.acceptProposedAction()


def dropEvent(self: MainWindow, event: QDropEvent) -> None:  # type: ignore[override]
    dropped = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
    if not dropped:
        return
    event.acceptProposedAction()
    cache_root = Path(self.output.text().strip() or (Path.cwd() / "generated" / "gui")) / "cache" / "dropped_mods"
    failures: list[str] = []
    newly_added: list[ModImportResult] = []
    for path in dropped:
        result = resolve_dropped_mod(path, cache_root)
        if result.error is not None:
            failures.append(f"{path.name}: {result.error}")
            continue
        if any(existing.mod_root == result.mod_root for existing in self._extra_mods):
            continue  # Already added; re-dropping the same archive already refreshed its extraction above.
        self._extra_mods.append(result)
        newly_added.append(result)
    self._refresh_extra_mods_list()
    if failures:
        QMessageBox.warning(self, "Could not add mod", "\n\n".join(failures))
    if not newly_added:
        return
    # A prior scan already exists in this session, and neither a real
    # scan nor another incremental merge is currently running (reusing
    # scan_button's enabled state as that guard -- both paths disable
    # it): incorporate the drop immediately, without waiting for a full
    # rescan of the whole installation, so testing a new mod doesn't
    # mean re-scanning 148 others just to see it. Falls back to the
    # original "rescan to include" behavior otherwise (nothing to merge
    # into yet, or something else is already in flight).
    # Also require no other backend read (_generate, _refit, faction
    # analysis, export, ...) to be in flight (self._threads): those
    # workers read self._registry only when their thread actually
    # executes, not when their button was clicked, so starting an
    # incremental incorporation -- which reassigns self._registry --
    # while one is still running could swap the data out from under it
    # mid-read. See _registry_write_in_progress for the read side of
    # this same guard.
    if self._scan_result is not None and self._config is not None and self._scan_thread is None and self.scan_button.isEnabled() and not self._threads:
        self._incorporate_dropped_mods(newly_added)
    else:
        self.statusBar().showMessage(f"Added {len(self._extra_mods)} additional mod(s); rescan to include {'them' if len(newly_added) > 1 else 'it'}.")


def _incorporate_dropped_mods(self: MainWindow, newly_added: list[ModImportResult]) -> None:
    config, existing_result = self._config, self._scan_result
    # Both narrowed here defensively, not just for the type checker: the
    # sole caller (dropEvent) already verified `self._config is not None`
    # and `self._scan_result is not None` before invoking this method,
    # but that guarantee doesn't cross a method boundary on its own.
    assert config is not None
    # `newly_added` only ever contains entries with `error is None`
    # (dropEvent filters on that), and `resolve_dropped_mod`/
    # `_locate_mod_info` (core/mod_import.py) only ever return
    # `error is None` together with a real `mod_root` -- never both
    # `None`. So `mod_root` is never `None` here.
    mod_roots = tuple(mod.mod_root for mod in newly_added if mod.mod_root is not None)
    assert len(mod_roots) == len(newly_added)
    operation = lambda: api.run_incremental_mod_scan(config, existing_result, mod_roots)
    self._run(f"Incorporating {len(newly_added)} dropped mod(s)…", operation, self._apply_incremental_scan_outcome, self.scan_button)


def _apply_incremental_scan_outcome(self: MainWindow, outcome: Any) -> None:
    """The `completed` half of `_incorporate_dropped_mods`, factored out
    as a directly-callable method (not an inline closure) so it can be
    exercised synchronously in tests without needing a real QThread to
    actually finish -- background-thread completion timing isn't
    reliably observable via processEvents() polling in a headless
    test harness (confirmed directly: even a trivial, guaranteed-fast
    `_run` operation never completed within 5s / 2.3M polls in that
    setup), independent of whether the real app (which runs a normal
    blocking app.exec() event loop, not a polling one) has any issue."""
    self._scan_result, self._registry = outcome.result, outcome.registry
    self._catalog = HullCatalog.from_scan(outcome.result)
    for value in self._catalog.hull_sizes():
        if self.size_filter.findData(value) < 0: self.size_filter.addItem(value, value)
    for value in self._catalog.source_mods():
        if self.source_filter.findData(value) < 0: self.source_filter.addItem(value, value)
    self._refresh_hulls(); self._populate_secondary()
    skipped_note = f"; {len(outcome.skipped_mod_roots)} could not be parsed" if outcome.skipped_mod_roots else ""
    self.statusBar().showMessage(f"Incorporated {len(outcome.added_mod_ids)} dropped mod(s) into the current session{skipped_note} -- a full rescan will re-verify everything together.")
    self.scan_summary.appendPlainText(f"\nIncrementally incorporated (not a full rescan): {', '.join(outcome.added_mod_ids) or 'none'}.")


def _refresh_extra_mods_list(self: MainWindow) -> None:
    self.extra_mods_list.clear()
    if not self._extra_mods:
        self.extra_mods_list.addItem("No additional mods added.")
        return
    for mod in self._extra_mods:
        item = QListWidgetItem(f"{mod.mod_name or mod.mod_id} [{mod.mod_id}]\n{mod.mod_root}")
        item.setData(Qt.UserRole, mod.mod_root)
        self.extra_mods_list.addItem(item)


def _remove_selected_extra_mod(self: MainWindow) -> None:
    item = self.extra_mods_list.currentItem()
    if item is None:
        return
    target = item.data(Qt.UserRole)
    if target is None:
        return
    self._extra_mods = [mod for mod in self._extra_mods if mod.mod_root != target]
    self._refresh_extra_mods_list()
    self.statusBar().showMessage("Removed from the next scan's additional mods. Rescan to apply.")


def _choose_installation(self: MainWindow) -> None:
    path = QFileDialog.getExistingDirectory(self, "Select Starsector installation")
    if path: self.root.setText(path)


def _choose_calibration_fixture(self: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Choose local calibration labels", self.calibration_fixture.text(), "JSON files (*.json)")
    if path:
        self.calibration_fixture.setText(path)
        self._preferences.setValue("paths/calibration_fixture", path)


def _choose_release_archive(self: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Choose VoidSmith portable archive", self.release_archive.text(), "Archives (*.zip *.tar.gz *.tgz *.tar)")
    if path:
        self.release_archive.setText(path)
        self._preferences.setValue("paths/release_archive", path)


def _verify_release_archive(self: MainWindow) -> None:
    archive_text = self.release_archive.text().strip()
    if not archive_text:
        self.release_detail.setPlainText("Choose a local portable archive first."); return
    archive = Path(archive_text); checksum = Path(f"{archive}.sha256")
    def complete(result: Any) -> None:
        self.release_detail.setPlainText(
            f"{'PASS' if result.passed else 'CHECK REQUIRED'} — {result.version or 'unknown version'} / {result.platform or 'unknown platform'}\n"
            f"Checksum: {result.checksum_status}; inventory: {result.inventory_status}.\n"
            + "\n".join(result.findings)
        )
    self._run("Verifying portable archive inventory…", lambda: api.run_verify_portable_release(archive, checksum if checksum.is_file() else None), complete, self.release_verify_button)


def _evaluate_local_calibration(self: MainWindow) -> None:
    if self._scan_result is None or self._registry is None:
        self.calibration_detail.setPlainText("Scan local data before evaluating calibration labels."); return
    fixture_text = self.calibration_fixture.text().strip()
    if not fixture_text:
        self.calibration_detail.setPlainText("Choose a local hash-bound calibration label fixture first."); return
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    fixture, scan, registry = Path(fixture_text), self._scan_result, self._registry
    def complete(result: Any) -> None:
        report = result.report
        self.calibration_detail.setPlainText(
            f"Fixture: {report.fixture_id}\nHeuristic set: {report.heuristic_set}\n"
            f"Match {report.matched}; mismatch {report.mismatched}; stale {report.stale}; unsupported {report.unsupported}.\n"
            "Review result only: labels and heuristics were not changed."
        )
    self._run("Evaluating local hash-bound calibration labels…", lambda: api.run_local_calibration_workspace(fixture, scan, registry, heuristic_set), complete, self.calibration_button)


def _choose_advanced_config(self: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Select advanced generation request", filter="JSON files (*.json)")
    if path: self.advanced_config.setText(path)


def _start_scan(self: MainWindow) -> None:
    root_text, output_text = self.root.text().strip(), self.output.text().strip()
    if not root_text: QMessageBox.warning(self, "Installation required", "Choose your Starsector installation folder first."); return
    root = Path(root_text)
    if not root.is_dir(): QMessageBox.warning(self, "Invalid installation", f"'{root}' does not exist or is not a folder. Choose the folder containing your Starsector installation."); return
    if not _looks_like_starsector_install(root):
        QMessageBox.warning(self, "Not a Starsector installation", f"'{root}' does not look like a Starsector installation -- no starsector-core folder or starsector.exe was found there. Scanning an unrelated folder can be slow and won't produce useful results. Choose the top-level folder Starsector was installed into.")
        return
    if not output_text: QMessageBox.warning(self, "Output directory required", "Choose a safe output directory for generated reports and local cache data."); return
    output = Path(output_text)
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        QMessageBox.warning(self, "Output directory not writable", f"Could not create or write to '{output}': {exc}"); return
    if self._scan_thread is not None: return
    self._scan_discarded = False; self._scan_cancel_event = threading.Event(); self.scan_button.setEnabled(False); self.cancel_scan_button.setEnabled(True)
    self._scan_recent_sources.clear()
    self._scan_progress = QProgressDialog("Scanning read-only Starsector and enabled-mod data…", "Cancel Scan", 0, 0, self)
    self._scan_progress.setWindowTitle("Scanning Local Data"); self._scan_progress.setWindowModality(Qt.WindowModal); self._scan_progress.canceled.connect(self._discard_scan); self._scan_progress.show()
    # `self._extra_mods` only ever holds `ModImportResult`s with
    # `error is None` (see `dropEvent`'s own filter), which
    # `core/mod_import.py` guarantees always carries a real `mod_root`.
    extra_mod_paths = tuple(mod.mod_root for mod in self._extra_mods if mod.mod_root is not None)
    assert len(extra_mod_paths) == len(self._extra_mods)
    self._config = AppConfig(root, output, output / "logs", extra_mod_paths=extra_mod_paths, include_disabled_mods=self.include_disabled_mods.isChecked())
    thread = QThread(self); worker = ScanWorker(self._config, cancel_check=self._scan_cancel_event.is_set); worker.moveToThread(thread); thread.started.connect(worker.run); worker.progress.connect(self._scan_progressed)
    # thread.quit is connected FIRST for every terminal signal, before
    # the application-level handler that acts on the result -- Qt calls
    # slots in connection order, so this guarantees the thread is asked
    # to stop regardless of what _scan_complete/_operation_failed do
    # (including raising), rather than the thread's own termination
    # depending on an application handler completing cleanly first.
    worker.completed.connect(thread.quit); worker.completed.connect(self._scan_complete)
    worker.failed.connect(thread.quit); worker.failed.connect(self._operation_failed)
    worker.cancelled.connect(thread.quit)
    thread.finished.connect(worker.deleteLater); thread.finished.connect(self._scan_finished)
    self._scan_thread = thread; self._scan_worker = worker; self.scan_button.setEnabled(False); self.statusBar().showMessage("Scanning read-only source data…")
    self._scan_last_progress = None; self._scan_last_progress_at = monotonic(); self._scan_stall_warned_at = None; self._scan_watchdog.start()
    thread.start()


def _scan_progressed(self: MainWindow, progress: Any) -> None:
    """Present scanner telemetry only; the GUI never interprets game data."""
    self._scan_last_progress = progress; self._scan_last_progress_at = monotonic(); self._scan_stall_warned_at = None
    stage = str(getattr(progress, "stage", "SCANNING")).replace("_", " ").title()
    completed = int(getattr(progress, "completed_sources", 0))
    total = int(getattr(progress, "total_sources", 0))
    entities = int(getattr(progress, "entities_found", 0))
    current_source = str(getattr(progress, "current_source", "") or "")
    source_text = f" {completed}/{total} sources" if total else ""
    message = f"{stage}{source_text} - {entities} records found"
    if current_source:
        # A real, named source, not just an aggregate count -- this is
        # what actually proves the scan is doing something specific
        # right now instead of just a number that might be frozen.
        # Tracked in a short rolling trail (not just the single current
        # name) so the dialog reads as a real, moving list of recent
        # activity: see core/scanner.py's own per-source "starting"
        # events, which report this before a slow individual source's
        # own fingerprint/parse has finished, not only after.
        if not self._scan_recent_sources or self._scan_recent_sources[-1] != current_source:
            self._scan_recent_sources.append(current_source)
        message += f"\nCurrently scanning: {current_source}"
        trail = [name for name in self._scan_recent_sources if name != current_source]
        if trail:
            message += f"\nRecently: {', '.join(trail)}"
    if self._scan_progress is not None and not self._scan_discarded:
        self._scan_progress.setLabelText(message)
        # A real total isn't known during the brief initial DISCOVERING
        # stage (0), so the dialog stays an indeterminate spinner until
        # then; once PARSING reports a real source count, switch to a
        # determinate bar with a real, live-updating value so the dialog
        # visibly moves instead of appearing frozen for the scan's
        # duration -- see core/scanner.py's own per-source progress fix.
        if total:
            if self._scan_progress.maximum() != total:
                self._scan_progress.setMaximum(total)
            self._scan_progress.setValue(completed)
    self.statusBar().showMessage(f"{message.splitlines()[0]}{' -- ' + current_source if current_source else ''}")


def _scan_complete(self: MainWindow, outcome: Any) -> None:
    if self._scan_discarded:
        self.scan_summary.setPlainText("Latest scan completed but its results were discarded at user request. No source data was changed.")
        self.statusBar().showMessage("Scan completed; results discarded.")
        return
    if outcome is None:
        # A worker that reported a scan error emits no usable outcome.
        # Keep the current UI state intact instead of turning that known
        # failure into a second callback exception.
        self.scan_summary.setPlainText("Scan did not produce a result. Check the log for the original error.")
        self.statusBar().showMessage("Scan failed; existing results were kept.")
        return
    self._scan_result, self._registry = outcome.result, outcome.registry; self._catalog = HullCatalog.from_scan(outcome.result)
    self.size_filter.clear(); self.source_filter.clear(); self.faction_filter.clear(); self.size_filter.addItem("All sizes", None); self.source_filter.addItem("All source mods", None); self.faction_filter.addItem("All factions", None)
    for value in self._catalog.hull_sizes(): self.size_filter.addItem(value, value)
    for value in self._catalog.source_mods(): self.source_filter.addItem(value, value)
    for faction in self._catalog.factions(): self.faction_filter.addItem(f"{faction.name} ({faction.source_mod})", (faction.id, faction.source_mod))
    diagnostic_lines = api.scan_diagnostic_lines(getattr(outcome, "report", None))
    self.scan_diagnostics_view.setPlainText("\n".join(diagnostic_lines) if diagnostic_lines else "No located parse failures and no enabled mods missing from the install.")
    self._refresh_hulls(); self._populate_secondary()
    extra_note = f"Additional dropped mod(s) included: {', '.join(mod.mod_id or mod.mod_name or '?' for mod in self._extra_mods)}." if self._extra_mods else ""
    self.scan_summary.setPlainText("\n".join(line for line in (
        f"Loaded: {len(outcome.result.hulls)} hulls, {len(outcome.result.weapons)} weapons, {len(outcome.result.hullmods)} hullmods, {len(outcome.result.variants)} variants.",
        f"Diagnostics: {len(outcome.result.warnings)} warnings, {len(outcome.result.errors)} source errors, {len(outcome.result.skipped_entities)} skipped records.",
        f"{len(diagnostic_lines)} located diagnostic line(s) are listed under Data / Analysis > Diagnostics." if diagnostic_lines else "",
        self._scan_metrics_summary(outcome.result),
        extra_note,
        "Source data was read-only. Inspect Data / Analysis for entity provenance; local reports are under the configured output directory.",
    ) if line))
    self.statusBar().showMessage(f"Scan complete: {len(outcome.result.hulls)} hulls, {len(outcome.result.errors)} source errors.")


def _scan_metrics_summary(result: Any) -> str:
    metrics = getattr(result, "scan_metrics", None)
    if metrics is None:
        return "Scan timing unavailable."
    total = getattr(metrics, "stage_seconds", {}).get("total", 0.0)
    return f"Performance: {getattr(metrics, 'sources_scanned', 0)} sources, {getattr(metrics, 'files_hashed', 0)} relevant files hashed, {total:.2f}s total."


def _discard_scan(self: MainWindow) -> None:
    """Requests cooperative cancellation (Scanner.cancel_check, checked
    between sources -- see core/scanner.py's ScanCancelled) and
    discards any result that arrives anyway. Not instant: a source's
    own fingerprint/parse already in flight still finishes first, so
    the scan stops within roughly one source's worth of time rather
    than immediately, but "Scan Installed Data" re-enables as soon as
    that happens instead of waiting for the whole remaining scan."""
    if self._scan_thread is None: return
    self._scan_discarded = True; self.cancel_scan_button.setEnabled(False)
    if self._scan_cancel_event is not None: self._scan_cancel_event.set()
    if self._scan_progress is not None: self._scan_progress.setLabelText("Cancelling… finishing the current source before stopping.")
    self.statusBar().showMessage("Cancelling scan…")


def _scan_finished(self: MainWindow) -> None:
    self._scan_watchdog.stop()
    self.scan_button.setEnabled(True); self.cancel_scan_button.setEnabled(False); self._scan_thread = None; self._scan_cancel_event = None; self._scan_worker = None
    if self._scan_progress is not None: self._scan_progress.close(); self._scan_progress.deleteLater(); self._scan_progress = None
    if self._scan_discarded: self.statusBar().showMessage("Scan cancelled.")
    self._maybe_close_after_background_work()


def _check_scan_stall(self: MainWindow) -> None:
    """Watchdog tick (every 5s while a scan is in flight): if no real
    progress event has arrived in a while, log exactly what was last
    known -- stage, source, how long ago -- plus live worker/thread
    state, so an apparent hang is diagnosable from the log without
    needing to catch it live. Re-logs at most once per stall (reset the
    moment real progress resumes), not every 5s while it persists."""
    if self._scan_thread is None or self._scan_last_progress_at is None:
        return
    elapsed = monotonic() - self._scan_last_progress_at
    if elapsed < _SCAN_STALL_WARNING_INTERVAL_S:
        return
    if self._scan_stall_warned_at is not None:
        return
    self._scan_stall_warned_at = monotonic()
    stage = getattr(self._scan_last_progress, "stage", None) if self._scan_last_progress is not None else None
    source = getattr(self._scan_last_progress, "current_source", "") if self._scan_last_progress is not None else ""
    logging.getLogger("svg").warning(
        "Scan appears stalled: no progress event for %.1fs (last stage=%s, last source=%s, "
        "thread.isRunning()=%s, thread.isFinished()=%s, worker reference alive=%s)",
        elapsed, stage or "<none yet>", source or "<none>",
        self._scan_thread.isRunning(), self._scan_thread.isFinished(), self._scan_worker is not None,
    )


def _workspace_changed(self: MainWindow, index: int) -> None:
    # Table rows stay in compact model storage rather than allocating one
    # widget item per cell. Materialization is still deferred until Data /
    # Analysis is opened; normalized backend indexes are already available.
    if index == 3 and self._data_tables_pending:
        self._populate_data_tables()


def _populate_secondary(self: MainWindow) -> None:
    if self._scan_result is None: return
    self.variant_list.clear(); self.faction_list.clear(); self.generation_faction_selector.clear(); self.generation_faction_selector.addItem("No faction selected", None)
    for variant in sorted(self._scan_result.variants, key=lambda item: (item.name, item.id)):
        item = QListWidgetItem(f"{variant.name} • {variant.hull_id or 'Unknown hull'}"); item.setData(Qt.UserRole, variant.id); self.variant_list.addItem(item)
    for faction in sorted(self._scan_result.factions, key=lambda item: (item.name, item.id)):
        item = QListWidgetItem(f"{faction.name} • {faction.source_mod}"); item.setData(Qt.UserRole, (faction.id, faction.source_mod)); self.faction_list.addItem(item)
    for faction in sorted(self._scan_result.factions, key=lambda item: (item.name, item.id)):
        self.generation_faction_selector.addItem(f"{faction.name} ({faction.source_mod})", faction.id)
    self._data_entities = {"Weapons": self._scan_result.weapons, "Hullmods": self._scan_result.hullmods, "Fighters": self._scan_result.fighters, "Variants": self._scan_result.variants}
    self._data_tables_pending = True
    self.provenance_detail.setPlainText("Open Data / Analysis to materialize local normalized tables on demand.")
    for button in (self.fix_button, self.improve_button, self.compare_refit_button, self.copy_retrofit_button, self.load_editable_retrofit_button, self.populate_retrofits_button, self.capability_button, self.recommend_button, self.build_comparison_button, self.fleet_support_button, self.fleet_support_why_not_button, self.scenario_evaluate_button, self.export_button, self.calibration_button, self.save_feedback_button): button.setEnabled(True)


def _populate_data_tables(self: MainWindow) -> None:
    if not self._data_tables_pending:
        return
    entity_records = self._data_entities
    records: dict[str, list[tuple[str, ...]]] = {"Weapons": [(x.name, x.size or "Unknown", x.mount_type or "Unknown", x.source_mod) for x in entity_records["Weapons"]], "Hullmods": [(x.name, "Yes" if x.hidden else "No", x.source_mod) for x in entity_records["Hullmods"]], "Fighters": [(x.name, x.role or "Unknown", x.source_mod) for x in entity_records["Fighters"]], "Variants": [(x.name, x.hull_id or "Unknown", x.source_mod) for x in entity_records["Variants"]]}
    for name, rows in records.items():
        model = self.data_tables[name].model()
        assert isinstance(model, EntityTableModel)
        model.set_records(rows, list(entity_records[name]))
    self._data_tables_pending = False
