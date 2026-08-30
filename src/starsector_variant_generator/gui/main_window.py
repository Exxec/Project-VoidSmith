"""Qt desktop shell; all rules, scoring, and legality stay in the backend."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace as dataclass_replace
from collections import deque
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import Any

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from starsector_variant_generator import api
from starsector_variant_generator.analysis.fleet_support import FleetSelection, FleetSupportConstraints, SupportFocus, fleet_support_request_from_payload, fleet_support_request_to_payload, parse_fleet_selections
from starsector_variant_generator.analysis.scenario_advisor import ScenarioCapabilityTarget, generic_scenario_profiles, scenario_advisor_request_from_payload, scenario_advisor_request_to_payload, user_defined_scenario
from starsector_variant_generator.core.config import DEFAULT_HEURISTIC_SET, AppConfig
from starsector_variant_generator.core.mod_import import ModImportResult, resolve_dropped_mod
from starsector_variant_generator.core.models import Hull, Variant
from starsector_variant_generator.gui.canvas import MOUNT_TYPE_COLORS, TechnicalCanvas, _detect_mirror_mount_pairs, _displayable_weapon_mounts
from starsector_variant_generator.gui.helpers import _looks_like_starsector_install
from starsector_variant_generator.gui.models import EntityTableModel
from starsector_variant_generator.gui.presentation import format_fleet_support_comparison, format_fleet_support_result, format_fleet_support_why_not, format_generation_results, format_scenario_fleet_assessment
from starsector_variant_generator.gui.session import HullCatalog
from starsector_variant_generator.gui.workers.analysis_worker import AnalysisWorker
from starsector_variant_generator.gui.workers.scan_worker import ScanWorker
from starsector_variant_generator.profiles.catalog import available_profiles

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
_SCAN_STALL_WARNING_INTERVAL_S = 20.0


class MainWindow(QMainWindow):
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
        tabs = QTabWidget()
        self.workspace_tabs = tabs
        for widget, title in ((self._ships(), "Ships"), (self._retrofits(), "Retrofits"), (self._faction(), "Faction"), (self._data(), "Data / Analysis"), (self._settings(), "Settings / Export")):
            tabs.addTab(widget, title)
        tabs.currentChanged.connect(self._workspace_changed)
        return tabs

    def _ships(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); tabs = QTabWidget()
        self.ship_tabs = tabs
        tabs.addTab(self._browse(), "Browse / Fit")
        self.inspect_detail = QPlainTextEdit(); self.inspect_detail.setReadOnly(True); self.inspect_detail.setPlainText("Select a hull in Browse / Fit.")
        tabs.addTab(self.inspect_detail, "Inspect")
        self.compare_detail = QPlainTextEdit(); self.compare_detail.setReadOnly(True); self.compare_detail.setPlainText("Generated candidates appear here.")
        tabs.addTab(self.compare_detail, "Compare"); layout.addWidget(tabs); return page

    def _browse(self) -> QWidget:
        # Center panel favored: weapon slots are selected directly on the
        # rendered hull, and Generation Controls/Generated Build Paths now
        # live in the inspector's own "Generate" tab rather than stacked
        # below the canvas, so the canvas gets the majority of the space.
        split = QSplitter(Qt.Horizontal); split.addWidget(self._browser()); split.addWidget(self._center()); split.addWidget(self._inspector()); split.setSizes([250, 1150, 260]); return split

    def _browser(self) -> QWidget:
        panel = QFrame(); panel.setObjectName("panel"); layout = QVBoxLayout(panel); group = QGroupBox("HULL BROWSER & FILTERS"); filters = QVBoxLayout(group)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search scanned hulls…"); self.search.textChanged.connect(self._schedule_hull_refresh); filters.addWidget(self.search)
        self.size_filter, self.source_filter, self.faction_filter = QComboBox(), QComboBox(), QComboBox()
        for label, box in (("HULL SIZE", self.size_filter), ("SOURCE MOD", self.source_filter), ("FACTION", self.faction_filter)):
            filters.addWidget(QLabel(label)); filters.addWidget(box); box.currentIndexChanged.connect(self._refresh_hulls)
        reset = QPushButton("Reset Filters"); reset.clicked.connect(self._reset_filters); filters.addWidget(reset); layout.addWidget(group)
        self.count = QLabel("HULLS (scan required)"); layout.addWidget(self.count)
        self.hull_list = QListWidget(); self.hull_list.addItem("Scan an installation to populate hulls"); self.hull_list.currentRowChanged.connect(self._selected_hull); layout.addWidget(self.hull_list, 1)
        return panel

    def _center(self) -> QWidget:
        # Generation Controls and Generated Build Paths moved to the
        # inspector's "Generate" tab (see _inspector) so this panel is
        # dedicated to the ship canvas -- previously those two groups took
        # up most of this panel's vertical space, squeezing the canvas (and
        # its now-clickable mount boxes) into a comparatively tiny strip;
        # confirmed directly against a real user screenshot.
        panel = QFrame(); panel.setObjectName("panel"); layout = QVBoxLayout(panel)
        self.heading = QLabel("No hull selected"); self.heading.setObjectName("heading"); self.subheading = QLabel("Scan an installation to begin"); self.subheading.setObjectName("muted")
        layout.addWidget(self.heading); layout.addWidget(self.subheading); self.canvas = TechnicalCanvas(); self.canvas.slot_clicked.connect(self._choose_slot); layout.addWidget(self.canvas, 1)
        canvas_controls = QHBoxLayout()
        zoom_in, zoom_out, fit_view = QPushButton("Zoom +"), QPushButton("Zoom −"), QPushButton("Fit View")
        zoom_in.clicked.connect(self.canvas.zoom_in); zoom_out.clicked.connect(self.canvas.zoom_out); fit_view.clicked.connect(self.canvas.reset_view)
        canvas_controls.addWidget(zoom_in); canvas_controls.addWidget(zoom_out); canvas_controls.addWidget(fit_view); canvas_controls.addStretch()
        layout.addLayout(canvas_controls)
        legend = QHBoxLayout()
        for mount_type, hex_color in MOUNT_TYPE_COLORS.items():
            swatch = QLabel(); swatch.setFixedSize(10, 10); swatch.setStyleSheet(f"background-color: {hex_color}; border-radius: 2px;")
            legend.addWidget(swatch); legend.addWidget(QLabel(mount_type.title()))
        legend.addStretch(); layout.addLayout(legend)
        return panel

    def _inspector_tab(self) -> QWidget:
        panel = QWidget(); layout = QVBoxLayout(panel); group = QGroupBox("BUILD INSPECTOR"); box = QVBoxLayout(group); self.values: dict[str, QLabel] = {}
        for key in ("Hull Size", "Source Mod", "OP", "Weapon Mounts", "Built-ins"):
            row = QHBoxLayout(); row.addWidget(QLabel(key)); value = QLabel("—"); value.setObjectName("muted"); row.addWidget(value); box.addLayout(row); self.values[key] = value
        layout.addWidget(group)
        self.fit_metrics = QLabel("FIT STATUS: select a hull"); self.fit_metrics.setObjectName("muted"); self.fit_metrics.setWordWrap(True); layout.addWidget(self.fit_metrics)
        self.slot_include_hidden = QCheckBox("Show hidden / restricted equipment"); self.slot_include_hidden.setToolTip("Only availability explicitly marked in local scanned data is hidden."); layout.addWidget(self.slot_include_hidden)
        self.mirror_fitting = QCheckBox("Mirror fitting"); self.mirror_fitting.setToolTip("No hull selected yet."); self.mirror_fitting.setEnabled(False); layout.addWidget(self.mirror_fitting)
        layout.addStretch(1)
        self.add_to_fleet_support_button = QPushButton("Add to Fleet Support"); self.add_to_fleet_support_button.setEnabled(False); self.add_to_fleet_support_button.setToolTip("Adds the currently inspected hull as a locked Fleet Support Advisor selection."); self.add_to_fleet_support_button.clicked.connect(self._add_current_hull_to_fleet_support); layout.addWidget(self.add_to_fleet_support_button)
        self.save_editable_fit_button = QPushButton("Save Fit to Editable Library"); self.save_editable_fit_button.setEnabled(False); self.save_editable_fit_button.setToolTip("Saves this legal canvas fit only under the configured output directory."); self.save_editable_fit_button.clicked.connect(self._save_current_fit_to_library); layout.addWidget(self.save_editable_fit_button)
        self.generate_button = QPushButton("Generate Best"); self.generate_button.setObjectName("primary"); self.generate_button.setEnabled(False); self.generate_button.clicked.connect(self._generate); layout.addWidget(self.generate_button)
        return panel

    def _generate_tab(self) -> QWidget:
        panel = QWidget(); layout = QVBoxLayout(panel)
        controls = QGroupBox("GENERATION CONTROLS"); form = QFormLayout(controls)
        self.mode_selector = QComboBox()
        for label, value in (("Beginner", "beginner"), ("Guided", "guided"), ("Advanced / Manual", "advanced")):
            self.mode_selector.addItem(label, value)
        self.profile_selector = QComboBox(); self.profile_selector.addItem("Auto: viable build archetypes", None)
        for profile in available_profiles(): self.profile_selector.addItem(profile.display_name, profile.identifier)
        self.flux_selector = QComboBox()
        for value in ("SAFE", "BALANCED", "AGGRESSIVE"): self.flux_selector.addItem(value.title(), value)
        self.faction_mode_selector = QComboBox()
        for label, value in (("Strict Faction", "STRICT_FACTION"), ("Faction+", "FACTION_PLUS"), ("Unrestricted", "UNRESTRICTED")):
            self.faction_mode_selector.addItem(label, value)
        self.generation_faction_selector = QComboBox(); self.generation_faction_selector.addItem("No faction selected", None)
        self.max_candidates = QSpinBox(); self.max_candidates.setRange(1, 20); self.max_candidates.setValue(5)
        self.search_depth = QSpinBox(); self.search_depth.setRange(1, 10); self.search_depth.setValue(1)
        self.advanced_config = QLineEdit(); self.advanced_config.setPlaceholderText("Optional implemented advanced-request JSON")
        pick_advanced = QPushButton("Choose…"); pick_advanced.clicked.connect(self._choose_advanced_config)
        advanced_row = QWidget(); advanced_layout = QHBoxLayout(advanced_row); advanced_layout.setContentsMargins(0, 0, 0, 0); advanced_layout.addWidget(self.advanced_config, 1); advanced_layout.addWidget(pick_advanced)
        for label, widget in (("Mode", self.mode_selector), ("Profile", self.profile_selector), ("Flux posture", self.flux_selector), ("Equipment access", self.faction_mode_selector), ("Faction", self.generation_faction_selector), ("Candidate limit", self.max_candidates), ("Search depth", self.search_depth), ("Advanced request", advanced_row)):
            form.addRow(label, widget)
        layout.addWidget(controls)
        group = QGroupBox("GENERATED BUILD PATHS"); box = QVBoxLayout(group)
        self.candidate_cards = QListWidget(); self.candidate_cards.addItem("Select a hull and choose Generate Best."); self.candidate_cards.currentRowChanged.connect(self._preview_candidate); box.addWidget(self.candidate_cards)
        self.build_results = QPlainTextEdit(); self.build_results.setReadOnly(True); self.build_results.setMaximumHeight(105); self.build_results.setPlainText("Backend score and evidence for the selected candidate appear here."); box.addWidget(self.build_results)
        self.open_advanced_button = QPushButton("Open Selected in Advanced"); self.open_advanced_button.setEnabled(False); self.open_advanced_button.clicked.connect(self._open_selected_in_advanced); box.addWidget(self.open_advanced_button)
        self._generated_candidates: list[dict[str, Any]] = []; layout.addWidget(group, 1)
        return panel

    def _inspector(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._inspector_tab(), "Inspector")
        tabs.addTab(self._generate_tab(), "Generate")
        return tabs

    def _retrofits(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.addWidget(QLabel("REFIT / REPAIR ASSISTANT")); self.variant_list = QListWidget(); self.variant_list.addItem("Scan an installation to load existing variants"); self.variant_list.itemDoubleClicked.connect(self._open_variant_hull); layout.addWidget(self.variant_list, 1)
        library_group = QGroupBox("LOCAL EDITABLE RETROFIT LIBRARY"); library_layout = QVBoxLayout(library_group); self.editable_retrofit_list = QListWidget(); self.editable_retrofit_list.addItem("Choose an output directory, then refresh local editable copies."); self.editable_retrofit_list.itemDoubleClicked.connect(self._open_editable_retrofit_item); refresh_library = QPushButton("Refresh Editable Library"); refresh_library.clicked.connect(self._refresh_editable_retrofit_library); publish_editable = QPushButton("Publish Selected as Compatibility Mod"); publish_editable.clicked.connect(self._publish_editable_retrofit); show_history = QPushButton("Show Selected Replacement History"); show_history.clicked.connect(self._show_editable_retrofit_history); restore_history = QPushButton("Restore History Version…"); restore_history.clicked.connect(self._restore_editable_retrofit_history); library_layout.addWidget(self.editable_retrofit_list); library_layout.addWidget(refresh_library); library_layout.addWidget(publish_editable); library_layout.addWidget(show_history); library_layout.addWidget(restore_history); layout.addWidget(library_group)
        controls = QHBoxLayout(); self.fix_button = QPushButton("Suggest Legality Fix"); self.improve_button = QPushButton("Improve Variant"); self.compare_refit_button = QPushButton("Compare Before / After"); self.apply_refit_result_button = QPushButton("Load Last Refit Result"); self.copy_retrofit_button = QPushButton("Copy to Editable Library"); self.load_editable_retrofit_button = QPushButton("Load Editable Copy…"); self.populate_retrofits_button = QPushButton("Populate Missing Variations")
        for button, slot in ((self.fix_button, self._fix_legality), (self.improve_button, self._improve_quality), (self.compare_refit_button, self._compare_refit)):
            button.setEnabled(False); button.clicked.connect(slot); controls.addWidget(button)
        self.apply_refit_result_button.setEnabled(False); self.apply_refit_result_button.clicked.connect(self._apply_last_refit_result); controls.addWidget(self.apply_refit_result_button)
        self.copy_retrofit_button.setEnabled(False); self.copy_retrofit_button.clicked.connect(self._copy_retrofit_to_library); controls.addWidget(self.copy_retrofit_button)
        self.load_editable_retrofit_button.setEnabled(False); self.load_editable_retrofit_button.clicked.connect(self._load_editable_retrofit); controls.addWidget(self.load_editable_retrofit_button)
        self.populate_retrofits_button.setEnabled(False); self.populate_retrofits_button.clicked.connect(self._populate_missing_retrofits); controls.addWidget(self.populate_retrofits_button)
        layout.addLayout(controls)
        options = QGroupBox("REFIT CONTROLS"); form = QFormLayout(options)
        self.refit_mode_selector = QComboBox()
        for label, value in (("Balanced Improvement", "BALANCED_IMPROVEMENT"), ("Reduce Flux", "REDUCE_FLUX"), ("Improve Role Match", "IMPROVE_ROLE_MATCH"), ("Improve Logistics", "IMPROVE_LOGISTICS")):
            self.refit_mode_selector.addItem(label, value)
        self.refit_profile_selector = QComboBox()
        for profile in available_profiles(): self.refit_profile_selector.addItem(profile.display_name, profile.identifier)
        self.refit_substitution_selector = QComboBox()
        for label, value in (("Cheapest", "cheapest"), ("Exact", "exact"), ("Starsector Style", "starsector_style"), ("Adaptive", "adaptive")):
            self.refit_substitution_selector.addItem(label, value)
        self.refit_locked_mounts, self.refit_locked_hullmods, self.refit_locked_wings = QLineEdit(), QLineEdit(), QLineEdit()
        for widget in (self.refit_locked_mounts, self.refit_locked_hullmods, self.refit_locked_wings): widget.setPlaceholderText("Comma-separated IDs; optional")
        self.editable_hullmods, self.editable_wings = QLineEdit(), QLineEdit()
        self.editable_vents, self.editable_capacitors = QLineEdit(), QLineEdit()
        self.editable_hullmods.setPlaceholderText("Comma-separated IDs; saved with editable fit")
        self.editable_wings.setPlaceholderText("Comma-separated IDs; saved with editable fit")
        self.editable_vents.setPlaceholderText("Blank preserves loaded value; otherwise non-negative integer")
        self.editable_capacitors.setPlaceholderText("Blank preserves loaded value; otherwise non-negative integer")
        for field in (self.editable_hullmods, self.editable_wings, self.editable_vents, self.editable_capacitors): field.textChanged.connect(self._update_fit_metrics)
        self.video_review_path = QLineEdit(str(self._preferences.value("paths/video_review_transcript", "")))
        self.video_review_path.setPlaceholderText("Optional local VIDEO_REVIEW_TRANSCRIPT JSON")
        choose_video_review = QPushButton("Choose…"); choose_video_review.clicked.connect(self._choose_video_review)
        video_review_row = QWidget(); video_review_layout = QHBoxLayout(video_review_row); video_review_layout.setContentsMargins(0, 0, 0, 0); video_review_layout.addWidget(self.video_review_path, 1); video_review_layout.addWidget(choose_video_review)
        for label, widget in (("Quality mode", self.refit_mode_selector), ("Target profile", self.refit_profile_selector), ("Legality substitution", self.refit_substitution_selector), ("Locked mounts", self.refit_locked_mounts), ("Locked hullmods", self.refit_locked_hullmods), ("Locked fighter wings", self.refit_locked_wings), ("Editable hullmods", self.editable_hullmods), ("Editable fighter wings", self.editable_wings), ("Editable flux vents", self.editable_vents), ("Editable flux capacitors", self.editable_capacitors), ("Video review evidence", video_review_row)):
            form.addRow(label, widget)
        layout.addWidget(options); self.refit_detail = QPlainTextEdit(); self.refit_detail.setReadOnly(True); self.refit_detail.setPlainText("Choose a scanned variant. Suggestions preserve backend legality and selected locks."); layout.addWidget(self.refit_detail, 1); return page

    def _faction(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.addWidget(QLabel("FACTION CAPABILITY & RECOMMENDATIONS")); self.faction_list = QListWidget(); self.faction_list.addItem("Scan an installation to load factions"); self.faction_list.currentRowChanged.connect(self._faction_selected); layout.addWidget(self.faction_list, 1)
        pack_group = QGroupBox("OPTIONAL FACTION KNOWLEDGE PACK"); pack_form = QFormLayout(pack_group)
        self.knowledge_pack_path = QLineEdit(str(self._preferences.value("paths/knowledge_pack", ""))); self.knowledge_pack_path.setPlaceholderText("Optional local faction-pack JSON")
        choose_pack = QPushButton("Choose…"); choose_pack.clicked.connect(self._choose_knowledge_pack)
        pack_row = QWidget(); pack_layout = QHBoxLayout(pack_row); pack_layout.setContentsMargins(0, 0, 0, 0); pack_layout.addWidget(self.knowledge_pack_path, 1); pack_layout.addWidget(choose_pack)
        pack_form.addRow("Pack", pack_row); layout.addWidget(pack_group)
        controls = QHBoxLayout(); self.capability_button = QPushButton("Analyze Capability"); self.recommend_button = QPushButton("Find Gap Recommendations")
        for button, slot in ((self.capability_button, self._analyze_capability), (self.recommend_button, self._gap_recommendations)):
            button.setEnabled(False); button.clicked.connect(slot); controls.addWidget(button)
        layout.addLayout(controls)
        support_group = QGroupBox("FLEET SUPPORT ADVISOR — LOCKED SHIPS")
        support_form = QFormLayout(support_group)
        self.fleet_support_hulls = QLineEdit(); self.fleet_support_hulls.setPlaceholderText("Comma-separated hull IDs; repeat an ID for another selected ship")
        self.fleet_support_focus = QComboBox()
        for focus in SupportFocus: self.fleet_support_focus.addItem(focus.value.replace("_", " ").title(), focus.value)
        self.fleet_support_access = QComboBox()
        for label, value in (("Strict Faction", "STRICT_FACTION"), ("Faction+", "FACTION_PLUS"), ("Unrestricted", "UNRESTRICTED")): self.fleet_support_access.addItem(label, value)
        self.fleet_support_allow_foreign = QCheckBox("Allow foreign hulls"); self.fleet_support_allow_foreign.setChecked(True)
        self.fleet_support_include_hidden = QCheckBox("Include hidden / secret hulls")
        self.fleet_support_heuristic = QComboBox()
        self.fleet_support_heuristic.addItem("Baseline 0.12", "baseline_0.12")
        self.fleet_support_heuristic.addItem("Baseline 0.13 (diverse)", "baseline_0.13")
        self.fleet_support_heuristic.addItem("Baseline 0.14 (composition synergy)", "baseline_0.14")
        self.fleet_support_candidate = QLineEdit(); self.fleet_support_candidate.setPlaceholderText("Optional hull ID to explain")
        self.fleet_support_button = QPushButton("Advise Additions"); self.fleet_support_button.setEnabled(False); self.fleet_support_button.clicked.connect(self._fleet_support)
        self.fleet_support_why_not_button = QPushButton("Why Not?"); self.fleet_support_why_not_button.setEnabled(False); self.fleet_support_why_not_button.clicked.connect(self._fleet_support_why_not)
        self.generate_support_fit_button = QPushButton("Generate Support Fit"); self.generate_support_fit_button.setEnabled(False); self.generate_support_fit_button.setToolTip("Revalidates the selected recommendation, then runs the normal bounded fit generator. Logistics-only purposes remain unavailable until modeled."); self.generate_support_fit_button.clicked.connect(self._generate_support_fit)
        self.clear_fleet_support_button = QPushButton("Clear"); self.clear_fleet_support_button.clicked.connect(self._clear_fleet_support)
        self.save_fleet_support_button = QPushButton("Save Request…"); self.save_fleet_support_button.clicked.connect(self._save_fleet_support_request)
        self.load_fleet_support_button = QPushButton("Load Request…"); self.load_fleet_support_button.clicked.connect(self._load_fleet_support_request)
        self.compare_fleet_support_button = QPushButton("Compare Selected"); self.compare_fleet_support_button.clicked.connect(self._compare_fleet_support_cards)
        support_buttons = QWidget(); support_buttons_layout = QHBoxLayout(support_buttons); support_buttons_layout.setContentsMargins(0, 0, 0, 0); support_buttons_layout.addWidget(self.fleet_support_button); support_buttons_layout.addWidget(self.fleet_support_why_not_button); support_buttons_layout.addWidget(self.generate_support_fit_button); support_buttons_layout.addWidget(self.compare_fleet_support_button); support_buttons_layout.addWidget(self.save_fleet_support_button); support_buttons_layout.addWidget(self.load_fleet_support_button); support_buttons_layout.addWidget(self.clear_fleet_support_button)
        support_form.addRow("Keep / lock", self.fleet_support_hulls); support_form.addRow("Focus", self.fleet_support_focus); support_form.addRow("Access", self.fleet_support_access); support_form.addRow("Heuristics", self.fleet_support_heuristic); support_form.addRow("Availability", self.fleet_support_allow_foreign); support_form.addRow("Visibility", self.fleet_support_include_hidden); support_form.addRow("Candidate", self.fleet_support_candidate); support_form.addRow(support_buttons)
        scenario_group = QGroupBox("SCENARIO / MISSION ADVISOR — LOCKED SHIPS"); scenario_form = QFormLayout(scenario_group)
        self.scenario_profile = QComboBox()
        for profile in generic_scenario_profiles(): self.scenario_profile.addItem(profile.display_name, profile.scenario_id)
        self.scenario_profile.addItem("Custom declared targets", "CUSTOM")
        self.scenario_targets = QLineEdit(); self.scenario_targets.setPlaceholderText("Custom only: CAPABILITY=0.70, CAPABILITY=0.55")
        self.scenario_evaluate_button = QPushButton("Evaluate Scenario"); self.scenario_evaluate_button.setEnabled(False); self.scenario_evaluate_button.clicked.connect(self._evaluate_scenario)
        self.generate_scenario_fit_button = QPushButton("Generate Scenario Fit"); self.generate_scenario_fit_button.setEnabled(False); self.generate_scenario_fit_button.setToolTip("Revalidates a current scenario recommendation against the declared targets, then runs the normal bounded generator."); self.generate_scenario_fit_button.clicked.connect(self._generate_scenario_fit)
        self.save_scenario_button = QPushButton("Save Request…"); self.save_scenario_button.clicked.connect(self._save_scenario_request)
        self.load_scenario_button = QPushButton("Load Request…"); self.load_scenario_button.clicked.connect(self._load_scenario_request)
        scenario_buttons = QWidget(); scenario_buttons_layout = QHBoxLayout(scenario_buttons); scenario_buttons_layout.setContentsMargins(0, 0, 0, 0); scenario_buttons_layout.addWidget(self.scenario_evaluate_button); scenario_buttons_layout.addWidget(self.generate_scenario_fit_button); scenario_buttons_layout.addWidget(self.save_scenario_button); scenario_buttons_layout.addWidget(self.load_scenario_button)
        scenario_form.addRow("Scenario", self.scenario_profile); scenario_form.addRow("Targets", self.scenario_targets); scenario_form.addRow(scenario_buttons)
        layout.addWidget(support_group); layout.addWidget(scenario_group); self.fleet_support_cards = QListWidget(); self.fleet_support_cards.setSelectionMode(QAbstractItemView.ExtendedSelection); self.fleet_support_cards.addItem("Run Fleet Support Advisor to populate recommendation cards."); self.fleet_support_cards.currentRowChanged.connect(self._fleet_support_card_selected); layout.addWidget(self.fleet_support_cards, 1); self.faction_detail = QPlainTextEdit(); self.faction_detail.setReadOnly(True); self.faction_detail.setPlainText("Select a faction after scanning, or enter locked hull IDs for support advice."); layout.addWidget(self.faction_detail, 2); return page

    def _data(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); split = QSplitter(Qt.Horizontal); tabs = QTabWidget(); self.data_tables: dict[str, QTableView] = {}; self._data_entities: dict[str, list[Any]] = {}
        for title, headers in (("Weapons", ["Name", "Size", "Type", "Source Mod"]), ("Hullmods", ["Name", "Hidden", "Source Mod"]), ("Fighters", ["Name", "Role", "Source Mod"]), ("Variants", ["Name", "Hull", "Source Mod"])):
            table = QTableView(); table.setModel(EntityTableModel(headers, table)); table.setEditTriggers(QTableView.NoEditTriggers); table.selectionModel().selectionChanged.connect(lambda _selected, _deselected, title=title: self._show_provenance(title)); tabs.addTab(table, title); self.data_tables[title] = table
        self.provenance_detail = QPlainTextEdit(); self.provenance_detail.setReadOnly(True); self.provenance_detail.setPlainText("Select a normalized record to inspect local source provenance.")
        provenance_group = QGroupBox("PROVENANCE"); provenance_layout = QVBoxLayout(provenance_group); provenance_layout.addWidget(self.provenance_detail)
        split.addWidget(tabs); split.addWidget(provenance_group); split.setSizes([860, 360]); layout.addWidget(split); return page

    def _settings(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); group = QGroupBox("INSTALLATION, SCAN & EXPORT"); box = QVBoxLayout(group)
        self.root = QLineEdit(str(self._preferences.value("paths/starsector", ""))); self.root.setPlaceholderText("Select Starsector installation folder")
        choose = QPushButton("Choose Installation…"); choose.clicked.connect(self._choose_installation); self.output = QLineEdit(str(self._preferences.value("paths/output", (Path.cwd() / "generated" / "gui").resolve())))
        self.include_disabled_mods = QCheckBox("Include installed-but-disabled mods")
        self.include_disabled_mods.setToolTip(
            "Off (default): scan only core plus mods listed as enabled in Starsector's own mods\\enabled_mods.json, "
            "matching what actually loads in-game. On: also scan every mod physically present under mods\\ even if "
            "disabled there -- a disabled mod's hulls/factions/weapons are otherwise completely absent, which can "
            "look like a scanning bug (e.g. a faction patch mod that's enabled shows its own additions, but the "
            "base faction mod it patches is invisible if that one is disabled)."
        )
        self.include_disabled_mods.setChecked(bool(self._preferences.value("scan/include_disabled_mods", False, type=bool)))
        self.scan_button = QPushButton("Scan Installed Data"); self.scan_button.setObjectName("primary"); self.scan_button.clicked.connect(self._start_scan)
        self.cancel_scan_button = QPushButton("Cancel Scan"); self.cancel_scan_button.setEnabled(False); self.cancel_scan_button.clicked.connect(self._discard_scan)
        self.export_button = QPushButton("Export Current Hull (conservative)"); self.export_button.setEnabled(False); self.export_button.clicked.connect(self._export_current)
        for label, widget in (("STARSECTOR PATH", self.root), ("", choose), ("SAFE OUTPUT DIRECTORY", self.output), ("", self.include_disabled_mods), ("", self.scan_button), ("", self.cancel_scan_button), ("", self.export_button)):
            if label: box.addWidget(QLabel(label))
            box.addWidget(widget)
        layout.addWidget(group)
        mods_group = QGroupBox("ADDITIONAL MODS (drag && drop)"); mods_layout = QVBoxLayout(mods_group)
        mods_layout.addWidget(QLabel("Drag a mod folder or .zip archive anywhere onto this window to add it to the next scan — it does not need to be installed under the Starsector installation's mods folder."))
        self.extra_mods_list = QListWidget(); self.extra_mods_list.addItem("No additional mods added."); mods_layout.addWidget(self.extra_mods_list, 1)
        remove_extra_mod = QPushButton("Remove Selected"); remove_extra_mod.clicked.connect(self._remove_selected_extra_mod); mods_layout.addWidget(remove_extra_mod)
        layout.addWidget(mods_group)
        summary_group = QGroupBox("LATEST LOCAL SCAN / REPORT STATUS"); summary_layout = QVBoxLayout(summary_group)
        self.scan_summary = QPlainTextEdit(); self.scan_summary.setReadOnly(True); self.scan_summary.setMaximumHeight(150)
        self.scan_summary.setPlainText("No local scan has been loaded. Source files are read-only; reports are written only under the configured output directory.")
        summary_layout.addWidget(self.scan_summary); layout.addWidget(summary_group); layout.addStretch(); return page

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
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

    def _incorporate_dropped_mods(self, newly_added: list[ModImportResult]) -> None:
        config, existing_result = self._config, self._scan_result
        mod_roots = tuple(mod.mod_root for mod in newly_added)
        operation = lambda: api.run_incremental_mod_scan(config, existing_result, mod_roots)  # noqa: E731
        self._run(f"Incorporating {len(newly_added)} dropped mod(s)…", operation, self._apply_incremental_scan_outcome, self.scan_button)

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

    def _refresh_extra_mods_list(self) -> None:
        self.extra_mods_list.clear()
        if not self._extra_mods:
            self.extra_mods_list.addItem("No additional mods added.")
            return
        for mod in self._extra_mods:
            item = QListWidgetItem(f"{mod.mod_name or mod.mod_id} [{mod.mod_id}]\n{mod.mod_root}")
            item.setData(Qt.UserRole, mod.mod_root)
            self.extra_mods_list.addItem(item)

    def _remove_selected_extra_mod(self) -> None:
        item = self.extra_mods_list.currentItem()
        if item is None:
            return
        target = item.data(Qt.UserRole)
        if target is None:
            return
        self._extra_mods = [mod for mod in self._extra_mods if mod.mod_root != target]
        self._refresh_extra_mods_list()
        self.statusBar().showMessage("Removed from the next scan's additional mods. Rescan to apply.")

    def _choose_installation(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Starsector installation")
        if path: self.root.setText(path)

    def _choose_advanced_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select advanced generation request", filter="JSON files (*.json)")
        if path: self.advanced_config.setText(path)

    def _start_scan(self) -> None:
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
        self._config = AppConfig(root, output, output / "logs", extra_mod_paths=tuple(mod.mod_root for mod in self._extra_mods), include_disabled_mods=self.include_disabled_mods.isChecked())
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

    def _scan_progressed(self, progress: Any) -> None:
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

    def _scan_complete(self, outcome: Any) -> None:
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
        self._refresh_hulls(); self._populate_secondary()
        extra_note = f"Additional dropped mod(s) included: {', '.join(mod.mod_id or mod.mod_name or '?' for mod in self._extra_mods)}." if self._extra_mods else ""
        self.scan_summary.setPlainText("\n".join(line for line in (
            f"Loaded: {len(outcome.result.hulls)} hulls, {len(outcome.result.weapons)} weapons, {len(outcome.result.hullmods)} hullmods, {len(outcome.result.variants)} variants.",
            f"Diagnostics: {len(outcome.result.warnings)} warnings, {len(outcome.result.errors)} source errors, {len(outcome.result.skipped_entities)} skipped records.",
            self._scan_metrics_summary(outcome.result),
            extra_note,
            "Source data was read-only. Inspect Data / Analysis for entity provenance; local reports are under the configured output directory.",
        ) if line))
        self.statusBar().showMessage(f"Scan complete: {len(outcome.result.hulls)} hulls, {len(outcome.result.errors)} source errors.")

    @staticmethod
    def _scan_metrics_summary(result: Any) -> str:
        metrics = getattr(result, "scan_metrics", None)
        if metrics is None:
            return "Scan timing unavailable."
        total = getattr(metrics, "stage_seconds", {}).get("total", 0.0)
        return f"Performance: {getattr(metrics, 'sources_scanned', 0)} sources, {getattr(metrics, 'files_hashed', 0)} relevant files hashed, {total:.2f}s total."

    def _discard_scan(self) -> None:
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

    def _scan_finished(self) -> None:
        self._scan_watchdog.stop()
        self.scan_button.setEnabled(True); self.cancel_scan_button.setEnabled(False); self._scan_thread = None; self._scan_cancel_event = None; self._scan_worker = None
        if self._scan_progress is not None: self._scan_progress.close(); self._scan_progress.deleteLater(); self._scan_progress = None
        if self._scan_discarded: self.statusBar().showMessage("Scan cancelled.")
        self._maybe_close_after_background_work()

    def _check_scan_stall(self) -> None:
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

    def _workspace_changed(self, index: int) -> None:
        # Table rows stay in compact model storage rather than allocating one
        # widget item per cell. Materialization is still deferred until Data /
        # Analysis is opened; normalized backend indexes are already available.
        if index == 3 and self._data_tables_pending:
            self._populate_data_tables()

    def _populate_secondary(self) -> None:
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
        for button in (self.fix_button, self.improve_button, self.compare_refit_button, self.copy_retrofit_button, self.load_editable_retrofit_button, self.populate_retrofits_button, self.capability_button, self.recommend_button, self.fleet_support_button, self.fleet_support_why_not_button, self.scenario_evaluate_button, self.export_button): button.setEnabled(True)

    def _populate_data_tables(self) -> None:
        if not self._data_tables_pending:
            return
        entity_records = self._data_entities
        records: dict[str, list[tuple[str, ...]]] = {"Weapons": [(x.name, x.size or "Unknown", x.mount_type or "Unknown", x.source_mod) for x in entity_records["Weapons"]], "Hullmods": [(x.name, "Yes" if x.hidden else "No", x.source_mod) for x in entity_records["Hullmods"]], "Fighters": [(x.name, x.role or "Unknown", x.source_mod) for x in entity_records["Fighters"]], "Variants": [(x.name, x.hull_id or "Unknown", x.source_mod) for x in entity_records["Variants"]]}
        for name, rows in records.items():
            model = self.data_tables[name].model()
            assert isinstance(model, EntityTableModel)
            model.set_records(rows, list(entity_records[name]))
        self._data_tables_pending = False

    def _refresh_hulls(self) -> None:
        if self._catalog is None: return
        self._visible = self._catalog.filter(self.search.text(), self.size_filter.currentData(), self.source_filter.currentData(), self.faction_filter.currentData()); self.hull_list.blockSignals(True); self.hull_list.clear()
        for hull in self._visible:
            # A real, blank hull.name is not unusual -- confirmed on a live
            # install: many modded composite-hull sub-modules (e.g. a boss
            # ship's individual turret pieces) genuinely declare no display
            # name at all, since they're never shown standalone in-game.
            # Falling back to the real hull id keeps every row distinguishable
            # instead of many identical "<size> • <source_mod>" rows.
            affiliations = ", ".join(self._catalog.faction_labels_for(hull)) or "No parsed faction"
            item = QListWidgetItem(f"{hull.name or hull.id}\n{hull.hull_size or 'Unknown'} • {hull.source_mod} • {affiliations}"); item.setData(Qt.UserRole, hull.id); self.hull_list.addItem(item)
        self.hull_list.blockSignals(False); self.count.setText(f"HULLS ({len(self._visible)})"); self.hull_list.setCurrentRow(0 if self._visible else -1)

    def _schedule_hull_refresh(self) -> None:
        """Avoid rebuilding a large hull list once per keystroke."""
        self._hull_filter_timer.start()

    def _reset_filters(self) -> None: self.search.clear(); self.size_filter.setCurrentIndex(0); self.source_filter.setCurrentIndex(0); self.faction_filter.setCurrentIndex(0)

    def _show_provenance(self, category: str) -> None:
        table = self.data_tables[category]; row = table.currentIndex().row()
        model = table.model()
        if not isinstance(model, EntityTableModel) or row < 0 or row >= len(model.entities): return
        entity = model.entities[row]
        lines = [
            f"ID: {entity.id}", f"Name: {entity.name}", f"Source mod: {entity.source_mod}",
            f"Source file: {entity.source_path}", f"Source hash: {entity.source_hash or 'Unavailable'}",
            f"Source mod version: {entity.source_mod_version or 'Unavailable'}",
        ]
        if category == "Variants":
            lines.append(f"Parent hull: {entity.hull_id or 'Unavailable'}")
            if isinstance(entity.raw.get("modules"), list) and entity.raw["modules"]:
                lines.append("Complex module mappings: retained as provenance only; not compositely analyzed.")
        self.provenance_detail.setPlainText("\n".join(lines))

    def _open_variant_hull(self, item: QListWidgetItem) -> None:
        if self._registry is None: return
        variant = self._registry.variants.by_id.get(str(item.data(Qt.UserRole)))
        if variant is not None:
            self._open_retrofit_variant(variant)

    def _open_retrofit_variant(self, variant: Variant) -> None:
        if self._registry is None:
            return
        hull = self._registry.hulls.by_id.get(variant.hull_id) if variant and variant.hull_id else None
        if hull is None:
            self.refit_detail.setPlainText("The variant parent hull is missing or ambiguous; it cannot be opened safely.")
            return
        self.workspace_tabs.setCurrentIndex(0); self.ship_tabs.setCurrentIndex(0)
        try: self.hull_list.setCurrentRow(self._visible.index(hull))
        except ValueError:
            self.search.clear(); self.size_filter.setCurrentIndex(0); self.source_filter.setCurrentIndex(0); self.faction_filter.setCurrentIndex(0); self._refresh_hulls(); self.hull_list.setCurrentRow(self._visible.index(hull))
        self._loaded_retrofit_variant = variant
        self._fit_weapons = {**hull.built_in_weapons, **variant.weapons_by_mount}
        self.editable_hullmods.setText(", ".join(variant.hullmods)); self.editable_wings.setText(", ".join(variant.fighter_wings))
        self.editable_vents.setText("" if variant.flux_vents is None else str(variant.flux_vents)); self.editable_capacitors.setText("" if variant.flux_capacitors is None else str(variant.flux_capacitors))
        self._update_fit_metrics(); self.canvas.show_hull(hull, self._fit_weapons, self._registry.weapons.by_id)
        self.inspect_detail.appendPlainText(f"\nEditing existing variant: {variant.id}\nSaving creates/replaces only a local editable copy.")

    def _selected_hull(self, row: int) -> None:
        if row < 0 or row >= len(self._visible): self.canvas.show_empty(); self.generate_button.setEnabled(False); self._mirror_pairs = {}; self.mirror_fitting.setEnabled(False); self.mirror_fitting.setChecked(False); self.mirror_fitting.setText("Mirror fitting"); self.mirror_fitting.setToolTip("No hull selected yet."); return
        hull = self._visible[row]; self._current_hull = hull; self._loaded_retrofit_variant = None; self._fit_weapons = dict(hull.built_in_weapons); self.editable_hullmods.clear(); self.editable_wings.clear(); self.editable_vents.clear(); self.editable_capacitors.clear(); self.heading.setText(hull.name or hull.id); self.subheading.setText(f"{hull.id} • {hull.source_mod}")
        data = {"Hull Size": hull.hull_size or "Unknown", "Source Mod": hull.source_mod, "OP": str(hull.ordnance_points or "Unknown"), "Weapon Mounts": str(len(_displayable_weapon_mounts(hull))), "Built-ins": str(len(hull.built_in_hullmods) + len(hull.built_in_weapons))}
        for key, value in data.items(): self.values[key].setText(value)
        self._mirror_pairs = _detect_mirror_mount_pairs(hull)
        pair_count = len(self._mirror_pairs) // 2
        self.mirror_fitting.setEnabled(pair_count > 0)
        if not pair_count: self.mirror_fitting.setChecked(False)
        self.mirror_fitting.setText(f"Mirror fitting ({pair_count} pair{'s' if pair_count != 1 else ''} detected)" if pair_count else "Mirror fitting (no symmetric pairs detected)")
        self.mirror_fitting.setToolTip("Assigning or clearing a weapon on one mount also applies it to its detected left/right mirror mount." if pair_count else "No left/right mirror-symmetric mount pairs were found in this hull's parsed geometry.")
        affiliations = ", ".join(self._catalog.faction_labels_for(hull)) if self._catalog is not None else ""
        self._update_fit_metrics(); self.canvas.show_hull(hull, self._fit_weapons, self._registry.weapons.by_id if self._registry is not None else None); self.inspect_detail.setPlainText(f"{hull.name} ({hull.id})\nSource: {hull.source_mod}\nFaction evidence: {affiliations or 'No parsed faction'}\nSelectable weapon mounts: {len(_displayable_weapon_mounts(hull))} | Launch bays: {len(hull.launch_bay_slots)} | OP: {hull.ordnance_points}"); self.generate_button.setEnabled(self._registry is not None); self.add_to_fleet_support_button.setEnabled(self._registry is not None); self.save_editable_fit_button.setEnabled(self._registry is not None)

    def _update_fit_metrics(self) -> None:
        if self._registry is None or self._current_hull is None: return
        try:
            fit = self._editable_canvas_variant(f"gui_{self._current_hull.id}", "GUI Fit")
        except ValueError as exc:
            self.fit_metrics.setText(f"FIT STATUS: INVALID EDITABLE FIELD\n{exc}")
            return
        summary = api.run_fit_summary(self._registry, fit)
        available = summary["hull_ordnance_points"] if summary["hull_ordnance_points"] is not None else "Unknown"
        text = f"FIT STATUS: {summary['legality']}\nWeapon OP {summary['weapon_op_used']}/{available}"
        if summary["weapon_op_remaining"] is not None: text += f" (remaining {summary['weapon_op_remaining']})"
        notes = [*summary["failures"], *summary["uncertainties"]]
        self.fit_metrics.setText(text + (f"\n{'; '.join(notes)}" if notes else ""))

    def _editable_canvas_variant(self, variant_id: str, name: str) -> Variant:
        if self._current_hull is None:
            raise ValueError("No hull selected.")
        loaded = self._loaded_retrofit_variant
        vents = self._editable_stat_value(self.editable_vents, loaded.flux_vents if loaded else None)
        capacitors = self._editable_stat_value(self.editable_capacitors, loaded.flux_capacitors if loaded else None)
        hullmods = tuple(item.strip() for item in self.editable_hullmods.text().split(",") if item.strip())
        wings = tuple(item.strip() for item in self.editable_wings.text().split(",") if item.strip())
        return Variant(variant_id, name, "USER_EDITABLE", self._current_hull.source_path, hull_id=self._current_hull.id, weapons_by_mount=dict(self._fit_weapons), hullmods=hullmods, fighter_wings=wings, flux_vents=vents, flux_capacitors=capacitors)

    def _save_current_fit_to_library(self) -> None:
        if self._registry is None or self._current_hull is None:
            return
        output = self.output.text().strip()
        if not output:
            QMessageBox.warning(self, "Output directory required", "Choose an output directory before saving an editable fit."); return
        default_id = self._loaded_retrofit_variant.id if self._loaded_retrofit_variant is not None else f"{self._current_hull.id}_custom"
        variant_id, accepted = QInputDialog.getText(self, "Save editable fit", "Variant ID", text=default_id)
        if not accepted or not variant_id.strip():
            return
        try:
            fit = self._editable_canvas_variant(variant_id.strip(), variant_id.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Fit not saved", str(exc)); return
        try:
            path = api.save_editable_retrofit_variant(self._registry, fit, Path(output), replace=False)
        except FileExistsError:
            if QMessageBox.question(self, "Replace editable fit?", "A local editable fit with this ID already exists. Replace it?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            path = api.save_editable_retrofit_variant(self._registry, fit, Path(output), replace=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Fit not saved", str(exc)); return
        self.statusBar().showMessage(f"Saved editable local fit: {path}")
        self._refresh_editable_retrofit_library()

    @staticmethod
    def _editable_stat_value(field: QLineEdit, fallback: int | None) -> int | None:
        text = field.text().strip()
        if not text:
            return fallback
        if not text.isdecimal():
            raise ValueError("Editable flux vents/capacitors must be non-negative integers.")
        return int(text)

    def _choose_slot(self, slot_id: str) -> None:
        if self._registry is None or self._current_hull is None: return
        faction_id = self.generation_faction_selector.currentData(); faction_mode = str(self.faction_mode_selector.currentData())
        if faction_mode == "STRICT_FACTION" and faction_id is None:
            QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction equipment access."); return
        # STRICT_FACTION filtering re-classifies every scanned weapon's
        # faction affinity against every scanned faction's known_* lists
        # (analysis/equipment_affinity.py) -- on a large real install this
        # is a real, non-instant computation, and unlike every other
        # backend call in this file it runs synchronously on the GUI
        # thread (a modal QInputDialog needs the result immediately
        # afterwards, so it can't go through the background-thread _run()
        # pattern without restructuring this into an async flow). A wait
        # cursor plus a status-bar message is the minimal, low-risk way to
        # signal "working" for that duration.
        self.statusBar().showMessage("Finding backend-eligible weapons for this mount…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            eligible = api.run_slot_eligible_weapons(self._registry, self._current_hull.id, slot_id, include_hidden=self.slot_include_hidden.isChecked(), faction_id=str(faction_id) if faction_id else None, faction_mode=faction_mode)
        except ValueError as exc:
            # Reachable when self._current_hull/slot data has gone stale
            # relative to self._registry -- e.g. an incremental dropped-mod
            # incorporation (see _apply_incremental_scan_outcome) made the
            # displayed hull ambiguous after it was selected but before this
            # slot was double-clicked. Previously unguarded: this raised a
            # bare ValueError straight out of a Qt slot instead of the
            # QMessageBox.critical every other backend call in this file
            # routes failures through.
            self._operation_failed(str(exc)); return
        finally:
            QApplication.restoreOverrideCursor()
        choices = ["<Empty>", *[f"{x.name} [{x.id}] — {x.source_mod}" for x in eligible]]; choice, accepted = QInputDialog.getItem(self, "Select legal weapon", slot_id, choices, 0, True)
        if not accepted: return
        mirror_id = self._mirror_pairs.get(slot_id) if self.mirror_fitting.isChecked() else None
        if mirror_id is not None and mirror_id in self._current_hull.built_in_weapons: mirror_id = None
        if choice == "<Empty>":
            self._fit_weapons.pop(slot_id, None)
            if mirror_id is not None: self._fit_weapons.pop(mirror_id, None)
        else:
            selected = next((weapon for weapon in eligible if f"{weapon.name} [{weapon.id}] — {weapon.source_mod}" == choice), None)
            if selected is None: QMessageBox.warning(self, "Invalid selection", "Choose an item from the backend-filtered list."); return
            self._fit_weapons[slot_id] = selected.id
            if mirror_id is not None: self._fit_weapons[mirror_id] = selected.id
        fit = Variant(f"gui_{self._current_hull.id}", "GUI Fit", "GENERATED", self._current_hull.source_path, hull_id=self._current_hull.id, weapons_by_mount=dict(self._fit_weapons)); assessment = api.run_validate_fit(self._registry, fit); details = "; ".join(x.message for x in (*assessment.failures, *assessment.uncertainties))
        self.statusBar().showMessage(f"{assessment.result}: {details or 'No legality findings.'}"); self._update_fit_metrics(); self.canvas.show_hull(self._current_hull, self._fit_weapons, self._registry.weapons.by_id); self.inspect_detail.appendPlainText(f"\nManual fit legality: {assessment.result}\n{details}")

    def _run(self, message: str, operation: Callable[[], Any], completed: Callable[[Any], None], control: QPushButton, *, cancellable: bool = False) -> None:
        # Backend tasks are immutable snapshots. Token-gating prevents a stale
        # result from replacing a newer UI request without unsafe cancellation.
        token = self._operation_tokens.get(control, 0) + 1; self._operation_tokens[control] = token
        thread = QThread(self); worker = AnalysisWorker(operation); worker.moveToThread(thread); thread.started.connect(worker.run)
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
            self.statusBar().showMessage("Stopped waiting for the scenario analysis; the read-only calculation will finish safely in the background.")
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
        self._threads.discard(thread); self._active_workers.pop(thread, None); control.setEnabled(self._registry is not None); thread.deleteLater()
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
        if self._registry is not None and self._current_hull is not None:
            if self._registry_write_in_progress():
                self.statusBar().showMessage("A scan or mod incorporation is still in progress; wait for it to finish before generating.")
                return
            hull_id = self._current_hull.id
            mode = str(self.mode_selector.currentData())
            profile = self.profile_selector.currentData()
            faction_mode = str(self.faction_mode_selector.currentData())
            faction_id = self.generation_faction_selector.currentData()
            flux_mode = str(self.flux_selector.currentData())
            max_candidates = self.max_candidates.value()
            search_depth = self.search_depth.value()
            config_text = self.advanced_config.text().strip()
            advanced_config = Path(config_text) if config_text else None
            if advanced_config is not None and not advanced_config.is_file():
                QMessageBox.warning(self, "Invalid advanced request", "Choose an existing JSON request file or clear the field.")
                return
            if advanced_config is not None and mode != "advanced":
                QMessageBox.warning(self, "Advanced request", "Select Advanced / Manual mode before applying an advanced request.")
                return
            if faction_mode == "STRICT_FACTION" and faction_id is None:
                QMessageBox.warning(self, "Faction required", "Select a faction before using Strict Faction equipment access.")
                return
            heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
            self._run(
                "Generating legal build candidates…",
                lambda: api.run_generate(
                    self._registry, heuristic_set, hull_id, mode, profile=profile, faction_id=str(faction_id) if faction_id else None,
                    faction_mode=faction_mode, advanced_config=advanced_config,
                    flux_mode=flux_mode, max_candidates=max_candidates, search_depth=search_depth,
                ),
                self._generation_complete, self.generate_button,
            )
    def _generation_complete(self, outcome: Any) -> None:
        text = format_generation_results(outcome.assessed_candidates, outcome.selected_profile, outcome.flux_mode)
        self._generated_candidates = list(outcome.assessed_candidates)
        self.candidate_cards.blockSignals(True); self.candidate_cards.clear()
        for index, candidate in enumerate(self._generated_candidates, 1):
            build = candidate.get("build_archetype", {})
            label = candidate.get("recommendation_label") or build.get("role") or "Candidate"
            score = candidate.get("build_recommendation_score", candidate.get("quality", {}).get("final_score"))
            confidence = build.get("confidence")
            item = QListWidgetItem(f"{index}. {label}\nScore: {score if score is not None else 'Unavailable'}   Confidence: {confidence if confidence is not None else 'Unavailable'}")
            item.setData(Qt.UserRole, index - 1); self.candidate_cards.addItem(item)
        self.candidate_cards.blockSignals(False)
        self.open_advanced_button.setEnabled(bool(self._generated_candidates))
        if self._generated_candidates: self.candidate_cards.setCurrentRow(0)
        else: self.build_results.setPlainText(text)
        self.compare_detail.setPlainText(text); self.statusBar().showMessage("Generation complete.")

    def _preview_candidate(self, row: int) -> None:
        if row < 0 or row >= len(self._generated_candidates): return
        candidate = self._generated_candidates[row]
        self.build_results.setPlainText(format_generation_results([candidate], "Selected candidate", "Backend supplied"))
        variant = candidate.get("variant", {})
        weapons = variant.get("weapons_by_mount")
        if self._current_hull is not None and isinstance(weapons, dict):
            self._fit_weapons = {str(mount): str(weapon) for mount, weapon in weapons.items()}
            self.canvas.show_hull(self._current_hull, self._fit_weapons, self._registry.weapons.by_id if self._registry is not None else None)

    def _open_selected_in_advanced(self) -> None:
        """Keep the selected backend result visible; never regenerate it here."""
        row = self.candidate_cards.currentRow()
        if row < 0 or row >= len(self._generated_candidates): return
        profile_id = self._generated_candidates[row].get("profile_id")
        if isinstance(profile_id, str):
            index = self.profile_selector.findData(profile_id)
            if index >= 0: self.profile_selector.setCurrentIndex(index)
        mode_index = self.mode_selector.findData("advanced")
        if mode_index >= 0: self.mode_selector.setCurrentIndex(mode_index)
        self.build_results.appendPlainText("Opened in Advanced controls without regenerating; the selected candidate remains on the fitting canvas.")
        self.statusBar().showMessage("Selected candidate preserved in Advanced / Manual controls.")

    def _variant_id(self) -> str | None:
        item = self.variant_list.currentItem(); return str(item.data(Qt.UserRole)) if item is not None else None
    def _refit(self, operation: Callable[[str], Any], button: QPushButton, message: str, on_result: Callable[[Any], None] | None = None) -> None:
        variant_id = self._variant_id()
        if self._registry is None or variant_id is None: self.refit_detail.setPlainText("Select an existing scanned variant first."); return
        if self._registry_write_in_progress(): self.refit_detail.setPlainText("A scan or mod incorporation is still in progress; wait for it to finish first."); return
        self._run(message, lambda: operation(variant_id), on_result or (lambda result: self.refit_detail.setPlainText(str(result))), button)

    def _show_refit_result(self, result: Any) -> None:
        self._last_refit_result = result
        self.apply_refit_result_button.setEnabled(hasattr(result, "refitted_variant"))
        self.refit_detail.setPlainText(str(result))

    def _apply_last_refit_result(self) -> None:
        result = getattr(self, "_last_refit_result", None)
        variant = getattr(result, "refitted_variant", None)
        if not isinstance(variant, Variant):
            self.refit_detail.setPlainText("Run a Refit Assistant operation that returns a variant first."); return
        self._open_retrofit_variant(dataclass_replace(variant, source_mod="USER_EDITABLE"))
        self.statusBar().showMessage("Loaded Refit Assistant result into the editable canvas; save to create a local working copy.")
    def _compare_refit(self) -> None:
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

    @staticmethod
    def _editable_change_summary(before: Variant, after: Variant) -> tuple[str, ...]:
        changes = []
        for mount in sorted(set(before.weapons_by_mount) | set(after.weapons_by_mount)):
            if before.weapons_by_mount.get(mount) != after.weapons_by_mount.get(mount):
                changes.append(f"mount {mount}: {before.weapons_by_mount.get(mount, '<empty>')} → {after.weapons_by_mount.get(mount, '<empty>')}")
        for label, old, new in (("hullmods", before.hullmods, after.hullmods), ("fighter wings", before.fighter_wings, after.fighter_wings), ("flux vents", before.flux_vents, after.flux_vents), ("flux capacitors", before.flux_capacitors, after.flux_capacitors)):
            if old != new: changes.append(f"{label}: {old!r} → {new!r}")
        return tuple(changes) or ("No editable differences from the loaded local copy.",)

    def _choose_video_review(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose video review transcript", self.video_review_path.text(), "JSON files (*.json)")
        if path:
            self.video_review_path.setText(path)
            self._preferences.setValue("paths/video_review_transcript", path)

    @staticmethod
    def _refit_lock_ids(field: QLineEdit) -> frozenset[str]:
        return frozenset(item.strip() for item in field.text().split(",") if item.strip())

    def _fix_legality(self) -> None:
        mounts, hullmods, wings = self._refit_lock_ids(self.refit_locked_mounts), self._refit_lock_ids(self.refit_locked_hullmods), self._refit_lock_ids(self.refit_locked_wings)
        mode = str(self.refit_substitution_selector.currentData())
        heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
        self._refit(lambda item: api.run_fix_legality(self._registry, item, heuristic_set, locked_mount_ids=mounts, locked_hullmod_ids=hullmods, locked_wing_ids=wings, substitution_mode=mode), self.fix_button, "Finding minimal legality fixes", self._show_refit_result)

    def _improve_quality(self) -> None:
        mounts, hullmods, wings = self._refit_lock_ids(self.refit_locked_mounts), self._refit_lock_ids(self.refit_locked_hullmods), self._refit_lock_ids(self.refit_locked_wings)
        mode, profile = str(self.refit_mode_selector.currentData()), str(self.refit_profile_selector.currentData())
        heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
        self._refit(lambda item: api.run_improve_quality(self._registry, item, mode, profile, heuristic_set, locked_mount_ids=mounts, locked_hullmod_ids=hullmods, locked_wing_ids=wings), self.improve_button, "Improving existing variant", self._show_refit_result)

    def _retrofit_output_root(self) -> Path | None:
        value = self.output.text().strip()
        if not value:
            self.refit_detail.setPlainText("Choose an output directory before creating editable retrofit copies.")
            return None
        return Path(value)

    def _copy_retrofit_to_library(self) -> None:
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

    def _load_editable_retrofit(self) -> None:
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

    def _refresh_editable_retrofit_library(self) -> None:
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

    def _open_editable_retrofit_item(self, item: QListWidgetItem) -> None:
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

    def _show_editable_retrofit_history(self) -> None:
        item = self.editable_retrofit_list.currentItem()
        value = item.data(Qt.UserRole) if item is not None else None
        if not isinstance(value, str):
            self.refit_detail.setPlainText("Select a local editable retrofit first."); return
        path = Path(value); history = path.parent / ".history" / path.stem
        entries = sorted(history.glob("*.variant")) if history.is_dir() else []
        self.refit_detail.setPlainText("Replacement history is recoverable local output only.\n" + ("\n".join(str(entry) for entry in entries) if entries else "No prior local replacement versions."))

    def _publish_editable_retrofit(self) -> None:
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

    def _restore_editable_retrofit_history(self) -> None:
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

    def _populate_missing_retrofits(self) -> None:
        if self._registry is None or self._current_hull is None or (output := self._retrofit_output_root()) is None:
            self.refit_detail.setPlainText("Select a hull in Ships, then choose an output directory."); return
        heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
        self._run("Checking existing retrofits and creating local starter variations when absent…", lambda: api.load_or_populate_retrofits(self._registry, self._current_hull.id, output, heuristic_set), lambda result: (self.refit_detail.setPlainText(result.note + ("\nExisting scanned variants:\n" + "\n".join(item.id for item in result.existing_variants) if result.existing_variants else "\nProfiles considered: " + ", ".join(result.attempted_profiles) + "\nProfiles generated: " + (", ".join(result.generated_profiles) or "None") + ("\nEditable local files:\n" + "\n".join(map(str, result.generated_paths)) if result.generated_paths else ""))), self._refresh_editable_retrofit_library()), self.populate_retrofits_button)

    def _faction_selected(self, _: int) -> None: self.faction_detail.setPlainText("Choose capability analysis or gap recommendations.") if self._faction_id() else None
    def _choose_knowledge_pack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose faction knowledge pack", self.knowledge_pack_path.text(), "JSON files (*.json)")
        if path:
            self.knowledge_pack_path.setText(path)
            self._preferences.setValue("paths/knowledge_pack", path)
    def _faction_id(self) -> tuple[str, str | None] | None:
        item = self.faction_list.currentItem(); value = item.data(Qt.UserRole) if item is not None else None; return tuple(value) if isinstance(value, tuple) and len(value) == 2 else None
    def _faction_run(self, operation: Callable[[str, str | None], Any], button: QPushButton, message: str) -> None:
        selected = self._faction_id()
        if self._registry is None or selected is None: self.faction_detail.setPlainText("Select a scanned faction first."); return
        if self._registry_write_in_progress(): self.faction_detail.setPlainText("A scan or mod incorporation is still in progress; wait for it to finish first."); return
        faction_id, source_mod = selected; self._run(message, lambda: operation(faction_id, source_mod), lambda result: self.faction_detail.setPlainText(str(result)), button)
    def _analyze_capability(self) -> None:
        heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
        pack_path = self.knowledge_pack_path.text().strip()
        def analyze(faction: str, source: str | None) -> dict[str, object]:
            result: dict[str, object] = {"automatic_capability": api.run_faction_capability(self._registry, faction, source, heuristic_set)}
            if pack_path:
                pack = api.resolve_optional_knowledge_pack(Path(pack_path), self._registry)
                result["knowledge_pack"] = pack
            return result
        self._faction_run(analyze, self.capability_button, "Computing faction capability vector…")
    def _gap_recommendations(self) -> None:
        heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
        pack_path = self.knowledge_pack_path.text().strip()
        def recommend(faction: str, source: str | None) -> object:
            pack = api.resolve_optional_knowledge_pack(Path(pack_path), self._registry) if pack_path else None
            return api.run_gap_recommendations(self._registry, faction, source, heuristic_set, pack)
        self._faction_run(recommend, self.recommend_button, "Ranking Hull + BuildArchetype gap solutions…")

    def _fleet_support(self) -> None:
        if self._registry is None:
            self.faction_detail.setPlainText("Scan an installation before asking for fleet support advice."); return
        hull_ids = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
        if not hull_ids:
            self.faction_detail.setPlainText("Enter at least one locked hull ID. Repeating an ID records another selected ship."); return
        try:
            selections = parse_fleet_selections(hull_ids)
        except ValueError as exc:
            self.faction_detail.setPlainText(str(exc)); return
        selected = self._faction_id()
        access = str(self.fleet_support_access.currentData())
        if access == "STRICT_FACTION" and selected is None:
            QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
        heuristic_set = str(self.fleet_support_heuristic.currentData())
        constraints = FleetSupportConstraints(access_mode=access, allow_foreign_hulls=self.fleet_support_allow_foreign.isChecked(), include_hidden_hulls=self.fleet_support_include_hidden.isChecked(), focus=SupportFocus(str(self.fleet_support_focus.currentData())))
        faction_id, source_mod = selected if selected is not None else (None, None)
        self._run("Analyzing locked fleet selections and ranking individual additions…", lambda: api.run_fleet_support_advisor(self._registry, selections, faction_id, source_mod, heuristic_set, constraints), self._show_fleet_support_result, self.fleet_support_button)

    def _show_fleet_support_result(self, result: Any) -> None:
        self._fleet_support_last_result = result
        self._advisor_card_origin = "FLEET_SUPPORT"
        self.faction_detail.setPlainText(format_fleet_support_result(result))
        self.fleet_support_cards.clear()
        for item in result.recommendations:
            purposes = ", ".join(item.support_purposes) or "support addition"
            card = QListWidgetItem(f"{item.hull_id}  •  {purposes}  •  score {item.recommendation_score:.3f}")
            card.setData(Qt.UserRole, item.hull_id)
            composition = item.score_components.composition_synergy if item.score_components is not None else None
            card.setToolTip(f"Supports: {', '.join(item.supports)}\nComposition synergy: {composition:.3f}" if composition is not None else f"Supports: {', '.join(item.supports)}\n{item.diversity_reason or 'Selected by score.'}")
            self.fleet_support_cards.addItem(card)
        if not result.recommendations:
            self.fleet_support_cards.addItem("No material candidate additions.")

    def _scenario_profile_from_controls(self) -> Any:
        selected = str(self.scenario_profile.currentData())
        if selected != "CUSTOM":
            return next(profile for profile in generic_scenario_profiles() if profile.scenario_id == selected)
        targets: list[ScenarioCapabilityTarget] = []
        for token in self.scenario_targets.text().split(","):
            name, separator, value = token.strip().partition("=")
            if not separator:
                raise ValueError("Custom scenario targets use CAPABILITY=0.00 through CAPABILITY=1.00")
            try:
                targets.append(ScenarioCapabilityTarget(name.strip().upper(), float(value.strip())))
            except ValueError as exc:
                raise ValueError(f"Invalid target value for {name.strip() or 'capability'}") from exc
        return user_defined_scenario("custom_declared", "Custom Declared Scenario", tuple(targets))

    def _evaluate_scenario(self) -> None:
        if self._registry is None:
            self.faction_detail.setPlainText("Scan an installation before evaluating a scenario."); return
        tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
        if not tokens:
            self.faction_detail.setPlainText("Enter at least one locked hull ID before evaluating a scenario."); return
        try:
            selections = parse_fleet_selections(tokens); scenario = self._scenario_profile_from_controls()
        except ValueError as exc:
            self.faction_detail.setPlainText(str(exc)); return
        selected = self._faction_id(); constraints = self._fleet_support_constraints_from_controls()
        if constraints.access_mode == "STRICT_FACTION" and selected is None:
            QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
        faction_id, source_mod = selected if selected is not None else (None, None)
        heuristic_set = str(self.fleet_support_heuristic.currentData())
        def complete(result: Any) -> None:
            self._scenario_last_result = result
            self._advisor_card_origin = "SCENARIO"
            self.faction_detail.setPlainText(format_scenario_fleet_assessment(result))
            self.fleet_support_cards.clear()
            for item in result.recommendations:
                purposes = ", ".join(item.support_purposes) or "scenario support addition"
                card = QListWidgetItem(f"{item.hull_id} - {purposes} - scenario score {item.recommendation_score:.3f}")
                card.setData(Qt.UserRole, item.hull_id)
                card.setToolTip("Scenario-targeted addition. Revalidate before generating a concrete fit.\nSupports: " + ", ".join(item.supports))
                self.fleet_support_cards.addItem(card)
            if not result.recommendations:
                self.fleet_support_cards.addItem("No material scenario-targeted additions.")
        self._run("Comparing locked fleet mechanics with declared scenario targets", lambda: api.run_scenario_fleet_advisor(self._registry, selections, scenario, faction_id, source_mod, heuristic_set, constraints), complete, self.scenario_evaluate_button, cancellable=True)

    def _generate_scenario_fit(self) -> None:
        if self._registry is None:
            self.faction_detail.setPlainText("Scan an installation before generating a scenario fit."); return
        candidate = self.fleet_support_candidate.text().strip()
        tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
        if not candidate or not tokens:
            self.faction_detail.setPlainText("Select a current scenario recommendation and keep at least one locked hull ID."); return
        try:
            selections = parse_fleet_selections(tokens); scenario = self._scenario_profile_from_controls()
        except ValueError as exc:
            self.faction_detail.setPlainText(str(exc)); return
        selected = self._faction_id(); constraints = self._fleet_support_constraints_from_controls()
        if constraints.access_mode == "STRICT_FACTION" and selected is None:
            QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
        faction_id, source_mod = selected if selected is not None else (None, None)
        heuristic_set = str(self.fleet_support_heuristic.currentData())
        def complete(outcome: Any) -> None:
            self.faction_detail.setPlainText(
                f"SCENARIO SUPPORT FIT - {outcome.recommendation.hull_id}\n"
                f"Scenario: {outcome.assessment.scenario.display_name}\nPurpose: {outcome.support_purpose}\n"
                f"Generator profile: {outcome.generator_profile}\n\n"
                + format_generation_results(outcome.generation.assessed_candidates, outcome.generation.selected_profile, outcome.generation.flux_mode)
            )
        self._run("Revalidating scenario recommendation and generating a concrete fit", lambda: api.run_generate_scenario_support_fit(self._registry, selections, scenario, candidate, faction_id, source_mod, heuristic_set, constraints), complete, self.generate_scenario_fit_button, cancellable=True)

    def _save_scenario_request(self) -> None:
        tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
        try:
            selections = parse_fleet_selections(tokens); scenario = self._scenario_profile_from_controls()
        except ValueError as exc:
            self.faction_detail.setPlainText(str(exc)); return
        path, _ = QFileDialog.getSaveFileName(self, "Save Scenario Advisor Request", "scenario-advisor-request.json", "JSON files (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(scenario_advisor_request_to_payload(selections, scenario, self._fleet_support_constraints_from_controls()), indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Request not saved", str(exc)); return
        self.statusBar().showMessage("Scenario Advisor request saved; it contains only declared selections, targets, and constraints.")

    def _load_scenario_request(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Scenario Advisor Request", "", "JSON files (*.json)")
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            selections, scenario, constraints = scenario_advisor_request_from_payload(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Request not loaded", str(exc)); return
        entries = [(f"variant:{item.variant_id}" if item.variant_id else str(item.hull_id)) + (f"*{item.count}" if item.count != 1 else "") for item in selections]
        self.fleet_support_hulls.setText(", ".join(entries))
        profile_index = self.scenario_profile.findData(scenario.scenario_id)
        if profile_index >= 0:
            self.scenario_profile.setCurrentIndex(profile_index); self.scenario_targets.clear()
        else:
            self.scenario_profile.setCurrentIndex(self.scenario_profile.findData("CUSTOM"))
            self.scenario_targets.setText(", ".join(f"{item.capability}={item.target:.2f}" for item in scenario.capability_targets))
        self.fleet_support_focus.setCurrentIndex(max(0, self.fleet_support_focus.findData(constraints.focus.value)))
        self.fleet_support_access.setCurrentIndex(max(0, self.fleet_support_access.findData(constraints.access_mode)))
        self.fleet_support_allow_foreign.setChecked(constraints.allow_foreign_hulls)
        self.fleet_support_include_hidden.setChecked(constraints.include_hidden_hulls)
        self.statusBar().showMessage("Scenario Advisor request loaded; scan local data before evaluating it.")

    def _compare_fleet_support_cards(self) -> None:
        result = getattr(self, "_scenario_last_result", None) if self._advisor_card_origin == "SCENARIO" else getattr(self, "_fleet_support_last_result", None)
        by_id = {item.hull_id: item for item in getattr(result, "recommendations", ())}
        selected = tuple(by_id[item.data(Qt.UserRole)] for item in self.fleet_support_cards.selectedItems() if isinstance(item.data(Qt.UserRole), str) and item.data(Qt.UserRole) in by_id)
        if len(selected) < 2:
            self.faction_detail.setPlainText("Select at least two recommendation cards to compare their backend evidence."); return
        self.faction_detail.setPlainText(format_fleet_support_comparison(selected))

    def _fleet_support_card_selected(self, _: int) -> None:
        item = self.fleet_support_cards.currentItem()
        hull_id = item.data(Qt.UserRole) if item is not None else None
        if isinstance(hull_id, str):
            self.fleet_support_candidate.setText(hull_id)

    def _generate_support_fit(self) -> None:
        if self._registry is None:
            self.faction_detail.setPlainText("Scan an installation before generating a support fit."); return
        if self._advisor_card_origin == "SCENARIO":
            self.faction_detail.setPlainText("These cards came from Scenario Advisor. Use Generate Scenario Fit so the declared scenario targets are revalidated."); return
        candidate = self.fleet_support_candidate.text().strip()
        tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
        if not candidate or not tokens:
            self.faction_detail.setPlainText("Select a current support recommendation and keep at least one locked hull ID."); return
        try:
            selections = parse_fleet_selections(tokens)
        except ValueError as exc:
            self.faction_detail.setPlainText(str(exc)); return
        selected = self._faction_id(); constraints = self._fleet_support_constraints_from_controls()
        if constraints.access_mode == "STRICT_FACTION" and selected is None:
            QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
        faction_id, source_mod = selected if selected is not None else (None, None)
        heuristic_set = str(self.fleet_support_heuristic.currentData())
        def complete(outcome: Any) -> None:
            self.faction_detail.setPlainText(f"SUPPORT FIT — {outcome.recommendation.hull_id}\nPurpose: {outcome.support_purpose}\nGenerator profile: {outcome.generator_profile}\n\n" + format_generation_results(outcome.generation.assessed_candidates, outcome.generation.selected_profile, outcome.generation.flux_mode))
        self._run("Revalidating advisor recommendation and generating a concrete support fit…", lambda: api.run_generate_fleet_support_fit(self._registry, selections, candidate, faction_id, source_mod, heuristic_set, constraints), complete, self.generate_support_fit_button)

    def _add_current_hull_to_fleet_support(self) -> None:
        if self._current_hull is None:
            return
        current = [item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip()]
        current.append(self._current_hull.id)
        self.fleet_support_hulls.setText(", ".join(current))
        self.workspace_tabs.setCurrentIndex(2)
        self.fleet_support_hulls.setFocus()
        self.statusBar().showMessage(f"Added {self._current_hull.id} as a locked Fleet Support Advisor selection.")

    def _clear_fleet_support(self) -> None:
        self.fleet_support_hulls.clear()
        self.fleet_support_candidate.clear()
        self.faction_detail.setPlainText("Fleet Support Advisor selection cleared. Enter locked hull IDs or add one from Ships.")
        self.statusBar().showMessage("Fleet Support Advisor local selection cleared.")

    def _fleet_support_constraints_from_controls(self) -> FleetSupportConstraints:
        return FleetSupportConstraints(
            access_mode=str(self.fleet_support_access.currentData()),
            allow_foreign_hulls=self.fleet_support_allow_foreign.isChecked(),
            include_hidden_hulls=self.fleet_support_include_hidden.isChecked(),
            focus=SupportFocus(str(self.fleet_support_focus.currentData())),
        )

    def _save_fleet_support_request(self) -> None:
        tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
        try:
            selections = parse_fleet_selections(tokens)
        except ValueError as exc:
            self.faction_detail.setPlainText(str(exc)); return
        path, _ = QFileDialog.getSaveFileName(self, "Save Fleet Support Request", "fleet-support-request.json", "JSON files (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(fleet_support_request_to_payload(selections, self._fleet_support_constraints_from_controls()), indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Request not saved", str(exc)); return
        self.statusBar().showMessage("Fleet Support Advisor request saved.")

    def _load_fleet_support_request(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Fleet Support Request", "", "JSON files (*.json)")
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            selections, constraints = fleet_support_request_from_payload(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Request not loaded", str(exc)); return
        entries = []
        for item in selections:
            identifier = f"variant:{item.variant_id}" if item.variant_id else str(item.hull_id)
            entries.append(f"{identifier}*{item.count}" if item.count != 1 else identifier)
        self.fleet_support_hulls.setText(", ".join(entries))
        self.fleet_support_focus.setCurrentIndex(max(0, self.fleet_support_focus.findData(constraints.focus.value)))
        self.fleet_support_access.setCurrentIndex(max(0, self.fleet_support_access.findData(constraints.access_mode)))
        self.fleet_support_allow_foreign.setChecked(constraints.allow_foreign_hulls)
        self.fleet_support_include_hidden.setChecked(constraints.include_hidden_hulls)
        self.statusBar().showMessage("Fleet Support Advisor request loaded.")

    def _fleet_support_why_not(self) -> None:
        if self._registry is None:
            self.faction_detail.setPlainText("Scan an installation before asking for a Fleet Support Why-Not explanation."); return
        candidate = self.fleet_support_candidate.text().strip()
        hull_ids = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
        if not candidate or not hull_ids:
            self.faction_detail.setPlainText("Enter both a candidate hull ID and at least one locked hull ID."); return
        try:
            selections = parse_fleet_selections(hull_ids)
        except ValueError as exc:
            self.faction_detail.setPlainText(str(exc)); return
        selected = self._faction_id(); access = str(self.fleet_support_access.currentData())
        if access == "STRICT_FACTION" and selected is None:
            QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
        heuristic_set = str(self.fleet_support_heuristic.currentData())
        constraints = FleetSupportConstraints(access_mode=access, allow_foreign_hulls=self.fleet_support_allow_foreign.isChecked(), include_hidden_hulls=self.fleet_support_include_hidden.isChecked(), focus=SupportFocus(str(self.fleet_support_focus.currentData())))
        faction_id, source_mod = selected if selected is not None else (None, None)
        self._run("Explaining Fleet Support Advisor candidate…", lambda: api.run_fleet_support_why_not(self._registry, selections, candidate, faction_id, source_mod, heuristic_set, constraints), lambda result: self.faction_detail.setPlainText(format_fleet_support_why_not(result)), self.fleet_support_why_not_button)

    def _export_current(self) -> None:
        if self._registry is None or self._current_hull is None: QMessageBox.information(self, "No hull selected", "Select a scanned hull before exporting."); return
        output_text = self.output.text().strip()
        # Mirrors _start_scan's own check on this same field: without it, a
        # cleared output box wouldn't raise or warn at all -- write_variant
        # creates missing parent directories on demand, so Path("") would
        # silently resolve to (and write under) the current working
        # directory instead of anywhere the user chose.
        if not output_text: QMessageBox.warning(self, "Output directory required", "Choose a safe output directory for generated reports and local cache data."); return
        if self._registry_write_in_progress(): self.statusBar().showMessage("A scan or mod incorporation is still in progress; wait for it to finish before exporting."); return
        output, hull_id = Path(output_text), self._current_hull.id
        heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
        self._run("Creating conservative compatibility-mod export…", lambda: api.run_export(self._registry, heuristic_set, output, hull_id, "LINE_BRAWLER"), lambda path: self.statusBar().showMessage(f"Export complete: {path}"), self.export_button)

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
