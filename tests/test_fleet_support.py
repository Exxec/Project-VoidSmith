from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.fleet_support import FleetSelection, FleetSupportConstraints, SupportFocus, _rank_fleet_support, analyze_player_fleet, explain_fleet_support_candidate, fleet_support_request_from_payload, fleet_support_request_to_payload, parse_fleet_selections, recommend_fleet_support
from starsector_variant_generator import api
from starsector_variant_generator.core.models import Faction, Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry


SOURCE = Path("fixture")


def hull(hull_id: str, *, speed: int = 100, armor: int = 300, flux: int = 300, hints: tuple[str, ...] = (), mounts: int = 2, cargo: int | None = None, burn: int | None = None, sensor: float | None = None) -> Hull:
    return Hull(
        hull_id, hull_id, "core", SOURCE, hull_size="FRIGATE", ordnance_points=40,
        weapon_mounts=tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(mounts)),
        flux_capacity=flux * 10, flux_dissipation=flux, cargo_capacity=cargo, max_burn=burn, sensor_profile=sensor, hull_hints=hints,
        raw={"armor rating": armor, "hitpoints": armor * 8, "max speed": speed, "acceleration": speed, "max turn rate": speed},
    )


class FleetSupportAdvisorTests(unittest.TestCase):
    def test_user_owned_request_snapshot_round_trips_without_registry_data(self) -> None:
        selections = (FleetSelection("frigate", 2), FleetSelection(variant_id="cruiser_loadout"))
        constraints = FleetSupportConstraints(focus=SupportFocus.LOGISTICS, recommendation_count=4)
        payload = fleet_support_request_to_payload(selections, constraints)
        restored_selections, restored_constraints = fleet_support_request_from_payload(payload)
        self.assertEqual(selections, restored_selections)
        self.assertEqual(constraints, restored_constraints)
        self.assertNotIn("hulls", payload)

    def test_explicit_count_tokens_preserve_player_declared_instances(self) -> None:
        self.assertEqual((FleetSelection("frigate", 2), FleetSelection("cruiser", 1)), parse_fleet_selections(("frigate*2", "cruiser")))
        with self.assertRaises(ValueError):
            parse_fleet_selections(("frigate*0",))

    def test_locked_selection_aggregates_needs_and_is_never_recommended(self) -> None:
        striker = hull("striker", speed=120, armor=150, flux=150, mounts=1)
        anchor = hull("anchor", speed=45, armor=1600, flux=1400, mounts=6)
        freighter = hull("freighter", speed=80, armor=500, flux=300, hints=("CIVILIAN", "FREIGHTER"), cargo=800)
        registry = Registry.from_scan(ScanResult(hulls=[striker, anchor, freighter]))

        result = recommend_fleet_support((FleetSelection("striker", 2),), registry, heuristic_set="baseline_0.12")

        self.assertIn("SUSTAINED_PRESSURE", {need.capability for need in result.profile.support_needs})
        self.assertNotIn("striker", {rec.hull_id for rec in result.recommendations})
        self.assertIn(("striker", "LOCKED_PLAYER_SELECTION"), result.excluded_candidates)
        self.assertTrue(result.recommendations)
        self.assertEqual("NOT_EVALUATED_NO_CONCRETE_FIT", result.recommendations[0].fit_legality_status)

    def test_logistics_focus_prefers_logistics_evidence_and_records_unknown_campaign_dimensions(self) -> None:
        striker = hull("striker", speed=120, armor=150, flux=150, mounts=1)
        freighter = hull("freighter", speed=80, armor=500, flux=300, hints=("CIVILIAN", "FREIGHTER"), cargo=800)
        registry = Registry.from_scan(ScanResult(hulls=[striker, freighter]))

        result = recommend_fleet_support((FleetSelection("striker"),), registry, heuristic_set="baseline_0.12", constraints=FleetSupportConstraints(focus=SupportFocus.LOGISTICS))

        self.assertEqual("freighter", result.recommendations[0].hull_id)
        self.assertEqual("LOGISTICS_SUPPORT", result.recommendations[0].category)
        logistics = next(item for item in result.category_shortlists if item.category == "LOGISTICS_SUPPORT")
        self.assertEqual(("freighter",), tuple(item.hull_id for item in logistics.recommendations))
        self.assertIn("range_match", result.recommendations[0].compatibility.unknown_dimensions)
        self.assertIsNone(result.recommendations[0].friction.sensor_penalty)

    def test_strict_faction_access_excludes_non_native_hulls(self) -> None:
        striker = hull("striker", speed=120, armor=150, flux=150, mounts=1)
        native = hull("native", speed=45, armor=1600, flux=1400, mounts=6)
        foreign = hull("foreign", speed=45, armor=1800, flux=1600, mounts=7)
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("striker", "native"))
        registry = Registry.from_scan(ScanResult(hulls=[striker, native, foreign], factions=[faction]))

        result = recommend_fleet_support((FleetSelection("striker"),), registry, faction, "baseline_0.12", FleetSupportConstraints(access_mode="STRICT_FACTION"))

        self.assertEqual("native", result.recommendations[0].hull_id)
        # Source provenance alone does not fabricate FOREIGN affinity; strict
        # policy still excludes this unlisted, unaligned hull.
        self.assertIn(("foreign", "ACCESS_POLICY_UNALIGNED"), result.excluded_candidates)

    def test_unresolved_and_structurally_ineligible_selections_are_preserved_as_evidence_gaps(self) -> None:
        normal = hull("normal")
        fighter = Hull("fighter", "fighter", "core", SOURCE, hull_size="FIGHTER")
        registry = Registry.from_scan(ScanResult(hulls=[normal, fighter]))

        profile = analyze_player_fleet((FleetSelection("missing"), FleetSelection("fighter"), FleetSelection("normal")), registry)

        self.assertEqual(("missing",), profile.unresolved_hull_ids)
        self.assertEqual(("fighter",), profile.excluded_selection_hull_ids)
        self.assertEqual(("normal",), profile.resolved_hull_ids)

    def test_stealth_focus_is_explicitly_unavailable_without_sensor_or_phase_evidence(self) -> None:
        selected = hull("selected")
        candidate = hull("candidate", armor=1800, flux=1600, mounts=7)
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate]))

        result = recommend_fleet_support((FleetSelection("selected"),), registry, heuristic_set="baseline_0.12", constraints=FleetSupportConstraints(focus=SupportFocus.STEALTH))

        self.assertEqual((), result.profile.support_needs)
        self.assertEqual((), result.recommendations)

    def test_unaddressed_need_is_reported_instead_of_padding_a_shortlist(self) -> None:
        selected = hull("selected", speed=120, armor=150, flux=150, mounts=1)
        registry = Registry.from_scan(ScanResult(hulls=[selected]))

        result = recommend_fleet_support((FleetSelection("selected"),), registry, heuristic_set="baseline_0.12")

        self.assertFalse(result.recommendations)
        self.assertEqual(tuple(need.capability for need in result.profile.support_needs), tuple(need.capability for need in result.unaddressed_support_needs))

    def test_why_not_reuses_shortlist_ranking_and_distinguishes_locked_selection(self) -> None:
        selected = hull("selected", speed=120, armor=150, flux=150, mounts=1)
        strong = hull("strong", speed=45, armor=1800, flux=1600, mounts=7)
        weaker = hull("weaker", speed=50, armor=1500, flux=1400, mounts=6)
        registry = Registry.from_scan(ScanResult(hulls=[selected, strong, weaker]))
        constraints = FleetSupportConstraints(recommendation_count=1)

        _, ranked, _ = _rank_fleet_support((FleetSelection("selected"),), registry, None, "baseline_0.12", constraints)
        self.assertGreaterEqual(len(ranked), 2)
        recommended = explain_fleet_support_candidate((FleetSelection("selected"),), registry, ranked[0].hull_id, heuristic_set="baseline_0.12", constraints=constraints)
        below_cutoff = explain_fleet_support_candidate((FleetSelection("selected"),), registry, ranked[1].hull_id, heuristic_set="baseline_0.12", constraints=constraints)
        locked = explain_fleet_support_candidate((FleetSelection("selected"),), registry, "selected", heuristic_set="baseline_0.12", constraints=constraints)

        self.assertTrue(recommended.recommended)
        self.assertEqual(1, recommended.rank)
        self.assertFalse(below_cutoff.recommended)
        self.assertEqual(2, below_cutoff.rank)
        self.assertIn("shortlist cutoff", below_cutoff.reason)
        self.assertIn("LOCKED_PLAYER_SELECTION", locked.reason)

    def test_diversity_enabled_shortlist_records_mechanical_family_evidence(self) -> None:
        selected = hull("selected", speed=120, armor=150, flux=150, mounts=1)
        line_ship = hull("line_ship", speed=45, armor=1800, flux=1600, mounts=7)
        alternate = hull("alternate", speed=65, armor=1200, flux=1200, mounts=5)
        registry = Registry.from_scan(ScanResult(hulls=[selected, line_ship, alternate]))

        result = recommend_fleet_support((FleetSelection("selected"),), registry, heuristic_set="baseline_0.13", constraints=FleetSupportConstraints(recommendation_count=2))

        self.assertTrue(result.recommendations)
        self.assertEqual(1, result.recommendations[0].shortlist_order)
        self.assertTrue(result.recommendations[0].mechanical_archetypes)
        self.assertIsNotNone(result.recommendations[0].diversity_reason)

    def test_static_base_burn_match_is_visible_without_claiming_campaign_effects(self) -> None:
        selected = hull("selected", speed=100, armor=150, flux=150, mounts=1, burn=8)
        candidate = hull("candidate", speed=45, armor=1800, flux=1600, mounts=7, burn=6)
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate]))

        result = recommend_fleet_support((FleetSelection("selected"),), registry, heuristic_set="baseline_0.12")

        self.assertEqual(.75, result.recommendations[0].compatibility.burn_speed_match)
        self.assertEqual(.25, result.recommendations[0].friction.burn_penalty)
        self.assertIn("Static base max-burn", result.recommendations[0].friction.notes[0])

    def test_existing_variant_ranges_supply_range_cohesion_only_when_resolved(self) -> None:
        selected = hull("selected", speed=100, armor=150, flux=150, mounts=1)
        candidate = hull("candidate", speed=45, armor=1800, flux=1600, mounts=7)
        close = Weapon("close", "Close", "core", SOURCE, range=500)
        long = Weapon("long", "Long", "core", SOURCE, range=1000)
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate], weapons=[close, long], variants=[Variant("selected_std", "Selected", "core", SOURCE, hull_id="selected", weapons_by_mount={"a": "close"}), Variant("candidate_std", "Candidate", "core", SOURCE, hull_id="candidate", weapons_by_mount={"a": "long"})]))

        result = recommend_fleet_support((FleetSelection("selected"),), registry, heuristic_set="baseline_0.12")

        self.assertEqual(.5, result.recommendations[0].compatibility.range_match)
        self.assertEqual(.5, result.recommendations[0].friction.range_mismatch)

    def test_variant_selection_resolves_its_hull_and_uses_its_own_weapon_range(self) -> None:
        selected = hull("selected", speed=100, armor=150, flux=150, mounts=1)
        candidate = hull("candidate", speed=45, armor=1800, flux=1600, mounts=7)
        close, long = Weapon("close", "Close", "core", SOURCE, range=500), Weapon("long", "Long", "core", SOURCE, range=1000)
        selected_variant = Variant("selected_loadout", "Selected", "core", SOURCE, hull_id="selected", weapons_by_mount={"a": "close"})
        candidate_variant = Variant("candidate_std", "Candidate", "core", SOURCE, hull_id="candidate", weapons_by_mount={"a": "long"})
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate], weapons=[close, long], variants=[selected_variant, candidate_variant]))

        result = recommend_fleet_support((FleetSelection(variant_id="selected_loadout"),), registry, heuristic_set="baseline_0.12")

        self.assertEqual(("selected",), result.profile.resolved_hull_ids)
        self.assertEqual(.5, result.recommendations[0].compatibility.range_match)

    def test_variant_selection_does_not_mix_other_loadout_weapon_evidence(self) -> None:
        selected = hull("selected")
        kinetic = Weapon("kinetic", "Kinetic", "core", SOURCE, damage_type="KINETIC", range=300)
        he = Weapon("he", "HE", "core", SOURCE, damage_type="HE", range=1200)
        close = Variant("close_fit", "Close", "core", SOURCE, hull_id="selected", weapons_by_mount={"a": "kinetic"})
        distant = Variant("distant_fit", "Distant", "core", SOURCE, hull_id="selected", weapons_by_mount={"a": "he"})
        registry = Registry.from_scan(ScanResult(hulls=[selected], weapons=[kinetic, he], variants=[close, distant]))

        profile = analyze_player_fleet((FleetSelection(variant_id="close_fit"),), registry)

        self.assertEqual(1.0, profile.capability_vector["KINETIC_PRESSURE"].score)
        self.assertEqual(0.0, profile.capability_vector["ARMOR_BREAKING"].score)

    def test_direct_phase_hint_and_normalized_sensor_fields_are_used_without_inference(self) -> None:
        selected = hull("selected", speed=100, armor=150, flux=150, mounts=1, hints=("PHASE",), sensor=50)
        candidate = hull("candidate", speed=45, armor=1800, flux=1600, mounts=7, hints=("PHASE",), sensor=100)
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate]))
        result = recommend_fleet_support((FleetSelection("selected"),), registry, heuristic_set="baseline_0.14")
        self.assertIn("PHASE_HULL_HINT", result.profile.declared_traits)
        self.assertEqual(1.0, result.recommendations[0].compatibility.phase_trait_match)
        self.assertEqual(.5, result.recommendations[0].compatibility.sensor_profile_match)
        self.assertGreater(result.recommendations[0].score_components.composition_synergy, 0.0)

    def test_count_aware_composition_traits_distinguish_phase_heavy_selection(self) -> None:
        phase = hull("phase", hints=("PHASE",))
        line = hull("line", armor=1800, flux=1600, mounts=7)
        registry = Registry.from_scan(ScanResult(hulls=[phase, line]))
        profile = analyze_player_fleet((FleetSelection("phase", 5), FleetSelection("line", 1)), registry, heuristic_set="baseline_0.14")
        phase_trait = next(item for item in profile.composition_traits if item.name == "PHASE_ORIENTED")
        self.assertAlmostEqual(5 / 6, phase_trait.score, places=6)
        self.assertEqual(1.0, phase_trait.confidence)

    def test_composition_synergy_is_separate_and_affects_current_heuristic_score(self) -> None:
        selected = hull("selected", hints=("PHASE",), cargo=10, burn=8, sensor=50)
        phase_freighter = hull("phase_freighter", hints=("PHASE", "CIVILIAN", "FREIGHTER"), cargo=800, burn=8, sensor=50)
        ordinary_freighter = hull("ordinary_freighter", hints=("CIVILIAN", "FREIGHTER"), cargo=800, burn=5, sensor=300)
        registry = Registry.from_scan(ScanResult(hulls=[selected, phase_freighter, ordinary_freighter]))
        result = recommend_fleet_support((FleetSelection("selected"),), registry, heuristic_set="baseline_0.14", constraints=FleetSupportConstraints(focus=SupportFocus.LOGISTICS, recommendation_count=2))
        records = {item.hull_id: item for item in result.recommendations}
        self.assertGreater(records["phase_freighter"].score_components.composition_synergy, records["ordinary_freighter"].score_components.composition_synergy)
        self.assertGreater(records["phase_freighter"].recommendation_score, records["ordinary_freighter"].recommendation_score)
        self.assertIn("CARGO_SUPPORT", records["phase_freighter"].support_purposes)

    def test_support_fit_revalidates_shortlisted_candidate_then_uses_normal_generator(self) -> None:
        selected = hull("selected", speed=120, armor=150, flux=150, mounts=1)
        candidate = hull("candidate", speed=45, armor=1800, flux=1600, mounts=7)
        registry = Registry.from_scan(ScanResult(hulls=[selected, candidate]))
        outcome = api.run_generate_fleet_support_fit(registry, (FleetSelection("selected"),), "candidate", heuristic_set="baseline_0.14")
        self.assertEqual("candidate", outcome.recommendation.hull_id)
        self.assertIn(outcome.generator_profile, {"LINE_ARTILLERY", "TANK", "FAST_STRIKE", "PD_ESCORT", "CARRIER_SUPPORT", "MISSILE_SUPPORT"})
        self.assertTrue(outcome.generation.assessed_candidates)


if __name__ == "__main__":
    unittest.main()
