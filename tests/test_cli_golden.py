"""Golden test for the command-line grammar (docs/AUTOMATION_PLAN.md V0.4).

A change to any command's options, choices, defaults or help text changes its hash in tests/cli_golden.json, so a grammar change is
always deliberate: review the diff, then regenerate with `python -m tests.test_cli_golden --write` and explain it in the commit.
The hash is taken over the parser structure, not the rendered --help text, because argparse renders usage differently between
Python 3.11, 3.12 and 3.13+.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unittest
from pathlib import Path

from starsector_variant_generator.cli.main import build_parser

GOLDEN = Path(__file__).with_name("cli_golden.json")


def _describe(action: argparse.Action) -> dict[str, object]:
    return {
        "options": list(action.option_strings),
        "dest": action.dest,
        "nargs": action.nargs,
        "required": action.required,
        "choices": None if action.choices is None or isinstance(action, argparse._SubParsersAction) else [str(c) for c in action.choices],
        "default": None if action.default is None else str(action.default).replace("\\", "/"),
        "type": getattr(action.type, "__name__", None),
        "help": action.help,
    }


def command_hashes(parser: argparse.ArgumentParser, prefix: str = "") -> dict[str, str]:
    """sha256 (first 16 hex) of each command's own arguments, keyed by command path ('save write')."""
    hashes: dict[str, str] = {}
    own = [_describe(a) for a in parser._actions if not isinstance(a, argparse._SubParsersAction)]
    payload = json.dumps({"description": parser.description, "arguments": own}, sort_keys=True)
    hashes[prefix or "(root)"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            helps = {choice.dest: choice.help for choice in action._choices_actions}
            for name, sub in action.choices.items():
                path = f"{prefix} {name}".strip()
                hashes.update(command_hashes(sub, path))
                hashes[path] = hashlib.sha256((hashes[path] + str(helps.get(name))).encode("utf-8")).hexdigest()[:16]
    return hashes


class CliGoldenTests(unittest.TestCase):
    def test_every_command_matches_its_pinned_hash(self) -> None:
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        actual = command_hashes(build_parser())
        self.assertEqual(sorted(expected), sorted(actual), "Commands were added or removed; regenerate with --write after review.")
        changed = sorted(name for name in expected if expected[name] != actual[name])
        self.assertEqual([], changed, "Command line changed; if deliberate run: python -m tests.test_cli_golden --write")

    def test_the_rewrite_capable_commands_are_pinned(self) -> None:
        pinned = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for command in ("export", "refit", "save write", "scan", "validate"):
            self.assertIn(command, pinned)


if __name__ == "__main__":
    if "--write" in sys.argv:
        GOLDEN.write_text(json.dumps(command_hashes(build_parser()), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN}")
    else:
        unittest.main()
