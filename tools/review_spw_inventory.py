"""Review an explicitly selected SPW identity inventory against an installation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from starsector_variant_generator.core.spw_inventory import review_spw_inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("installation", type=Path)
    args = parser.parse_args()
    report = review_spw_inventory(args.inventory, args.installation)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "REVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
