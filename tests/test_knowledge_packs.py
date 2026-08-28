from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.core.knowledge_packs import (
    approved_equipment_ids, assess_pack_freshness, build_archetype_preference, capability_gap_guidance, equipment_guidance_confidence,
    load_knowledge_pack, officer_guidance, progression_guidance_confidence, progression_hull_ids, resolve_knowledge_pack, retrofit_template_ids,
)
from starsector_variant_generator.core.models import Faction, Hull, ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.api import run_generate

SOURCE = Path("fixture")


def _minimal_pack(**manifest_overrides: object) -> dict:
    manifest = {
        "schema_version": "1.0", "pack_version": "0.1.0",
        "target_faction_id": "hmi", "target_mod_id": "hmi", "target_mod_version": "0.4.0e",
        "authored_date": "2026-08-22", "authorship_method": "AI_ASSISTED_REVIEW",
    }
    manifest.update(manifest_overrides)
    return {"manifest": manifest, "faction": {"traits": ["armor-heavy"]}}


class LoadKnowledgePackTests(unittest.TestCase):
    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(load_knowledge_pack(Path(temp) / "missing.json"))

    def test_malformed_json_returns_none_rather_than_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            path.write_text("{not valid", encoding="utf-8")
            self.assertIsNone(load_knowledge_pack(path))

    def test_missing_required_top_level_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            path.write_text(json.dumps({"manifest": _minimal_pack()["manifest"]}), encoding="utf-8")
            self.assertIsNone(load_knowledge_pack(path))

    def test_missing_required_manifest_field_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            del data["manifest"]["authored_date"]
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertIsNone(load_knowledge_pack(path))

    def test_invalid_authorship_method_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            path.write_text(json.dumps(_minimal_pack(authorship_method="MADE_UP")), encoding="utf-8")
            self.assertIsNone(load_knowledge_pack(path))

    def test_a_valid_pack_loads_with_its_example_only_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            data["example_only"] = True
            path.write_text(json.dumps(data), encoding="utf-8")
            pack = load_knowledge_pack(path)
            self.assertIsNotNone(pack)
            self.assertTrue(pack.example_only)
            self.assertEqual("hmi", pack.manifest.target_faction_id)
            self.assertEqual("1.0", pack.manifest.schema_version)

    def test_the_neutral_example_file_loads_and_validates(self) -> None:
        example_path = Path(__file__).parent.parent / "knowledge_packs" / "examples" / "faction.example.json"
        pack = load_knowledge_pack(example_path)
        self.assertIsNotNone(pack)
        self.assertTrue(pack.example_only)
        self.assertEqual("example_faction", pack.manifest.target_faction_id)
        self.assertEqual({}, pack.manifest.source_hashes)


class PackFreshnessTests(unittest.TestCase):
    def _load(self, temp: str, **manifest_overrides: object) -> object:
        path = Path(temp) / "pack.json"
        path.write_text(json.dumps(_minimal_pack(**manifest_overrides)), encoding="utf-8")
        return load_knowledge_pack(path)

    def test_incompatible_when_target_faction_does_not_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = self._load(temp)
            registry = Registry.from_scan(ScanResult())
            self.assertEqual("INCOMPATIBLE", assess_pack_freshness(pack, registry).status)

    def test_incompatible_when_target_mod_is_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = self._load(temp)
            faction = Faction("hmi", "HMI", "some_other_mod", SOURCE)
            registry = Registry.from_scan(ScanResult(factions=[faction]))
            self.assertEqual("INCOMPATIBLE", assess_pack_freshness(pack, registry).status)

    def test_current_when_no_source_hashes_recorded_and_faction_and_mod_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = self._load(temp)
            faction = Faction("hmi", "HMI", "hmi", SOURCE)
            registry = Registry.from_scan(ScanResult(factions=[faction]))
            self.assertEqual("CURRENT", assess_pack_freshness(pack, registry).status)

    def test_current_when_every_recorded_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = self._load(temp, source_hashes={"faction:hmi": "abc123"})
            faction = Faction("hmi", "HMI", "hmi", SOURCE, source_hash="abc123")
            registry = Registry.from_scan(ScanResult(factions=[faction]))
            self.assertEqual("CURRENT", assess_pack_freshness(pack, registry).status)

    def test_stale_when_no_recorded_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = self._load(temp, source_hashes={"faction:hmi": "old_hash"})
            faction = Faction("hmi", "HMI", "hmi", SOURCE, source_hash="new_hash")
            registry = Registry.from_scan(ScanResult(factions=[faction]))
            self.assertEqual("STALE", assess_pack_freshness(pack, registry).status)

    def test_partially_stale_when_some_but_not_all_hashes_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = self._load(temp, source_hashes={"faction:hmi": "match", "hull:roach_king": "stale"})
            faction = Faction("hmi", "HMI", "hmi", SOURCE, source_hash="match")
            hull = Hull("roach_king", "Roach King", "hmi", SOURCE, source_hash="changed")
            registry = Registry.from_scan(ScanResult(factions=[faction], hulls=[hull]))
            self.assertEqual("PARTIALLY_STALE", assess_pack_freshness(pack, registry).status)


class ResolveKnowledgePackTests(unittest.TestCase):
    def test_build_archetype_preference_is_optional_and_stale_adjusted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack(source_hashes={"faction:hmi": "old"})
            data["build_archetype_preferences"] = [{"build_id": "TANK", "preference": 0.9, "confidence": 0.8}]
            path.write_text(json.dumps(data), encoding="utf-8")
            pack = load_knowledge_pack(path)
            faction = Faction("hmi", "HMI", "hmi", SOURCE, source_hash="new")
            resolved = resolve_knowledge_pack(pack, Registry.from_scan(ScanResult(factions=[faction])))
            self.assertEqual((0.9, 0.4), build_archetype_preference(resolved, "hmi", "TANK"))
    def test_unresolved_hull_reference_is_dropped_and_recorded_not_silently_lost(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            data["hull_archetypes"] = [
                {"hull_id": "roach_king", "basis": ["EXISTING_VARIANTS"], "confidence": 0.8},
                {"hull_id": "removed_hull", "basis": ["EXISTING_VARIANTS"], "confidence": 0.5},
            ]
            path.write_text(json.dumps(data), encoding="utf-8")
            pack = load_knowledge_pack(path)
            faction = Faction("hmi", "HMI", "hmi", SOURCE)
            hull = Hull("roach_king", "Roach King", "hmi", SOURCE)
            registry = Registry.from_scan(ScanResult(factions=[faction], hulls=[hull]))
            resolved = resolve_knowledge_pack(pack, registry)
            self.assertEqual(1, len(resolved.hull_archetypes))
            self.assertEqual("roach_king", resolved.hull_archetypes[0]["hull_id"])
            self.assertEqual(1, len(resolved.unresolved_references))
            self.assertIn("removed_hull", resolved.unresolved_references[0])

    def test_resolves_only_real_approved_equipment_and_records_bad_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            data["approved_equipment"] = [
                {"id": "foreign_gun", "kind": "weapons", "confidence": 0.8},
                {"id": "missing_gun", "kind": "weapons", "confidence": 0.8},
            ]
            path.write_text(json.dumps(data), encoding="utf-8")
            pack = load_knowledge_pack(path)
            faction = Faction("hmi", "HMI", "hmi", SOURCE)
            from starsector_variant_generator.core.models import Weapon
            weapon = Weapon("foreign_gun", "Foreign gun", "other", SOURCE)
            resolved = resolve_knowledge_pack(pack, Registry.from_scan(ScanResult(factions=[faction], weapons=[weapon])))
            self.assertEqual(frozenset({"foreign_gun"}), approved_equipment_ids(resolved, "hmi", "weapons"))
            self.assertTrue(any("missing_gun" in item for item in resolved.unresolved_references))

    def test_stale_approval_remains_advisory_but_reduces_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack(source_hashes={"faction:hmi": "old"})
            data["approved_equipment"] = [{"id": "foreign_gun", "kind": "weapons", "confidence": 0.8}]
            path.write_text(json.dumps(data), encoding="utf-8")
            pack = load_knowledge_pack(path)
            faction = Faction("hmi", "HMI", "hmi", SOURCE, source_hash="new")
            from starsector_variant_generator.core.models import Weapon
            weapon = Weapon("foreign_gun", "Foreign gun", "other", SOURCE)
            resolved = resolve_knowledge_pack(pack, Registry.from_scan(ScanResult(factions=[faction], weapons=[weapon])))
            self.assertEqual("STALE", resolved.freshness.status)
            self.assertEqual(frozenset({"foreign_gun"}), approved_equipment_ids(resolved, "hmi", "weapons"))
            self.assertAlmostEqual(0.4, equipment_guidance_confidence(resolved, "hmi", "weapons", "foreign_gun"))

    def test_stale_capability_guidance_remains_visible_with_reduced_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack(source_hashes={"faction:hmi": "old"})
            data["capability_gap_guidance"] = [{"role": "LINE_ARTILLERY", "notes": "A documented doctrine caveat.", "basis": ["CURATED_GUIDE"], "confidence": 0.8}]
            path.write_text(json.dumps(data), encoding="utf-8")
            pack = load_knowledge_pack(path)
            faction = Faction("hmi", "HMI", "hmi", SOURCE, source_hash="new")
            resolved = resolve_knowledge_pack(pack, Registry.from_scan(ScanResult(factions=[faction])))
            self.assertEqual((("A documented doctrine caveat.", 0.4),), capability_gap_guidance(resolved, "hmi", "LINE_ARTILLERY"))

    def test_strict_generation_allows_a_resolved_approved_weapon_without_affecting_legality(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            data["approved_equipment"] = [{"id": "foreign_gun", "kind": "weapons", "confidence": 0.9}]
            path.write_text(json.dumps(data), encoding="utf-8")
            from starsector_variant_generator.core.models import Weapon
            faction = Faction("hmi", "HMI", "hmi", SOURCE)
            hull = Hull("hull", "Hull", "hmi", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
            weapon = Weapon("foreign_gun", "Foreign gun", "other", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
            registry = Registry.from_scan(ScanResult(factions=[faction], hulls=[hull], weapons=[weapon]))
            pack = resolve_knowledge_pack(load_knowledge_pack(path), registry)
            outcome = run_generate(registry, "baseline_0.2", "hull", "guided", profile="LINE_BRAWLER", faction_id="hmi", faction_mode="STRICT_FACTION", knowledge_pack=pack)
            self.assertEqual({"A": "foreign_gun"}, outcome.candidates[0].variant.weapons_by_mount)
            self.assertEqual("LEGAL", outcome.candidates[0].legality)


class ProgressionGuidanceTests(unittest.TestCase):
    def test_resolved_stage_hulls_are_advisory_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            data["progression_tiers"] = [{"tier": "EARLY", "recommended_hull_ids": ["b", "a", "a"]}]
            path.write_text(json.dumps(data), encoding="utf-8")
            faction = Faction("hmi", "HMI", "hmi", SOURCE)
            hulls = [Hull("a", "A", "hmi", SOURCE), Hull("b", "B", "hmi", SOURCE)]
            resolved = resolve_knowledge_pack(load_knowledge_pack(path), Registry.from_scan(ScanResult(factions=[faction], hulls=hulls)))
            self.assertEqual(("a", "b"), progression_hull_ids(resolved, "hmi", "EARLY"))
            self.assertEqual(1.0, progression_guidance_confidence(resolved, "hmi", "EARLY"))

    def test_resolved_retrofit_template_is_auditable_guidance_not_a_loadout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            data["retrofit_templates"] = [{
                "id": "anchor_refit", "hull_id": "anchor", "target_role": "LINE_BRAWLER",
                "category": "RETROFIT", "confidence": 0.8,
            }]
            path.write_text(json.dumps(data), encoding="utf-8")
            faction = Faction("hmi", "HMI", "hmi", SOURCE)
            hull = Hull("anchor", "Anchor", "hmi", SOURCE)
            resolved = resolve_knowledge_pack(load_knowledge_pack(path), Registry.from_scan(ScanResult(factions=[faction], hulls=[hull])))
            self.assertEqual((("anchor_refit", 0.8),), retrofit_template_ids(resolved, "hmi", "anchor", "LINE_BRAWLER"))
            self.assertEqual((), retrofit_template_ids(resolved, "hmi", "anchor", "LINE_ARTILLERY"))

    def test_officer_guidance_is_presentational_and_freshness_labelled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            data = _minimal_pack()
            data["officer_guidance"] = [{"role": "LINE_BRAWLER", "notes": "Advisory only.", "confidence": 0.7}]
            path.write_text(json.dumps(data), encoding="utf-8")
            faction = Faction("hmi", "HMI", "hmi", SOURCE)
            resolved = resolve_knowledge_pack(load_knowledge_pack(path), Registry.from_scan(ScanResult(factions=[faction])))
            self.assertEqual(0.7, officer_guidance(resolved, "hmi")[0]["guidance_confidence"])

if __name__ == "__main__":
    unittest.main()
