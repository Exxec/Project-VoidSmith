"""Measure the read-only lightweight scan without persisting source content.

Use this against a local installation only.  The profile writes aggregate timing
and workload numbers under the explicitly supplied output directory; it never
modifies Starsector or a mod.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from starsector_variant_generator.core.scanner import Scanner


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile VoidSmith's read-only lightweight scan.")
    parser.add_argument("starsector_path", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--include-disabled-mods", action="store_true")
    parser.add_argument("--cold", action="store_true", help="Disable local normalized source snapshots for this benchmark.")
    parser.add_argument("--workers", type=int, default=None, help="Bounded source-parser worker count (default: serial; maximum 8).")
    args = parser.parse_args()
    if not args.starsector_path.is_dir():
        parser.error("starsector_path must be an existing installation directory")
    if args.runs < 1:
        parser.error("--runs must be at least one")

    durations: list[float] = []
    scan_metrics: list[dict[str, object]] = []
    summary: dict[str, object] | None = None
    for _ in range(args.runs):
        started = time.perf_counter()
        cache_dir = None if args.cold else args.output_dir / "cache"
        result = Scanner(
            args.starsector_path, include_disabled_mods=args.include_disabled_mods,
            cache_dir=cache_dir, max_workers=args.workers,
        ).scan()
        durations.append(time.perf_counter() - started)
        if result.scan_metrics is not None:
            scan_metrics.append({
                "stage_seconds": result.scan_metrics.stage_seconds,
                "sources_scanned": result.scan_metrics.sources_scanned,
                "files_hashed": result.scan_metrics.files_hashed,
                "bytes_hashed": result.scan_metrics.bytes_hashed,
                "sources_reused": result.scan_metrics.sources_reused,
                "sources_recomputed": result.scan_metrics.sources_recomputed,
                "parallel_workers": result.scan_metrics.parallel_workers,
                "cache_hit_rate": result.scan_metrics.cache_hit_rate,
            })
        summary = result.report("profile", include_entities=False)

    payload = {
        "schema_version": "scan-performance-profile-0.1",
        "runs": args.runs,
        "seconds": [round(value, 6) for value in durations],
        "median_seconds": round(statistics.median(durations), 6),
        "minimum_seconds": round(min(durations), 6),
        "scan_metrics": scan_metrics,
        "counts": summary["counts"] if summary is not None else {},
        "source_snapshot_cache": "DISABLED_COLD" if args.cold else str(args.output_dir / "cache"),
        "requested_workers": args.workers,
    }
    destination = args.output_dir / "reports" / "scan_performance_profile.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote aggregate read-only scan profile: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
