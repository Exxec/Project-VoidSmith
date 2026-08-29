from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings, QSize, Qt, QThread
    from PySide6.QtWidgets import QApplication, QListWidgetItem, QProgressDialog
    from starsector_variant_generator.gui.main_window import MainWindow, TechnicalCanvas, _SCAN_STALL_WARNING_INTERVAL_S
    from starsector_variant_generator.gui.workers.analysis_worker import AnalysisWorker
except ImportError:
    QApplication = None

from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.models import Faction, Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.gui.resources import _safe_sprite_path
from starsector_variant_generator.gui.canvas import _displayable_weapon_mounts, _mount_scene_position, _mount_scene_rotation, _sprite_geometry_scale


@unittest.skipIf(QApplication is None, "PySide6 optional GUI dependency is not installed")
class GuiCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        # MainWindow persists preferences (window size, last-used mode, ...)
        # to the real OS-native QSettings store by name ("VoidSmith",
        # "Desktop") -- indistinguishable from a real end user's saved
        # settings. `QSettings.setDefaultFormat(IniFormat)` alone does NOT
        # redirect this: the 2-arg `QSettings(organization, application)`
        # constructor `main_window.py` actually calls hardcodes
        # `NativeFormat` (the Windows registry) regardless of
        # `setDefaultFormat` -- confirmed directly (`QSettings("VoidSmith",
        # "Desktop").format()` still reports `NativeFormat` even after
        # `setDefaultFormat(IniFormat)`). Every test in this class was
        # therefore silently reading/writing the real
        # `HKEY_CURRENT_USER\Software\VoidSmith\Desktop` registry key the
        # whole time, not an isolated file -- a real risk of clobbering an
        # actual user's saved GUI preferences by running this suite. Patch
        # the `QSettings` name `main_window` imports directly instead, to a
        # subclass that always forces `IniFormat` at a private temp path.
        cls._settings_dir = TemporaryDirectory()
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, cls._settings_dir.name)

        class _IsolatedQSettings(QSettings):  # noqa: N801 -- matches QSettings' own naming
            def __init__(self, organization: str, application: str) -> None:
                super().__init__(QSettings.IniFormat, QSettings.UserScope, organization, application)

        cls._qsettings_patcher = patch("starsector_variant_generator.gui.main_window.QSettings", _IsolatedQSettings)
        cls._qsettings_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._qsettings_patcher.stop()
        cls._settings_dir.cleanup()

    def setUp(self) -> None:
        # The isolated store above still persists *across test methods*
        # within this class (they all construct QSettings("VoidSmith",
        # "Desktop"), the same identity) -- clear it before every test so
        # one test's window.close() can never leak state into the next.
        self._isolated_preferences().clear()

    @staticmethod
    def _isolated_preferences() -> QSettings:
        # Matches the isolated IniFormat store `_IsolatedQSettings` (patched
        # into main_window) actually reads/writes -- the bare
        # QSettings("VoidSmith", "Desktop") constructor used here in test
        # code would otherwise hit NativeFormat (the real registry) again.
        return QSettings(QSettings.IniFormat, QSettings.UserScope, "VoidSmith", "Desktop")

    def test_canvas_plots_only_parsed_slot_locations(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "A", "size": "SMALL", "type": "BALLISTIC", "locations": [2, 3]},
            {"id": "B", "size": "SMALL", "type": "MISSILE"},
        ))
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        self.assertGreaterEqual(len(canvas.scene_.items()), 4)

    def test_canvas_hides_scrollbars_but_keeps_drag_pan_mode(self) -> None:
        from PySide6.QtWidgets import QGraphicsView

        canvas = TechnicalCanvas()
        self.assertEqual(Qt.ScrollBarAlwaysOff, canvas.horizontalScrollBarPolicy())
        self.assertEqual(Qt.ScrollBarAlwaysOff, canvas.verticalScrollBarPolicy())
        self.assertEqual(QGraphicsView.ScrollHandDrag, canvas.dragMode())

    def test_mount_box_position_maps_forward_lateral_geometry_to_the_upright_canvas(self) -> None:
        # Per the Starsector modding wiki (File overview: ship): weapon
        # slot `locations` are already Cartesian coordinates relative to
        # the hull's declared `center` (itself measured from the sprite's
        # bottom-left pixel, Y-up) -- NOT a further offset from it. An
        # Direct screen X/Y placement quarter-turned every upright hull.
        # Forward (+X) maps screen-up; lateral (+Y) maps screen-right.
        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "A", "size": "SMALL", "type": "BALLISTIC", "locations": [30, 20]},
        ), raw={"ship_data": {"width": 80, "height": 100, "center": [40, 50]}})
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        x1, y1, x2, y2 = canvas._slot_hit_boxes["A"]
        center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
        self.assertAlmostEqual(20.0, center_x)
        self.assertAlmostEqual(-30.0, center_y)

    def test_mount_scene_position_keeps_forward_and_lateral_axes_distinct(self) -> None:
        self.assertEqual((46.0, -190.0), _mount_scene_position([190.0, 46.0]))

    def test_weapon_preview_rotation_uses_the_same_axis_mapping_as_slots(self) -> None:
        # A +X-facing source sprite at slot angle 0 points canvas-up; a
        # lateral +Y slot angle points canvas-right, exactly like position.
        self.assertEqual(-90.0, _mount_scene_rotation(0.0))
        self.assertEqual(0.0, _mount_scene_rotation(90.0))

    def test_carrier_and_decorative_anchors_are_not_displayed_as_weapon_slots(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "gun", "type": "BALLISTIC", "mount": "TURRET", "locations": [0, 0]},
            {"id": "bay", "type": "LAUNCH_BAY", "mount": "HIDDEN", "locations": [200, 30, 180, 30]},
            {"id": "light", "type": "DECORATIVE", "mount": "HARDPOINT", "locations": [10, 10]},
        ), launch_bay_slots=("bay",))
        self.assertEqual(("gun",), tuple(slot["id"] for slot in _displayable_weapon_mounts(hull)))
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        self.assertEqual({"gun"}, set(canvas._slot_hit_boxes))

    def test_carrier_launch_bays_render_as_a_non_selectable_side_stack(self) -> None:
        hull = Hull("h", "Carrier", "core", Path("fixture"), weapon_mounts=(
            {"id": "LB 1", "type": "LAUNCH_BAY", "mount": "HIDDEN", "locations": [10, 10]},
            {"id": "LB 2", "type": "LAUNCH_BAY", "mount": "HIDDEN", "locations": [20, 10]},
        ), launch_bay_slots=("LB 1", "LB 2"), fighter_bays=2)
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        text = "\n".join(item.toPlainText() for item in canvas.scene_.items() if hasattr(item, "toPlainText"))
        self.assertIn("Fighter bays (2)", text)
        self.assertIn("LB 1", text)
        self.assertIn("LB 2", text)
        self.assertEqual({}, canvas._slot_hit_boxes)

    def test_sprite_texture_is_mapped_to_declared_ship_geometry(self) -> None:
        # A mod is allowed to ship art at a different texture resolution than
        # its `.ship` geometry. Mounts stay in declared geometry units, so
        # the sprite must be scaled into those units rather than moving every
        # mount to native texture pixels.
        self.assertEqual((0.5, 0.5), _sprite_geometry_scale(400, 200, 200.0, 100.0, True))
        self.assertEqual((1.0, 1.0), _sprite_geometry_scale(400, 200, 200.0, 100.0, False))

    def test_canvas_registers_a_clickable_hit_box_for_each_selectable_mount(self) -> None:
        # Weapon slots are now selected by clicking their rendered box
        # directly on the hull (the former right-side QListWidget was
        # removed) -- a built-in mount is drawn but must stay unclickable
        # since the game fills it automatically.
        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "A", "size": "SMALL", "type": "BALLISTIC", "locations": [2, 3]},
            {"id": "B", "size": "SMALL", "type": "MISSILE", "locations": [-2, 3]},
        ), built_in_weapons={"B": "some_builtin_weapon"})
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        self.assertIn("A", canvas._slot_hit_boxes)
        self.assertNotIn("B", canvas._slot_hit_boxes)

    def test_canvas_renders_declared_weapon_sprite_for_selected_weapon(self) -> None:
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QGraphicsPixmapItem

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sprite_path = root / "graphics" / "weapons" / "gun.png"
            sprite_path.parent.mkdir(parents=True)
            image = QImage(16, 8, QImage.Format_ARGB32); image.fill(Qt.red); self.assertTrue(image.save(str(sprite_path)))
            weapon = Weapon("gun", "Gun", "core", root / "data" / "weapons" / "weapon_data.csv", raw={"weapon_spec": {"turretSprite": "graphics/weapons/gun.png"}})
            hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=({"id": "A", "size": "SMALL", "type": "BALLISTIC", "mount": "TURRET", "angle": 0, "locations": [2, 3]},))
            canvas = TechnicalCanvas(); canvas.show_hull(hull, {"A": "gun"}, {"gun": weapon})
            self.assertTrue(any(isinstance(item, QGraphicsPixmapItem) for item in canvas.scene_.items()))

    def test_canvas_click_on_a_mount_box_emits_slot_clicked(self) -> None:
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtTest import QTest

        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "A", "size": "SMALL", "type": "BALLISTIC", "locations": [2, 3]},
        ))
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        x1, y1, x2, y2 = canvas._slot_hit_boxes["A"]
        view_point = QPoint(canvas.mapFromScene(QPointF((x1 + x2) / 2, (y1 + y2) / 2)))
        clicked: list[str] = []
        canvas.slot_clicked.connect(clicked.append)
        QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, view_point)
        self.assertEqual(["A"], clicked)

    def test_canvas_click_outside_any_mount_box_does_not_emit(self) -> None:
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtTest import QTest

        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "A", "size": "SMALL", "type": "BALLISTIC", "locations": [2, 3]},
        ))
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        view_point = QPoint(canvas.mapFromScene(QPointF(-9999, -9999)))
        clicked: list[str] = []
        canvas.slot_clicked.connect(clicked.append)
        QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, view_point)
        self.assertEqual([], clicked)

    def test_sprite_resolution_rejects_paths_outside_the_scanned_source(self) -> None:
        root = Path("C:/fixture/source")
        self.assertIsNone(_safe_sprite_path(root, "../../outside.png"))

    def test_canvas_labels_module_composition_as_unmodeled(self) -> None:
        hull = Hull("module_parent", "Module Parent", "core", Path("fixture"), hull_hints=("SHIP_WITH_MODULES",))
        canvas = TechnicalCanvas(); canvas.show_hull(hull)
        text = "\n".join(item.toPlainText() for item in canvas.scene_.items() if hasattr(item, "toPlainText"))
        self.assertIn("Composite module behavior is not modeled", text)

    def test_canvas_slot_clicked_signal_is_wired_to_choose_slot(self) -> None:
        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        with patch("starsector_variant_generator.gui.main_window.QInputDialog.getItem", return_value=("Gun [gun] — core", True)):
            window.canvas.slot_clicked.emit("A")
        self.assertEqual("gun", window._fit_weapons.get("A"))
        window.close()

    def test_opening_retrofit_loads_its_weapon_fit_into_the_canvas_context(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=({"id": "A", "size": "SMALL", "type": "BALLISTIC", "locations": [0, 0]},))
        weapon = Weapon("gun", "Gun", "core", Path("fixture"))
        variant = Variant("fit", "Fit", "core", Path("fixture"), hull_id="h", weapons_by_mount={"A": "gun"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))
        window = MainWindow(); window._registry = registry; window._visible = (hull,)
        item = QListWidgetItem("Fit"); item.setData(Qt.UserRole, "fit")
        window._open_variant_hull(item)
        self.assertEqual("gun", window._fit_weapons["A"])
        self.assertEqual("fit", window._loaded_retrofit_variant.id)
        window.close()

    def test_editable_flux_fields_reject_negative_or_non_numeric_values(self) -> None:
        window = MainWindow()
        window.editable_vents.setText("-1")
        with self.assertRaises(ValueError): window._editable_stat_value(window.editable_vents, None)
        window.editable_vents.setText("12")
        self.assertEqual(12, window._editable_stat_value(window.editable_vents, None))
        window.close()

    def test_editable_retrofit_library_lists_only_local_variant_files(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp); library = root / "editable_retrofits"; library.mkdir(); (library / "saved.variant").write_text('{"variantId":"saved"}', encoding="utf-8")
            window = MainWindow(); window.output.setText(str(root)); window._refresh_editable_retrofit_library()
            self.assertEqual("[UNSCANNED] saved.variant", window.editable_retrofit_list.item(0).text())
            window.close()

    def test_editable_change_summary_reports_only_explicit_field_differences(self) -> None:
        before = Variant("v", "V", "USER_EDITABLE", Path("v"), hull_id="h", weapons_by_mount={"A": "old"}, hullmods=("old_mod",), flux_vents=2)
        after = Variant("v", "V", "USER_EDITABLE", Path("v"), hull_id="h", weapons_by_mount={"A": "new"}, hullmods=("new_mod",), flux_vents=3)
        changes = MainWindow._editable_change_summary(before, after)
        self.assertIn("mount A: old → new", changes)
        self.assertIn("hullmods: ('old_mod',) → ('new_mod',)", changes)

    def test_refit_result_can_be_loaded_into_editable_canvas_without_writing(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=({"id": "A", "size": "SMALL", "type": "BALLISTIC", "locations": [0, 0]},))
        weapon = Weapon("gun", "Gun", "core", Path("fixture"))
        variant = Variant("refit", "Refit", "core", Path("fixture"), hull_id="h", weapons_by_mount={"A": "gun"})
        window = MainWindow(); window._registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon])); window._visible = (hull,); window._last_refit_result = SimpleNamespace(refitted_variant=variant)
        window._apply_last_refit_result()
        self.assertEqual("USER_EDITABLE", window._loaded_retrofit_variant.source_mod)
        self.assertEqual("gun", window._fit_weapons["A"])
        window.close()

    def test_window_exposes_backend_generation_controls(self) -> None:
        window = MainWindow()
        self.assertEqual(window.mode_selector.currentData(), "beginner")
        self.assertEqual(window.profile_selector.currentData(), None)
        self.assertEqual(window.max_candidates.value(), 5)
        window.close()

    def test_first_ever_launch_defaults_to_maximized(self) -> None:
        # No stored preference at all (setUp clears QSettings every test) --
        # a genuinely first-ever launch should not open into main_window's
        # small hardcoded resize(1600, 920) default on a modern display.
        # __init__ calls showMaximized() before the caller's own show()
        # (matching app.py's real `MainWindow(); window.show()` sequence);
        # the offscreen QPA platform only reports the maximized state once
        # the window has actually been shown.
        window = MainWindow()
        window.show()
        self.assertTrue(window.isMaximized())
        window.close()

    def test_close_event_persists_maximized_state_and_pre_maximize_size(self) -> None:
        window = MainWindow()
        window.show()
        window.close()
        preferences = self._isolated_preferences()
        self.assertTrue(preferences.value("window/maximized", type=bool))
        # normalGeometry(), not the maximized size, so a later un-maximized
        # launch resizes to something sane instead of full-screen dimensions.
        self.assertEqual((1600, 920), (preferences.value("window/size").width(), preferences.value("window/size").height()))
        window.deleteLater()

    def test_non_maximized_preference_is_restored_on_next_launch(self) -> None:
        preferences = self._isolated_preferences()
        preferences.setValue("window/maximized", False)
        preferences.setValue("window/size", window_size := QSize(900, 700))
        window = MainWindow()
        self.assertFalse(window.isMaximized())
        self.assertEqual(window_size, window.size())
        window.close()

    def test_maximized_preference_is_restored_on_next_launch(self) -> None:
        preferences = self._isolated_preferences()
        preferences.setValue("window/maximized", True)
        window = MainWindow()
        self.assertTrue(window.isMaximized())
        window.close()

    def test_data_tables_materialize_only_when_data_workspace_is_opened(self) -> None:
        scan = ScanResult(hulls=[Hull("h", "Hull", "core", Path("fixture"))], weapons=[Weapon("w", "Weapon", "core", Path("fixture"))])
        window = MainWindow()
        window._scan_complete(SimpleNamespace(result=scan, registry=Registry.from_scan(scan)))
        self.assertTrue(window._data_tables_pending)
        self.assertEqual(0, window.data_tables["Weapons"].model().rowCount())
        window.workspace_tabs.setCurrentIndex(3)
        self.assertFalse(window._data_tables_pending)
        self.assertEqual(1, window.data_tables["Weapons"].model().rowCount())
        window.close()

    def test_background_result_token_rejects_stale_completion(self) -> None:
        window = MainWindow()
        completed: list[str] = []
        window._operation_tokens[window.generate_button] = 2
        window._complete_operation(window.generate_button, 1, completed.append, "stale")
        window._complete_operation(window.generate_button, 2, completed.append, "current")
        self.assertEqual(["current"], completed)
        window.close()

    def test_hull_search_uses_a_debounce_timer(self) -> None:
        window = MainWindow()
        window._schedule_hull_refresh()
        self.assertTrue(window._hull_filter_timer.isActive())
        window.close()

    def test_extra_mods_list_reflects_added_and_removed_entries(self) -> None:
        from starsector_variant_generator.core.mod_import import ModImportResult
        window = MainWindow()
        self.assertEqual(1, window.extra_mods_list.count())  # "No additional mods added."
        window._extra_mods = [ModImportResult(Path("/tmp/dropped"), "dropped_mod", "Dropped Mod", None)]
        window._refresh_extra_mods_list()
        self.assertEqual(1, window.extra_mods_list.count())
        self.assertIn("dropped_mod", window.extra_mods_list.item(0).text())
        window.extra_mods_list.setCurrentRow(0)
        window._remove_selected_extra_mod()
        self.assertEqual([], window._extra_mods)
        self.assertEqual("No additional mods added.", window.extra_mods_list.item(0).text())
        window.close()

    def test_dropping_a_real_mod_folder_adds_it_without_needing_installation(self) -> None:
        from PySide6.QtCore import QMimeData, QPointF, QUrl
        from PySide6.QtGui import QDropEvent

        with TemporaryDirectory() as tmp:
            mod_dir = Path(tmp) / "dropped_folder"
            mod_dir.mkdir()
            (mod_dir / "mod_info.json").write_text('{"id": "folder_mod", "name": "Folder Mod"}', encoding="utf-8")
            window = MainWindow()
            window.output.setText(str(Path(tmp) / "output"))
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(mod_dir))])
            event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.NoButton, Qt.NoModifier)
            window.dropEvent(event)
            self.assertEqual(1, len(window._extra_mods))
            self.assertEqual("folder_mod", window._extra_mods[0].mod_id)
            self.assertIn("folder_mod", window.extra_mods_list.item(0).text())
            window.close()

    def test_dropping_a_mod_after_a_scan_chooses_the_incremental_path(self) -> None:
        # The whole point of this feature: once a scan already exists in
        # the session, a drop should be usable immediately for fast
        # iterative testing, without needing "Scan Installed Data" again.
        # Verifies dropEvent's synchronous choice (starts the incremental
        # merge, doesn't fall back to "rescan to include") -- the merge
        # logic itself (_apply_incremental_scan_outcome, called once the
        # real background operation finishes) is exercised directly,
        # synchronously, in the next test; see that test's docstring for
        # why waiting on a real QThread here isn't reliable in this
        # headless test harness.
        from unittest.mock import patch
        from PySide6.QtCore import QMimeData, QPointF, QUrl
        from PySide6.QtGui import QDropEvent

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            scan = ScanResult(hulls=[Hull("existing_hull", "Existing Hull", "core", Path("fixture"))])
            window = MainWindow()
            window._scan_complete(SimpleNamespace(result=scan, registry=Registry.from_scan(scan)))
            window._config = AppConfig(Path(tmp) / "install", Path(tmp) / "output", Path(tmp) / "output" / "logs")

            mod_dir = Path(tmp) / "dropped_mod"
            mod_dir.mkdir()
            (mod_dir / "mod_info.json").write_text('{"id": "dropped_mod", "name": "Dropped Mod"}', encoding="utf-8")

            mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(mod_dir))])
            event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.NoButton, Qt.NoModifier)
            with patch.object(window, "_run") as run_mock:
                window.dropEvent(event)
            run_mock.assert_called_once()
            message, operation, completed, control = run_mock.call_args[0]
            self.assertIn("Incorporating", message)
            self.assertEqual(window._apply_incremental_scan_outcome, completed)
            self.assertIs(window.scan_button, control)
            self.assertNotIn("rescan to include", window.statusBar().currentMessage())
            window.close()

    def test_apply_incremental_scan_outcome_refreshes_hull_list_and_catalog(self) -> None:
        # The `completed` half of the drop-incorporation flow, called
        # directly (as `_run` would once the real background operation
        # finishes) rather than through a real QThread -- background-
        # thread completion timing isn't reliably observable via
        # processEvents() polling in this headless test harness: confirmed
        # directly, a trivial guaranteed-fast `_run` operation never
        # completed within 5s / 2.3M polls in the same setup, independent
        # of this feature. The real app runs a normal blocking app.exec()
        # event loop, not a polling one, so this is a test-harness
        # limitation, not evidence of a bug in the real threading path.
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            existing = ScanResult(hulls=[Hull("existing_hull", "Existing Hull", "core", Path("fixture"))])
            window = MainWindow()
            window._scan_complete(SimpleNamespace(result=existing, registry=Registry.from_scan(existing)))
            self.assertEqual(1, len(window._visible))

            merged = ScanResult(hulls=[
                Hull("existing_hull", "Existing Hull", "core", Path("fixture")),
                Hull("new_hull", "New Hull", "dropped_mod", Path("fixture")),
            ])
            outcome = SimpleNamespace(result=merged, registry=Registry.from_scan(merged), added_mod_ids=("dropped_mod",), skipped_mod_roots=())

            window._apply_incremental_scan_outcome(outcome)

            self.assertEqual(2, len(window._visible))
            self.assertIn("new_hull", {hull.id for hull in window._visible})
            self.assertEqual("dropped_mod", window._registry.hulls.by_id["new_hull"].source_mod)
            self.assertIn("Incorporated 1 dropped mod", window.statusBar().currentMessage())
            window.close()

    def test_open_selected_candidate_in_advanced_preserves_candidate_state(self) -> None:
        window = MainWindow()
        window._generated_candidates = [{"profile_id": "LINE_ARTILLERY", "variant": {"weapons_by_mount": {}}}]
        window.candidate_cards.clear(); window.candidate_cards.addItem("Candidate"); window.candidate_cards.setCurrentRow(0)
        window._open_selected_in_advanced()
        self.assertEqual("advanced", window.mode_selector.currentData())
        self.assertEqual("LINE_ARTILLERY", window.profile_selector.currentData())
        window.close()

    def test_candidate_preview_passes_weapon_index_for_static_weapon_art(self) -> None:
        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        window._generated_candidates = [{"variant": {"weapons_by_mount": {"A": "gun"}}}]
        with patch("starsector_variant_generator.gui.main_window.format_generation_results", return_value=""), patch.object(window.canvas, "show_hull") as show_hull:
            window._preview_candidate(0)
        show_hull.assert_called_once_with(hull, {"A": "gun"}, registry.weapons.by_id)
        window.close()

    def test_mirror_detection_pairs_symmetric_hardpoints_and_skips_centerline(self) -> None:
        from starsector_variant_generator.gui.main_window import _detect_mirror_mount_pairs

        hull = Hull("hammerhead_like", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "WS 001", "size": "MEDIUM", "type": "BALLISTIC", "mount": "HARDPOINT", "angle": 0, "arc": 10, "locations": [84, 31]},
            {"id": "WS 002", "size": "MEDIUM", "type": "BALLISTIC", "mount": "HARDPOINT", "angle": 0, "arc": 10, "locations": [84, -31]},
            {"id": "WS 005", "size": "SMALL", "type": "HYBRID", "mount": "TURRET", "angle": 45, "arc": 215, "locations": [57, 16]},
            {"id": "WS 006", "size": "SMALL", "type": "HYBRID", "mount": "TURRET", "angle": -45, "arc": 215, "locations": [57, -16]},
            {"id": "WS SPINE", "size": "LARGE", "type": "BALLISTIC", "mount": "HARDPOINT", "angle": 0, "arc": 5, "locations": [90, 0]},
        ))
        pairs = _detect_mirror_mount_pairs(hull)
        self.assertEqual(pairs.get("WS 001"), "WS 002"); self.assertEqual(pairs.get("WS 002"), "WS 001")
        self.assertEqual(pairs.get("WS 005"), "WS 006"); self.assertEqual(pairs.get("WS 006"), "WS 005")
        self.assertNotIn("WS SPINE", pairs)

    def test_mirror_detection_never_pairs_geometrically_distinct_mounts(self) -> None:
        from starsector_variant_generator.gui.main_window import _detect_mirror_mount_pairs

        # Modeled on the real Odyssey: superficially similar (same type/angle)
        # but not true mirror images -- x/y don't negate. Must stay unpaired.
        hull = Hull("odyssey_like", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "WS 002", "size": "LARGE", "type": "ENERGY", "mount": "TURRET", "angle": 90, "arc": 150, "locations": [27, 39]},
            {"id": "WS 003", "size": "LARGE", "type": "ENERGY", "mount": "TURRET", "angle": 90, "arc": 150, "locations": [-42, 27]},
        ))
        self.assertEqual({}, _detect_mirror_mount_pairs(hull))

    def _mirror_test_registry_and_hull(self) -> tuple[Registry, Hull]:
        hull = Hull("h", "Hull", "core", Path("fixture"), hull_size="DESTROYER", ordnance_points=40, weapon_mounts=(
            {"id": "A", "size": "SMALL", "type": "BALLISTIC", "mount": "HARDPOINT", "angle": 0, "arc": 10, "locations": [10, 5]},
            {"id": "B", "size": "SMALL", "type": "BALLISTIC", "mount": "HARDPOINT", "angle": 0, "arc": 10, "locations": [10, -5]},
        ))
        weapon = Weapon("gun", "Gun", "core", Path("fixture"), size="SMALL", mount_type="BALLISTIC", ordnance_points=2)
        scan = ScanResult(hulls=[hull], weapons=[weapon])
        return Registry.from_scan(scan), hull

    def test_mirror_fitting_applies_selection_to_the_detected_partner_mount(self) -> None:
        from unittest.mock import patch

        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        self.assertTrue(window.mirror_fitting.isEnabled())
        window.mirror_fitting.setChecked(True)
        with patch("starsector_variant_generator.gui.main_window.QInputDialog.getItem", return_value=("Gun [gun] — core", True)):
            window._choose_slot("A")
        self.assertEqual("gun", window._fit_weapons.get("A")); self.assertEqual("gun", window._fit_weapons.get("B"))
        with patch("starsector_variant_generator.gui.main_window.QInputDialog.getItem", return_value=("<Empty>", True)):
            window._choose_slot("A")
        self.assertNotIn("A", window._fit_weapons); self.assertNotIn("B", window._fit_weapons)
        window.close()

    def test_mirror_fitting_off_only_changes_the_clicked_mount(self) -> None:
        from unittest.mock import patch

        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        self.assertFalse(window.mirror_fitting.isChecked())
        with patch("starsector_variant_generator.gui.main_window.QInputDialog.getItem", return_value=("Gun [gun] — core", True)):
            window._choose_slot("A")
        self.assertEqual("gun", window._fit_weapons.get("A")); self.assertNotIn("B", window._fit_weapons)
        window.close()

    def test_mirror_checkbox_disabled_with_no_pairs_detected(self) -> None:
        hull = Hull("asym", "Hull", "core", Path("fixture"), weapon_mounts=(
            {"id": "A", "size": "SMALL", "type": "BALLISTIC", "angle": 0, "arc": 10, "locations": [10, 5]},
        ))
        window = MainWindow()
        window._registry = Registry.from_scan(ScanResult(hulls=[hull])); window._visible = (hull,); window._selected_hull(0)
        self.assertFalse(window.mirror_fitting.isEnabled())
        window.close()

    def test_scan_progressed_shows_current_source_and_a_recent_trail(self) -> None:
        # Rather than only an aggregate count, the dialog must show a real,
        # named source currently being processed plus a short trail of
        # recently-finished ones, so a scan reads as visibly moving work
        # instead of a single number that might be frozen.
        window = MainWindow()
        window._scan_progress = QProgressDialog("", "Cancel", 0, 0, window)
        for name in ("Starsector Core", "Adjusted Sector", "Arma Armatura"):
            window._scan_progressed(SimpleNamespace(stage="PARSING", completed_sources=1, total_sources=119, entities_found=10, current_source=name))
        label = window._scan_progress.labelText()
        self.assertIn("Currently scanning: Arma Armatura", label)
        self.assertIn("Recently:", label)
        self.assertIn("Starsector Core", label)
        self.assertIn("Adjusted Sector", label)
        self.assertNotIn("Recently: Starsector Core, Adjusted Sector, Arma Armatura", label)  # current name excluded from the trail
        self.assertIn("Arma Armatura", window.statusBar().currentMessage())
        window.close()

    def test_scan_progressed_does_not_duplicate_consecutive_identical_sources_in_the_trail(self) -> None:
        window = MainWindow()
        window._scan_progress = QProgressDialog("", "Cancel", 0, 0, window)
        # The real scanner emits a "starting" and a "done" event naming the
        # SAME source back to back -- the trail must not grow on that pair.
        window._scan_progressed(SimpleNamespace(stage="FINGERPRINTING", completed_sources=0, total_sources=119, entities_found=0, current_source="Starsector Core"))
        window._scan_progressed(SimpleNamespace(stage="FINGERPRINTING", completed_sources=1, total_sources=119, entities_found=0, current_source="Starsector Core"))
        self.assertEqual(["Starsector Core"], list(window._scan_recent_sources))
        window.close()

    def test_looks_like_starsector_install_requires_a_real_telltale(self) -> None:
        from starsector_variant_generator.gui.main_window import _looks_like_starsector_install

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(_looks_like_starsector_install(root))
            (root / "starsector-core").mkdir()
            self.assertTrue(_looks_like_starsector_install(root))

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "starsector.exe").write_text("", encoding="utf-8")
            self.assertTrue(_looks_like_starsector_install(root))

    def test_no_stored_install_path_does_not_schedule_an_auto_scan(self) -> None:
        # No paths/starsector preference at all (setUp clears QSettings
        # every test) -- constructing MainWindow must not even schedule the
        # auto-scan timer, let alone attempt a scan against an empty path.
        with patch("starsector_variant_generator.gui.main_window.QTimer.singleShot") as scheduled:
            window = MainWindow()
        self.assertFalse(any(call.args and call.args[-1] == window._maybe_auto_scan for call in scheduled.call_args_list))
        window.close()

    def test_stored_invalid_install_path_does_not_schedule_an_auto_scan(self) -> None:
        preferences = self._isolated_preferences()
        preferences.setValue("paths/starsector", r"C:\definitely\not\a\real\starsector\install")
        with patch("starsector_variant_generator.gui.main_window.QTimer.singleShot") as scheduled:
            window = MainWindow()
        self.assertFalse(any(call.args and call.args[-1] == window._maybe_auto_scan for call in scheduled.call_args_list))
        window.close()

    def test_stored_valid_install_path_triggers_an_automatic_scan(self) -> None:
        # A previously-configured, still-valid install path (remembered via
        # the existing paths/starsector preference) should scan on launch
        # instead of sitting idle waiting for a manual click -- the user's
        # explicit "must scan data every time it's restarted" complaint.
        # _maybe_auto_scan is invoked directly rather than waiting for the
        # real 150ms QTimer, matching this test file's established
        # discipline of calling worker/callback methods synchronously
        # instead of relying on real Qt timer/event-loop delivery.
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            preferences = self._isolated_preferences()
            preferences.setValue("paths/starsector", str(root))
            preferences.setValue("paths/output", str(Path(tmp) / "output"))
            window = MainWindow()
            window._maybe_auto_scan()
            self.assertIsNotNone(window._scan_thread)
            self.assertTrue(window.cancel_scan_button.isEnabled())
            window._discard_scan()
            window.close()

    def test_maybe_auto_scan_is_a_no_op_once_a_scan_is_already_underway(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            window._start_scan()
            first_thread = window._scan_thread
            window._maybe_auto_scan()  # must not start a second, competing scan
            self.assertIs(first_thread, window._scan_thread)
            window._discard_scan()
            window.close()

    def test_scan_forwards_include_disabled_mods_checkbox_into_config(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            window.include_disabled_mods.setChecked(True)
            window._start_scan()
            self.assertTrue(window._config.include_disabled_mods)
            window._discard_scan()
            window.close()

    def test_include_disabled_mods_preference_is_restored_on_next_launch(self) -> None:
        preferences = self._isolated_preferences()
        preferences.setValue("scan/include_disabled_mods", True)
        window = MainWindow()
        self.assertTrue(window.include_disabled_mods.isChecked())
        window.close()

    def test_scan_rejects_a_path_that_does_not_look_like_a_starsector_install(self) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            window = MainWindow()
            window.root.setText(tmp)  # An arbitrary empty folder -- not a real install.
            window.output.setText(str(Path(tmp) / "output"))
            with patch("starsector_variant_generator.gui.main_window.QMessageBox.warning") as warn:
                window._start_scan()
            warn.assert_called_once()
            self.assertIn("does not look like a Starsector installation", warn.call_args[0][2])
            self.assertIsNone(window._scan_thread)
            self.assertFalse(window.cancel_scan_button.isEnabled())
            window.close()

    def test_scan_rejects_empty_installation_path_without_disabling_the_scan_button(self) -> None:
        from unittest.mock import patch

        window = MainWindow()
        window.root.setText("")
        with patch("starsector_variant_generator.gui.main_window.QMessageBox.warning") as warn:
            window._start_scan()
        warn.assert_called_once()
        self.assertIsNone(window._scan_thread)
        self.assertTrue(window.scan_button.isEnabled())
        window.close()

    def test_discard_scan_requests_cooperative_cancellation(self) -> None:
        # _scan_finished (which re-enables scan_button once the background
        # QThread actually stops) is exercised by production use and by
        # ScanWorker's own unit-level cancellation test below; verifying
        # real cross-thread QThread teardown timing in a headless unittest
        # is exactly the kind of Qt-internals race this project's existing
        # GUI tests already avoid (no prior test here waits on a live
        # background scan thread either). This test covers what's actually
        # new and deterministic: requesting cancellation sets the real
        # cooperative cancel flag Scanner.scan() checks, immediately and
        # synchronously, regardless of how long the background thread then
        # takes to notice it. ignore_cleanup_errors: a real background
        # thread is started (and never waited on here), so it may still
        # hold this directory's log file open when this block exits.
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            window._start_scan()
            self.assertFalse(window.scan_button.isEnabled())
            self.assertTrue(window.cancel_scan_button.isEnabled())
            window._discard_scan()
            self.assertTrue(window._scan_cancel_event.is_set())
            self.assertFalse(window.cancel_scan_button.isEnabled())
            window.close()

    def test_scan_worker_emits_cancelled_not_failed_on_scan_cancelled(self) -> None:
        # Exercises ScanWorker.run()'s new exception routing directly (no
        # QThread involved -- run() is just a plain method, callable
        # synchronously), proving a cancelled scan reaches the GUI as a
        # calm `cancelled` signal, never the scary `failed`/QMessageBox.
        # critical path a genuine error would trigger.
        from starsector_variant_generator.gui.workers.scan_worker import ScanWorker

        # ignore_cleanup_errors: configure_logging() opens a log file handle
        # that Windows keeps locked past this block's exit even though
        # nothing here needs it anymore -- not a behavior this test is
        # about, so the directory's removal failing is tolerated rather
        # than treated as a test failure.
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            config = AppConfig(root, Path(tmp) / "output", Path(tmp) / "output" / "logs")
            worker = ScanWorker(config, cancel_check=lambda: True)
            outcomes = {"cancelled": 0, "completed": 0, "failed": []}
            worker.cancelled.connect(lambda: outcomes.__setitem__("cancelled", outcomes["cancelled"] + 1))
            worker.completed.connect(lambda _: outcomes.__setitem__("completed", outcomes["completed"] + 1))
            worker.failed.connect(outcomes["failed"].append)
            worker.run()
            self.assertEqual(1, outcomes["cancelled"])
            self.assertEqual(0, outcomes["completed"])
            self.assertEqual([], outcomes["failed"])

    def test_scan_worker_reference_is_retained_for_the_whole_thread_lifetime(self) -> None:
        # QObject.moveToThread() transfers the underlying Qt object's
        # ownership to the target thread but does nothing to keep the
        # *Python* wrapper referenced -- without an explicit instance
        # attribute, the local `worker` variable inside _start_scan goes
        # out of scope the moment the method returns, risking the Python
        # object being garbage-collected while its C++-side QObject is
        # still alive and running in the background thread.
        from starsector_variant_generator.gui.workers.scan_worker import ScanWorker

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            window._start_scan()
            self.assertIsNotNone(window._scan_worker)
            self.assertIsInstance(window._scan_worker, ScanWorker)
            window._discard_scan()
            window.close()

    def test_active_workers_mapping_retains_the_generic_run_worker(self) -> None:
        # Same lifetime hazard as ScanWorker, for the generic _run() path
        # every other background operation (_generate, refit modes, faction
        # analysis, export) uses -- a thread-to-worker mapping keeps each
        # worker referenced for exactly as long as its own thread runs,
        # distinguishing it from any other concurrently in-flight operation.
        window = MainWindow()
        window._run("Working…", lambda: "result", lambda _result: None, window.generate_button)
        self.assertEqual(1, len(window._active_workers))
        thread = next(iter(window._active_workers))
        self.assertIsInstance(window._active_workers[thread], AnalysisWorker)
        window.close()

    def test_terminal_scan_paths_clear_the_retained_worker_reference(self) -> None:
        # _scan_finished is the one real terminal path for every scan
        # outcome (completed/failed/cancelled all route through
        # thread.finished -> _scan_finished, per _start_scan's wiring) --
        # it must release the worker reference this fix added, the same
        # way it already releases _scan_thread/_scan_cancel_event, or the
        # fix would just move the leak from "never released" to "released
        # too late."
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            window._start_scan()
            self.assertIsNotNone(window._scan_worker)
            window._scan_finished()
            self.assertIsNone(window._scan_worker)
            self.assertTrue(window.scan_button.isEnabled())
            window.close()

    def _simulate_scan_in_flight(self, window: "MainWindow") -> None:
        # A placeholder "a scan is currently running" state, deliberately
        # NOT a real _start_scan() call: _scan_finished is only ever
        # connected to a real thread.finished in production, which by
        # definition means the background thread has genuinely stopped by
        # the time it runs. Calling _scan_finished() manually while an
        # actual _start_scan()-launched QThread is still live -- as an
        # earlier version of these tests did -- creates an artificial,
        # unsafe race that is not a production scenario, and segfaulted
        # PySide6's C++ layer directly (QProgressDialog.deleteLater() while
        # the still-running real thread could still touch it). A never-
        # started placeholder QThread is safe to discard the same way.
        window._scan_thread = QThread(window); window._scan_worker = object()
        window._scan_progress = QProgressDialog("", "Cancel", 0, 0, window)
        window.scan_button.setEnabled(False); window.cancel_scan_button.setEnabled(True)

    def test_scan_can_restart_after_successful_completion(self) -> None:
        # _scan_thread is not None: return guards _start_scan against a
        # concurrent scan -- if a terminal path ever failed to clear it,
        # every future scan attempt would silently no-op forever, exactly
        # the "stuck, no way to retry" shape reported against this feature.
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            self._simulate_scan_in_flight(window)
            scan = ScanResult(hulls=[Hull("h", "Hull", "core", Path("fixture"))])
            window._scan_complete(SimpleNamespace(result=scan, registry=Registry.from_scan(scan)))
            window._scan_finished()
            self.assertIsNone(window._scan_thread)
            self.assertTrue(window.scan_button.isEnabled())
            window._start_scan()
            self.assertIsNotNone(window._scan_thread)
            window._discard_scan(); window.close()

    def test_scan_can_restart_after_failure(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            self._simulate_scan_in_flight(window)
            from unittest.mock import patch
            with patch("starsector_variant_generator.gui.main_window.QMessageBox.critical"):
                window._operation_failed("Simulated backend failure")
            window._scan_finished()
            self.assertIsNone(window._scan_thread)
            self.assertTrue(window.scan_button.isEnabled())
            window._start_scan()
            self.assertIsNotNone(window._scan_thread)
            window._discard_scan(); window.close()

    def test_scan_can_restart_after_cancellation(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            self._simulate_scan_in_flight(window)
            window._discard_scan()
            window._scan_finished()
            self.assertIsNone(window._scan_thread)
            self.assertTrue(window.scan_button.isEnabled())
            window._start_scan()
            self.assertIsNotNone(window._scan_thread)
            self.assertFalse(window._scan_discarded)  # a fresh scan is not pre-discarded
            window._discard_scan(); window.close()

    def test_scan_stall_watchdog_logs_last_known_state_once(self) -> None:
        # A genuine stall (no progress event for a long stretch) must be
        # diagnosable from the log without catching it live: last stage,
        # last source, how long ago, and live thread/worker state.
        from unittest.mock import patch

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            window._start_scan()
            window._scan_progressed(SimpleNamespace(stage="PARSING", completed_sources=5, total_sources=119, entities_found=10, current_source="Some Mod"))
            window._scan_last_progress_at -= (_SCAN_STALL_WARNING_INTERVAL_S + 1)  # simulate time passing without a new event
            with patch("starsector_variant_generator.gui.main_window.logging.getLogger") as get_logger:
                window._check_scan_stall()
                get_logger.assert_called_with("svg")
                warning_call = get_logger.return_value.warning.call_args
                self.assertIn("Some Mod", warning_call.args)
                self.assertIn("PARSING", warning_call.args)
            # A second tick without new progress must not log again immediately.
            with patch("starsector_variant_generator.gui.main_window.logging.getLogger") as get_logger:
                window._check_scan_stall()
                get_logger.return_value.warning.assert_not_called()
            window._discard_scan()
            window.close()

    def test_scan_stall_watchdog_is_silent_while_progress_is_recent(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            window._start_scan()
            from unittest.mock import patch
            with patch("starsector_variant_generator.gui.main_window.logging.getLogger") as get_logger:
                window._check_scan_stall()
                get_logger.assert_not_called()
            window._discard_scan()
            window.close()

    def test_scan_watchdog_starts_and_stops_with_the_scan(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            window = MainWindow()
            window.root.setText(str(root)); window.output.setText(str(Path(tmp) / "output"))
            self.assertFalse(window._scan_watchdog.isActive())
            window._start_scan()
            self.assertTrue(window._scan_watchdog.isActive())
            window._scan_finished()
            self.assertFalse(window._scan_watchdog.isActive())
            window.close()

    def test_finish_thread_clears_its_active_workers_entry(self) -> None:
        window = MainWindow()
        window._run("Working…", lambda: "result", lambda _result: None, window.generate_button)
        thread = next(iter(window._active_workers))
        window._finish_thread(thread, window.generate_button)
        self.assertEqual({}, window._active_workers)
        # control.setEnabled(self._registry is not None) -- a fresh window
        # has no registry yet, so the button correctly stays disabled here;
        # what this test actually proves is the mapping cleanup.
        self.assertFalse(window.generate_button.isEnabled())
        window.close()

    def test_scan_worker_run_reaches_the_gui_progress_dialog(self) -> None:
        # Proves the real wiring _start_scan connects (worker.progress ->
        # _scan_progressed) actually delivers a progress event to the
        # dialog, using ScanWorker.run() called directly -- a plain method,
        # not requiring a real background QThread to actually finish (see
        # this file's other worker tests for why that isn't reliably
        # observable in this headless harness).
        from starsector_variant_generator.gui.workers.scan_worker import ScanWorker

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
            config = AppConfig(root, Path(tmp) / "output", Path(tmp) / "output" / "logs")
            window = MainWindow()
            window._scan_progress = QProgressDialog("", "Cancel", 0, 0, window)
            worker = ScanWorker(config)
            worker.progress.connect(window._scan_progressed)
            worker.completed.connect(window._scan_complete)
            worker.run()
            # Last real progress event api.run_scan emits before returning
            # is WRITING_REPORT (Scanner.scan()'s own COMPLETE stage fires
            # earlier, before the post-scan registry/change-impact/report
            # phases) -- this proves a real progress event reached the
            # dialog end-to-end, not any specific stage's exact wording.
            self.assertNotEqual("", window._scan_progress.labelText())
            self.assertIn("Writing Report", window._scan_progress.labelText())
            window.close()

    def test_scan_worker_terminal_signals_always_quit_the_thread(self) -> None:
        # completed/failed/cancelled must each reach thread.quit -- the
        # actual wiring _start_scan sets up -- so a scan can never leave
        # its QThread running forever regardless of which of the three
        # ways it ends. thread.quit is connected FIRST, before the
        # application-level handler, specifically so a raising handler
        # (exercised here with a deliberately fake `None`/"boom" payload)
        # can never prevent the thread from being asked to stop.
        #
        # Constructed directly rather than via the real _start_scan/
        # moveToThread path: once a worker is actually moved to its real
        # thread, Qt's AutoConnection resolution compares the *emitting
        # object's* thread affinity against each receiver's -- which
        # differs for `thread.quit` (affiliated with the thread that
        # created it, i.e. this one) only when something is genuinely
        # running cross-thread. Manually emitting from the main thread
        # after a moveToThread() that was never followed by a real
        # thread.start() produces a queued connection with nothing ever
        # pumping it, an artifact of that specific test shape, confirmed
        # directly (isolated repro: identical wiring emits synchronously
        # and reaches the mock when the worker's affinity was never
        # migrated, and does not when it was moved but never started).
        # Real production code doesn't hit this: worker.run() genuinely
        # executes on the moved thread once thread.start() is called, so
        # every emit is consistently a real cross-thread queued
        # connection there, not this test's artifact.
        from unittest.mock import patch
        from starsector_variant_generator.gui.workers.scan_worker import ScanWorker

        for signal_name, emit_args in (("completed", (None,)), ("failed", ("boom",)), ("cancelled", ())):
            with TemporaryDirectory(ignore_cleanup_errors=True) as tmp, \
                 patch.object(QThread, "quit") as quit_mock, \
                 patch("starsector_variant_generator.gui.main_window.QMessageBox.critical"):
                root = Path(tmp) / "install"; (root / "starsector-core").mkdir(parents=True)
                config = AppConfig(root, Path(tmp) / "output", Path(tmp) / "output" / "logs")
                window = MainWindow()
                thread = QThread(window)
                worker = ScanWorker(config)
                worker.completed.connect(thread.quit); worker.completed.connect(window._scan_complete)
                worker.failed.connect(thread.quit); worker.failed.connect(window._operation_failed)
                worker.cancelled.connect(thread.quit)
                getattr(worker, signal_name).emit(*emit_args)
                quit_mock.assert_called()
                window.close()

    def test_refit_controls_expose_only_backend_supported_choices(self) -> None:
        window = MainWindow()
        self.assertEqual({"BALANCED_IMPROVEMENT", "REDUCE_FLUX", "IMPROVE_ROLE_MATCH", "IMPROVE_LOGISTICS"}, {window.refit_mode_selector.itemData(index) for index in range(window.refit_mode_selector.count())})
        self.assertEqual({"cheapest", "exact", "starsector_style", "adaptive"}, {window.refit_substitution_selector.itemData(index) for index in range(window.refit_substitution_selector.count())})
        window.refit_locked_mounts.setText(" A, B ,, ")
        self.assertEqual(frozenset({"A", "B"}), window._refit_lock_ids(window.refit_locked_mounts))
        window.close()

    def test_choose_slot_reports_a_stale_hull_instead_of_raising(self) -> None:
        # Reproduces a real, previously-unguarded crash: self._current_hull
        # can go stale relative to self._registry (e.g. an incremental
        # dropped-mod incorporation made the displayed hull's id ambiguous
        # after it was selected but before a slot was double-clicked --
        # EntityIndex.build pops a second claimant out of by_id into
        # duplicates, per core/registry.py). api.run_slot_eligible_weapons
        # raises plain ValueError for a hull id no longer in by_id; before
        # this fix, _choose_slot called it completely unguarded, unlike
        # every other backend call in this file (which routes failures
        # through _run/_operation_failed). Confirmed real by calling this
        # directly against a registry that does not contain the selected
        # hull: it used to propagate the ValueError straight out of a Qt
        # slot instead of showing the same QMessageBox.critical every other
        # failure in this window uses.
        from unittest.mock import patch

        stale_hull = Hull("missing_hull", "Missing Hull", "core", Path("fixture"), weapon_mounts=({"id": "A", "size": "SMALL", "type": "BALLISTIC"},))
        window = MainWindow()
        window._current_hull = stale_hull
        window._registry = Registry.from_scan(ScanResult(hulls=[]))  # does not index missing_hull
        with patch("starsector_variant_generator.gui.main_window.QMessageBox.critical") as critical:
            window._choose_slot("A")  # must not raise
        critical.assert_called_once()
        self.assertIn("Hull not found or ambiguous", critical.call_args[0][2])
        self.assertIn("Operation failed", window.statusBar().currentMessage())
        window.close()

    def test_choose_slot_shows_a_wait_cursor_while_computing_eligible_weapons(self) -> None:
        # api.run_slot_eligible_weapons re-classifies faction affinity for
        # every scanned weapon against every scanned faction under
        # STRICT_FACTION (analysis/equipment_affinity.py: O(weapons *
        # factions), and it runs synchronously on the GUI thread because a
        # modal QInputDialog needs its result immediately afterwards -- it
        # can't go through the background-thread _run() pattern used
        # everywhere else without restructuring this into an async flow.
        # Verifies the minimal busy-feedback fix: a wait cursor is set for
        # the duration of that call and always restored afterward, even
        # though the call itself is faked out here (no real registry-scale
        # timing is being asserted, just that the feedback exists).
        from unittest.mock import patch

        from PySide6.QtWidgets import QApplication

        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        observed_cursor: list[bool] = []

        def _fake_eligible(*_args: object, **_kwargs: object) -> list[Weapon]:
            observed_cursor.append(QApplication.overrideCursor() is not None)
            return []

        with patch("starsector_variant_generator.gui.main_window.api.run_slot_eligible_weapons", side_effect=_fake_eligible), \
             patch("starsector_variant_generator.gui.main_window.QInputDialog.getItem", return_value=("<Empty>", True)):
            window._choose_slot("A")
        self.assertEqual([True], observed_cursor)
        self.assertIsNone(QApplication.overrideCursor())  # restored afterward
        window.close()

    def test_registry_write_in_progress_tracks_scan_thread_and_scan_button(self) -> None:
        window = MainWindow()
        self.assertFalse(window._registry_write_in_progress())
        window.scan_button.setEnabled(False)
        self.assertTrue(window._registry_write_in_progress())
        window.scan_button.setEnabled(True)
        self.assertFalse(window._registry_write_in_progress())
        window.close()

    def test_generate_declines_to_start_while_a_registry_write_is_in_progress(self) -> None:
        # The real race this guards: _generate's background worker reads
        # self._registry only when its QThread actually executes, not when
        # Generate Best was clicked -- if a full scan or an incremental
        # dropped-mod incorporation (both disable scan_button while in
        # flight) finishes and reassigns self._registry in between, the
        # generation could silently run against different backend data
        # than what was on screen when the button was pressed, or fail
        # confusingly if the selected hull became ambiguous. Verifies the
        # new guard declines to start _run at all while scan_button is
        # disabled, rather than racing it.
        from unittest.mock import patch

        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        window.scan_button.setEnabled(False)  # simulates an in-flight scan/incorporation
        with patch.object(window, "_run") as run_mock:
            window._generate()
        run_mock.assert_not_called()
        self.assertIn("in progress", window.statusBar().currentMessage())
        window.close()

    def test_refit_action_declines_to_start_while_a_registry_write_is_in_progress(self) -> None:
        from unittest.mock import patch

        registry, _hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry
        item = QListWidgetItem("Variant"); item.setData(Qt.UserRole, "variant_id")
        window.variant_list.clear(); window.variant_list.addItem(item); window.variant_list.setCurrentItem(item)
        window.scan_button.setEnabled(False)
        with patch.object(window, "_run") as run_mock:
            window._compare_refit()
        run_mock.assert_not_called()
        self.assertIn("in progress", window.refit_detail.toPlainText())
        window.close()

    def test_faction_action_declines_to_start_while_a_registry_write_is_in_progress(self) -> None:
        from unittest.mock import patch

        faction = Faction("faction_a", "Faction A", "core", Path("fixture"))
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        window = MainWindow()
        window._registry = registry
        item = QListWidgetItem("Faction A"); item.setData(Qt.UserRole, ("faction_a", "core"))
        window.faction_list.clear(); window.faction_list.addItem(item); window.faction_list.setCurrentItem(item)
        window.scan_button.setEnabled(False)
        with patch.object(window, "_run") as run_mock:
            window._analyze_capability()
        run_mock.assert_not_called()
        self.assertIn("in progress", window.faction_detail.toPlainText())
        window.close()

    def test_export_declines_to_start_while_a_registry_write_is_in_progress(self) -> None:
        from unittest.mock import patch

        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        window.output.setText("some/output/dir")
        window.scan_button.setEnabled(False)
        with patch.object(window, "_run") as run_mock:
            window._export_current()
        run_mock.assert_not_called()
        self.assertIn("in progress", window.statusBar().currentMessage())
        window.close()

    def test_export_requires_an_output_directory(self) -> None:
        # Mirrors _start_scan's own validation of this same field: without
        # it, write_variant's own path.parent.mkdir(parents=True) would
        # silently create output under Path("") (the current working
        # directory) instead of anywhere the user actually chose, with no
        # warning at all.
        from unittest.mock import patch

        registry, hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry; window._visible = (hull,); window._selected_hull(0)
        window.output.setText("")
        with patch("starsector_variant_generator.gui.main_window.QMessageBox.warning") as warn, patch.object(window, "_run") as run_mock:
            window._export_current()
        warn.assert_called_once()
        run_mock.assert_not_called()
        window.close()

    def test_drop_falls_back_to_rescan_message_while_another_operation_is_in_flight(self) -> None:
        # Symmetric half of the same race: dropEvent must not start a new
        # incremental incorporation (which reassigns self._registry) while
        # some other backend read (_generate, _refit, faction analysis,
        # export -- all tracked in self._threads via _run) is already using
        # the current registry.
        from unittest.mock import patch
        from PySide6.QtCore import QMimeData, QPointF, QUrl
        from PySide6.QtGui import QDropEvent
        from PySide6.QtCore import QThread

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            scan = ScanResult(hulls=[Hull("existing_hull", "Existing Hull", "core", Path("fixture"))])
            window = MainWindow()
            window._scan_complete(SimpleNamespace(result=scan, registry=Registry.from_scan(scan)))
            window._config = AppConfig(Path(tmp) / "install", Path(tmp) / "output", Path(tmp) / "output" / "logs")
            in_flight_thread = QThread(window)
            window._threads.add(in_flight_thread)

            mod_dir = Path(tmp) / "dropped_mod"; mod_dir.mkdir()
            (mod_dir / "mod_info.json").write_text('{"id": "dropped_mod", "name": "Dropped Mod"}', encoding="utf-8")
            mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(mod_dir))])
            event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.NoButton, Qt.NoModifier)
            with patch.object(window, "_run") as run_mock:
                window.dropEvent(event)
            run_mock.assert_not_called()
            self.assertIn("rescan to include", window.statusBar().currentMessage())
            window._threads.discard(in_flight_thread)
            window.close()

    def test_fleet_support_generator_rejects_a_scenario_card_with_actionable_guidance(self) -> None:
        from unittest.mock import patch

        registry, _hull = self._mirror_test_registry_and_hull()
        window = MainWindow()
        window._registry = registry
        window._advisor_card_origin = "SCENARIO"
        with patch.object(window, "_run") as run_mock:
            window._generate_support_fit()
        run_mock.assert_not_called()
        self.assertIn("Generate Scenario Fit", window.faction_detail.toPlainText())
        window.close()
