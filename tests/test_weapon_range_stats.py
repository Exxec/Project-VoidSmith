from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.weapon_range_stats import compute_derived_combat_stats
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry


SOURCE = Path("fixture")


def registry_with(*, weapons: tuple[Weapon, ...] = (), hullmods: tuple[Hullmod, ...] = ()) -> Registry:
    return Registry.from_scan(ScanResult(weapons=list(weapons), hullmods=list(hullmods)))


class DerivedWeaponRangeStatsTests(unittest.TestCase):
    def test_targetingunit_applies_percent_bonus_to_ballistic_weapon_range(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="BALLISTIC", range=1000.0)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("targetingunit",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertEqual(1200.0, derived.effective_range_by_mount["A"])
        self.assertEqual(("targetingunit",), derived.applied_effect_hullmod_ids)
        effect = derived.applied_effects[0]
        self.assertEqual("percent_add", effect.operation)
        self.assertEqual(0.20, effect.percent_bonus)
        self.assertEqual(200.0, effect.delta)

    def test_targetingunit_does_not_apply_to_missile_weapon(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="MISSILE", range=800.0)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("targetingunit",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertEqual({}, derived.effective_range_by_mount)
        self.assertEqual((), derived.applied_effect_hullmod_ids)
        self.assertEqual(("targetingunit",), derived.unverified_hullmod_ids)

    def test_dedicated_targeting_core_not_applied_on_frigate(self) -> None:
        # dedicated_targeting_core's own desc text: "Can not be installed on
        # a frigate or a destroyer" -- percent_bonus_by_hull_size omits
        # FRIGATE/DESTROYER entirely, so a frigate carrying it anyway (e.g.
        # modded data) never gets a fabricated bonus.
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="ENERGY", range=500.0)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("dedicated_targeting_core",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertEqual({}, derived.effective_range_by_mount)
        self.assertEqual(("dedicated_targeting_core",), derived.unverified_hullmod_ids)

    def test_dedicated_targeting_core_applies_on_capital(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CAPITAL_SHIP")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="ENERGY", range=1000.0)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("dedicated_targeting_core",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertEqual(1500.0, derived.effective_range_by_mount["A"])

    def test_unverified_hullmod_is_reported_not_silently_applied(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="BALLISTIC", range=500.0)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("some_unresearched_hullmod",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertEqual({}, derived.effective_range_by_mount)
        self.assertEqual(("some_unresearched_hullmod",), derived.unverified_hullmod_ids)

    def test_missing_weapon_range_leaves_mount_absent_not_zero(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="BALLISTIC", range=None)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("targetingunit",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertEqual({}, derived.effective_range_by_mount)
        self.assertEqual(("targetingunit",), derived.unverified_hullmod_ids)

    def test_targetingunit_and_dedicated_targeting_core_stack_without_a_fabricated_combined_value(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CAPITAL_SHIP")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="BALLISTIC", range=1000.0)
        variant = Variant(
            "v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"},
            hullmods=("targetingunit", "dedicated_targeting_core"),
        )
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertIsNone(derived.effective_range_by_mount["A"])
        self.assertEqual(1, len(derived.stacking_notes))
        self.assertIn("mount A", derived.stacking_notes[0])
        self.assertEqual(2, len(derived.applied_effects))
        by_id = {effect.hullmod_id: effect for effect in derived.applied_effects}
        self.assertEqual(1600.0, by_id["targetingunit"].resulting_range_alone)
        self.assertEqual(1500.0, by_id["dedicated_targeting_core"].resulting_range_alone)

    def test_efficiency_is_delta_per_op_spent(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="BALLISTIC", range=1000.0)
        mod = Hullmod("targetingunit", "Integrated Targeting Unit", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 4})
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("targetingunit",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,), hullmods=(mod,)))
        effect = derived.applied_effects[0]
        self.assertEqual(100.0, effect.delta)
        self.assertEqual(4, effect.op_cost)
        self.assertEqual(25.0, effect.efficiency)

    def test_efficiency_is_none_when_op_cost_is_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="BALLISTIC", range=1000.0)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("targetingunit",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertIsNone(derived.applied_effects[0].efficiency)

    def test_multiple_equipped_weapons_each_get_their_own_applied_effect(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        ballistic = Weapon("w1", "Ballistic", "core", SOURCE, mount_type="BALLISTIC", range=500.0)
        energy = Weapon("w2", "Energy", "core", SOURCE, mount_type="ENERGY", range=600.0)
        missile = Weapon("w3", "Missile", "core", SOURCE, mount_type="MISSILE", range=2000.0)
        variant = Variant(
            "v", "Variant", "core", SOURCE, hull_id="h",
            weapons_by_mount={"A": "w1", "B": "w2", "C": "w3"}, hullmods=("targetingunit",),
        )
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(ballistic, energy, missile)))
        self.assertEqual(550.0, derived.effective_range_by_mount["A"])
        self.assertEqual(660.0, derived.effective_range_by_mount["B"])
        self.assertNotIn("C", derived.effective_range_by_mount)

    def test_applied_weapon_range_effects_carry_the_unified_adapter_modeled_evidence_class(self) -> None:
        """ROADMAP.md Phase 29 (Evidence/Provenance Unification): always
        sourced from a verified adapters.combat_hullmod_effects table
        entry, so this must always report `ADAPTER_MODELED`."""
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER")
        weapon = Weapon("w", "Weapon", "core", SOURCE, mount_type="BALLISTIC", range=1000.0)
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("targetingunit",))
        derived = compute_derived_combat_stats(hull, variant, registry_with(weapons=(weapon,)))
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, derived.applied_effects[0].evidence_class)


if __name__ == "__main__":
    unittest.main()
