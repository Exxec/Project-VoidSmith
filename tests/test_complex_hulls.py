from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.complex_hulls import (
    COMPLEX_HULL_ACCEPTANCE_MATRIX,
    ComplexHullAcceptance,
    ComplexHullFeature,
    complex_hull_matrix_entry,
)
from starsector_variant_generator.analysis.composite_hulls import (
    CompositeHullDefinition,
    CompositeHullProfile,
    CompositeShipProfile,
    HullDefinition,
    ModuleResolution,
    ResolvedShipStructure,
    ShipModule,
    build_composite_hull_definitions,
    build_composite_hull_profiles,
    build_composite_ship_profiles,
    classify_hull_definition,
    module_mappings,
    resolve_ship_structure,
)
from starsector_variant_generator.core.models import Hull, ScanResult, Variant
from starsector_variant_generator.core.registry import Registry


class ComplexHullMatrixTests(unittest.TestCase):
    def test_matrix_covers_every_required_feature_exactly_once(self) -> None:
        self.assertEqual({entry.feature for entry in COMPLEX_HULL_ACCEPTANCE_MATRIX}, set(ComplexHullFeature))
        self.assertEqual(len(COMPLEX_HULL_ACCEPTANCE_MATRIX), len(ComplexHullFeature))

    def test_module_local_weapons_are_separate_but_scripted_behavior_remains_unknown(self) -> None:
        self.assertIs(
            complex_hull_matrix_entry(ComplexHullFeature.MODULE_LOCAL_WEAPONS).acceptance,
            ComplexHullAcceptance.PARSED_SEPARATELY,
        )
        self.assertIs(
            complex_hull_matrix_entry(ComplexHullFeature.SCRIPTED_MODULE_BEHAVIOR).acceptance,
            ComplexHullAcceptance.UNKNOWN_SCRIPTED_EFFECT,
        )

    def test_structural_profile_keeps_repeated_children_separate(self) -> None:
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        child = Hull("child", "Child", "fixture", Path("child.csv"))
        parent_variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", raw={"modules": [{"A": "child_variant", "B": "child_variant"}]})
        child_variant = Variant("child_variant", "Child", "fixture", Path("child.variant"), hull_id="child", weapons_by_mount={"C": "child_weapon"})
        scan = ScanResult(hulls=[parent, child], variants=[parent_variant, child_variant])

        # Deliberately exercises the backward-compatible alias name (the
        # record was renamed CompositeShipProfile in Phase 27) to prove the
        # alias genuinely still works, not just that it type-checks.
        profile = build_composite_hull_profiles(scan, Registry.from_scan(scan))[0]

        self.assertEqual("STRUCTURAL_ONLY", profile.analysis_state)
        self.assertEqual(2, len(profile.modules))
        self.assertTrue(all(module.resolution is ModuleResolution.RESOLVED for module in profile.modules))
        self.assertIn(ComplexHullFeature.REPEATED_MODULES, profile.structural_features)
        self.assertNotIn("child_weapon", repr(profile))


class CompositeShipProfileRenameTests(unittest.TestCase):
    """Phase 27: CompositeHullProfile was renamed CompositeShipProfile."""

    def test_alias_is_the_same_type_not_a_separate_copy(self) -> None:
        self.assertIs(CompositeHullProfile, CompositeShipProfile)

    def test_build_composite_ship_profiles_is_the_primary_name(self) -> None:
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        child = Hull("child", "Child", "fixture", Path("child.csv"))
        parent_variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", raw={"modules": [{"A": "child_variant"}]})
        child_variant = Variant("child_variant", "Child", "fixture", Path("child.variant"), hull_id="child")
        scan = ScanResult(hulls=[parent, child], variants=[parent_variant, child_variant])
        registry = Registry.from_scan(scan)

        profiles = build_composite_ship_profiles(scan, registry)

        self.assertEqual(1, len(profiles))
        self.assertIsInstance(profiles[0], CompositeShipProfile)
        # Both entry points must agree byte-for-byte -- the alias is a name,
        # not a second implementation.
        self.assertEqual(profiles, build_composite_hull_profiles(scan, registry))


class HullDefinitionTests(unittest.TestCase):
    """Phase 27: formalizes the previously-repeated hull_hints string matching."""

    def test_classifies_every_declared_structural_role(self) -> None:
        hull = Hull("h", "H", "fixture", Path("h.csv"), hull_hints=("SHIP_WITH_MODULES", "CARRIER"))
        definition = classify_hull_definition(hull)
        self.assertEqual(HullDefinition("h", "fixture", is_parent=True, is_module=False, is_under_parent=False, is_station=False), definition)

    def test_hints_are_case_insensitive_like_the_original_inline_checks(self) -> None:
        hull = Hull("h", "H", "fixture", Path("h.csv"), hull_hints=("station",))
        self.assertTrue(classify_hull_definition(hull).is_station)

    def test_a_hull_with_no_composite_hints_classifies_as_none_of_the_four(self) -> None:
        hull = Hull("h", "H", "fixture", Path("h.csv"), hull_hints=("CARRIER",))
        definition = classify_hull_definition(hull)
        self.assertFalse(definition.is_parent or definition.is_module or definition.is_under_parent or definition.is_station)


class ShipModuleTests(unittest.TestCase):
    """Phase 27: module_mappings now returns typed ShipModule, not bare tuples."""

    def test_returns_one_typed_entry_per_declared_slot(self) -> None:
        variant = Variant("v", "V", "fixture", Path("v.variant"), raw={"modules": [{"SM": "child_a", "SM2": "child_b"}]})
        mappings = module_mappings(variant)
        self.assertEqual({ShipModule("SM", "child_a"), ShipModule("SM2", "child_b")}, set(mappings))

    def test_empty_or_missing_modules_key_returns_nothing(self) -> None:
        self.assertEqual((), module_mappings(Variant("v", "V", "fixture", Path("v.variant"))))
        self.assertEqual((), module_mappings(Variant("v", "V", "fixture", Path("v.variant"), raw={"modules": []})))

    def test_a_blank_slot_id_is_not_a_real_mapping(self) -> None:
        variant = Variant("v", "V", "fixture", Path("v.variant"), raw={"modules": [{"": "child_a", "SM": "child_b"}]})
        self.assertEqual((ShipModule("SM", "child_b"),), module_mappings(variant))


class CompositeHullDefinitionTests(unittest.TestCase):
    """Phase 27: hull-type-level composite declaration, distinct from a
    single ship's CompositeShipProfile."""

    def _hmi_locomotive_style_fixture(self) -> tuple[ScanResult, Registry]:
        # Mirrors the real hmi_locomotive shape this project already
        # verified (ROADMAP.md Phase 26): one parent hull with multiple
        # variants, each declaring several module slots against a shared
        # pool of child hull types.
        parent = Hull("locomotive", "Locomotive", "fixture", Path("loco.csv"), hull_hints=("SHIP_WITH_MODULES",))
        gun_left = Hull("gun_left", "Gun Left", "fixture", Path("gl.csv"))
        gun_right = Hull("gun_right", "Gun Right", "fixture", Path("gr.csv"))
        variant_a = Variant(
            "loco_std", "Standard", "fixture", Path("loco_std.variant"), hull_id="locomotive",
            raw={"modules": [{"GL": "gun_left_v"}, {"GR": "gun_right_v"}]},
        )
        variant_b = Variant(
            "loco_armoured", "Armoured", "fixture", Path("loco_armoured.variant"), hull_id="locomotive",
            raw={"modules": [{"GL": "gun_left_v"}]},
        )
        child_a = Variant("gun_left_v", "Gun Left", "fixture", Path("gl.variant"), hull_id="gun_left")
        child_b = Variant("gun_right_v", "Gun Right", "fixture", Path("gr.variant"), hull_id="gun_right")
        scan = ScanResult(hulls=[parent, gun_left, gun_right], variants=[variant_a, variant_b, child_a, child_b])
        return scan, Registry.from_scan(scan)

    def test_aggregates_variants_and_distinct_child_hull_ids_across_the_hull_type(self) -> None:
        scan, registry = self._hmi_locomotive_style_fixture()

        definitions = build_composite_hull_definitions(scan, registry)

        self.assertEqual(1, len(definitions))
        definition = definitions[0]
        self.assertEqual("locomotive", definition.hull.hull_id)
        self.assertTrue(definition.hull.is_parent)
        self.assertEqual(2, definition.variants_with_module_maps)
        self.assertEqual(("gun_left", "gun_right"), definition.distinct_child_hull_ids)

    def test_a_declared_parent_with_no_variant_evidence_still_appears_with_zero_counts(self) -> None:
        parent = Hull("lonely_parent", "Lonely", "fixture", Path("lp.csv"), hull_hints=("SHIP_WITH_MODULES",))
        scan = ScanResult(hulls=[parent])

        definitions = build_composite_hull_definitions(scan, Registry.from_scan(scan))

        self.assertEqual(1, len(definitions))
        self.assertEqual(0, definitions[0].variants_with_module_maps)
        self.assertEqual((), definitions[0].distinct_child_hull_ids)

    def test_a_hull_with_neither_the_hint_nor_any_module_evidence_is_excluded(self) -> None:
        plain = Hull("plain", "Plain", "fixture", Path("plain.csv"))
        scan = ScanResult(hulls=[plain])

        self.assertEqual((), build_composite_hull_definitions(scan, Registry.from_scan(scan)))


class ResolvedShipStructureTests(unittest.TestCase):
    """Phase 27: resolves a CompositeShipProfile's ids into real entities."""

    def test_resolves_parent_and_module_entities_for_every_resolved_module(self) -> None:
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        child = Hull("child", "Child", "fixture", Path("child.csv"))
        parent_variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", raw={"modules": [{"SM": "child_variant"}]})
        child_variant = Variant("child_variant", "Child", "fixture", Path("child.variant"), hull_id="child")
        scan = ScanResult(hulls=[parent, child], variants=[parent_variant, child_variant])
        registry = Registry.from_scan(scan)
        profile = build_composite_ship_profiles(scan, registry)[0]

        structure = resolve_ship_structure(scan, registry, profile)

        self.assertIsInstance(structure, ResolvedShipStructure)
        self.assertEqual(parent, structure.parent_hull)
        self.assertEqual(parent_variant, structure.parent_variant)
        self.assertEqual(child, structure.module_hulls["SM"])
        self.assertEqual(child_variant, structure.module_variants["SM"])

    def test_an_unresolved_module_stays_none_rather_than_guessed(self) -> None:
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        parent_variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", raw={"modules": [{"SM": "missing_child_variant"}]})
        scan = ScanResult(hulls=[parent], variants=[parent_variant])
        registry = Registry.from_scan(scan)
        profile = build_composite_ship_profiles(scan, registry)[0]
        self.assertEqual(ModuleResolution.UNRESOLVED_CHILD_VARIANT, profile.modules[0].resolution)

        structure = resolve_ship_structure(scan, registry, profile)

        self.assertIsNone(structure.module_hulls["SM"])
        self.assertIsNone(structure.module_variants["SM"])
