"""Result-cache reuse for `run_gap_recommendations` (core/result_cache.py
wired in via api.py + analysis/gap_recommendation.py's fingerprint helpers).

Covers exactly what CLAUDE.md's "Legality vs. quality is a hard boundary"
correctness stance demands for any cache: a hit must return an identical
result to a fresh computation, a real changed input must force
recomputation (not merely "the code runs"), and an incomplete/unsafe
context must never be served from -- or written to -- the cache at all.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starsector_variant_generator import api
from starsector_variant_generator.analysis import (
    gap_recommendation as gap_recommendation_module,
)
from starsector_variant_generator.analysis.gap_recommendation import (
    CacheReadiness,
    gap_recommendation_fingerprint,
)
from starsector_variant_generator.core.models import Faction, Hull, ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.result_cache import AnalysisResultCache

SOURCE = Path("fixture")


def _hashed_registry(hull_hash: str = "hull-hash-1", faction_hash: str = "faction-hash-1") -> Registry:
    """A minimal registry where every entity carries a real source hash --
    the precondition `gap_recommendation_fingerprint` requires for
    `CACHE_SAFE`."""
    hull = Hull(
        "brawler_hull", "Brawler Hull", "core", SOURCE, source_hash=hull_hash,
        weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(2)),
    )
    faction = Faction("f", "Faction", "core", SOURCE, source_hash=faction_hash, known_hulls=("brawler_hull",))
    return Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))


class GapRecommendationFingerprintTests(unittest.TestCase):
    def test_fully_hashed_context_is_cache_safe(self) -> None:
        registry = _hashed_registry()
        faction = registry.factions.by_id["f"]
        fingerprint = gap_recommendation_fingerprint(faction, registry, "baseline_0.2")
        self.assertEqual(CacheReadiness.CACHE_SAFE, fingerprint.readiness)
        self.assertTrue(fingerprint.reusable())

    def test_missing_source_hash_is_cache_unsafe(self) -> None:
        # Matches the rest of this project's test fixtures, which construct
        # entities without an explicit source_hash (defaults to None).
        hull = Hull("h", "Hull", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        fingerprint = gap_recommendation_fingerprint(faction, registry, "baseline_0.2")
        self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, fingerprint.readiness)
        self.assertFalse(fingerprint.reusable())

    def test_two_factions_over_an_otherwise_identical_registry_do_not_collide(self) -> None:
        # AnalysisResultCache.key only hashes the declared context, and its
        # table's real primary key is cache_key alone -- if two different
        # factions produced the same context hash, the second `put` would
        # silently overwrite the first faction's cached row.
        hull = Hull("h", "Hull", "core", SOURCE, source_hash="hull-hash", weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        faction_a = Faction("a", "Faction A", "core", SOURCE, source_hash="hash-a", known_hulls=("h",))
        faction_b = Faction("b", "Faction B", "core", SOURCE, source_hash="hash-b", known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction_a, faction_b]))
        fingerprint_a = gap_recommendation_fingerprint(faction_a, registry, "baseline_0.2")
        fingerprint_b = gap_recommendation_fingerprint(faction_b, registry, "baseline_0.2")
        self.assertNotEqual(
            AnalysisResultCache.fingerprint_key(fingerprint_a),
            AnalysisResultCache.fingerprint_key(fingerprint_b),
        )


class GapRecommendationResultCacheTests(unittest.TestCase):
    def test_cache_hit_returns_an_identical_result_without_recomputing(self) -> None:
        registry = _hashed_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            first = api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
            with mock.patch.object(
                api, "recommend_gap_solutions",
                wraps=gap_recommendation_module.recommend_gap_solutions,
            ) as spy:
                second = api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
            spy.assert_not_called()
        self.assertEqual(first, second)

    def test_changed_hull_input_forces_recomputation_not_a_stale_hit(self) -> None:
        registry_before = _hashed_registry(hull_hash="hull-hash-A")
        registry_after = _hashed_registry(hull_hash="hull-hash-B")
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_gap_recommendations(registry_before, "f", None, "baseline_0.2", result_cache=cache)
            with mock.patch.object(
                api, "recommend_gap_solutions",
                wraps=gap_recommendation_module.recommend_gap_solutions,
            ) as spy:
                api.run_gap_recommendations(registry_after, "f", None, "baseline_0.2", result_cache=cache)
            spy.assert_called_once()

    def test_changed_heuristic_set_forces_recomputation(self) -> None:
        registry = _hashed_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
            with mock.patch.object(
                api, "recommend_gap_solutions",
                wraps=gap_recommendation_module.recommend_gap_solutions,
            ) as spy:
                api.run_gap_recommendations(registry, "f", None, "baseline_0.5", result_cache=cache)
            spy.assert_called_once()

    def test_incomplete_context_is_never_served_or_persisted(self) -> None:
        # No explicit source_hash anywhere -> CACHE_UNSAFE_INCOMPLETE_CONTEXT.
        # Every call must genuinely recompute; a cache "hit" here would be a
        # silently-wrong reuse of a result whose real inputs were never
        # actually proven unchanged.
        hull = Hull("h", "Hull", "core", SOURCE, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("h",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], factions=[faction]))
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
            with mock.patch.object(
                api, "recommend_gap_solutions",
                wraps=gap_recommendation_module.recommend_gap_solutions,
            ) as spy:
                api.run_gap_recommendations(registry, "f", None, "baseline_0.2", result_cache=cache)
            spy.assert_called_once()

    def test_no_result_cache_argument_behaves_exactly_as_before(self) -> None:
        """Every existing caller that doesn't opt in sees zero behavior change."""
        registry = _hashed_registry()
        direct = gap_recommendation_module.recommend_gap_solutions(registry.factions.by_id["f"], registry, "baseline_0.2")
        via_api = api.run_gap_recommendations(registry, "f", None, "baseline_0.2")
        self.assertEqual(direct, via_api)


if __name__ == "__main__":
    unittest.main()
