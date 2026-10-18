"""`calibration resolve | approve | propose` (docs/AUTOMATION_PLAN.md V2.1 to V2.4).

Sheets are read and written only under the generated folder. `approve` is run by a person who names themselves; nothing here marks
a row approved by itself, and nothing here changes or registers a heuristic set.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from starsector_variant_generator.analysis import calibration_propose, calibration_review
from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.scanner import Scanner

COMMAND = "calibration"
DEFAULT_GENERATED = Path("generated")


def add_parsers(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    root = subparsers.add_parser(COMMAND, help="Review-sheet tooling: resolve names to hull ids with pre-checks, approve ready rows by a named reviewer, propose a heuristic-set candidate")
    actions = root.add_subparsers(dest="calibration_command", required=True)
    for name, help_text in (("resolve", "Resolve display names to scanned hull ids, pre-check equipment and legality, sort ready rows first (writes a new sheet)"),
                            ("propose", "Measure registered heuristic sets against APPROVED rows and write a candidate stub; never registers or tunes")):
        sub = actions.add_parser(name, help=help_text)
        sub.add_argument("sheet", type=Path, help="Review sheet CSV under the generated folder")
        sub.add_argument("--starsector-path", type=Path, required=True)
        sub.add_argument("--generated-dir", type=Path, default=DEFAULT_GENERATED)
        sub.add_argument("--all-installed-mods", action="store_true")
        if name == "resolve":
            sub.add_argument("--output", type=Path, help="New sheet (default: <sheet>.resolved.csv beside it)")
            sub.add_argument("--name-column", default="ship_display")
            sub.add_argument("--loadout-column", default="loadout_text")
            sub.add_argument("--variant-column", default="variant_id", help="Column naming an existing variant to validate (rows without one skip legality)")
        else:
            sub.add_argument("--sets", nargs="*", help="Heuristic set ids to measure (default: all registered)")
            sub.add_argument("--base-set", default="baseline_0.7")
            sub.add_argument("--output-dir", type=Path, help="Where the report and candidate go (default: <generated>/calibration-proposals)")
    approve = actions.add_parser("approve", help="Mark ready rows APPROVED for a named reviewer; rows that failed a pre-check are refused")
    approve.add_argument("sheet", type=Path, help="A resolved sheet under the generated folder")
    approve.add_argument("--reviewer", required=True, help="Your own name; recorded with the date")
    approve.add_argument("--rows", help="Row ids such as 3,5-7 (the row_id column)")
    approve.add_argument("--all-ready", action="store_true", help="Every row with ready_for_review TRUE")
    approve.add_argument("--generated-dir", type=Path, default=DEFAULT_GENERATED)


def _scan(args: argparse.Namespace) -> tuple[ScanResult, Registry]:
    scan = Scanner(args.starsector_path, include_disabled_mods=args.all_installed_mods).scan()
    return scan, Registry.from_scan(scan)


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        if args.calibration_command == "resolve":
            scan, registry = _scan(args)
            output = args.output or args.sheet.with_suffix(".resolved.csv")
            summary = calibration_review.resolve_sheet(
                args.sheet, output, scan, registry, args.generated_dir,
                name_column=args.name_column, loadout_column=args.loadout_column, variant_column=args.variant_column,
            )
        elif args.calibration_command == "approve":
            rows = calibration_review.parse_row_spec(args.rows) if args.rows else None
            summary = calibration_review.approve_rows(args.sheet, args.generated_dir, args.reviewer, rows=rows, all_ready=args.all_ready)
        else:
            scan, registry = _scan(args)
            output_dir = args.output_dir or args.generated_dir / "calibration-proposals"
            summary = calibration_propose.propose(
                args.sheet, scan, registry, args.generated_dir, output_dir,
                set_ids=args.sets, base_set=args.base_set,
            )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2, default=str))
    return 0
