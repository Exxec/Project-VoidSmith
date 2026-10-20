"""Optional ``voidsmith-gui`` desktop entry point (``svg-gui`` remains an alias)."""
from __future__ import annotations

import argparse
import sys

HELP_FLAGS = ("--version", "--help", "-h")


def _is_cli_invocation(argv: list[str]) -> bool:
    """True when the first argument asks for the command-line tool (version, help or a command) instead of the window."""
    if len(argv) < 2:
        return False
    if argv[1] in HELP_FLAGS:
        return True
    from starsector_variant_generator.cli.main import build_parser
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return argv[1] in action.choices
    return False


def main() -> int:
    if _is_cli_invocation(sys.argv):
        from starsector_variant_generator.cli.main import main as cli_main
        return cli_main()
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
