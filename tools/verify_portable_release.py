"""Verify a VoidSmith portable archive locally without extracting it."""
from __future__ import annotations

import argparse
from pathlib import Path

from starsector_variant_generator.analysis.release_verification import verify_portable_release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--checksum")
    args = parser.parse_args()
    result = verify_portable_release(Path(args.archive), Path(args.checksum) if args.checksum else None)
    print(f"Archive: {result.archive}")
    print(f"Version: {result.version or 'Unavailable'}  Platform: {result.platform or 'Unavailable'}")
    print(f"Checksum: {result.checksum_status}  Inventory: {result.inventory_status}")
    for finding in result.findings:
        print(f"- {finding}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
