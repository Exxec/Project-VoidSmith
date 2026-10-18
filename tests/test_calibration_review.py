from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from starsector_variant_generator.analysis import calibration_propose, calibration_review
from starsector_variant_generator.analysis.calibration_review import (
    approve_rows,
    check_equipment,
    parse_row_spec,
    read_sheet,
    require_under,
    resolve_name,
    resolve_sheet,
)
from starsector_variant_generator.analysis.calibration_runner import CalibrationRun
from starsector_variant_generator.core.heuristics import REGISTRY, get_heuristic_set
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry

SRC = Path("fixture")
HEADER = ["ship_display", "loadout_text", "variant_id", "normalized_archetype_hints", "review_status"]
PENDING = "PROVISIONAL_REVIEW_REQUIRED"


def synthetic_scan() -> ScanResult:
    hulls = [
        Hull("alpha", "Alpha Frigate", "core", SRC / "alpha.ship", hull_size="FRIGATE", ordnance_points=20, source_hash="h1",
             weapon_mounts=({"id": "WS 1", "size": "SMALL", "type": "BALLISTIC"},)),
        Hull("alpha_d", "Alpha Frigate (D)", "core", SRC / "alpha_d.ship", source_hash="h2"),
        Hull("beta", "Beta Cruiser", "mod_one", SRC / "beta.ship", source_hash="h3"),
        Hull("beta", "Beta Cruiser", "mod_two", SRC / "beta2.ship", source_hash="h4"),
        Hull("gamma", "Gamma Destroyer", "core", SRC / "gamma.ship", source_hash="h5"),
        Hull("gamma_skin", "Gamma Destroyer", "core", SRC / "gamma.skin", source_hash="h6"),
    ]
    weapons = [Weapon("pulse_gun", "Pulse Gun", "core", SRC, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)]
    hullmods = [Hullmod("heavy_plating", "Heavy Plating", "core", SRC)]
    variants = [Variant("alpha_ok", "Alpha OK", "core", SRC, hull_id="alpha", weapons_by_mount={"WS 1": "pulse_gun"}),
                Variant("alpha_bad", "Alpha Bad", "core", SRC, hull_id="alpha", weapons_by_mount={"WS 1": "missing_gun"})]
    return ScanResult(hulls=hulls, weapons=weapons, hullmods=hullmods, variants=variants)


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows([HEADER, *rows])


class ResolveNameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hulls = synthetic_scan().hulls

    def test_exact_then_normalised_then_qualifier_rules(self) -> None:
        exact = resolve_name("Alpha Frigate", self.hulls)
        self.assertEqual(("EXACT_NAME", "alpha"), (exact.rule, exact.hull.id))
        self.assertEqual("NORMALISED_NAME", resolve_name("alpha-frigate", self.hulls).rule)
        self.assertEqual("QUALIFIER_STRIPPED", resolve_name("Alpha Frigate (Vanilla)", self.hulls).rule)

    def test_a_d_suffix_in_the_sheet_selects_the_damaged_hull(self) -> None:
        self.assertEqual("alpha_d", resolve_name("Alpha Frigate (D)", self.hulls).hull.id)

    def test_same_name_in_two_mods_is_ambiguous_and_lists_candidates(self) -> None:
        resolved = resolve_name("Beta Cruiser", self.hulls)
        self.assertEqual(("AMBIGUOUS", None), (resolved.rule, resolved.hull))
        self.assertEqual(("hull:mod_one:beta", "hull:mod_two:beta"), resolved.candidates)

    def test_a_skin_with_the_base_name_is_ambiguous_on_exact_but_base_preferred_after_stripping(self) -> None:
        self.assertEqual("AMBIGUOUS", resolve_name("Gamma Destroyer", self.hulls).rule)
        self.assertEqual("gamma", resolve_name("Gamma Destroyer (Vanilla)", self.hulls).hull.id)

    def test_a_miss_stays_unresolved(self) -> None:
        missed = resolve_name("Nothing Like It", self.hulls)
        self.assertEqual(("UNRESOLVED", None), (missed.rule, missed.hull))


class EquipmentTests(unittest.TestCase):
    def test_items_must_all_name_scanned_equipment(self) -> None:
        known = calibration_review.equipment_index(synthetic_scan())
        self.assertEqual(("TRUE", ()), check_equipment("2x Pulse Gun, Heavy Plating", known))
        self.assertEqual(("FALSE", ("keep cheap",)), check_equipment("1x Pulse Gun; keep cheap", known))
        self.assertEqual(("NOT_APPLICABLE", ()), check_equipment("  ", known))


class SheetWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "generated"
        self.scan = synthetic_scan()
        self.registry = Registry.from_scan(self.scan)
        self.sheet = self.root / "calibration" / "sheet.csv"
        write_csv(self.sheet, [
            ["Beta Cruiser", "", "", "TANK", PENDING],
            ["Alpha Frigate", "2x Pulse Gun", "alpha_ok", "SKIRMISHER;SURVEY", PENDING],
            ["Alpha Frigate", "free text note", "", "TANK", PENDING],
            ["Alpha Frigate", "Pulse Gun", "alpha_bad", "TANK", PENDING],
            ["Gamma Destroyer (Vanilla)", "", "", "TANK", PENDING],
        ])
        self.out = self.root / "calibration" / "sheet.resolved.csv"

    def resolve(self) -> list[dict[str, str]]:
        resolve_sheet(self.sheet, self.out, self.scan, self.registry, self.root)
        return read_sheet(self.out)[1]

    def test_resolve_adds_prechecks_and_sorts_ready_rows_first(self) -> None:
        rows = self.resolve()
        self.assertEqual(["2", "5", "1", "3", "4"], [r["row_id"] for r in rows])
        by_id = {r["row_id"]: r for r in rows}
        self.assertEqual("AMBIGUOUS", by_id["1"]["resolve_rule"])
        self.assertEqual("FALSE", by_id["3"]["equipment_ok"])
        self.assertEqual("free text note", by_id["3"]["equipment_unresolved"])
        self.assertEqual(("LEGAL", "TRUE"), (by_id["2"]["legality"], by_id["2"]["ready_for_review"]))
        self.assertEqual(("ILLEGAL", "FALSE"), (by_id["4"]["legality"], by_id["4"]["ready_for_review"]))
        self.assertEqual("hull:core:gamma", by_id["5"]["resolved_hull_key"])

    def test_the_original_sheet_is_not_changed_and_outside_paths_are_refused(self) -> None:
        before = self.sheet.read_bytes()
        self.resolve()
        self.assertEqual(before, self.sheet.read_bytes())
        with self.assertRaises(ValueError):
            resolve_sheet(self.sheet, Path(self.tmp.name) / "elsewhere.csv", self.scan, self.registry, self.root)
        with self.assertRaises(ValueError):
            require_under(Path(self.tmp.name) / "x.csv", self.root)

    def test_approval_needs_a_named_reviewer_and_only_ready_rows_are_approved(self) -> None:
        self.resolve()
        with self.assertRaises(ValueError):
            approve_rows(self.out, self.root, "  ", all_ready=True)
        result = approve_rows(self.out, self.root, "Pat Reviewer", rows=[2, 3, 99], today=date(2026, 10, 18))
        self.assertEqual(["2"], result["approved"])
        self.assertEqual({"3": "NOT_READY: failed a pre-check", "99": "NO_SUCH_ROW"}, {r["row_id"]: r["reason"] for r in result["refused"]})
        by_id = {r["row_id"]: r for r in read_sheet(self.out)[1]}
        self.assertEqual(("APPROVED", "Pat Reviewer", "2026-10-18"), (by_id["2"]["review_status"], by_id["2"]["approved_by"], by_id["2"]["approved_on"]))
        self.assertEqual(PENDING, by_id["3"]["review_status"])
        log = self.out.with_suffix(".approvals.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual({"reviewer": "Pat Reviewer", "date": "2026-10-18", "rows": ["2"]}, json.loads(log[0]))

    def test_all_ready_approves_every_ready_row_once(self) -> None:
        self.resolve()
        first = approve_rows(self.out, self.root, "Pat Reviewer", all_ready=True)
        self.assertEqual(["2", "5"], first["approved"])
        again = approve_rows(self.out, self.root, "Pat Reviewer", rows=[2])
        self.assertEqual("ALREADY_REVIEWED", again["refused"][0]["reason"])

    def test_approval_requires_a_resolved_sheet_and_exactly_one_selector(self) -> None:
        with self.assertRaises(ValueError):
            approve_rows(self.sheet, self.root, "Pat Reviewer", all_ready=True)
        self.resolve()
        with self.assertRaises(ValueError):
            approve_rows(self.out, self.root, "Pat Reviewer")

    def test_row_specs(self) -> None:
        self.assertEqual([3, 5, 6, 7], parse_row_spec("3,5-7"))
        for bad in ("a", "7-5", "1;2"):
            with self.assertRaises(ValueError):
                parse_row_spec(bad)

    def test_propose_measures_approved_rows_only_and_writes_an_unregistered_candidate(self) -> None:
        self.resolve()
        approve_rows(self.out, self.root, "Pat Reviewer", rows=[2])

        def fake(labels, scan, registry, set_id):
            actual = "SKIRMISHER" if set_id == "baseline_0.2" else "TANK"
            return CalibrationRun({lab.entity_key: {"entity_hash": lab.entity_hash, "actual": actual} for lab in labels}, (), {})
        out_dir = self.root / "calibration-proposals"
        with mock.patch.object(calibration_propose, "collect_all_observations", side_effect=fake):
            report = calibration_propose.propose(self.out, self.scan, self.registry, self.root, out_dir,
                                                 set_ids=["baseline_0.1", "baseline_0.2"], base_set="baseline_0.1", today=date(2026, 10, 18))
        self.assertEqual(1, report["approved_rows_used"])
        self.assertEqual((0, 1), (report["sets"]["baseline_0.1"]["matched"], report["sets"]["baseline_0.1"]["mismatched"]))
        self.assertEqual("baseline_0.2", report["best_measured_set"])
        self.assertEqual(1, len(report["moves"]["baseline_0.2"]))
        candidate = json.loads((out_dir / "candidate_heuristic_set_2026-10-18.json").read_text(encoding="utf-8"))
        self.assertEqual("PROPOSED_NOT_REGISTERED", candidate["status"])
        self.assertEqual(dict(get_heuristic_set("baseline_0.2").values), candidate["values"])
        self.assertNotIn(candidate["identifier"], REGISTRY)

    def test_propose_with_no_approved_rows_writes_no_candidate(self) -> None:
        self.resolve()
        out_dir = self.root / "calibration-proposals"
        report = calibration_propose.propose(self.out, self.scan, self.registry, self.root, out_dir, set_ids=["baseline_0.1"])
        self.assertEqual(0, report["approved_rows_used"])
        self.assertEqual([], list(out_dir.glob("candidate_*")))


if __name__ == "__main__":
    unittest.main()
