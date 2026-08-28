from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from starsector_variant_generator.core.models import (
    ModInfo,
    ScanResult,
    SourceType,
    Weapon,
)
from starsector_variant_generator.core.scan_profiles import (
    create_scan_profile,
    diff_scan_profile,
    import_trios_profile,
    load_scan_profiles,
    save_scan_profiles,
)


def test_scan_profile_is_read_only_snapshot_with_explicit_loadout_diff() -> None:
    root = Path("fixture")
    original = ScanResult(mods=[ModInfo("a", "A", None, root, True, source_type=SourceType.MOD)], weapons=[Weapon("w", "W", "a", root, source_hash="one")])
    profile = create_scan_profile("Baseline", root, original, datetime(2026, 1, 1, tzinfo=UTC))
    changed = ScanResult(mods=[ModInfo("b", "B", None, root, True, source_type=SourceType.MOD)], weapons=[Weapon("w", "W", "a", root, source_hash="two")])
    diff = diff_scan_profile(profile, root, changed)
    assert diff.status == "CHANGED_LOADOUT"
    assert diff.added_mod_ids == ("b",)
    assert diff.removed_mod_ids == ("a",)


def test_scan_profiles_round_trip_only_application_owned_json() -> None:
    root = Path("fixture")
    profile = create_scan_profile("Baseline", root, ScanResult(), datetime(2026, 1, 1, tzinfo=UTC))
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "output" / "scan_profiles.json"
        save_scan_profiles(path, (profile,))
        assert load_scan_profiles(path) == (profile,)


def test_trios_profile_import_is_explicit_read_only_membership_preview() -> None:
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "trios_mod_profiles-v2.json"
        path.write_text('{"modProfiles":[{"name":"Campaign","enabledModVariants":[{"modId":"alpha","smolVariantId":"alpha-1"},{"modId":"beta"}]}]}', encoding="utf-8")
        preview = import_trios_profile(path, "Campaign")
        assert preview.provider == "TriOS"
        assert preview.mod_ids == ("alpha", "beta")
        assert "alpha" in preview.ignored_variant_metadata[0]
