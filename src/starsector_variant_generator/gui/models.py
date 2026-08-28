"""Qt table models over normalized backend data.

Extracted from `gui/main_window.py` (Phase 35, GUI modularization) with no
behavior change -- `EntityTableModel` moved here verbatim. It has no
`MainWindow` coupling (it only reads its own constructor arguments and
`set_records` payload) and no external module imported it directly before
this move, so `main_window.py` re-imports the name it still needs rather
than keeping a compatibility re-export purely for its own sake.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QWidget


class EntityTableModel(QAbstractTableModel):
    """Lazy Qt model for normalized data tables; avoids per-cell widgets."""

    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.headers = headers
        self.rows: list[tuple[str, ...]] = []
        self.entities: list[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if role == Qt.DisplayRole and index.isValid():
            return self.rows[index.row()][index.column()]
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return None

    def set_records(self, rows: list[tuple[str, ...]], entities: list[Any]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.entities = entities
        self.endResetModel()
