"""Self-closing offscreen initialization test for the optional desktop GUI."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from starsector_variant_generator.gui.main_window import MainWindow


def main() -> int:
    app = QApplication([]); window = MainWindow(); window.show(); QTimer.singleShot(100, app.quit); return app.exec()

if __name__ == "__main__": raise SystemExit(main())
