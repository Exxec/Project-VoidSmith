"""Extract structural data + baseline behavior for user-selected local benchmarks.

Read-only against game/mod sources, per this project's hard rules -- writes
only under tests/local_fixtures/ and tests/local_results/ (both gitignored;
see tests/local_fixtures/.gitignore). Deliberately does not commit or
print full raw hull data: only the structural fields the local-canonical
test suite (tests/test_canonical_local.py) actually checks (hull size,
mount id/type/size, fighter bay count, hull hints) plus this project's own
computed classifier/legality output -- never descriptions, sprites, tags,
or other copyrighted flavor content.

Create tests/local_fixtures/benchmark_manifest.json from the neutral template
first, then run:
    python tools/build_local_benchmarks.py --starsector-path "C:\\...\\Starsector"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from starsector_variant_generator.analysis.classification import (
    classify_civilian_role,
    classify_hull,
)
from starsector_variant_generator.core.logging import configure_logging
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.scanner import Scanner
from starsector_variant_generator.generation.candidate import (
    generate_conservative_candidate,
)
from starsector_variant_generator.validation.legality import validate_variant

LOCAL_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "local_fixtures"
LOCAL_RESULTS_DIR = Path(__file__).resolve().parent.parent / "tests" / "local_results"
MANIFEST_PATH = LOCAL_FIXTURES_DIR / "benchmark_manifest.json"


def structural_hull_data(hull) -> dict:
    return {
        "hull_size": hull.hull_size,
        "ordnance_points": hull.ordnance_points,
        "fighter_bays": hull.fighter_bays,
        "hull_hints": list(hull.hull_hints),
        "weapon_mounts": [
            {"id": mount.get("id"), "type": mount.get("type"), "size": mount.get("size")}
            for mount in hull.weapon_mounts
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--starsector-path", type=Path, required=True)
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        parser.error("No local benchmark manifest. Copy tests/canonical/benchmark_manifest.template.json to tests/local_fixtures/benchmark_manifest.json and select entities from your own installation.")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["benchmarks"]
    logger = configure_logging(Path("generated") / "logs")
    result = Scanner(args.starsector_path, logger).scan()
    registry = Registry.from_scan(result)

    LOCAL_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    written, missing = 0, []
    for entry in manifest:
        hull_id = entry["local_source_hull_id"]
        benchmark_id = entry["benchmark_id"]
        hull = registry.hulls.by_id.get(hull_id)
        if hull is None:
            reason = "ambiguous across mods" if hull_id in registry.hulls.duplicates else "not found"
            missing.append(f"{benchmark_id} ({hull_id}): {reason}")
            continue

        fixture = structural_hull_data(hull)
        (LOCAL_FIXTURES_DIR / f"{benchmark_id}.generated.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")

        classification = classify_hull(hull)
        civilian = classify_civilian_role(hull)
        baseline = {
            "role_compatibility": classification.role_compatibility,
            "civilian_role_tags": list(civilian.role_tags),
            "conservative_candidate": None,
        }
        if hull.weapon_mounts:
            candidate = generate_conservative_candidate(hull_id, "LINE_BRAWLER", registry)
            assessment = validate_variant(candidate.variant, registry)
            baseline["conservative_candidate"] = {
                "legality": str(candidate.legality),
                "revalidated_legality": str(assessment.result),
            }
        (LOCAL_RESULTS_DIR / f"{benchmark_id}_baseline.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        written += 1

    print(f"Wrote {written}/{len(manifest)} local benchmark fixture(s) to {LOCAL_FIXTURES_DIR}")
    if missing:
        print("Not resolved (source hull not present in this install, or ambiguous):")
        for line in missing:
            print(f"  - {line}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
