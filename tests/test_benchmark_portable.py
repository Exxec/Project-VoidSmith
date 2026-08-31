"""Portable canonical-archetype regression suite -- runs everywhere, no Starsector install needed.

Uses hand-authored synthetic hulls (tests/fixtures/synthetic/*.json) that
represent benchmark archetypes -- structural stand-ins for well-known real
ship classes (frigate skirmisher, mixed destroyer, armored artillery
cruiser, carrier, heavy-broadside capital) -- rather than copied real
Starsector data. See docs/ROADMAP.md's "Canonical benchmark suite" section
for why this split exists, and tests/test_canonical_local.py for the
counterpart that runs against real named hulls when a Starsector install
is configured locally.
"""

from __future__ import annotations

import unittest

from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.core.models import ScanResult, Variant
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.candidate import (
    generate_conservative_candidate,
)
from starsector_variant_generator.validation.legality import (
    LegalityResult,
    validate_variant,
)
from tests.benchmark_support import (
    load_synthetic_archetype,
    mount_classes,
    registry_for,
)

ARCHETYPES = (
    "frigate_ballistic_aggressive",
    "destroyer_forward_mixed",
    "cruiser_armor_artillery",
    "carrier_strike_support",
    "capital_heavy_broadside",
)


class BenchmarkArchetypeTests(unittest.TestCase):
    def test_every_archetype_loads_and_parses_its_declared_mount_classes(self) -> None:
        expected = {
            "frigate_ballistic_aggressive": {"SMALL_BALLISTIC", "SMALL_MISSILE"},
            "destroyer_forward_mixed": {"MEDIUM_BALLISTIC", "MEDIUM_ENERGY", "SMALL_ENERGY", "SMALL_MISSILE"},
            "cruiser_armor_artillery": {"LARGE_BALLISTIC", "MEDIUM_BALLISTIC", "SMALL_MISSILE"},
            "carrier_strike_support": {"SMALL_BALLISTIC", "SMALL_ENERGY"},
            "capital_heavy_broadside": {"LARGE_BALLISTIC", "MEDIUM_BALLISTIC", "SMALL_MISSILE"},
        }
        for name in ARCHETYPES:
            hull, _ = load_synthetic_archetype(name)
            self.assertTrue(expected[name].issubset(mount_classes(hull)), f"{name}: {mount_classes(hull)}")

    def test_capital_archetype_has_the_highest_line_brawler_score(self) -> None:
        scores = {name: classify_hull(load_synthetic_archetype(name)[0]).role_compatibility["LINE_BRAWLER"] for name in ARCHETYPES}
        self.assertEqual("capital_heavy_broadside", max(scores, key=scores.get))

    def test_cruiser_archetype_has_the_highest_line_artillery_score(self) -> None:
        scores = {name: classify_hull(load_synthetic_archetype(name)[0]).role_compatibility["LINE_ARTILLERY"] for name in ARCHETYPES}
        self.assertEqual("cruiser_armor_artillery", max(scores, key=scores.get))

    def test_carrier_archetype_is_the_only_one_with_carrier_evidence(self) -> None:
        for name in ARCHETYPES:
            hull, _ = load_synthetic_archetype(name)
            carrier_score = classify_hull(hull).role_compatibility["CARRIER"]
            if name == "carrier_strike_support":
                self.assertEqual(1.0, carrier_score)
            else:
                self.assertEqual(0.0, carrier_score)

    def test_every_archetype_produces_a_legal_conservative_candidate(self) -> None:
        for name in ARCHETYPES:
            hull, weapons = load_synthetic_archetype(name)
            registry = registry_for(hull, weapons)
            result = generate_conservative_candidate(hull.id, "LINE_BRAWLER", registry)
            self.assertEqual(LegalityResult.LEGAL, result.legality, f"{name}: {result.omissions}")

    def test_an_energy_weapon_is_rejected_on_the_frigates_pure_ballistic_mount(self) -> None:
        frigate_hull, frigate_weapons = load_synthetic_archetype("frigate_ballistic_aggressive")
        _, destroyer_weapons = load_synthetic_archetype("destroyer_forward_mixed")
        energy_weapon = next(weapon for weapon in destroyer_weapons if weapon.mount_type == "ENERGY")
        registry = Registry.from_scan(ScanResult(hulls=[frigate_hull], weapons=[*frigate_weapons, energy_weapon]))
        variant = Variant("v", "V", "benchmark", frigate_hull.source_path, hull_id=frigate_hull.id, weapons_by_mount={"WS 001": energy_weapon.id})
        assessment = validate_variant(variant, registry)
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertIn("MOUNT_TYPE_MISMATCH", {finding.code for finding in assessment.failures})


if __name__ == "__main__":
    unittest.main()
