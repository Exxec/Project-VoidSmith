from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starsector_variant_generator import api
from starsector_variant_generator.analysis.fleet_advisory_boundaries import (
    fleet_advisory_boundaries,
)
from starsector_variant_generator.analysis.fleet_support import FleetSelection
from starsector_variant_generator.core.knowledge_packs import (
    load_knowledge_pack,
    resolve_knowledge_pack,
)
from starsector_variant_generator.core.models import Faction, ScanResult
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class FleetAdvisoryBoundaryTests(unittest.TestCase):
    def test_deployment_points_are_explicitly_indeterminate_not_a_zero_total(self) -> None:
        registry = Registry.from_scan(ScanResult())
        result = api.run_fleet_advisory_boundaries(registry, (FleetSelection("unresolved"),))
        self.assertEqual("NOT_DETERMINABLE", result.deployment_points.status)
        self.assertIsNone(result.deployment_points.total_deployment_points)
        self.assertEqual(("unresolved",), result.deployment_points.selected_entries)
        self.assertIn("not a normalized field", result.deployment_points.notes[0])

    def test_resolved_pack_guidance_is_visible_but_remains_advisory(self) -> None:
        payload = {
            "manifest": {"schema_version": "1", "pack_version": "1", "target_faction_id": "f", "target_mod_id": "core", "authored_date": "2026-08-28", "authorship_method": "HUMAN_AUTHORED"},
            "faction": {},
            "officer_guidance": [{"role": "LINE_BRAWLER", "notes": "Use only as guidance.", "confidence": .8}],
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "pack.json"; path.write_text(json.dumps(payload), encoding="utf-8")
            pack = load_knowledge_pack(path)
            registry = Registry.from_scan(ScanResult(factions=[Faction("f", "Faction", "core", SOURCE)]))
            resolved = resolve_knowledge_pack(pack, registry)
            result = fleet_advisory_boundaries((), registry, "f", resolved)
        self.assertEqual("PACK_GUIDANCE_AVAILABLE", result.officer_guidance.status)
        self.assertEqual("LINE_BRAWLER", result.officer_guidance.entries[0].role)
        self.assertEqual(.8, result.officer_guidance.entries[0].confidence)
        self.assertIn("not read or inferred", result.officer_guidance.notes[0])


if __name__ == "__main__":
    unittest.main()
