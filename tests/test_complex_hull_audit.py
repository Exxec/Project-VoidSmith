from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.complex_hull_audit import audit_complex_hulls
from starsector_variant_generator.core.models import Hull, ScanResult, Variant
from starsector_variant_generator.core.registry import Registry


class ComplexHullAuditTests(unittest.TestCase):
    def test_empty_modules_array_is_not_a_module_map(self) -> None:
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", raw={"modules": []})
        scan = ScanResult(hulls=[parent], variants=[variant])

        audit = audit_complex_hulls(scan, Registry.from_scan(scan))

        self.assertEqual(audit["summary"]["variants_with_module_maps"], 0)

    def test_module_child_is_audited_without_becoming_parent_weapon_evidence(self) -> None:
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        child = Hull("child", "Child", "fixture", Path("child.csv"))
        parent_variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", weapons_by_mount={"P": "parent_weapon"}, raw={"modules": [{"SM": "child_variant"}]})
        child_variant = Variant("child_variant", "Child", "fixture", Path("child.variant"), hull_id="child", weapons_by_mount={"C": "child_weapon"})
        scan = ScanResult(hulls=[parent, child], variants=[parent_variant, child_variant])

        audit = audit_complex_hulls(scan, Registry.from_scan(scan))

        self.assertEqual(audit["summary"]["variants_with_module_maps"], 1)
        self.assertEqual(audit["summary"]["unresolved_child_hulls"], 0)
        self.assertEqual("STRUCTURAL_ONLY", audit["structural_profiles"][0]["analysis_state"])
        self.assertEqual(parent_variant.weapons_by_mount, {"P": "parent_weapon"})

    def test_missing_child_hull_is_warning_not_a_guess(self) -> None:
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        parent_variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", raw={"modules": [{"SM": "child_variant"}]})
        child_variant = Variant("child_variant", "Child", "fixture", Path("child.variant"), hull_id="missing_child")
        scan = ScanResult(hulls=[parent], variants=[parent_variant, child_variant])

        audit = audit_complex_hulls(scan, Registry.from_scan(scan))

        self.assertEqual(audit["summary"]["unresolved_child_hulls"], 1)
        self.assertIn("UNRESOLVED_MODULE_HULL", {finding["code"] for finding in audit["findings"]})

    def test_station_and_under_parent_hints_are_classified_and_counted(self) -> None:
        # Phase 27: parents/modules/under_parent/stations are now derived
        # from analysis/composite_hulls.py::classify_hull_definition rather
        # than four independent inline hint-string comprehensions; this
        # proves the real end-to-end audit path still counts every hint
        # correctly through that formalized layer.
        station = Hull("station", "Station", "fixture", Path("station.csv"), hull_hints=("SHIP_WITH_MODULES", "STATION"))
        sub_module = Hull("sub", "Sub", "fixture", Path("sub.csv"), hull_hints=("UNDER_PARENT",))
        scan = ScanResult(hulls=[station, sub_module])

        audit = audit_complex_hulls(scan, Registry.from_scan(scan))

        self.assertEqual(1, audit["summary"]["parent_hulls_with_structural_hint"])
        self.assertEqual(1, audit["summary"]["station_hulls"])
        self.assertEqual(1, audit["summary"]["under_parent_hulls"])

    def test_composite_hull_definitions_are_additive_and_typed(self) -> None:
        # Phase 27: CompositeHullDefinition is a new, additive field in the
        # real audit output -- proves it flows end to end through the real
        # entry point, not just the unit-level analysis/composite_hulls.py
        # tests in tests/test_complex_hulls.py.
        parent = Hull("parent", "Parent", "fixture", Path("parent.csv"), hull_hints=("SHIP_WITH_MODULES",))
        child = Hull("child", "Child", "fixture", Path("child.csv"))
        parent_variant = Variant("parent_variant", "Parent", "fixture", Path("parent.variant"), hull_id="parent", raw={"modules": [{"SM": "child_variant"}]})
        child_variant = Variant("child_variant", "Child", "fixture", Path("child.variant"), hull_id="child")
        scan = ScanResult(hulls=[parent, child], variants=[parent_variant, child_variant])

        audit = audit_complex_hulls(scan, Registry.from_scan(scan))

        self.assertEqual("complex-hull-audit-0.3", audit["schema_version"])
        self.assertIn("composite_hull_definitions", audit)
        definitions = {entry["hull"]["hull_id"]: entry for entry in audit["composite_hull_definitions"]}
        self.assertEqual(1, definitions["parent"]["variants_with_module_maps"])
        self.assertEqual(("child",), definitions["parent"]["distinct_child_hull_ids"])
