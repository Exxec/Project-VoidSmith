"""Worker boundary for read-only backend scans."""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from starsector_variant_generator import api
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.logging import configure_logging
from starsector_variant_generator.core.scanner import ScanCancelled


class ScanWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(object)
    cancelled = Signal()

    def __init__(self, config: AppConfig, cancel_check: Callable[[], bool] | None = None) -> None:
        super().__init__()
        self._config = config
        self._cancel_check = cancel_check

    @Slot()
    def run(self) -> None:
        logger = logging.getLogger("svg")  # fallback if configure_logging itself fails below
        try:
            logger = configure_logging(self._config.log_dir)
            # include_entities=False: the GUI reads outcome.result/outcome.registry
            # directly and never touches outcome.report at all (confirmed: no
            # main_window.py reference to it), so the default include_entities=True
            # would build a full asdict() copy of every scanned entity purely to
            # discard it -- real, wasted CPU/memory on every scan for nothing used.
            self.completed.emit(api.run_scan(self._config, logger, include_disabled_mods=self._config.include_disabled_mods, include_entities=False, progress_callback=self.progress.emit, cancel_check=self._cancel_check))
        except ScanCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - UI boundary: detailed trace remains in logs.
            # logger.exception() captures the full traceback to
            # <output_dir>/logs/svg.log, not just str(exc) -- previously
            # nothing actually wrote the traceback anywhere despite this
            # comment's prior claim that one did.
            logger.exception("Scan failed")
            self.failed.emit(str(exc))
