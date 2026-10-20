from __future__ import annotations

import unittest

from starsector_variant_generator.gui.app import _is_cli_invocation


class GuiCliDispatchTests(unittest.TestCase):
    def test_version_and_help_flags_go_to_the_cli(self) -> None:
        self.assertTrue(_is_cli_invocation(["VoidSmith.exe", "--version"]))
        self.assertTrue(_is_cli_invocation(["VoidSmith.exe", "--help"]))

    def test_a_known_command_goes_to_the_cli(self) -> None:
        self.assertTrue(_is_cli_invocation(["VoidSmith.exe", "acceptance", "--help"]))

    def test_no_arguments_or_qt_options_open_the_window(self) -> None:
        self.assertFalse(_is_cli_invocation(["VoidSmith.exe"]))
        self.assertFalse(_is_cli_invocation(["VoidSmith.exe", "--smoke-test"]))
        self.assertFalse(_is_cli_invocation(["VoidSmith.exe", "-platform", "offscreen"]))


if __name__ == "__main__":
    unittest.main()
