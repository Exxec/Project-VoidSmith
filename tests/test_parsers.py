from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Hull
from starsector_variant_generator.parsers.common import csv_rows, json_file, parse_float, parse_int
from starsector_variant_generator.parsers.entities import (
    faction_from_file, hull_from_row, hull_from_skin, variant_from_file, weapon_from_row,
)


FIXTURES = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_numeric_parsers_normalize_optional_source_values(self) -> None:
        self.assertEqual(2, parse_int(" 2 "))
        self.assertEqual(2, parse_int("2.0"))
        self.assertIsNone(parse_int(""))
        self.assertIsNone(parse_int("   "))
        self.assertIsNone(parse_int(None))
        self.assertEqual(2.5, parse_float(" 2.5 "))

    def test_numeric_parsers_record_invalid_nonblank_values(self) -> None:
        warnings: list[dict[str, object]] = []
        self.assertEqual(7, parse_int("abc", 7, warnings=warnings, field="fighterBays"))
        self.assertEqual(1.5, parse_float("NaN", 1.5, warnings=warnings, field="maxFlux"))
        self.assertEqual([
            {"code": "INVALID_NUMERIC_VALUE", "expected_type": "int", "value": "abc", "field": "fighterBays"},
            {"code": "INVALID_NUMERIC_VALUE", "expected_type": "float", "value": "NaN", "field": "maxFlux"},
        ], warnings)

    def test_hull_numeric_field_preserves_invalid_raw_value_and_reports_it(self) -> None:
        warnings: list[dict[str, object]] = []
        hull = hull_from_row({"id": "bad_bays", "name": "Bad Bays", "fighter bays": "abc"}, "fixture_mod", Path("fixture.csv"), numeric_warnings=warnings)
        self.assertIsNone(hull.fighter_bays)
        self.assertEqual("abc", hull.raw["fighter bays"])
        self.assertEqual("fighterBays", warnings[0]["field"])
    def test_csv_rows_normalizes_literal_empty_single_quote_sentinel(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wing_data.csv"
            path.write_text("id,name\n'',Example\n", encoding="utf-8")
            self.assertEqual("", next(csv_rows(path))["id"])

    def test_csv_rows_skips_entire_commented_multiline_record(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data.csv"
            path.write_text('id,desc\nvalid,Normal\n#disabled,"line one\nline two"\n', encoding="utf-8")
            self.assertEqual(["valid"], [row["id"] for row in csv_rows(path)])

    def test_json_file_accepts_legacy_windows_1252_text(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.ship"
            path.write_bytes(b'{"name":"Myst\xe8re"}')
            self.assertEqual("Myst" + chr(0xE8) + "re", json_file(path)["name"])

    def test_vanilla_style_hull_normalizes_and_preserves_raw_fields(self) -> None:
        path = FIXTURES / "vanilla_mod/data/hulls/ship_data.csv"
        hull = hull_from_row(next(csv_rows(path)), "core", path)
        self.assertEqual("fixture_frigate", hull.id)
        self.assertEqual(45, hull.ordnance_points)
        self.assertEqual("preserve-me", hull.raw["customField"])

    def test_hull_reads_documented_weapon_slots_when_ship_file_is_present(self) -> None:
        csv_path = FIXTURES / "vanilla_mod/data/hulls/ship_data.csv"
        ship_path = FIXTURES / "vanilla_mod/data/hulls/fixture_frigate.ship"
        hull = hull_from_row(next(csv_rows(csv_path)), "core", csv_path, ship_path)
        self.assertEqual("WS 001", hull.weapon_mounts[0]["id"])
        self.assertEqual("BALLISTIC", hull.weapon_mounts[0]["type"])
        self.assertEqual(("BAY 001",), hull.launch_bay_slots)
        self.assertEqual(("fixture_wing",), hull.built_in_fighter_wings)
        self.assertEqual({"WS 002": "fixture_flak"}, hull.built_in_weapons)

    def test_hull_reads_documented_flux_fields(self) -> None:
        path = FIXTURES / "vanilla_mod/data/hulls/ship_data.csv"
        hull = hull_from_row(next(csv_rows(path)), "core", path)
        self.assertEqual(4000.0, hull.flux_capacity)
        self.assertEqual(120.0, hull.flux_dissipation)
        self.assertEqual(0.5, hull.shield_upkeep)
        self.assertEqual(1, hull.fighter_bays)

    def test_hull_reads_documented_civilian_stats_and_hints(self) -> None:
        path = FIXTURES / "vanilla_mod/data/hulls/ship_data.csv"
        hull = hull_from_row(next(csv_rows(path)), "core", path)
        self.assertEqual(40.0, hull.cargo_capacity)
        self.assertEqual(25.0, hull.fuel_capacity)
        self.assertEqual(25, hull.crew_min)
        self.assertEqual(50, hull.crew_max)
        self.assertEqual(4.0, hull.supplies_per_month)
        self.assertEqual(10.0, hull.max_burn)
        self.assertEqual(("CIVILIAN", "FREIGHTER"), hull.hull_hints)

    def test_hull_normalizes_sensor_profile_aliases(self) -> None:
        hull = hull_from_row({"id": "sensor_hull", "name": "Sensor Hull", "sensorProfile": "75"}, "fixture_mod", Path("fixture.csv"))
        self.assertEqual(75.0, hull.sensor_profile)

    def test_modded_column_aliases_are_supported_without_interpreting_mechanics(self) -> None:
        path = FIXTURES / "modded_mod/data/hulls/ship_data.csv"
        hull = hull_from_row(next(csv_rows(path)), "fixture_mod", path)
        self.assertEqual("modded_destroyer", hull.id)
        self.assertEqual("unknown_scripted_effect", hull.raw["customMechanic"])

    def test_weapon_normalizes_standard_and_modded_aliases(self) -> None:
        vanilla = FIXTURES / "vanilla_mod/data/weapons/weapon_data.csv"
        modded = FIXTURES / "modded_mod/data/weapons/weapon_data.csv"
        vanilla_weapon = weapon_from_row(next(csv_rows(vanilla)), "core", vanilla)
        self.assertEqual(700.0, vanilla_weapon.range)
        self.assertEqual(25.0, vanilla_weapon.flux_per_shot)
        self.assertEqual(150.0, vanilla_weapon.flux_per_second)
        weapon = weapon_from_row(next(csv_rows(modded)), "fixture_mod", modded)
        self.assertEqual("modded_lance", weapon.id)
        self.assertEqual("scripted", weapon.raw["customTag"])
        self.assertEqual("ENERGY", weapon.mount_type)

    def test_variant_extracts_only_declared_loadout_data(self) -> None:
        path = FIXTURES / "vanilla_mod/data/variants/fixture_frigate.variant"
        variant = variant_from_file(path, "core")
        self.assertEqual("fixture_frigate", variant.hull_id)
        self.assertEqual({"WS 001": "fixture_gun"}, variant.weapons_by_mount)
        self.assertEqual(("fixture_mod",), variant.hullmods)

    def test_faction_extracts_nested_known_equipment_lists(self) -> None:
        path = FIXTURES / "vanilla_mod/data/world/factions/fixture.faction"
        faction = faction_from_file(path, "core")
        self.assertEqual(("fixture_frigate",), faction.known_hulls)
        self.assertEqual(("fixture_gun",), faction.known_weapons)
        self.assertEqual(("fixture_wing",), faction.known_fighters)
        self.assertEqual(("fixture_mod",), faction.known_hullmods)

    def test_csv_supports_legacy_windows_1252_text(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.csv"
            path.write_bytes("id,name\nlegacy,Queen\x92s Ship\n".encode("latin-1"))
            self.assertEqual("Queen’s Ship", next(csv_rows(path))["name"])

    def test_json_escapes_legacy_control_characters_inside_strings(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.json"
            path.write_bytes(b'{"name":"bad\x16name"}')
            self.assertEqual("bad\x16name", json_file(path)["name"])

    def test_relaxed_json_accepts_bare_leading_decimal_numbers(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "skin_like.json"
            path.write_text('{"baseValueMult":.7, "negative":-.5, "list":[.25, .5], "name":".7 is not a number here"}', encoding="utf-8")
            data = json_file(path)
            self.assertEqual(0.7, data["baseValueMult"])
            self.assertEqual(-0.5, data["negative"])
            self.assertEqual([0.25, 0.5], data["list"])
            self.assertEqual(".7 is not a number here", data["name"])

    def test_relaxed_json_accepts_leading_unary_plus_numbers(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plus_like.json"
            path.write_text('{"renderOrderMod":+30, "list":[+5, -3, 1], "name":"literal +7 in string"}', encoding="utf-8")
            data = json_file(path)
            self.assertEqual(30, data["renderOrderMod"])
            self.assertEqual([5, -3, 1], data["list"])
            self.assertEqual("literal +7 in string", data["name"])

    def test_relaxed_json_accepts_hash_comments_trailing_commas_and_bare_keys(self) -> None:
        path = FIXTURES / "modded_mod/data/variants/relaxed.variant"
        variant = variant_from_file(path, "fixture_mod")
        self.assertEqual("relaxed_variant", variant.id)
        self.assertEqual(("fixture_mod",), variant.hullmods)

    def test_skin_overrides_declared_scalar_fields_and_keeps_the_rest(self) -> None:
        base = Hull("brawler", "Brawler", "core", Path("b"), hull_size="FRIGATE", ordnance_points=45)
        skin = hull_from_skin(base, {"skinHullId": "brawler_lg", "hullName": "Brawler (LG)", "ordnancePoints": 47}, "core", Path("brawler_lg.skin"))
        self.assertEqual("brawler_lg", skin.id)
        self.assertEqual("Brawler (LG)", skin.name)
        self.assertEqual(47, skin.ordnance_points)
        self.assertEqual("FRIGATE", skin.hull_size)

    def test_skin_removes_and_overrides_weapon_slots(self) -> None:
        base = Hull("brawler", "Brawler", "core", Path("b"), weapon_mounts=(
            {"id": "WS 001", "type": "BALLISTIC", "size": "SMALL"},
            {"id": "WS 002", "type": "ENERGY", "size": "SMALL"},
        ))
        skin = hull_from_skin(base, {
            "skinHullId": "brawler_lg",
            "removeWeaponSlots": ["WS 002"],
            "weaponSlotChanges": {"WS 001": {"type": "ENERGY"}},
        }, "core", Path("b.skin"))
        self.assertEqual(1, len(skin.weapon_mounts))
        self.assertEqual("ENERGY", skin.weapon_mounts[0]["type"])
        self.assertEqual("SMALL", skin.weapon_mounts[0]["size"])

    def test_skin_built_in_mods_are_additive_after_explicit_removal(self) -> None:
        base = Hull("h", "Hull", "core", Path("b"), built_in_hullmods=("armored_hull", "reinforced_hull"))
        skin = hull_from_skin(base, {"skinHullId": "h_skin", "removeBuiltInMods": ["armored_hull"], "builtInMods": ["fourteenth"]}, "core", Path("b.skin"))
        self.assertEqual(("reinforced_hull", "fourteenth"), skin.built_in_hullmods)

    def test_skin_built_in_weapons_removal_and_override(self) -> None:
        base = Hull("h", "Hull", "core", Path("b"), built_in_weapons={"WS 002": "old_weapon"})
        skin = hull_from_skin(base, {"skinHullId": "h_skin", "removeBuiltInWeapons": ["WS 002"], "builtInWeapons": {"WS 003": "new_weapon"}}, "core", Path("b.skin"))
        self.assertEqual({"WS 003": "new_weapon"}, skin.built_in_weapons)

    def test_skin_hints_are_added_and_removed(self) -> None:
        base = Hull("h", "Hull", "core", Path("b"), hull_hints=("CIVILIAN", "FREIGHTER"))
        skin = hull_from_skin(base, {"skinHullId": "h_skin", "removeHints": ["FREIGHTER"], "addHints": ["TANKER"]}, "core", Path("b.skin"))
        self.assertEqual(("CIVILIAN", "TANKER"), skin.hull_hints)

    def test_skin_without_a_usable_skin_hull_id_returns_none(self) -> None:
        base = Hull("h", "Hull", "core", Path("b"))
        self.assertIsNone(hull_from_skin(base, {}, "core", Path("b.skin")))

    def test_skin_preserves_unmodeled_fields_and_base_provenance_in_raw(self) -> None:
        base = Hull("h", "Hull", "core", Path("b"))
        skin = hull_from_skin(base, {"skinHullId": "h_skin", "maxSpeed": 90, "shieldEfficiency": 0.6}, "core", Path("b.skin"))
        self.assertEqual(90, skin.raw["skin_data"]["maxSpeed"])
        self.assertEqual("h", skin.raw["base_hull_id"])


if __name__ == "__main__":
    unittest.main()
