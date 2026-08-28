"""Read-only, per-mod acceptance sweep over enabled and/or all installed mods.

Classifies EACH installed mod (never the whole install in aggregate) into
PASS / PASS_WITH_UNKNOWNS / PARTIAL / FAIL -- see
`starsector_variant_generator.analysis.mod_acceptance` for the evidence rules
and the exact meaning of each classification. This is a diagnostic sweep, not
a legality result: `validation/legality.py` remains the sole source of
LEGAL/ILLEGAL/NOT_DETERMINABLE.

This tool is read-only against the configured Starsector installation and
writes only under `--output-dir` (default `generated/`, gitignored). Mirrors
`tools/audit_complex_hulls.py`'s shape.

Example:
    .venv\\Scripts\\python.exe tools\\mod_acceptance_sweep.py \
        --starsector-path "C:\\Program Files (x86)\\Fractal Softworks\\Starsector" \
        --output-dir generated
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from starsector_variant_generator.analysis.mod_acceptance import audit_mod_acceptance
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.scanner import Scanner

_COLUMN_HEADER = f"{'MOD ID':<40} {'CLASSIFICATION':<20} {'HULLS':>6} {'WPN':>6} {'FTR':>5} {'HMOD':>6} {'VAR':>6} {'FAC':>5}"


def _run_sweep(starsector_path: Path, include_disabled_mods: bool) -> dict:
    scan = Scanner(starsector_path, logging.getLogger("svg.mod-acceptance-sweep"), include_disabled_mods=include_disabled_mods).scan()
    audit = audit_mod_acceptance(scan, Registry.from_scan(scan))
    audit["scan_scope"] = "ALL_INSTALLED" if include_disabled_mods else "ENABLED_ONLY"
    audit["scan_summary"] = {
        "mods": len(scan.mods), "hulls": len(scan.hulls), "variants": len(scan.variants),
        "parser_errors": len(scan.errors), "skipped_entities": len(scan.skipped_entities),
    }
    return audit


def _print_summary_table(audit: dict) -> None:
    print(f"\n{audit['scan_scope']}: {audit['summary']['mods_classified']} mod(s) classified "
          f"({', '.join(f'{count} {name}' for name, count in audit['summary']['by_classification'].items())})")
    print(_COLUMN_HEADER)
    print("-" * len(_COLUMN_HEADER))
    for record in audit["records"]:
        counts = record["entity_counts"]
        print(
            f"{record['mod_id']:<40.40} {record['classification']:<20} "
            f"{counts.get('hulls', 0):>6} {counts.get('weapons', 0):>6} {counts.get('fighters', 0):>5} "
            f"{counts.get('hullmods', 0):>6} {counts.get('variants', 0):>6} {counts.get('factions', 0):>5}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only per-mod acceptance sweep for enabled and/or all installed mods.")
    parser.add_argument("--starsector-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    parser.add_argument("--scope", choices=("both", "enabled", "all"), default="both", help="Scan enabled mods, all installed mods, or both (default).")
    args = parser.parse_args()
    reports_dir = args.output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    scopes = ((False, "enabled"), (True, "all_installed"))
    if args.scope == "enabled":
        scopes = scopes[:1]
    elif args.scope == "all":
        scopes = scopes[1:]
    for include_disabled_mods, name in scopes:
        audit = _run_sweep(args.starsector_path, include_disabled_mods)
        destination = reports_dir / f"mod_acceptance_sweep_{name}.json"
        destination.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        _print_summary_table(audit)
        print(f"\nFull report: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
