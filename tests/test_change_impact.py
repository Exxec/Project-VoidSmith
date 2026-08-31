from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.analysis.change_impact import analyze_change_impact
from starsector_variant_generator.core.cache import build_manifest
from starsector_variant_generator.core.knowledge_packs import load_knowledge_pack
from starsector_variant_generator.core.models import (
    Faction,
    FighterWing,
    Hull,
    Hullmod,
    ScanResult,
    Variant,
    Weapon,
)
from starsector_variant_generator.output.change_impact_report import (
    compact_change_impact,
    write_change_impact_report,
)

P = Path("fixture")

class ChangeImpactTests(unittest.TestCase):
    def test_weapon_change_invalidates_direct_variant_hull_and_faction_outputs(self) -> None:
        old = ScanResult(weapons=[Weapon("w", "W", "core", P, source_hash="old")])
        hull = Hull("h", "H", "core", P, source_hash="h")
        variant = Variant("v", "V", "core", P, source_hash="v", hull_id="h", weapons_by_mount={"A": "w"})
        faction = Faction("f", "F", "core", P, source_hash="f", known_hulls=("h",))
        report = analyze_change_impact(build_manifest(old), ScanResult(hulls=[hull], weapons=[Weapon("w", "W", "core", P, source_hash="new")], variants=[variant], factions=[faction]))
        self.assertEqual("CHANGED", next(c.status for c in report.changes if c.entity_id == "w"))
        self.assertIn(("variant_analysis", "v"), {(i.kind, i.target_id) for i in report.impacts})
        self.assertIn(("gap_recommendations", "f"), {(i.kind, i.target_id) for i in report.impacts})

    def test_duplicate_canonical_key_is_a_conflict(self) -> None:
        first = Weapon("w", "W", "core", P, source_hash="a")
        second = Weapon("w", "W2", "core", P, source_hash="b")
        report = analyze_change_impact(None, ScanResult(weapons=[first, second]))
        self.assertEqual("CONFLICTED", report.changes[0].status)
        self.assertTrue(report.warnings)

    def test_same_id_at_distinct_source_paths_is_not_a_conflict(self) -> None:
        first = Weapon("w", "W", "core", P, source_hash="a")
        second = Weapon("w", "W2", "core", Path("other"), source_hash="b")
        report = analyze_change_impact(None, ScanResult(weapons=[first, second]))
        self.assertEqual(["ADDED", "ADDED"], [change.status for change in report.changes])

    def test_removal_uses_conservative_review_target(self) -> None:
        old = build_manifest(ScanResult(weapons=[Weapon("w", "W", "core", P, source_hash="old")]))
        report = analyze_change_impact(old, ScanResult())
        self.assertIn(("scan_analysis_review", "CONSERVATIVE"), {(i.kind, i.certainty) for i in report.impacts})

    def test_compact_impact_contains_counts_not_entity_records(self) -> None:
        report = analyze_change_impact(None, ScanResult(weapons=[Weapon("w", "W", "core", P, source_hash="new")]))
        compact = compact_change_impact(report)
        self.assertEqual({"ADDED": 1}, compact["changes_by_status"])
        self.assertNotIn("changes", compact)

    def test_changed_pack_source_marks_knowledge_pack_freshness_and_report_is_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack_path = Path(temp) / "pack.json"
            pack_path.write_text(json.dumps({"manifest": {"schema_version":"1", "pack_version":"1", "target_faction_id":"f", "target_mod_id":"core", "source_hashes":{"weapon:w":"old"}, "authored_date":"2026-01-01", "authorship_method":"HUMAN_AUTHORED"}, "faction": {}}), encoding="utf-8")
            pack = load_knowledge_pack(pack_path)
            report = analyze_change_impact(build_manifest(ScanResult(weapons=[Weapon("w", "W", "core", P, source_hash="old")])), ScanResult(weapons=[Weapon("w", "W", "core", P, source_hash="new")]), (pack,))
            self.assertIn(("knowledge_pack_freshness", str(pack_path)), {(i.kind, i.target_id) for i in report.impacts})
            out = Path(temp) / "reports" / "impact.json"
            write_change_impact_report(report, out)
            self.assertEqual("change-impact-0.1", json.loads(out.read_text(encoding="utf-8"))["schema_version"])

    def test_direct_impacts_reverse_index_matches_original_scan_per_change_output(self) -> None:
        """Golden-output regression for _direct_impacts's reverse-index lookup.

        This scenario was used to capture the *original* O(changed x variants)
        implementation's exact output before it was replaced with per-category
        reverse-index dicts (weapon/hullmod/fighter/hull id -> variants), so a
        future change to that lookup can be checked against this test instead
        of re-deriving the golden values by hand. It deliberately covers a
        variant (v1) that references the same weapon/hullmod/fighter id more
        than once (two mounts sharing weapon "w1"; a duplicated hullmod and
        fighter-wing entry) -- the case where a reverse index could plausibly
        list a variant twice for one changed entity, which must still collapse
        to the same single-token `because` set the original membership-test
        scan produced (each `add()` call is a set union, so duplicates are
        idempotent either way; this test is the proof)."""
        hulls = [Hull("h1", "H1", "core", P, source_hash="h1"), Hull("h2", "H2", "core", P, source_hash="h2")]
        weapons = [Weapon("w1", "W1", "core", P, source_hash="w1"), Weapon("w2", "W2", "core", P, source_hash="w2")]
        hullmods = [Hullmod("hm1", "HM1", "core", P, source_hash="hm1")]
        fighters = [FighterWing("f1", "F1", "core", P, source_hash="f1")]
        variants = [
            # v1: weapon w1 on two mounts, duplicated hullmod/fighter refs.
            Variant("v1", "V1", "core", P, source_hash="v1", hull_id="h1",
                    weapons_by_mount={"A": "w1", "B": "w1", "C": "w2"},
                    hullmods=("hm1", "hm1"), fighter_wings=("f1", "f1")),
            Variant("v2", "V2", "core", P, source_hash="v2", hull_id="h1",
                    weapons_by_mount={"A": "w1"}, hullmods=("hm1",), fighter_wings=("f1",)),
            Variant("v3", "V3", "core", P, source_hash="v3", hull_id="h2",
                    weapons_by_mount={"A": "w2"}, hullmods=(), fighter_wings=()),
        ]
        factions = [Faction("fac1", "FAC1", "core", P, source_hash="fac1", known_hulls=("h1", "h2"))]
        scan = ScanResult(hulls=hulls, weapons=weapons, hullmods=hullmods, fighters=fighters, variants=variants, factions=factions)

        def impact_set(report):
            return {(i.kind, i.target_id, i.certainty, i.because) for i in report.impacts}

        # Cold: previous_manifest=None -> every entity ADDED.
        cold = analyze_change_impact(None, scan)
        self.assertEqual(10, len(cold.changes))
        self.assertEqual(impact_set(cold), {
            ("build_archetype_profile", "h1", "EXACT", ("ADDED:fighters:core:f1:fixture", "ADDED:hullmods:core:hm1:fixture", "ADDED:hulls:core:h1:fixture", "ADDED:weapons:core:w1:fixture", "ADDED:weapons:core:w2:fixture")),
            ("build_archetype_profile", "h2", "EXACT", ("ADDED:hulls:core:h2:fixture", "ADDED:weapons:core:w2:fixture")),
            # New in ROADMAP Phase 34: fac1.known_hulls=("h1","h2") directly
            # evidences both hulls as faction impacts even before the
            # variant-cascade below independently reaches the same faction
            # via v1/v2/v3 -- see test_faction_known_list_impact_does_not_
            # require_a_referencing_variant below for the isolated case
            # where only this new path fires (no variant at all).
            ("faction_known_list", "fac1", "EXACT", ("ADDED:hulls:core:h1:fixture", "ADDED:hulls:core:h2:fixture")),
            ("faction_capability_profile", "fac1", "EXACT", ("ADDED:factions:core:fac1:fixture", "ADDED:fighters:core:f1:fixture", "ADDED:hullmods:core:hm1:fixture", "ADDED:hulls:core:h1:fixture", "ADDED:hulls:core:h2:fixture", "ADDED:weapons:core:w1:fixture", "ADDED:weapons:core:w2:fixture")),
            ("gap_recommendations", "fac1", "EXACT", ("ADDED:factions:core:fac1:fixture", "ADDED:fighters:core:f1:fixture", "ADDED:hullmods:core:hm1:fixture", "ADDED:hulls:core:h1:fixture", "ADDED:hulls:core:h2:fixture", "ADDED:weapons:core:w1:fixture", "ADDED:weapons:core:w2:fixture")),
            ("mechanical_profile", "h1", "EXACT", ("ADDED:fighters:core:f1:fixture", "ADDED:hullmods:core:hm1:fixture", "ADDED:hulls:core:h1:fixture", "ADDED:weapons:core:w1:fixture", "ADDED:weapons:core:w2:fixture")),
            ("mechanical_profile", "h2", "EXACT", ("ADDED:hulls:core:h2:fixture", "ADDED:weapons:core:w2:fixture")),
            ("variant_analysis", "v1", "EXACT", ("ADDED:fighters:core:f1:fixture", "ADDED:hullmods:core:hm1:fixture", "ADDED:hulls:core:h1:fixture", "ADDED:weapons:core:w1:fixture", "ADDED:weapons:core:w2:fixture")),
            ("variant_analysis", "v2", "EXACT", ("ADDED:fighters:core:f1:fixture", "ADDED:hullmods:core:hm1:fixture", "ADDED:hulls:core:h1:fixture", "ADDED:weapons:core:w1:fixture")),
            ("variant_analysis", "v3", "EXACT", ("ADDED:hulls:core:h2:fixture", "ADDED:weapons:core:w2:fixture")),
            ("weapon_profile", "w1", "EXACT", ("ADDED:weapons:core:w1:fixture",)),
            ("weapon_profile", "w2", "EXACT", ("ADDED:weapons:core:w2:fixture",)),
        })

        # Warm: previous_manifest == current -> all UNCHANGED, no impacts.
        manifest = build_manifest(scan)
        warm = analyze_change_impact(manifest, scan)
        self.assertEqual(10, len(warm.changes))
        self.assertTrue(all(change.status == "UNCHANGED" for change in warm.changes))
        self.assertEqual((), warm.impacts)

        # Partial: only weapon w1's hash differs -> cascades to v1, v2 (both
        # reference w1, v1 via two mounts), hull h1 (shared by v1/v2), and
        # faction fac1 (knows h1) -- but NOT v3/h2 (only reference w2).
        prior_entries = [dict(entry) for entry in manifest["entries"]]
        for entry in prior_entries:
            if entry["category"] == "weapons" and entry["id"] == "w1":
                entry["source_hash"] = "OLD_HASH"
        partial = analyze_change_impact({"schema_version": 1, "entries": prior_entries}, scan)
        self.assertEqual("CHANGED", next(c.status for c in partial.changes if c.entity_id == "w1"))
        self.assertEqual(impact_set(partial), {
            ("build_archetype_profile", "h1", "EXACT", ("CHANGED:weapons:core:w1:fixture",)),
            ("faction_capability_profile", "fac1", "EXACT", ("CHANGED:weapons:core:w1:fixture",)),
            ("gap_recommendations", "fac1", "EXACT", ("CHANGED:weapons:core:w1:fixture",)),
            ("mechanical_profile", "h1", "EXACT", ("CHANGED:weapons:core:w1:fixture",)),
            ("variant_analysis", "v1", "EXACT", ("CHANGED:weapons:core:w1:fixture",)),
            ("variant_analysis", "v2", "EXACT", ("CHANGED:weapons:core:w1:fixture",)),
            ("weapon_profile", "w1", "EXACT", ("CHANGED:weapons:core:w1:fixture",)),
        })

    # --- ROADMAP Phase 34: transitive-impact extension regression tests ---
    # Synthetic-fixture only, per this project's standing rule (no real
    # Starsector/mod data in the committed suite).

    def test_faction_known_list_impact_does_not_require_a_referencing_variant(self) -> None:
        """A faction's known_weapons entry evidences impact even with zero variants.

        This is the real gap Phase 34 closes: before this change, a faction
        impact only ever appeared via the variant-reference cascade (a
        variant equips the changed id AND the faction knows that variant's
        hull). A faction can genuinely know a weapon with no variant
        currently equipping it (a real, legal state made more common by
        Registry.resolve_faction's SVG-015 same-id faction merge) -- that
        case previously produced no faction impact evidence at all.
        """
        faction = Faction("fac", "FAC", "core", P, source_hash="fac", known_weapons=("w1",))
        old = ScanResult(weapons=[Weapon("w1", "W1", "core", P, source_hash="old")], factions=[faction])
        new = ScanResult(weapons=[Weapon("w1", "W1", "core", P, source_hash="new")], factions=[faction])
        report = analyze_change_impact(build_manifest(old), new)
        impacts = {(i.kind, i.target_id, i.certainty) for i in report.impacts}
        self.assertIn(("faction_known_list", "fac", "EXACT"), impacts)
        # No variant references "w1" at all, so the pre-existing
        # variant-cascade impacts must stay genuinely absent here.
        self.assertFalse(any(i.kind == "variant_analysis" for i in report.impacts))
        self.assertFalse(any(i.kind == "faction_capability_profile" for i in report.impacts))

    def test_faction_known_list_impact_is_absent_without_real_known_list_evidence(self) -> None:
        """No faction_known_list impact when the id is genuinely not known by any faction."""
        old = ScanResult(weapons=[Weapon("w1", "W1", "core", P, source_hash="old")])
        faction = Faction("fac", "FAC", "core", P, source_hash="fac", known_weapons=("other_weapon",))
        new = ScanResult(weapons=[Weapon("w1", "W1", "core", P, source_hash="new")], factions=[faction])
        report = analyze_change_impact(build_manifest(old), new)
        self.assertFalse(any(i.kind == "faction_known_list" for i in report.impacts))

    def test_knowledge_pack_reference_impact_from_actual_pack_content(self) -> None:
        """A pack's own hull_archetypes/approved_equipment content evidences impact.

        Distinct from the pre-existing `knowledge_pack_freshness` impact,
        which only fires when the pack author recorded a matching
        `manifest.source_hashes` entry. This pack deliberately records no
        source_hashes at all, so freshness must stay silent while the new
        content-reference check still fires from the pack's real
        hull_archetypes/approved_equipment entries.
        """
        with tempfile.TemporaryDirectory() as temp:
            pack_path = Path(temp) / "pack.json"
            pack_path.write_text(json.dumps({
                "manifest": {
                    "schema_version": "1", "pack_version": "1", "target_faction_id": "fac",
                    "target_mod_id": "core", "source_hashes": {},
                    "authored_date": "2026-01-01", "authorship_method": "HUMAN_AUTHORED",
                },
                "faction": {},
                "hull_archetypes": [{"hull_id": "h1", "archetype": "LINE_BRAWLER"}],
                "approved_equipment": [{"kind": "weapons", "id": "w1", "confidence": 0.8}],
            }), encoding="utf-8")
            pack = load_knowledge_pack(pack_path)
            self.assertIsNotNone(pack)
            old = ScanResult(hulls=[Hull("h1", "H1", "core", P, source_hash="old")],
                              weapons=[Weapon("w1", "W1", "core", P, source_hash="old")])
            new = ScanResult(hulls=[Hull("h1", "H1", "core", P, source_hash="new")],
                              weapons=[Weapon("w1", "W1", "core", P, source_hash="new")])
            report = analyze_change_impact(build_manifest(old), new, (pack,))
            impacts = {(i.kind, i.target_id) for i in report.impacts}
            self.assertIn(("knowledge_pack_reference", str(pack_path)), impacts)
            # No source_hashes were recorded, so the pre-existing freshness
            # check must genuinely stay silent -- proving these are two
            # independently evidenced, non-overlapping impact categories.
            self.assertNotIn(("knowledge_pack_freshness", str(pack_path)), impacts)

    def test_knowledge_pack_reference_impact_is_absent_when_pack_does_not_cite_the_id(self) -> None:
        """No knowledge_pack_reference impact for an id the pack's content never mentions."""
        with tempfile.TemporaryDirectory() as temp:
            pack_path = Path(temp) / "pack.json"
            pack_path.write_text(json.dumps({
                "manifest": {
                    "schema_version": "1", "pack_version": "1", "target_faction_id": "fac",
                    "target_mod_id": "core", "source_hashes": {},
                    "authored_date": "2026-01-01", "authorship_method": "HUMAN_AUTHORED",
                },
                "faction": {},
                "hull_archetypes": [{"hull_id": "some_other_hull", "archetype": "LINE_BRAWLER"}],
            }), encoding="utf-8")
            pack = load_knowledge_pack(pack_path)
            self.assertIsNotNone(pack)
            old = ScanResult(hulls=[Hull("h1", "H1", "core", P, source_hash="old")])
            new = ScanResult(hulls=[Hull("h1", "H1", "core", P, source_hash="new")])
            report = analyze_change_impact(build_manifest(old), new, (pack,))
            self.assertFalse(any(i.kind == "knowledge_pack_reference" for i in report.impacts))

    def test_adapter_coverage_impact_for_a_hullmod_with_a_verified_effect_table_entry(self) -> None:
        """A changed hullmod id present in a real adapters/vanilla effect table is flagged.

        "heavyarmor" is a real entry in DEFENSE_HULLMOD_EFFECTS
        (adapters/vanilla/__init__.py) -- genuine evidence, not a synthetic
        id, since this check's whole purpose is citing real adapter-table
        membership.
        """
        old = ScanResult(hullmods=[Hullmod("heavyarmor", "Heavy Armor", "core", P, source_hash="old")])
        new = ScanResult(hullmods=[Hullmod("heavyarmor", "Heavy Armor", "core", P, source_hash="new")])
        report = analyze_change_impact(build_manifest(old), new)
        matching = [i for i in report.impacts if i.kind == "adapter_coverage" and i.target_id == "heavyarmor"]
        self.assertEqual(1, len(matching))
        self.assertTrue(any("DEFENSE_HULLMOD_EFFECTS" in reason for reason in matching[0].because))

    def test_adapter_coverage_impact_is_absent_for_an_unmodeled_hullmod(self) -> None:
        """No adapter_coverage impact for a hullmod id no adapter table documents."""
        old = ScanResult(hullmods=[Hullmod("totally_unmodeled_hullmod", "X", "core", P, source_hash="old")])
        new = ScanResult(hullmods=[Hullmod("totally_unmodeled_hullmod", "X", "core", P, source_hash="new")])
        report = analyze_change_impact(build_manifest(old), new)
        self.assertFalse(any(i.kind == "adapter_coverage" for i in report.impacts))


if __name__ == "__main__": unittest.main()
