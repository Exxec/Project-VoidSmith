from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.combat_entity import (
    CombatEntityKind,
    DeploymentModel,
    StructuralSupport,
    classify_combat_entity_kind,
    classify_fighter_wing_entity,
    recommendation_eligibility,
)
from starsector_variant_generator.analysis.gap_recommendation import (
    CapabilityGap,
    recommend_acquisition_solutions,
)
from starsector_variant_generator.core.models import (
    Faction,
    FighterWing,
    Hull,
    ScanResult,
)
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class CombatEntityKindTests(unittest.TestCase):
    def test_explicit_structure_is_classified_without_changing_legality(self) -> None:
        cases = (
            (Hull("ship", "Ship", "core", SOURCE), CombatEntityKind.NORMAL_SHIP, StructuralSupport.FULL, True),
            (Hull("fighter", "Fighter", "core", SOURCE, hull_size="FIGHTER"), CombatEntityKind.FIGHTER_LIKE_HULL, StructuralSupport.PARTIAL, False),
            (Hull("parent", "Parent", "core", SOURCE, hull_hints=("SHIP_WITH_MODULES",)), CombatEntityKind.COMPOSITE_PARENT, StructuralSupport.PARTIAL, False),
            (Hull("module", "Module", "core", SOURCE, hull_hints=("MODULE",)), CombatEntityKind.SHIP_MODULE, StructuralSupport.UNSUPPORTED, False),
            (Hull("station", "Station", "core", SOURCE, hull_hints=("STATION", "UNDER_PARENT")), CombatEntityKind.STATION_MODULE, StructuralSupport.UNSUPPORTED, False),
            (Hull("unboardable", "Unboardable", "core", SOURCE, hull_hints=("UNBOARDABLE",)), CombatEntityKind.UNBOARDABLE_COMBAT_ENTITY, StructuralSupport.PARTIAL, False),
        )
        for hull, kind, support, eligible in cases:
            with self.subTest(hull=hull.id):
                result = recommendation_eligibility(hull)
                self.assertEqual(kind, classify_combat_entity_kind(hull))
                self.assertEqual(support, result.structural_support)
                self.assertEqual(eligible, result.eligible)

    def test_ordinary_recommendations_exclude_fighter_like_hulls(self) -> None:
        mounts = tuple({"type": "BALLISTIC", "size": "SMALL"} for _ in range(8))
        normal = Hull("normal", "Normal", "core", SOURCE, weapon_mounts=mounts)
        fighter = Hull("fighter", "Fighter", "core", SOURCE, hull_size="FIGHTER", weapon_mounts=mounts)
        faction = Faction("f", "Faction", "core", SOURCE)
        registry = Registry.from_scan(ScanResult(hulls=[normal, fighter], factions=[faction]))
        gap = CapabilityGap("LINE_BRAWLER", "GAP", 0.0, 1.0)

        results = recommend_acquisition_solutions(faction, registry, (gap,))

        self.assertEqual(["normal"], [item.hull_id for item in results["LINE_BRAWLER"]])

    def test_explicit_mech_hint_and_wing_role_keep_entity_and_deployment_separate(self) -> None:
        mech = Hull("mech", "Mech", "core", SOURCE, hull_size="FIGHTER", hull_hints=("MECH",))
        mech_profile = recommendation_eligibility(mech)
        bomber_profile = classify_fighter_wing_entity(FighterWing("b", "Bomber", "core", SOURCE, role="bomber"))

        self.assertEqual(CombatEntityKind.MECH, mech_profile.entity_kind)
        self.assertEqual(DeploymentModel.UNKNOWN, mech_profile.deployment_model)
        self.assertEqual(CombatEntityKind.BOMBER, bomber_profile.entity_kind)
        self.assertEqual(DeploymentModel.WING_BASED, bomber_profile.deployment_model)
        self.assertEqual({"BOMBER": 1.0}, bomber_profile.role_scores)


if __name__ == "__main__":
    unittest.main()
