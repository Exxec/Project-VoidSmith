from __future__ import annotations

import shutil
import tempfile
import time
import unittest
import json
from pathlib import Path

from starsector_variant_generator.core.scanner import Scanner, ScanCancelled
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.models import FighterWing, Hullmod, ScanResult


FIXTURES = Path(__file__).parent / "fixtures"


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "game"
        shutil.copytree(FIXTURES / "game_install", self.root)
        shutil.copytree(FIXTURES / "vanilla_mod", self.root, dirs_exist_ok=True)
        shutil.copytree(FIXTURES / "modded_mod", self.root / "mods/fixture_mod", dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scans_core_and_only_enabled_mods(self) -> None:
        result = Scanner(self.root).scan()
        self.assertEqual(2, len(result.mods))
        self.assertEqual({"fixture_frigate", "fixture_frigate_lg", "modded_destroyer"}, {hull.id for hull in result.hulls})
        fixture_hull = next(hull for hull in result.hulls if hull.id == "fixture_frigate")
        self.assertEqual("WS 001", fixture_hull.weapon_mounts[0]["id"])
        fixture_weapon = next(weapon for weapon in result.weapons if weapon.id == "fixture_gun")
        self.assertEqual("BALLISTIC", fixture_weapon.mount_type)
        self.assertEqual("graphics/weapons/fixture_turret.png", fixture_weapon.raw["weapon_spec"]["turretSprite"])
        self.assertEqual("graphics/weapons/fixture_hardpoint.png", fixture_weapon.raw["weapon_spec"]["hardpointSprite"])
        self.assertEqual(64, len(fixture_weapon.source_hash or ""))
        self.assertEqual(3, len(result.variants))
        self.assertFalse(result.errors)
        self.assertTrue(all(mod.enabled is not None for mod in result.mods))

    def test_diagnostic_scan_can_include_disabled_installed_mods(self) -> None:
        disabled = self.root / "mods" / "disabled_fixture"
        shutil.copytree(FIXTURES / "game_install/mods/fixture_mod", disabled)
        shutil.copytree(FIXTURES / "modded_mod", disabled, dirs_exist_ok=True)
        info_path = disabled / "mod_info.json"
        info = json.loads(info_path.read_text(encoding="utf-8"))
        info["id"] = "disabled_fixture"
        info_path.write_text(json.dumps(info), encoding="utf-8")
        result = Scanner(self.root, include_disabled_mods=True).scan()
        self.assertIn("disabled_fixture", {mod.mod_id for mod in result.mods})
        self.assertIn("disabled_fixture", {hull.source_mod for hull in result.hulls})

    def test_extra_mod_paths_are_scanned_alongside_the_normal_enabled_set(self) -> None:
        # An external mod folder not installed under `<root>/mods/` at all
        # (e.g. a drag-and-dropped mod) -- extra_mod_paths adds it to the
        # scan without needing enabled_mods.json to know about it.
        external = Path(self.temp_dir.name) / "dropped" / "external_mod"
        shutil.copytree(FIXTURES / "game_install/mods/fixture_mod", external)
        shutil.copytree(FIXTURES / "modded_mod", external, dirs_exist_ok=True)
        info_path = external / "mod_info.json"
        info = json.loads(info_path.read_text(encoding="utf-8"))
        info["id"] = "external_mod"
        info_path.write_text(json.dumps(info), encoding="utf-8")
        result = Scanner(self.root, extra_mod_paths=(external,)).scan()
        self.assertIn("external_mod", {mod.mod_id for mod in result.mods})
        self.assertIn("external_mod", {hull.source_mod for hull in result.hulls})
        # Extra paths add to the normal source set -- they never replace it.
        self.assertIn("fixture_mod", {hull.source_mod for hull in result.hulls})
        self.assertIn("core", {hull.source_mod for hull in result.hulls})

    def test_skin_is_materialized_as_a_derived_hull(self) -> None:
        result = Scanner(self.root).scan()
        skin_hull = next(hull for hull in result.hulls if hull.id == "fixture_frigate_lg")
        self.assertEqual("Fixture Frigate (LG)", skin_hull.name)
        self.assertEqual(50, skin_hull.ordnance_points)
        mounts_by_id = {mount["id"]: mount for mount in skin_hull.weapon_mounts}
        self.assertNotIn("BAY 001", mounts_by_id)
        self.assertEqual("ENERGY", mounts_by_id["WS 001"]["type"])
        self.assertEqual({"WS 002": "fixture_flak"}, skin_hull.built_in_weapons)
        self.assertEqual(("fixture_wing",), skin_hull.built_in_fighter_wings)
        self.assertEqual(64, len(skin_hull.source_hash or ""))
        self.assertEqual("fixture_frigate", skin_hull.raw["base_hull_id"])
        self.assertIsInstance(skin_hull.raw["ship_data"], dict)
        self.assertEqual(str(next(hull for hull in result.hulls if hull.id == "fixture_frigate").source_path), skin_hull.raw["sprite_source_path"])

    def test_skin_with_unresolved_base_hull_is_reported_not_silently_dropped(self) -> None:
        result = Scanner(self.root).scan()
        self.assertNotIn("fixture_frigate_unresolved", {hull.id for hull in result.hulls})
        self.assertTrue(any("no_such_base_hull" in warning for warning in result.warnings))

    def test_prefers_starsector_core_directory_when_present(self) -> None:
        core = self.root / "starsector-core"
        core.mkdir()
        self.assertEqual(core, Scanner(self.root).discover_sources()[0].path)

    def test_report_records_heuristic_provenance_but_does_not_score(self) -> None:
        report = Scanner(self.root).scan().report("baseline_0.1")
        self.assertEqual("baseline_0.1", report["heuristic_set"])
        self.assertEqual(2, report["counts"]["weapons"])
        self.assertNotIn("scores", report)

    def test_compact_report_omits_raw_source_entities(self) -> None:
        report = Scanner(self.root).scan().report("baseline_0.1", include_entities=False)
        self.assertEqual(2, report["counts"]["weapons"])
        self.assertNotIn("entities", report)

    def test_scan_emits_staged_progress_and_records_workload_metrics(self) -> None:
        progress = []
        result = Scanner(self.root, progress_callback=progress.append).scan()
        # PARSING now emits exactly one event per source (the initial
        # "total sources is now known" event, then one per source as its
        # future is harvested via as_completed()) instead of a "starting" +
        # "done" pair -- as_completed() only yields a future once it has
        # already resolved, so a separate pre-wait event no longer reflects
        # anything real. See Phase 37's WORK_LOG entry.
        self.assertEqual(
            ["DISCOVERING", "PARSING",
             "FINGERPRINTING", "FINGERPRINTING", "FINGERPRINTING", "FINGERPRINTING",
             "PARSING", "PARSING",
             "RESOLVING_REFERENCES", "COMPLETE"],
            [item.stage for item in progress],
        )
        # Every per-source event now names the real source it concerns, not
        # just an aggregate count -- every FINGERPRINTING event and every
        # PARSING event after the initial "total sources is now known" one.
        self.assertTrue(all(item.current_source for item in progress if item.stage == "FINGERPRINTING"))
        parsing_events = [item for item in progress if item.stage == "PARSING"]
        self.assertTrue(all(item.current_source for item in parsing_events[1:]))
        self.assertIsNotNone(result.scan_metrics)
        assert result.scan_metrics is not None
        self.assertEqual(2, result.scan_metrics.sources_scanned)
        self.assertGreater(result.scan_metrics.files_hashed, 0)
        self.assertGreaterEqual(result.scan_metrics.stage_seconds["total"], 0.0)
        # Fingerprinting and source-parsing are now broken out from the
        # combined "parsing" bucket (which still exists, unchanged, as the
        # sum of both plus the final merge) so a caller can see how much of
        # a scan is spent hash-checking cache eligibility versus actually
        # parsing/re-parsing sources.
        self.assertGreaterEqual(result.scan_metrics.stage_seconds["fingerprinting"], 0.0)
        self.assertGreaterEqual(result.scan_metrics.stage_seconds["source_parsing"], 0.0)
        self.assertGreaterEqual(result.scan_metrics.stage_seconds["parsing"], result.scan_metrics.stage_seconds["fingerprinting"])
        self.assertIn("scan_metrics", result.report("baseline_0.1", include_entities=False))

    def test_fingerprinting_progress_reports_incrementally_even_on_a_fully_cold_cache(self) -> None:
        """Regression test: on a first-ever scan (every source a cache miss),
        the fingerprint-check pass used to report nothing at all -- real
        progress only resumed once the first source's actual parse future
        resolved, which on a large real install can be most of a scan's
        duration with zero visible movement. FINGERPRINTING events must
        report a real, monotonically increasing completed/total count
        through that whole pass, independent of PARSING's own count."""
        cache_dir = Path(self.temp_dir.name) / "generated" / "cache"
        progress = []
        Scanner(self.root, cache_dir=cache_dir, progress_callback=progress.append).scan()
        fingerprint_events = [item for item in progress if item.stage == "FINGERPRINTING"]
        # A "starting" event (real source name, pre-increment count) and a
        # "done" event (post-increment count) per source -- 2 sources x 2
        # events each.
        self.assertEqual(4, len(fingerprint_events))
        self.assertEqual([(0, 2), (1, 2), (1, 2), (2, 2)], [(item.completed_sources, item.total_sources) for item in fingerprint_events])
        self.assertTrue(all(item.current_source for item in fingerprint_events))

    def test_source_fingerprint_isolated_matches_serial_and_reports_hash_state_to_merge(self) -> None:
        """`scan()`'s fingerprinting stage now dispatches `_source_fingerprint`
        calls to a bounded thread pool (real, measured win against the local
        install -- see docs/WORK_LOG.md's Phase 37 entry), each via a private
        `Scanner` so concurrent hashing never shares `self._hash_cache`.
        `_source_fingerprint_isolated` must still produce the exact same
        fingerprint a plain serial call would, and must hand back real hash
        state the coordinator can merge back into its own totals."""
        coordinator = Scanner(self.root)
        sources = coordinator.discover_sources()
        source = next(item for item in sources if item.mod_id == "fixture_mod")
        serial_scanner = Scanner(self.root)
        serial_fingerprint = serial_scanner._source_fingerprint(source)
        isolated_fingerprint, hash_cache, hash_bytes = coordinator._source_fingerprint_isolated(source)
        self.assertEqual(serial_fingerprint, isolated_fingerprint)
        self.assertEqual(serial_scanner._hash_cache, hash_cache)
        self.assertEqual(serial_scanner._hash_bytes, hash_bytes)

    def test_cancel_check_stops_the_scan_before_completion(self) -> None:
        progress = []
        with self.assertRaises(ScanCancelled):
            Scanner(self.root, cancel_check=lambda: True, progress_callback=progress.append).scan()
        stages = [item.stage for item in progress]
        self.assertNotIn("RESOLVING_REFERENCES", stages)
        self.assertNotIn("COMPLETE", stages)

    def test_cancel_check_during_parsing_stops_cleanly_without_hanging(self) -> None:
        # Forces the cache-miss/executor path (a real cache_dir, nothing
        # cached yet), then requests cancellation only after both sources
        # have been fingerprinted -- exercising ScanCancelled raised from
        # inside the ThreadPoolExecutor loop and its shutdown(wait=True,
        # cancel_futures=True) cleanup, not just the earlier, simpler loop.
        cache_dir = Path(self.temp_dir.name) / "generated" / "cache"
        calls = {"n": 0}

        def cancel_after_fingerprinting() -> bool:
            calls["n"] += 1
            return calls["n"] > 2

        with self.assertRaises(ScanCancelled):
            Scanner(self.root, cache_dir=cache_dir, cancel_check=cancel_after_fingerprinting).scan()

    def test_hash_verified_source_snapshots_reuse_unchanged_sources_and_preserve_output(self) -> None:
        cache_dir = Path(self.temp_dir.name) / "generated" / "cache"
        first = Scanner(self.root, cache_dir=cache_dir, max_workers=2).scan()
        second = Scanner(self.root, cache_dir=cache_dir, max_workers=2).scan()
        first_report = first.report("baseline_0.1")
        second_report = second.report("baseline_0.1")
        first_report.pop("scan_metrics", None)
        second_report.pop("scan_metrics", None)
        self.assertEqual(first_report, second_report)
        assert second.scan_metrics is not None
        self.assertEqual(2, second.scan_metrics.sources_reused)
        self.assertEqual(0, second.scan_metrics.sources_recomputed)
        self.assertTrue((cache_dir / "source_snapshots").is_dir())
        # cache_hit_rate is sources_reused / sources_scanned, precomputed
        # once so a caller doesn't have to divide the two counts itself.
        assert first.scan_metrics is not None
        self.assertEqual(0.0, first.scan_metrics.cache_hit_rate)
        self.assertEqual(1.0, second.scan_metrics.cache_hit_rate)

    def test_changed_source_recomputes_only_its_snapshot(self) -> None:
        cache_dir = Path(self.temp_dir.name) / "generated" / "cache"
        Scanner(self.root, cache_dir=cache_dir, max_workers=2).scan()
        weapons = self.root / "mods" / "fixture_mod" / "data" / "weapons" / "weapon_data.csv"
        weapons.write_text(weapons.read_text(encoding="utf-8") + "modded_extra,Extra,SMALL,BALLISTIC,1,500,ENERGY\n", encoding="utf-8")
        result = Scanner(self.root, cache_dir=cache_dir, max_workers=2).scan()
        assert result.scan_metrics is not None
        self.assertEqual(1, result.scan_metrics.sources_reused)
        self.assertEqual(1, result.scan_metrics.sources_recomputed)
        self.assertEqual(0.5, result.scan_metrics.cache_hit_rate)
        self.assertIn("modded_extra", {weapon.id for weapon in result.weapons})

    def test_parse_futures_harvest_in_completion_order_but_merge_stays_deterministic(self) -> None:
        """Regression test for the as_completed() harvesting switch: PARSING
        progress must reflect true completion order (a later-submitted but
        faster source is reported before an earlier-submitted, slower one
        finishes), while the merged scan output stays byte-identical to a
        plain single-worker, submission-order scan regardless of which
        source's future actually resolved first."""

        class ReorderedCompletionScanner(Scanner):
            # `core` is discovered/submitted first (see discover_sources());
            # deliberately making its own parse the slowest guarantees
            # `fixture_mod` -- submitted second -- completes first, so any
            # observed "fixture_mod before core" ordering below can only
            # come from real completion order, never submission order.
            def _scan_source_fragment(self, source):
                if source.mod_id == "core":
                    time.sleep(0.15)
                return super()._scan_source_fragment(source)

        baseline = Scanner(self.root).scan()  # single-worker: submission order
        progress = []
        reordered = ReorderedCompletionScanner(self.root, max_workers=2, progress_callback=progress.append).scan()

        parsing_sources = [item.current_source for item in progress if item.stage == "PARSING" and item.current_source]
        self.assertEqual(["Fixture Mod", "Starsector Core"], parsing_sources)

        # Despite finishing in reverse completion order, merged entity order
        # (and everything else) must be identical to a deterministic
        # submission-order scan -- Registry construction and report output
        # must never depend on which thread happened to finish first.
        baseline_report = baseline.report("baseline_0.1")
        reordered_report = reordered.report("baseline_0.1")
        baseline_report.pop("scan_metrics", None)
        reordered_report.pop("scan_metrics", None)
        self.assertEqual(baseline_report, reordered_report)

    def test_default_parser_worker_count_is_serial_but_parallel_is_explicit(self) -> None:
        default = Scanner(self.root).scan()
        parallel = Scanner(self.root, max_workers=8).scan()
        assert default.scan_metrics is not None and parallel.scan_metrics is not None
        self.assertEqual(1, default.scan_metrics.parallel_workers)
        self.assertEqual(2, parallel.scan_metrics.parallel_workers)

    def test_fighter_row_without_stable_id_is_skipped_not_collapsed_to_filename(self) -> None:
        wings = self.root / "data/hulls/wing_data.csv"
        wings.write_text(wings.read_text(encoding="utf-8") + "'',Incomplete,,\n", encoding="utf-8")
        result = Scanner(self.root).scan()
        self.assertNotIn("wing_data", {fighter.id for fighter in result.fighters})
        self.assertTrue(any("fighter row without a stable id skipped" in item for item in result.skipped_entities))

    def test_registry_indexes_entities_and_reports_unresolved_references(self) -> None:
        registry = Registry.from_scan(Scanner(self.root).scan())
        self.assertIn("fixture_frigate", registry.hulls.by_id)
        self.assertIn("fixture_gun", registry.weapons.by_id)
        self.assertFalse(registry.unresolved_references)
        self.assertEqual(("fixture_mod", "base_game"), (registry.missing_dependencies[0].mod_id, registry.missing_dependencies[0].dependency_id))

    def test_registry_canonicalizes_semantically_identical_hullmod_duplicates(self) -> None:
        from starsector_variant_generator.core.models import Hullmod, Variant
        core = Hullmod("shared", "Shared", "core", Path("core.csv"), hidden=False, raw={"id": "shared"})
        copied = Hullmod("shared", "  Shared  ", "copy_mod", Path("copy.csv"), hidden=False, raw={"id": " shared "})
        variant = Variant("v", "V", "mod", Path("v.variant"), hullmods=("shared",))
        registry = Registry.from_scan(ScanResult(hullmods=[core, copied], variants=[variant]))
        self.assertEqual("core", registry.hullmods.by_id["shared"].source_mod)
        self.assertNotIn("shared", registry.hullmods.duplicates)
        self.assertFalse(registry.unresolved_references)
        self.assertEqual("RESOLVED", registry.trace_reference("hullmod", "shared")["status"])
        self.assertEqual("DUPLICATE_IDENTICAL", registry.trace_reference("hullmod", "shared")["identity_status"])
        self.assertEqual("CANONICALIZED_DUPLICATE", registry.trace_reference("hullmod", "shared")["resolution_method"])

    def test_registry_keeps_semantically_divergent_hullmod_duplicates_ambiguous(self) -> None:
        from starsector_variant_generator.core.models import Hullmod, Variant
        core = Hullmod("shared", "Shared", "core", Path("core.csv"), hidden=False, raw={"id": "shared"})
        changed = Hullmod("shared", "Changed", "copy_mod", Path("copy.csv"), hidden=True, raw={"id": "shared", "hidden": "true"})
        variant = Variant("v", "V", "mod", Path("v.variant"), hullmods=("shared",))
        registry = Registry.from_scan(ScanResult(hullmods=[core, changed], variants=[variant]))
        self.assertNotIn("shared", registry.hullmods.by_id)
        trace = registry.trace_reference("hullmod", "shared")
        self.assertEqual("AMBIGUOUS_CONFLICT", trace["status"])
        self.assertEqual("DUPLICATE_DIVERGENT", trace["identity_status"])

    def test_variant_reference_uses_its_declared_dependency_scope(self) -> None:
        from starsector_variant_generator.core.models import Hullmod, ModInfo, Variant
        core = Hullmod("shared", "Shared", "core", Path("core.csv"), raw={"id": "shared"})
        unrelated = Hullmod("shared", "Shared", "unrelated", Path("other.csv"), raw={"id": "shared", "script": "custom.Override"})
        variant = Variant("consumer_variant", "Consumer", "consumer", Path("consumer.variant"), hullmods=("shared",))
        mod_info = lambda mod_id: ModInfo(mod_id, mod_id, None, Path(mod_id), True)
        registry = Registry.from_scan(ScanResult(
            hullmods=[core, unrelated], variants=[variant],
            mods=[mod_info("core"), mod_info("consumer"), mod_info("unrelated")],
        ))

        self.assertEqual([], registry.unresolved_references)
        trace = registry.trace_reference("hullmod", "shared", "consumer")
        self.assertEqual("RESOLVED_CONTEXTUAL", trace["status"])
        self.assertEqual("core", trace["resolved_source_mod"])
        self.assertEqual("CONTEXTUAL_CORE_FALLBACK", trace["resolution_method"])
        self.assertEqual("DUPLICATE_DIVERGENT", trace["identity_status"])
        self.assertEqual("unrelated", trace["shadowed_contextual_candidates"][0]["source_mod"])
        self.assertEqual("AMBIGUOUS_CONFLICT", registry.trace_reference("hullmod", "shared")["status"])

    def test_contextual_hullmod_duplicate_prefers_same_mod_then_dependency(self) -> None:
        from starsector_variant_generator.core.models import Hullmod, ModInfo
        hullmod = lambda source: Hullmod("shared", "Shared", source, Path(f"{source}.csv"), raw={"script": source})
        mod = lambda mod_id, dependencies=(): ModInfo(mod_id, mod_id, None, Path(mod_id), True, dependencies)
        same_mod_registry = Registry.from_scan(ScanResult(
            hullmods=[hullmod("core"), hullmod("consumer"), hullmod("library")],
            mods=[mod("core"), mod("consumer", ("library",)), mod("library")],
        ))
        self.assertEqual("SAME_MOD", same_mod_registry.trace_reference("hullmod", "shared", "consumer")["resolution_method"])
        dependency_registry = Registry.from_scan(ScanResult(
            hullmods=[hullmod("core"), hullmod("library")],
            mods=[mod("core"), mod("consumer", ("library",)), mod("library")],
        ))
        self.assertEqual("DEPENDENCY", dependency_registry.trace_reference("hullmod", "shared", "consumer")["resolution_method"])

    def test_contextual_hullmod_duplicate_refuses_multiple_relevant_dependencies(self) -> None:
        from starsector_variant_generator.core.models import Hullmod, ModInfo
        hullmod = lambda source: Hullmod("shared", "Shared", source, Path(f"{source}.csv"), raw={"script": source})
        mod = lambda mod_id, dependencies=(): ModInfo(mod_id, mod_id, None, Path(mod_id), True, dependencies)
        registry = Registry.from_scan(ScanResult(
            hullmods=[hullmod("core"), hullmod("library_a"), hullmod("library_b")],
            mods=[mod("core"), mod("consumer", ("library_a", "library_b")), mod("library_a"), mod("library_b")],
        ))
        self.assertEqual("AMBIGUOUS_CONFLICT", registry.trace_reference("hullmod", "shared", "consumer")["status"])

    def test_object_dependency_declarations_extract_only_explicit_ids(self) -> None:
        info_path = self.root / "mods/fixture_mod/mod_info.json"
        raw = json.loads(info_path.read_text(encoding="utf-8"))
        raw["dependencies"] = [{"id": "base_game", "version": "99"}, {"name": "unresolved-name"}]
        info_path.write_text(json.dumps(raw), encoding="utf-8")
        result = Scanner(self.root).scan()
        fixture_mod = next(mod for mod in result.mods if mod.mod_id == "fixture_mod")
        self.assertEqual(("base_game",), fixture_mod.dependencies)
        self.assertTrue(any("Dependency entry without explicit string id" in item for item in result.skipped_entities))

    def test_structured_mod_version_is_deterministic_json_provenance(self) -> None:
        info_path = self.root / "mods/fixture_mod/mod_info.json"
        raw = json.loads(info_path.read_text(encoding="utf-8"))
        raw["version"] = {"patch": 3, "major": 1}
        info_path.write_text(json.dumps(raw), encoding="utf-8")
        mod = next(item for item in Scanner(self.root).discover_sources() if item.mod_id == "fixture_mod")
        self.assertEqual('{"major":1,"patch":3}', mod.version)

    def test_registry_queries_preserve_ambiguity_and_source_evidence(self) -> None:
        registry = Registry.from_scan(Scanner(self.root).scan())
        self.assertEqual(["fixture_gun"], [weapon.id for weapon in registry.weapons_matching("medium", "ballistic")])
        self.assertEqual(["fixture_frigate_Standard"], [variant.id for variant in registry.variants_for_hull("fixture_frigate")])
        equipment = registry.faction_equipment("fixture")
        self.assertIn("fixture_gun", equipment["known_weapons"])

    def test_malformed_ship_does_not_abort_remaining_hull_rows(self) -> None:
        hull_dir = self.root / "data/hulls"
        (hull_dir / "ship_data.csv").write_text(
            "id,name,hullSize,ordnancePoints\nbad,Bad,FRIGATE,1\nfixture_frigate,Fixture Frigate,FRIGATE,45\n",
            encoding="utf-8",
        )
        (hull_dir / "bad.ship").write_text("{ invalid", encoding="utf-8")
        result = Scanner(self.root).scan()
        self.assertIn("fixture_frigate", {hull.id for hull in result.hulls})
        self.assertTrue(any("bad.ship" in error for error in result.errors))


class RegistryMatchingTests(unittest.TestCase):
    def test_fighters_matching_filters_by_role(self) -> None:
        interceptor = FighterWing("wing_a", "Wing A", "core", Path("f"), role="INTERCEPTOR")
        bomber = FighterWing("wing_b", "Wing B", "core", Path("f"), role="BOMBER")
        registry = Registry.from_scan(ScanResult(fighters=[interceptor, bomber]))
        self.assertEqual(["wing_a"], [wing.id for wing in registry.fighters_matching("interceptor")])
        self.assertEqual({"wing_a", "wing_b"}, {wing.id for wing in registry.fighters_matching()})

    def test_hullmods_matching_filters_by_hidden(self) -> None:
        hidden = Hullmod("mod_a", "Mod A", "core", Path("h"), hidden=True)
        visible = Hullmod("mod_b", "Mod B", "core", Path("h"), hidden=False)
        registry = Registry.from_scan(ScanResult(hullmods=[hidden, visible]))
        self.assertEqual(["mod_a"], [mod.id for mod in registry.hullmods_matching(hidden=True)])
        self.assertEqual({"mod_a", "mod_b"}, {mod.id for mod in registry.hullmods_matching()})


if __name__ == "__main__":
    unittest.main()
