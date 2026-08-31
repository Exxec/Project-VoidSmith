import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starsector_variant_generator.core.models import Hull, ScanResult, Variant
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.output.retrofit_library import (
    copy_existing_retrofit,
    inspect_editable_retrofit,
    load_editable_retrofit,
    populate_variations_if_missing,
    publish_editable_retrofit,
    restore_editable_retrofit_history,
    starter_profiles_for_hull,
    variants_for_hull,
    working_copy_path,
)


class RetrofitLibraryTests(unittest.TestCase):
    def test_existing_variant_is_copied_only_to_user_owned_library(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp); source = root / "source.variant"; source.write_text('{"variantId":"fit"}', encoding="utf-8")
            variant = Variant("fit", "Fit", "core", source, hull_id="h")
            target = copy_existing_retrofit(variant, root / "output", replace=True)
            self.assertEqual('{"variantId":"fit"}', target.read_text(encoding="utf-8"))
            self.assertEqual('{"variantId":"fit"}', source.read_text(encoding="utf-8"))

    def test_replacing_a_local_copy_keeps_a_content_addressed_history_version(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp); source = root / "source.variant"; source.write_text('{"variantId":"fit","displayName":"First"}', encoding="utf-8")
            variant = Variant("fit", "Fit", "core", source, hull_id="h")
            target = copy_existing_retrofit(variant, root / "output", replace=True)
            source.write_text('{"variantId":"fit","displayName":"Second"}', encoding="utf-8")
            copy_existing_retrofit(variant, root / "output", replace=True)
            backups = list((target.parent / ".history" / "fit").glob("*.variant"))
            self.assertEqual(1, len(backups))
            self.assertIn("First", backups[0].read_text(encoding="utf-8"))

    def test_restoring_history_preserves_the_current_local_copy_too(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp); source = root / "source.variant"; source.write_text('{"variantId":"fit","displayName":"First"}', encoding="utf-8")
            variant = Variant("fit", "Fit", "core", source, hull_id="h")
            target = copy_existing_retrofit(variant, root / "output", replace=True)
            source.write_text('{"variantId":"fit","displayName":"Second"}', encoding="utf-8")
            copy_existing_retrofit(variant, root / "output", replace=True)
            history = next((target.parent / ".history" / "fit").glob("*.variant"))
            restore_editable_retrofit_history(history, root / "output")
            self.assertIn("First", target.read_text(encoding="utf-8"))
            self.assertEqual(2, len(list((target.parent / ".history" / "fit").glob("*.variant"))))

    def test_hull_variant_lookup_is_stable_and_path_rejects_traversal(self) -> None:
        registry = Registry.from_scan(ScanResult(hulls=[Hull("h", "Hull", "core", Path("fixture"))], variants=[Variant("b", "B", "core", Path("b"), hull_id="h"), Variant("a", "A", "core", Path("a"), hull_id="h")]))
        self.assertEqual(("a", "b"), tuple(item.id for item in variants_for_hull(registry, "h")))
        with self.assertRaises(ValueError): working_copy_path(Path("out"), "../bad")

    def test_population_reports_existing_variants_without_writing_generated_ones(self) -> None:
        registry = Registry.from_scan(ScanResult(hulls=[Hull("h", "Hull", "core", Path("fixture"))], variants=[Variant("fit", "Fit", "core", Path("fit"), hull_id="h")]))
        with TemporaryDirectory() as temp:
            availability = populate_variations_if_missing(registry, "h", Path(temp))
        self.assertEqual(("fit",), tuple(item.id for item in availability.existing_variants))
        self.assertEqual((), availability.generated_paths)

    def test_local_reopen_rejects_paths_outside_the_user_owned_library(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp); outside = root / "source.variant"; outside.write_text('{"variantId":"bad"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_editable_retrofit(outside, root / "output")

    def test_inspection_keeps_malformed_local_file_visible_as_an_error(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp); library = root / "output" / "editable_retrofits"; library.mkdir(parents=True); path = library / "broken.variant"; path.write_text("not json", encoding="utf-8")
            record = inspect_editable_retrofit(path, root / "output", Registry())
            self.assertIsNone(record.variant_id)
            self.assertIsNone(record.legality)
            self.assertIsNotNone(record.message)

    def test_starter_profiles_are_hull_specific_but_have_stable_conservative_fallbacks(self) -> None:
        carrier = Hull("carrier", "Carrier", "core", Path("fixture"), fighter_bays=3, weapon_mounts=({"type": "BALLISTIC", "size": "SMALL"},))
        registry = Registry.from_scan(ScanResult(hulls=[carrier]))
        profiles = starter_profiles_for_hull(registry, "carrier")
        self.assertIn("CARRIER_SUPPORT", profiles)
        self.assertLessEqual(len(profiles), 3)
        self.assertEqual((), starter_profiles_for_hull(registry, "missing"))

    def test_population_records_attempted_and_generated_profiles(self) -> None:
        registry = Registry.from_scan(ScanResult(hulls=[Hull("h", "Hull", "core", Path("fixture"))]))
        with TemporaryDirectory() as temp:
            availability = populate_variations_if_missing(registry, "h", Path(temp))
        self.assertTrue(availability.attempted_profiles)
        self.assertEqual(availability.attempted_profiles, availability.generated_profiles)

    def test_publish_copies_only_the_local_editable_variant_to_a_separate_mod(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp); library = root / "output" / "editable_retrofits"; library.mkdir(parents=True)
            local = library / "fit.variant"; local.write_text('{"variantId":"fit","hullId":"h"}', encoding="utf-8")
            published = publish_editable_retrofit(local, root / "output")
            self.assertIn("VoidSmith Editable Retrofits", str(published))
            self.assertEqual(local.read_text(encoding="utf-8"), published.read_text(encoding="utf-8"))
            self.assertTrue((root / "output" / "VoidSmith Editable Retrofits" / "mod_info.json").is_file())
