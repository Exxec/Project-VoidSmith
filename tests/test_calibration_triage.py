from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.analysis import calibration_review
from starsector_variant_generator.analysis.calibration_review import (
    add_alias,
    aliases_path,
    load_aliases,
    read_sheet,
    resolve_sheet,
)
from starsector_variant_generator.analysis.calibration_triage import (
    REASON_AMBIGUOUS,
    REASON_LEGALITY,
    REASON_LOADOUT,
    REASON_UNRESOLVED,
    compact_ids,
    render_text,
    triage_sheet,
    triage_sheets,
)
from starsector_variant_generator.core.registry import Registry
from tests.test_calibration_review import synthetic_scan

HEADER = ["ship_display", "faction_context", "loadout_text", "variant_id", "review_status"]
PENDING = "PROVISIONAL_REVIEW_REQUIRED"
# (display, faction, loadout, variant_id, review_status)
ROWS = [
    ("Alpha Frigate", "Hegemony", "2x Pulse Gun, Heavy Plating", "alpha_ok", PENDING),  # ready
    ("Heavy Mauler", "Hegemony", "Pulse Gun", "", PENDING),  # UNRESOLVED_NAME
    ("Alpha Frigate", "Hegemony", "Pulse Gun, Mystery Gun", "", PENDING),  # UNMATCHED_LOADOUT 'Mystery Gun'
    ("Alpha Frigate", "Pirates", "Pulse Gun", "alpha_bad", PENDING),  # LEGALITY_FAILED
    ("Beta Cruiser", "Hegemony", "Pulse Gun", "", PENDING),  # AMBIGUOUS_NAME
    ("Alpha Frigate", "Hegemony", "Pulse Gun", "alpha_ok", "APPROVED"),  # already reviewed: counted, not grouped
    ("Alpha Frigate", "Hegemony", "Pulse Gun", "", PENDING),  # ready
]


class TriageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "generated"
        self.batch = self.root / "batch"
        self.batch.mkdir(parents=True)
        self.raw = self.batch / "review.csv"
        self.resolved = self.batch / "review.resolved.csv"
        self.scan = synthetic_scan()
        self.registry = Registry.from_scan(self.scan)
        with self.raw.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(ROWS)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def resolve(self) -> None:
        resolve_sheet(self.raw, self.resolved, self.scan, self.registry, self.root,
                      aliases=load_aliases(aliases_path(self.batch, self.root)))

    def groups(self, reason: str) -> dict[str, dict[str, object]]:
        summary = triage_sheet(self.resolved, self.root)
        return {g["key"]: g for g in summary["not_ready_groups"] if g["reason"] == reason}  # type: ignore[index]

    def test_compact_ids_makes_ranges_for_approve(self) -> None:
        self.assertEqual("3,5-7,9", compact_ids([9, 7, 3, 6, 5, 5]))
        self.assertEqual("", compact_ids([]))

    def test_not_ready_rows_group_by_reason_with_count_examples_and_one_fix(self) -> None:
        self.resolve()
        summary = triage_sheet(self.resolved, self.root)
        self.assertEqual((7, 1, 2, 4), (summary["rows"], summary["reviewed"], summary["ready"], summary["not_ready"]))
        unresolved = self.groups(REASON_UNRESOLVED)["Heavy Mauler"]
        self.assertEqual((1, "2"), (unresolved["count"], unresolved["rows"]))
        self.assertIn('alias add "' + str(self.batch) + '" "Heavy Mauler" <hull id>', unresolved["fix_command"])
        loadout = self.groups(REASON_LOADOUT)["Mystery Gun"]
        self.assertEqual(("3", "--equipment"), (loadout["rows"], loadout["fix_command"].split()[-1]))
        self.assertIn("legality ILLEGAL", self.groups(REASON_LEGALITY)["ILLEGAL"]["fix"])
        ambiguous = self.groups(REASON_AMBIGUOUS)["Beta Cruiser"]
        self.assertEqual(["hull:mod_one:beta", "hull:mod_two:beta"], ambiguous["fix"].split(": ", 1)[1].split(", "))

    def test_ready_rows_group_by_hull_and_faction_with_a_person_run_approve_line(self) -> None:
        self.resolve()
        ready = triage_sheet(self.resolved, self.root)["ready_groups"]
        self.assertEqual(1, len(ready))
        self.assertEqual(("hull:core:alpha", "Hegemony", 2), (ready[0]["hull"], ready[0]["faction"], ready[0]["count"]))
        self.assertTrue(ready[0]["approve_command"].endswith('--reviewer "<your name>" --rows 1,7'))
        self.assertIn("calibration approve", ready[0]["approve_command"])

    def test_adding_an_alias_then_resolving_again_clears_the_group(self) -> None:
        self.resolve()
        add_alias(self.batch, self.root, "Heavy Mauler", "alpha")
        add_alias(self.batch, self.root, "Mystery Gun", "pulse_gun", equipment=True)
        self.resolve()
        rows = {row["row_id"]: row for row in read_sheet(self.resolved)[1]}
        self.assertEqual(("ALIAS", "TRUE"), (rows["2"]["resolve_rule"], rows["2"]["ready_for_review"]))
        self.assertEqual(("TRUE", "TRUE"), (rows["3"]["equipment_ok"], rows["3"]["ready_for_review"]))
        triaged = triage_sheet(self.resolved, self.root)
        self.assertNotIn(REASON_UNRESOLVED, {g["reason"] for g in triaged["not_ready_groups"]})
        self.assertNotIn(REASON_LOADOUT, {g["reason"] for g in triaged["not_ready_groups"]})

    def test_the_raw_sheet_is_never_changed_and_aliases_stay_under_generated(self) -> None:
        before = self.raw.read_bytes()
        self.resolve()
        add_alias(self.batch, self.root, "Heavy Mauler", "alpha")
        triage_sheets([self.resolved], self.root, write_dir=self.batch)
        self.assertEqual(before, self.raw.read_bytes())
        outside = Path(self.tmp.name) / "elsewhere"
        with self.assertRaises(ValueError):
            add_alias(outside, self.root, "X", "y")
        with self.assertRaises(ValueError):
            triage_sheets([self.resolved], self.root, write_dir=outside)
        with self.assertRaises(ValueError):
            triage_sheet(outside / "review.csv", self.root)

    def test_alias_sidecar_is_a_json_file_and_a_malformed_one_is_refused(self) -> None:
        add_alias(self.batch, self.root, "Heavy Mauler", "alpha")
        add_alias(self.batch, self.root, "Heavy Mauler", "beta", equipment=False)
        self.assertEqual({"heavymauler": "beta"}, load_aliases(aliases_path(self.batch, self.root)).hulls)
        self.assertEqual("calibration_aliases.json", calibration_review.ALIASES_FILE)
        aliases_path(self.batch, self.root).write_text("[1]", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_aliases(aliases_path(self.batch, self.root))

    def test_triage_output_is_text_by_default_and_json_when_written(self) -> None:
        self.resolve()
        summary = triage_sheets([self.resolved], self.root, write_dir=self.batch)
        text = render_text(summary)
        self.assertIn("Heavy Mauler", text)
        self.assertIn("calibration-triage.json", summary["written"])  # type: ignore[index]
        self.assertTrue(Path(summary["written"]).is_file())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
