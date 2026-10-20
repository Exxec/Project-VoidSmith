"""Check a built VoidSmith executable against the source CLI (portable release parity).

The executable must answer `--version` with the pyproject version, and `--help` and `acceptance --help` must succeed. Every command
path pinned in tests/cli_golden.json must still appear in the help of its parent. Any problem exits 1 so a stale or partial
build cannot ship.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PYPROJECT = ROOT / "pyproject.toml"
DEFAULT_GOLDEN = ROOT / "tests" / "cli_golden.json"
ROOT_GOLDEN_KEY = "(root)"
VERSION_LINE = re.compile(r"^voidsmith (\S+)\s*$", re.MULTILINE)
TIMEOUT_SECONDS = 120

Runner = Callable[[Sequence[str]], tuple[int, str]]


def expected_version(pyproject: Path) -> str:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def golden_command_paths(golden: Path) -> list[str]:
    data = json.loads(golden.read_text(encoding="utf-8"))
    return sorted(path for path in data if path != ROOT_GOLDEN_KEY)


def _mentions(help_text: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", help_text) is not None


def find_parity_problems(run: Runner, version_text: str, command_paths: Sequence[str]) -> list[str]:
    """Return the parity problems found through `run`; an empty list means the executable matches the source CLI."""
    problems: list[str] = []
    code, output = run(["--version"])
    match = VERSION_LINE.search(output)
    if code != 0 or match is None:
        problems.append(f"--version failed (exit {code}) or printed no 'voidsmith <version>' line: {output.strip()[:200]!r}")
    elif match.group(1) != version_text:
        problems.append(f"executable version {match.group(1)} differs from pyproject version {version_text}")
    code, root_help = run(["--help"])
    if code != 0:
        problems.append(f"--help failed with exit {code}")
    code, _ = run(["acceptance", "--help"])
    if code != 0:
        problems.append(f"acceptance --help failed with exit {code}")
    helps: dict[str, str] = {"": root_help}
    for path in command_paths:
        words = path.split()
        parent = " ".join(words[:-1])
        if parent not in helps:
            code, helps[parent] = run([*parent.split(), "--help"])
            if code != 0:
                problems.append(f"'{parent} --help' failed with exit {code}")
        if not _mentions(helps[parent], words[-1]):
            problems.append(f"command missing from executable: {path}")
    return problems


def _subprocess_runner(executable: Path) -> Runner:
    def run(arguments: Sequence[str]) -> tuple[int, str]:
        try:
            completed = subprocess.run(
                [str(executable), *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TIMEOUT_SECONDS, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)
        return completed.returncode, completed.stdout + completed.stderr
    return run


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True, help="Built VoidSmith executable to check")
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    args = parser.parse_args(argv)
    if not args.exe.is_file():
        print(f"Executable not found: {args.exe}", file=sys.stderr)
        return 1
    version_text = expected_version(args.pyproject)
    paths = golden_command_paths(args.golden)
    problems = find_parity_problems(_subprocess_runner(args.exe), version_text, paths)
    for problem in problems:
        print(f"PARITY FAIL: {problem}")
    if problems:
        return 1
    print(f"Portable parity OK: voidsmith {version_text}, {len(paths)} golden command path(s) present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
