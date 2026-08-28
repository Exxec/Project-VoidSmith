"""Optional ``voidsmith-gui`` desktop entry point (``svg-gui`` remains an alias)."""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit("GUI support is optional. Install it with: pip install -e .[gui]") from exc
    from starsector_variant_generator.gui.main_window import MainWindow
    from starsector_variant_generator.gui.theme import APP_STYLESHEET
    app = QApplication(sys.argv)
    app.setApplicationName("VoidSmith")
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow(); window.show()
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
