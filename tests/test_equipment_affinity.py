from __future__ import annotations

import json
import tempfile
import unittest
from itertools import product
from pathlib import Path

from starsector_variant_generator.analysis.equipment_affinity import (
    classify_equipment_affinity,
    classify_equipment_availability,
)
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.knowledge_packs import (
    load_knowledge_pack,
    resolve_knowledge_pack,
)
from starsector_variant_generator.core.models import (
    Faction,
    FighterWing,
    Hull,
    Hullmod,
    ScanResult,
    Weapon,
)
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


def _naive_owners(entity_id: str, entity_kind: str, registry: Registry) -> tuple[str, ...]:
    """Reimplements the pre-optimization O(factions) per-call linear scan
    `classify_equipment_affinity` used before it gained a cached, per-
    `Registry` reverse ownership index (`analysis/equipment_affinity.py::
    _ownership_index`). Deliberately independent of that index's own code
    path, so this is a real oracle rather than the optimization checking
    itself: any future regression in the cached index's construction
    (missed entity, wrong id union across duplicate-id factions, etc.)
    would make `test_ownership_index_matches_naive_full_scan_across_a_mixed_registry`
    below fail even though nothing about this helper changed.
    """
    selector = {
        "weapons": lambda faction: faction.known_weapons,
        "fighters": lambda faction: faction.known_fighters,
        "hullmods": lambda faction: faction.known_hullmods,
        "hulls": lambda faction: faction.known_hulls,
    }[entity_kind]
    factions = list(registry.factions.by_id.values())
    for duplicate_group in registry.factions.duplicates.values():
        factions.extend(duplicate_group)
    return tuple(sorted({faction.id for faction in factions if entity_id in selector(faction)}))


class EquipmentAffinityTests(unittest.TestCase):
    def test_availability_only_uses_explicit_local_metadata(self) -> None:
        self.assertEqual("UNKNOWN", classify_equipment_availability(Weapon("plain", "Plain", "mod", SOURCE)))
        self.assertEqual("RARE", classify_equipment_availability(Weapon("rare", "Rare", "mod", SOURCE, raw={"tags": ["rare"]})))
        from starsector_variant_generator.core.models import Hullmod
        self.assertEqual("SECRET", classify_equipment_availability(Hullmod("hidden", "Hidden", "mod", SOURCE, hidden=True)))
        self.assertEqual("UNOBTAINABLE", classify_equipment_availability(Hullmod("built", "Built", "mod", SOURCE, built_in_only=True)))
    def test_an_item_no_faction_references_is_unaligned(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE, known_weapons=("other_gun",))
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        classification = classify_equipment_affinity("lonely_gun", "weapons", registry)
        self.assertEqual("UNALIGNED", classification.affinity)
        self.assertEqual((), classification.owning_faction_ids)
        # ROADMAP.md Phase 29: every non-APPROVED tier is real known_*-list
        # membership evidence -- DIRECT_DATA -- including the negative
        # (UNALIGNED) case, since "no faction lists it" is itself a directly
        # observed fact about the real parsed data, not an inference.
        self.assertEqual(EvidenceClass.DIRECT_DATA, classification.evidence_class)

    def test_an_item_the_requesting_faction_owns_is_native(self) -> None:
        faction = Faction("hegemony", "Hegemony", "core", SOURCE, known_weapons=("mygun",))
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        classification = classify_equipment_affinity("mygun", "weapons", registry, requesting_faction_id="hegemony")
        self.assertEqual("NATIVE", classification.affinity)
        self.assertEqual(("hegemony",), classification.owning_faction_ids)

    def test_an_item_one_other_faction_owns_is_foreign(self) -> None:
        owner = Faction("tritachyon", "Tri-Tachyon", "core", SOURCE, known_weapons=("theirgun",))
        requester = Faction("hegemony", "Hegemony", "core", SOURCE)
        registry = Registry.from_scan(ScanResult(factions=[owner, requester]))
        classification = classify_equipment_affinity("theirgun", "weapons", registry, requesting_faction_id="hegemony")
        self.assertEqual("FOREIGN", classification.affinity)
        self.assertEqual(("tritachyon",), classification.owning_faction_ids)

    def test_an_item_used_by_enough_factions_is_common(self) -> None:
        factions = [Faction(f"f{i}", f"F{i}", "core", SOURCE, known_weapons=("widegun",)) for i in range(4)]
        registry = Registry.from_scan(ScanResult(factions=factions))
        classification = classify_equipment_affinity("widegun", "weapons", registry, common_threshold=4)
        self.assertEqual("COMMON", classification.affinity)
        self.assertEqual(4, len(classification.owning_faction_ids))

    def test_requesting_factions_own_ownership_wins_over_common(self) -> None:
        factions = [Faction(f"f{i}", f"F{i}", "core", SOURCE, known_weapons=("widegun",)) for i in range(4)]
        registry = Registry.from_scan(ScanResult(factions=factions))
        classification = classify_equipment_affinity("widegun", "weapons", registry, requesting_faction_id="f0", common_threshold=4)
        self.assertEqual("NATIVE", classification.affinity)

    def test_fighters_and_hullmods_use_their_own_known_lists(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE, known_fighters=("wing_a",), known_hullmods=("mod_a",))
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        self.assertEqual("NATIVE", classify_equipment_affinity("wing_a", "fighters", registry, requesting_faction_id="f").affinity)
        self.assertEqual("NATIVE", classify_equipment_affinity("mod_a", "hullmods", registry, requesting_faction_id="f").affinity)
        self.assertEqual("UNALIGNED", classify_equipment_affinity("mod_a", "fighters", registry, requesting_faction_id="f").affinity)

    def test_hulls_use_their_own_known_hulls_list(self) -> None:
        faction = Faction("f", "Faction", "core", SOURCE, known_hulls=("hull_a",))
        registry = Registry.from_scan(ScanResult(factions=[faction]))
        self.assertEqual("NATIVE", classify_equipment_affinity("hull_a", "hulls", registry, requesting_faction_id="f").affinity)
        self.assertEqual("UNALIGNED", classify_equipment_affinity("hull_b", "hulls", registry, requesting_faction_id="f").affinity)

    def test_duplicate_id_factions_still_count_as_ownership_evidence(self) -> None:
        first = Faction("dup", "Dup1", "core", SOURCE, known_weapons=("shared_gun",))
        second = Faction("dup", "Dup2", "mod", SOURCE, known_weapons=())
        registry = Registry.from_scan(ScanResult(factions=[first, second]))
        classification = classify_equipment_affinity("shared_gun", "weapons", registry)
        self.assertEqual(("dup",), classification.owning_faction_ids)
        self.assertEqual("FOREIGN", classification.affinity)

    def test_unknown_entity_kind_raises_rather_than_silently_returning_nothing(self) -> None:
        registry = Registry.from_scan(ScanResult())
        with self.assertRaises(ValueError):
            classify_equipment_affinity("x", "not_a_real_kind", registry)

    def test_a_matching_pack_can_approve_foreign_equipment_without_overriding_native(self) -> None:
        owner = Faction("owner", "Owner", "other", SOURCE, known_weapons=("foreign_gun",))
        requester = Faction("f", "Faction", "core", SOURCE)
        weapon = Weapon("foreign_gun", "Foreign gun", "other", SOURCE)
        registry = Registry.from_scan(ScanResult(factions=[owner, requester], weapons=[weapon]))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pack.json"
            path.write_text(json.dumps({
                "manifest": {"schema_version": "1.0", "pack_version": "1", "target_faction_id": "f", "target_mod_id": "core", "authored_date": "2026-08-23", "authorship_method": "HUMAN_AUTHORED"},
                "faction": {"traits": []},
                "approved_equipment": [{"id": "foreign_gun", "kind": "weapons", "confidence": 0.9}],
            }), encoding="utf-8")
            pack = resolve_knowledge_pack(load_knowledge_pack(path), registry)
        classification = classify_equipment_affinity("foreign_gun", "weapons", registry, "f", knowledge_pack=pack)
        self.assertEqual("APPROVED", classification.affinity)
        self.assertAlmostEqual(0.9, classification.guidance_confidence)
        # ROADMAP.md Phase 29 (Evidence/Provenance Unification): APPROVED
        # comes from a resolved, human-authored knowledge-pack entry, the
        # shared vocabulary's CURATED_GUIDANCE class -- distinct from the
        # direct faction known_*-list membership every other tier uses.
        self.assertEqual(EvidenceClass.CURATED_GUIDANCE, classification.evidence_class)

    def test_ownership_index_matches_naive_full_scan_across_a_mixed_registry(self) -> None:
        """Golden-output regression for `_ownership_index`'s cached reverse
        lookup, mirroring `test_change_impact.py`'s
        `test_direct_impacts_reverse_index_matches_original_scan_per_change_output`
        pattern: `classify_equipment_affinity` used to rebuild
        `_all_factions(registry)` and linear-scan every faction's
        `known_*` tuple on EVERY call (`entity_id in selector(faction)`)
        -- O(entities x factions), measured costing real, non-trivial time
        in `gap_recommendation.py::recommend_acquisition_solutions`'s
        single pass over every indexed hull on the real 148-mod install.
        It was replaced with a reverse index (entity_kind -> {entity_id:
        owning faction ids}) built once per `Registry` and cached on that
        instance.

        This scenario deliberately covers: multiple entity kinds sharing
        one registry; an item owned by zero, one, several (but below
        `common_threshold`), and >= `common_threshold` factions; a
        duplicate-id faction pair (only one of the two knows the item,
        proving the union still credits the shared id); and both
        `requesting_faction_id=None` and a real requester so NATIVE
        wins over COMMON/FOREIGN are exercised. `_naive_owners` above is
        an independent reimplementation of the original per-call scan, so
        this test would catch a regression in the cached index itself,
        not just confirm the index agrees with the function that reads it.
        """
        common_owners = [Faction(f"common{i}", f"Common{i}", "core", SOURCE, known_weapons=("widegun",)) for i in range(4)]
        few_owners = [Faction(f"few{i}", f"Few{i}", "core", SOURCE, known_hullmods=("rare_mod",)) for i in range(2)]
        dup_first = Faction("dup", "Dup1", "core", SOURCE, known_fighters=("shared_wing",))
        dup_second = Faction("dup", "Dup2", "mod", SOURCE, known_fighters=())
        hull_owner = Faction("hullowner", "HullOwner", "core", SOURCE, known_hulls=("owned_hull",))
        requester = Faction("requester", "Requester", "core", SOURCE, known_weapons=("widegun",), known_hulls=("owned_hull",))
        factions = common_owners + few_owners + [dup_first, dup_second, hull_owner, requester]
        entities = [
            Weapon("widegun", "Wide Gun", "core", SOURCE), Weapon("lonely_gun", "Lonely Gun", "core", SOURCE),
            Hullmod("rare_mod", "Rare Mod", "core", SOURCE), FighterWing("shared_wing", "Shared Wing", "core", SOURCE),
            Hull("owned_hull", "Owned Hull", "core", SOURCE), Hull("unowned_hull", "Unowned Hull", "core", SOURCE),
        ]
        registry = Registry.from_scan(ScanResult(
            factions=factions, weapons=[e for e in entities if isinstance(e, Weapon)],
            hullmods=[e for e in entities if isinstance(e, Hullmod)],
            fighters=[e for e in entities if isinstance(e, FighterWing)],
            hulls=[e for e in entities if isinstance(e, Hull)],
        ))

        checks = [
            ("widegun", "weapons"), ("lonely_gun", "weapons"), ("rare_mod", "hullmods"),
            ("shared_wing", "fighters"), ("owned_hull", "hulls"), ("unowned_hull", "hulls"),
        ]
        requesting_ids = [None, "requester", "common0"]

        for (entity_id, entity_kind), requesting_id in product(checks, requesting_ids):
            with self.subTest(entity_id=entity_id, entity_kind=entity_kind, requesting_id=requesting_id):
                expected_owners = _naive_owners(entity_id, entity_kind, registry)
                actual = classify_equipment_affinity(entity_id, entity_kind, registry, requesting_id, common_threshold=4)
                self.assertEqual(expected_owners, actual.owning_faction_ids)
                # Independently re-derive the expected affinity tier from
                # the naive owners set, so this also catches a regression
                # in classify_equipment_affinity's own tier logic, not
                # just in the reverse index it now reads from.
                if requesting_id is not None and requesting_id in expected_owners:
                    expected_affinity = "NATIVE"
                elif not expected_owners:
                    expected_affinity = "UNALIGNED"
                elif len(expected_owners) >= 4:
                    expected_affinity = "COMMON"
                else:
                    expected_affinity = "FOREIGN"
                self.assertEqual(expected_affinity, actual.affinity)

        # Spot checks on the concrete expected values (not just agreement
        # with the naive oracle) for the trickiest cases. "widegun" is
        # owned by the 4 common_owners AND "requester" (5 total) --
        # requester's own known_weapons also lists it, deliberately, so
        # the no-requesting-faction case below still lands on COMMON.
        self.assertEqual(5, len(classify_equipment_affinity("widegun", "weapons", registry, common_threshold=4).owning_faction_ids))
        self.assertEqual("COMMON", classify_equipment_affinity("widegun", "weapons", registry, common_threshold=4).affinity)
        self.assertEqual("NATIVE", classify_equipment_affinity("widegun", "weapons", registry, "requester", common_threshold=4).affinity)
        self.assertEqual(("few0", "few1"), classify_equipment_affinity("rare_mod", "hullmods", registry, common_threshold=4).owning_faction_ids)
        self.assertEqual("FOREIGN", classify_equipment_affinity("rare_mod", "hullmods", registry, common_threshold=4).affinity)
        self.assertEqual(("dup",), classify_equipment_affinity("shared_wing", "fighters", registry, common_threshold=4).owning_faction_ids)
        self.assertEqual((), classify_equipment_affinity("lonely_gun", "weapons", registry, common_threshold=4).owning_faction_ids)

    def test_ownership_index_is_registry_scoped_not_globally_cached(self) -> None:
        """The reverse index the optimization introduced is cached ON the
        `Registry` instance (see `_OWNERSHIP_INDEX_ATTR`), not in a shared
        module-level structure keyed by id() or similar -- two distinct
        `Registry` objects, including ones built moments apart and
        possibly reusing memory addresses, must never see each other's
        ownership data."""
        registry_a = Registry.from_scan(ScanResult(factions=[Faction("f", "F", "core", SOURCE, known_weapons=("gun",))]))
        registry_b = Registry.from_scan(ScanResult(factions=[Faction("f", "F", "core", SOURCE, known_weapons=())]))
        # Prime registry_a's cache first.
        self.assertEqual(("f",), classify_equipment_affinity("gun", "weapons", registry_a, "f").owning_faction_ids)
        self.assertEqual((), classify_equipment_affinity("gun", "weapons", registry_b, "f").owning_faction_ids)
        # And the reverse order, to rule out call-order-dependent leakage.
        registry_c = Registry.from_scan(ScanResult(factions=[Faction("f", "F", "core", SOURCE, known_weapons=())]))
        registry_d = Registry.from_scan(ScanResult(factions=[Faction("f", "F", "core", SOURCE, known_weapons=("gun",))]))
        self.assertEqual((), classify_equipment_affinity("gun", "weapons", registry_c, "f").owning_faction_ids)
        self.assertEqual(("f",), classify_equipment_affinity("gun", "weapons", registry_d, "f").owning_faction_ids)


if __name__ == "__main__":
    unittest.main()
