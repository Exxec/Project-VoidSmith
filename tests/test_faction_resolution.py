from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Faction, ScanResult
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class FactionResolutionTests(unittest.TestCase):
    """Reproduces a real bug found against the live install: JaydeePiracy-5.2.2
    ships a partial `hegemony.faction` file (only `knownShips.hulls`, no `id`/
    `displayName`) that patches vanilla Hegemony's roster with `jdp_arcubus`
    rather than redefining the faction -- a common, real Starsector modding
    convention. Before this fix, `EntityIndex.build` treated the two same-id
    "hegemony" sources as an unresolved duplicate, so every caller either hit
    a hard "ambiguous" error or silently lost one side's known_* entries
    entirely (STRICT_FACTION/FACTION_PLUS generation silently degraded to no
    faction data at all -- see api.py's old `by_id.get(faction_id)`)."""

    def _split_hegemony_scan(self) -> ScanResult:
        core = Faction(
            "hegemony", "Hegemony", "core", SOURCE,
            known_hulls=("enforcer", "onslaught"), known_weapons=("hvd",), tags=("MILITARY",),
        )
        patch = Faction("hegemony", "hegemony", "JaydeePiracy", SOURCE, known_hulls=("jdp_arcubus",))
        return ScanResult(factions=[core, patch])

    def test_same_id_faction_sources_merge_known_hulls_by_default(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        faction = registry.resolve_faction("hegemony")
        self.assertIsNotNone(faction)
        assert faction is not None
        self.assertEqual(("enforcer", "jdp_arcubus", "onslaught"), faction.known_hulls)
        self.assertEqual(("hvd",), faction.known_weapons)

    def test_merge_prefers_identity_fields_from_the_more_complete_source(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        faction = registry.resolve_faction("hegemony")
        assert faction is not None
        self.assertEqual("Hegemony", faction.name)
        self.assertEqual(("MILITARY",), faction.tags)

    def test_explicit_source_mod_still_returns_one_unmerged_raw_source(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        faction = registry.resolve_faction("hegemony", source_mod="JaydeePiracy")
        assert faction is not None
        self.assertEqual(("jdp_arcubus",), faction.known_hulls)
        core_only = registry.resolve_faction("hegemony", source_mod="core")
        assert core_only is not None
        self.assertEqual(("enforcer", "onslaught"), core_only.known_hulls)

    def test_unresolvable_source_mod_returns_none(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        self.assertIsNone(registry.resolve_faction("hegemony", source_mod="NoSuchMod"))

    def test_unknown_faction_id_returns_none(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        self.assertIsNone(registry.resolve_faction("no_such_faction"))

    def test_single_source_faction_resolves_without_merging(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("carrier",))
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        self.assertIs(faction, registry.resolve_faction("f"))

    def test_faction_contributing_sources_lists_every_real_source_mod(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        self.assertEqual(("JaydeePiracy", "core"), registry.faction_contributing_sources("hegemony"))

    def test_faction_equipment_reports_merged_known_lists(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        equipment = registry.faction_equipment("hegemony")
        self.assertEqual(("enforcer", "jdp_arcubus", "onslaught"), equipment["known_hulls"])

    def test_faction_equipment_still_raises_for_a_faction_id_that_does_not_exist(self) -> None:
        registry = Registry.from_scan(self._split_hegemony_scan())
        with self.assertRaises(ValueError):
            registry.faction_equipment("no_such_faction")


if __name__ == "__main__":
    unittest.main()
