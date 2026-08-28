"""Batch-audit enabled and all-installed Starsector mod sources read-only.

Example:
    .venv\\Scripts\\python.exe tools\\audit_complex_hulls.py \
        --starsector-path "C:\\Program Files (x86)\\Fractal Softworks\\Starsector" \
        --output-dir generated
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from starsector_variant_generator.analysis.complex_hull_audit import audit_complex_hulls
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.scanner import Scanner


def _run_audit(starsector_path: Path, include_disabled_mods: bool) -> dict:
    scan = Scanner(starsector_path, logging.getLogger("svg.complex-hull-audit"), include_disabled_mods=include_disabled_mods).scan()
    audit = audit_complex_hulls(scan, Registry.from_scan(scan))
    audit["scan_scope"] = "ALL_INSTALLED" if include_disabled_mods else "ENABLED_ONLY"
    audit["scan_summary"] = {
        "mods": len(scan.mods), "hulls": len(scan.hulls), "variants": len(scan.variants),
        "parser_errors": len(scan.errors), "skipped_entities": len(scan.skipped_entities),
    }
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only complex hull acceptance audit for enabled and disabled installed mods.")
    parser.add_argument("--starsector-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    parser.add_argument("--scope", choices=("both", "enabled", "all"), default="both", help="Scan enabled mods, all installed mods, or both (default).")
    args = parser.parse_args()
    reports_dir = args.output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 0
    scopes = ((False, "enabled"), (True, "all_installed"))
    if args.scope == "enabled":
        scopes = scopes[:1]
    elif args.scope == "all":
        scopes = scopes[1:]
    for include_disabled_mods, name in scopes:
        audit = _run_audit(args.starsector_path, include_disabled_mods)
        destination = reports_dir / f"complex_hull_acceptance_{name}.json"
        destination.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        warning_count = audit["summary"]["warning_count"]
        print(f"{audit['scan_scope']}: {destination} ({warning_count} complex-hull warnings)")
        # Findings are diagnostic, not an application failure: ambiguous/missing
        # child records are deliberately contained by the acceptance matrix.
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
