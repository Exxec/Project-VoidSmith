"""Window layout helpers for MainWindow; GUI rules stay in the backend."""
from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTableView, QTabWidget, QVBoxLayout, QWidget
from starsector_variant_generator.analysis.fleet_support import SupportFocus
from starsector_variant_generator.analysis.recommendation_feedback import FeedbackKind
from starsector_variant_generator.analysis.scenario_advisor import generic_scenario_profiles
from starsector_variant_generator.gui.canvas import MOUNT_TYPE_COLORS, TechnicalCanvas
from starsector_variant_generator.gui.models import EntityTableModel
from starsector_variant_generator.gui.save_workshop import SaveWorkshopWidget
from starsector_variant_generator.profiles.catalog import available_profiles

if TYPE_CHECKING:
    from .main_window import MainWindow


def _make_tabs(self: MainWindow) -> QTabWidget:
    tabs = QTabWidget()
    self.workspace_tabs = tabs
    for widget, title in ((self._ships(), "Ships"), (self._retrofits(), "Retrofits"), (self._faction(), "Faction"), (self._data(), "Data / Analysis"), (self._settings(), "Settings / Export")):
        tabs.addTab(widget, title)
    self.save_workshop_page = None
    tabs.currentChanged.connect(self._workspace_changed)
    return tabs


def _ships(self: MainWindow) -> QWidget:
    page = QWidget(); layout = QVBoxLayout(page); tabs = QTabWidget()
    self.ship_tabs = tabs
    tabs.addTab(self._browse(), "Browse / Fit")
    self.inspect_detail = QPlainTextEdit(); self.inspect_detail.setReadOnly(True); self.inspect_detail.setPlainText("Select a hull in Browse / Fit.")
    tabs.addTab(self.inspect_detail, "Inspect")
    self.compare_detail = QPlainTextEdit(); self.compare_detail.setReadOnly(True); self.compare_detail.setPlainText("Generated candidates appear here.")
    tabs.addTab(self.compare_detail, "Compare"); layout.addWidget(tabs); return page


def _browse(self: MainWindow) -> QWidget:
    # Center panel favored: weapon slots are selected directly on the
    # rendered hull, and Generation Controls/Generated Build Paths now
    # live in the inspector's own "Generate" tab rather than stacked
    # below the canvas, so the canvas gets the majority of the space.
    split = QSplitter(Qt.Horizontal); split.addWidget(self._browser()); split.addWidget(self._center()); split.addWidget(self._inspector()); split.setSizes([250, 1150, 260]); return split


def _browser(self: MainWindow) -> QWidget:
    panel = QFrame(); panel.setObjectName("panel"); layout = QVBoxLayout(panel); group = QGroupBox("HULL BROWSER & FILTERS"); filters = QVBoxLayout(group)
    self.search = QLineEdit(); self.search.setPlaceholderText("Search scanned hulls…"); self.search.textChanged.connect(self._schedule_hull_refresh); filters.addWidget(self.search)
    self.size_filter, self.source_filter, self.faction_filter = QComboBox(), QComboBox(), QComboBox()
    for label, box in (("HULL SIZE", self.size_filter), ("SOURCE MOD", self.source_filter), ("FACTION", self.faction_filter)):
        filters.addWidget(QLabel(label)); filters.addWidget(box); box.currentIndexChanged.connect(self._refresh_hulls)
    reset = QPushButton("Reset Filters"); reset.clicked.connect(self._reset_filters); filters.addWidget(reset); layout.addWidget(group)
    self.count = QLabel("HULLS (scan required)"); layout.addWidget(self.count)
    self.hull_list = QListWidget(); self.hull_list.addItem("Scan an installation to populate hulls"); self.hull_list.currentRowChanged.connect(self._selected_hull); layout.addWidget(self.hull_list, 1)
    return panel


def _center(self: MainWindow) -> QWidget:
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


def _inspector_tab(self: MainWindow) -> QWidget:
    panel = QWidget(); layout = QVBoxLayout(panel); group = QGroupBox("BUILD INSPECTOR"); box = QVBoxLayout(group); self.values = {}
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


def _generate_tab(self: MainWindow) -> QWidget:
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
    self._generated_candidates = []; layout.addWidget(group, 1)
    return panel


def _inspector(self: MainWindow) -> QWidget:
    tabs = QTabWidget()
    tabs.addTab(self._inspector_tab(), "Inspector")
    tabs.addTab(self._generate_tab(), "Generate")
    return tabs


def _retrofits(self: MainWindow) -> QWidget:
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
    # Named distinctly from the `widget` loop variable used above (line
    # 317's placeholder-text loop): that binding's narrower `QLineEdit`
    # type otherwise gets attributed to this, unrelated, mixed-widget
    # loop (QComboBox/QLineEdit/QWidget), since both share one function
    # scope.
    for label, form_widget in (("Quality mode", self.refit_mode_selector), ("Target profile", self.refit_profile_selector), ("Legality substitution", self.refit_substitution_selector), ("Locked mounts", self.refit_locked_mounts), ("Locked hullmods", self.refit_locked_hullmods), ("Locked fighter wings", self.refit_locked_wings), ("Editable hullmods", self.editable_hullmods), ("Editable fighter wings", self.editable_wings), ("Editable flux vents", self.editable_vents), ("Editable flux capacitors", self.editable_capacitors), ("Video review evidence", video_review_row)):
        form.addRow(label, form_widget)
    layout.addWidget(options); self.refit_detail = QPlainTextEdit(); self.refit_detail.setReadOnly(True); self.refit_detail.setPlainText("Choose a scanned variant. Suggestions preserve backend legality and selected locks."); layout.addWidget(self.refit_detail, 1); return page


def _faction(self: MainWindow) -> QWidget:
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
    build_comparison_group = QGroupBox("BUILD PATH EXPLAINABILITY COMPARISON")
    build_comparison_form = QFormLayout(build_comparison_group)
    self.build_comparison_role = QLineEdit("LINE_BRAWLER"); self.build_comparison_role.setPlaceholderText("Capability role, for example LINE_BRAWLER")
    self.build_comparison_paths = QLineEdit(); self.build_comparison_paths.setPlaceholderText("hull_id:build_id, hull_id:build_id")
    self.build_comparison_button = QPushButton("Compare Why-Not Evidence"); self.build_comparison_button.setEnabled(False); self.build_comparison_button.clicked.connect(self._compare_build_paths)
    build_comparison_form.addRow("Role", self.build_comparison_role); build_comparison_form.addRow("Paths", self.build_comparison_paths); build_comparison_form.addRow(self.build_comparison_button); layout.addWidget(build_comparison_group)
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
    self.feedback_kind = QComboBox()
    for kind in FeedbackKind:
        self.feedback_kind.addItem(kind.value.replace("_", " ").title(), kind.value)
    self.save_feedback_button = QPushButton("Record Feedback")
    self.save_feedback_button.setEnabled(False); self.save_feedback_button.setToolTip("Stores explicit local review feedback only; it never changes legality, rankings, or heuristics automatically.")
    self.save_feedback_button.clicked.connect(self._save_recommendation_feedback)
    feedback_row = QWidget(); feedback_layout = QHBoxLayout(feedback_row); feedback_layout.setContentsMargins(0, 0, 0, 0); feedback_layout.addWidget(self.feedback_kind); feedback_layout.addWidget(self.save_feedback_button)
    support_form.addRow("Keep / lock", self.fleet_support_hulls); support_form.addRow("Focus", self.fleet_support_focus); support_form.addRow("Access", self.fleet_support_access); support_form.addRow("Heuristics", self.fleet_support_heuristic); support_form.addRow("Availability", self.fleet_support_allow_foreign); support_form.addRow("Visibility", self.fleet_support_include_hidden); support_form.addRow("Candidate", self.fleet_support_candidate); support_form.addRow("Local feedback", feedback_row); support_form.addRow(support_buttons)
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


def _data(self: MainWindow) -> QWidget:
    page = QWidget(); layout = QVBoxLayout(page); split = QSplitter(Qt.Horizontal); tabs = QTabWidget(); self.data_tables = {}; self._data_entities = {}
    for title, headers in (("Weapons", ["Name", "Size", "Type", "Source Mod"]), ("Hullmods", ["Name", "Hidden", "Source Mod"]), ("Fighters", ["Name", "Role", "Source Mod"]), ("Variants", ["Name", "Hull", "Source Mod"])):
        table = QTableView(); table.setModel(EntityTableModel(headers, table)); table.setEditTriggers(QTableView.NoEditTriggers); table.selectionModel().selectionChanged.connect(lambda _selected, _deselected, title=title: self._show_provenance(title)); tabs.addTab(table, title); self.data_tables[title] = table
    self.scan_diagnostics_view = QPlainTextEdit(); self.scan_diagnostics_view.setReadOnly(True)
    self.scan_diagnostics_view.setPlainText("Scan to list parse failures with locations and enabled mods that are not installed.")
    tabs.addTab(self.scan_diagnostics_view, "Diagnostics")
    self.provenance_detail = QPlainTextEdit(); self.provenance_detail.setReadOnly(True); self.provenance_detail.setPlainText("Select a normalized record to inspect local source provenance.")
    provenance_group = QGroupBox("PROVENANCE"); provenance_layout = QVBoxLayout(provenance_group); provenance_layout.addWidget(self.provenance_detail)
    split.addWidget(tabs); split.addWidget(provenance_group); split.setSizes([860, 360]); layout.addWidget(split); return page


def _settings(self: MainWindow) -> QWidget:
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
    self.save_workshop_enabled = QCheckBox("Enable Save Workshop (inspect, plan, write verified copies)")
    self.save_workshop_enabled.setChecked(False)
    self.save_workshop_enabled.setToolTip("Off by default. When on, the Save Workshop can inspect a save and plan edits; 'Write edited copy' then writes a verified NEW copy below the output directory, only for changes within the saved capacity. The original save is never changed.")
    self.save_workshop_enabled.toggled.connect(self._toggle_save_workshop)
    layout.addWidget(self.save_workshop_enabled)
    mods_group = QGroupBox("ADDITIONAL MODS (drag && drop)"); mods_layout = QVBoxLayout(mods_group)
    mods_layout.addWidget(QLabel("Drag a mod folder or .zip archive anywhere onto this window to add it to the next scan — it does not need to be installed under the Starsector installation's mods folder."))
    self.extra_mods_list = QListWidget(); self.extra_mods_list.addItem("No additional mods added."); mods_layout.addWidget(self.extra_mods_list, 1)
    remove_extra_mod = QPushButton("Remove Selected"); remove_extra_mod.clicked.connect(self._remove_selected_extra_mod); mods_layout.addWidget(remove_extra_mod)
    layout.addWidget(mods_group)
    summary_group = QGroupBox("LATEST LOCAL SCAN / REPORT STATUS"); summary_layout = QVBoxLayout(summary_group)
    self.scan_summary = QPlainTextEdit(); self.scan_summary.setReadOnly(True); self.scan_summary.setMaximumHeight(150)
    self.scan_summary.setPlainText("No local scan has been loaded. Source files are read-only; reports are written only under the configured output directory.")
    summary_layout.addWidget(self.scan_summary); layout.addWidget(summary_group)
    calibration_group = QGroupBox("LOCAL CALIBRATION WORKSPACE"); calibration_layout = QFormLayout(calibration_group)
    self.calibration_fixture = QLineEdit(str(self._preferences.value("paths/calibration_fixture", ""))); self.calibration_fixture.setPlaceholderText("Optional local hash-bound calibration labels JSON")
    choose_calibration = QPushButton("Choose…"); choose_calibration.clicked.connect(self._choose_calibration_fixture)
    calibration_path_row = QWidget(); calibration_path_layout = QHBoxLayout(calibration_path_row); calibration_path_layout.setContentsMargins(0, 0, 0, 0); calibration_path_layout.addWidget(self.calibration_fixture, 1); calibration_path_layout.addWidget(choose_calibration)
    self.calibration_button = QPushButton("Evaluate Local Labels"); self.calibration_button.setEnabled(False); self.calibration_button.clicked.connect(self._evaluate_local_calibration)
    self.calibration_detail = QPlainTextEdit(); self.calibration_detail.setReadOnly(True); self.calibration_detail.setMaximumHeight(110); self.calibration_detail.setPlainText("Load a local label fixture after scanning. Evaluation is read-only and never tunes heuristics.")
    calibration_layout.addRow("Fixture", calibration_path_row); calibration_layout.addRow(self.calibration_button); calibration_layout.addRow(self.calibration_detail); layout.addWidget(calibration_group)
    release_group = QGroupBox("PORTABLE RELEASE VERIFICATION")
    release_layout = QFormLayout(release_group)
    self.release_archive = QLineEdit(str(self._preferences.value("paths/release_archive", ""))); self.release_archive.setPlaceholderText("Local VoidSmith .zip or .tar.gz archive")
    choose_release = QPushButton("Choose…"); choose_release.clicked.connect(self._choose_release_archive)
    release_row = QWidget(); release_row_layout = QHBoxLayout(release_row); release_row_layout.setContentsMargins(0, 0, 0, 0); release_row_layout.addWidget(self.release_archive, 1); release_row_layout.addWidget(choose_release)
    self.release_verify_button = QPushButton("Verify Archive"); self.release_verify_button.clicked.connect(self._verify_release_archive)
    self.release_detail = QPlainTextEdit(); self.release_detail.setReadOnly(True); self.release_detail.setMaximumHeight(80); self.release_detail.setPlainText("Reads the archive and optional adjacent checksum without extracting or running it.")
    release_layout.addRow("Archive", release_row); release_layout.addRow(self.release_verify_button); release_layout.addRow(self.release_detail); layout.addWidget(release_group)
    layout.addStretch(); return page


def _toggle_save_workshop(self: MainWindow, enabled: bool) -> None:
    if enabled and self.save_workshop_page is None:
        self.save_workshop_page = SaveWorkshopWidget(self._run, lambda: Path(self.root.text().strip()) if self.root.text().strip() else None, self, output_dir=lambda: Path(self.output.text().strip()) if self.output.text().strip() else None)
        self.workspace_tabs.addTab(self.save_workshop_page, "Save Workshop")
    if self.save_workshop_page is not None:
        index = self.workspace_tabs.indexOf(self.save_workshop_page)
        self.workspace_tabs.setTabVisible(index, enabled)
        if enabled:
            self.workspace_tabs.setCurrentIndex(index)
        else:
            self.save_workshop_page._invalidate_plan()
