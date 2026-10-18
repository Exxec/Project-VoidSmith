"""Opt-in resource inspection and plan review; backend owns all checks."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSplitter, QTableView, QTabWidget, QVBoxLayout, QWidget)

from starsector_variant_generator import api
from starsector_variant_generator.campaign.edit_plan import EditRequest
from starsector_variant_generator.gui.presentation import format_save_plan, format_save_resources, format_save_write


class SaveResourceTableModel(QAbstractTableModel):
    HEADERS = ('Item', 'Current', 'New value', 'Check')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resources = ()
        self.pending: dict[str, str] = {}
        self.checks = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.resources)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.resources):
            return None
        resource = self.resources[index.row()]
        check = self.checks.get(resource.target)
        if role == Qt.ToolTipRole:
            return check.reason if check else resource.locator.evidence
        if role in (Qt.DisplayRole, Qt.EditRole):
            values = (resource.target, resource.value, self.pending.get(resource.target, ''),
                      check.outcome if check else 'Not planned')
            return values[index.column()] if 0 <= index.column() < len(values) else None
        return None

    def flags(self, index):
        result = super().flags(index)
        if index.isValid() and index.column() == 2:
            result |= Qt.ItemIsEditable
        return result

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid() or index.column() != 2 or not 0 <= index.row() < len(self.resources):
            return False
        self.pending[self.resources[index.row()].target] = str(value).strip()
        self.checks = {}
        self.dataChanged.emit(self.index(0, 0), self.index(max(0, self.rowCount()-1), 3))
        return True

    def set_resources(self, resources):
        self.beginResetModel()
        self.resources, self.pending, self.checks = resources, {}, {}
        self.endResetModel()

    def set_plan(self, plan):
        self.beginResetModel()
        self.checks = {change.target: change for change in plan.changes}
        self.endResetModel()

    def requests(self):
        return tuple(EditRequest(target, int(value)) for target, value in self.pending.items() if value)


class SaveWorkshopWidget(QWidget):
    def __init__(self, runner, installation_path, parent=None, output_dir=None):
        super().__init__(parent)
        self._runner = runner
        self._output_dir = output_dir or (lambda: None)
        self._current_plan = None
        self._installation_path = installation_path
        self._epoch = 0
        self.write_gate = api.run_save_write_gate()
        self.selected_save: Path | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Plans do not modify saves. Write edited copy writes a verified NEW copy below the output directory; your save is never changed.'))
        split = QSplitter(Qt.Horizontal)
        left = QWidget(); controls = QVBoxLayout(left)
        self.choose_button = QPushButton('Choose save directory…')
        self.choose_button.setProperty('readOnlySaveControl', True)
        self.choose_button.clicked.connect(self._choose_save)
        controls.addWidget(self.choose_button)
        self.selected_label = QLabel('No save selected'); self.selected_label.setWordWrap(True)
        controls.addWidget(self.selected_label)
        controls.addStretch()
        tabs = QTabWidget()
        self.overview = QPlainTextEdit(); self.overview.setReadOnly(True)
        tabs.addTab(self.overview, 'Overview')
        resources = QWidget(); rows = QVBoxLayout(resources)
        self.model = SaveResourceTableModel(self)
        self.table = QTableView(); self.table.setModel(self.model)
        rows.addWidget(self.table)
        self.allow_capacity = QCheckBox('Allow capacity uncertainty in this plan; consequences are UNKNOWN')
        self.allow_capacity.toggled.connect(self._invalidate_plan)
        rows.addWidget(self.allow_capacity)
        self.plan_button = QPushButton('Review edit plan'); self.plan_button.setProperty('readOnlySaveControl', True)
        self.plan_button.setEnabled(False)
        self.plan_button.clicked.connect(self.review_plan)
        rows.addWidget(self.plan_button)
        tabs.addTab(resources, 'Resources')
        self.plan_view = QPlainTextEdit(); self.plan_view.setReadOnly(True)
        tabs.addTab(self.plan_view, 'Plan and verify')
        split.addWidget(left); split.addWidget(tabs); split.setSizes([280, 850]); layout.addWidget(split)
        footer = QHBoxLayout()
        footer.addWidget(QLabel('Your original save is not changed. Capacity effects remain UNKNOWN.'), 1)
        self.write_button = QPushButton('Write edited copy'); self.write_button.setEnabled(False)
        self.write_button.setProperty('saveWriteControl', True)
        self.write_button.clicked.connect(self.write_copy)
        footer.addWidget(self.write_button); layout.addLayout(footer)
        self._refresh_write_button()
        self.model.dataChanged.connect(self._invalidate_plan)
        self._invalidate_plan()

    def _invalidate_plan(self, *_args):
        self._epoch += 1
        self._current_plan = None
        self.plan_view.setPlainText('Plan not current. Enter new values and choose Review edit plan.\nWrite gate: ' + self.write_gate.status)
        if hasattr(self, 'write_button'):
            self._refresh_write_button()

    def _choose_save(self):
        selected = QFileDialog.getExistingDirectory(self, 'Choose the save directory to inspect')
        if selected:
            self.inspect_directory(Path(selected))

    def inspect_directory(self, selected: Path):
        self.selected_save = selected
        self.selected_label.setText(str(selected))
        self.model.set_resources(())
        self.plan_button.setEnabled(False)
        self._invalidate_plan()
        self.overview.setPlainText('Inspecting selected save…')
        epoch = self._epoch
        def complete(result):
            if self._epoch != epoch:
                return
            self.overview.setPlainText(format_save_resources(result))
            self.model.set_resources(result.resources)
            self.plan_button.setEnabled(bool(result.resources))
        self._runner('Inspecting selected save read-only', lambda: api.run_save_resources(selected), complete,
                     self.choose_button, cancellable=True)

    def review_plan(self):
        if self.selected_save is None:
            self.plan_view.setPlainText('Choose a save before planning. No files written.')
            return
        try:
            requests = self.model.requests()
        except ValueError:
            self.plan_view.setPlainText('Enter whole-number text for each requested value. No files written.')
            return
        selected = self.selected_save
        if not requests:
            self.plan_view.setPlainText('Enter at least one new value before reviewing a plan. No files written.')
            return
        install = self._installation_path()
        opted_in = self.allow_capacity.isChecked()
        epoch = self._epoch
        def operation():
            catalog = api.run_save_commodity_catalog(install) if install is not None else None
            return api.run_save_edit_plan(selected, requests, catalog, allow_unknown_capacity=opted_in)
        def complete(result):
            if self._epoch != epoch:
                return
            self.model.set_plan(result)
            self._current_plan = result
            self.plan_view.setPlainText(format_save_plan(result))
            self._refresh_write_button()
        self._runner('Reviewing save edit plan; no writes', operation, complete, self.plan_button, cancellable=True)

    def _writable_plan(self):
        """The current plan if every change is ACCEPTED within the saved capacity (the capacity opt-in never enables a write)."""
        plan = self._current_plan
        if plan is None or not plan.changes or any(change.outcome != 'ACCEPTED' for change in plan.changes):
            return None
        return plan

    def _refresh_write_button(self):
        plan, output = self._writable_plan(), self._output_dir()
        self.write_button.setEnabled(plan is not None and output is not None)
        if plan is not None and output is not None:
            self.write_button.setToolTip(f'Writes a verified new copy below {output}. The original save is not changed.')
        elif plan is None:
            self.write_button.setToolTip('Review an edit plan first; every change must be ACCEPTED within the saved capacity. ' + self.write_gate.reason)
        else:
            self.write_button.setToolTip('Choose a safe output directory in Settings / Export.')

    def write_copy(self):
        plan, output = self._writable_plan(), self._output_dir()
        if plan is None or output is None:
            self.plan_view.setPlainText('Nothing to write: review an edit plan with only ACCEPTED changes and set an output directory. No files written.')
            return
        def operation():
            result = api.run_save_edit_write(plan, output)
            again = api.run_save_verify_copy(plan, Path(result.copy_dir)) if result.status == 'WRITTEN' and result.copy_dir else None
            return result, again
        def complete(outcome):
            result, again = outcome
            self._current_plan = None
            self.plan_view.setPlainText(format_save_write(result, again))
            self._refresh_write_button()
        self._runner('Writing a verified copy; the original is not changed', operation, complete, self.write_button)
