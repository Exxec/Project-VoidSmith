from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from starsector_variant_generator.gui.save_workshop import SaveWorkshopWidget
except ImportError:
    QApplication = None
from starsector_variant_generator.campaign.catalog import CommodityCatalog
from test_campaign_edit_plan import synthetic_save, source_hashes


@unittest.skipIf(QApplication is None, 'Optional PySide6 GUI dependency is not installed')
class SaveWorkshopGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = synthetic_save(self.root / 'save')
        def runner(_message, operation, completed, _button, **_kwargs):
            completed(operation())
        self.widget = SaveWorkshopWidget(runner, lambda: None)
        self.addCleanup(self.widget.close)

    def test_inspect_and_plan_smoke_leaves_sources_unchanged_and_write_disabled(self):
        before = source_hashes(self.folder)
        self.widget.inspect_directory(self.folder)
        self.assertIn('READABLE', self.widget.overview.toPlainText())
        model = self.widget.model
        self.assertEqual(model.rowCount(), 3)
        row = next(i for i,r in enumerate(model.resources) if r.target == 'credits')
        self.assertTrue(model.setData(model.index(row,2), '300'))
        self.widget.review_plan()
        self.assertIn('ACCEPTED', self.widget.plan_view.toPlainText())
        self.assertIn('120.0 -> 300', self.widget.plan_view.toPlainText())
        self.assertFalse(self.widget.write_button.isEnabled())
        self.assertIn('output directory', self.widget.write_button.toolTip())  # accepted plan, but no output directory set
        self.assertEqual(source_hashes(self.folder), before)

    def test_refusal_and_capacity_planning_opt_in_are_backend_results(self):
        self.widget.inspect_directory(self.folder)
        model = self.widget.model
        row = next(i for i,r in enumerate(model.resources) if r.target == 'commodity:supplies')
        model.setData(model.index(row,2), '30')
        self.widget.review_plan()
        self.assertIn('REFUSED', self.widget.plan_view.toPlainText())
        catalog = CommodityCatalog('PARSED',frozenset({'supplies'}))
        self.widget._installation_path = lambda: self.root
        with patch('starsector_variant_generator.api.run_save_commodity_catalog',return_value=catalog):
            self.widget.review_plan()
            self.assertIn('ACCEPTED: Within the saved capacity',self.widget.plan_view.toPlainText())  # 30 of capacity 100
            model.setData(model.index(row,2), '101')  # above the saved capacity of 100
            self.widget.review_plan()
            self.assertIn('NOT_DETERMINABLE',self.widget.plan_view.toPlainText())
            self.widget.allow_capacity.setChecked(True)
            self.assertIn('Plan not current',self.widget.plan_view.toPlainText())
            self.widget.review_plan()
        self.assertIn('Capacity planning opt-in: yes',self.widget.plan_view.toPlainText())
        self.assertFalse(self.widget.write_button.isEnabled())

    def test_input_changes_invalidate_plan_and_empty_or_bad_input_writes_nothing(self):
        self.widget.review_plan()
        self.assertIn('Choose a save',self.widget.plan_view.toPlainText())
        self.widget.inspect_directory(self.folder)
        self.widget.review_plan()
        self.assertIn('at least one',self.widget.plan_view.toPlainText())
        model=self.widget.model
        model.setData(model.index(0,2),'bad')
        self.widget.review_plan()
        self.assertIn('whole-number',self.widget.plan_view.toPlainText())
        model.setData(model.index(0,2),'50')
        self.assertIn('Plan not current',self.widget.plan_view.toPlainText())

    def test_stale_result_is_not_adopted(self):
        pending=[]
        self.widget._runner=lambda _message,operation,complete,_button,**_kwargs:pending.append((operation,complete))
        self.widget.inspect_directory(self.folder)
        operation,complete=pending[0]
        result=operation()
        self.widget._invalidate_plan()
        complete(result)
        self.assertEqual(self.widget.model.rowCount(),0)

    @patch('starsector_variant_generator.gui.main_window.MainWindow._start_scan', return_value=None)
    def test_main_window_preview_default_off_and_worker_finishes_without_scan(self, _start_scan):
        # Earlier GUI tests can leave queued auto-scan timers in the shared
        # QApplication. This worker test must not launch a scan or modal dialog.
        from starsector_variant_generator.gui.main_window import MainWindow
        settings=QSettings(str(self.root/'preferences.ini'),QSettings.IniFormat)
        with patch('starsector_variant_generator.gui.main_window.QSettings',return_value=settings):
            window=MainWindow()
        self.addCleanup(window.close)
        self.assertFalse(window.save_workshop_enabled.isChecked())
        self.assertIsNone(window.save_workshop_page)
        window.save_workshop_enabled.setChecked(True)
        widget=window.save_workshop_page
        self.assertIsNotNone(widget)
        widget.inspect_directory(self.folder)
        deadline=monotonic()+5
        while window._threads and monotonic()<deadline:
            self.app.processEvents(); sleep(0.01)
        for thread in tuple(window._threads):
            thread.quit(); thread.wait(2000)
        self.app.processEvents()
        self.assertFalse(window._threads)
        self.assertIn('READABLE',widget.overview.toPlainText())
        self.assertTrue(widget.choose_button.isEnabled())
        self.assertFalse(widget.write_button.isEnabled())
        window.save_workshop_enabled.setChecked(False)
        self.assertFalse(window.workspace_tabs.isTabVisible(window.workspace_tabs.indexOf(widget)))


@unittest.skipIf(QApplication is None, 'Optional PySide6 GUI dependency is not installed')
class SaveWorkshopWriteTests(unittest.TestCase):
    """Write edited copy: enabled only for a fully ACCEPTED plan with an output directory; the backend writer is mocked here."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = synthetic_save(self.root / 'save')
        self.out = self.root / 'out'
        def runner(_message, operation, completed, _button, **_kwargs):
            completed(operation())
        self.widget = SaveWorkshopWidget(runner, lambda: None, output_dir=lambda: self.out)
        self.addCleanup(self.widget.close)
        self.widget.inspect_directory(self.folder)

    def plan(self, target, value):
        model = self.widget.model
        row = next(i for i, r in enumerate(model.resources) if r.target == target)
        model.setData(model.index(row, 2), value)
        self.widget.review_plan()

    def test_button_is_disabled_until_an_accepted_plan_exists_and_after_an_edit(self):
        self.assertFalse(self.widget.write_button.isEnabled())
        self.plan('credits', '300')
        self.assertTrue(self.widget.write_button.isEnabled())
        self.widget.model.setData(self.widget.model.index(0, 2), '1')
        self.assertFalse(self.widget.write_button.isEnabled())

    def test_a_written_copy_is_reverified_and_shown_as_verified_with_the_writer_mocked(self):
        from starsector_variant_generator.campaign.verify import VerificationReport
        from starsector_variant_generator.campaign.writer import SaveWriteResult
        ok = VerificationReport('VERIFIED', True, True, True, (('credits', '120.0', '300.0'),), ())
        written = SaveWriteResult('WRITTEN', 'Verified copy written', str(self.out / 'copy'), ok, ('note',))
        self.plan('credits', '300')
        with patch('starsector_variant_generator.api.run_save_edit_write', return_value=written) as write,                 patch('starsector_variant_generator.api.run_save_verify_copy', return_value=ok) as verify:
            self.widget.write_copy()
        write.assert_called_once()
        self.assertEqual(self.out, write.call_args.args[1])
        verify.assert_called_once()
        text = self.widget.plan_view.toPlainText()
        self.assertIn('WRITE RESULT: WRITTEN', text)
        self.assertIn('VERIFIED', text)
        self.assertNotIn('FAILED_VERIFICATION', text)
        self.assertFalse(self.widget.write_button.isEnabled())  # one plan, one write

    def test_a_failed_reverification_is_reported_as_failed_verification(self):
        from starsector_variant_generator.campaign.verify import VerificationReport
        from starsector_variant_generator.campaign.writer import SaveWriteResult
        ok = VerificationReport('VERIFIED', True, True, True, (), ())
        bad = VerificationReport('FAILED', True, False, True, (), ('credits re-reads as 1',))
        written = SaveWriteResult('WRITTEN', 'Verified copy written', str(self.out / 'copy'), ok, ())
        self.plan('credits', '300')
        with patch('starsector_variant_generator.api.run_save_edit_write', return_value=written),                 patch('starsector_variant_generator.api.run_save_verify_copy', return_value=bad):
            self.widget.write_copy()
        self.assertIn('FAILED_VERIFICATION', self.widget.plan_view.toPlainText())
        self.assertIn('credits re-reads as 1', self.widget.plan_view.toPlainText())

    def test_an_over_capacity_plan_never_enables_or_calls_the_writer_even_with_the_opt_in(self):
        self.widget.allow_capacity.setChecked(True)
        self.plan('credits', '300')
        self.widget.plan_view.setPlainText('')
        row = next(i for i, r in enumerate(self.widget.model.resources) if r.target == 'commodity:supplies')
        catalog = CommodityCatalog('PARSED', frozenset({'supplies'}))
        self.widget._installation_path = lambda: self.root
        self.widget.model.setData(self.widget.model.index(row, 2), '101')
        with patch('starsector_variant_generator.api.run_save_commodity_catalog', return_value=catalog),                 patch('starsector_variant_generator.api.run_save_edit_write') as write:
            self.widget.review_plan()
            self.assertIn('NOT_DETERMINABLE', self.widget.plan_view.toPlainText())
            self.assertFalse(self.widget.write_button.isEnabled())
            self.widget.write_copy()
        write.assert_not_called()
        self.assertIn('Nothing to write', self.widget.plan_view.toPlainText())

    def test_real_backend_writes_a_verified_copy_and_leaves_the_original_untouched(self):
        before = source_hashes(self.folder)
        self.plan('credits', '300')
        self.widget.write_copy()
        text = self.widget.plan_view.toPlainText()
        self.assertIn('WRITE RESULT: WRITTEN', text)
        self.assertIn('VERIFIED', text)
        self.assertNotIn('FAILED_VERIFICATION', text)
        self.assertEqual(before, source_hashes(self.folder))
        self.assertTrue(any(self.out.rglob('campaign.xml')))


if __name__ == '__main__':
    unittest.main()
