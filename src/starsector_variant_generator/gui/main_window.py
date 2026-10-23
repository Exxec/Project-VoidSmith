"""Qt desktop shell; all rules, scoring, and legality stay in the backend."""
from __future__ import annotations

import json as json
import logging as logging
import threading as threading
from collections import deque as deque
from collections.abc import Callable as Callable
from pathlib import Path as Path
from time import monotonic as monotonic
from typing import Any as Any

from PySide6.QtCore import QObject as QObject, QSettings as QSettings, QSize as QSize, Qt as Qt, QThread as QThread, QTimer as QTimer
from PySide6.QtGui import QDragEnterEvent as QDragEnterEvent, QDropEvent as QDropEvent
from PySide6.QtWidgets import QAbstractItemView as QAbstractItemView, QApplication as QApplication, QCheckBox as QCheckBox, QComboBox as QComboBox, QFileDialog as QFileDialog, QFormLayout as QFormLayout, QFrame as QFrame, QGroupBox as QGroupBox, QHBoxLayout as QHBoxLayout, QInputDialog as QInputDialog, QLabel as QLabel, QLineEdit as QLineEdit, QListWidget as QListWidget, QListWidgetItem as QListWidgetItem, QMainWindow as QMainWindow, QMessageBox as QMessageBox, QPlainTextEdit as QPlainTextEdit, QProgressDialog as QProgressDialog, QPushButton as QPushButton, QSpinBox as QSpinBox, QSplitter as QSplitter, QTableView as QTableView, QTabWidget as QTabWidget, QVBoxLayout as QVBoxLayout, QWidget as QWidget

from starsector_variant_generator import api as api
from starsector_variant_generator.analysis.fleet_support import FleetSupportConstraints as FleetSupportConstraints, SupportFocus as SupportFocus, fleet_support_request_from_payload as fleet_support_request_from_payload, fleet_support_request_to_payload as fleet_support_request_to_payload, parse_fleet_selections as parse_fleet_selections
from starsector_variant_generator.analysis.recommendation_feedback import FeedbackKind as FeedbackKind, RecommendationFeedback as RecommendationFeedback
from starsector_variant_generator.analysis.scenario_advisor import ScenarioCapabilityTarget as ScenarioCapabilityTarget, generic_scenario_profiles as generic_scenario_profiles, scenario_advisor_request_from_payload as scenario_advisor_request_from_payload, scenario_advisor_request_to_payload as scenario_advisor_request_to_payload, user_defined_scenario as user_defined_scenario
from starsector_variant_generator.core.config import DEFAULT_HEURISTIC_SET as DEFAULT_HEURISTIC_SET, AppConfig as AppConfig
from starsector_variant_generator.core.mod_import import ModImportResult as ModImportResult, resolve_dropped_mod as resolve_dropped_mod
from starsector_variant_generator.core.models import Hull as Hull, Variant as Variant
from starsector_variant_generator.core.safeio import atomic_write_text as atomic_write_text
from starsector_variant_generator.gui.canvas import MOUNT_TYPE_COLORS as MOUNT_TYPE_COLORS, TechnicalCanvas as TechnicalCanvas, _detect_mirror_mount_pairs as _detect_mirror_mount_pairs, _displayable_weapon_mounts as _displayable_weapon_mounts
from starsector_variant_generator.gui.helpers import _looks_like_starsector_install as _looks_like_starsector_install
from starsector_variant_generator.gui.models import EntityTableModel as EntityTableModel
from starsector_variant_generator.gui.presentation import format_build_why_not_comparison as format_build_why_not_comparison, format_fleet_support_comparison as format_fleet_support_comparison, format_fleet_support_result as format_fleet_support_result, format_fleet_support_why_not as format_fleet_support_why_not, format_generation_results as format_generation_results, format_scenario_fleet_assessment as format_scenario_fleet_assessment
from starsector_variant_generator.gui.save_workshop import SaveWorkshopWidget as SaveWorkshopWidget
from starsector_variant_generator.gui.session import HullCatalog as HullCatalog
from starsector_variant_generator.gui.workers.analysis_worker import AnalysisWorker as AnalysisWorker
from starsector_variant_generator.gui.workers.save_worker import SaveWorker as SaveWorker
from starsector_variant_generator.gui.workers.scan_worker import ScanWorker as ScanWorker
from starsector_variant_generator.profiles.catalog import available_profiles as available_profiles

# `TechnicalCanvas`, `MOUNT_TYPE_COLORS`, and `_detect_mirror_mount_pairs`
# (all imported above from `gui/canvas.py`) and `_looks_like_starsector_
# install` (from `gui/helpers.py`) are re-exported here unchanged -- Phase 35
# (GUI modularization) moved their definitions out of this module, but
# `tests/test_gui_canvas.py` and any other caller still imports them
# directly from `starsector_variant_generator.gui.main_window`.

# How long a scan can go without a real progress event before the watchdog
# logs a stall warning. Deliberately generous: fingerprinting/parsing one
# large real source can legitimately take several real seconds on its own
# (see core/scanner.py's own per-source logging) -- this is meant to catch
# a genuine stall (no events at all for a long stretch), not to complain
# about ordinary per-source variance.
from .window_scan import _SCAN_STALL_WARNING_INTERVAL_S as _SCAN_STALL_WARNING_INTERVAL_S


from . import window_layout

from . import window_scan

from . import window_fitting

from . import window_retrofits

from . import window_faction

from . import window_advisors

class MainWindow(QMainWindow):
    _data_entities: dict[str, list[Any]]

    _generated_candidates: list[dict[str, Any]]
    data_tables: dict[str, QTableView]
    save_workshop_page: SaveWorkshopWidget | None
    values: dict[str, QLabel]
    def __init__(self) -> None:
        super().__init__()
        self._catalog: HullCatalog | None = None; self._visible: tuple[Hull, ...] = ()
        self._config: AppConfig | None = None
        self._registry: Any = None; self._scan_result: Any = None; self._current_hull: Hull | None = None; self._loaded_retrofit_variant: Variant | None = None
        self._fit_weapons: dict[str, str] = {}; self._mirror_pairs: dict[str, str] = {}; self._scan_thread: QThread | None = None; self._threads: set[QThread] = set()
        # True once the user has asked to close while background work was
        # still in flight (see closeEvent). Closing immediately in that
        # state would let Qt tear the window down while a QThread is still
        # live and might still emit into it -- the same class of race this
        # session already found to be a genuine PySide6 segfault risk
        # elsewhere (QProgressDialog.deleteLater() racing a still-running
        # thread). closeEvent defers the real close until every tracked
        # thread has actually finished, via _maybe_close_after_background_work.
        self._closing_requested = False
        # `moveToThread` transfers ownership of the underlying Qt object to
        # the target thread, but does nothing to keep the *Python* wrapper
        # object referenced -- if nothing holds a real reference to a worker
        # beyond the local variable in the method that constructs it, that
        # variable goes out of scope the moment the method returns while the
        # worker's own QThread keeps running in the background, risking the
        # Python object being garbage-collected out from under a still-live
        # C++-side QObject (and, in the generic case, corrupting whichever
        # entry belongs to a different in-flight operation once cleared).
        # Retained explicitly for the whole thread lifetime, cleared only
        # once that thread has actually finished (_scan_finished/_finish_thread).
        self._scan_worker: ScanWorker | None = None
        self._active_workers: dict[QThread, QObject] = {}
        self._scan_discarded = False; self._scan_progress: QProgressDialog | None = None; self._scan_cancel_event: threading.Event | None = None
        # Short rolling trail of real source names the current scan has
        # already moved past, shown alongside the live "currently scanning"
        # name so the dialog reads as a real, moving list of activity
        # rather than a single name replacing itself in place.
        self._scan_recent_sources: deque[str] = deque(maxlen=5)
        # Stall diagnostics: the watchdog fires periodically while a scan is
        # in flight and, if no real progress event has arrived recently,
        # logs exactly what was last known (stage, source, how long ago)
        # plus live worker/thread state -- so an apparent hang is
        # diagnosable from the log even if it can't be caught live.
        self._scan_last_progress: Any = None
        self._scan_last_progress_at: float | None = None
        self._scan_stall_warned_at: float | None = None
        self._scan_watchdog = QTimer(self); self._scan_watchdog.setInterval(5000); self._scan_watchdog.timeout.connect(self._check_scan_stall)
        self._data_tables_pending = False
        self._operation_tokens: dict[QPushButton, int] = {}
        self._operation_progress: dict[QThread, QProgressDialog] = {}
        self._advisor_card_origin: str | None = None
        self._extra_mods: list[ModImportResult] = []
        self.setAcceptDrops(True)
        self._preferences = QSettings("VoidSmith", "Desktop")
        # Preserve the user's existing local settings across the application
        # rename without retaining the former name as the active namespace.
        previous_preferences = QSettings("Starsector Variant Generator", "Desktop")
        for key in ("window/size", "paths/starsector", "paths/output"):
            if not self._preferences.contains(key) and previous_preferences.contains(key):
                self._preferences.setValue(key, previous_preferences.value(key))
        self.setWindowTitle("VoidSmith")
        # 1600x920 (not super().size(), Qt's bare 640x480 default for a
        # never-shown top-level widget) as the fallback for a first-ever
        # launch, so a later un-maximize lands somewhere reasonable rather
        # than a cramped default.
        self.resize(self._preferences.value("window/size", QSize(1600, 920)))  # type: ignore[call-overload]
        # Tracked ourselves via resizeEvent below rather than read back from
        # Qt's own normalGeometry() at close time -- confirmed unreliable
        # for this window (returns an invalid (-1, -1) size once shown while
        # started maximized, at least under the offscreen QPA platform used
        # in tests, and there is no reason to trust it more on a real one).
        self._last_normal_size = self.size()
        self._shown_once = False
        # No stored preference at all means a genuinely first-ever launch;
        # start maximized in that case too, so a fresh install doesn't open
        # into a small default window on today's larger/higher-DPI displays.
        # setWindowState (not showMaximized()) because the caller (app.py)
        # still calls .show() itself after construction; setting the state
        # ahead of that first real show is the idiom that reliably survives
        # a subsequent plain .show() call.
        if self._preferences.value("window/maximized", not self._preferences.contains("window/size"), type=bool):
            self.setWindowState(Qt.WindowMaximized)
        self.setCentralWidget(self._make_tabs())
        self._hull_filter_timer = QTimer(self); self._hull_filter_timer.setSingleShot(True); self._hull_filter_timer.setInterval(150); self._hull_filter_timer.timeout.connect(self._refresh_hulls)
        self.mode_selector.setCurrentIndex(max(0, self.mode_selector.findData(self._preferences.value("fit/mode", "beginner"))))
        self.faction_mode_selector.setCurrentIndex(max(0, self.faction_mode_selector.findData(self._preferences.value("fit/faction_mode", "FACTION_PLUS"))))
        self.slot_include_hidden.setChecked(bool(self._preferences.value("fit/show_hidden", False, type=bool)))
        self.fleet_support_hulls.setText(str(self._preferences.value("fleet_support/locked_hulls", "")))
        self.fleet_support_candidate.setText(str(self._preferences.value("fleet_support/candidate_hull", "")))
        self.fleet_support_focus.setCurrentIndex(max(0, self.fleet_support_focus.findData(self._preferences.value("fleet_support/focus", "BALANCED"))))
        self.fleet_support_access.setCurrentIndex(max(0, self.fleet_support_access.findData(self._preferences.value("fleet_support/access", "FACTION_PLUS"))))
        self.fleet_support_heuristic.setCurrentIndex(max(0, self.fleet_support_heuristic.findData(self._preferences.value("fleet_support/heuristic", "baseline_0.14"))))
        self.fleet_support_allow_foreign.setChecked(bool(self._preferences.value("fleet_support/allow_foreign", True, type=bool)))
        self.fleet_support_include_hidden.setChecked(bool(self._preferences.value("fleet_support/include_hidden", False, type=bool)))
        self.statusBar().showMessage("No scan loaded — configure an installation in Settings / Export.")
        # Auto-scan on launch when a previously-configured, still-valid
        # install path is already remembered (see paths/starsector above),
        # so the app doesn't sit idle requiring a manual click every
        # restart. Deliberately still a REAL scan, not a shortcut around
        # verification: Scanner's own per-source hash-verified snapshot
        # cache (core/scanner.py, keyed on config.output_dir/"cache" -- the
        # same output directory this preference-restored scan will reuse)
        # already makes a warm rescan of an unchanged install ~65% faster
        # than a cold one (freshly re-measured against the real 148-mod
        # install this feature was built against: 18.69s cold -> 6.62s
        # warm) while still re-checking every source's hash -- so this
        # trades one manual click for a shorter
        # wait, without ever silently trusting stale data. Deferred via
        # QTimer so the window finishes constructing/showing first instead
        # of a progress dialog appearing mid-construction.
        root_text = self.root.text().strip()
        if root_text and _looks_like_starsector_install(Path(root_text)):
            QTimer.singleShot(150, self._maybe_auto_scan)

    def _maybe_auto_scan(self) -> None:
        if self._scan_thread is None and self._registry is None:
            self._start_scan()

    def _make_tabs(self) -> QTabWidget:
        return window_layout._make_tabs(self)

    def _ships(self) -> QWidget:
        return window_layout._ships(self)

    def _browse(self) -> QWidget:
        return window_layout._browse(self)

    def _browser(self) -> QWidget:
        return window_layout._browser(self)

    def _center(self) -> QWidget:
        return window_layout._center(self)

    def _inspector_tab(self) -> QWidget:
        return window_layout._inspector_tab(self)

    def _generate_tab(self) -> QWidget:
        return window_layout._generate_tab(self)

    def _inspector(self) -> QWidget:
        return window_layout._inspector(self)

    def _retrofits(self) -> QWidget:
        return window_layout._retrofits(self)

    def _faction(self) -> QWidget:
        return window_layout._faction(self)

    def _data(self) -> QWidget:
        return window_layout._data(self)

    def _settings(self) -> QWidget:
        return window_layout._settings(self)

    def _toggle_save_workshop(self, enabled: bool) -> None:
        return window_layout._toggle_save_workshop(self, enabled)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        return window_scan.dragEnterEvent(self, event)

    def dropEvent(self, event: QDropEvent) -> None:
        return window_scan.dropEvent(self, event)

    def _incorporate_dropped_mods(self, newly_added: list[ModImportResult]) -> None:
        return window_scan._incorporate_dropped_mods(self, newly_added)

    def _apply_incremental_scan_outcome(self, outcome: Any) -> None:
        """The `completed` half of `_incorporate_dropped_mods`, factored out
        as a directly-callable method (not an inline closure) so it can be
        exercised synchronously in tests without needing a real QThread to
        actually finish -- background-thread completion timing isn't
        reliably observable via processEvents() polling in a headless
        test harness (confirmed directly: even a trivial, guaranteed-fast
        `_run` operation never completed within 5s / 2.3M polls in that
        setup), independent of whether the real app (which runs a normal
        blocking app.exec() event loop, not a polling one) has any issue."""
        return window_scan._apply_incremental_scan_outcome(self, outcome)

    def _refresh_extra_mods_list(self) -> None:
        return window_scan._refresh_extra_mods_list(self)

    def _remove_selected_extra_mod(self) -> None:
        return window_scan._remove_selected_extra_mod(self)

    def _choose_installation(self) -> None:
        return window_scan._choose_installation(self)

    def _choose_calibration_fixture(self) -> None:
        return window_scan._choose_calibration_fixture(self)

    def _choose_release_archive(self) -> None:
        return window_scan._choose_release_archive(self)

    def _verify_release_archive(self) -> None:
        return window_scan._verify_release_archive(self)

    def _evaluate_local_calibration(self) -> None:
        return window_scan._evaluate_local_calibration(self)

    def _choose_advanced_config(self) -> None:
        return window_scan._choose_advanced_config(self)

    def _start_scan(self) -> None:
        return window_scan._start_scan(self)

    def _scan_progressed(self, progress: Any) -> None:
        """Present scanner telemetry only; the GUI never interprets game data."""
        return window_scan._scan_progressed(self, progress)

    def _scan_complete(self, outcome: Any) -> None:
        return window_scan._scan_complete(self, outcome)

    @staticmethod
    def _scan_metrics_summary(result: Any) -> str:
        return window_scan._scan_metrics_summary(result)

    def _discard_scan(self) -> None:
        """Requests cooperative cancellation (Scanner.cancel_check, checked
        between sources -- see core/scanner.py's ScanCancelled) and
        discards any result that arrives anyway. Not instant: a source's
        own fingerprint/parse already in flight still finishes first, so
        the scan stops within roughly one source's worth of time rather
        than immediately, but "Scan Installed Data" re-enables as soon as
        that happens instead of waiting for the whole remaining scan."""
        return window_scan._discard_scan(self)

    def _scan_finished(self) -> None:
        return window_scan._scan_finished(self)

    def _check_scan_stall(self) -> None:
        """Watchdog tick (every 5s while a scan is in flight): if no real
        progress event has arrived in a while, log exactly what was last
        known -- stage, source, how long ago -- plus live worker/thread
        state, so an apparent hang is diagnosable from the log without
        needing to catch it live. Re-logs at most once per stall (reset the
        moment real progress resumes), not every 5s while it persists."""
        return window_scan._check_scan_stall(self)

    def _workspace_changed(self, index: int) -> None:
        return window_scan._workspace_changed(self, index)

    def _populate_secondary(self) -> None:
        return window_scan._populate_secondary(self)

    def _populate_data_tables(self) -> None:
        return window_scan._populate_data_tables(self)

    def _refresh_hulls(self) -> None:
        return window_fitting._refresh_hulls(self)

    def _schedule_hull_refresh(self) -> None:
        """Avoid rebuilding a large hull list once per keystroke."""
        return window_fitting._schedule_hull_refresh(self)

    def _reset_filters(self) -> None:
        return window_fitting._reset_filters(self)

    def _show_provenance(self, category: str) -> None:
        return window_fitting._show_provenance(self, category)

    def _open_variant_hull(self, item: QListWidgetItem) -> None:
        return window_fitting._open_variant_hull(self, item)

    def _open_retrofit_variant(self, variant: Variant) -> None:
        return window_fitting._open_retrofit_variant(self, variant)

    def _selected_hull(self, row: int) -> None:
        return window_fitting._selected_hull(self, row)

    def _update_fit_metrics(self) -> None:
        return window_fitting._update_fit_metrics(self)

    def _editable_canvas_variant(self, variant_id: str, name: str) -> Variant:
        return window_fitting._editable_canvas_variant(self, variant_id, name)

    def _save_current_fit_to_library(self) -> None:
        return window_fitting._save_current_fit_to_library(self)

    @staticmethod
    def _editable_stat_value(field: QLineEdit, fallback: int | None) -> int | None:
        return window_fitting._editable_stat_value(field, fallback)

    def _choose_slot(self, slot_id: str) -> None:
        return window_fitting._choose_slot(self, slot_id)

    def _run(self, message: str, operation: Callable[[], Any], completed: Callable[[Any], None], control: QPushButton, *, cancellable: bool = False) -> None:
        # Backend tasks are immutable snapshots. Token-gating prevents a stale
        # result from replacing a newer UI request without unsafe cancellation.
        token = self._operation_tokens.get(control, 0) + 1; self._operation_tokens[control] = token
        thread = QThread(self); worker = (SaveWorker if control.property("readOnlySaveControl") or control.property("saveWriteControl") else AnalysisWorker)(operation); worker.moveToThread(thread); thread.started.connect(worker.run)
        # thread.quit connected first, before the application-level
        # handler -- see _start_scan's identical reasoning.
        worker.completed.connect(thread.quit); worker.completed.connect(lambda result: self._complete_operation(control, token, completed, result))
        worker.failed.connect(thread.quit); worker.failed.connect(self._operation_failed)
        thread.finished.connect(worker.deleteLater); thread.finished.connect(lambda: self._finish_thread(thread, control))
        self._threads.add(thread); self._active_workers[thread] = worker; control.setEnabled(False); self.statusBar().showMessage(message)
        if cancellable:
            # Analysis services do not expose a safe checkpoint/cancel API.
            # Cancel therefore means "stop waiting for this result": the
            # in-flight read completes without adoption, and its thread is
            # still retained until Qt confirms it has stopped.
            progress = QProgressDialog(message, "Stop Waiting", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.canceled.connect(lambda: self._discard_operation_result(thread, control, token))
            self._operation_progress[thread] = progress
            progress.show()
        thread.start()

    def _discard_operation_result(self, thread: QThread, control: QPushButton, token: int) -> None:
        if self._operation_tokens.get(control) == token:
            self._operation_tokens[control] = token + 1
            self.statusBar().showMessage("Stopped waiting for the analysis; the read-only calculation will finish safely in the background.")
        dialog = self._operation_progress.get(thread)
        if dialog is not None:
            dialog.setLabelText("Stopping result delivery safely…")
            dialog.setCancelButton(None)

    def _complete_operation(self, control: QPushButton, token: int, completed: Callable[[Any], None], result: Any) -> None:
        if self._operation_tokens.get(control) == token:
            completed(result)

    def _fail_operation(self, control: QPushButton, token: int, message: str) -> None:
        # A user who stopped waiting for an operation also opted out of its
        # eventual error dialog. The traceback remains in the worker log.
        if self._operation_tokens.get(control) == token:
            self._operation_failed(message)

    def _finish_thread(self, thread: QThread, control: QPushButton) -> None:
        dialog = self._operation_progress.pop(thread, None)
        if dialog is not None:
            dialog.close(); dialog.deleteLater()
        self._threads.discard(thread); self._active_workers.pop(thread, None); control.setEnabled(False if control.property("saveWriteControl") else (self._registry is not None or control is self.release_verify_button or bool(control.property("readOnlySaveControl")))); thread.deleteLater()
        self._maybe_close_after_background_work()
    def _operation_failed(self, message: str) -> None: self.statusBar().showMessage(f"Operation failed: {message}"); QMessageBox.critical(self, "Operation failed", message)

    def _registry_write_in_progress(self) -> bool:
        """True while a full scan or an incremental dropped-mod
        incorporation is rewriting self._scan_result/self._registry/
        self._catalog -- both disable scan_button while in flight (see
        _start_scan and dropEvent's own guard). A backend read started via
        _run only actually reads self._registry once its worker thread
        executes, not when its button was clicked, so a write landing in
        that gap would silently swap the data out from under an
        already-running read. Callers that read the registry in a
        background thread (_generate, _refit, faction analysis, export)
        check this first and decline to start rather than race it."""
        return self._scan_thread is not None or not self.scan_button.isEnabled()

    def _generate(self) -> None:
        return window_fitting._generate(self)
    def _generation_complete(self, outcome: Any) -> None:
        return window_fitting._generation_complete(self, outcome)

    def _preview_candidate(self, row: int) -> None:
        return window_fitting._preview_candidate(self, row)

    def _open_selected_in_advanced(self) -> None:
        """Keep the selected backend result visible; never regenerate it here."""
        return window_fitting._open_selected_in_advanced(self)

    def _variant_id(self) -> str | None:
        return window_fitting._variant_id(self)
    def _refit(self, operation: Callable[[str], Any], button: QPushButton, message: str, on_result: Callable[[Any], None] | None = None) -> None:
        return window_fitting._refit(self, operation, button, message, on_result)

    def _show_refit_result(self, result: Any) -> None:
        return window_retrofits._show_refit_result(self, result)

    def _apply_last_refit_result(self) -> None:
        return window_retrofits._apply_last_refit_result(self)
    def _compare_refit(self) -> None:
        return window_retrofits._compare_refit(self)

    @staticmethod
    def _editable_change_summary(before: Variant, after: Variant) -> tuple[str, ...]:
        return window_retrofits._editable_change_summary(before, after)

    def _choose_video_review(self) -> None:
        return window_retrofits._choose_video_review(self)

    @staticmethod
    def _refit_lock_ids(field: QLineEdit) -> frozenset[str]:
        return window_retrofits._refit_lock_ids(field)

    def _fix_legality(self) -> None:
        return window_retrofits._fix_legality(self)

    def _improve_quality(self) -> None:
        return window_retrofits._improve_quality(self)

    def _retrofit_output_root(self) -> Path | None:
        return window_retrofits._retrofit_output_root(self)

    def _copy_retrofit_to_library(self) -> None:
        return window_retrofits._copy_retrofit_to_library(self)

    def _load_editable_retrofit(self) -> None:
        return window_retrofits._load_editable_retrofit(self)

    def _refresh_editable_retrofit_library(self) -> None:
        return window_retrofits._refresh_editable_retrofit_library(self)

    def _open_editable_retrofit_item(self, item: QListWidgetItem) -> None:
        return window_retrofits._open_editable_retrofit_item(self, item)

    def _show_editable_retrofit_history(self) -> None:
        return window_retrofits._show_editable_retrofit_history(self)

    def _publish_editable_retrofit(self) -> None:
        return window_retrofits._publish_editable_retrofit(self)

    def _restore_editable_retrofit_history(self) -> None:
        return window_retrofits._restore_editable_retrofit_history(self)

    def _populate_missing_retrofits(self) -> None:
        return window_retrofits._populate_missing_retrofits(self)

    def _apply_populate_missing_retrofits_result(self, result: Any) -> None:
        return window_retrofits._apply_populate_missing_retrofits_result(self, result)

    def _faction_selected(self, _: int) -> None:
        return window_faction._faction_selected(self, _)
    def _choose_knowledge_pack(self) -> None:
        return window_faction._choose_knowledge_pack(self)
    def _faction_id(self) -> tuple[str, str | None] | None:
        return window_faction._faction_id(self)
    def _faction_run(self, operation: Callable[[str, str | None], Any], button: QPushButton, message: str) -> None:
        return window_faction._faction_run(self, operation, button, message)
    def _analyze_capability(self) -> None:
        return window_faction._analyze_capability(self)
    def _gap_recommendations(self) -> None:
        return window_faction._gap_recommendations(self)

    def _compare_build_paths(self) -> None:
        return window_faction._compare_build_paths(self)

    def _save_recommendation_feedback(self) -> None:
        return window_faction._save_recommendation_feedback(self)

    def _fleet_support(self) -> None:
        return window_advisors._fleet_support(self)

    def _show_fleet_support_result(self, result: Any) -> None:
        return window_advisors._show_fleet_support_result(self, result)

    def _scenario_profile_from_controls(self) -> Any:
        return window_advisors._scenario_profile_from_controls(self)

    def _evaluate_scenario(self) -> None:
        return window_advisors._evaluate_scenario(self)

    def _generate_scenario_fit(self) -> None:
        return window_advisors._generate_scenario_fit(self)

    def _save_scenario_request(self) -> None:
        return window_advisors._save_scenario_request(self)

    def _load_scenario_request(self) -> None:
        return window_advisors._load_scenario_request(self)

    def _compare_fleet_support_cards(self) -> None:
        return window_advisors._compare_fleet_support_cards(self)

    def _fleet_support_card_selected(self, _: int) -> None:
        return window_advisors._fleet_support_card_selected(self, _)

    def _generate_support_fit(self) -> None:
        return window_advisors._generate_support_fit(self)

    def _add_current_hull_to_fleet_support(self) -> None:
        return window_advisors._add_current_hull_to_fleet_support(self)

    def _clear_fleet_support(self) -> None:
        return window_advisors._clear_fleet_support(self)

    def _fleet_support_constraints_from_controls(self) -> FleetSupportConstraints:
        return window_advisors._fleet_support_constraints_from_controls(self)

    def _save_fleet_support_request(self) -> None:
        return window_advisors._save_fleet_support_request(self)

    def _load_fleet_support_request(self) -> None:
        return window_advisors._load_fleet_support_request(self)

    def _fleet_support_why_not(self) -> None:
        return window_advisors._fleet_support_why_not(self)

    def _export_current(self) -> None:
        return window_fitting._export_current(self)

    def showEvent(self, event: Any) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._shown_once = True

    def resizeEvent(self, event: Any) -> None:  # type: ignore[override]
        # Gated on `_shown_once`: a resizeEvent reporting a transitional,
        # not-yet-maximized placeholder size can fire during the very first
        # show() while `window/maximized` is being applied, before
        # isMaximized() catches up -- confirmed directly (a bogus 640x480
        # "not maximized" resizeEvent fires ahead of the real maximize
        # taking hold). Ignoring resize events before the first real show
        # avoids that clobbering the real starting size.
        if self._shown_once and not self.isMaximized():
            self._last_normal_size = self.size()
        super().resizeEvent(event)

    def closeEvent(self, event: Any) -> None:  # type: ignore[override]
        # Never let Qt tear the window down while a background QThread
        # (the scan, or any generic _run()-launched operation in
        # self._threads) is still live -- closing here previously had no
        # guard at all, so closing mid-scan would race a real, running
        # thread against widget destruction, the same class of issue this
        # session already confirmed can segfault PySide6 elsewhere. Defer
        # the actual close: ignore this event, request cooperative
        # cancellation of any in-flight scan, and let
        # _maybe_close_after_background_work (called from every terminal
        # thread path) finish the close once nothing is running anymore.
        if self._scan_thread is not None or self._threads:
            event.ignore()
            if self._closing_requested:
                return  # already asked; still waiting for in-flight work to actually stop
            self._closing_requested = True
            if self._scan_thread is not None:
                self._discard_scan()
            self.statusBar().showMessage("Finishing in-progress work before closing…")
            return
        # self._last_normal_size (tracked via resizeEvent), not
        # normalGeometry(), so a later un-maximized launch resizes to the
        # window's real pre-maximize dimensions, not a full-screen size
        # masquerading as "normal".
        self._preferences.setValue("window/size", self._last_normal_size)
        self._preferences.setValue("window/maximized", self.isMaximized())
        self._preferences.setValue("paths/starsector", self.root.text()); self._preferences.setValue("paths/output", self.output.text())
        self._preferences.setValue("scan/include_disabled_mods", self.include_disabled_mods.isChecked())
        self._preferences.setValue("fit/mode", self.mode_selector.currentData()); self._preferences.setValue("fit/faction_mode", self.faction_mode_selector.currentData()); self._preferences.setValue("fit/show_hidden", self.slot_include_hidden.isChecked())
        self._preferences.setValue("fleet_support/locked_hulls", self.fleet_support_hulls.text()); self._preferences.setValue("fleet_support/candidate_hull", self.fleet_support_candidate.text()); self._preferences.setValue("fleet_support/focus", self.fleet_support_focus.currentData()); self._preferences.setValue("fleet_support/access", self.fleet_support_access.currentData()); self._preferences.setValue("fleet_support/heuristic", self.fleet_support_heuristic.currentData()); self._preferences.setValue("fleet_support/allow_foreign", self.fleet_support_allow_foreign.isChecked()); self._preferences.setValue("fleet_support/include_hidden", self.fleet_support_include_hidden.isChecked()); super().closeEvent(event)

    def _maybe_close_after_background_work(self) -> None:
        """Called from every terminal thread path (_scan_finished,
        _finish_thread) so a close requested while work was in flight
        actually completes the moment it's safe, instead of leaving the
        user stuck on a window that silently stopped responding to the
        close button."""
        if self._closing_requested and self._scan_thread is None and not self._threads:
            self.close()
