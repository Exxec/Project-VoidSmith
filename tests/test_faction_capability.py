from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.faction_capability import analyze_faction_capability
from starsector_variant_generator.core.models import Faction, Hull, ScanResult
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class FactionCapabilityTests(unittest.TestCase):
    def test_best_hull_per_role_is_selected_from_known_hulls(self) -> None:
        carrier = Hull("carrier", "Carrier", "core", SOURCE, weapon_mounts=(), launch_bay_slots=("BAY", "BAY"))
        brawler = Hull("brawler", "Brawler", "core", SOURCE, weapon_mounts=tuple({"type": "BALLISTIC", "size": "MEDIUM"} for _ in range(8)))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("carrier", "brawler"))
        registry = Registry.from_scan(ScanResult(hulls=[carrier, brawler], factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        self.assertEqual(2, profile.known_hulls_examined)
        by_role = {rc.role: rc for rc in profile.role_capabilities}
        self.assertEqual("carrier", by_role["CARRIER"].best_hull_id)
        self.assertEqual(1.0, by_role["CARRIER"].best_score)
        self.assertEqual("brawler", by_role["LINE_BRAWLER"].best_hull_id)

    def test_unresolved_known_hull_is_reported_not_silently_dropped(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("missing_hull",))
        registry = Registry.from_scan(ScanResult(hulls=[], factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        self.assertEqual(0, profile.known_hulls_examined)
        self.assertEqual(("missing_hull",), profile.unresolved_known_hull_ids)
        self.assertEqual((), profile.role_capabilities)

    def test_civilian_role_coverage_is_the_union_of_known_hull_hints(self) -> None:
        freighter = Hull("freighter", "Freighter", "core", SOURCE, hull_hints=("CIVILIAN", "FREIGHTER"))
        tanker = Hull("tanker", "Tanker", "core", SOURCE, hull_hints=("CIVILIAN", "TANKER"))
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("freighter", "tanker"))
        registry = Registry.from_scan(ScanResult(hulls=[freighter, tanker], factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        self.assertEqual(("CIVILIAN", "FREIGHTER", "TANKER"), profile.civilian_role_coverage)

    def test_faction_with_no_known_hulls_yields_empty_evidence_not_an_exception(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE)
        registry = Registry.from_scan(ScanResult(hulls=[], factions=[faction]))
        profile = analyze_faction_capability(faction, registry)
        self.assertEqual(0, profile.known_hulls_examined)
        self.assertEqual((), profile.role_capabilities)
        self.assertEqual((), profile.civilian_role_coverage)

    def test_capability_vector_aggregates_best_available_hull_evidence(self) -> None:
        armored = Hull("armored", "Armored", "core", SOURCE, raw={"armor rating": 1400, "hitpoints": 10000})
        fast = Hull("fast", "Fast", "core", SOURCE, raw={"max speed": 110})
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("armored", "fast"))
        profile = analyze_faction_capability(faction, Registry.from_scan(ScanResult(hulls=[armored, fast], factions=[faction])))
        self.assertIn("ARMOR_TANKING", profile.capability_vector)
        self.assertIn("MOBILITY", profile.capability_vector)
        self.assertTrue(profile.capability_vector["MOBILITY"].supporting_evidence[0].startswith("Best faction hull:"))


if __name__ == "__main__":
    unittest.main()
