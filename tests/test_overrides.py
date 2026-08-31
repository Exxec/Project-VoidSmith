from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.core.overrides import (
    apply_role_tag_override,
    load_overrides,
)


class OverridesTests(unittest.TestCase):
    def test_missing_file_yields_no_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual({}, load_overrides(Path(temp), "weapons"))

    def test_loads_a_valid_entity_keyed_override_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "weapons.json"
            path.write_text(json.dumps({
                "example_weapon": {"role_tags": ["ARTILLERY", "KINETIC_PRESSURE"], "notes": "Example only."},
            }), encoding="utf-8")
            overrides = load_overrides(Path(temp), "weapons")
            self.assertEqual(("ARTILLERY", "KINETIC_PRESSURE"), overrides["example_weapon"].role_tags)
            self.assertEqual("Example only.", overrides["example_weapon"].notes)

    def test_malformed_json_yields_no_overrides_rather_than_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "weapons.json"
            path.write_text("{not valid json", encoding="utf-8")
            self.assertEqual({}, load_overrides(Path(temp), "weapons"))

    def test_a_malformed_entry_is_skipped_but_valid_entries_still_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "weapons.json"
            path.write_text(json.dumps({
                "bad_entry": {"role_tags": "not-a-list"},
                "good_entry": {"role_tags": ["PD"]},
            }), encoding="utf-8")
            overrides = load_overrides(Path(temp), "weapons")
            self.assertNotIn("bad_entry", overrides)
            self.assertEqual(("PD",), overrides["good_entry"].role_tags)

    def test_apply_role_tag_override_unions_rather_than_replaces(self) -> None:
        from starsector_variant_generator.core.overrides import EntityOverride
        base = ("KINETIC_PRESSURE",)
        override = EntityOverride("w", role_tags=("PD",), notes=None)
        self.assertEqual(("KINETIC_PRESSURE", "PD"), apply_role_tag_override(base, override))

    def test_apply_role_tag_override_is_a_noop_when_no_override_exists(self) -> None:
        base = ("KINETIC_PRESSURE",)
        self.assertEqual(base, apply_role_tag_override(base, None))


if __name__ == "__main__":
    unittest.main()
