from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.api import run_fit_summary, run_slot_eligible_weapons
from starsector_variant_generator.core.models import Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry


class GuiBackendBridgeTests(unittest.TestCase):
    def test_slot_eligibility_uses_backend_mount_rules(self) -> None:
        hull=Hull("h","Hull","core",Path("h"),weapon_mounts=({"id":"M","size":"MEDIUM","type":"HYBRID"},))
        small=Weapon("s","Small","core",Path("s"),size="SMALL",mount_type="BALLISTIC")
        energy=Weapon("e","Energy","core",Path("e"),size="MEDIUM",mount_type="ENERGY")
        missile=Weapon("m","Missile","core",Path("m"),size="SMALL",mount_type="MISSILE")
        registry=Registry.from_scan(ScanResult(hulls=[hull],weapons=[small,energy,missile]))
        self.assertEqual(["e","s"],[weapon.id for weapon in run_slot_eligible_weapons(registry,"h","M")])

    def test_fit_summary_uses_backend_legality_and_normalized_weapon_op(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "S", "size": "SMALL", "type": "BALLISTIC"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=4)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        summary = run_fit_summary(registry, Variant("fit", "Fit", "generated", Path("fit"), hull_id="h", weapons_by_mount={"S": "w"}))
        self.assertEqual("LEGAL", summary["legality"])
        self.assertEqual((4, 6), (summary["weapon_op_used"], summary["weapon_op_remaining"]))

    def test_slot_filter_hides_restricted_and_applies_strict_faction(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), weapon_mounts=({"id": "S", "size": "SMALL", "type": "BALLISTIC"},))
        native = Weapon("native", "Native", "core", Path("native"), size="SMALL", mount_type="BALLISTIC")
        hidden = Weapon("hidden", "Hidden", "core", Path("hidden"), size="SMALL", mount_type="BALLISTIC", raw={"tags": ["HIDDEN"]})
        foreign = Weapon("foreign", "Foreign", "core", Path("foreign"), size="SMALL", mount_type="BALLISTIC")
        from starsector_variant_generator.core.models import Faction
        faction = Faction("f", "Faction", "core", Path("f"), known_weapons=("native",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[native, hidden, foreign], factions=[faction]))
        self.assertEqual(["native"], [item.id for item in run_slot_eligible_weapons(registry, "h", "S", faction_id="f", faction_mode="STRICT_FACTION")])
        self.assertIn("hidden", [item.id for item in run_slot_eligible_weapons(registry, "h", "S", include_hidden=True)])
