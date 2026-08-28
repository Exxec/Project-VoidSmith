from __future__ import annotations

import gc
import unittest
from pathlib import Path

from starsector_variant_generator.analysis.doctrine import _DOCTRINE_CACHE, DoctrineEvidence, analyze_faction_doctrine, doctrine_match
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Faction, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry


class DoctrineTests(unittest.TestCase):
    def test_doctrine_uses_existing_variant_evidence_only(self) -> None:
        faction = Faction("f", "Faction", "mod", Path("f"))
        weapon = Weapon("w", "Weapon", "mod", Path("w"), range=800)
        variant = Variant("v", "Variant", "mod", Path("v"), weapons_by_mount={"A": "w"}, hullmods=("mod_a", "mod_a"))
        evidence = analyze_faction_doctrine(faction, Registry.from_scan(ScanResult(factions=[faction], weapons=[weapon], variants=[variant])))
        self.assertEqual(1, evidence.variants_examined)
        self.assertEqual(800.0, evidence.average_weapon_range)
        self.assertEqual(("mod_a", 2), evidence.repeated_hullmods[0])

    def test_doctrine_evidence_class_is_inferred_mechanics_when_variants_exist(self) -> None:
        """ROADMAP.md Phase 29 (Evidence/Provenance Unification): doctrine
        evidence is a statistical aggregate over real variants (AGENTS.md's
        adapter-layer ladder tier 5), which maps onto the shared
        `EvidenceClass` vocabulary as `INFERRED_MECHANICS` -- a usage
        pattern, never a single hard fact."""
        faction = Faction("f", "Faction", "mod", Path("f"))
        weapon = Weapon("w", "Weapon", "mod", Path("w"), range=800)
        variant = Variant("v", "Variant", "mod", Path("v"), weapons_by_mount={"A": "w"}, hullmods=("mod_a",))
        evidence = analyze_faction_doctrine(faction, Registry.from_scan(ScanResult(factions=[faction], weapons=[weapon], variants=[variant])))
        self.assertEqual(EvidenceClass.INFERRED_MECHANICS, evidence.evidence_class)

    def test_doctrine_evidence_class_is_unknown_with_zero_examined_variants(self) -> None:
        """A faction with no matching variants has no usage pattern to infer
        from at all -- distinct from a real (if weak) inferred pattern, so
        this must report `UNKNOWN` rather than reusing `INFERRED_MECHANICS`
        as if some evidence existed."""
        faction = Faction("f", "Faction", "mod", Path("f"))
        evidence = analyze_faction_doctrine(faction, Registry.from_scan(ScanResult(factions=[faction])))
        self.assertEqual(0, evidence.variants_examined)
        self.assertEqual(EvidenceClass.UNKNOWN, evidence.evidence_class)

    def test_doctrine_match_returns_none_without_examined_variants(self) -> None:
        registry = Registry.from_scan(ScanResult())
        no_evidence = DoctrineEvidence("f", 0, None, (), ())
        candidate = Variant("v", "Variant", "generated", Path("v"), hull_id="h")
        self.assertIsNone(doctrine_match(candidate, registry, no_evidence))

    def test_doctrine_match_rewards_hullmod_overlap_with_evidence(self) -> None:
        weapon = Weapon("w", "Weapon", "mod", Path("w"), range=800)
        registry = Registry.from_scan(ScanResult(weapons=[weapon]))
        evidence = DoctrineEvidence("f", 3, 800.0, (("mod_a", 3),), ())
        aligned = Variant("v1", "V1", "generated", Path("v"), hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("mod_a",))
        misaligned = Variant("v2", "V2", "generated", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        aligned_score = doctrine_match(aligned, registry, evidence)
        misaligned_score = doctrine_match(misaligned, registry, evidence)
        self.assertEqual(1.0, aligned_score)
        self.assertLess(misaligned_score, aligned_score)

    def test_doctrine_match_baseline_0_2_partial_mismatch_is_pinned(self) -> None:
        """Regression anchor for `baseline_0.2`'s exact doctrine_match
        arithmetic (docs/ROADMAP.md Phase 16: "no representative benchmark
        suite covering doctrine_match's heuristic weights"). This pins
        current, real behavior for a partial-mismatch scenario (not just
        the trivial 1.0-match or None-evidence cases already covered
        above) so a future change to the weighting formula is caught,
        exactly like the golden `baseline_0.1` scoring regression test.
        This is deliberately NOT presented as calibration against any
        ground truth -- no labeled "this variant doctrine-matches well"
        dataset exists to calibrate against, so the target here is
        stability of the current, real formula, not correctness against
        an external standard this project has no way to verify.
        """
        weapon = Weapon("w", "Weapon", "mod", Path("w"), range=300)
        registry = Registry.from_scan(ScanResult(weapons=[weapon]))
        evidence = DoctrineEvidence("f", 5, 800.0, (("mod_a", 3), ("mod_b", 2)), ())
        candidate = Variant("v", "V", "generated", Path("v"), hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("mod_a",))
        score = doctrine_match(candidate, registry, evidence, "baseline_0.2")
        self.assertEqual(0.562, score)

    def test_repeated_calls_for_the_same_faction_and_registry_are_cached_and_equal(self) -> None:
        """Regression for a real, live perf finding: a single Gap Recommendation
        Engine retrofit search (`generation/refit.py::improve_quality` via
        `scoring/candidate_score.py::score_candidate`) can call
        `analyze_faction_doctrine` for the exact same (faction, registry) pair
        tens of thousands of times in one run. The memoized second call must
        return an equal result to a fresh computation -- caching must never
        change the answer, only avoid recomputing it."""
        faction = Faction("f", "Faction", "mod", Path("f"))
        weapon = Weapon("w", "Weapon", "mod", Path("w"), range=800)
        variant = Variant("v", "Variant", "mod", Path("v"), weapons_by_mount={"A": "w"}, hullmods=("mod_a",))
        registry = Registry.from_scan(ScanResult(factions=[faction], weapons=[weapon], variants=[variant]))
        first = analyze_faction_doctrine(faction, registry)
        second = analyze_faction_doctrine(faction, registry)
        self.assertEqual(first, second)
        self.assertIs(first, second)  # the cached call returns the exact cached object, not just an equal one

    def test_two_distinct_registries_with_the_same_faction_id_never_share_cached_evidence(self) -> None:
        """The cache is keyed on the real registry object's identity, not just
        `faction.id`/`source_mod` alone -- two unrelated scans that happen to
        reuse the same faction id must never see each other's evidence."""
        faction_a = Faction("f", "Faction", "mod", Path("f"))
        weapon_a = Weapon("w", "Weapon", "mod", Path("w"), range=800)
        variant_a = Variant("va", "VA", "mod", Path("va"), weapons_by_mount={"A": "w"})
        registry_a = Registry.from_scan(ScanResult(factions=[faction_a], weapons=[weapon_a], variants=[variant_a]))

        faction_b = Faction("f", "Faction", "mod", Path("f"))  # same id/source_mod, a different scan entirely
        weapon_b = Weapon("w", "Weapon", "mod", Path("w"), range=200)
        variant_b = Variant("vb1", "VB1", "mod", Path("vb1"), weapons_by_mount={"A": "w"})
        variant_b2 = Variant("vb2", "VB2", "mod", Path("vb2"), weapons_by_mount={"A": "w"})
        registry_b = Registry.from_scan(ScanResult(factions=[faction_b], weapons=[weapon_b], variants=[variant_b, variant_b2]))

        evidence_a = analyze_faction_doctrine(faction_a, registry_a)
        evidence_b = analyze_faction_doctrine(faction_b, registry_b)
        self.assertEqual(1, evidence_a.variants_examined)
        self.assertEqual(800.0, evidence_a.average_weapon_range)
        self.assertEqual(2, evidence_b.variants_examined)
        self.assertEqual(200.0, evidence_b.average_weapon_range)

    def test_a_collected_registry_drops_its_cache_entry_instead_of_leaking(self) -> None:
        """The weakref finalizer must actually fire and remove the entry --
        otherwise a long-running process (the GUI, repeated CLI invocations
        in one interpreter) would grow this cache unbounded."""
        faction = Faction("f", "Faction", "mod", Path("f"))
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        analyze_faction_doctrine(faction, registry)
        self.assertIn(id(registry), _DOCTRINE_CACHE)
        registry_id = id(registry)
        del registry
        gc.collect()
        self.assertNotIn(registry_id, _DOCTRINE_CACHE)


if __name__ == "__main__":
    unittest.main()
