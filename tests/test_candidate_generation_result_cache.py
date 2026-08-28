"""Result-cache reuse for `generate_candidate_alternatives` and
`generate_build_archetype_candidates` (core/result_cache.py wired in via
api.py + generation/candidate.py's fingerprint helpers).

Mirrors tests/test_gap_recommendation_result_cache.py's shape and the same
correctness stance from CLAUDE.md's "Legality vs. quality is a hard
boundary": a hit must return an identical result to a fresh computation, a
real changed input must force recomputation (not merely "the code runs"),
and an incomplete/unsafe context must never be served from -- or written
to -- the cache at all.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from starsector_variant_generator import api
from starsector_variant_generator.generation import candidate as candidate_module
from starsector_variant_generator.generation.candidate import (
    build_archetype_candidates_fingerprint,
    candidate_alternatives_fingerprint,
)
from starsector_variant_generator.core.models import Hull, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.result_cache import AnalysisResultCache, CacheReadiness

SOURCE = Path("fixture")


def _hashed_alternatives_registry(hull_hash: str = "hull-hash-1", pricier_hash: str = "pricier-hash-1") -> Registry:
    """A minimal registry where every entity carries a real source hash --
    the precondition `candidate_alternatives_fingerprint` requires for
    `CACHE_SAFE`. Two mounts and two differently priced eligible weapons so
    a search_depth=1 alternative genuinely differs from the baseline."""
    hull = Hull(
        "hull", "Hull", "core", SOURCE, source_hash=hull_hash, ordnance_points=10,
        weapon_mounts=(
            {"id": "A", "type": "BALLISTIC", "size": "SMALL"},
            {"id": "B", "type": "BALLISTIC", "size": "SMALL"},
        ),
    )
    cheap = Weapon("cheap", "Cheap", "core", SOURCE, source_hash="cheap-hash-1", size="SMALL", mount_type="BALLISTIC", ordnance_points=2)
    pricier = Weapon("pricier", "Pricier", "core", SOURCE, source_hash=pricier_hash, size="SMALL", mount_type="BALLISTIC", ordnance_points=6)
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap, pricier]))


def _multi_mount_build_archetype_registry(missile_hash: str = "missile-hash-1") -> Registry:
    """The same multi-mount build-archetype-eligible fixture as
    tests/test_build_archetypes.py, with real source hashes added."""
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
        Weapon("missile", "Missile", "core", SOURCE, source_hash=missile_hash, size="MEDIUM", mount_type="MISSILE", ordnance_points=5, range=700),
    ]
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=weapons))


class CandidateAlternativesFingerprintTests(unittest.TestCase):
    def test_fully_hashed_context_is_cache_safe(self) -> None:
        registry = _hashed_alternatives_registry()
        fingerprint = candidate_alternatives_fingerprint("hull", "LINE_BRAWLER", registry)
        self.assertEqual(CacheReadiness.CACHE_SAFE, fingerprint.readiness)
        self.assertTrue(fingerprint.reusable())

    def test_missing_source_hash_is_cache_unsafe(self) -> None:
        hull = Hull("hull", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "W", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        fingerprint = candidate_alternatives_fingerprint("hull", "LINE_BRAWLER", registry)
        self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, fingerprint.readiness)
        self.assertFalse(fingerprint.reusable())

    def test_unresolved_hull_is_cache_unsafe(self) -> None:
        registry = _hashed_alternatives_registry()
        fingerprint = candidate_alternatives_fingerprint("does_not_exist", "LINE_BRAWLER", registry)
        self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, fingerprint.readiness)

    def test_two_hulls_sharing_a_source_hash_do_not_collide(self) -> None:
        # AnalysisResultCache.key only hashes the declared context, and its
        # table's real primary key is cache_key alone -- if two different
        # hulls (even ones whose content happens to hash identically)
        # produced the same context hash, the second `put` would silently
        # overwrite the first hull's cached row. hull_id is folded into
        # constraints_hash specifically to prevent this.
        hull_a = Hull("hull_a", "Hull A", "core", SOURCE, source_hash="same-hash", ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        hull_b = Hull("hull_b", "Hull B", "core", SOURCE, source_hash="same-hash", ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "W", "core", SOURCE, source_hash="w-hash", size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        registry = Registry.from_scan(ScanResult(hulls=[hull_a, hull_b], weapons=[weapon]))
        fingerprint_a = candidate_alternatives_fingerprint("hull_a", "LINE_BRAWLER", registry)
        fingerprint_b = candidate_alternatives_fingerprint("hull_b", "LINE_BRAWLER", registry)
        self.assertNotEqual(
            AnalysisResultCache.fingerprint_key(fingerprint_a),
            AnalysisResultCache.fingerprint_key(fingerprint_b),
        )


class CandidateAlternativesResultCacheTests(unittest.TestCase):
    def test_cache_hit_returns_an_identical_result_without_recomputing(self) -> None:
        registry = _hashed_alternatives_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            first = api.run_generate(registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache)
            with mock.patch.object(
                api, "generate_candidate_alternatives",
                wraps=candidate_module.generate_candidate_alternatives,
            ) as spy:
                second = api.run_generate(registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache)
            spy.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(2, len(first.candidates))

    def test_changed_weapon_input_forces_recomputation_not_a_stale_hit(self) -> None:
        registry_before = _hashed_alternatives_registry(pricier_hash="pricier-hash-A")
        registry_after = _hashed_alternatives_registry(pricier_hash="pricier-hash-B")
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_generate(registry_before, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache)
            with mock.patch.object(
                api, "generate_candidate_alternatives",
                wraps=candidate_module.generate_candidate_alternatives,
            ) as spy:
                api.run_generate(registry_after, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache)
            spy.assert_called_once()

    def test_changed_search_depth_forces_recomputation(self) -> None:
        registry = _hashed_alternatives_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_generate(registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache)
            with mock.patch.object(
                api, "generate_candidate_alternatives",
                wraps=candidate_module.generate_candidate_alternatives,
            ) as spy:
                api.run_generate(registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=2, result_cache=cache)
            spy.assert_called_once()

    def test_incomplete_context_is_never_served_or_persisted(self) -> None:
        hull = Hull("hull", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"}, {"id": "B", "type": "BALLISTIC", "size": "SMALL"}))
        cheap = Weapon("cheap", "Cheap", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=2)
        pricier = Weapon("pricier", "Pricier", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=6)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap, pricier]))
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_generate(registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache)
            with mock.patch.object(
                api, "generate_candidate_alternatives",
                wraps=candidate_module.generate_candidate_alternatives,
            ) as spy:
                api.run_generate(registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER", flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache)
            spy.assert_called_once()

    def test_no_result_cache_argument_behaves_exactly_as_before(self) -> None:
        """Every existing caller that doesn't opt in sees zero behavior change."""
        registry = _hashed_alternatives_registry()
        direct = candidate_module.generate_candidate_alternatives(
            "hull", "LINE_BRAWLER", registry, max_candidates=2, search_depth=1, flux_mode="BALANCED",
        )
        via_api = api.run_generate(
            registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER",
            flux_mode="BALANCED", max_candidates=2, search_depth=1,
        ).candidates
        self.assertEqual(tuple(direct), tuple(via_api))


class BuildArchetypeCandidatesFingerprintTests(unittest.TestCase):
    def test_fully_hashed_context_is_cache_safe(self) -> None:
        registry = _multi_mount_build_archetype_registry()
        fingerprint = build_archetype_candidates_fingerprint("multi", registry, "baseline_0.4")
        self.assertEqual(CacheReadiness.CACHE_SAFE, fingerprint.readiness)
        self.assertTrue(fingerprint.reusable())

    def test_missing_source_hash_is_cache_unsafe(self) -> None:
        hull = Hull("multi", "Multi", "core", SOURCE, ordnance_points=50, flux_dissipation=500,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "MEDIUM"},))
        weapon = Weapon("short", "Short", "core", SOURCE, size="MEDIUM", mount_type="BALLISTIC", ordnance_points=5)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        fingerprint = build_archetype_candidates_fingerprint("multi", registry, "baseline_0.4")
        self.assertEqual(CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT, fingerprint.readiness)


class BuildArchetypeCandidatesResultCacheTests(unittest.TestCase):
    def test_cache_hit_returns_an_identical_result_without_recomputing(self) -> None:
        registry = _multi_mount_build_archetype_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            first = api.run_generate(registry, "baseline_0.4", "multi", "guided", result_cache=cache)
            with mock.patch.object(
                api, "generate_build_archetype_candidates",
                wraps=candidate_module.generate_build_archetype_candidates,
            ) as spy:
                second = api.run_generate(registry, "baseline_0.4", "multi", "guided", result_cache=cache)
            spy.assert_not_called()
        self.assertEqual(first, second)
        self.assertTrue(first.build_candidates)

    def test_changed_weapon_input_forces_recomputation_not_a_stale_hit(self) -> None:
        registry_before = _multi_mount_build_archetype_registry(missile_hash="missile-hash-A")
        registry_after = _multi_mount_build_archetype_registry(missile_hash="missile-hash-B")
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_generate(registry_before, "baseline_0.4", "multi", "guided", result_cache=cache)
            with mock.patch.object(
                api, "generate_build_archetype_candidates",
                wraps=candidate_module.generate_build_archetype_candidates,
            ) as spy:
                api.run_generate(registry_after, "baseline_0.4", "multi", "guided", result_cache=cache)
            spy.assert_called_once()

    def test_incomplete_context_is_never_served_or_persisted(self) -> None:
        hull = Hull("multi", "Multi", "core", SOURCE, ordnance_points=50, flux_dissipation=500,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "MEDIUM"}, {"id": "M", "type": "MISSILE", "size": "MEDIUM"}))
        weapons = [
            Weapon("short", "Short", "core", SOURCE, size="MEDIUM", mount_type="BALLISTIC", ordnance_points=5),
            Weapon("missile", "Missile", "core", SOURCE, size="MEDIUM", mount_type="MISSILE", ordnance_points=5),
        ]
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=weapons))
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            api.run_generate(registry, "baseline_0.4", "multi", "guided", result_cache=cache)
            with mock.patch.object(
                api, "generate_build_archetype_candidates",
                wraps=candidate_module.generate_build_archetype_candidates,
            ) as spy:
                api.run_generate(registry, "baseline_0.4", "multi", "guided", result_cache=cache)
            spy.assert_called_once()

    def test_no_result_cache_argument_behaves_exactly_as_before(self) -> None:
        registry = _multi_mount_build_archetype_registry()
        direct = candidate_module.generate_build_archetype_candidates(
            "multi", registry, "baseline_0.4", max_candidates=5, alternatives_per_build=2, search_depth=1,
            allowed_weapon_ids=None, preferred_weapon_ids=None, denied_weapon_ids=None, locked_weapons_by_mount=None,
            empty_mount_ids=None, flux_mode="BALANCED", allowed_hullmod_ids=None, preferred_hullmod_ids=None,
            allowed_wing_ids=None, preferred_wing_ids=None, weapon_role_overrides=None,
        )
        via_api = api.run_generate(registry, "baseline_0.4", "multi", "guided").build_candidates
        self.assertEqual(direct, via_api)


class HeuristicSetFingerprintTests(unittest.TestCase):
    """Regression coverage for threading a real, caller-controlled
    `heuristic_set` down to `allocate_vents_and_capacitors`
    (generation/vent_cap.py) and for keeping the two candidate-generation
    fingerprints honest about it. See generation/candidate.py's module-level
    comment above `CANDIDATE_GENERATION_ADAPTER_VERSION` for the full story:
    this used to be a permanently fixed value baked into the fingerprint
    so that `AnalysisResultCache` never had to distinguish it; now that it
    is real and caller-controlled, the cache MUST distinguish it.
    """

    def test_candidate_alternatives_fingerprint_key_differs_across_heuristic_set(self) -> None:
        registry = _hashed_alternatives_registry()
        fingerprint_a = candidate_alternatives_fingerprint("hull", "LINE_BRAWLER", registry, heuristic_set="baseline_0.2")
        fingerprint_b = candidate_alternatives_fingerprint("hull", "LINE_BRAWLER", registry, heuristic_set="baseline_0.3")
        self.assertEqual("baseline_0.2", fingerprint_a.heuristic_set)
        self.assertEqual("baseline_0.3", fingerprint_b.heuristic_set)
        self.assertNotEqual(
            AnalysisResultCache.fingerprint_key(fingerprint_a),
            AnalysisResultCache.fingerprint_key(fingerprint_b),
        )

    def test_cached_result_under_one_heuristic_set_is_never_served_to_a_different_heuristic_set(self) -> None:
        """The single most important test for this task: a result cached
        while generating under one heuristic_set must never come back for a
        call made under a different heuristic_set, even though hull,
        profile, and every other constraint are identical -- and the
        original heuristic_set's own cache entry must remain independently
        valid and unclobbered afterward. Before this task, this couldn't
        even be expressed: `generate_candidate_alternatives` had no real
        `heuristic_set` input at all, so there was nothing here to go stale
        (the earlier investigation's reason for not wiring FLUX into
        vent_cap without first closing this gap).
        """
        registry = _hashed_alternatives_registry()
        with tempfile.TemporaryDirectory() as temp:
            cache = AnalysisResultCache(Path(temp) / "cache.sqlite")
            first = api.run_generate(
                registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER",
                flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache,
            )
            # A call under a different heuristic_set -- same hull, profile,
            # and every other constraint -- must force a fresh computation,
            # not be served from baseline_0.2's cache entry.
            with mock.patch.object(
                api, "generate_candidate_alternatives",
                wraps=candidate_module.generate_candidate_alternatives,
            ) as spy:
                api.run_generate(
                    registry, "baseline_0.3", "hull", "beginner", profile="LINE_BRAWLER",
                    flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache,
                )
            spy.assert_called_once()
            self.assertEqual("baseline_0.3", spy.call_args.kwargs.get("heuristic_set"))
            # baseline_0.2's own entry must still be independently reusable
            # afterward -- writing the baseline_0.3 result must not have
            # clobbered or evicted it under a colliding cache key.
            with mock.patch.object(
                api, "generate_candidate_alternatives",
                wraps=candidate_module.generate_candidate_alternatives,
            ) as spy_again:
                third = api.run_generate(
                    registry, "baseline_0.2", "hull", "beginner", profile="LINE_BRAWLER",
                    flux_mode="BALANCED", max_candidates=2, search_depth=1, result_cache=cache,
                )
            spy_again.assert_not_called()
        self.assertEqual(first, third)


class VentCapHeuristicSetThreadingTests(unittest.TestCase):
    """Proves the actual plumbing fix, independent of the cache: a real
    `heuristic_set` passed to `generate_candidate_alternatives` reaches
    `allocate_vents_and_capacitors` and can change its output.

    No two entries in `core/heuristics.py::REGISTRY` currently disagree on
    the vent/cap-relevant values (`beginner_flux_target` /
    `balanced_flux_target` / `aggressive_flux_target` have been
    0.90 / 0.75 / 0.55 unchanged since baseline_0.1 through baseline_0.8),
    so this is a correctness/plumbing fix with no currently observable
    difference across real registry entries -- an honest outcome, not a
    gap in this test. To still prove the wiring itself is correct (not just
    that it doesn't crash), this patches `generation.vent_cap.get_heuristic_set`
    with two fake heuristic_set identifiers whose `balanced_flux_target`
    values are deliberately made to differ, and confirms the resulting
    variant's vent count actually differs -- exactly what would happen for
    real the day a registry entry's flux target changes.
    """

    def _flux_registry(self) -> Registry:
        hull = Hull(
            "hull", "Hull", "core", SOURCE, source_hash="hull-hash", hull_size="FRIGATE",
            ordnance_points=20, flux_dissipation=50.0, shield_upkeep=0.0,
            weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},),
        )
        weapon = Weapon(
            "w", "W", "core", SOURCE, source_hash="w-hash", size="SMALL",
            mount_type="BALLISTIC", ordnance_points=2, flux_per_second=100.0,
        )
        return Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))

    def test_vent_allocation_differs_when_the_forwarded_heuristic_set_differs(self) -> None:
        registry = self._flux_registry()

        def fake_get_heuristic_set(identifier: str) -> SimpleNamespace:
            # sustained load = 100/s, hull dissipation = 50 -- a low target
            # (0.10) is already met with 0 vents; a high target (0.99)
            # needs ceil((0.99*100-50)/10)=5 vents, well within FRIGATE's
            # 10-vent cap and the 18 OP left after the 2-OP weapon.
            values = {"balanced_flux_target": 0.99} if identifier == "test_high_target" else {"balanced_flux_target": 0.10}
            return SimpleNamespace(values=values)

        with mock.patch(
            "starsector_variant_generator.generation.vent_cap.get_heuristic_set",
            side_effect=fake_get_heuristic_set,
        ):
            low = candidate_module.generate_candidate_alternatives(
                "hull", "LINE_BRAWLER", registry, max_candidates=1, flux_mode="BALANCED",
                heuristic_set="test_low_target",
            )
            high = candidate_module.generate_candidate_alternatives(
                "hull", "LINE_BRAWLER", registry, max_candidates=1, flux_mode="BALANCED",
                heuristic_set="test_high_target",
            )
        self.assertEqual(0, low[0].variant.flux_vents or 0)
        self.assertEqual(5, high[0].variant.flux_vents)
        self.assertNotEqual(low[0].variant.flux_vents, high[0].variant.flux_vents)


if __name__ == "__main__":
    unittest.main()
