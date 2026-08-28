from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.profiles.advanced import load_advanced_request


class AdvancedRequestTests(unittest.TestCase):
    def test_loads_implemented_restrictions_without_gameplay_inference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "advanced.json"
            path.write_text(json.dumps({"profile": "LINE_ARTILLERY", "faction_mode": "FACTION_PLUS", "allowed_weapon_ids": ["a"], "denied_weapon_ids": ["b"], "locked_weapons_by_mount": {"WS 1": "a"}, "empty_mount_ids": ["WS 2"]}), encoding="utf-8")
            request = load_advanced_request(path)
            self.assertEqual("LINE_ARTILLERY", request.profile_id)
            self.assertEqual(frozenset({"a"}), request.allowed_weapon_ids)
            self.assertEqual({"WS 1": "a"}, request.locked_weapons_by_mount)

    def test_rejects_unsupported_or_conflicting_options(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "advanced.json"
            path.write_text('{"officer_skills": ["x"]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                load_advanced_request(path)
            path.write_text('{"locked_weapons_by_mount": {"A": "x"}, "empty_mount_ids": ["A"]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot lock and empty"):
                load_advanced_request(path)

    def test_scoring_weight_overrides_are_loaded_when_within_the_allowed_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "advanced.json"
            path.write_text(json.dumps({"scoring_weight_overrides": {"weight_flux_sustainability": 0.5, "weight_role_match": 0.1}}), encoding="utf-8")
            request = load_advanced_request(path)
            self.assertEqual({"weight_flux_sustainability": 0.5, "weight_role_match": 0.1}, request.scoring_weight_overrides)

    def test_survivability_weight_override_is_loaded_from_the_registered_weight_allow_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "advanced.json"
            path.write_text(json.dumps({"scoring_weight_overrides": {"weight_survivability": 0.4}}), encoding="utf-8")
            request = load_advanced_request(path)
            self.assertEqual({"weight_survivability": 0.4}, request.scoring_weight_overrides)

    def test_scoring_weight_overrides_defaults_to_none_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "advanced.json"
            path.write_text("{}", encoding="utf-8")
            request = load_advanced_request(path)
            self.assertIsNone(request.scoring_weight_overrides)

    def test_scoring_weight_overrides_rejects_an_unsupported_heuristic_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "advanced.json"
            path.write_text(json.dumps({"scoring_weight_overrides": {"artillery_min_range": 5000.0}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported keys"):
                load_advanced_request(path)

    def test_scoring_weight_overrides_rejects_a_negative_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "advanced.json"
            path.write_text(json.dumps({"scoring_weight_overrides": {"weight_role_match": -1.0}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-negative"):
                load_advanced_request(path)


if __name__ == "__main__":
    unittest.main()
