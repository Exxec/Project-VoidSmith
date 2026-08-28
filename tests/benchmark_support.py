"""Shared loading/helpers for the synthetic + local-canonical benchmark suites.

See tests/fixtures/synthetic/*.json (hand-authored, invented values -- not
copied game data). Optional local canonical benchmarks are selected only by a
user-created manifest under tests/local_fixtures/, outside version control.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starsector_variant_generator.core.models import Hull, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry

SYNTHETIC_DIR = Path(__file__).parent / "fixtures" / "synthetic"
LOCAL_FIXTURES_DIR = Path(__file__).parent / "local_fixtures"
LOCAL_RESULTS_DIR = Path(__file__).parent / "local_results"
CANONICAL_MANIFEST = LOCAL_FIXTURES_DIR / "benchmark_manifest.json"


def load_synthetic_archetype(name: str) -> tuple[Hull, list[Weapon]]:
    """Load one tests/fixtures/synthetic/<name>.json into real Hull/Weapon objects."""
    path = SYNTHETIC_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    hull_data = dict(data["hull"])
    hull_data["weapon_mounts"] = tuple(dict(mount) for mount in hull_data.get("weapon_mounts", ()))
    hull_data["launch_bay_slots"] = tuple(hull_data.get("launch_bay_slots", ()))
    hull = Hull(source_mod="benchmark", source_path=path, **hull_data)
    weapons = [Weapon(source_mod="benchmark", source_path=path, **weapon_data) for weapon_data in data.get("weapons", [])]
    return hull, weapons


def registry_for(hull: Hull, weapons: list[Weapon]) -> Registry:
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=weapons))


def mount_classes(hull: Hull) -> set[str]:
    """`"{SIZE}_{TYPE}"` per mount, e.g. `"SMALL_BALLISTIC"` -- the vocabulary
    tests/canonical/benchmark_manifest.json's `expected_mount_classes` uses."""
    return {
        f"{str(mount.get('size', '')).upper()}_{str(mount.get('type', '')).upper()}"
        for mount in hull.weapon_mounts
    }


def load_canonical_manifest() -> list[dict[str, Any]]:
    if not CANONICAL_MANIFEST.exists():
        return []
    return json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))["benchmarks"]


def local_fixture_path(benchmark_id: str) -> Path:
    return LOCAL_FIXTURES_DIR / f"{benchmark_id}.generated.json"


def load_local_fixture(benchmark_id: str) -> dict[str, Any] | None:
    path = local_fixture_path(benchmark_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
