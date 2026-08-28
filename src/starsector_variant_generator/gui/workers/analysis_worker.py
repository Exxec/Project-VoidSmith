"""Generic worker for already-defined deterministic backend operations."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

# The same logger name `core/logging.py::configure_logging` configures (a
# file handler under the user's chosen output/logs directory). A worker
# constructed before any scan has run may find this logger has no handler
# yet (nothing configured `logging.getLogger("svg")` so far this session);
# Python's logging module still accepts the call in that case, it just has
# nowhere to write until a handler exists -- never raises on its own.
_LOGGER = logging.getLogger("svg")


class AnalysisWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__(); self._operation = operation
    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(self._operation())
        except Exception as exc:  # noqa: BLE001 - worker boundary must return backend failures to Qt.
            # logger.exception() captures the full traceback, not just
            # str(exc) -- the GUI only ever showed the bare message, with no
            # way to see where a failure actually originated afterward.
            _LOGGER.exception("Background operation failed")
            self.failed.emit(str(exc))
