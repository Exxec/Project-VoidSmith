"""Gap recommendation cache responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack
from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.result_cache import AnalysisContextFingerprint, CacheReadiness
from .models import AcquisitionRecommendation, CapabilityGap, GapRecommendationResult, NativeRecommendation, RecommendationConstraints, RetrofitRecommendation

# --- Result-cache reuse (core/result_cache.py) --------------------------
#
# `recommend_gap_solutions` is a heavier, multi-step computation than a
# single hull/faction report: its retrofit leg runs a genuine refit-
# improvement search (`generation/refit.py::improve_quality`) per
# candidate hull, and its acquisition leg scores every indexed hull in the
# registry. Repeated calls for the same faction/heuristic_set/knowledge-
# pack/constraints (a GUI user reopening the same faction, or a batch
# evaluation across runs) can safely reuse a prior result -- but only when
# every real input is honestly captured. See `_registry_wide_entity_hashes`
# below for why that surface is the whole registry, not a bounded slice.

# The retrofit leg's adapter-derived defense/mobility/logistics effects
# (`generation/refit.py` -> `starsector_variant_generator.adapters`,
# `analysis/combat_stats.py`, `analysis/mobility_stats.py`) are a fixed,
# hand-authored vanilla table -- never derived from scanned Java source, so
# no per-scan source hash applies to them. Bump this marker if that table's
# effect values or coverage ever change, the same way
# `hullmod_static_analysis.API_EFFECT_REGISTRY_VERSION` versions the
# separate, Java-derived hullmod registry.
GAP_RECOMMENDATION_ADAPTER_VERSION = "vanilla_static_adapters-1"


def _registry_wide_entity_hashes(registry: Registry) -> tuple[str, ...] | None:
    """Every consumed entity's real source hash, or ``None`` if incomplete.

    `recommend_gap_solutions` cannot be narrowed to one hull's or one
    faction's own referenced entities the way
    `output/analysis_reports.py`'s `_hull_profile_fingerprint` /
    `_faction_capability_fingerprint` are: its acquisition leg
    (`recommend_acquisition_solutions`) iterates every indexed hull in
    `registry.hulls.by_id` directly (not just this faction's known hulls),
    its retrofit leg's refit search draws weapon/hullmod substitutes from
    the entire weapon/hullmod registry the same way
    `generation/candidate.py` does, and cross-faction equipment affinity
    (`analysis/equipment_affinity.py`) depends on every other faction's own
    known-hull/known-weapon/known-hullmod sets. A change anywhere in the
    scan can therefore change this result, so the honest dependency
    surface is the whole registry. Any entity missing a source hash fails
    this closed rather than guessing the real surface is narrower.
    """
    hashes: list[str] = []
    for index in (registry.hulls, registry.weapons, registry.hullmods, registry.fighters, registry.variants, registry.factions):
        for entity in index.by_id.values():
            if entity.source_hash is None:
                return None
            hashes.append(entity.source_hash)
    return tuple(sorted(hashes))


def _knowledge_pack_fingerprint(knowledge_pack: ResolvedKnowledgePack | None) -> str:
    """A stable identifier for every resolved-pack field this engine actually
    consumes (build-archetype preference, progression guidance, capability-
    gap guidance, retrofit templates, officer guidance, approved equipment).
    Two packs at the same freshness status can still carry different
    resolved content, so freshness status alone would be unsafe here."""
    if knowledge_pack is None:
        return "NONE"
    payload = {
        "path": str(knowledge_pack.pack.path),
        "pack_version": knowledge_pack.pack.manifest.pack_version,
        "target_faction_id": knowledge_pack.pack.manifest.target_faction_id,
        "example_only": knowledge_pack.pack.example_only,
        "freshness_status": knowledge_pack.freshness.status,
        "freshness_reasons": list(knowledge_pack.freshness.reasons),
        "hull_archetypes": list(knowledge_pack.hull_archetypes),
        "retrofit_templates": list(knowledge_pack.retrofit_templates),
        "approved_equipment": list(knowledge_pack.approved_equipment),
        "unresolved_references": list(knowledge_pack.unresolved_references),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def gap_recommendation_fingerprint(
    faction: Faction,
    registry: Registry,
    heuristic_set: str,
    knowledge_pack: ResolvedKnowledgePack | None = None,
    constraints: RecommendationConstraints | None = None,
) -> AnalysisContextFingerprint:
    """Declare `recommend_gap_solutions`'s real, complete dependency context.

    `target_faction_id` is folded into `constraints_hash` (not just passed
    as the cache's `target_id`) because `AnalysisResultCache.key` only
    hashes the declared context -- two different factions evaluated against
    an otherwise-identical registry/heuristic_set/pack/constraints would
    otherwise produce the same context hash and collide in the cache's
    single-column primary key. See `analyze_faction_capability`'s own
    fingerprint sibling in `output/analysis_reports.py`, which avoids the
    same collision by hashing the faction entity itself as a dependency.
    """
    constraints = constraints or RecommendationConstraints()
    entity_hashes = _registry_wide_entity_hashes(registry)
    constraints_payload = {
        "target_faction_id": faction.id,
        "target_faction_source_hash": faction.source_hash,
        "allow_foreign_hulls": constraints.allow_foreign_hulls,
        "include_experimental_builds": constraints.include_experimental_builds,
        "campaign_stage": constraints.campaign_stage,
    }
    constraints_hash = hashlib.sha256(
        json.dumps(constraints_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    complete = entity_hashes is not None and faction.source_hash is not None
    return AnalysisContextFingerprint(
        operation="gap_recommendation",
        entity_hashes=entity_hashes if entity_hashes is not None else (),
        heuristic_set=heuristic_set,
        adapter_versions=(GAP_RECOMMENDATION_ADAPTER_VERSION,),
        knowledge_pack_freshness=_knowledge_pack_fingerprint(knowledge_pack),
        constraints_hash=constraints_hash,
        readiness=CacheReadiness.CACHE_SAFE if complete else CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT,
    )


def gap_recommendation_result_to_payload(result: GapRecommendationResult) -> dict[str, Any]:
    """JSON-safe serialization for the result cache. `dataclasses.asdict`
    already recursively converts every nested dataclass, and `EvidenceClass`
    (a `StrEnum`) serializes as a plain string, so no further conversion is
    needed on the write path."""
    return asdict(result)


def _restore_archetype_evidence(data: dict[str, Any] | None) -> dict[str, tuple[str, ...]]:
    return {key: tuple(value) for key, value in (data or {}).items()}


def _restore_capability_gap(data: dict[str, Any]) -> CapabilityGap:
    return CapabilityGap(
        role=data["role"], tier=data["tier"],
        faction_existing_coverage=data["faction_existing_coverage"],
        evidence_confidence=data["evidence_confidence"],
        guidance_notes=tuple(data.get("guidance_notes") or ()),
        guidance_confidence=data.get("guidance_confidence"),
        capability_dimension=data.get("capability_dimension"),
        vector_score=data.get("vector_score"),
        vector_confidence=data.get("vector_confidence"),
        evidence_class=EvidenceClass(data.get("evidence_class") or EvidenceClass.INFERRED_MECHANICS.value),
    )


def _restore_native(data: dict[str, Any]) -> NativeRecommendation:
    return NativeRecommendation(
        role=data["role"], hull_id=data["hull_id"], capability_score=data["capability_score"], rank=data["rank"],
        confidence=data.get("confidence", 1.0),
        archetype_scores=dict(data.get("archetype_scores") or {}),
        archetype_evidence=_restore_archetype_evidence(data.get("archetype_evidence")),
        diversity_reason=data.get("diversity_reason"),
        build_archetype_id=data.get("build_archetype_id"),
        build_archetype_label=data.get("build_archetype_label"),
        build_compatibility=data.get("build_compatibility"),
        build_confidence=data.get("build_confidence"),
        build_maturity=data.get("build_maturity"),
        recommendation_score=data.get("recommendation_score"),
        incremental_capability_gain=data.get("incremental_capability_gain", 0.0),
        evidence_class=EvidenceClass(data.get("evidence_class") or EvidenceClass.INFERRED_MECHANICS.value),
    )


def _restore_retrofit(data: dict[str, Any]) -> RetrofitRecommendation:
    return RetrofitRecommendation(
        role=data["role"], hull_id=data["hull_id"], variant_id=data["variant_id"],
        capability_score=data["capability_score"], role_match_before=data["role_match_before"],
        role_match_after=data["role_match_after"], quality_gain=data["quality_gain"],
        changes=data["changes"], change_cost=data["change_cost"], rank=data["rank"],
        confidence=data.get("confidence", 1.0),
        archetype_scores=dict(data.get("archetype_scores") or {}),
        archetype_evidence=_restore_archetype_evidence(data.get("archetype_evidence")),
        diversity_reason=data.get("diversity_reason"),
        build_archetype_id=data.get("build_archetype_id"),
        build_archetype_label=data.get("build_archetype_label"),
        build_compatibility=data.get("build_compatibility"),
        build_confidence=data.get("build_confidence"),
        build_maturity=data.get("build_maturity"),
        recommendation_score=data.get("recommendation_score"),
        incremental_capability_gain=data.get("incremental_capability_gain", 0.0),
        retrofit_disruption=data.get("retrofit_disruption", 0.0),
        role_distortion=data.get("role_distortion", 0.0),
        knowledge_template_ids=tuple(data.get("knowledge_template_ids") or ()),
        knowledge_guidance_confidence=data.get("knowledge_guidance_confidence"),
        evidence_class=EvidenceClass(data.get("evidence_class") or EvidenceClass.INFERRED_MECHANICS.value),
    )


def _restore_acquisition(data: dict[str, Any]) -> AcquisitionRecommendation:
    return AcquisitionRecommendation(
        role=data["role"], hull_id=data["hull_id"], capability_score=data["capability_score"],
        affinity=data["affinity"], owning_faction_ids=tuple(data.get("owning_faction_ids") or ()),
        preference_weight=data["preference_weight"], rank=data["rank"],
        confidence=data.get("confidence", 1.0),
        archetype_scores=dict(data.get("archetype_scores") or {}),
        archetype_evidence=_restore_archetype_evidence(data.get("archetype_evidence")),
        diversity_reason=data.get("diversity_reason"),
        build_archetype_id=data.get("build_archetype_id"),
        build_archetype_label=data.get("build_archetype_label"),
        build_compatibility=data.get("build_compatibility"),
        build_confidence=data.get("build_confidence"),
        build_maturity=data.get("build_maturity"),
        recommendation_score=data.get("recommendation_score"),
        incremental_capability_gain=data.get("incremental_capability_gain", 0.0),
        evidence_class=EvidenceClass(data.get("evidence_class") or EvidenceClass.INFERRED_MECHANICS.value),
    )


def gap_recommendation_result_from_payload(payload: dict[str, Any]) -> GapRecommendationResult:
    """Reconstruct a `GapRecommendationResult` from a cached JSON payload.

    Reverses `gap_recommendation_result_to_payload` field-for-field --
    every tuple- and `EvidenceClass`-typed field is rebuilt explicitly so a
    cache hit compares equal (`==`) to the same fresh computation. A plain
    JSON round-trip alone would leave tuples as lists, which fail dataclass
    equality against the real, freshly-computed result.
    """
    return GapRecommendationResult(
        faction_id=payload["faction_id"],
        gaps=tuple(_restore_capability_gap(item) for item in payload.get("gaps", ())),
        native_recommendations={
            role: tuple(_restore_native(item) for item in items)
            for role, items in (payload.get("native_recommendations") or {}).items()
        },
        unaddressed_gaps=tuple(payload.get("unaddressed_gaps") or ()),
        retrofit_recommendations={
            role: tuple(_restore_retrofit(item) for item in items)
            for role, items in (payload.get("retrofit_recommendations") or {}).items()
        },
        acquisition_recommendations={
            role: tuple(_restore_acquisition(item) for item in items)
            for role, items in (payload.get("acquisition_recommendations") or {}).items()
        },
        fully_unaddressed_gaps=tuple(payload.get("fully_unaddressed_gaps") or ()),
        officer_guidance=tuple(payload.get("officer_guidance") or ()),
    )
