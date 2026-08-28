"""Build a review queue from a scan report without changing game/mod files."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: build_issue_inventory.py <scan-report.json> <output.md>")
        return 2
    report_path, output_path = map(Path, sys.argv[1:])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    errors = report.get("errors", []) + report.get("skipped_entities", [])
    categories = Counter()
    for error in errors:
        if error.startswith("Malformed mod metadata"):
            categories["mod metadata format"] += 1
        elif error.startswith("Enabled mod not discovered"):
            categories["enabled mod unavailable"] += 1
        elif ".faction" in error:
            categories["faction format"] += 1
        elif "mod_info.json" in error:
            categories["mod metadata format"] += 1
        elif ".variant" in error:
            categories["variant format"] += 1
        else:
            categories["other parse error"] += 1
    lines = [
        "# Malformed and nonstandard file review queue", "",
        "Derived from the current read-only scan report. These are not source-file defects until their format is verified; no source data has been changed.", "",
        "## Summary", "",
        f"- Total review items: {len(errors)}",
    ]
    lines.extend(f"- {category}: {count}" for category, count in sorted(categories.items()))
    lines.extend(["", "## Files", ""])
    lines.extend(f"- [ ] `{error}`" for error in errors)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
