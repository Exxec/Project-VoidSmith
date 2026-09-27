"""Verify a VoidSmith portable archive locally without extracting it."""
from __future__ import annotations

import argparse
from pathlib import Path

from starsector_variant_generator.analysis.release_verification import verify_portable_release
from starsector_variant_generator.analysis.release_chain import verify_release_chain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--checksum")
    parser.add_argument("--release-evidence", help="Optional source/build/gate evidence JSON")
    parser.add_argument("--downloaded-asset", help="Separately downloaded release asset for publication hash check")
    args = parser.parse_args()
    result = verify_portable_release(Path(args.archive), Path(args.checksum) if args.checksum else None)
    print(f"Archive: {result.archive}")
    print(f"Version: {result.version or 'Unavailable'}  Platform: {result.platform or 'Unavailable'}")
    print(f"Checksum: {result.checksum_status}  Inventory: {result.inventory_status}")
    for finding in result.findings:
        print(f"- {finding}")
    if args.release_evidence or args.downloaded_asset:
        chain = verify_release_chain(Path(args.archive),
            Path(args.release_evidence) if args.release_evidence else None,
            Path(args.downloaded_asset) if args.downloaded_asset else None)
        for name, gate in chain["gates"].items():
            print(f"{name}: {gate['state']}")
        for finding in chain["findings"]:
            print(f"- {finding}")
        return 0 if result.passed and not chain["findings"] else 1
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
