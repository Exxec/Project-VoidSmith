from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "verify_portable_cli.py"
_SPEC = importlib.util.spec_from_file_location("verify_portable_cli", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
parity = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(parity)

GOOD_HELP = "usage: voidsmith\n  scan  Read data\n  calibration  Calibration\n  acceptance  Acceptance\n"
CALIBRATION_HELP = "  approve  Approve rows\n  resolve  Resolve rows\n"
SOURCE_PATHS = ["acceptance", "calibration", "calibration approve", "calibration resolve", "scan"]


def fake_runner(version_line: str = "voidsmith 0.2.0\n", *, drop: str | None = None, exit_code: int = 0) -> parity.Runner:
    """A stand-in executable that answers the same argument lists the real check sends."""
    root_help = GOOD_HELP.replace("scan", "") if drop == "scan" else GOOD_HELP
    calibration_help = CALIBRATION_HELP.replace("approve", "") if drop == "approve" else CALIBRATION_HELP
    responses: dict[tuple[str, ...], tuple[int, str]] = {
        ("--version",): (0, version_line),
        ("--help",): (exit_code, root_help),
        ("acceptance", "--help"): (0, "usage: voidsmith acceptance\n"),
        ("calibration", "--help"): (0, calibration_help),
    }

    def run(arguments: Sequence[str]) -> tuple[int, str]:
        return responses.get(tuple(arguments), (0, ""))

    return run


class ParityCheckTests(unittest.TestCase):
    def test_matching_version_and_all_commands_pass(self) -> None:
        self.assertEqual([], parity.find_parity_problems(fake_runner(), "0.2.0", SOURCE_PATHS))

    def test_version_that_differs_from_pyproject_fails(self) -> None:
        problems = parity.find_parity_problems(fake_runner("voidsmith 0.1.0\n"), "0.2.0", SOURCE_PATHS)
        self.assertEqual(["executable version 0.1.0 differs from pyproject version 0.2.0"], problems)

    def test_missing_version_line_fails(self) -> None:
        problems = parity.find_parity_problems(fake_runner("Traceback: nothing\n"), "0.2.0", SOURCE_PATHS)
        self.assertTrue(any(problem.startswith("--version failed") for problem in problems))

    def test_missing_top_level_command_is_named(self) -> None:
        problems = parity.find_parity_problems(fake_runner(drop="scan"), "0.2.0", SOURCE_PATHS)
        self.assertEqual(["command missing from executable: scan"], problems)

    def test_missing_subcommand_is_named_with_its_full_path(self) -> None:
        problems = parity.find_parity_problems(fake_runner(drop="approve"), "0.2.0", SOURCE_PATHS)
        self.assertEqual(["command missing from executable: calibration approve"], problems)

    def test_failing_help_is_reported(self) -> None:
        problems = parity.find_parity_problems(fake_runner(exit_code=2), "0.2.0", SOURCE_PATHS)
        self.assertIn("--help failed with exit 2", problems)

    def test_golden_command_paths_exclude_the_root_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            golden = Path(tmp) / "golden.json"
            golden.write_text(json.dumps({"(root)": "a", "scan": "b", "calibration approve": "c"}), encoding="utf-8")
            self.assertEqual(["calibration approve", "scan"], parity.golden_command_paths(golden))

    def test_main_fails_for_a_missing_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(1, parity.main(["--exe", str(Path(tmp) / "VoidSmith.exe")]))


if __name__ == "__main__":
    unittest.main()
