"""Phase 33 (ROADMAP.md): the real, per-call `CacheReadiness` status
(`CACHE_SAFE` / `CACHE_UNSAFE_INCOMPLETE_CONTEXT` / `CACHE_DISABLED`)
surfaced from `api.run_generate`/`api.run_gap_recommendations`'s real
`AnalysisResultCache` decisions.

`core/result_cache.py`'s `AnalysisContextFingerprint.readiness` already
computed `CACHE_SAFE`/`CACHE_UNSAFE_INCOMPLETE_CONTEXT` internally (used
only to gate `get_fingerprint`/`put_fingerprint`'s reuse -- see
`tests/test_gap_recommendation_result_cache.py` and
`tests/test_candidate_generation_result_cache.py`), but that decision was
never surfaced to a caller or a report, and `CACHE_DISABLED` (no
`AnalysisResultCache` instance supplied at all -- the real path every GUI
call and any direct library caller takes today) was defined but never
produced anywhere. This file proves all three states are now real,
observable outcomes of real `api.py` code paths, not just enum members.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.core.models import Faction, Hull, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.result_cache import (
    AnalysisResultCache,
    CacheReadiness,
    resolve_cache_status,
)

SOURCE = Path("fixture")


class ResolveCacheStatusUnitTests(unittest.TestCase):
    """Direct coverage of the small shared decision helper itself."""

    def test_no_cache_instance_is_disabled(self) -> None:
        self.assertEqual(CacheReadiness.CACHE_DISABLED, resolve_cache_status(None, None))

    def test_no_fingerprint_is_disabled_even_with_a_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            self.assertEqual(CacheReadiness.CACHE_DISABLED, resolve_cache_status(cache, None))

    def test_cache_present_mirrors_fingerprint_readiness(self) -> None:
        from starsector_variant_generator.core.result_cache import AnalysisContextFingerprint
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            safe = AnalysisContextFingerprint("op", ("h",), "baseline_0.2", readiness=CacheReadiness.CACHE_SAFE)
            unsafe = AnalysisContextFingerprint("op", (), "baseline_0.2", readiness=CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT)
            self.assertEqual(CacheReadiness.CACHE_SAFE, resolve_cache_status(cache, safe))
            self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, resolve_cache_status(cache, unsafe))


def _hashed_gap_recommendation_registry() -> Registry:
    hull = Hull(
        "brawler_hull", "Brawler Hull", "core", SOURCE, source_hash="hull-hash-1",
        weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2)),
    )
    faction = Faction("f", "Faction", "core", SOURCE, source_hash="faction-hash-1", known_hulls=("brawler_hull",))
    return Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))


def _incomplete_gap_recommendation_registry() -> Registry:
    # No explicit source_hash anywhere -- the real precondition
    # `gap_recommendation_fingerprint` requires for CACHE_SAFE; matches this
    # project's other test fixtures that omit it entirely.
    hull = Hull("h", "Hull", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
    faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
    return Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))


class GapRecommendationCacheReadinessTests(unittest.TestCase):
    """All three states, produced by real `api.run_gap_recommendations` calls."""

    def test_no_result_cache_argument_is_cache_disabled(self) -> None:
        registry = _hashed_gap_recommendation_registry()
        result = api.run_gap_recommendations(registry, "f", None, "baseline_0.2")
        self.assertEqual(CacheReadiness.CACHE_DISABLED, result.cache_readiness)

    def test_fully_hashed_registry_with_cache_is_cache_safe(self) -> None:
        registry = _hashed_gap_recommendation_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            result = api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
        self.assertEqual(CacheReadiness.CACHE_SAFE, result.cache_readiness)

    def test_cache_safe_on_both_a_fresh_compute_and_a_real_hit(self) -> None:
        """CACHE_SAFE describes context completeness, not hit-vs-miss: a
        first call (miss, computed fresh, then stored) and a second call
        against an unchanged registry (a real hit) must both report
        CACHE_SAFE, and the two results must be identical."""
        registry = _hashed_gap_recommendation_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            first = api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
            second = api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
        self.assertEqual(CacheReadiness.CACHE_SAFE, first.cache_readiness)
        self.assertEqual(CacheReadiness.CACHE_SAFE, second.cache_readiness)
        self.assertEqual(first, second)

    def test_incomplete_context_with_cache_is_cache_unsafe_incomplete_context(self) -> None:
        registry = _incomplete_gap_recommendation_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            result = api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
        self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, result.cache_readiness)

    def test_cache_readiness_survives_asdict_as_a_reportable_plain_value(self) -> None:
        """The whole point of this phase: a report (`asdict(result)`, as
        `cli/main.py`'s `recommend` command already writes) must be able to
        state the real reason, not just carry an opaque Python attribute."""
        registry = _hashed_gap_recommendation_registry()
        result = api.run_gap_recommendations(registry, "f", None, "baseline_0.2")
        payload = dataclasses.asdict(result)
        self.assertEqual("CACHE_DISABLED", payload["cache_readiness"])
        self.assertIsInstance(payload["cache_readiness"], str)  # StrEnum: a real str, JSON-serializable as-is
        self.assertEqual('"CACHE_DISABLED"', json.dumps(payload["cache_readiness"]))


def _hashed_alternatives_registry() -> Registry:
    hull = Hull(
        "hull", "Hull", "core", SOURCE, source_hash="hull-hash-1", ordnance_points=10,
        weapon_mounts=(
            {"id": "A", "type": "BALLISTIC", "size": "SMALL"},
            {"id": "B", "type": "BALLISTIC", "size": "SMALL"},
        ),
    )
    cheap = Weapon("cheap", "Cheap", "core", SOURCE, source_hash="cheap-hash-1", size="SMALL", mount_type="BALLISTIC", ordnance_points=2)
    pricier = Weapon("pricier", "Pricier", "core", SOURCE, source_hash="pricier-hash-1", size="SMALL", mount_type="BALLISTIC", ordnance_points=6)
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap, pricier]))


def _incomplete_alternatives_registry() -> Registry:
    hull = Hull("hull", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=(
        {"id": "A", "type": "BALLISTIC", "size": "SMALL"}, {"id": "B", "type": "BALLISTIC", "size": "SMALL"},
    ))
    cheap = Weapon("cheap", "Cheap", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=2)
    pricier = Weapon("pricier", "Pricier", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=6)
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap, pricier]))


class CandidateAlternativesCacheReadinessTests(unittest.TestCase):
    """All three states via the plain (non-build-archetype) `run_generate` path."""

    def test_no_result_cache_argument_is_cache_disabled(self) -> None:
        registry = _hashed_alternatives_registry()
        outcome = api.run_generate(registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1)
        self.assertEqual(CacheReadiness.CACHE_DISABLED, outcome.cache_readiness)

    def test_fully_hashed_registry_with_cache_is_cache_safe(self) -> None:
        registry = _hashed_alternatives_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            outcome = api.run_generate(
                registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER",
                flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache,
            )
        self.assertEqual(CacheReadiness.CACHE_SAFE, outcome.cache_readiness)

    def test_incomplete_context_with_cache_is_cache_unsafe_incomplete_context(self) -> None:
        registry = _incomplete_alternatives_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            outcome = api.run_generate(
                registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER",
                flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache,
            )
        self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, outcome.cache_readiness)


def _multi_mount_build_archetype_registry() -> Registry:
    hull = Hull(
        "multi", "Multi", "core", SOURCE, source_hash="multi-hash-1", ordnance_points=50, flux_dissipation=500,
        weapon_mounts=(
            {"id": "A", "type": "BALLISTIC", "size": "MEDIUM", "arc": 90},
            {"id": "B", "type": "BALLISTIC", "size": "MEDIUM", "arc": 90},
            {"id": "M", "type": "MISSILE", "size": "MEDIUM", "arc": 180},
        ),
        raw={"armor rating": 900, "hitpoints": 8000, "max speed": 60, "shield type": "OMNI"},
    )
    weapons = [
        Weapon("short", "Short", "core", SOURCE, source_hash="short-hash-1", size="MEDIUM", mount_type="BALLISTIC", ordnance_points=5, range=500),
        Weapon("missile", "Missile", "core", SOURCE, source_hash="missile-hash-1", size="MEDIUM", mount_type="MISSILE", ordnance_points=5, range=700),
    ]
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=weapons))


def _incomplete_multi_mount_build_archetype_registry() -> Registry:
    hull = Hull("multi", "Multi", "core", SOURCE, ordnance_points=50, flux_dissipation=500,
                weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "MEDIUM"},))
    weapon = Weapon("short", "Short", "core", SOURCE, size="MEDIUM", mount_type="BALLISTIC", ordnance_points=5)
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))


class BuildArchetypeCacheReadinessTests(unittest.TestCase):
    """All three states via `run_generate`'s multi-archetype (`--mode guided`) path."""

    def test_no_result_cache_argument_is_cache_disabled(self) -> None:
        registry = _multi_mount_build_archetype_registry()
        outcome = api.run_generate(registry, "baseline_0.4", "multi", "guided")
        self.assertEqual(CacheReadiness.CACHE_DISABLED, outcome.cache_readiness)

    def test_fully_hashed_registry_with_cache_is_cache_safe(self) -> None:
        registry = _multi_mount_build_archetype_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            outcome = api.run_generate(registry, "baseline_0.4", "multi", "guided", result_cache=cache)
        self.assertEqual(CacheReadiness.CACHE_SAFE, outcome.cache_readiness)

    def test_incomplete_context_with_cache_is_cache_unsafe_incomplete_context(self) -> None:
        registry = _incomplete_multi_mount_build_archetype_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            outcome = api.run_generate(registry, "baseline_0.4", "multi", "guided", result_cache=cache)
        self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, outcome.cache_readiness)


if __name__ == "__main__":
    unittest.main()
