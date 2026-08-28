"""Create hash-only local calibration observations from a read-only scan.

This intentionally does not assign GOOD/POOR labels or alter heuristics; a
reviewer supplies those expectations in a separate local label fixture.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from starsector_variant_generator.core.scanner import Scanner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starsector-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-installed-mods", action="store_true")
    parser.add_argument("--kind", choices=("hull", "weapon", "hullmod", "variant"), required=True)
    parser.add_argument("--id", action="append", required=True, help="Stable entity ID to include; repeatable.")
    args = parser.parse_args()
    scan = Scanner(args.starsector_path, include_disabled_mods=args.all_installed_mods).scan()
    collection = {"hull": scan.hulls, "weapon": scan.weapons, "hullmod": scan.hullmods, "variant": scan.variants}[args.kind]
    requested = set(args.id)
    observations: dict[str, dict[str, str]] = {}
    for entity in collection:
        if entity.id in requested and entity.source_hash:
            observations[f"{args.kind}:{entity.source_mod}:{entity.id}"] = {"entity_hash": entity.source_hash}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(observations, indent=2, sort_keys=True), encoding="utf-8")
    missing = requested - {entity.id for entity in collection}
    if missing:
        print(f"Missing requested IDs: {', '.join(sorted(missing))}")
    print(f"Wrote {len(observations)} hash-only observations to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
