"""Create a local, hash-bound release-chain sidecar after packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Release evidence output already exists")
    commit = _git("rev-parse", "HEAD")
    clean = not _git("status", "--porcelain")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    payload = {
        "schema_version": "voidsmith-release-chain-1",
        "archive_sha256": archive_hash,
        "source": {"commit": commit, "clean": clean,
                   "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None},
        "gates": {"build": {"state": "PASS", "date": datetime.now(UTC).date().isoformat(),
                            "evidence": f"{archive.name} sha256:{archive_hash}"},
                  "tests": {"state": "NOT_RUN"}, "native": {"state": "NOT_RUN"},
                  "live": {"state": "NOT_RUN"}, "rights": {"state": "UNKNOWN"},
                  "publication": {"state": "NOT_RUN"}},
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
