from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.analysis.fleet_support import (
    FleetSupportConstraints,
    SupportFocus,
    fleet_support_request_from_payload,
    fleet_support_request_to_payload,
    parse_fleet_selections,
)
from starsector_variant_generator.analysis.gap_recommendation import (
    BuildWhyNotExplanation,
    CombinedWhyNotExplanation,
    RecommendationConstraints,
)
from starsector_variant_generator.analysis.scenario_advisor import (
    generic_scenario_profiles,
    scenario_advisor_request_from_payload,
    scenario_advisor_request_to_payload,
)
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.logging import configure_logging
from starsector_variant_generator.core.result_cache import AnalysisResultCache
from starsector_variant_generator.output.analysis_reports import (
    write_scan_analysis_reports,
)
from starsector_variant_generator.output.change_impact_report import (
    compact_change_impact,
    write_change_impact_report,
    write_compact_change_impact_report,
)
from starsector_variant_generator.output.diagnostic_summary import summarize_scan_issues
from starsector_variant_generator.profiles.catalog import (
    available_profiles,
    get_profile,
)
from starsector_variant_generator.profiles.modes import UserMode


def _why_not_report_lines(explanation: CombinedWhyNotExplanation | BuildWhyNotExplanation) -> tuple[str, ...]:
    """Real bug fixed here (docs/BUGS.md SVG-019): `api.run_why_not` returns
    `BuildWhyNotExplanation` (a flat `.reason`) when the caller passes
    `--build-archetype`, and only returns the legacy hull-level
    `CombinedWhyNotExplanation` (with `.native`/`.retrofit`/`.acquisition`,
    each carrying their own `.reason`) otherwise. The previous unconditional
    `explanation.native.reason` etc. raised `AttributeError` for every real
    `why-not --build-archetype` invocation.
    """
    if isinstance(explanation, BuildWhyNotExplanation):
        return (f"build: {explanation.reason}",)
    return (
        f"native: {explanation.native.reason}",
        f"retrofit: {explanation.retrofit.reason}",
        f"acquisition: {explanation.acquisition.reason}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="voidsmith")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="Read core and enabled-mod data without modifying sources")
    scan.add_argument("--config", type=Path)
    scan.add_argument("--starsector-path", type=Path)
    scan.add_argument("--output-dir", type=Path, default=Path("generated"))
    scan.add_argument("--all-installed-mods", action="store_true", help="Diagnostic scan of disabled as well as enabled installed mods; still read-only")
    scan.add_argument("--summary-only", action="store_true", help="Diagnostic mode: write scan/cache/impact summaries but skip optional per-entity analysis reports")
    subparsers.add_parser("list-profiles", help="List deterministic quality profiles")
    query = subparsers.add_parser("query", help="Query unambiguous normalized entities from a fresh read-only scan")
    query.add_argument("entity", choices=["weapons", "variants", "faction-equipment", "hulls", "fighters", "hullmods"])
    query.add_argument("--size")
    query.add_argument("--mount-type")
    query.add_argument("--hull-id")
    query.add_argument("--hull-size")
    query.add_argument("--civilian-only", action="store_true", help="query hulls: only include hulls whose documented \"hints\" column contains CIVILIAN")
    query.add_argument("--role", help="query fighters: filter by the wing's source-declared role")
    query.add_argument("--hidden-only", action="store_true", help="query hullmods: only include hullmods documented as hidden")
    query.add_argument("--faction-id")
    query.add_argument("--source-mod")
    query.add_argument("--starsector-path", type=Path, required=True)
    query.add_argument("--output-dir", type=Path, default=Path("generated"))
    query.add_argument("--overrides-dir", type=Path, default=Path("config/overrides"), help="Manual classification-override directory (see FORMAL_SPECIFICATION.md section 46); missing files are a no-op")
    validate = subparsers.add_parser("validate", help="Validate one existing variant using documented parsed evidence")
    validate.add_argument("variant_id")
    validate.add_argument("--starsector-path", type=Path, required=True)
    validate.add_argument("--output-dir", type=Path, default=Path("generated"))
    generate = subparsers.add_parser("generate", help="Generate capped, conservative candidate alternatives and legal-only quality reports")
    generate.add_argument("hull_id")
    generate.add_argument("--profile")
    generate.add_argument("--mode", choices=[mode.value for mode in UserMode], default=UserMode.BEGINNER.value)
    generate.add_argument("--faction-id")
    generate.add_argument("--faction-mode", choices=["STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"])
    generate.add_argument("--knowledge-pack", type=Path, help="Optional resolved Faction Doctrine & Retrofit Pack; advisory only, never affects legality")
    generate.add_argument("--advanced-config", type=Path, help="Strict JSON request containing implemented advanced restrictions")
    generate.add_argument("--flux-mode", choices=["SAFE", "BALANCED", "AGGRESSIVE"], help="Flux-sustainability target; defaults from --mode (beginner=SAFE, guided=BALANCED, advanced=AGGRESSIVE)")
    generate.add_argument("--max-candidates", type=int, default=5, help="Bounded number of deterministic alternatives (1-20)")
    generate.add_argument("--search-depth", type=int, default=1, help="Alternate ranks explored per mount (1 = original single-alternate bound; higher explores rank 2, 3, ... one mount at a time, never combinatorially)")
    generate.add_argument("--build-alternatives", type=int, default=2, help="Maximum bounded variants explored per inferred build path when no explicit --profile is selected")
    generate.add_argument("--overrides-dir", type=Path, default=Path("config/overrides"), help="Manual classification-override directory (see FORMAL_SPECIFICATION.md section 46); missing files are a no-op. Currently affects only PD_ESCORT's PD_FIRST weapon-priority sort.")
    generate.add_argument("--starsector-path", type=Path, required=True)
    generate.add_argument("--output-dir", type=Path, default=Path("generated"))
    export = subparsers.add_parser("export", help="Generate and export a LEGAL candidate compatibility mod")
    export.add_argument("hull_id")
    export.add_argument("--profile", default="LINE_BRAWLER")
    export.add_argument("--overrides-dir", type=Path, default=Path("config/overrides"), help="Manual classification-override directory (see FORMAL_SPECIFICATION.md section 46); missing files are a no-op. Currently affects only PD_ESCORT's PD_FIRST weapon-priority sort.")
    export.add_argument("--starsector-path", type=Path, required=True)
    export.add_argument("--output-dir", type=Path, default=Path("generated"))
    doctrine = subparsers.add_parser("doctrine", help="Report evidence from existing variants for one faction")
    doctrine.add_argument("faction_id")
    doctrine.add_argument("--source-mod")
    doctrine.add_argument("--starsector-path", type=Path, required=True)
    doctrine.add_argument("--output-dir", type=Path, default=Path("generated"))
    faction_capability = subparsers.add_parser("faction-capability", help="Report per-role capability evidence for one faction's known hulls")
    faction_capability.add_argument("faction_id")
    faction_capability.add_argument("--source-mod")
    faction_capability.add_argument("--starsector-path", type=Path, required=True)
    faction_capability.add_argument("--output-dir", type=Path, default=Path("generated"))
    recommend = subparsers.add_parser("recommend", help="Recommend native, retrofit, and acquisition solutions for a faction's detected capability gaps (see GAP_RECOMMENDATION_ENGINE.md)")
    recommend.add_argument("faction_id")
    recommend.add_argument("--source-mod")
    recommend.add_argument("--knowledge-pack", type=Path, help="Optional advisory pack used for approved acquisition affinity and confidence")
    recommend.add_argument("--no-foreign-hulls", action="store_true", help="Exclude FOREIGN-affinity acquisition hulls; COMMON and UNALIGNED remain eligible")
    recommend.add_argument("--exclude-experimental-builds", action="store_true", help="Do not return inferred Experimental build paths")
    recommend.add_argument("--campaign-stage", choices=["EARLY", "MID", "LATE", "ENDGAME"], help="Optional user-selected Knowledge Pack progression tier; advisory only")
    recommend.add_argument("--starsector-path", type=Path, required=True)
    recommend.add_argument("--output-dir", type=Path, default=Path("generated"))
    fleet_support = subparsers.add_parser("fleet-support", help="Advise individual additions for locked player-selected ships; never optimizes quantities or replaces selections")
    fleet_support.add_argument("hull_id", nargs="*", help="Locked selected hull id(s), optionally hull_id*count; repeated IDs also record multiple ships")
    fleet_support.add_argument("--faction-id", help="Optional faction access context")
    fleet_support.add_argument("--source-mod", help="Disambiguates --faction-id when multiple sources declare it")
    fleet_support.add_argument("--access-mode", choices=["STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"], default="FACTION_PLUS")
    fleet_support.add_argument("--no-foreign-hulls", action="store_true")
    fleet_support.add_argument("--include-hidden-hulls", action="store_true")
    fleet_support.add_argument("--focus", choices=[item.value for item in SupportFocus], default=SupportFocus.BALANCED.value)
    fleet_support.add_argument("--count", type=int, help="Maximum individually ranked additions; does not choose quantities")
    fleet_support.add_argument("--request-snapshot", type=Path, help="Load a user-owned Fleet Support Advisor request JSON")
    fleet_support.add_argument("--save-request-snapshot", type=Path, help="Write this user-owned request JSON")
    fleet_support.add_argument("--starsector-path", type=Path, required=True)
    fleet_support.add_argument("--output-dir", type=Path, default=Path("generated"))
    scenario_advisor = subparsers.add_parser("scenario-advisor", help="Assess locked ships against a declared scenario; never predicts battle outcomes")
    scenario_advisor.add_argument("hull_id", nargs="*", help="Locked selected hull id(s), optionally hull_id*count")
    scenario_advisor.add_argument("--scenario", choices=[item.scenario_id for item in generic_scenario_profiles()], help="Generic scenario template")
    scenario_advisor.add_argument("--request-snapshot", type=Path, help="Load a portable user-owned Scenario Advisor request JSON")
    scenario_advisor.add_argument("--save-request-snapshot", type=Path, help="Write a portable user-owned Scenario Advisor request JSON")
    scenario_advisor.add_argument("--faction-id"); scenario_advisor.add_argument("--source-mod")
    scenario_advisor.add_argument("--access-mode", choices=["STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"], default="FACTION_PLUS")
    scenario_advisor.add_argument("--focus", choices=[item.value for item in SupportFocus], default=SupportFocus.BALANCED.value)
    scenario_advisor.add_argument("--count", type=int); scenario_advisor.add_argument("--starsector-path", type=Path, required=True); scenario_advisor.add_argument("--output-dir", type=Path, default=Path("generated"))
    fleet_support_why_not = subparsers.add_parser("fleet-support-why-not", help="Explain why one hull was or was not selected as an addition for locked ships")
    fleet_support_why_not.add_argument("candidate_hull_id")
    fleet_support_why_not.add_argument("locked_hull_id", nargs="+", help="Locked selected hull id(s), optionally hull_id*count")
    fleet_support_why_not.add_argument("--faction-id")
    fleet_support_why_not.add_argument("--source-mod")
    fleet_support_why_not.add_argument("--access-mode", choices=["STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"], default="FACTION_PLUS")
    fleet_support_why_not.add_argument("--no-foreign-hulls", action="store_true")
    fleet_support_why_not.add_argument("--include-hidden-hulls", action="store_true")
    fleet_support_why_not.add_argument("--focus", choices=[item.value for item in SupportFocus], default=SupportFocus.BALANCED.value)
    fleet_support_why_not.add_argument("--count", type=int)
    fleet_support_why_not.add_argument("--starsector-path", type=Path, required=True)
    fleet_support_why_not.add_argument("--output-dir", type=Path, default=Path("generated"))
    why_not = subparsers.add_parser("why-not", help="Explain why a specific hull was or wasn't recommended for a capability gap role, across native/retrofit/acquisition (GAP_RECOMMENDATION_ENGINE.md section 13)")
    why_not.add_argument("faction_id")
    why_not.add_argument("role")
    why_not.add_argument("hull_id")
    why_not.add_argument("--build-archetype", help="Explain one specific Hull + BuildArchetype path (for example TANK or FINISHER)")
    why_not.add_argument("--source-mod")
    why_not.add_argument("--knowledge-pack", type=Path, help="Optional advisory pack; uses the same acquisition-affinity context as recommend")
    why_not.add_argument("--campaign-stage", choices=["EARLY", "MID", "LATE", "ENDGAME"], help="Must match recommend's selected stage; requires --build-archetype for an exact build-path explanation")
    why_not.add_argument("--starsector-path", type=Path, required=True)
    why_not.add_argument("--output-dir", type=Path, default=Path("generated"))
    analyze = subparsers.add_parser("analyze-variant", help="Analyze legality and quality of an existing variant")
    analyze.add_argument("variant_id")
    analyze.add_argument("--profile", default="LINE_BRAWLER")
    analyze.add_argument("--flux-mode", choices=["SAFE", "BALANCED", "AGGRESSIVE"], default="BALANCED")
    analyze.add_argument("--faction-id")
    analyze.add_argument("--source-mod", help="Disambiguates --faction-id when multiple mods declare the same faction id")
    analyze.add_argument("--overrides-dir", type=Path, default=Path("config/overrides"), help="Manual classification-override directory (see FORMAL_SPECIFICATION.md section 46); missing files are a no-op. Affects the hull's civilian_role_tags.")
    analyze.add_argument("--starsector-path", type=Path, required=True)
    analyze.add_argument("--output-dir", type=Path, default=Path("generated"))
    check_export = subparsers.add_parser("check-export", help="Check generated-export source hashes against a fresh read-only scan")
    check_export.add_argument("manifest", type=Path)
    check_export.add_argument("--starsector-path", type=Path, required=True)
    check_export.add_argument("--output-dir", type=Path, default=Path("generated"))
    refit = subparsers.add_parser("refit", help="Minimal-change refit for an existing variant (HULLMODS_CIVILIAN_AND_REFIT.md): FIX_LEGALITY (default) or a quality-improvement mode")
    refit.add_argument("variant_id")
    refit.add_argument("--mode", choices=["FIX_LEGALITY", "REDUCE_FLUX", "IMPROVE_ROLE_MATCH", "IMPROVE_LOGISTICS", "BALANCED_IMPROVEMENT"], default="FIX_LEGALITY", help="FIX_LEGALITY (default) needs no --profile. The 4 quality-improvement modes need --profile; IMPROVE_AI_FIT/IMPROVE_SURVEY/IMPROVE_SALVAGE are not implemented (no real per-ship evidence to search toward -- see generation/refit.py UNIMPLEMENTED_QUALITY_MODES).")
    refit.add_argument("--profile", help="Required for quality-improvement modes (--mode other than FIX_LEGALITY); the role intent role_match/BALANCED_IMPROVEMENT search toward")
    refit.add_argument("--flux-mode", choices=["SAFE", "BALANCED", "AGGRESSIVE"], default="BALANCED", help="Quality-improvement modes only")
    refit.add_argument("--lock-mount", action="append", default=[], help="Mount id the refit must never change (repeatable)")
    refit.add_argument("--lock-hullmod", action="append", default=[], help="Hullmod id the refit must never remove (repeatable)")
    refit.add_argument("--lock-wing", action="append", default=[], help="Fighter wing id the refit must never remove (repeatable)")
    refit.add_argument("--substitution-mode", choices=["cheapest", "exact", "starsector_style", "adaptive"], default="cheapest", help="FIX_LEGALITY only: how a mount-incompatible weapon is replaced: cheapest OP (default); EXACT (never substitutes -- removes and reports the weapon as missing instead, EQUIPMENT_ACCESS_AND_AUTOFIT.md); STARSECTOR_STYLE (closest available substitute that keeps the original's category/group intent, EQUIPMENT_ACCESS_AND_AUTOFIT.md); or ADAPTIVE (best real role/range/flux/damage/affinity match, EQUIPMENT_ACCESS_AND_AUTOFIT.md)")
    refit.add_argument("--faction-id", help="FIX_LEGALITY: requesting faction for --substitution-mode adaptive's affinity component. Quality-improvement modes: faction for faction_doctrine_match scoring.")
    refit.add_argument("--source-mod", help="Disambiguates --faction-id when multiple mods declare the same faction id (quality-improvement modes)")
    refit.add_argument("--starsector-path", type=Path, required=True)
    refit.add_argument("--output-dir", type=Path, default=Path("generated"))
    args = parser.parse_args()
    if args.command == "list-profiles":
        for profile in available_profiles():
            print(f"{profile.identifier}: {profile.display_name} - {profile.description}")
        return 0
    if args.command == "query":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            # Every branch feeds the same generic `{"entity": ..., "records": records}`
            # JSON dump below; `run_query_faction_equipment` genuinely returns a
            # dict (per-known-category id tuples) rather than a per-entity record
            # list like the other 5 branches, so this is a real, documented union
            # rather than a loosened/`Any` annotation.
            records: list[dict] | dict[str, tuple[str, ...]]
            if args.entity == "weapons":
                records = api.run_query_weapons(registry, args.size, args.mount_type, args.overrides_dir, args.faction_id)
            elif args.entity == "hulls":
                records = api.run_query_hulls(registry, args.hull_size, args.civilian_only, args.overrides_dir)
            elif args.entity == "fighters":
                records = api.run_query_fighters(registry, args.role, args.faction_id)
            elif args.entity == "hullmods":
                records = api.run_query_hullmods(registry, True if args.hidden_only else None, args.faction_id)
            elif args.entity == "variants":
                records = api.run_query_variants(registry, args.hull_id)
            else:
                records = api.run_query_faction_equipment(registry, args.faction_id, args.source_mod)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"query_{args.entity}.json"
        report_path.write_text(json.dumps({"entity": args.entity, "records": records}, indent=2, default=str), encoding="utf-8")
        print(f"Query report: {report_path}")
        return 0
    if args.command == "validate":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            assessment = api.run_validate(registry, args.variant_id)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"validation_{args.variant_id}.json"
        report_path.write_text(json.dumps(asdict(assessment), indent=2, default=str), encoding="utf-8")
        print(f"{assessment.result}: {report_path}")
        return 0 if assessment.result == "LEGAL" else 1
    if args.command == "generate":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        result_cache = AnalysisResultCache(config.output_dir / "cache" / "analysis_results.sqlite")
        try:
            knowledge_pack = api.resolve_optional_knowledge_pack(args.knowledge_pack, registry)
            outcome = api.run_generate(
                registry, config.heuristic_set, args.hull_id, args.mode,
                profile=args.profile, faction_id=args.faction_id, faction_mode=args.faction_mode,
                advanced_config=args.advanced_config, flux_mode=args.flux_mode,
                max_candidates=args.max_candidates, search_depth=args.search_depth, build_alternatives=args.build_alternatives,
                overrides_dir=args.overrides_dir, knowledge_pack=knowledge_pack, result_cache=result_cache,
            )
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"candidates_{args.hull_id}_{outcome.selected_profile}.json"
        advanced = outcome.advanced
        advanced_report = None if advanced is None else {
            "profile_id": advanced.profile_id,
            "faction_mode": advanced.faction_mode,
            "allowed_weapon_ids": sorted(advanced.allowed_weapon_ids) if advanced.allowed_weapon_ids is not None else None,
            "denied_weapon_ids": sorted(advanced.denied_weapon_ids),
            "locked_weapons_by_mount": advanced.locked_weapons_by_mount,
            "empty_mount_ids": sorted(advanced.empty_mount_ids),
            "scoring_weight_overrides": advanced.scoring_weight_overrides,
        }
        report_path.write_text(json.dumps({
            "mode_preset": asdict(outcome.defaults), "effective_profile_id": outcome.selected_profile,
            "effective_flux_mode": outcome.flux_mode, "advanced_request": advanced_report,
            "faction_id": args.faction_id, "faction_mode": outcome.faction_mode,
            "faction_preference_evidence": outcome.faction_preference_evidence,
            "cache_readiness": outcome.cache_readiness,
            "bounded_search": {
                "maximum_requested": args.max_candidates, "search_depth": args.search_depth, "build_alternatives": args.build_alternatives,
                "generated": len(outcome.assessed_candidates),
                "strategy": "baseline plus up to search_depth next-ranked documented weapons per mount, one mount changed at a time",
            },
            "candidates": outcome.assessed_candidates,
        }, indent=2, default=str), encoding="utf-8")
        legal_count = sum(item["legality"] == "LEGAL" for item in outcome.assessed_candidates)
        print(f"{legal_count} LEGAL candidate(s): {report_path}")
        return 0 if legal_count else 1
    if args.command == "export":
        try:
            get_profile(args.profile)
        except ValueError as exc:
            parser.error(str(exc))
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            path = api.run_export(registry, config.heuristic_set, config.output_dir, args.hull_id, args.profile, args.overrides_dir)
        except ValueError as exc:
            print(str(exc))
            return 1
        print(f"Exported compatibility variant: {path}")
        return 0
    if args.command == "doctrine":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            evidence = api.run_doctrine(registry, args.faction_id, args.source_mod)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"doctrine_{args.faction_id}.json"
        report_path.write_text(json.dumps(asdict(evidence), indent=2, default=str), encoding="utf-8")
        print(f"Doctrine evidence: {report_path}")
        return 0
    if args.command == "faction-capability":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            capability_profile = api.run_faction_capability(registry, args.faction_id, args.source_mod, config.heuristic_set)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"faction_capability_{args.faction_id}.json"
        report_path.write_text(json.dumps(asdict(capability_profile), indent=2, default=str), encoding="utf-8")
        print(f"Faction capability profile: {report_path}")
        return 0
    if args.command == "recommend":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        result_cache = AnalysisResultCache(config.output_dir / "cache" / "analysis_results.sqlite")
        try:
            knowledge_pack = api.resolve_optional_knowledge_pack(args.knowledge_pack, registry)
            constraints = RecommendationConstraints(not args.no_foreign_hulls, not args.exclude_experimental_builds, args.campaign_stage)
            result = api.run_gap_recommendations(registry, args.faction_id, args.source_mod, config.heuristic_set, knowledge_pack, constraints, result_cache)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"recommend_{args.faction_id}.json"
        report_path.write_text(json.dumps(asdict(result), indent=2, default=str), encoding="utf-8")
        print(f"{len(result.gaps)} capability gap(s), {len(result.unaddressed_gaps)} without a native solution, {len(result.fully_unaddressed_gaps)} unaddressed by any leg: {report_path}")
        return 0
    if args.command == "fleet-support":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            if not args.request_snapshot and not args.hull_id:
                parser.error("fleet-support requires locked hull IDs or --request-snapshot")
            selections, support_constraints = fleet_support_request_from_payload(json.loads(args.request_snapshot.read_text(encoding="utf-8"))) if args.request_snapshot else (parse_fleet_selections(tuple(args.hull_id)), FleetSupportConstraints(args.access_mode, not args.no_foreign_hulls, args.include_hidden_hulls, SupportFocus(args.focus), args.count))
            if args.save_request_snapshot:
                args.save_request_snapshot.parent.mkdir(parents=True, exist_ok=True)
                args.save_request_snapshot.write_text(json.dumps(fleet_support_request_to_payload(selections, support_constraints), indent=2), encoding="utf-8")
            fleet_result = api.run_fleet_support_advisor(registry, selections, args.faction_id, args.source_mod, config.heuristic_set, support_constraints)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "fleet_support.json"
        report_path.write_text(json.dumps(asdict(fleet_result), indent=2, default=str), encoding="utf-8")
        print(f"{len(fleet_result.profile.support_needs)} advisory support need(s), {len(fleet_result.recommendations)} individually ranked addition(s): {report_path}")
        return 0
    if args.command == "fleet-support-why-not":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            selections = parse_fleet_selections(tuple(args.locked_hull_id))
            support_constraints = FleetSupportConstraints(args.access_mode, not args.no_foreign_hulls, args.include_hidden_hulls, SupportFocus(args.focus), args.count)
            fleet_why_not_result = api.run_fleet_support_why_not(registry, selections, args.candidate_hull_id, args.faction_id, args.source_mod, config.heuristic_set, support_constraints)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"fleet_support_why_not_{args.candidate_hull_id}.json"
        report_path.write_text(json.dumps(asdict(fleet_why_not_result), indent=2, default=str), encoding="utf-8")
        print(f"{fleet_why_not_result.reason}: {report_path}")
        return 0
    if args.command == "scenario-advisor":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        registry = api.build_registry(config, configure_logging(config.log_dir))
        try:
            if args.request_snapshot:
                selections, scenario, support_constraints = scenario_advisor_request_from_payload(json.loads(args.request_snapshot.read_text(encoding="utf-8")))
            else:
                if not args.hull_id or not args.scenario:
                    parser.error("scenario-advisor requires locked hull IDs and --scenario, or --request-snapshot")
                selections = parse_fleet_selections(tuple(args.hull_id)); scenario = next(item for item in generic_scenario_profiles() if item.scenario_id == args.scenario)
                support_constraints = FleetSupportConstraints(args.access_mode, True, False, SupportFocus(args.focus), args.count)
            if args.save_request_snapshot:
                args.save_request_snapshot.parent.mkdir(parents=True, exist_ok=True)
                args.save_request_snapshot.write_text(json.dumps(scenario_advisor_request_to_payload(selections, scenario, support_constraints), indent=2), encoding="utf-8")
            scenario_result = api.run_scenario_fleet_advisor(registry, selections, scenario, args.faction_id, args.source_mod, config.heuristic_set, support_constraints)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"; report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "scenario_advisor.json"; report_path.write_text(json.dumps(asdict(scenario_result), indent=2, default=str), encoding="utf-8")
        print(f"{scenario_result.readiness} mechanical alignment, {len(scenario_result.recommendations)} individual addition(s): {report_path}")
        return 0
    if args.command == "why-not":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            if args.campaign_stage and not args.build_archetype:
                parser.error("why-not --campaign-stage requires --build-archetype so the explanation can reproduce the exact Hull + BuildArchetype ranking")
            knowledge_pack = api.resolve_optional_knowledge_pack(args.knowledge_pack, registry)
            explanation = api.run_why_not(registry, args.faction_id, args.role, args.hull_id, args.source_mod, config.heuristic_set, knowledge_pack, args.build_archetype, args.campaign_stage)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"why_not_{args.faction_id}_{args.role}_{args.hull_id}.json"
        report_path.write_text(json.dumps(asdict(explanation), indent=2, default=str), encoding="utf-8")
        for line in _why_not_report_lines(explanation):
            print(line)
        print(f"report: {report_path}")
        return 0
    if args.command == "analyze-variant":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        try:
            analysis = api.run_analyze_variant(registry, args.variant_id, args.profile, args.flux_mode, config.heuristic_set, args.faction_id, args.source_mod, args.overrides_dir)
        except ValueError as exc:
            parser.error(str(exc))
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"analysis_{args.variant_id}.json"
        report_path.write_text(json.dumps(asdict(analysis), indent=2, default=str), encoding="utf-8")
        print(f"Variant analysis: {report_path}")
        return 0
    if args.command == "check-export":
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        staleness = api.run_check_export(registry, args.manifest)
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "export_staleness.json"
        report_path.write_text(json.dumps(asdict(staleness), indent=2), encoding="utf-8")
        print(f"{'STALE' if staleness.stale else 'CURRENT'}: {report_path}")
        return 1 if staleness.stale else 0
    if args.command == "refit":
        if args.mode != "FIX_LEGALITY" and not args.profile:
            parser.error("--profile is required for quality-improvement --mode values")
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
        logger = configure_logging(config.log_dir)
        registry = api.build_registry(config, logger)
        report_dir = config.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"refit_{args.variant_id}.json"
        if args.mode == "FIX_LEGALITY":
            try:
                fix_result = api.run_fix_legality(
                    registry, args.variant_id, config.heuristic_set,
                    frozenset(args.lock_mount), frozenset(args.lock_hullmod), frozenset(args.lock_wing),
                    args.substitution_mode, args.faction_id,
                )
            except ValueError as exc:
                parser.error(str(exc))
            report_path.write_text(json.dumps(asdict(fix_result), indent=2, default=str), encoding="utf-8")
            status = "already LEGAL" if not fix_result.changes and fix_result.final_legality.result == "LEGAL" else f"{len(fix_result.changes)} change(s), now {fix_result.final_legality.result}"
            print(f"{status}: {report_path}")
            return 0 if fix_result.final_legality.result == "LEGAL" else 1
        try:
            quality_result = api.run_improve_quality(
                registry, args.variant_id, args.mode, args.profile, config.heuristic_set,
                frozenset(args.lock_mount), frozenset(args.lock_hullmod), frozenset(args.lock_wing),
                args.flux_mode, args.faction_id, args.source_mod,
            )
        except ValueError as exc:
            parser.error(str(exc))
        report_path.write_text(json.dumps(asdict(quality_result), indent=2, default=str), encoding="utf-8")
        if quality_result.note:
            status = quality_result.note
        else:
            status = f"{len(quality_result.changes)} change(s), {quality_result.metric_name} {quality_result.before_score:.1f} -> {quality_result.after_score:.1f}"
        print(f"{status}: {report_path}")
        return 0
    if args.command != "scan":
        return 2
    if args.config:
        config = AppConfig.from_toml(args.config)
    elif args.starsector_path:
        config = AppConfig(args.starsector_path, args.output_dir, args.output_dir / "logs")
    else:
        parser.error("scan requires --config or --starsector-path")
    logger = configure_logging(config.log_dir)
    scan_outcome = api.run_scan(
        config, logger, include_disabled_mods=args.all_installed_mods,
        include_entities=not args.summary_only,
    )
    report_dir = config.output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    if args.summary_only:
        scan_outcome.report["analysis_reports"] = {"status": "SKIPPED", "reason": "summary-only diagnostic scan"}
        scan_outcome.report["change_impact"] = compact_change_impact(scan_outcome.change_impact)
        scan_outcome.report["registry"] = {
            "unresolved_reference_count": len(scan_outcome.registry.unresolved_references),
            "missing_dependency_count": len(scan_outcome.registry.missing_dependencies),
        }
        scan_outcome.report["diagnostics"] = summarize_scan_issues(scan_outcome.result)
    else:
        scan_outcome.report["analysis_reports"] = write_scan_analysis_reports(
            scan_outcome.result, scan_outcome.registry, report_dir, config.heuristic_set,
            reuse_if_unchanged=scan_outcome.cache_result.status == "UNCHANGED",
        )
    impact_path = config.output_dir / "reports" / "change_impact.json"
    if args.summary_only:
        write_compact_change_impact_report(scan_outcome.change_impact, impact_path)
    else:
        write_change_impact_report(scan_outcome.change_impact, impact_path)
    scan_outcome.report["change_impact_report"] = str(impact_path)
    report_path = report_dir / "scan_summary.json"
    report_path.write_text(json.dumps(scan_outcome.report, indent=2, default=str), encoding="utf-8")
    print(f"Read-only scan complete: {report_path}")
    return 0 if not scan_outcome.result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
