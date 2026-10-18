from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from test_campaign_edit_plan import source_hashes, synthetic_save

from starsector_variant_generator import api
from starsector_variant_generator.campaign.catalog import CommodityCatalog
from starsector_variant_generator.campaign.edit_plan import EditRequest
from starsector_variant_generator.campaign.overage import format_overage_lines, overage_preview
from starsector_variant_generator.gui.presentation import format_save_plan


class OveragePreviewUnitTests(unittest.TestCase):
    def test_cost_is_a_tenth_per_unit_over_and_capped_at_fifty_per_resource(self) -> None:
        preview = overage_preview({"cargo": Decimal(150), "fuel": Decimal(2000)}, {"cargo": Decimal(100), "fuel": Decimal(1000)})
        cargo, fuel, speed = preview
        self.assertEqual(("5", False), (cargo["supplies_per_day"], cargo["capped"]))
        self.assertEqual(("50", True), (fuel["supplies_per_day"], fuel["capped"]))
        self.assertEqual("2.0000", speed["worst_ratio"])
        self.assertEqual(["RC8-35"], speed["rows"])

    def test_nothing_over_means_no_preview(self) -> None:
        self.assertEqual((), overage_preview({"cargo": Decimal(100)}, {"cargo": Decimal(100)}))

    def test_unknown_dimensions_and_zero_capacity_are_skipped_not_guessed(self) -> None:
        self.assertEqual((), overage_preview({"fuel": Decimal(5)}, {"cargo": Decimal(1)}))
        self.assertEqual((), overage_preview({"fuel": Decimal(5)}, {"fuel": Decimal(0)}))

    def test_lines_cite_row_ids_and_say_the_write_stays_refused(self) -> None:
        text = "\n".join(format_overage_lines(overage_preview({"cargo": Decimal(150)}, {"cargo": Decimal(100)})))
        for needle in ("RC8-34", "RC8-35", "RC8-36", "stays refused", "UNKNOWN", "0.98a-RC8"):
            self.assertIn(needle, text)


class OveragePreviewPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = synthetic_save(self.root / "save")
        self.catalog = CommodityCatalog("PARSED", frozenset({"supplies"}), (("synthetic.csv", "neutral"),))

    def plan(self, value: int):
        return api.run_save_edit_plan(self.folder, (EditRequest("commodity:supplies", value),), self.catalog)

    def test_an_over_capacity_edit_is_previewed_but_stays_not_determinable_and_unwritable(self) -> None:
        before = source_hashes(self.folder)
        plan = self.plan(300)
        self.assertEqual("NOT_DETERMINABLE", plan.changes[0].outcome)
        cargo = plan.overage_preview[0]
        self.assertEqual(("cargo", "300", "100", "200", "20"), (cargo["dimension"], cargo["used"], cargo["capacity"], cargo["excess"], cargo["supplies_per_day"]))
        text = format_save_plan(plan)
        self.assertIn("OVERAGE PREVIEW", text)
        self.assertIn("RC8-34", text)
        result = api.run_save_edit_write(plan, self.root / "out")
        self.assertNotEqual("WRITTEN", result.status)
        self.assertFalse((self.root / "out").exists() and any((self.root / "out").rglob("campaign.xml")))
        self.assertEqual(before, source_hashes(self.folder))

    def test_even_with_the_capacity_opt_in_the_write_is_refused(self) -> None:
        plan = api.run_save_edit_plan(self.folder, (EditRequest("commodity:supplies", 300),), self.catalog, allow_unknown_capacity=True)
        self.assertTrue(plan.overage_preview)
        self.assertNotEqual("WRITTEN", api.run_save_edit_write(plan, self.root / "out").status)

    def test_a_within_capacity_edit_has_no_preview(self) -> None:
        plan = self.plan(50)
        self.assertEqual("ACCEPTED", plan.changes[0].outcome)
        self.assertEqual((), plan.overage_preview)
        self.assertNotIn("OVERAGE PREVIEW", format_save_plan(plan))


if __name__ == "__main__":
    unittest.main()
