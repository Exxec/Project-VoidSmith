"""Importable service layer wrapping each CLI command's orchestration.

`cli/main.py` used to hold this orchestration (mode/advanced-request
resolution, faction restriction assembly, candidate ranking, report-dict
assembly) inline inside `argparse` handling, which meant any other
front end -- notably the future GUI described in `GUI.md` -- would have
had to either shell out to the `svg` CLI or re-derive this logic itself.
GUI.md's Readiness Gate (section 50) says the production GUI "should bind
to those services directly" once backend contracts are stable; this module
is that binding surface.

Moving the logic here changes no CLI-observable behavior: `cli/main.py`
now only parses arguments, calls these functions, and serializes/prints
the result exactly as before (see the golden regression test and the full
suite, both unchanged). Every function is read-only against game/mod
sources; only `run_scan`'s cache manifest and `run_export`'s writer touch
disk, both already-existing side effects scoped to `--output-dir`.

None of these functions print or write report *files* -- callers own
presentation and persistence, matching how a GUI would want an in-memory
result object rather than a file to re-read. They raise `ValueError` on
the same user-facing conditions the CLI already handled via
`parser.error(...)`; callers decide how to present that (CLI: exit code 2
and usage text; GUI: an error dialog).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from logging import Logger
from pathlib import Path
from time import perf_counter
from typing import Callable

from starsector_variant_generator.analysis.classification import classify_civilian_role, classify_fighter, classify_hullmod, classify_weapon
from starsector_variant_generator.analysis.combat_entity import classify_fighter_wing_entity, recommendation_eligibility
from starsector_variant_generator.analysis.combat_doctrine import infer_combat_doctrine
from starsector_variant_generator.analysis.campaign_save_discovery import CampaignSaveDiscovery, discover_campaign_directory
from starsector_variant_generator.analysis.change_impact import ChangeImpactReport, analyze_change_impact
from starsector_variant_generator.analysis.doctrine import DoctrineEvidence, analyze_faction_doctrine
from starsector_variant_generator.analysis.equipment_affinity import classify_equipment_affinity, classify_equipment_availability
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack, approved_equipment_ids, load_knowledge_pack, resolve_knowledge_pack
from starsector_variant_generator.analysis.faction_capability import FactionCapabilityProfile, analyze_faction_capability
from starsector_variant_generator.analysis.fleet_advisory_boundaries import FleetAdvisoryBoundaries, fleet_advisory_boundaries
from starsector_variant_generator.analysis.fleet_support import FleetSelection, FleetSupportConstraints, FleetSupportRecommendation, FleetSupportResult, FleetSupportWhyNotExplanation, explain_fleet_support_candidate, recommend_fleet_support, support_fit_profile
from starsector_variant_generator.analysis.scenario_advisor import ScenarioFleetAssessment, ScenarioObjectiveProfile, assess_scenario_fleet
from starsector_variant_generator.analysis.gap_recommendation import (
    BuildWhyNotExplanation, CombinedWhyNotExplanation, GapRecommendationResult, RecommendationConstraints,
    explain_build_candidate, explain_candidate, gap_recommendation_fingerprint, gap_recommendation_result_from_payload,
    gap_recommendation_result_to_payload, recommend_gap_solutions,
)
from starsector_variant_generator.analysis.variant import VariantAnalysis, analyze_variant
from starsector_variant_generator.analysis.video_review import load_video_review_transcript, resolve_control_suitability_evidence
from starsector_variant_generator.core.cache import CacheComparison, load_manifest, update_manifest
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Faction, ScanProgress, ScanResult, Variant, Weapon
from starsector_variant_generator.core.overrides import apply_role_tag_override, load_overrides
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.result_cache import AnalysisResultCache, CacheReadiness, resolve_cache_status
from starsector_variant_generator.core.mount_compatibility import MOUNT_TYPE_COMPATIBILITY
from starsector_variant_generator.core.scanner import Scanner
from starsector_variant_generator.generation.candidate import (
    BuildCandidateResult, CandidateResult, build_archetype_candidates_fingerprint, build_archetype_candidates_result_from_payload,
    build_archetype_candidates_result_to_payload, candidate_alternatives_fingerprint, candidate_alternatives_result_from_payload,
    candidate_alternatives_result_to_payload, generate_build_archetype_candidates, generate_candidate_alternatives, generate_conservative_candidate,
)
from starsector_variant_generator.generation.refit import QualityRefitResult, RefitResult, fix_legality, improve_quality
from starsector_variant_generator.output.staleness import StalenessReport, check_generation_manifest
from starsector_variant_generator.output.writer import write_compatibility_mod
from starsector_variant_generator.output.retrofit_library import copy_existing_retrofit, inspect_editable_retrofit, load_editable_retrofit, populate_variations_if_missing, publish_editable_retrofit, restore_editable_retrofit_history, save_editable_variant, variants_for_hull
from starsector_variant_generator.profiles.advanced import AdvancedGenerationRequest, load_advanced_request
from starsector_variant_generator.profiles.catalog import get_profile
from starsector_variant_generator.profiles.modes import ModeDefaults, UserMode, resolve_mode
from starsector_variant_generator.scoring.candidate_score import score_candidate
from starsector_variant_generator.validation.legality import LegalityAssessment, validate_variant


def build_registry(config: AppConfig, logger: Logger) -> Registry:
    """The read-only scan + index step every other command in this module needs."""
    return Registry.from_scan(Scanner(config.starsector_path, logger, cache_dir=config.output_dir / "cache", extra_mod_paths=config.extra_mod_paths).scan())


@dataclass(frozen=True)
class ScanOutcome:
    result: ScanResult
    registry: Registry
    cache_result: CacheComparison
    change_impact: ChangeImpactReport
    report: dict


def run_scan(
    config: AppConfig,
    logger: Logger,
    include_disabled_mods: bool = False,
    include_entities: bool = True,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> ScanOutcome:
    """Scan enabled mods by default; diagnostics may opt into all installed mods.

    `cancel_check`, when given, lets `Scanner.scan()` raise `ScanCancelled`
    cooperatively between sources (see its docstring) instead of running a
    scan to completion the caller no longer wants.
    """
    result = Scanner(
        config.starsector_path, logger, include_disabled_mods=include_disabled_mods,
        progress_callback=progress_callback, cache_dir=config.output_dir / "cache",
        extra_mod_paths=config.extra_mod_paths, cancel_check=cancel_check,
    ).scan()
    # Scanner.scan() itself now reports progress throughout (see
    # core/scanner.py's FINGERPRINTING/PARSING fix), but everything below
    # this point used to report nothing at all, no matter how long it took
    # -- measured on the real 148-mod install, analyze_change_impact() alone
    # (diffing the whole manifest against the prior scan, ~13k+ entities)
    # took a real, silent 4.3s, on top of whatever result.report() and
    # registry-building add. To a user watching the GUI's progress dialog,
    # that read as the scan being stuck again even though Scanner's own
    # part had genuinely finished. These labels aren't granular counters
    # (none of the three steps below have anything to count against), but
    # each at least proves forward motion instead of a frozen dialog.
    entities_found = sum(len(getattr(result, field)) for field in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions"))

    def _emit_post_scan_progress(stage: str) -> None:
        if progress_callback is not None:
            progress_callback(ScanProgress(stage=stage, entities_found=entities_found, warnings=len(result.warnings), errors=len(result.errors)))

    # Timestamped, matching Scanner.scan()'s own per-source logging: if a
    # scan ever appears to hang again during this post-scan phase, the log's
    # last unmatched "starting" line (no following "took Ns" line) names
    # exactly which of these three steps was running.
    _emit_post_scan_progress("BUILDING_REGISTRY")
    _phase_started = perf_counter()
    logger.info("Building registry from %d hulls / %d weapons / %d hullmods / %d variants / %d factions",
                len(result.hulls), len(result.weapons), len(result.hullmods), len(result.variants), len(result.factions))
    registry = Registry.from_scan(result)
    logger.info("Registry built in %.2fs", perf_counter() - _phase_started)
    manifest_path = config.output_dir / "cache" / "scan_manifest.json"
    _emit_post_scan_progress("ANALYZING_CHANGES")
    _phase_started = perf_counter()
    logger.info("Analyzing change impact against prior manifest %s", manifest_path)
    change_impact = analyze_change_impact(load_manifest(manifest_path), result)
    cache_result = update_manifest(manifest_path, result)
    logger.info("Change impact analyzed in %.2fs", perf_counter() - _phase_started)
    _emit_post_scan_progress("WRITING_REPORT")
    _phase_started = perf_counter()
    logger.info("Building scan report (include_entities=%s)", include_entities)
    report = result.report(config.heuristic_set, include_entities=include_entities)
    logger.info("Scan report built in %.2fs", perf_counter() - _phase_started)
    report["cache"] = asdict(cache_result)
    report["change_impact"] = asdict(change_impact)
    report["registry"] = {
        "unresolved_references": [asdict(item) for item in registry.unresolved_references],
        "missing_dependencies": [asdict(item) for item in registry.missing_dependencies],
        "canonical_duplicate_resolutions": [asdict(item) for item in registry.canonical_duplicate_resolutions],
        "duplicate_identities": [asdict(item) for item in registry.duplicate_identities],
        "contextual_reference_resolutions": [asdict(item) for item in registry.contextual_reference_resolutions],
    }
    return ScanOutcome(result, registry, cache_result, change_impact, report)


@dataclass(frozen=True)
class IncrementalScanOutcome:
    result: ScanResult
    registry: Registry
    added_mod_ids: tuple[str, ...]
    skipped_mod_roots: tuple[Path, ...]


def run_incremental_mod_scan(
    config: AppConfig,
    existing_result: ScanResult,
    mod_roots: tuple[Path, ...],
    logger: Logger | None = None,
) -> IncrementalScanOutcome:
    """Parse each of `mod_roots` in isolation and merge them into a copy of
    an already-scanned `existing_result`, without re-scanning anything
    else -- lets a user incorporate a freshly drag-and-dropped mod
    immediately, for fast iterative testing, without waiting for a full
    rescan of the whole installation. `existing_result` itself is never
    mutated; a new `ScanResult` is returned.

    Deliberately NOT a substitute for a real full scan, and not claimed to
    be one:
    - Nothing outside `mod_roots` is re-verified against its own current
      disk state. A source that changed on disk since `existing_result`
      was produced won't be picked up here -- only a real `run_scan` does.
    - Skin resolution runs the newly-added mods' own pending skins against
      the full merged hull set (so a new mod's skin can resolve against an
      already-scanned base hull, and vice versa), but any skin left
      unresolved from the *original* full scan is not retried here: that
      working state is scan-instance-local and already discarded by the
      time this function runs.
    Duplicate-ID detection, by contrast, IS full-fidelity: `Registry.from_scan`
    rebuilds the index from the complete merged entity list, so a new mod
    colliding with an already-scanned entity is still caught correctly.
    """
    scanner = Scanner(config.starsector_path, logger, cache_dir=config.output_dir / "cache")
    merged = ScanResult(
        mods=list(existing_result.mods), hulls=list(existing_result.hulls), weapons=list(existing_result.weapons),
        fighters=list(existing_result.fighters), hullmods=list(existing_result.hullmods), variants=list(existing_result.variants),
        factions=list(existing_result.factions), warnings=list(existing_result.warnings), errors=list(existing_result.errors),
        skipped_entities=list(existing_result.skipped_entities), parse_warnings=list(existing_result.parse_warnings), scan_metrics=existing_result.scan_metrics,
    )
    added_mod_ids: list[str] = []
    skipped_mod_roots: list[Path] = []
    pending_skins: list[tuple[str, str | None, Path, dict]] = []
    for mod_root in mod_roots:
        scanned = scanner.scan_single_mod(mod_root)
        if scanned is None:
            skipped_mod_roots.append(mod_root)
            continue
        info, fragment = scanned
        merged.mods.append(info)
        Scanner._merge_fragment(merged, fragment)
        pending_skins.extend(fragment.pending_skins)
        added_mod_ids.append(info.mod_id)
    scanner._pending_skins = pending_skins
    scanner._resolve_skins(merged)
    registry = Registry.from_scan(merged)
    return IncrementalScanOutcome(merged, registry, tuple(added_mod_ids), tuple(skipped_mod_roots))


def run_query_weapons(registry: Registry, size: str | None, mount_type: str | None, overrides_dir: Path, requesting_faction_id: str | None = None) -> list[dict]:
    weapon_overrides = load_overrides(overrides_dir, "weapons")
    records = []
    for weapon in registry.weapons_matching(size, mount_type):
        record = asdict(weapon)
        classification = classify_weapon(weapon)
        override = weapon_overrides.get(weapon.id)
        record["role_tags"] = list(apply_role_tag_override(classification.role_tags, override))
        record["range_band"] = classification.range_band
        record["role_tags_overridden"] = override is not None
        affinity = classify_equipment_affinity(weapon.id, "weapons", registry, requesting_faction_id)
        record["faction_affinity"] = affinity.affinity
        record["owning_faction_ids"] = list(affinity.owning_faction_ids)
        record["availability_class"] = classify_equipment_availability(weapon)
        records.append(record)
    return records


def run_slot_eligible_weapons(
    registry: Registry,
    hull_id: str,
    mount_id: str,
    *,
    include_hidden: bool = False,
    faction_id: str | None = None,
    faction_mode: str = "UNRESTRICTED",
) -> list[Weapon]:
    """Return backend-authoritative mount-compatible weapons for GUI selectors.

    This is intentionally mount compatibility only; full variant OP and other
    legality are evaluated by `run_validate` after a user changes a fit.
    """
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None:
        raise ValueError(f"Hull not found or ambiguous: {hull_id}")
    mount = next((item for item in hull.weapon_mounts if str(item.get("id")) == mount_id), None)
    if mount is None:
        raise ValueError(f"Mount {mount_id!r} is not defined by hull {hull_id}")
    if mount_id in hull.built_in_weapons:
        return []
    order = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}
    mount_size = order.get(str(mount.get("size", "")).upper())
    allowed_types = MOUNT_TYPE_COMPATIBILITY.get(str(mount.get("type", "")).upper(), frozenset())
    if faction_mode not in {"STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"}:
        raise ValueError(f"Unknown faction mode: {faction_mode}")
    if faction_mode == "STRICT_FACTION" and faction_id is None:
        raise ValueError("STRICT_FACTION slot filtering requires a resolved faction")
    return sorted((weapon for weapon in registry.weapons.by_id.values()
                   if mount_size is not None and order.get((weapon.size or "").upper()) is not None
                   and order[(weapon.size or "").upper()] <= mount_size
                   and weapon.mount_type is not None and weapon.mount_type.upper() in allowed_types
                   and (include_hidden or classify_equipment_availability(weapon) not in {"SECRET", "DEV_ONLY", "UNOBTAINABLE"})
                   and (faction_mode != "STRICT_FACTION" or classify_equipment_affinity(weapon.id, "weapons", registry, faction_id).affinity in {"NATIVE", "APPROVED"})),
                  key=lambda weapon: (weapon.name.casefold(), weapon.source_mod, weapon.id))


def run_query_hulls(registry: Registry, hull_size: str | None, civilian_only: bool, overrides_dir: Path | None = None) -> list[dict]:
    hull_overrides = load_overrides(overrides_dir, "hulls") if overrides_dir else {}
    records = []
    for hull in registry.hulls_matching(hull_size):
        civilian = classify_civilian_role(hull)
        override = hull_overrides.get(hull.id)
        role_tags = apply_role_tag_override(civilian.role_tags, override)
        is_civilian = "CIVILIAN" in role_tags
        if civilian_only and not is_civilian:
            continue
        record = asdict(hull)
        record["civilian_role_tags"] = list(role_tags)
        record["is_civilian"] = is_civilian
        record["civilian_role_tags_overridden"] = override is not None
        record["recommendation_eligibility"] = asdict(recommendation_eligibility(hull))
        record["combat_doctrine"] = asdict(infer_combat_doctrine(hull, registry))
        records.append(record)
    return records


def run_query_fighters(registry: Registry, role: str | None, requesting_faction_id: str | None = None) -> list[dict]:
    records = []
    for fighter in registry.fighters_matching(role):
        record = asdict(fighter)
        record["role_tags"] = list(classify_fighter(fighter).role_tags)
        affinity = classify_equipment_affinity(fighter.id, "fighters", registry, requesting_faction_id)
        record["faction_affinity"] = affinity.affinity
        record["owning_faction_ids"] = list(affinity.owning_faction_ids)
        record["availability_class"] = classify_equipment_availability(fighter)
        record["combat_entity_profile"] = asdict(classify_fighter_wing_entity(fighter))
        records.append(record)
    return records


def run_query_hullmods(registry: Registry, hidden: bool | None, requesting_faction_id: str | None = None) -> list[dict]:
    records = []
    for hullmod in registry.hullmods_matching(hidden):
        record = asdict(hullmod)
        record["property_tags"] = list(classify_hullmod(hullmod).property_tags)
        affinity = classify_equipment_affinity(hullmod.id, "hullmods", registry, requesting_faction_id)
        record["faction_affinity"] = affinity.affinity
        record["owning_faction_ids"] = list(affinity.owning_faction_ids)
        record["availability_class"] = classify_equipment_availability(hullmod)
        records.append(record)
    return records


def run_query_variants(registry: Registry, hull_id: str | None) -> list[dict]:
    if not hull_id:
        raise ValueError("query variants requires --hull-id")
    return [asdict(variant) for variant in registry.variants_for_hull(hull_id)]


def run_query_faction_equipment(registry: Registry, faction_id: str | None, source_mod: str | None) -> list:
    if not faction_id:
        raise ValueError("query faction-equipment requires --faction-id")
    return registry.faction_equipment(faction_id, source_mod)


def run_validate(registry: Registry, variant_id: str) -> LegalityAssessment:
    variant = registry.variants.by_id.get(variant_id)
    if variant is None:
        raise ValueError(f"Variant not found or ambiguous: {variant_id}")
    return validate_variant(variant, registry)


def run_validate_fit(registry: Registry, variant: Variant) -> LegalityAssessment:
    """Validate an in-memory GUI fit through the same backend legality engine."""
    return validate_variant(variant, registry)


def run_fit_summary(registry: Registry, variant: Variant) -> dict[str, object]:
    """Return GUI-presentable fit facts from backend data, never UI rules."""
    assessment = run_validate_fit(registry, variant)
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    weapon_op = sum((registry.weapons.by_id[weapon_id].ordnance_points or 0)
                    for weapon_id in variant.weapons_by_mount.values()
                    if weapon_id in registry.weapons.by_id)
    available = hull.ordnance_points if hull else None
    return {
        "legality": assessment.result.value,
        "failures": [item.message for item in assessment.failures],
        "uncertainties": [item.message for item in assessment.uncertainties],
        "weapon_op_used": weapon_op,
        "hull_ordnance_points": available,
        "weapon_op_remaining": available - weapon_op if available is not None else None,
    }


def resolve_faction(registry: Registry, faction_id: str, source_mod: str | None) -> Faction:
    faction = registry.resolve_faction(faction_id, source_mod or None)
    if faction is None:
        raise ValueError(f"Faction not found or ambiguous: {faction_id}; provide --source-mod for overrides")
    return faction


@dataclass(frozen=True)
class GenerateOutcome:
    defaults: ModeDefaults
    advanced: AdvancedGenerationRequest | None
    selected_profile: str
    flux_mode: str
    faction_mode: str
    faction: Faction | None
    faction_preference_evidence: bool
    candidates: list[CandidateResult]
    assessed_candidates: list[dict]
    build_candidates: tuple[BuildCandidateResult, ...] = ()
    # Real, inspectable per-call cache decision (Phase 33, ROADMAP.md):
    # CACHE_DISABLED when no `result_cache` was supplied at all, otherwise
    # the real fingerprint's declared readiness for whichever branch (build
    # archetype or plain alternatives) this call actually took.
    cache_readiness: CacheReadiness = CacheReadiness.CACHE_DISABLED


def run_generate(
    registry: Registry,
    heuristic_set: str,
    hull_id: str,
    mode: str,
    profile: str | None = None,
    faction_id: str | None = None,
    faction_mode: str | None = None,
    advanced_config: Path | None = None,
    flux_mode: str | None = None,
    max_candidates: int = 5,
    search_depth: int = 1,
    build_alternatives: int = 2,
    overrides_dir: Path | None = None,
    knowledge_pack: ResolvedKnowledgePack | None = None,
    result_cache: AnalysisResultCache | None = None,
) -> GenerateOutcome:
    if not 1 <= max_candidates <= 20:
        raise ValueError("--max-candidates must be between 1 and 20")
    if not 1 <= search_depth <= 10:
        raise ValueError("--search-depth must be between 1 and 10")
    if not 1 <= build_alternatives <= 10:
        raise ValueError("--build-alternatives must be between 1 and 10")
    defaults = resolve_mode(UserMode(mode), profile)
    advanced = load_advanced_request(advanced_config, defaults.profile_id) if advanced_config else None
    if advanced and mode != UserMode.ADVANCED.value:
        raise ValueError("--advanced-config requires --mode advanced")
    selected_profile = advanced.profile_id if advanced else defaults.profile_id
    get_profile(selected_profile)
    resolved_flux_mode = flux_mode or defaults.flux_mode
    resolved_faction_mode = faction_mode or (advanced.faction_mode if advanced else defaults.faction_mode)
    faction = registry.resolve_faction(faction_id) if faction_id else None
    if resolved_faction_mode == "STRICT_FACTION" and faction is None:
        raise ValueError("STRICT_FACTION generation requires an indexed --faction-id")
    approved_weapons = approved_equipment_ids(knowledge_pack, faction.id, "weapons") if faction else frozenset()
    approved_hullmods = approved_equipment_ids(knowledge_pack, faction.id, "hullmods") if faction else frozenset()
    approved_wings = approved_equipment_ids(knowledge_pack, faction.id, "fighters") if faction else frozenset()
    allowed_weapons = set(faction.known_weapons) | set(approved_weapons) if resolved_faction_mode == "STRICT_FACTION" and faction else None
    preferred_weapons = set(faction.known_weapons) | set(approved_weapons) if resolved_faction_mode == "FACTION_PLUS" and faction else None
    if advanced and advanced.allowed_weapon_ids is not None:
        advanced_allowed = set(advanced.allowed_weapon_ids)
        allowed_weapons = advanced_allowed if allowed_weapons is None else allowed_weapons & advanced_allowed
    # Same faction-evidence pattern as weapons above: a faction's own parsed
    # known_hullmods/known_fighters, not an inferred "good for this role" list.
    allowed_hullmods = set(faction.known_hullmods) | set(approved_hullmods) if resolved_faction_mode == "STRICT_FACTION" and faction else None
    preferred_hullmods = set(faction.known_hullmods) | set(approved_hullmods) if resolved_faction_mode == "FACTION_PLUS" and faction else None
    allowed_wings = set(faction.known_fighters) | set(approved_wings) if resolved_faction_mode == "STRICT_FACTION" and faction else None
    preferred_wings = set(faction.known_fighters) | set(approved_wings) if resolved_faction_mode == "FACTION_PLUS" and faction else None
    weapon_role_overrides = load_overrides(overrides_dir, "weapons") if overrides_dir else None
    build_candidates: tuple[BuildCandidateResult, ...] = ()
    if profile is None and advanced is None and "build_archetype_viable_min_compatibility" in get_heuristic_set(heuristic_set).values:
        build_generation_kwargs = dict(
            max_candidates=max_candidates, alternatives_per_build=build_alternatives, search_depth=search_depth,
            allowed_weapon_ids=allowed_weapons, preferred_weapon_ids=preferred_weapons,
            denied_weapon_ids=None, locked_weapons_by_mount=None, empty_mount_ids=None,
            flux_mode=resolved_flux_mode, allowed_hullmod_ids=allowed_hullmods,
            preferred_hullmod_ids=preferred_hullmods, allowed_wing_ids=allowed_wings,
            preferred_wing_ids=preferred_wings, weapon_role_overrides=weapon_role_overrides,
        )
        if result_cache is not None:
            fingerprint = build_archetype_candidates_fingerprint(hull_id, registry, heuristic_set, **build_generation_kwargs)
            cache_readiness = resolve_cache_status(result_cache, fingerprint)
            cached = result_cache.get_fingerprint("build_archetype_candidates", hull_id, fingerprint)
            if cached is not None:
                build_candidates = build_archetype_candidates_result_from_payload(cached)
            else:
                build_candidates = generate_build_archetype_candidates(hull_id, registry, heuristic_set, **build_generation_kwargs)
                result_cache.put_fingerprint("build_archetype_candidates", hull_id, fingerprint, build_archetype_candidates_result_to_payload(build_candidates))
        else:
            cache_readiness = resolve_cache_status(result_cache, None)
            build_candidates = generate_build_archetype_candidates(hull_id, registry, heuristic_set, **build_generation_kwargs)
        candidates = [item.candidate for item in build_candidates]
        selected_profile = "MULTI_ARCHETYPE"
        assessed_candidates = []
        for item in build_candidates:
            quality = score_candidate(item.candidate.variant, registry, item.profile_id, heuristic_set, resolved_flux_mode, faction)
            recommendation_score = round((quality.final_score or 0.0) * item.build.compatibility, 3) if quality.final_score is not None else None
            assessed_candidates.append({
                "variant": asdict(item.candidate.variant), "legality": item.candidate.legality,
                "omissions": item.candidate.omissions, "omission_records": [asdict(record) for record in item.candidate.omission_records], "build_archetype": asdict(item.build),
                "profile_id": item.profile_id,
                "recommendation_label": f"Best {item.build.role}",
                "build_recommendation_score": recommendation_score,
                "quality": asdict(quality),
            })
    else:
        alternatives_kwargs = dict(
            allowed_weapon_ids=allowed_weapons, preferred_weapon_ids=preferred_weapons,
            denied_weapon_ids=set(advanced.denied_weapon_ids) if advanced else None,
            locked_weapons_by_mount=advanced.locked_weapons_by_mount if advanced else None,
            empty_mount_ids=set(advanced.empty_mount_ids) if advanced else None,
            max_candidates=max_candidates, flux_mode=resolved_flux_mode,
            allowed_hullmod_ids=allowed_hullmods, preferred_hullmod_ids=preferred_hullmods,
            allowed_wing_ids=allowed_wings, preferred_wing_ids=preferred_wings,
            search_depth=search_depth, weapon_role_overrides=weapon_role_overrides,
            heuristic_set=heuristic_set,
        )
        if result_cache is not None:
            fingerprint = candidate_alternatives_fingerprint(hull_id, selected_profile, registry, **alternatives_kwargs)
            cache_readiness = resolve_cache_status(result_cache, fingerprint)
            cached = result_cache.get_fingerprint("candidate_alternatives", hull_id, fingerprint)
            if cached is not None:
                candidates = candidate_alternatives_result_from_payload(cached)
            else:
                candidates = generate_candidate_alternatives(hull_id, selected_profile, registry, **alternatives_kwargs)
                result_cache.put_fingerprint("candidate_alternatives", hull_id, fingerprint, candidate_alternatives_result_to_payload(candidates))
        else:
            cache_readiness = resolve_cache_status(result_cache, None)
            candidates = generate_candidate_alternatives(hull_id, selected_profile, registry, **alternatives_kwargs)
        assessed_candidates = [
            {"variant": asdict(candidate.variant), "legality": candidate.legality, "profile_id": selected_profile,
             "omissions": candidate.omissions, "omission_records": [asdict(record) for record in candidate.omission_records],
             "quality": asdict(score_candidate(candidate.variant, registry, selected_profile, heuristic_set, resolved_flux_mode, faction, advanced.scoring_weight_overrides if advanced else None))}
            for candidate in candidates
        ]
    # Quality is reported only after legality. Ordering cannot make an
    # illegal or indeterminate variant eligible for export/use.
    assessed_candidates.sort(key=lambda item: (
        item["legality"] != "LEGAL",
        -(item.get("build_recommendation_score", item["quality"]["final_score"]) if item.get("build_recommendation_score", item["quality"]["final_score"]) is not None else -1.0),
        item["variant"]["id"],
    ))
    return GenerateOutcome(
        defaults, advanced, selected_profile, resolved_flux_mode, resolved_faction_mode,
        faction, bool(preferred_weapons), candidates, assessed_candidates, build_candidates, cache_readiness,
    )


def run_export(registry: Registry, heuristic_set: str, output_dir: Path, hull_id: str, profile: str, overrides_dir: Path | None = None) -> Path:
    get_profile(profile)
    weapon_role_overrides = load_overrides(overrides_dir, "weapons") if overrides_dir else None
    # heuristic_set is forwarded to generation now, not just to the writer
    # below -- the same silent-drop gap generate_candidate_alternatives had
    # in run_generate before this parameter became real on
    # generate_conservative_candidate; see generation/candidate.py.
    candidate = generate_conservative_candidate(hull_id, profile, registry, weapon_role_overrides=weapon_role_overrides, heuristic_set=heuristic_set)
    return write_compatibility_mod(candidate.variant, registry, output_dir / "compatibility_mod", heuristic_set, profile)


def run_doctrine(registry: Registry, faction_id: str, source_mod: str | None) -> DoctrineEvidence:
    faction = resolve_faction(registry, faction_id, source_mod)
    return analyze_faction_doctrine(faction, registry)


def run_faction_capability(
    registry: Registry, faction_id: str, source_mod: str | None,
    heuristic_set: str = "baseline_0.5",
) -> FactionCapabilityProfile:
    faction = resolve_faction(registry, faction_id, source_mod)
    return analyze_faction_capability(faction, registry, heuristic_set)


def resolve_optional_knowledge_pack(path: Path | None, registry: Registry) -> ResolvedKnowledgePack | None:
    """Load optional advisory pack guidance without making it a registry or legality dependency."""
    if path is None:
        return None
    pack = load_knowledge_pack(path)
    if pack is None:
        raise ValueError(f"Knowledge pack could not be loaded: {path}")
    return resolve_knowledge_pack(pack, registry)


def run_gap_recommendations(
    registry: Registry, faction_id: str, source_mod: str | None,
    heuristic_set: str = "baseline_0.2", knowledge_pack: ResolvedKnowledgePack | None = None,
    constraints: RecommendationConstraints | None = None,
    result_cache: AnalysisResultCache | None = None,
) -> GapRecommendationResult:
    """Compute a faction's gap recommendations, optionally reusing a prior
    result from `result_cache` (`core/result_cache.py`).

    `result_cache` defaults to `None`: every existing caller (CLI, GUI,
    tests) that doesn't pass one sees identical behavior to before this
    parameter existed -- a cache miss always falls through to the exact
    same real computation. Reuse is only ever attempted when the caller
    opts in by supplying a cache, and even then only served when
    `gap_recommendation_fingerprint` reports `CACHE_SAFE` (every consumed
    entity across the whole registry has a real source hash) -- see that
    function's docstring for why this operation's dependency surface is
    the entire registry rather than a bounded per-faction slice.

    The returned result's own `cache_readiness` field (Phase 33,
    ROADMAP.md) makes *why* a value was or wasn't reused explicit and
    inspectable for this specific call: `CACHE_DISABLED` when no
    `result_cache` was supplied at all (the final line below), otherwise
    the real fingerprint's declared readiness (`CACHE_SAFE` for a complete
    dependency context, `CACHE_UNSAFE_INCOMPLETE_CONTEXT` when it wasn't).
    This is orthogonal to hit-vs-miss: a `CACHE_SAFE` call may still have
    missed and freshly computed (then stored for next time) rather than
    hit an existing row.
    """
    faction = resolve_faction(registry, faction_id, source_mod)
    if result_cache is not None:
        fingerprint = gap_recommendation_fingerprint(faction, registry, heuristic_set, knowledge_pack, constraints)
        cache_readiness = resolve_cache_status(result_cache, fingerprint)
        cached = result_cache.get_fingerprint("gap_recommendation", faction.id, fingerprint)
        if cached is not None:
            result = gap_recommendation_result_from_payload(cached)
        else:
            result = recommend_gap_solutions(faction, registry, heuristic_set, knowledge_pack, constraints)
            result_cache.put_fingerprint("gap_recommendation", faction.id, fingerprint, gap_recommendation_result_to_payload(result))
        # `cache_readiness` (Phase 33, ROADMAP.md) is overwritten here, not
        # trusted from the payload/fresh computation: it must reflect this
        # specific call's real decision (CACHE_SAFE/CACHE_UNSAFE_INCOMPLETE_CONTEXT),
        # not whatever was true when an older cached payload was stored, or
        # the CACHE_DISABLED default `recommend_gap_solutions` itself always
        # returns (it never touches a cache).
        return replace(result, cache_readiness=cache_readiness)
    return recommend_gap_solutions(faction, registry, heuristic_set, knowledge_pack, constraints)


def run_fleet_support_advisor(
    registry: Registry, selections: tuple[FleetSelection, ...], faction_id: str | None = None,
    source_mod: str | None = None, heuristic_set: str = "baseline_0.14",
    constraints: FleetSupportConstraints = FleetSupportConstraints(),
) -> FleetSupportResult:
    """Rank individual additions for locked player selections.

    This intentionally does not call generation or validation: without a
    concrete candidate variant, fit legality cannot be determined.  The
    result reports that boundary explicitly for every recommendation.
    """
    faction = resolve_faction(registry, faction_id, source_mod) if faction_id else None
    return recommend_fleet_support(selections, registry, faction, heuristic_set, constraints)


def run_scenario_fleet_advisor(
    registry: Registry, selections: tuple[FleetSelection, ...], scenario: ScenarioObjectiveProfile,
    faction_id: str | None = None, source_mod: str | None = None,
    heuristic_set: str = "baseline_0.14", constraints: FleetSupportConstraints = FleetSupportConstraints(),
) -> ScenarioFleetAssessment:
    """Assess locked fleet alignment with a declared scenario profile.

    This never reads campaign state, resolves a mission by name, predicts a
    battle result, or changes the selected fleet.
    """
    faction = resolve_faction(registry, faction_id, source_mod) if faction_id else None
    return assess_scenario_fleet(selections, registry, scenario, faction, heuristic_set, constraints)


def run_campaign_save_discovery(directory: Path) -> CampaignSaveDiscovery:
    """Expose the user-selected, read-only campaign-directory boundary.

    This is deliberately independent of scanning and registry state: no game
    source and no campaign entry is parsed by discovery alone.
    """
    return discover_campaign_directory(directory)


def run_fleet_advisory_boundaries(
    registry: Registry, selections: tuple[FleetSelection, ...], faction_id: str | None = None,
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> FleetAdvisoryBoundaries:
    """Expose evidence-limited DP/officer advisory views without ranking."""
    return fleet_advisory_boundaries(selections, registry, faction_id, knowledge_pack)


@dataclass(frozen=True)
class ScenarioSupportFitOutcome:
    """A concrete-fit handoff from a freshly revalidated scenario advisory.

    The scenario assessment remains a static alignment view.  Only the
    generated variants in ``generation`` carry normal fit legality results.
    """
    assessment: ScenarioFleetAssessment
    recommendation: FleetSupportRecommendation
    support_purpose: str
    generator_profile: str
    generation: GenerateOutcome


def run_generate_scenario_support_fit(
    registry: Registry, selections: tuple[FleetSelection, ...], scenario: ScenarioObjectiveProfile,
    hull_id: str, faction_id: str | None = None, source_mod: str | None = None,
    heuristic_set: str = "baseline_0.14", constraints: FleetSupportConstraints = FleetSupportConstraints(),
    mode: str = "guided", max_candidates: int = 5, search_depth: int = 1,
) -> ScenarioSupportFitOutcome:
    """Generate only a currently shortlisted scenario-fit recommendation.

    Re-running the Scenario Advisor preserves its declared targets and locked
    selections; a hull from an old or unrelated Fleet Support run cannot be
    silently treated as scenario-qualified.
    """
    faction = resolve_faction(registry, faction_id, source_mod) if faction_id else None
    assessment = assess_scenario_fleet(selections, registry, scenario, faction, heuristic_set, constraints)
    recommendation = next((item for item in assessment.recommendations if item.hull_id == hull_id), None)
    if recommendation is None:
        raise ValueError("Scenario-fit generation requires a currently shortlisted Scenario Advisor recommendation")
    selection = support_fit_profile(recommendation)
    if selection is None:
        raise ValueError("This scenario recommendation has no modeled combat support-fit purpose; logistics-specific fitting is not implemented")
    purpose, profile = selection
    generated = run_generate(
        registry, heuristic_set, hull_id, mode, profile=profile, faction_id=faction_id,
        faction_mode="STRICT_FACTION" if constraints.access_mode == "STRICT_FACTION" else "FACTION_PLUS",
        max_candidates=max_candidates, search_depth=search_depth,
    )
    return ScenarioSupportFitOutcome(assessment, recommendation, purpose, profile, generated)


def load_or_populate_retrofits(
    registry: Registry, hull_id: str, output_root: Path, heuristic_set: str = "baseline_0.2",
) -> object:
    """Return scanned fits, or create local validated starter fits if absent."""
    return populate_variations_if_missing(registry, hull_id, output_root, heuristic_set=heuristic_set)


def save_editable_retrofit_copy(registry: Registry, variant_id: str, output_root: Path, *, replace: bool = False) -> Path:
    variant = registry.variants.by_id.get(variant_id)
    if variant is None:
        raise ValueError(f"Variant not found or ambiguous: {variant_id}")
    return copy_existing_retrofit(variant, output_root, replace=replace)


def save_editable_retrofit_variant(registry: Registry, variant: Variant, output_root: Path, *, replace: bool = False) -> Path:
    return save_editable_variant(variant, registry, output_root, replace=replace)


def load_editable_retrofit_variant(output_root: Path, path: Path) -> Variant:
    return load_editable_retrofit(path, output_root)


def restore_editable_retrofit_variant_history(output_root: Path, history_path: Path) -> Path:
    return restore_editable_retrofit_history(history_path, output_root)


def inspect_editable_retrofit_variant(registry: Registry, output_root: Path, path: Path) -> object:
    return inspect_editable_retrofit(path, output_root, registry)


def publish_editable_retrofit_variant(output_root: Path, path: Path, *, replace: bool = False) -> Path:
    return publish_editable_retrofit(path, output_root, replace=replace)


def run_fleet_support_why_not(
    registry: Registry, selections: tuple[FleetSelection, ...], hull_id: str,
    faction_id: str | None = None, source_mod: str | None = None,
    heuristic_set: str = "baseline_0.14", constraints: FleetSupportConstraints = FleetSupportConstraints(),
) -> FleetSupportWhyNotExplanation:
    """Explain an addition using Fleet Support Advisor's exact ranking path."""
    faction = resolve_faction(registry, faction_id, source_mod) if faction_id else None
    return explain_fleet_support_candidate(selections, registry, hull_id, faction, heuristic_set, constraints)


@dataclass(frozen=True)
class FleetSupportFitOutcome:
    """An explicit post-advisor handoff, never a fit claim on the hull card."""
    recommendation: FleetSupportRecommendation
    support_purpose: str
    generator_profile: str
    generation: GenerateOutcome


def run_generate_fleet_support_fit(
    registry: Registry, selections: tuple[FleetSelection, ...], hull_id: str,
    faction_id: str | None = None, source_mod: str | None = None,
    heuristic_set: str = "baseline_0.14", constraints: FleetSupportConstraints = FleetSupportConstraints(),
    mode: str = "guided", max_candidates: int = 5, search_depth: int = 1,
) -> FleetSupportFitOutcome:
    """Generate a concrete fit only after revalidating a current hull advisory.

    The recommendation remains a hull-only advisory until this function calls
    the normal bounded generator. Its returned variants carry normal
    validation results; no output file is written here.
    """
    faction = resolve_faction(registry, faction_id, source_mod) if faction_id else None
    advisory = recommend_fleet_support(selections, registry, faction, heuristic_set, constraints)
    recommendation = next((item for item in advisory.recommendations if item.hull_id == hull_id), None)
    if recommendation is None:
        raise ValueError("Support-fit generation requires a currently shortlisted Fleet Support Advisor recommendation")
    selection = support_fit_profile(recommendation)
    if selection is None:
        raise ValueError("This recommendation has no modeled combat support-fit purpose; logistics-specific fitting is not implemented")
    purpose, profile = selection
    generated = run_generate(
        registry, heuristic_set, hull_id, mode, profile=profile, faction_id=faction_id,
        faction_mode="STRICT_FACTION" if constraints.access_mode == "STRICT_FACTION" else "FACTION_PLUS",
        max_candidates=max_candidates, search_depth=search_depth,
    )
    return FleetSupportFitOutcome(recommendation, purpose, profile, generated)


def run_why_not(
    registry: Registry, faction_id: str, role: str, hull_id: str,
    source_mod: str | None = None, heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
    build_archetype_id: str | None = None,
    campaign_stage: str | None = None,
) -> CombinedWhyNotExplanation | BuildWhyNotExplanation:
    faction = resolve_faction(registry, faction_id, source_mod)
    if build_archetype_id:
        return explain_build_candidate(faction, registry, role, hull_id, build_archetype_id, heuristic_set, knowledge_pack, campaign_stage)
    if campaign_stage:
        raise ValueError("campaign_stage requires build_archetype_id so Why-Not can reproduce the exact Hull + BuildArchetype ranking")
    return explain_candidate(faction, registry, role, hull_id, heuristic_set, knowledge_pack)


def run_analyze_variant(
    registry: Registry, variant_id: str, profile: str, flux_mode: str,
    heuristic_set: str = "baseline_0.2",
    faction_id: str | None = None, source_mod: str | None = None,
    overrides_dir: Path | None = None,
) -> VariantAnalysis:
    get_profile(profile)
    variant = registry.variants.by_id.get(variant_id)
    if variant is None:
        raise ValueError(f"Variant not found or ambiguous: {variant_id}")
    faction = resolve_faction(registry, faction_id, source_mod) if faction_id else None
    hull_override = None
    if overrides_dir and variant.hull_id:
        hull_override = load_overrides(overrides_dir, "hulls").get(variant.hull_id)
    return analyze_variant(variant, registry, profile, flux_mode, faction, hull_override, heuristic_set=heuristic_set)


def run_analyze_variant_record(
    registry: Registry, variant: Variant, profile: str, flux_mode: str, heuristic_set: str = "baseline_0.2",
) -> VariantAnalysis:
    """Analyze an explicit user-owned editable variant without indexing it."""
    get_profile(profile)
    return analyze_variant(variant, registry, profile, flux_mode, None, None, heuristic_set=heuristic_set)


def run_variant_control_evidence(registry: Registry, variant_id: str, transcript_path: Path) -> dict[str, object]:
    """Return advisory transcript claims applicable to one locally resolved variant.

    This is deliberately a presentation-only service. It neither contributes
    to `VariantAnalysis`'s mechanical fields nor calls validation/scoring.
    """
    variant = registry.variants.by_id.get(variant_id)
    if variant is None:
        raise ValueError(f"Variant not found or ambiguous: {variant_id}")
    if not variant.hull_id:
        return {"variant_id": variant.id, "hull_id": None, "status": "UNRESOLVED_VARIANT_HULL", "claims": []}
    all_evidence = resolve_control_suitability_evidence(load_video_review_transcript(transcript_path), registry)
    claims = [item for item in all_evidence if item.hull_id == variant.hull_id]
    return {
        "variant_id": variant.id,
        "hull_id": variant.hull_id,
        "status": "RESOLVED_CLAIMS" if claims else "NO_RESOLVED_CLAIMS",
        "claims": [asdict(item) for item in claims],
        "unresolved_records": sum(item.hull_id is None for item in all_evidence),
        "advisory_only": True,
    }


def run_check_export(registry: Registry, manifest: Path) -> StalenessReport:
    return check_generation_manifest(manifest, registry)


def run_fix_legality(
    registry: Registry, variant_id: str, heuristic_set: str = "baseline_0.2",
    locked_mount_ids: frozenset[str] = frozenset(),
    locked_hullmod_ids: frozenset[str] = frozenset(),
    locked_wing_ids: frozenset[str] = frozenset(),
    substitution_mode: str = "cheapest",
    requesting_faction_id: str | None = None,
) -> RefitResult:
    variant = registry.variants.by_id.get(variant_id)
    if variant is None:
        raise ValueError(f"Variant not found or ambiguous: {variant_id}")
    return fix_legality(variant, registry, heuristic_set, locked_mount_ids, locked_hullmod_ids, locked_wing_ids, substitution_mode, requesting_faction_id)


def run_improve_quality(
    registry: Registry, variant_id: str, mode: str, profile: str,
    heuristic_set: str = "baseline_0.2",
    locked_mount_ids: frozenset[str] = frozenset(),
    locked_hullmod_ids: frozenset[str] = frozenset(),
    locked_wing_ids: frozenset[str] = frozenset(),
    flux_mode: str = "BALANCED",
    faction_id: str | None = None, source_mod: str | None = None,
) -> QualityRefitResult:
    variant = registry.variants.by_id.get(variant_id)
    if variant is None:
        raise ValueError(f"Variant not found or ambiguous: {variant_id}")
    get_profile(profile)
    faction = resolve_faction(registry, faction_id, source_mod) if faction_id else None
    return improve_quality(variant, registry, mode, profile, heuristic_set, locked_mount_ids, locked_hullmod_ids, locked_wing_ids, flux_mode, faction)
