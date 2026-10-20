"""`validate-all` and `acceptance` commands (docs/AUTOMATION_PLAN.md V1.1, V1.2).

Both walk a whole install, so each prints one progress line per finished item (`--quiet` turns it off); `acceptance` also keeps a
resumable checkpoint. Neither writes anywhere but the configured output directory, and neither changes a game or mod file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.analysis.acceptance_baseline import (
    baseline_from_audit,
    compare_with_baseline,
    format_change,
    load_baseline,
    run_acceptance,
)
from starsector_variant_generator.analysis.check_mod import check_mod
from starsector_variant_generator.analysis.validate_all import to_markdown
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.logging import configure_logging
from starsector_variant_generator.core.mod_import import resolve_dropped_mod
from starsector_variant_generator.core.models import ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.safeio import atomic_write_json, atomic_write_text
from starsector_variant_generator.analysis.stale_enabled_mods import format_stale_entry
from starsector_variant_generator.core.scanner import Scanner, enabled_mods_file

COMMANDS = ("validate-all", "acceptance", "check-mod")
VERDICT_EXIT_CODES = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
DEFAULT_BASELINE = Path("generated/reports/acceptance_baseline.json")


def add_parsers(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    validate_all = subparsers.add_parser("validate-all", help="Validate every shipped variant through the legality engine; table by finding code and by mod (JSON and Markdown)")
    validate_all.add_argument("--source", default="all", help="all (default), core, or mod:<id>")
    validate_all.add_argument("--quiet", action="store_true", help="No per-mod progress lines")
    validate_all.add_argument("--all-installed-mods", action="store_true", help="Include installed mods that are not enabled")
    validate_all.add_argument("--starsector-path", type=Path, required=True)
    validate_all.add_argument("--output-dir", type=Path, default=Path("generated"))
    check_mod = subparsers.add_parser("check-mod", help="Read-only JSON verdict (PASS, REVIEW, FAIL) on one mod folder: variant validation and located parse failures; never edits the mod")
    check_mod.add_argument("mod_path", type=Path, help="The mod folder (for example a BridgeForge working copy); a folder wrapping one mod folder is accepted")
    check_mod.add_argument("--context", choices=("core", "enabled"), default="core", help="Judge against the core data only (default) or core plus every enabled mod")
    check_mod.add_argument("--output", type=Path, help="Write the JSON verdict here (not inside the mod folder); default prints it")
    check_mod.add_argument("--starsector-path", type=Path, required=True)
    check_mod.add_argument("--output-dir", type=Path, default=Path("generated"), help="Scan cache and logs")
    acceptance = subparsers.add_parser("acceptance", help="Per-mod acceptance verdicts compared with a baseline file; prints only changes")
    acceptance.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="Baseline verdict file to compare with (read-only unless --write-baseline)")
    acceptance.add_argument("--write-baseline", action="store_true", help="Replace the baseline with this run's verdicts (an explicit, person-run step)")
    acceptance.add_argument("--quiet", action="store_true", help="No per-mod progress lines")
    acceptance.add_argument("--all-installed-mods", action="store_true", help="Judge every installed mod, not only the enabled ones")
    acceptance.add_argument("--chunk-size", type=int, default=8, help="Mods audited per step; each step is checkpointed")
    acceptance.add_argument("--starsector-path", type=Path, required=True)
    acceptance.add_argument("--output-dir", type=Path, default=Path("generated"))


def _scan(args: argparse.Namespace, include_disabled: bool) -> tuple[AppConfig, ScanResult, Registry]:
    config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
    logger = configure_logging(config.log_dir)
    scanner = Scanner(config.starsector_path, logger, cache_dir=config.output_dir / "cache", include_disabled_mods=include_disabled)
    scan = scanner.scan()
    return config, scan, Registry.from_scan(scan)


def _run_validate_all(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    config, scan, registry = _scan(args, args.all_installed_mods)

    def progress(index: int, total: int, mod: str, count: int, seconds: float) -> None:
        if not args.quiet:
            print(f"[{index}/{total}] {mod}: {count} variant(s) ({seconds:.1f}s)", flush=True)

    try:
        report = api.run_validate_all(scan, registry=registry, source=args.source, on_source_done=progress)
    except ValueError as exc:
        parser.error(str(exc))
    report_dir = config.output_dir / "reports"
    json_path, md_path = report_dir / "validate_all.json", report_dir / "validate_all.md"
    atomic_write_json(json_path, report, sort_keys=True)
    atomic_write_text(md_path, to_markdown(report))
    results = report["results"]
    print(f"validate-all {args.source}: {report['variants_validated']} variant(s), {results}")
    print(f"Reports: {json_path} and {md_path}")
    return 1 if isinstance(results, dict) and results.get("ILLEGAL") else 0


def _run_acceptance(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    config, scan, registry = _scan(args, args.all_installed_mods)
    scope = "ALL_INSTALLED" if args.all_installed_mods else "ENABLED_ONLY"
    report_dir = config.output_dir / "reports"
    checkpoint = report_dir / f"acceptance_{scope.lower()}.partial.jsonl"
    report_dir.mkdir(parents=True, exist_ok=True)

    def progress(index: int, total: int, mod: str, classification: str, seconds: float) -> None:
        if not args.quiet:
            print(f"[{index}/{total}] {mod}: {classification} ({seconds:.1f}s)", flush=True)

    enabled_file = enabled_mods_file(config.starsector_path)
    audit = run_acceptance(
        scan, registry, scope=scope, chunk_size=args.chunk_size, checkpoint_path=checkpoint, progress=progress,
        enabled_file=str(enabled_file),
    )
    if audit["resumed_mods"]:
        print(f"Resumed from checkpoint: {len(audit['resumed_mods'])} mod(s) were already finished.")
    for entry in audit["stale_enabled"]:
        print(format_stale_entry(entry))
    full_path = report_dir / f"acceptance_{scope.lower()}.json"
    atomic_write_text(full_path, json.dumps(audit, indent=2, sort_keys=True, default=str))
    current = baseline_from_audit(audit)
    try:
        baseline = load_baseline(args.baseline)
    except ValueError as exc:
        parser.error(str(exc))
    code = 0
    if baseline is None:
        print(f"No baseline at {args.baseline}; run with --write-baseline to record this run. Summary: {audit['summary']['by_classification']}")
    else:
        changes = compare_with_baseline(baseline, current)
        for change in changes:
            print(format_change(change))
        print(f"{len(changes)} change(s) against {args.baseline}; summary: {audit['summary']['by_classification']}")
        code = 1 if any(change["regression"] for change in changes) else 0
    if args.write_baseline:
        atomic_write_json(args.baseline, current, sort_keys=True)
        print(f"Baseline written: {args.baseline}")
    print(f"Full report: {full_path}")
    return code


def _run_check_mod(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    info = resolve_dropped_mod(args.mod_path, args.output_dir / "unused")
    mod_root = info.mod_root or args.mod_path
    if not mod_root.is_dir():
        parser.error(f"{args.mod_path} is not a folder")
    output = args.output
    if output is not None and mod_root.resolve() in output.resolve().parents:
        parser.error("--output must not be inside the mod folder; check-mod never writes there")
    config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
    scanner = Scanner(config.starsector_path, configure_logging(config.log_dir), cache_dir=config.output_dir / "cache", extra_mod_paths=(mod_root,))
    verdict = check_mod(scanner.scan(), mod_root, mod_id=info.mod_id, mod_name=info.mod_name, context=args.context)
    if output is not None:
        atomic_write_json(output, verdict, sort_keys=True)
        print(f"check-mod {verdict['verdict']}: {output}")
    else:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    return VERDICT_EXIT_CODES[verdict["verdict"]]


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "validate-all":
        return _run_validate_all(args, parser)
    if args.command == "check-mod":
        return _run_check_mod(args, parser)
    return _run_acceptance(args, parser)
