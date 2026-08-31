from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.mod_acceptance import (
    FAIL,
    PARTIAL,
    PASS,
    PASS_WITH_UNKNOWNS,
    audit_mod_acceptance,
)
from starsector_variant_generator.core.models import (
    Hull,
    Hullmod,
    ModInfo,
    ScanResult,
    SourceType,
    Variant,
    Weapon,
)
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


def _records_by_id(audit: dict) -> dict[str, dict]:
    return {record["mod_id"]: record for record in audit["records"]}


class ModAcceptanceClassificationTests(unittest.TestCase):
    """Covers all four classifications with deliberately constructed
    synthetic scenarios only -- never real mod/entity data, per AGENTS.md's
    distribution boundary."""

    def test_pass_for_clean_mod_with_no_defect_signal(self) -> None:
        mod = ModInfo("clean_mod", "Clean Mod", "1.0", Path("mods/clean_mod"), True)
        hull = Hull("clean_hull", "Clean Hull", "clean_mod", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("clean_weapon", "Clean Weapon", "clean_mod", SOURCE)
        variant = Variant("clean_variant", "Clean Variant", "clean_mod", SOURCE, hull_id="clean_hull", weapons_by_mount={"WS1": "clean_weapon"})
        scan = ScanResult(mods=[mod], hulls=[hull], weapons=[weapon], variants=[variant])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        record = _records_by_id(audit)["clean_mod"]
        self.assertEqual(PASS, record["classification"])
        self.assertEqual({"hulls": 1, "weapons": 1, "fighters": 0, "hullmods": 0, "variants": 1, "factions": 0}, record["entity_counts"])
        self.assertEqual([], record["findings"])

    def test_pass_with_unknowns_for_unmodeled_hullmod_effect(self) -> None:
        mod = ModInfo("quirky_mod", "Quirky Mod", "1.0", Path("mods/quirky_mod"), True)
        hull = Hull("quirky_hull", "Quirky Hull", "quirky_mod", SOURCE, hull_size="FRIGATE")
        # "quirky_scripted_hullmod" has no entry in any modeled adapter effect
        # table (it isn't a real vanilla id) -- DerivedShipState reports it as
        # an unapplied/unknown hullmod effect, which is the expected,
        # tolerated PASS_WITH_UNKNOWNS signal for modded content per
        # AGENTS.md's UNKNOWN_SCRIPTED_EFFECT ladder, not a defect.
        hullmod = Hullmod("quirky_scripted_hullmod", "Quirky Scripted Hullmod", "quirky_mod", SOURCE)
        variant = Variant(
            "quirky_variant", "Quirky Variant", "quirky_mod", SOURCE, hull_id="quirky_hull",
            hullmods=("quirky_scripted_hullmod",),
        )
        scan = ScanResult(mods=[mod], hulls=[hull], hullmods=[hullmod], variants=[variant])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        record = _records_by_id(audit)["quirky_mod"]
        self.assertEqual(PASS_WITH_UNKNOWNS, record["classification"])
        self.assertEqual(["quirky_scripted_hullmod"], record["unknown_effect_hullmod_ids"])
        self.assertIn("UNKNOWN_HULLMOD_EFFECTS", {finding["code"] for finding in record["findings"]})

    def test_partial_for_duplicate_ids_and_unresolved_reference(self) -> None:
        modA = ModInfo("mod_a", "Mod A", "1.0", Path("mods/mod_a"), True)
        modB = ModInfo("mod_b", "Mod B", "1.0", Path("mods/mod_b"), True)
        hull_a = Hull("shared_hull", "Shared Hull A", "mod_a", SOURCE, hull_size="FRIGATE")
        hull_b = Hull("shared_hull", "Shared Hull B", "mod_b", SOURCE, hull_size="FRIGATE")
        variant = Variant(
            "mod_a_variant", "Mod A Variant", "mod_a", SOURCE, hull_id="shared_hull",
            weapons_by_mount={"WS1": "never_parsed_weapon"},
        )
        scan = ScanResult(mods=[modA, modB], hulls=[hull_a, hull_b], variants=[variant])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        records = _records_by_id(audit)
        self.assertEqual(PARTIAL, records["mod_a"]["classification"])
        self.assertEqual({"hulls": ["shared_hull"]}, records["mod_a"]["duplicate_entity_ids"])
        # "shared_hull" is itself ambiguous (present in both mod_a and mod_b),
        # so Registry._resolve_variants also can't resolve mod_a_variant's own
        # hull_id reference through the now-ambiguous `by_id` -- both real,
        # independent unresolved references are expected here.
        self.assertEqual(
            [
                {"variant_id": "mod_a_variant", "reference_type": "hull", "reference_id": "shared_hull"},
                {"variant_id": "mod_a_variant", "reference_type": "weapon", "reference_id": "never_parsed_weapon"},
            ],
            records["mod_a"]["unresolved_references"],
        )
        # mod_b contributed no variant/reference issue of its own, but still
        # shares the ambiguous "shared_hull" id -- also PARTIAL, never silently
        # clean, since the duplicate is real evidence against this mod too.
        self.assertEqual(PARTIAL, records["mod_b"]["classification"])
        self.assertEqual({"hulls": ["shared_hull"]}, records["mod_b"]["duplicate_entity_ids"])

    def test_partial_for_fighter_wing_anomaly_not_covered_by_registry_resolution(self) -> None:
        # Registry._resolve_variants deliberately checks only hull/weapon/
        # hullmod references, never variant.fighter_wings or
        # Hull.built_in_fighter_wings -- this sweep fills that real coverage
        # gap independently (see module docstring).
        mod = ModInfo("carrier_mod", "Carrier Mod", "1.0", Path("mods/carrier_mod"), True)
        hull = Hull("carrier_hull", "Carrier Hull", "carrier_mod", SOURCE, hull_size="CRUISER")
        variant = Variant(
            "carrier_variant", "Carrier Variant", "carrier_mod", SOURCE, hull_id="carrier_hull",
            fighter_wings=("missing_wing",),
        )
        scan = ScanResult(mods=[mod], hulls=[hull], variants=[variant])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        record = _records_by_id(audit)["carrier_mod"]
        self.assertEqual(PARTIAL, record["classification"])
        self.assertEqual(
            [{"context": "variant_fighter_wing", "id": "carrier_variant", "reference_id": "missing_wing"}],
            record["unresolved_fighter_wing_references"],
        )

    def test_partial_for_missing_declared_dependency(self) -> None:
        mod = ModInfo("dependent_mod", "Dependent Mod", "1.0", Path("mods/dependent_mod"), True, dependencies=("never_installed_mod",))
        hull = Hull("dependent_hull", "Dependent Hull", "dependent_mod", SOURCE, hull_size="FRIGATE")
        scan = ScanResult(mods=[mod], hulls=[hull])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        record = _records_by_id(audit)["dependent_mod"]
        self.assertEqual(PARTIAL, record["classification"])
        self.assertEqual(["never_installed_mod"], record["missing_dependencies"])

    def test_fail_for_modinfo_backed_mod_with_only_errors_and_no_entities(self) -> None:
        mod = ModInfo("broken_mod", "Broken Mod", "1.0", Path("mods/broken_mod"), True)
        scan = ScanResult(mods=[mod], errors=[f"{Path('mods/broken_mod/broken.ship')}: unexpected token"])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        record = _records_by_id(audit)["broken_mod"]
        self.assertEqual(FAIL, record["classification"])
        self.assertEqual(1, len(record["errors"]))

    def test_fail_synthetic_record_for_unparseable_mod_info(self) -> None:
        # A mod whose mod_info.json itself failed to parse never gets a real
        # ModInfo (see core/scanner.py::Scanner._mod_info_from_dir), so it is
        # recovered here as a synthetic FAIL record from the scanner's own
        # discovery_skipped message, exactly as constructed by the scanner.
        scan = ScanResult(skipped_entities=["Malformed mod metadata skipped: mods/unreadable_mod/mod_info.json: Expecting value: line 1 column 1"])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        records = _records_by_id(audit)
        self.assertIn("UNPARSEABLE:unreadable_mod", records)
        record = records["UNPARSEABLE:unreadable_mod"]
        self.assertEqual(FAIL, record["classification"])
        self.assertEqual("METADATA_UNREADABLE", record["mod_info_status"])

    def test_fail_synthetic_record_for_enabled_mod_not_discovered(self) -> None:
        scan = ScanResult(skipped_entities=["Enabled mod not discovered: never_on_disk_mod"])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        records = _records_by_id(audit)
        self.assertIn("never_on_disk_mod", records)
        record = records["never_on_disk_mod"]
        self.assertEqual(FAIL, record["classification"])
        self.assertEqual("ENABLED_NOT_FOUND", record["mod_info_status"])

    def test_adapter_usage_recorded_for_core_source_hull(self) -> None:
        # "expanded_cargo_holds" is this project's own already-modeled vanilla
        # ("core") logistics hullmod effect (adapters/vanilla), the same real,
        # already-tracked signal every other consumer (analysis/civilian.py
        # etc.) uses -- not fabricated for this test alone (see
        # tests/test_civilian.py for the same idiom).
        core = ModInfo("core", "Starsector", None, Path("core"), True, source_type=SourceType.CORE)
        hull = Hull("core_freighter", "Core Freighter", "core", SOURCE, hull_size="FRIGATE")
        variant = Variant(
            "core_freighter_variant", "Core Freighter Variant", "core", SOURCE, hull_id="core_freighter",
            hullmods=("expanded_cargo_holds",),
        )
        scan = ScanResult(mods=[core], hulls=[hull], variants=[variant])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        # "core" is a CORE source, not a MOD source, so it is not itself
        # classified as an installed mod record -- but the adapter-usage
        # aggregation must not raise, and no mod record fabricates a claim
        # about core content.
        self.assertNotIn("core", _records_by_id(audit))

    def test_multipart_hull_findings_are_reused_from_complex_hull_audit(self) -> None:
        mod = ModInfo("composite_mod", "Composite Mod", "1.0", Path("mods/composite_mod"), True)
        parent = Hull("composite_parent", "Composite Parent", "composite_mod", SOURCE, hull_hints=("SHIP_WITH_MODULES",))
        parent_variant = Variant(
            "composite_parent_variant", "Composite Parent Variant", "composite_mod", SOURCE,
            hull_id="composite_parent", raw={"modules": [{"SM": "missing_child_variant"}]},
        )
        scan = ScanResult(mods=[mod], hulls=[parent], variants=[parent_variant])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        record = _records_by_id(audit)["composite_mod"]
        self.assertEqual(PARTIAL, record["classification"])
        self.assertTrue(record["multipart_hull_findings"])
        self.assertIn("UNRESOLVED_MODULE_VARIANT", {finding["code"] for finding in record["multipart_hull_findings"]})

    def test_summary_counts_match_records(self) -> None:
        mod = ModInfo("solo_mod", "Solo Mod", "1.0", Path("mods/solo_mod"), True)
        scan = ScanResult(mods=[mod])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        self.assertEqual(1, audit["summary"]["mods_classified"])
        self.assertEqual(1, audit["summary"]["by_classification"][PASS])
        self.assertEqual(0, audit["summary"]["by_classification"][PASS_WITH_UNKNOWNS])
        self.assertEqual(0, audit["summary"]["by_classification"][PARTIAL])
        self.assertEqual(0, audit["summary"]["by_classification"][FAIL])

    def test_never_emits_a_legality_verdict(self) -> None:
        """This module must never classify a mod as LEGAL/ILLEGAL/
        NOT_DETERMINABLE -- those are validation/legality.py's exclusive
        vocabulary (AGENTS.md's legality/quality boundary). The module's own
        `scope_note` prose is allowed to *name* those words while explaining
        that it deliberately stays out of that space; what must never happen
        is a record's `classification` field taking one of those values, and
        `validation.legality` must never be imported by this module."""
        import starsector_variant_generator.analysis.mod_acceptance as mod_acceptance_module
        for name, value in vars(mod_acceptance_module).items():
            module_of_value = getattr(value, "__module__", "")
            self.assertNotIn("validation", module_of_value, f"{name} pulls in {module_of_value}")

        mod = ModInfo("legality_free_mod", "Legality Free Mod", "1.0", Path("mods/legality_free_mod"), True)
        scan = ScanResult(mods=[mod])

        audit = audit_mod_acceptance(scan, Registry.from_scan(scan))

        for record in audit["records"]:
            self.assertIn(record["classification"], (PASS, PASS_WITH_UNKNOWNS, PARTIAL, FAIL))


if __name__ == "__main__":
    unittest.main()
