from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Faction, Hull, ScanResult
from starsector_variant_generator.gui.session import HullCatalog


class GuiSessionTests(unittest.TestCase):
    def test_hull_catalog_uses_normalized_hulls_without_inference(self) -> None:
        catalog = HullCatalog.from_scan(ScanResult(hulls=[
            Hull("a", "Aegis", "mod_a", Path("a"), hull_size="FRIGATE"),
            Hull("b", "Bastion", "mod_b", Path("b"), hull_size="CRUISER"),
        ]))
        self.assertEqual(("CRUISER", "FRIGATE"), catalog.hull_sizes())
        self.assertEqual(("Aegis",), tuple(hull.name for hull in catalog.filter("aeg", hull_size="FRIGATE")))
        self.assertEqual(("Bastion",), tuple(hull.name for hull in catalog.filter(source_mod="mod_b")))

    def test_faction_filter_uses_declared_membership_independently_of_source_mod(self) -> None:
        foreign_hull = Hull("foreign", "Foreign Hull", "hmi", Path("hmi"), hull_size="DESTROYER")
        core_hull = Hull("core", "Core Hull", "core", Path("core"), hull_size="DESTROYER")
        faction = Faction("persean", "Persean League", "core", Path("faction"), known_hulls=("foreign", "core"))
        catalog = HullCatalog.from_scan(ScanResult(hulls=[foreign_hull, core_hull], factions=[faction]))
        self.assertEqual(("Persean League",), catalog.faction_labels_for(foreign_hull))
        self.assertEqual(("Core Hull", "Foreign Hull"), tuple(hull.name for hull in catalog.filter(faction_key=("persean", "core"))))
