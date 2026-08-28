from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.candidate import generate_candidate_alternatives, generate_conservative_candidate
from starsector_variant_generator.validation.legality import LegalityResult


class GenerationTests(unittest.TestCase):
    def test_conservative_candidate_is_deterministic_and_legal(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},))
        cheap = Weapon("cheap", "Cheap", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        expensive = Weapon("expensive", "Expensive", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=11, range=1000)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap, expensive]))
        result = generate_conservative_candidate("hull", "LINE_ARTILLERY", registry)
        self.assertEqual(LegalityResult.LEGAL, result.legality)
        self.assertEqual({"WS 1": "cheap"}, result.variant.weapons_by_mount)

    def test_strict_faction_allow_list_is_hard_candidate_filter(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},))
        allowed = Weapon("allowed", "Allowed", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        other = Weapon("other", "Other", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=1)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[allowed, other]))
        result = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, {"allowed"})
        self.assertEqual({"WS 1": "allowed"}, result.variant.weapons_by_mount)

    def test_faction_plus_prefers_explicit_native_evidence_but_can_fallback(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},))
        native = Weapon("native", "Native", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        fallback = Weapon("fallback", "Fallback", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=1)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[native, fallback]))
        preferred = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, preferred_weapon_ids={"native"})
        self.assertEqual({"WS 1": "native"}, preferred.variant.weapons_by_mount)
        fallback_only = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, preferred_weapon_ids={"not-compatible"})
        self.assertEqual({"WS 1": "fallback"}, fallback_only.variant.weapons_by_mount)

    def test_advanced_locks_and_empty_mounts_are_constraints_not_legality_claims(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=(
            {"id": "A", "type": "BALLISTIC", "size": "SMALL"}, {"id": "B", "type": "BALLISTIC", "size": "SMALL"},
        ))
        weapon = Weapon("weapon", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        result = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, locked_weapons_by_mount={"A": "weapon"}, empty_mount_ids={"B"})
        self.assertEqual({"A": "weapon"}, result.variant.weapons_by_mount)
        self.assertIn("B: explicitly left empty by advanced request", result.omissions)

    def test_bounded_alternatives_are_distinct_deterministic_and_independently_legal(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=(
            {"id": "A", "type": "BALLISTIC", "size": "SMALL"},
        ))
        first = Weapon("first", "First", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=900)
        second = Weapon("second", "Second", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=4, range=700)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[first, second]))
        results = generate_candidate_alternatives("hull", "LINE_ARTILLERY", registry, max_candidates=5)
        self.assertEqual(2, len(results))
        self.assertEqual(["first", "second"], [result.variant.weapons_by_mount["A"] for result in results])
        self.assertEqual([LegalityResult.LEGAL, LegalityResult.LEGAL], [result.legality for result in results])
        self.assertEqual(["hull_LINE_ARTILLERY_svg", "hull_LINE_ARTILLERY_svg_alt1"], [result.variant.id for result in results])

    def test_candidate_search_rejects_nonpositive_bound(self) -> None:
        registry = Registry.from_scan(ScanResult())
        with self.assertRaises(ValueError):
            generate_candidate_alternatives("hull", "LINE_BRAWLER", registry, max_candidates=0)

    def test_candidate_search_rejects_nonpositive_search_depth(self) -> None:
        registry = Registry.from_scan(ScanResult())
        with self.assertRaises(ValueError):
            generate_candidate_alternatives("hull", "LINE_BRAWLER", registry, search_depth=0)

    def test_search_depth_one_is_byte_identical_to_the_original_bound(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        first = Weapon("first", "First", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=900)
        second = Weapon("second", "Second", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=4, range=700)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[first, second]))
        default_depth = generate_candidate_alternatives("hull", "LINE_ARTILLERY", registry, max_candidates=5)
        explicit_depth_one = generate_candidate_alternatives("hull", "LINE_ARTILLERY", registry, max_candidates=5, search_depth=1)
        self.assertEqual(
            [c.variant.weapons_by_mount for c in default_depth],
            [c.variant.weapons_by_mount for c in explicit_depth_one],
        )

    def test_deeper_search_reaches_a_third_ranked_weapon_a_single_alternate_rank_cannot(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapons = [Weapon(f"w{i}", f"W{i}", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=i + 1) for i in range(4)]
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=weapons))
        shallow = generate_candidate_alternatives("hull", "LINE_BRAWLER", registry, max_candidates=10, search_depth=1)
        deep = generate_candidate_alternatives("hull", "LINE_BRAWLER", registry, max_candidates=10, search_depth=3)
        self.assertEqual(2, len(shallow))  # baseline (w0) + one alternate rank (w1)
        self.assertEqual(4, len(deep))  # baseline plus ranks for w1, w2, w3
        self.assertEqual(
            ["w0", "w1", "w2", "w3"],
            [c.variant.weapons_by_mount["A"] for c in deep],
        )
        self.assertTrue(all(c.legality == LegalityResult.LEGAL for c in deep))

    def test_generated_candidate_with_full_flux_data_allocates_vents_and_stays_legal(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), hull_size="FRIGATE", ordnance_points=20,
                    weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},),
                    flux_dissipation=50.0, shield_upkeep=0.0)
        weapon = Weapon("gun", "Gun", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500, flux_per_second=100.0)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        result = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, flux_mode="BALANCED")
        self.assertEqual(LegalityResult.LEGAL, result.legality)
        self.assertIsNotNone(result.variant.flux_vents)
        self.assertGreater(result.variant.flux_vents, 0)

    def test_baseline_0_10_end_to_end_allocates_fewer_vents_for_a_candidate_that_installs_fluxdistributor(self) -> None:
        """Integration coverage for the full _build_candidate wiring (not
        just allocate_vents_and_capacitors in isolation, see
        tests/test_vent_cap.py's own HullmodAdjustedVentCapAllocationTests):
        hullmod_selection.hullmod_ids finalized inside _build_candidate must
        actually reach allocate_vents_and_capacitors, and only take effect
        under baseline_0.10's opt-in gate. Same DESTROYER/100.0/200.0 fixture
        numbers as test_vent_cap.py's HullmodAdjustedVentCapAllocationTests.
        """
        hull = Hull("hull", "Hull", "core", Path("h"), hull_size="DESTROYER", ordnance_points=50,
                    weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},),
                    flux_dissipation=100.0, shield_upkeep=0.0)
        weapon = Weapon("gun", "Gun", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=10, range=500, flux_per_second=200.0)
        fluxdistributor = Hullmod("fluxdistributor", "Flux Distributor", "core", Path("m"), op_cost_by_hull_size={"DESTROYER": 8})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[fluxdistributor]))

        # baseline_0.7 (shipped default): the hullmod is installed either way, but the gate is
        # absent, so vent allocation must be identical (byte-for-byte reproducible) regardless.
        without_0_7 = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, denied_hullmod_ids={"fluxdistributor"}, flux_mode="BALANCED", heuristic_set="baseline_0.7")
        with_0_7 = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, flux_mode="BALANCED", heuristic_set="baseline_0.7")
        self.assertEqual((), without_0_7.variant.hullmods)
        self.assertEqual(("fluxdistributor",), with_0_7.variant.hullmods)
        self.assertEqual(5, without_0_7.variant.flux_vents)
        self.assertEqual(5, with_0_7.variant.flux_vents)

        # baseline_0.10: the gate is present, so installing fluxdistributor now genuinely
        # changes how many vents the generator spends OP on -- 0 instead of 5 (0.75*200-160 < 0).
        without_0_10 = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, denied_hullmod_ids={"fluxdistributor"}, flux_mode="BALANCED", heuristic_set="baseline_0.10")
        with_0_10 = generate_conservative_candidate("hull", "LINE_BRAWLER", registry, flux_mode="BALANCED", heuristic_set="baseline_0.10")
        self.assertEqual((), without_0_10.variant.hullmods)
        self.assertEqual(("fluxdistributor",), with_0_10.variant.hullmods)
        self.assertEqual(5, without_0_10.variant.flux_vents)
        self.assertIsNone(with_0_10.variant.flux_vents)  # 0 vents allocated -> Variant stores None, not 0
        self.assertEqual(LegalityResult.LEGAL, with_0_10.legality)

    def test_pd_escort_profile_prefers_pd_tagged_weapons_even_when_pricier(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},))
        cheap_non_pd = Weapon("cheap", "Cheap", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=2, raw={"tags": "none"})
        pricier_pd = Weapon("pd_gun", "PDGun", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=6, raw={"tags": "pd"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap_non_pd, pricier_pd]))
        result = generate_conservative_candidate("hull", "PD_ESCORT", registry)
        self.assertEqual({"WS 1": "pd_gun"}, result.variant.weapons_by_mount)
        self.assertEqual(LegalityResult.LEGAL, result.legality)

    def test_pd_escort_profile_honors_a_weapon_role_override(self) -> None:
        from starsector_variant_generator.core.overrides import EntityOverride
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},))
        cheap_non_pd = Weapon("cheap", "Cheap", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=2, raw={"tags": "none"})
        pricier_overridden_pd = Weapon("overridden_gun", "OverriddenGun", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=6, raw={"tags": "none"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap_non_pd, pricier_overridden_pd]))
        overrides = {"overridden_gun": EntityOverride("overridden_gun", ("PD",), None)}
        without_override = generate_conservative_candidate("hull", "PD_ESCORT", registry)
        self.assertEqual({"WS 1": "cheap"}, without_override.variant.weapons_by_mount)
        with_override = generate_conservative_candidate("hull", "PD_ESCORT", registry, weapon_role_overrides=overrides)
        self.assertEqual({"WS 1": "overridden_gun"}, with_override.variant.weapons_by_mount)

    def test_generation_never_assigns_a_weapon_to_a_hull_fixed_built_in_mount(self) -> None:
        # A weapon that itself declares mountType "BUILT_IN" (real vanilla
        # data does this) would otherwise look "eligible" for any BUILT_IN
        # mount, regardless of which specific weapon that hull actually
        # hardwires there -- this must stay omitted, not guessed at.
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10,
                    weapon_mounts=({"id": "WS 1", "type": "BUILT_IN", "size": "SMALL"},),
                    built_in_weapons={"WS 1": "flak"})
        builtin_typed_weapon = Weapon("some_builtin_weapon", "W", "core", Path("w"), size="SMALL", mount_type="BUILT_IN", ordnance_points=0)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[builtin_typed_weapon]))
        result = generate_conservative_candidate("hull", "LINE_BRAWLER", registry)
        self.assertEqual({}, result.variant.weapons_by_mount)
        self.assertEqual(LegalityResult.LEGAL, result.legality)
        self.assertIn("WS 1: hull-fixed built-in weapon, left for the game to auto-fill", result.omissions)

    def test_structural_slots_have_typed_omission_records(self) -> None:
        hull = Hull("structural", "Structural", "core", Path("h"), ordnance_points=10, weapon_mounts=(
            {"id": "BAY", "type": "LAUNCH_BAY", "size": "SMALL"},
            {"id": "MOD", "type": "STATION_MODULE", "size": "LARGE"},
            {"id": "FIXED", "type": "BUILT_IN", "size": "SMALL"},
        ))
        result = generate_conservative_candidate("structural", "LINE_BRAWLER", Registry.from_scan(ScanResult(hulls=[hull])))
        self.assertEqual({"STRUCTURAL_SLOT_OMITTED"}, {item.code for item in result.omission_records})
        self.assertEqual({"LAUNCH_BAY", "STATION_MODULE", "BUILT_IN"}, {item.mount_type for item in result.omission_records})

    def test_generation_without_flux_data_never_allocates_vents(self) -> None:
        hull = Hull("hull", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "WS 1", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("gun", "Gun", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        result = generate_conservative_candidate("hull", "LINE_BRAWLER", registry)
        self.assertIsNone(result.variant.flux_vents)
        self.assertIsNone(result.variant.flux_capacitors)


if __name__ == "__main__":
    unittest.main()
