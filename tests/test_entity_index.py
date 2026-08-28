from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import EntityIndex

SOURCE = Path("fixture")


class EntityIndexDuplicateTests(unittest.TestCase):
    """Reproduces a real bug found against the live install: a third (or
    later) entity sharing an already-duplicated id matched neither of
    `build`'s two branches (`id in by_id` had already been popped away by
    the second claimant; `id not in duplicates` was now false too) and was
    silently dropped -- not indexed, not counted as a duplicate, gone
    entirely. Confirmed for real: the "hegemony" faction id has three real
    sources on a live 148-mod install (core, plus two separate mods each
    shipping a same-id `hegemony.faction` patch file); only two of the
    three ever reached `duplicates`."""

    def test_two_claimants_both_land_in_duplicates_and_by_id_is_cleared(self) -> None:
        a = Faction("f", "A", "mod_a", SOURCE)
        b = Faction("f", "B", "mod_b", SOURCE)
        index = EntityIndex.build([a, b])
        self.assertNotIn("f", index.by_id)
        self.assertEqual([a, b], index.duplicates["f"])

    def test_third_claimant_is_not_silently_dropped(self) -> None:
        a = Faction("f", "A", "mod_a", SOURCE)
        b = Faction("f", "B", "mod_b", SOURCE)
        c = Faction("f", "C", "mod_c", SOURCE)
        index = EntityIndex.build([a, b, c])
        self.assertNotIn("f", index.by_id)
        self.assertEqual([a, b, c], index.duplicates["f"])

    def test_fourth_claimant_is_also_retained(self) -> None:
        entities = [Faction("f", letter, f"mod_{letter.lower()}", SOURCE) for letter in "ABCD"]
        index = EntityIndex.build(entities)
        self.assertEqual(entities, index.duplicates["f"])

    def test_unrelated_ids_are_unaffected_by_a_separate_ids_collision(self) -> None:
        collided = [Faction("f", letter, f"mod_{letter.lower()}", SOURCE) for letter in "ABC"]
        unique = Faction("g", "Unique", "mod_g", SOURCE)
        index = EntityIndex.build([*collided, unique])
        self.assertEqual(collided, index.duplicates["f"])
        self.assertIs(unique, index.by_id["g"])

    def test_single_claimant_is_indexed_normally(self) -> None:
        only = Faction("f", "Only", "mod_a", SOURCE)
        index = EntityIndex.build([only])
        self.assertIs(only, index.by_id["f"])
        self.assertEqual({}, index.duplicates)


if __name__ == "__main__":
    unittest.main()
