"""Gap Recommendation Engine: native, retrofit, and acquisition legs.

See GAP_RECOMMENDATION_ENGINE.md (project-authored, root of the repo) for
the full target design. Native search (section 6) was the only leg
implementable at first, since retrofit/acquisition search structurally
depended on the Equipment Access / Adaptive Autofit and Refit Assistant
phases (root ROADMAP.md phases 8 and 9) -- neither existed yet. Both now
do, so sections 5 and 7 are implemented below too.

Retrofit search (section 5) is NOT "make a structurally weak hull strong
at this role" -- `classify_hull`'s capability axes are purely structural
(mount composition, fighter-bay presence); no refit can add a hull LARGE
mounts it doesn't have. What it actually searches for, per
FACTION_KNOWLEDGE_PACKS.md section 14 ("search native retrofit
solutions"): among the SAME structurally-capable native hulls the native
leg already finds, does that hull's real, currently-fitted variant
actually realize that structural potential, or would a genuine Refit
Assistant pass (`generation/refit.py::improve_quality`, `IMPROVE_ROLE_MATCH`)
meaningfully close a loadout-quality gap on top of it? This is honest,
bounded v1 work: it reuses the native leg's own ranked candidate pool and
the Refit Assistant's own real quality delta, never inventing a new
inference mechanism.

Acquisition search (section 7) ranks non-native hulls (COMMON/FOREIGN/
UNALIGNED per `analysis/equipment_affinity.py`, extended here to hulls)
by `capability_score * affinity_preference_<tier>` -- the same
`baseline_0.2` preference table adaptive substitution scoring already
uses, directly implementing FACTION_KNOWLEDGE_PACKS.md section 9's
"foreign acquisitions normally need a clear capability advantage" without
inventing a new doctrine-strictness mechanism (section 9's LOOSE/BALANCED/
STRICT modes remain unimplemented -- that's a real, separate future step,
not silently approximated here).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from dataclasses import replace as dataclass_replace
from enum import StrEnum
from typing import Any

from starsector_variant_generator.analysis.build_archetypes import (
    BuildArchetypeProfile,
    infer_build_archetypes,
    profile_id_for_build,
)
from starsector_variant_generator.analysis.capability_vector import (
    CapabilityVector,
    infer_hull_capability_vector,
)
from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.analysis.combat_entity import (
    recommendation_eligibility,
)
from starsector_variant_generator.analysis.equipment_affinity import (
    classify_equipment_affinity,
)
from starsector_variant_generator.analysis.faction_capability import (
    FactionCapabilityProfile,
    analyze_faction_capability,
)
from starsector_variant_generator.analysis.mechanical_archetypes import (
    MechanicalArchetypeProfile,
    infer_mechanical_archetypes,
)
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.knowledge_packs import (
    ResolvedKnowledgePack,
    build_archetype_preference,
    capability_gap_guidance,
    officer_guidance,
    progression_guidance_confidence,
    progression_hull_ids,
    retrofit_template_ids,
)
from starsector_variant_generator.core.models import Faction, Variant
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.result_cache import (
    AnalysisContextFingerprint,
    CacheReadiness,
)
from starsector_variant_generator.generation.refit import (
    QualityRefitResult,
    improve_quality,
)


@dataclass(frozen=True)
class CapabilityGap:
    role: str
    tier: str  # "WEAK" or "GAP" -- see GAP_RECOMMENDATION_ENGINE.md section 4
    faction_existing_coverage: float
    evidence_confidence: float
    guidance_notes: tuple[str, ...] = ()
    guidance_confidence: float | None = None
    capability_dimension: str | None = None
    vector_score: float | None = None
    vector_confidence: float | None = None
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


@dataclass(frozen=True)
class RecommendationConstraints:
    """Lightweight policy filters; never legality or capability inference."""

    allow_foreign_hulls: bool = True
    include_experimental_builds: bool = True
    campaign_stage: str | None = None  # user-selected pack guidance; never inferred from a save


@dataclass(frozen=True)
class RecommendationAudit:
    """One real candidate's complete ranking context for one recommendation
    leg, computed exactly once by that leg's own audit-trail builder
    (`_native_audit_trail`/`_retrofit_audit_trail`/`_acquisition_audit_trail`)
    and consumed identically by both that leg's `recommend_*_solutions`
    function (which keeps only the `recommended=True` entries, ordered by
    `selection_order`, to build its returned shortlist) and its
    `explain_*_candidate` Why-Not counterpart (which looks up one
    candidate's own entry) -- so Why-Not can never independently
    reconstruct ranking/selection logic that could drift from what
    actually produced the real recommendation.

    ROADMAP.md Phase 32: consolidates Phase 11's "shared ranking helper"
    fix (both paths already called the same `_rank_candidates_for_role`/
    `_rank_build_candidates_for_role`/`_diverse_*_shortlist` primitives)
    into a first-class, reusable, per-candidate TYPE. Before this phase,
    the Retrofit and Acquisition legs' `explain_*_candidate` functions did
    NOT reuse those shared primitives the way the Native leg's did -- each
    had its own inline, hull-only, non-build-aware recomputation that could
    (and, confirmed live, DID) disagree with the real build-aware
    `recommend_*_solutions` result under `baseline_0.4`+ heuristic sets
    (including the CLI's real default `baseline_0.7`). See SVG-018 in
    `docs/BUGS.md`.

    Deliberately NOT persisted on `GapRecommendationResult` or the result
    cache's JSON payload: every consumer of this type recomputes it fresh
    within one real command (matching this project's "everything is read
    fresh per command" architecture, CLAUDE.md/AGENTS.md), so this type's
    value is the single shared construction path per call, not cross-call
    persistence -- adding it to the cached payload would also require
    extending `gap_recommendation_result_to_payload`/`_from_payload`'s
    exact round-trip contract, out of this phase's minimal-touch scope.

    `extra` carries leg-specific raw components (e.g. Retrofit's real
    `Variant`/`QualityRefitResult`/gain, Acquisition's affinity
    classification, every leg's inferred `BuildArchetypeProfile`) that a
    caller needs to build its own public dataclass instance from this audit
    without recomputing them -- the same role
    `RetrofitWhyNotExplanation.scoring_components`/
    `AcquisitionWhyNotExplanation.scoring_components` already played,
    generalized across every leg and shared with the ranking path too.
    """

    leg: str  # "NATIVE" | "RETROFIT" | "ACQUISITION"
    role: str
    hull_id: str
    build_archetype_id: str | None
    own_score: float  # this candidate's own real ranking score (composite where build-aware); every construction site below always supplies a real float, never None
    rank: int  # 1-based rank among every real candidate considered for this (leg, role); every construction site below always supplies `index + 1`, never None
    total_candidates: int
    best_score: float | None
    cutoff_score: float | None  # lowest score among the real selected shortlist, when one was chosen
    recommended: bool  # inside the real, returned shortlist for this (leg, role)?
    selection_order: int | None  # 1-based position within the real returned shortlist -- only set when recommended
    selection_reason: str | None
    extra: dict[str, Any] = field(default_factory=dict)


def _require_selection_order(audit: RecommendationAudit) -> int:
    """Type-narrowing accessor for `audit.selection_order` (`int | None`).

    Every `_native_audit_trail`/`_retrofit_audit_trail`/
    `_acquisition_audit_trail` construction site builds `selection_reasons`
    and `selection_order` from the very same `selected` shortlist in the
    same pass (see each trail builder's own code), so `recommended=True`
    and `selection_order is not None` are always set together -- an audit
    can never be `recommended` with no `selection_order`. Every call site
    below already filters to `audit.recommended` before calling this, so
    the `ValueError` should be unreachable in practice; it exists to fail
    loudly on an invariant violation rather than let a `None` silently
    become an arbitrary sort position or a fabricated `rank`.
    """
    if audit.selection_order is None:
        raise ValueError(
            f"RecommendationAudit for hull {audit.hull_id!r} ({audit.leg} leg, role {audit.role!r}) is "
            "marked recommended=True but carries no selection_order -- audit-trail invariant violated."
        )
    return audit.selection_order


@dataclass(frozen=True)
class NativeRecommendation:
    role: str
    hull_id: str
    capability_score: float
    rank: int
    confidence: float = 1.0  # resolved-faction-hull evidence only; no scripted-mechanic inference
    archetype_scores: dict[str, float] = field(default_factory=dict)
    archetype_evidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diversity_reason: str | None = None
    build_archetype_id: str | None = None
    build_archetype_label: str | None = None
    build_compatibility: float | None = None
    build_confidence: float | None = None
    build_maturity: str | None = None
    recommendation_score: float | None = None
    incremental_capability_gain: float = 0.0
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


@dataclass(frozen=True)
class GapRecommendationResult:
    faction_id: str
    gaps: tuple[CapabilityGap, ...]
    native_recommendations: dict[str, tuple[NativeRecommendation, ...]]
    unaddressed_gaps: tuple[str, ...]  # no NATIVE solution for this gap -- retrofit/acquisition may still exist
    retrofit_recommendations: dict[str, tuple[RetrofitRecommendation, ...]] = field(default_factory=dict)
    acquisition_recommendations: dict[str, tuple[AcquisitionRecommendation, ...]] = field(default_factory=dict)
    fully_unaddressed_gaps: tuple[str, ...] = ()  # no solution across ALL THREE legs -- GAP_RECOMMENDATION_ENGINE.md section 15
    officer_guidance: tuple[dict[str, object], ...] = ()  # advisory pack data, never a score input
    # Real, inspectable per-call cache decision (Phase 33, ROADMAP.md) --
    # NOT persisted meaningfully through the result cache's own payload
    # round-trip: `recommend_gap_solutions` itself never touches a cache, so
    # its direct callers correctly see the honest default below; only
    # `api.py::run_gap_recommendations` (the one real `AnalysisResultCache`
    # consumer for this operation) overwrites it via `dataclasses.replace`
    # after a lookup/store, reflecting *that specific call's* real decision
    # rather than whatever was true when an older cached payload was stored.
    cache_readiness: CacheReadiness = CacheReadiness.CACHE_DISABLED


def _evidence_confidence(profile: FactionCapabilityProfile) -> float:
    total = profile.known_hulls_examined + len(profile.unresolved_known_hull_ids)
    return (profile.known_hulls_examined / total) if total else 0.0


# Shared by `detect_capability_gaps` (per-role CapabilityVector dimension
# lookup) and `_capability_gap_confidence_inputs` (ROADMAP.md Phase 32: lets
# a Why-Not explanation compute the identical evidence_confidence/
# vector_confidence a `CapabilityGap` for that role would carry, even when
# asked about a role that is not currently a detected WEAK/GAP-tier gap for
# this faction) -- one literal table, never two that could drift apart.
_ROLE_CAPABILITY_DIMENSION = {
    "LINE_ARTILLERY": "LONG_RANGE_PRESSURE", "LINE_BRAWLER": "SUSTAINED_PRESSURE",
    "MISSILE_SUPPORT": "MISSILE_PROJECTION", "CARRIER": "CARRIER_PROJECTION",
    "BATTLE_CARRIER": "CARRIER_PROJECTION",
}


def _recommendation_confidence_from_values(
    evidence_confidence: float, vector_confidence: float | None,
    build: BuildArchetypeProfile | None = None, extra: float = 1.0,
) -> float:
    """Conservative confidence propagation for ranking evidence.

    The score and confidence remain separate.  A mechanically viable build
    with incomplete scanned inputs can rank well, but cannot present itself
    as fully certain. Takes raw evidence/vector confidence values (rather
    than a full `CapabilityGap`) so a Why-Not explanation -- which may be
    asked about a role that is not currently a detected gap for this
    faction, and so has no real `CapabilityGap` instance to read -- can
    still report the exact same confidence a real ranking would have
    produced for that role. `_recommendation_confidence` (below) is the
    `CapabilityGap`-based convenience wrapper every ranking function
    actually calls.
    """
    factors = [evidence_confidence, extra]
    if vector_confidence is not None:
        factors.append(vector_confidence)
    if build is not None:
        factors.append(build.confidence)
    return round(min(factors), 3)


def _recommendation_confidence(gap: CapabilityGap, build: BuildArchetypeProfile | None = None, extra: float = 1.0) -> float:
    return _recommendation_confidence_from_values(gap.evidence_confidence, gap.vector_confidence, build, extra)


def _capability_gap_confidence_inputs(
    profile: FactionCapabilityProfile, role: str, heuristic_set: str = "baseline_0.2",
) -> tuple[float, float | None]:
    """The exact `(evidence_confidence, vector_confidence)` pair a real
    `CapabilityGap` for `role` would carry, computed for ANY role -- not
    just a currently WEAK/GAP-tier one. Why-Not (`explain_native_candidate`/
    `explain_retrofit_candidate`/`explain_acquisition_candidate`) answers
    "would this hull be recommended for `role`?" even for a role that is
    not currently a detected gap for this faction (an ADEQUATE/STRONG axis,
    or a role the real ranking never touched this call), so it cannot
    always look up a real `CapabilityGap` instance the way a ranking
    function -- which only ever iterates `detect_capability_gaps`'s
    WEAK/GAP-tier output -- can. Mirrors `detect_capability_gaps`'s own
    per-capability confidence computation exactly (never a second,
    potentially-drifting formula), just without that function's
    tier-based filtering.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    vector_enabled = "weight_pd_coverage" in heuristics
    dimension = _ROLE_CAPABILITY_DIMENSION.get(role)
    vector_evidence = profile.capability_vector.get(dimension) if vector_enabled and dimension else None
    evidence_confidence = min(_evidence_confidence(profile), vector_evidence.confidence) if vector_evidence else _evidence_confidence(profile)
    vector_confidence = vector_evidence.confidence if vector_evidence else None
    return evidence_confidence, vector_confidence


def detect_capability_gaps(
    profile: FactionCapabilityProfile,
    heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> tuple[CapabilityGap, ...]:
    """Classify each of `classify_hull`'s 5 real capability axes into a tier.

    Only WEAK and GAP tiers are returned -- STRONG/ADEQUATE axes are not
    "meaningful" gaps per GAP_RECOMMENDATION_ENGINE.md section 4.
    Thresholds are named, versioned heuristics (Agent.md's rule), not
    literal constants here.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    weak_threshold = heuristics["gap_weak_threshold"]
    adequate_threshold = heuristics["gap_adequate_threshold"]
    vector_enabled = "weight_pd_coverage" in heuristics
    gaps = []
    for capability in profile.role_capabilities:
        dimension = _ROLE_CAPABILITY_DIMENSION.get(capability.role)
        # CapabilityVector was introduced after the legacy role-only sets.
        # Do not silently alter their reproducible recommendations or
        # confidence semantics; baseline_0.5+ opts into this richer evidence.
        vector_evidence = profile.capability_vector.get(dimension) if vector_enabled and dimension else None
        vector_score = vector_evidence.score if vector_evidence and vector_evidence.score is not None else None
        coverage = max(capability.best_score, vector_score or 0.0)
        confidence = min(_evidence_confidence(profile), vector_evidence.confidence) if vector_evidence else _evidence_confidence(profile)
        if coverage >= adequate_threshold:
            continue
        tier = "WEAK" if coverage >= weak_threshold else "GAP"
        guidance = capability_gap_guidance(knowledge_pack, profile.faction_id, capability.role)
        gaps.append(CapabilityGap(
            capability.role, tier, coverage, confidence,
            tuple(note for note, _ in guidance),
            min((guidance_confidence for _, guidance_confidence in guidance), default=None),
            dimension if vector_enabled else None, vector_score, vector_evidence.confidence if vector_evidence else None,
        ))
    return tuple(sorted(gaps, key=lambda gap: gap.role))


def _resolved_known_hulls(faction: Faction, registry: Registry) -> list:
    return [
        registry.hulls.by_id[hull_id] for hull_id in faction.known_hulls
        if hull_id in registry.hulls.by_id and recommendation_eligibility(registry.hulls.by_id[hull_id]).eligible
    ]


def _rank_candidates_for_role(role: str, resolved_hulls: list) -> list[tuple[float, str]]:
    """Every resolved known hull's real score for `role`, positive-only, ranked.

    Full ranking, not truncated to `gap_recommendation_count` -- shared by
    `recommend_native_solutions` (which truncates) and
    `explain_native_candidate` (which needs a hull's true rank even when
    it falls outside the top N actually recommended).
    """
    candidates = [(classify_hull(hull).role_compatibility.get(role, 0.0), hull.id) for hull in resolved_hulls]
    candidates = [(score, hull_id) for score, hull_id in candidates if score > 0.0]
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates


def _diverse_hull_shortlist(ranked: list[tuple[float, str]], registry: Registry, count: int, heuristic_set: str) -> list[tuple[float, str, str]]:
    """Score-first, deterministic diversity selection for one recommendation leg.

    Only baseline_0.3 enables this behavior. A candidate outside the best
    score's configured tolerance is never selected ahead of a better option
    merely to improve variety.
    """
    if heuristic_set != "baseline_0.3":
        return [(score, hull_id, "Selected by recommendation score.") for score, hull_id in ranked[:count]]
    values = get_heuristic_set(heuristic_set).values
    if not ranked:
        return []
    best_score = ranked[0][0]
    tolerance = values["recommendation_diversity_material_score_tolerance"]
    selected: list[tuple[float, str, str]] = [(ranked[0][0], ranked[0][1], "Highest recommendation score.")]
    remaining = ranked[1:]
    profiles = {hull_id: infer_mechanical_archetypes(registry.hulls.by_id[hull_id], registry) for _, hull_id in ranked}
    role_sets = {
        hull_id: {role for role, score in classify_hull(registry.hulls.by_id[hull_id]).role_compatibility.items() if score >= values["recommendation_diversity_min_archetype_compatibility"]}
        for _, hull_id in ranked
    }
    archetype_sets = {
        hull_id: {name for name, score in profile.compatibility_scores.items() if score >= values["recommendation_diversity_min_archetype_compatibility"]}
        for hull_id, profile in profiles.items()
    }
    while remaining and len(selected) < count:
        competitive = [item for item in remaining if item[0] >= best_score * (1.0 - tolerance)]
        pool = competitive or remaining
        selected_ids = [hull_id for _, hull_id, _ in selected]
        def diversity_key(item: tuple[float, str], selected_ids: list[str] = selected_ids) -> tuple[float, float, str]:
            similarities = []
            for selected_id in selected_ids:
                role_similarity = _jaccard(role_sets[item[1]], role_sets[selected_id])
                archetype_similarity = _jaccard(archetype_sets[item[1]], archetype_sets[selected_id])
                similarities.append(
                    values["recommendation_diversity_role_difference_weight"] * role_similarity
                    + values["recommendation_diversity_archetype_difference_weight"] * archetype_similarity
                )
            similarity = max(similarities, default=0.0)
            adjusted_score = item[0] - values["recommendation_diversity_similarity_penalty"] * similarity * best_score
            return (adjusted_score, 1.0 - similarity, item[1])
        choice = max(pool, key=diversity_key)
        reason = "Selected after score ranking for distinct functional-role and inferred mechanical-archetype evidence within the material score tolerance." if choice in competitive else "Selected by recommendation score; no remaining score-competitive alternative was available for diversity."
        selected.append((choice[0], choice[1], reason))
        remaining.remove(choice)
    return selected


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 1.0


def _native_audit_trail(
    faction: Faction,
    registry: Registry,
    role: str,
    heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
    constraints: RecommendationConstraints | None = None,
) -> dict[tuple[str, str | None], RecommendationAudit]:
    """Every real NATIVE candidate for `role`, ranked exactly once, keyed by
    `(hull_id, build_archetype_id_or_None)`. `recommend_native_solutions`
    (which keeps only `recommended=True` entries, ordered by
    `selection_order`) and `explain_native_candidate` (which looks up one
    hull's entries) both read from this single computation -- see
    `RecommendationAudit`'s own docstring for why this consolidation
    matters (ROADMAP.md Phase 32). Keyed by `role` (not a `CapabilityGap`)
    since confidence -- the one field that depends on the full gap's
    `evidence_confidence`/`vector_confidence` -- is computed by each
    caller at its own construction site (both already have the real `gap`
    object in scope there), keeping this trail's ranking computation
    itself gap-independent and reusable from a bare hull_id/role query too.
    """
    constraints = constraints or RecommendationConstraints()
    heuristics = get_heuristic_set(heuristic_set).values
    max_recommendations = int(heuristics["gap_recommendation_count"])
    resolved_hulls = _resolved_known_hulls(faction, registry)
    build_aware = "build_archetype_viable_min_compatibility" in heuristics
    audits: dict[tuple[str, str | None], RecommendationAudit] = {}
    if build_aware:
        ranked = _rank_build_candidates_for_role(
            role, resolved_hulls, registry, heuristic_set, knowledge_pack,
            faction.id, constraints.include_experimental_builds, constraints.campaign_stage,
        )
        total_candidates = len(ranked)
        best_score = ranked[0][0] if ranked else None
        selected = _diverse_build_shortlist(ranked, max_recommendations, heuristic_set, registry)
        selection_reasons = {(hull_id, build.build_id): reason for _, hull_id, build, reason in selected}
        selection_order = {(hull_id, build.build_id): index + 1 for index, (_, hull_id, build, _) in enumerate(selected)}
        cutoff_score = min((score for score, _, _, _ in selected), default=None)
        for index, (score, hull_id, build) in enumerate(ranked):
            key = (hull_id, build.build_id)
            audits[key] = RecommendationAudit(
                "NATIVE", role, hull_id, build.build_id, score, index + 1, total_candidates,
                best_score, cutoff_score, key in selection_reasons, selection_order.get(key),
                selection_reasons.get(key),
                extra={
                    "capability_score": classify_hull(registry.hulls.by_id[hull_id]).role_compatibility.get(role, 0.0),
                    "build": build,
                },
            )
    else:
        ranked_hulls = _rank_candidates_for_role(role, resolved_hulls)
        total_candidates = len(ranked_hulls)
        best_score = ranked_hulls[0][0] if ranked_hulls else None
        selected_hulls = _diverse_hull_shortlist(ranked_hulls, registry, max_recommendations, heuristic_set)
        hull_selection_reasons = {hull_id: reason for _, hull_id, reason in selected_hulls}
        hull_selection_order = {hull_id: index + 1 for index, (_, hull_id, _) in enumerate(selected_hulls)}
        cutoff_score = ranked_hulls[max_recommendations - 1][0] if len(ranked_hulls) >= max_recommendations else None
        for index, (score, hull_id) in enumerate(ranked_hulls):
            audits[(hull_id, None)] = RecommendationAudit(
                "NATIVE", role, hull_id, None, score, index + 1, total_candidates,
                best_score, cutoff_score, hull_id in hull_selection_reasons, hull_selection_order.get(hull_id),
                hull_selection_reasons.get(hull_id),
                extra={"capability_score": score, "build": None},
            )
    return audits


def _native_hull_level_lookup(
    audits: dict[tuple[str, str | None], RecommendationAudit], hull_id: str,
) -> tuple[int | None, int, float | None, bool, str | None, float | None]:
    """Collapse a build-aware `(hull, build)`-keyed native audit trail down
    to one hull's hull-level rank/recommended status -- the dedup-to-best-
    build-per-hull view the legacy, hull-level `WhyNotExplanation` type
    (predating BuildArchetype-aware recommendations) needs. Reads only
    already-computed audit entries -- the same values
    `recommend_native_solutions` itself used -- and never re-ranks from the
    underlying primitives a second time.

    Returns (rank, total_candidates, best_score, recommended, selection_reason, cutoff_score).
    """
    by_hull: dict[str, RecommendationAudit] = {}
    for audit in sorted(audits.values(), key=lambda item: item.rank):
        by_hull.setdefault(audit.hull_id, audit)  # `audits` is rank-ordered per (hull, build); first hit is the hull's best-scoring build
    ranked_hulls = sorted(by_hull.values(), key=lambda item: (-(item.own_score or 0.0), item.hull_id))
    total_candidates = len(ranked_hulls)
    best_score = ranked_hulls[0].own_score if ranked_hulls else None
    rank = next((index + 1 for index, item in enumerate(ranked_hulls) if item.hull_id == hull_id), None)
    hull_audits = [item for item in audits.values() if item.hull_id == hull_id]
    recommended = any(item.recommended for item in hull_audits)
    selection_reason = next(
        (item.selection_reason for item in sorted(hull_audits, key=lambda item: (item.selection_order is None, item.selection_order or 0)) if item.recommended),
        None,
    )
    cutoff_score = next((item.cutoff_score for item in audits.values()), None)
    return rank, total_candidates, best_score, recommended, selection_reason, cutoff_score


def recommend_native_solutions(
    faction: Faction,
    registry: Registry,
    heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
    constraints: RecommendationConstraints | None = None,
) -> GapRecommendationResult:
    """Rank the faction's own real known_hulls against each detected gap.

    Ranks by raw `capability_score`, not a gain over `faction_existing_coverage`:
    that coverage figure is itself defined as the *best score among this
    same native hull set* (`analyze_faction_capability`), so a
    "capability_gain vs. existing coverage" filter would be tautologically
    zero for every native hull -- none can ever beat a baseline derived
    from its own set's maximum. That comparison is only meaningful for
    retrofit/acquisition candidates, which sit outside the native pool
    (see GAP_RECOMMENDATION_ENGINE.md sections 5-7, not yet implemented).
    A gap with no known hull scoring above zero for that role at all is
    recorded in `unaddressed_gaps` rather than padded with a zero-score
    recommendation.
    """
    constraints = constraints or RecommendationConstraints()
    profile = analyze_faction_capability(faction, registry, heuristic_set)
    gaps = detect_capability_gaps(profile, heuristic_set, knowledge_pack)

    native_recommendations: dict[str, tuple[NativeRecommendation, ...]] = {}
    unaddressed: list[str] = []
    for gap in gaps:
        audits = _native_audit_trail(faction, registry, gap.role, heuristic_set, knowledge_pack, constraints)
        selected_audits = sorted((audit for audit in audits.values() if audit.recommended), key=_require_selection_order)
        if not selected_audits:
            unaddressed.append(gap.role)
            continue
        native_recommendations[gap.role] = tuple(
            # `capability_score` is always this hull's own raw, structural
            # `classify_hull(...).role_compatibility[role]` (GAP_RECOMMENDATION_ENGINE.md
            # section 6; matches what RetrofitRecommendation/AcquisitionRecommendation
            # and explain_native_candidate's own independent computation report for
            # the same hull/role), never the Hull+Build composite -- that composite
            # is `audit.own_score` here (already stored separately as
            # `recommendation_score`). In the non-build-aware branch this is the
            # same raw value already.
            NativeRecommendation(gap.role, audit.hull_id,
                                 audit.extra["capability_score"],
                                 rank=_require_selection_order(audit), confidence=_recommendation_confidence(gap, audit.extra["build"]),
                                 archetype_scores=infer_mechanical_archetypes(registry.hulls.by_id[audit.hull_id], registry).compatibility_scores,
                                 archetype_evidence=infer_mechanical_archetypes(registry.hulls.by_id[audit.hull_id], registry).evidence_by_archetype,
                                 diversity_reason=audit.selection_reason,
                                 build_archetype_id=audit.build_archetype_id,
                                 build_archetype_label=audit.extra["build"].role if audit.extra["build"] else None,
                                 build_compatibility=audit.extra["build"].compatibility if audit.extra["build"] else None,
                                 build_confidence=audit.extra["build"].confidence if audit.extra["build"] else None,
                                 build_maturity=audit.extra["build"].maturity if audit.extra["build"] else None,
                                 recommendation_score=audit.own_score,
                                 incremental_capability_gain=0.0)
            for audit in selected_audits
        )
    return GapRecommendationResult(profile.faction_id, gaps, native_recommendations, tuple(unaddressed))


# The 5 real `classify_hull` capability axes onto the closest matching
# `profiles/catalog.py` quality profile -- needed because retrofit search
# has to hand a real, existing profile_id to `improve_quality`/
# `score_candidate`, and those two vocabularies were never unified.
# BATTLE_CARRIER (a hybrid carrier/artillery axis) has no dedicated
# profile of its own; CARRIER_SUPPORT is the closest real intent, same as
# CARRIER's own mapping. Explicit and documented, not inferred silently.
_ROLE_TO_PROFILE = {
    "LINE_ARTILLERY": "LINE_ARTILLERY",
    "LINE_BRAWLER": "LINE_BRAWLER",
    "MISSILE_SUPPORT": "MISSILE_SUPPORT",
    "CARRIER": "CARRIER_SUPPORT",
    "BATTLE_CARRIER": "CARRIER_SUPPORT",
}

_ROLE_TO_BUILD_IDS = {
    "LINE_BRAWLER": ("TANK", "LINE_ANCHOR", "FINISHER"),
    "LINE_ARTILLERY": ("ARTILLERY",),
    "MISSILE_SUPPORT": ("MISSILE_SUPPORT", "PD_ESCORT"),
    "CARRIER": ("CARRIER_SUPPORT", "BATTLECARRIER"),
    "BATTLE_CARRIER": ("BATTLECARRIER", "CARRIER_SUPPORT"),
}


def _build_for_gap(hull_id: str, role: str, registry: Registry, heuristic_set: str) -> BuildArchetypeProfile | None:
    if "build_archetype_viable_min_compatibility" not in get_heuristic_set(heuristic_set).values:
        return None
    hull = registry.hulls.by_id[hull_id]
    preferred = set(_ROLE_TO_BUILD_IDS.get(role, ()))
    builds = infer_build_archetypes(hull, registry, heuristic_set)
    candidates = [build for build in builds if build.build_id in preferred] or list(builds)
    return candidates[0] if candidates else None


def _rank_build_candidates_for_role(
    role: str, resolved_hulls: list, registry: Registry, heuristic_set: str,
    knowledge_pack: ResolvedKnowledgePack | None = None, faction_id: str | None = None,
    include_experimental_builds: bool = True, campaign_stage: str | None = None,
) -> list[tuple[float, str, BuildArchetypeProfile]]:
    """Rank independently viable ``Hull + BuildArchetype`` solutions."""
    ranked: list[tuple[float, str, BuildArchetypeProfile]] = []
    preferred = set(_ROLE_TO_BUILD_IDS.get(role, ()))
    values = get_heuristic_set(heuristic_set).values
    progression_ids = set(progression_hull_ids(knowledge_pack, faction_id or "", campaign_stage))
    progression_confidence = progression_guidance_confidence(knowledge_pack, faction_id or "", campaign_stage) or 0.0
    for hull in resolved_hulls:
        capability = classify_hull(hull).role_compatibility.get(role, 0.0)
        if capability <= 0.0:
            continue
        for build in infer_build_archetypes(hull, registry, heuristic_set):
            if preferred and build.build_id not in preferred:
                continue
            if not include_experimental_builds and build.maturity == "EXPERIMENTAL":
                continue
            # The role capability remains the primary signal; build
            # compatibility makes two fits on the same hull independently
            # rankable rather than collapsing them to one hull identity.
            preference = build_archetype_preference(knowledge_pack, faction_id or "", build.build_id)
            bias = 1.0
            if preference is not None:
                preferred_value, guidance_confidence = preference
                bias += (preferred_value - 0.5) * values["knowledge_build_archetype_preference_weight"] * guidance_confidence
            # Stage guidance is only a small, freshness-adjusted advisory
            # tie-breaker. It cannot introduce a hull, build, or role that
            # the mechanical inference did not already admit.
            if hull.id in progression_ids and "knowledge_progression_preference_weight" in values:
                bias += values["knowledge_progression_preference_weight"] * progression_confidence
            ranked.append((round(capability * build.compatibility * bias, 6), hull.id, build))
    return sorted(ranked, key=lambda item: (-item[0], item[1], item[2].build_id))


def _build_similarity(
    candidate: tuple[float, str, BuildArchetypeProfile],
    selected: tuple[float, str, BuildArchetypeProfile],
    registry: Registry | None,
) -> float:
    """Deterministic within-/cross-hull build similarity from stored inference.

    This is deliberately posture- and evidence-based, rather than a
    hand-authored hull-family label.  A different build id is not by itself
    proof of useful variety.
    """
    _, candidate_hull_id, candidate_build = candidate
    _, selected_hull_id, selected_build = selected
    posture_matches = sum((
        candidate_build.tactical_style == selected_build.tactical_style,
        candidate_build.target_range == selected_build.target_range,
        candidate_build.flux_posture == selected_build.flux_posture,
        candidate_build.survivability_posture == selected_build.survivability_posture,
    )) / 4.0
    priority_similarity = _jaccard(set(candidate_build.equipment_priorities), set(selected_build.equipment_priorities))
    mechanical_similarity = 0.0
    if registry is not None:
        candidate_mechanical = infer_mechanical_archetypes(registry.hulls.by_id[candidate_hull_id], registry)
        selected_mechanical = infer_mechanical_archetypes(registry.hulls.by_id[selected_hull_id], registry)
        candidate_roles = {name for name, score in candidate_mechanical.compatibility_scores.items() if score >= 0.20}
        selected_roles = {name for name, score in selected_mechanical.compatibility_scores.items() if score >= 0.20}
        mechanical_similarity = _jaccard(candidate_roles, selected_roles)
    return round(.40 * posture_matches + .30 * priority_similarity + .30 * mechanical_similarity, 6)


def _diverse_build_shortlist(ranked: list[tuple[float, str, BuildArchetypeProfile]], count: int, heuristic_set: str, registry: Registry | None = None) -> list[tuple[float, str, BuildArchetypeProfile, str]]:
    if not ranked:
        return []
    values = get_heuristic_set(heuristic_set).values
    selected = [(ranked[0][0], ranked[0][1], ranked[0][2], "Highest Hull + BuildArchetype recommendation score.")]
    remaining = ranked[1:]
    while remaining and len(selected) < count:
        best_score = ranked[0][0]
        competitive = [item for item in remaining if item[0] >= best_score * (1.0 - values["recommendation_diversity_material_score_tolerance"])]
        pool = competitive or remaining
        similarities = {
            (item[1], item[2].build_id): max((_build_similarity(item, prior[:3], registry) for prior in selected), default=0.0)
            for item in pool
        }
        choice = max(pool, key=lambda item: (
            1.0 - similarities[(item[1], item[2].build_id)], item[0], item[1], item[2].build_id,
        ))
        similarity = similarities[(choice[1], choice[2].build_id)]
        reason = ("Selected after score ranking as a materially competitive mechanically and tactically distinct Hull + BuildArchetype solution "
                  f"(similarity={similarity:.3f})." if choice in competitive else
                  "Selected by Hull + BuildArchetype recommendation score; no remaining score-competitive alternative was available for diversity.")
        selected.append((choice[0], choice[1], choice[2], reason))
        remaining.remove(choice)
    return selected


@dataclass(frozen=True)
class RetrofitRecommendation:
    role: str
    hull_id: str
    variant_id: str  # the real, existing variant a genuine Refit Assistant pass was run against
    capability_score: float  # structural (classify_hull); unchanged by refit, same figure the native leg reports
    role_match_before: float  # this real variant's current role_match component (score_candidate)
    role_match_after: float  # role_match after generation/refit.py::improve_quality's IMPROVE_ROLE_MATCH search
    quality_gain: float
    changes: int
    change_cost: float
    rank: int
    confidence: float = 1.0  # legal, evaluated real-variant evidence; source coverage is folded in by caller
    archetype_scores: dict[str, float] = field(default_factory=dict)
    archetype_evidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diversity_reason: str | None = None
    build_archetype_id: str | None = None
    build_archetype_label: str | None = None
    build_compatibility: float | None = None
    build_confidence: float | None = None
    build_maturity: str | None = None
    recommendation_score: float | None = None
    incremental_capability_gain: float = 0.0
    retrofit_disruption: float = 0.0
    role_distortion: float = 0.0
    knowledge_template_ids: tuple[str, ...] = ()
    knowledge_guidance_confidence: float | None = None
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


def _variants_for_hull(hull_id: str, registry: Registry) -> list[Variant]:
    return sorted((variant for variant in registry.variants.by_id.values() if variant.hull_id == hull_id), key=lambda variant: variant.id)


@dataclass(frozen=True)
class _RetrofitOpportunity:
    """`_best_retrofit_for_hull`'s real return payload for one hull's most
    improvable real variant.

    `before_score`/`after_score` are copied out of `result` narrowed to
    plain `float`: `_best_retrofit_for_hull`'s own loop below already only
    ever keeps a candidate once both are confirmed real (`continue`d past
    otherwise, so `gain = after - before` is always a real subtraction),
    so every caller downstream needs the guaranteed-non-None value here --
    not `QualityRefitResult`'s own honestly `float | None` field type,
    which correctly stays Optional there because a *different*,
    not-yet-evaluated variant can genuinely have no score at all.
    """

    gain: float
    variant: Variant
    result: QualityRefitResult
    before_score: float
    after_score: float


def _best_retrofit_for_hull(
    hull_id: str, profile_id: str, registry: Registry, faction: Faction, heuristic_set: str, min_gain: float,
) -> _RetrofitOpportunity | None:
    """The most-improvable of this hull's real, existing variants, if any
    genuinely improves by at least `min_gain` under `IMPROVE_ROLE_MATCH`.

    Examines every real variant for this hull (not just one) since which
    named variant is worth retrofitting is itself real information --
    picks the one with the largest real quality_gain, not the first found.
    Returns None if this hull has no real variant, none are legal/
    scoreable starting points, or none genuinely improve -- never
    fabricates a retrofit opportunity that isn't real.
    """
    best: _RetrofitOpportunity | None = None
    for variant in _variants_for_hull(hull_id, registry):
        result = improve_quality(variant, registry, "IMPROVE_ROLE_MATCH", profile_id, heuristic_set, faction=faction)
        if result.before_score is None or result.after_score is None:
            continue
        gain = result.after_score - result.before_score
        if gain < min_gain:
            continue
        if best is None or gain > best.gain:
            best = _RetrofitOpportunity(gain, variant, result, result.before_score, result.after_score)
    return best


def _retrofit_audit_trail(
    faction: Faction, registry: Registry, role: str, heuristic_set: str = "baseline_0.2",
    constraints: RecommendationConstraints | None = None,
) -> tuple[dict[tuple[str, str | None], RecommendationAudit], set[tuple[str, str | None]]]:
    """Every real RETROFIT candidate for `role`: which `(hull_id,
    build_archetype_id_or_None)` pairs were CONSIDERED (examined by a real
    `_best_retrofit_for_hull` search), and, among those, which found a
    genuine `>= refit_min_quality_gain` improvement and how they rank/were
    selected -- built exactly once and read identically by
    `recommend_retrofit_solutions` and `explain_retrofit_candidate`.

    **SVG-018** (`docs/BUGS.md`): under a build-aware heuristic set
    (`baseline_0.4`+, including the CLI's real default `baseline_0.7`),
    `recommend_retrofit_solutions` examines EVERY real `Hull +
    BuildArchetype` combination `_rank_build_candidates_for_role` produces
    (not truncated to the top `gap_recommendation_count` structurally-
    capable hulls the way the legacy branch is). Before this phase,
    `explain_retrofit_candidate` unconditionally used the legacy hull-only,
    truncated candidate pool regardless of heuristic set -- confirmed live
    to both under-report "not considered" for a hull the real build-aware
    search DID examine and recommend, and over-report "recommended" for a
    hull it did not.

    Returns `(audits, considered)`: `audits` is keyed by every candidate
    that found a genuine improvement (retrofit's own real ranking pool);
    `considered` is the broader set of every `(hull_id,
    build_archetype_id_or_None)` pair the search actually examined,
    whether or not a genuine improvement was found for it.
    """
    constraints = constraints or RecommendationConstraints()
    heuristics = get_heuristic_set(heuristic_set).values
    max_recommendations = int(heuristics["gap_recommendation_count"])
    min_gain = heuristics["refit_min_quality_gain"]
    resolved_hulls = _resolved_known_hulls(faction, registry)
    build_aware = "build_archetype_viable_min_compatibility" in heuristics
    audits: dict[tuple[str, str | None], RecommendationAudit] = {}
    considered: set[tuple[str, str | None]] = set()
    if build_aware:
        found_builds: list[tuple[float, str, BuildArchetypeProfile, Variant, QualityRefitResult, float]] = []
        for _structural_score, hull_id, build in _rank_build_candidates_for_role(role, resolved_hulls, registry, heuristic_set, include_experimental_builds=constraints.include_experimental_builds):
            considered.add((hull_id, build.build_id))
            opportunity = _best_retrofit_for_hull(hull_id, profile_id_for_build(build.build_id), registry, faction, heuristic_set, min_gain)
            if opportunity is None:
                continue
            reference_cost = heuristics.get("retrofit_disruption_reference_cost")
            disruption = min(1.0, opportunity.result.total_change_cost / reference_cost) if reference_cost else 0.0
            score = opportunity.after_score * build.compatibility * (1.0 - heuristics.get("retrofit_disruption_penalty_weight", 0.0) * disruption)
            found_builds.append((round(score, 6), hull_id, build, opportunity.variant, opportunity.result, opportunity.gain))
        found_builds.sort(key=lambda item: (-item[0], item[1], item[2].build_id, item[3].id))
        total_candidates = len(found_builds)
        best_score = found_builds[0][0] if found_builds else None
        selected = _diverse_build_shortlist([(score, hull_id, build) for score, hull_id, build, _, _, _ in found_builds], max_recommendations, heuristic_set, registry)
        selection_reasons = {(hull_id, build.build_id): reason for _, hull_id, build, reason in selected}
        selection_order = {(hull_id, build.build_id): index + 1 for index, (_, hull_id, build, _) in enumerate(selected)}
        cutoff_score = min((score for score, _, _, _ in selected), default=None)
        for index, (score, hull_id, build, variant, result, gain) in enumerate(found_builds):
            key = (hull_id, build.build_id)
            audits[key] = RecommendationAudit(
                "RETROFIT", role, hull_id, build.build_id, score, index + 1, total_candidates,
                best_score, cutoff_score, key in selection_reasons, selection_order.get(key),
                selection_reasons.get(key),
                extra={
                    "build": build, "variant": variant, "result": result, "gain": gain,
                    "capability_score": classify_hull(registry.hulls.by_id[hull_id]).role_compatibility.get(role, 0.0),
                },
            )
    else:
        profile_id = _ROLE_TO_PROFILE.get(role)
        ranked_hulls = _rank_candidates_for_role(role, resolved_hulls)[:max_recommendations]
        considered.update((hull_id, None) for _, hull_id in ranked_hulls)
        if profile_id is not None:
            # (capability_score, hull_id, variant, result, gain, after_score) --
            # after_score is carried alongside `result` (rather than read back
            # off it every time) since it is the one already-narrowed-non-None
            # float `_best_retrofit_for_hull` guarantees; `result.after_score`
            # itself stays honestly `float | None` (QualityRefitResult's own
            # field type) for any OTHER variant this trail did not select.
            found: list[tuple[float, str, Variant, QualityRefitResult, float, float]] = []
            for capability_score, hull_id in ranked_hulls:
                opportunity = _best_retrofit_for_hull(hull_id, profile_id, registry, faction, heuristic_set, min_gain)
                if opportunity is None:
                    continue
                found.append((capability_score, hull_id, opportunity.variant, opportunity.result, opportunity.gain, opportunity.after_score))
            found.sort(key=lambda item: (-item[5], item[1], item[2].id))
            total_candidates = len(found)
            best_score = found[0][5] if found else None
            selected_hulls = _diverse_hull_shortlist([(after_score, hull_id) for _, hull_id, _, _, _, after_score in found], registry, max_recommendations, heuristic_set)
            hull_selection_reasons = {hull_id: reason for _, hull_id, reason in selected_hulls}
            hull_selection_order = {hull_id: index + 1 for index, (_, hull_id, _) in enumerate(selected_hulls)}
            cutoff_score = min((score for score, _, _ in selected_hulls), default=None)
            for index, (capability_score, hull_id, variant, result, gain, after_score) in enumerate(found):
                audits[(hull_id, None)] = RecommendationAudit(
                    "RETROFIT", role, hull_id, None, after_score, index + 1, total_candidates,
                    best_score, cutoff_score, hull_id in hull_selection_reasons, hull_selection_order.get(hull_id),
                    hull_selection_reasons.get(hull_id),
                    extra={"build": None, "variant": variant, "result": result, "gain": gain, "capability_score": capability_score},
                )
    return audits, considered


def recommend_retrofit_solutions(
    faction: Faction, registry: Registry, gaps: tuple[CapabilityGap, ...],
    heuristic_set: str = "baseline_0.2", constraints: RecommendationConstraints | None = None,
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> dict[str, tuple[RetrofitRecommendation, ...]]:
    """GAP_RECOMMENDATION_ENGINE.md section 5 / FACTION_KNOWLEDGE_PACKS.md
    section 14's "search native retrofit solutions": among the same
    structurally-capable native hulls `recommend_native_solutions` already
    ranks (bounded to the same top `gap_recommendation_count`, since those
    are the hulls actually being shown), find the real existing variant
    whose current loadout most under-realizes that structural potential,
    and report the genuine quality gain a real Refit Assistant pass
    achieves. A hull with no real variant, or none that improve by at
    least `refit_min_quality_gain`, is simply absent from the result for
    that gap -- never padded with a fabricated recommendation.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    build_aware = "build_archetype_viable_min_compatibility" in heuristics
    constraints = constraints or RecommendationConstraints()

    retrofits: dict[str, tuple[RetrofitRecommendation, ...]] = {}
    for gap in gaps:
        if not build_aware and _ROLE_TO_PROFILE.get(gap.role) is None:
            continue
        audits, _considered = _retrofit_audit_trail(faction, registry, gap.role, heuristic_set, constraints)
        selected_audits = sorted((audit for audit in audits.values() if audit.recommended), key=_require_selection_order)
        retrofits[gap.role] = tuple(
            RetrofitRecommendation(
                gap.role, audit.hull_id, audit.extra["variant"].id, audit.extra["capability_score"],
                audit.extra["result"].before_score, audit.extra["result"].after_score, audit.extra["gain"],
                len(audit.extra["result"].changes), audit.extra["result"].total_change_cost, _require_selection_order(audit),
                confidence=(_recommendation_confidence(gap, audit.extra["build"]) if audit.extra["build"] is not None else gap.evidence_confidence),
                archetype_scores=infer_mechanical_archetypes(registry.hulls.by_id[audit.hull_id], registry).compatibility_scores,
                archetype_evidence=infer_mechanical_archetypes(registry.hulls.by_id[audit.hull_id], registry).evidence_by_archetype,
                diversity_reason=audit.selection_reason,
                build_archetype_id=audit.build_archetype_id,
                build_archetype_label=audit.extra["build"].role if audit.extra["build"] else None,
                build_compatibility=audit.extra["build"].compatibility if audit.extra["build"] else None,
                build_confidence=audit.extra["build"].confidence if audit.extra["build"] else None,
                build_maturity=audit.extra["build"].maturity if audit.extra["build"] else None,
                recommendation_score=audit.own_score,
                incremental_capability_gain=0.0,
                retrofit_disruption=(
                    min(1.0, audit.extra["result"].total_change_cost / heuristics["retrofit_disruption_reference_cost"])
                    if audit.extra["build"] and heuristics.get("retrofit_disruption_reference_cost") else 0.0
                ),
                role_distortion=(round(1.0 - audit.extra["build"].compatibility, 6) if audit.extra["build"] else 0.0),
                knowledge_template_ids=tuple(template_id for template_id, _ in retrofit_template_ids(knowledge_pack, faction.id, audit.hull_id, gap.role)),
                knowledge_guidance_confidence=min((confidence for _, confidence in retrofit_template_ids(knowledge_pack, faction.id, audit.hull_id, gap.role)), default=None),
            )
            for audit in selected_audits
        )
    return retrofits


@dataclass(frozen=True)
class AcquisitionRecommendation:
    role: str
    hull_id: str
    capability_score: float
    affinity: str  # "COMMON" | "FOREIGN" | "UNALIGNED" -- never NATIVE, that's the native leg's job
    owning_faction_ids: tuple[str, ...]
    preference_weight: float  # affinity_preference_<tier>, baseline_0.2 -- the same table adaptive substitution uses
    rank: int
    confidence: float = 1.0  # source coverage plus optional knowledge-pack evidence
    archetype_scores: dict[str, float] = field(default_factory=dict)
    archetype_evidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diversity_reason: str | None = None
    build_archetype_id: str | None = None
    build_archetype_label: str | None = None
    build_compatibility: float | None = None
    build_confidence: float | None = None
    build_maturity: str | None = None
    recommendation_score: float | None = None
    incremental_capability_gain: float = 0.0
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


def _acquisition_audit_trail(
    faction: Faction, registry: Registry, role: str, heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None, constraints: RecommendationConstraints | None = None,
    candidates: list[tuple[float, float, float, str, object]] | None = None,
) -> dict[tuple[str, str | None], RecommendationAudit]:
    """Every real ACQUISITION candidate for `role` (a real, indexed hull
    this faction does not already know, scoring > 0.0 on `role`), ranked
    exactly once, keyed by `(hull_id, build_archetype_id_or_None)`.
    `recommend_acquisition_solutions` (which keeps only `recommended=True`
    entries, ordered by `selection_order`) and `explain_acquisition_candidate`
    (which looks up one hull's entries) both read from this single
    computation.

    **SVG-018** (`docs/BUGS.md`): before this phase,
    `explain_acquisition_candidate` always used a hull-only,
    non-build-aware, non-diversity-selecting ranking regardless of
    heuristic set -- disagreeing with the real build-aware
    `recommend_acquisition_solutions` result under `baseline_0.4`+
    (including the CLI's real default `baseline_0.7`), and, more subtly,
    also disagreeing with the legacy leg's own `_diverse_hull_shortlist`
    selection under `baseline_0.3` (`explain_acquisition_candidate` never
    called it at all, unlike `explain_native_candidate`'s pre-existing
    correct legacy branch). Routing both paths through this shared trail
    fixes both.

    `candidates` lets a caller that already scanned every indexed hull once
    across several roles (`recommend_acquisition_solutions`'s own
    `classify_hull`/affinity pass, gap-independent per hull -- see that
    function's docstring) hand in its already-computed per-role slice
    instead of this function re-scanning the whole registry; omitted
    (`None`), it performs that scan itself for the single `role` requested
    -- the natural, no-worse-than-before cost for a single-role,
    single-hull Why-Not query.
    """
    constraints = constraints or RecommendationConstraints()
    heuristics = get_heuristic_set(heuristic_set).values
    max_recommendations = int(heuristics["gap_recommendation_count"])
    build_aware = "build_archetype_viable_min_compatibility" in heuristics
    if candidates is None:
        candidates = _acquisition_candidates_for_role(faction, registry, role, heuristic_set, knowledge_pack, constraints)

    audits: dict[tuple[str, str | None], RecommendationAudit] = {}
    if build_aware:
        preferred = set(_ROLE_TO_BUILD_IDS.get(role, ()))
        build_candidates: list[tuple[float, float, float, str, object, BuildArchetypeProfile]] = []
        for composite, score, weight, hull_id, affinity in candidates:
            hull = registry.hulls.by_id[hull_id]
            for build in infer_build_archetypes(hull, registry, heuristic_set):
                if preferred and build.build_id not in preferred:
                    continue
                if not constraints.include_experimental_builds and build.maturity == "EXPERIMENTAL":
                    continue
                build_candidates.append((round(composite * build.compatibility, 6), score, weight, hull_id, affinity, build))
        build_candidates.sort(key=lambda item: (-item[0], item[3], item[5].build_id))
        total_candidates = len(build_candidates)
        best_score = build_candidates[0][0] if build_candidates else None
        selected = _diverse_build_shortlist([(composite, hull_id, build) for composite, _, _, hull_id, _, build in build_candidates], max_recommendations, heuristic_set, registry)
        selection_reasons = {(hull_id, build.build_id): reason for _, hull_id, build, reason in selected}
        selection_order = {(hull_id, build.build_id): index + 1 for index, (_, hull_id, build, _) in enumerate(selected)}
        cutoff_score = min((score for score, _, _, _ in selected), default=None)
        for index, (composite, score, weight, hull_id, affinity, build) in enumerate(build_candidates):
            key = (hull_id, build.build_id)
            audits[key] = RecommendationAudit(
                "ACQUISITION", role, hull_id, build.build_id, composite, index + 1, total_candidates,
                best_score, cutoff_score, key in selection_reasons, selection_order.get(key),
                selection_reasons.get(key),
                extra={"build": build, "score": score, "weight": weight, "affinity": affinity},
            )
    else:
        candidates_sorted = sorted(candidates, key=lambda item: (-item[0], item[3]))
        total_candidates = len(candidates_sorted)
        best_score = candidates_sorted[0][0] if candidates_sorted else None
        selected_hulls = _diverse_hull_shortlist([(composite, hull_id) for composite, _, _, hull_id, _ in candidates_sorted], registry, max_recommendations, heuristic_set)
        hull_selection_reasons = {hull_id: reason for _, hull_id, reason in selected_hulls}
        hull_selection_order = {hull_id: index + 1 for index, (_, hull_id, _) in enumerate(selected_hulls)}
        cutoff_score = candidates_sorted[max_recommendations - 1][0] if len(candidates_sorted) >= max_recommendations else None
        for index, (composite, score, weight, hull_id, affinity) in enumerate(candidates_sorted):
            audits[(hull_id, None)] = RecommendationAudit(
                "ACQUISITION", role, hull_id, None, composite, index + 1, total_candidates,
                best_score, cutoff_score, hull_id in hull_selection_reasons, hull_selection_order.get(hull_id),
                hull_selection_reasons.get(hull_id),
                extra={"build": None, "score": score, "weight": weight, "affinity": affinity},
            )
    return audits


def _acquisition_candidates_for_role(
    faction: Faction, registry: Registry, role: str, heuristic_set: str,
    knowledge_pack: ResolvedKnowledgePack | None, constraints: RecommendationConstraints,
) -> list[tuple[float, float, float, str, object]]:
    """Every real, non-native, positive-`role`-scoring hull's composite
    acquisition score/affinity -- the per-hull scan step shared by
    `_acquisition_audit_trail`'s single-role callers
    (`explain_acquisition_candidate`) and `recommend_acquisition_solutions`'s
    own multi-role batched scan (which performs this same scan once across
    every gap's role, for the efficiency reason that function's own
    docstring already names, then hands each role's slice in directly
    rather than calling this a second time)."""
    heuristics = get_heuristic_set(heuristic_set).values
    native_hull_ids = {hull_id for hull_id in faction.known_hulls if hull_id in registry.hulls.by_id}
    candidates: list[tuple[float, float, float, str, object]] = []
    for hull_id, hull in registry.hulls.by_id.items():
        if hull_id in native_hull_ids or not recommendation_eligibility(hull).eligible:
            continue
        score = classify_hull(hull).role_compatibility.get(role, 0.0)
        if score <= 0.0:
            continue
        affinity = classify_equipment_affinity(
            hull_id, "hulls", registry, requesting_faction_id=faction.id,
            knowledge_pack=knowledge_pack,
        )
        if not constraints.allow_foreign_hulls and affinity.affinity == "FOREIGN":
            continue
        weight = heuristics[f"affinity_preference_{affinity.affinity.lower()}"]
        candidates.append((score * weight, score, weight, hull_id, affinity))
    return candidates


def recommend_acquisition_solutions(
    faction: Faction,
    registry: Registry,
    gaps: tuple[CapabilityGap, ...],
    heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
    constraints: RecommendationConstraints | None = None,
) -> dict[str, tuple[AcquisitionRecommendation, ...]]:
    """GAP_RECOMMENDATION_ENGINE.md section 7: rank real, indexed hulls this
    faction does NOT already know (COMMON/FOREIGN/UNALIGNED per
    `analysis/equipment_affinity.py`, extended to hulls) by
    `capability_score * affinity_preference_<tier>` -- directly
    implementing FACTION_KNOWLEDGE_PACKS.md section 9's "foreign
    acquisitions normally need a clear capability advantage" using the
    already-registered preference table, not a new doctrine-strictness
    mechanism (LOOSE/BALANCED/STRICT remain unimplemented).

    Single pass over every real indexed hull (not per-gap) since both
    `classify_hull` and hull affinity are gap-independent -- avoids
    redundant classification work across gaps; each role's slice is then
    handed to `_acquisition_audit_trail` so the ranking/selection
    computation itself still goes through exactly one shared construction
    path, identical to what `explain_acquisition_candidate` uses.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    constraints = constraints or RecommendationConstraints()
    native_hull_ids = {hull_id for hull_id in faction.known_hulls if hull_id in registry.hulls.by_id}
    gap_roles = {gap.role for gap in gaps}

    per_role_candidates: dict[str, list[tuple[float, float, float, str, object]]] = {role: [] for role in gap_roles}
    for hull_id, hull in registry.hulls.by_id.items():
        if hull_id in native_hull_ids or not recommendation_eligibility(hull).eligible:
            continue
        role_scores = classify_hull(hull).role_compatibility
        relevant = {role: role_scores.get(role, 0.0) for role in gap_roles if role_scores.get(role, 0.0) > 0.0}
        if not relevant:
            continue
        affinity = classify_equipment_affinity(
            hull_id, "hulls", registry, requesting_faction_id=faction.id,
            knowledge_pack=knowledge_pack,
        )
        if not constraints.allow_foreign_hulls and affinity.affinity == "FOREIGN":
            continue
        weight = heuristics[f"affinity_preference_{affinity.affinity.lower()}"]
        for role, score in relevant.items():
            per_role_candidates[role].append((score * weight, score, weight, hull_id, affinity))

    acquisitions: dict[str, tuple[AcquisitionRecommendation, ...]] = {}
    for gap in gaps:
        audits = _acquisition_audit_trail(faction, registry, gap.role, heuristic_set, knowledge_pack, constraints, per_role_candidates.get(gap.role, []))
        selected_audits = sorted((audit for audit in audits.values() if audit.recommended), key=_require_selection_order)
        acquisitions[gap.role] = tuple(
            AcquisitionRecommendation(
                gap.role, audit.hull_id, audit.extra["score"], audit.extra["affinity"].affinity, audit.extra["affinity"].owning_faction_ids,
                audit.extra["weight"], _require_selection_order(audit),
                # The faction's resolved-hull coverage is the universal
                # evidence limit.  Pack approval adds no invented certainty:
                # it can only reduce confidence when its freshness/evidence
                # says less than one.
                confidence=(
                    _recommendation_confidence(gap, audit.extra["build"], audit.extra["affinity"].guidance_confidence if audit.extra["affinity"].guidance_confidence is not None else 1.0)
                    if audit.extra["build"] is not None
                    else gap.evidence_confidence * (audit.extra["affinity"].guidance_confidence if audit.extra["affinity"].guidance_confidence is not None else 1.0)
                ),
                archetype_scores=infer_mechanical_archetypes(registry.hulls.by_id[audit.hull_id], registry).compatibility_scores,
                archetype_evidence=infer_mechanical_archetypes(registry.hulls.by_id[audit.hull_id], registry).evidence_by_archetype,
                diversity_reason=audit.selection_reason,
                build_archetype_id=audit.build_archetype_id,
                build_archetype_label=audit.extra["build"].role if audit.extra["build"] else None,
                build_compatibility=audit.extra["build"].compatibility if audit.extra["build"] else None,
                build_confidence=audit.extra["build"].confidence if audit.extra["build"] else None,
                build_maturity=audit.extra["build"].maturity if audit.extra["build"] else None,
                recommendation_score=audit.own_score,
                incremental_capability_gain=max(0.0, audit.extra["score"] - gap.faction_existing_coverage),
            )
            for audit in selected_audits
        )
    return acquisitions


def recommend_gap_solutions(
    faction: Faction,
    registry: Registry,
    heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
    constraints: RecommendationConstraints | None = None,
) -> GapRecommendationResult:
    """All 3 implemented legs combined: `recommend_native_solutions`'s
    result, extended with `retrofit_recommendations`/
    `acquisition_recommendations` and a real `fully_unaddressed_gaps`
    (GAP_RECOMMENDATION_ENGINE.md section 15's full-maturity definition:
    a gap with no solution across native, retrofit, AND acquisition --
    not just no native solution, which `unaddressed_gaps` alone still
    means, unchanged, since that is itself real and distinct information
    ("this faction's own hulls can't cover this at all")).
    """
    constraints = constraints or RecommendationConstraints()
    native_result = recommend_native_solutions(faction, registry, heuristic_set, knowledge_pack, constraints)
    retrofit = recommend_retrofit_solutions(faction, registry, native_result.gaps, heuristic_set, constraints, knowledge_pack)
    acquisition = recommend_acquisition_solutions(faction, registry, native_result.gaps, heuristic_set, knowledge_pack, constraints)
    fully_unaddressed = tuple(
        role for role in native_result.unaddressed_gaps
        if not retrofit.get(role) and not acquisition.get(role)
    )
    return dataclass_replace(
        native_result,
        retrofit_recommendations=retrofit,
        acquisition_recommendations=acquisition,
        fully_unaddressed_gaps=fully_unaddressed,
        officer_guidance=officer_guidance(knowledge_pack, faction.id),
    )


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


@dataclass(frozen=True)
class WhyNotExplanation:
    role: str
    hull_id: str
    resolved: bool  # is hull_id even a real, resolved known hull of this faction?
    capability_score: float | None  # this hull's real role_compatibility score, if resolved
    rank: int | None  # 1-based rank among ALL positive-scoring known hulls for this role (not just the top N recommended)
    total_candidates: int  # how many known hulls scored above zero for this role at all
    recommended: bool  # was this hull actually inside the top gap_recommendation_count?
    best_score: float | None  # the #1-ranked hull's score, for comparison
    reason: str
    archetype_scores: dict[str, float] = field(default_factory=dict)
    archetype_evidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diversity_reason: str | None = None
    # ROADMAP.md Phase 32: the identical confidence
    # `recommend_native_solutions` computed for this exact candidate (via
    # the same `RecommendationAudit` entry's `extra["build"]`), not a
    # second, potentially-drifting computation. `None` only when this hull
    # was never part of the real ranked candidate pool for `role` at all
    # (see `resolved`/`recommended`).
    confidence: float | None = None


def explain_native_candidate(faction: Faction, registry: Registry, role: str, hull_id: str, heuristic_set: str = "baseline_0.2") -> WhyNotExplanation:
    """Answer "why wasn't <hull_id> recommended for <role>?" using
    `_native_audit_trail` -- the exact same audit `recommend_native_solutions`
    itself builds and reads (ROADMAP.md Phase 32), so this can never
    re-derive a separate, potentially-drifting explanation mechanism.

    `recommend_native_solutions` itself branches on whether the heuristic
    set is build-aware (`baseline_0.4`+, including the CLI's real default
    `baseline_0.7`): it ranks `Hull + BuildArchetype` combinations via
    `_rank_build_candidates_for_role`/`_diverse_build_shortlist`, not the
    legacy hull-only `_rank_candidates_for_role`/`_diverse_hull_shortlist`
    pair -- and `_diverse_build_shortlist` always performs similarity-based
    diversity selection (unlike the legacy pair, which only does so under
    `baseline_0.3`), so a build-aware shortlist is never simply "top N by
    raw score." `_native_audit_trail` branches the exact same way -- found
    live against the real 148-mod install: without this branch, `svg
    why-not xlu MISSILE_SUPPORT xlu_chrominus` (no `--build-archetype`)
    reported "Recommended: ranked 2 of 13" under `baseline_0.7`, while the
    real `svg recommend xlu` result for that exact role never lists
    `xlu_chrominus` at all (its true native shortlist is `xlu_calc`,
    `xlu_wolfsteel`, `xlu_oxide`) -- exactly the "second inference
    mechanism that could disagree with the actual recommendations" this
    docstring says doesn't exist.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    max_recommendations = int(heuristics["gap_recommendation_count"])
    resolved_hulls = _resolved_known_hulls(faction, registry)
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None or hull_id not in {h.id for h in resolved_hulls}:
        return WhyNotExplanation(role, hull_id, False, None, None, 0, False, None, "Not a resolved known hull of this faction.")
    own_score = classify_hull(hull).role_compatibility.get(role, 0.0)
    build_aware = "build_archetype_viable_min_compatibility" in heuristics
    audits = _native_audit_trail(faction, registry, role, heuristic_set)
    if build_aware:
        rank, total_candidates, best_score, recommended, selection_reason, cutoff_score = _native_hull_level_lookup(audits, hull_id)
    else:
        audit = audits.get((hull_id, None))
        total_candidates = len(audits)
        best_score = next((item.best_score for item in audits.values()), None)
        rank = audit.rank if audit else None
        recommended = audit.recommended if audit else False
        selection_reason = audit.selection_reason if audit else None
        cutoff_score = audit.cutoff_score if audit else None
    if own_score <= 0.0:
        return WhyNotExplanation(role, hull_id, True, own_score, None, total_candidates, False, best_score, f"Scores 0.0 on {role} -- no real evidence of this capability at all.")
    # ROADMAP.md Phase 32: identical confidence to the real ranking's own
    # `_recommendation_confidence(gap, audit.extra["build"])` for this exact
    # candidate -- `hull_audits`/`best_hull_audit` is the same "hull's own
    # best-ranked real audit entry" `_native_hull_level_lookup` reads for
    # rank/recommended, so its `extra["build"]` is the identical build
    # `recommend_native_solutions` used (or `None` in non-build-aware mode,
    # matching that branch's own `extra["build"]` exactly).
    hull_audits = [item for item in audits.values() if item.hull_id == hull_id]
    best_hull_audit = min(hull_audits, key=lambda item: item.rank) if hull_audits else None
    confidence = None
    if best_hull_audit is not None:
        profile = analyze_faction_capability(faction, registry, heuristic_set)
        evidence_confidence, vector_confidence = _capability_gap_confidence_inputs(profile, role, heuristic_set)
        confidence = _recommendation_confidence_from_values(evidence_confidence, vector_confidence, best_hull_audit.extra["build"])
    archetype = infer_mechanical_archetypes(hull, registry)
    # Diversity phrasing applies whenever the actual selection could deviate
    # from a pure top-N-by-score cutoff: build-aware ranking always uses
    # `_diverse_build_shortlist`'s similarity-based selection; the legacy
    # hull-only path only does under `baseline_0.3`.
    diversity_selection = build_aware or heuristic_set == "baseline_0.3"
    if recommended:
        reason = f"Recommended: ranked {rank} of {total_candidates} real known hulls scoring above zero on {role}. {selection_reason}"
    elif diversity_selection:
        cutoff = cutoff_score if cutoff_score is not None else 0.0
        reason = f"Not selected after score-first diversity: ranked {rank} of {total_candidates}; score {own_score:.3f} versus selected cutoff {cutoff:.3f}. Its inferred functional-role/archetype evidence was not a more competitive distinct solution."
    else:
        gap_to_cutoff = (cutoff_score if cutoff_score is not None else own_score) - own_score
        reason = f"Ranked {rank} of {total_candidates}, {gap_to_cutoff:.3f} below the lowest-scoring hull that was recommended (top {max_recommendations} shown)."
    return WhyNotExplanation(role, hull_id, True, own_score, rank, total_candidates, recommended, best_score, reason,
                             archetype.compatibility_scores, archetype.evidence_by_archetype,
                             selection_reason, confidence)


@dataclass(frozen=True)
class RetrofitWhyNotExplanation:
    role: str
    hull_id: str
    considered: bool  # was this hull among the native leg's top-ranked structurally-capable candidates retrofit search even examines?
    has_real_variant: bool | None  # None only when not considered
    variant_id: str | None  # the specific real variant a retrofit pass would improve, if any
    role_match_before: float | None
    role_match_after: float | None
    quality_gain: float | None
    recommended: bool
    reason: str
    recommendation_score: float | None = None
    rank: int | None = None
    scoring_components: dict[str, float] = field(default_factory=dict)
    # ROADMAP.md Phase 32: identical to `RetrofitRecommendation.confidence`
    # for this exact candidate when one was real (see
    # `explain_retrofit_candidate`); `None` when this hull was never part
    # of the real retrofit candidate pool at all.
    confidence: float | None = None


def explain_retrofit_candidate(faction: Faction, registry: Registry, role: str, hull_id: str, heuristic_set: str = "baseline_0.2") -> RetrofitWhyNotExplanation:
    """Answer "why wasn't <hull_id> recommended for retrofit on <role>?"
    using `_retrofit_audit_trail` -- the exact same audit
    `recommend_retrofit_solutions` itself builds and reads (ROADMAP.md
    Phase 32), so this can never re-derive a separate, potentially-
    drifting explanation mechanism. `_retrofit_audit_trail` branches on
    heuristic-set build-awareness the same way `recommend_retrofit_solutions`
    does -- fixing SVG-018 (`docs/BUGS.md`), where this function previously
    always used the legacy hull-only, native-top-N-truncated candidate
    pool regardless of heuristic set, disagreeing with the real
    `baseline_0.4`+ build-aware search.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    min_gain = heuristics["refit_min_quality_gain"]
    build_aware = "build_archetype_viable_min_compatibility" in heuristics
    audits, considered = _retrofit_audit_trail(faction, registry, role, heuristic_set)
    hull_considered = any(key[0] == hull_id for key in considered)
    if not hull_considered:
        return RetrofitWhyNotExplanation(role, hull_id, False, None, None, None, None, None, False, "Not among the native leg's top structurally-capable candidates for this role -- retrofit search only examines those (see recommend_native_solutions).")
    if not build_aware and _ROLE_TO_PROFILE.get(role) is None:
        return RetrofitWhyNotExplanation(role, hull_id, True, None, None, None, None, None, False, f"No quality-profile mapping exists for capability axis {role!r} (see _ROLE_TO_PROFILE).")
    hull_audits = [audit for audit in audits.values() if audit.hull_id == hull_id]
    if not hull_audits:
        variants = _variants_for_hull(hull_id, registry)
        if not variants:
            return RetrofitWhyNotExplanation(role, hull_id, True, False, None, None, None, None, False, "This hull has no real, indexed variant to retrofit.")
        return RetrofitWhyNotExplanation(role, hull_id, True, True, None, None, None, None, False, f"This hull has {len(variants)} real variant(s), but none improve role_match by at least {min_gain:.2f} via IMPROVE_ROLE_MATCH -- already close to its own structural potential, or not a legal/scoreable starting point.")
    # Hull-level best: the highest-ranked of this hull's own real, genuine
    # retrofit opportunities (exactly one in legacy/non-build-aware mode;
    # build-aware mode can have several distinct builds for the same hull,
    # so the best-ranked one represents this hull-level -- not
    # build-specific -- explanation; see explain_build_candidate for a
    # build-specific one).
    best_audit = min(hull_audits, key=lambda audit: audit.rank)
    recommended = any(audit.recommended for audit in hull_audits)
    rank, total_candidates = best_audit.rank, best_audit.total_candidates
    result, variant, gain = best_audit.extra["result"], best_audit.extra["variant"], best_audit.extra["gain"]
    if recommended:
        reason = f"Recommended: retrofitting {variant.id!r} improves role_match from {result.before_score:.1f} to {result.after_score:.1f} (rank {rank} of {total_candidates} real retrofit opportunities found for this gap)."
    else:
        cutoff = best_audit.cutoff_score
        cutoff_text = f"; score {best_audit.own_score:.6f} versus selected cutoff {cutoff:.6f}" if cutoff is not None else ""
        reason = (
            f"Ranked {rank} of {total_candidates} real retrofit opportunities for this gap (retrofitting "
            f"{variant.id!r} improves role_match from {result.before_score:.1f} to {result.after_score:.1f}), "
            f"but did not clear the recommendation cutoff{cutoff_text}."
        )
    # ROADMAP.md Phase 32: identical confidence to the real ranking's own
    # `_recommendation_confidence(gap, audit.extra["build"])` (build-aware)
    # or `gap.evidence_confidence` (legacy) for this exact candidate --
    # `best_audit` is the same real audit entry `recommend_retrofit_solutions`
    # itself would have selected/ranked for this hull.
    profile = analyze_faction_capability(faction, registry, heuristic_set)
    evidence_confidence, vector_confidence = _capability_gap_confidence_inputs(profile, role, heuristic_set)
    if best_audit.extra["build"] is not None:
        confidence = _recommendation_confidence_from_values(evidence_confidence, vector_confidence, best_audit.extra["build"])
    else:
        confidence = evidence_confidence
    return RetrofitWhyNotExplanation(
        role, hull_id, True, True, variant.id, result.before_score, result.after_score, gain, recommended, reason,
        best_audit.own_score, rank,
        {"quality_before": result.before_score, "quality_after": result.after_score, "quality_gain": gain,
         "change_cost": result.total_change_cost},
        confidence,
    )


@dataclass(frozen=True)
class AcquisitionWhyNotExplanation:
    role: str
    hull_id: str
    resolved: bool  # is hull_id even a real, indexed hull?
    is_native: bool  # already known by this faction -- acquisition doesn't apply, see native/retrofit legs instead
    capability_score: float | None
    affinity: str | None
    rank: int | None
    total_candidates: int
    recommended: bool
    reason: str
    recommendation_score: float | None = None
    preference_weight: float | None = None
    scoring_components: dict[str, float] = field(default_factory=dict)
    # ROADMAP.md Phase 32: identical to `AcquisitionRecommendation.confidence`
    # for this exact candidate when one was real (see
    # `explain_acquisition_candidate`); `None` when this hull was never part
    # of the real acquisition candidate pool at all.
    confidence: float | None = None


def explain_acquisition_candidate(
    faction: Faction,
    registry: Registry,
    role: str,
    hull_id: str,
    heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> AcquisitionWhyNotExplanation:
    """Answer "why wasn't <hull_id> recommended for acquisition on <role>?"
    using `_acquisition_audit_trail` -- the exact same audit
    `recommend_acquisition_solutions` itself builds and reads (ROADMAP.md
    Phase 32), so this can never re-derive a separate, potentially-
    drifting explanation mechanism. See `_acquisition_audit_trail`'s own
    docstring for SVG-018 (`docs/BUGS.md`): this function previously
    always used a hull-only, non-build-aware, non-diversity-selecting
    ranking regardless of heuristic set.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    max_recommendations = int(heuristics["gap_recommendation_count"])
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None:
        return AcquisitionWhyNotExplanation(role, hull_id, False, False, None, None, None, 0, False, "Not a real, indexed hull.")
    native_hull_ids = {known_id for known_id in faction.known_hulls if known_id in registry.hulls.by_id}
    if hull_id in native_hull_ids:
        return AcquisitionWhyNotExplanation(role, hull_id, True, True, None, None, None, 0, False, "This hull is already known natively by this faction -- see the native/retrofit legs, not acquisition.")
    own_score = classify_hull(hull).role_compatibility.get(role, 0.0)
    if own_score <= 0.0:
        return AcquisitionWhyNotExplanation(role, hull_id, True, False, own_score, None, None, 0, False, f"Scores 0.0 on {role} -- no real evidence of this capability at all.")
    audits = _acquisition_audit_trail(faction, registry, role, heuristic_set, knowledge_pack)
    hull_audits = [audit for audit in audits.values() if audit.hull_id == hull_id]
    if not hull_audits:
        # Own structural score is positive, but no mechanically viable
        # BuildArchetype exists on this hull for this role under a
        # build-aware heuristic set -- real, but distinct from "ranked
        # last": the hull never entered the real candidate pool at all.
        return AcquisitionWhyNotExplanation(role, hull_id, True, False, own_score, None, None, 0, False, f"No mechanically viable BuildArchetype exists on this hull for {role} under this heuristic set.")
    # Hull-level best: the highest-ranked of this hull's own real
    # acquisition candidacies -- exactly one in legacy/non-build-aware
    # mode; build-aware mode can have several distinct builds for the
    # same hull.
    best_audit = min(hull_audits, key=lambda audit: audit.rank)
    rank, total_candidates = best_audit.rank, best_audit.total_candidates
    own_affinity, own_composite = best_audit.extra["affinity"].affinity, best_audit.own_score
    preference_weight = best_audit.extra["weight"]
    recommended = any(audit.recommended for audit in hull_audits)
    if recommended:
        reason = f"Recommended: ranked {rank} of {total_candidates} real non-native candidates scoring above zero on {role} ({own_affinity.lower()} affinity)."
    else:
        cutoff = best_audit.cutoff_score
        gap_to_cutoff = (cutoff - own_composite) if cutoff is not None else 0.0
        reason = f"Ranked {rank} of {total_candidates}, {gap_to_cutoff:.3f} below the lowest-ranked hull that was recommended (top {max_recommendations} shown)."
    # ROADMAP.md Phase 32: identical confidence to the real ranking's own
    # `_recommendation_confidence(gap, audit.extra["build"], guidance_confidence)`
    # (build-aware) or `gap.evidence_confidence * guidance_confidence`
    # (legacy) for this exact candidate -- `best_audit` is the same real
    # audit entry `recommend_acquisition_solutions` itself would have
    # selected/ranked for this hull, so its `extra["affinity"]` carries the
    # identical pack-approval guidance_confidence too.
    profile = analyze_faction_capability(faction, registry, heuristic_set)
    evidence_confidence, vector_confidence = _capability_gap_confidence_inputs(profile, role, heuristic_set)
    guidance_confidence = best_audit.extra["affinity"].guidance_confidence if best_audit.extra["affinity"].guidance_confidence is not None else 1.0
    if best_audit.extra["build"] is not None:
        confidence = _recommendation_confidence_from_values(evidence_confidence, vector_confidence, best_audit.extra["build"], guidance_confidence)
    else:
        confidence = evidence_confidence * guidance_confidence
    return AcquisitionWhyNotExplanation(
        role, hull_id, True, False, own_score, own_affinity, rank, total_candidates, recommended, reason,
        own_composite, preference_weight,
        {"functional_capability": own_score, "affinity_preference": preference_weight, "recommendation_score": own_composite},
        confidence,
    )


@dataclass(frozen=True)
class CombinedWhyNotExplanation:
    """All 3 implemented legs' answer to "why wasn't <hull_id> recommended
    for <role>?" in one call -- a real caller asking this question wants
    the full picture, not three separate lookups that could silently
    disagree about which leg's ranking is authoritative."""

    native: WhyNotExplanation
    retrofit: RetrofitWhyNotExplanation
    acquisition: AcquisitionWhyNotExplanation


@dataclass(frozen=True)
class BuildWhyNotExplanation:
    """Build-specific counterpart to the legacy hull-level Why-Not result."""

    role: str
    hull_id: str
    build_archetype_id: str
    resolved: bool
    build: BuildArchetypeProfile | None
    recommended_legs: tuple[str, ...]
    reason: str
    recommendation_score: float | None = None
    rank: int | None = None
    selected_cutoff: float | None = None
    scoring_components: dict[str, float] = field(default_factory=dict)
    diversity_evidence: str | None = None
    leg_scoring_components: dict[str, dict[str, float]] = field(default_factory=dict)


def explain_candidate(
    faction: Faction,
    registry: Registry,
    role: str,
    hull_id: str,
    heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> CombinedWhyNotExplanation:
    return CombinedWhyNotExplanation(
        explain_native_candidate(faction, registry, role, hull_id, heuristic_set),
        explain_retrofit_candidate(faction, registry, role, hull_id, heuristic_set),
        explain_acquisition_candidate(faction, registry, role, hull_id, heuristic_set, knowledge_pack),
    )


def explain_build_candidate(
    faction: Faction, registry: Registry, role: str, hull_id: str, build_archetype_id: str,
    heuristic_set: str = "baseline_0.2", knowledge_pack: ResolvedKnowledgePack | None = None,
    campaign_stage: str | None = None,
) -> BuildWhyNotExplanation:
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None:
        return BuildWhyNotExplanation(role, hull_id, build_archetype_id, False, None, (), "Not a real, indexed hull.")
    if "build_archetype_viable_min_compatibility" not in get_heuristic_set(heuristic_set).values:
        return BuildWhyNotExplanation(role, hull_id, build_archetype_id, True, None, (), f"Heuristic set {heuristic_set} predates build-archetype recommendations.")
    build = next((item for item in infer_build_archetypes(hull, registry, heuristic_set) if item.build_id == build_archetype_id), None)
    if build is None:
        return BuildWhyNotExplanation(role, hull_id, build_archetype_id, True, None, (), "This hull has no mechanically supported viable or Experimental path with that build archetype id.")
    constraints = RecommendationConstraints(campaign_stage=campaign_stage)
    result = recommend_gap_solutions(faction, registry, heuristic_set, knowledge_pack, constraints)
    legs = tuple(name for name, recommendations in (
        ("NATIVE", result.native_recommendations.get(role, ())),
        ("RETROFIT", result.retrofit_recommendations.get(role, ())),
        ("ACQUISITION", result.acquisition_recommendations.get(role, ())),
    ) if any(item.hull_id == hull_id and item.build_archetype_id == build_archetype_id for item in recommendations))
    # Read components from the recommendation records themselves.  This is
    # intentionally not a second scoring implementation: selected legs carry
    # the exact values used to rank them.
    leg_components: dict[str, dict[str, float]] = {}
    native = next((item for item in result.native_recommendations.get(role, ()) if item.hull_id == hull_id and item.build_archetype_id == build_archetype_id), None)
    if native is not None:
        leg_components["NATIVE"] = {
            "functional_capability": native.capability_score,
            "build_compatibility": native.build_compatibility or 0.0,
            "recommendation_score": native.recommendation_score or 0.0,
        }
    retrofit = next((item for item in result.retrofit_recommendations.get(role, ()) if item.hull_id == hull_id and item.build_archetype_id == build_archetype_id), None)
    if retrofit is not None:
        leg_components["RETROFIT"] = {
            "quality_before": retrofit.role_match_before,
            "quality_after": retrofit.role_match_after,
            "quality_gain": retrofit.quality_gain,
            "change_cost": retrofit.change_cost,
            "retrofit_disruption": retrofit.retrofit_disruption,
            "role_distortion": retrofit.role_distortion,
            "recommendation_score": retrofit.recommendation_score or 0.0,
        }
    acquisition = next((item for item in result.acquisition_recommendations.get(role, ()) if item.hull_id == hull_id and item.build_archetype_id == build_archetype_id), None)
    if acquisition is not None:
        leg_components["ACQUISITION"] = {
            "functional_capability": acquisition.capability_score,
            "affinity_preference": acquisition.preference_weight,
            "build_compatibility": acquisition.build_compatibility or 0.0,
            "incremental_capability_gain": acquisition.incremental_capability_gain,
            "recommendation_score": acquisition.recommendation_score or 0.0,
        }
    resolved_hulls = _resolved_known_hulls(faction, registry)
    ranked = _rank_build_candidates_for_role(
        role, resolved_hulls, registry, heuristic_set, knowledge_pack, faction.id,
        campaign_stage=campaign_stage,
    )
    own = next((item for item in ranked if item[1] == hull_id and item[2].build_id == build_archetype_id), None)
    if own is None:
        return BuildWhyNotExplanation(
            role, hull_id, build_archetype_id, True, build, legs,
            f"This build is mechanically inferred but has no positive {role} functional-capability score, so it is not eligible for this recommendation leg.",
            scoring_components={"build_compatibility": build.compatibility, "functional_capability": 0.0},
        )
    selected = _diverse_build_shortlist(ranked, int(get_heuristic_set(heuristic_set).values["gap_recommendation_count"]), heuristic_set, registry)
    selected_keys = {(item[1], item[2].build_id): item for item in selected}
    rank = next(index + 1 for index, item in enumerate(ranked) if item[1] == hull_id and item[2].build_id == build_archetype_id)
    cutoff = min((item[0] for item in selected), default=None)
    components = {
        "functional_capability": classify_hull(hull).role_compatibility.get(role, 0.0),
        "build_compatibility": build.compatibility,
        "knowledge_pack_bias": round(own[0] / (classify_hull(hull).role_compatibility.get(role, 0.0) * build.compatibility), 6) if classify_hull(hull).role_compatibility.get(role, 0.0) and build.compatibility else 1.0,
        "recommendation_score": own[0],
    }
    selected_item = selected_keys.get((hull_id, build_archetype_id))
    if legs or selected_item:
        diversity = selected_item[3] if selected_item else None
        reason = f"Recommended as a Hull + BuildArchetype solution in {', '.join(legs) or 'the native ranking'}; rank {rank} of {len(ranked)} at exact score {own[0]:.6f}."
    else:
        diversity = None
        reason = f"Not selected for {role}: rank {rank} of {len(ranked)}, exact score {own[0]:.6f} versus selected cutoff {(cutoff or 0.0):.6f}. Compatibility is {build.compatibility:.3f}, maturity {build.maturity}; score-first mechanical/tactical diversity selected more competitive combinations."
    return BuildWhyNotExplanation(role, hull_id, build_archetype_id, True, build, legs, reason, own[0], rank, cutoff, components, diversity, leg_components)


# --- Scenario-Aware Recommendations (ROADMAP.md Phase 31, Charter -------
# Priority 9) ---------------------------------------------------------------
#
# Extends ranking from `Hull + BuildArchetype` to `Hull + BuildArchetype +
# ScenarioObjective` units, e.g. "this hull is a good RAIDING pick," not
# just "this hull is a good LINE_ARTILLERY pick." Everything below is
# strictly additive: it reads the ALREADY-RANKED, ALREADY-LEGAL
# Native/Retrofit/Acquisition records a `GapRecommendationResult` already
# carries (never recomputes or reorders them) and produces a brand new,
# separately-reported category, every record of which is tagged
# `SCENARIO_RECOMMENDATION_KIND` ("INFERRED_SCENARIO_OPTION") so it can
# never be confused with the mature, direct role-gap evidence the rest of
# this module produces. `recommend_gap_solutions` itself is left completely
# unmodified -- nothing here is wired into its output; a caller who wants
# scenario options calls `recommend_scenario_solutions` explicitly with an
# already-computed `GapRecommendationResult`.
#
# Naming note: `analysis/scenario_objectives.py::ScenarioObjective` is an
# unrelated, earlier-landed concept (which generation-time coverage
# objectives, e.g. LINE_HOLD/BREAKTHROUGH, a single build archetype already
# supports -- a generation-presentation detail). `ScenarioCategory` below is
# a different, new concept (faction-level recommendation scenario, e.g.
# RAIDING/DEFENSE) and deliberately uses a different name to avoid
# colliding with that existing, actively-imported class.

SCENARIO_RECOMMENDATION_KIND = "INFERRED_SCENARIO_OPTION"


class ScenarioCategory(StrEnum):
    """A small, explicitly synthetic set of fleet-deployment scenario intents.

    Checked against real data before inventing this: no parseable Starsector
    hull/variant/faction field in this project's schema records a
    documented "mission role," "deployment points," or comparable in-game
    scenario tag (see `DATA_SCHEMA.md`; the closest real data is the hull
    CSV `hints` column already consumed by `classify_civilian_role`/
    `infer_mechanical_archetypes`, which covers civilian/logistics roles
    only, not combat deployment intent). This set is therefore an explicit,
    honestly-labeled heuristic taxonomy -- never a documented game
    mechanic, never legality, never evidence -- kept deliberately small.
    Every recommendation this taxonomy produces carries
    `SCENARIO_RECOMMENDATION_KIND` so it is structurally impossible to
    mistake for evidence-based output.

    ROADMAP.md Phase 40 (user "Phase 4") extended the original four
    (RAIDING/DEFENSE/ESCORT/PATROL, Phase 31) with nine further categories,
    each backed by a genuinely distinct real signal from
    `analysis/capability_vector.py::CapabilityVector` (real, mostly
    existing-variant-mounted-weapon evidence, distinct from the purely
    structural `MechanicalArchetypeProfile`/`BuildArchetypeProfile` fields
    the original four use exclusively) and/or `HullFeatureVector` fields --
    see `_scenario_fit_score`'s per-branch comments for the exact citation
    per category. Two of the task's eleven suggested categories were
    deliberately NOT added: BREAKTHROUGH (its natural formula -- HE
    burst/armor-breaking plus mobility -- would have reused ANTI_ARMOR's own
    `ARMOR_BREAKING`/`STRIKER` terms at similar weights, producing a
    near-duplicate ranking under a different name, which this phase's own
    instruction explicitly forbids) and ENDURANCE (no real per-hull ammo/
    fight-duration-endurance signal exists in this project's current schema
    distinct from what LINE_HOLDING's `SUSTAINED_PRESSURE` or DEFENSE's
    survivability terms already cover; a formula built only from those same
    inputs would again just be a relabeled duplicate).
    """

    RAIDING = "RAIDING"
    DEFENSE = "DEFENSE"
    ESCORT = "ESCORT"
    PATROL = "PATROL"
    ANTI_ARMOR = "ANTI_ARMOR"
    ANTI_SHIELD = "ANTI_SHIELD"
    LINE_HOLDING = "LINE_HOLDING"
    LONG_RANGE_PRESSURE = "LONG_RANGE_PRESSURE"
    MISSILE_STRIKE = "MISSILE_STRIKE"
    PD_SCREEN = "PD_SCREEN"
    CARRIER_SUPPORT = "CARRIER_SUPPORT"
    PURSUIT = "PURSUIT"
    LOW_COST_REFIT_FRIENDLY = "LOW_COST_REFIT_FRIENDLY"


def _bucket(value: str | None, weights: dict[str, float]) -> float:
    return weights.get(value or "", 0.0)


def _capability_dim(capability: CapabilityVector | None, name: str) -> tuple[float, str]:
    """Real `CapabilityVector` dimension value plus a citable evidence line.

    Returns `(0.0, "...no resolved evidence...")` rather than fabricating a
    value when the dimension has no score (e.g. a weapon-mounted-evidence
    dimension like `ARMOR_BREAKING`/`KINETIC_PRESSURE` for a hull with no
    resolved existing-variant weapons) -- the same honest-absence discipline
    the rest of this module follows.
    """
    if capability is None:
        return 0.0, f"capability_vector unavailable for {name} (no registry/hull context supplied)."
    evidence = capability.dimensions.get(name)
    if evidence is None or evidence.score is None:
        availability = evidence.availability if evidence is not None else "UNKNOWN"
        return 0.0, f"capability_vector[{name}]: no resolved evidence (availability={availability})."
    return evidence.score, f"capability_vector[{name}]: score={evidence.score:.6f}, confidence={evidence.confidence:.3f}, availability={evidence.availability}."


def _op_scale(value: float | None, reference: float = 200.0) -> float:
    # Mirrors `analysis/mechanical_archetypes.py::infer_mechanical_archetypes`'s
    # own `op = _scale(f.ordnance_points, 200.0)` normalization exactly, so
    # this module's OP-based term uses the same reference the rest of the
    # codebase already established rather than inventing a new constant.
    return max(0.0, min(1.0, float(value) / reference)) if value is not None else 0.0


def _scenario_fit_score(
    scenario: ScenarioCategory,
    build: BuildArchetypeProfile,
    mechanical: MechanicalArchetypeProfile,
    capability: CapabilityVector | None = None,
) -> tuple[float, tuple[str, ...]]:
    """A bounded [0.0, 1.0] heuristic scenario-fit strength.

    Every input term is a real, already-computed structural/build/capability
    signal (`MechanicalArchetypeProfile.compatibility_scores`,
    `BuildArchetypeProfile`'s own tactical/range/survivability/flux posture
    fields, and -- for the nine categories added in ROADMAP.md Phase 40 --
    `CapabilityVector` dimensions, which additionally fold in real
    existing-variant mounted-weapon evidence such as damage type and mount
    type) -- nothing here invents a new game fact. `capability` is optional
    and defaults to `None` so the original four categories (RAIDING/
    DEFENSE/ESCORT/PATROL, ROADMAP.md Phase 31), which never reference it,
    are computed byte-identically to before this phase. The *combination
    weights* below are a first-pass, honestly-labeled heuristic overlay
    (the same status as this module's other first-pass weights, e.g.
    `gap_strong_threshold`), never a citable game mechanic, and are never
    consulted by legality or by the mature Native/Retrofit/Acquisition
    ranking this function only reads from.
    """
    scores = mechanical.compatibility_scores
    style = build.tactical_style
    target_range = build.target_range
    survivability = build.survivability_posture
    flux = build.flux_posture
    priorities = set(build.equipment_priorities)
    # Explicitly `tuple[str, ...]`, not the 2-element shape inferred from
    # this literal alone: every scenario branch below appends further
    # evidence lines onto this same name (`evidence = evidence + (...)`,
    # 1 to 2 more strings depending on the category), which is a real,
    # deliberate variable-length accumulation matching this function's
    # `tuple[str, ...]` return type -- not an inconsistent shape.
    evidence: tuple[str, ...] = (
        f"tactical_style={style}; target_range={target_range}; survivability_posture={survivability}; flux_posture={flux}; equipment_priorities={build.equipment_priorities!r}",
        (
            f"mechanical_archetype_scores: STRIKER={scores['STRIKER']:.3f}, SKIRMISHER={scores['SKIRMISHER']:.3f}, "
            f"ARMOR_BRAWLER={scores['ARMOR_BRAWLER']:.3f}, SHIELD_BRAWLER={scores['SHIELD_BRAWLER']:.3f}, "
            f"LINE_SHIP={scores['LINE_SHIP']:.3f}, PD_ESCORT={scores['PD_ESCORT']:.3f}"
        ),
    )
    if scenario == ScenarioCategory.RAIDING:
        # Mobility/strike-oriented, short-range, willing to forgo maximum
        # survivability for the ability to disengage -- a raider that can't
        # leave is just a slow brawler.
        score = (
            0.35 * scores["STRIKER"] + 0.25 * scores["SKIRMISHER"]
            + 0.20 * (1.0 if style == "FLANK_AND_COMMIT" else 0.0)
            + 0.10 * (1.0 if target_range == "SHORT" else 0.0)
            + 0.10 * _bucket(survivability, {"MEDIUM": 1.0, "HIGH": 0.5})
        )
    elif scenario == ScenarioCategory.DEFENSE:
        # Hold-the-line, maximum survivability, conservative flux posture.
        score = (
            0.30 * scores["ARMOR_BRAWLER"] + 0.25 * scores["SHIELD_BRAWLER"]
            + 0.20 * (1.0 if style == "HOLD_LINE" else 0.0)
            + 0.15 * _bucket(survivability, {"MAXIMUM": 1.0, "HIGH": 0.7, "MEDIUM": 0.3})
            + 0.10 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
        )
    elif scenario == ScenarioCategory.ESCORT:
        # Point-defense/screening for allied ships, with enough mobility to
        # reposition alongside whatever it is escorting.
        score = (
            0.40 * scores["PD_ESCORT"] + 0.20 * (1.0 if style == "SCREEN_ALLIES" else 0.0)
            + 0.15 * (1.0 if "PD" in priorities else 0.0) + 0.15 * scores["SKIRMISHER"]
            + 0.10 * (1.0 if target_range in ("SHORT", "MEDIUM") else 0.0)
        )
    elif scenario == ScenarioCategory.PATROL:
        # General-purpose sustained-coverage posture: moderate everything,
        # line-ship/skirmisher qualities rather than a specialist extreme.
        score = (
            0.30 * scores["LINE_SHIP"] + 0.25 * scores["SKIRMISHER"]
            + 0.15 * (1.0 if style in ("STAND_OFF", "HOLD_LINE") else 0.0)
            + 0.15 * (1.0 if target_range == "MEDIUM" else 0.0)
            + 0.15 * _bucket(survivability, {"HIGH": 1.0, "MEDIUM": 0.7, "MAXIMUM": 0.5})
        )
    elif scenario == ScenarioCategory.ANTI_ARMOR:
        # Real evidence: `CapabilityVector.ARMOR_BREAKING`, the fraction of
        # this hull's real existing-variant mounted weapons dealing HE
        # damage (armor's specific counter in Starsector's damage-type
        # system) -- distinct from every original-four term, none of which
        # reference weapon damage type at all. Structural STRIKER/
        # ARMOR_BRAWLER terms reflect the survivability/mobility needed to
        # close to an HE weapon's effective range and stay there.
        armor_breaking_value, armor_breaking_evidence = _capability_dim(capability, "ARMOR_BREAKING")
        score = 0.55 * armor_breaking_value + 0.25 * scores["STRIKER"] + 0.20 * scores["ARMOR_BRAWLER"]
        evidence = evidence + (armor_breaking_evidence,)
    elif scenario == ScenarioCategory.ANTI_SHIELD:
        # Real evidence: `CapabilityVector.KINETIC_PRESSURE`, the real
        # existing-variant mounted-weapon kinetic-damage fraction (shields'
        # specific counter) -- the direct complement of ANTI_ARMOR above,
        # backed by a different real weapon-damage-type fact, not a
        # relabeling of it. LINE_SHIP/conservative-flux terms reflect the
        # sustained fire needed to keep shields down rather than a single
        # burst.
        kinetic_value, kinetic_evidence = _capability_dim(capability, "KINETIC_PRESSURE")
        score = 0.55 * kinetic_value + 0.25 * scores["LINE_SHIP"] + 0.20 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.6})
        evidence = evidence + (kinetic_evidence,)
    elif scenario == ScenarioCategory.LINE_HOLDING:
        # Real evidence: `CapabilityVector.SUSTAINED_PRESSURE` (LINE_SHIP
        # structural compatibility blended with documented flux
        # dissipation) -- an OUTPUT-endurance signal, distinct from
        # DEFENSE's SURVIVABILITY-weighted ARMOR_BRAWLER/SHIELD_BRAWLER
        # terms: a ship can hold a line by out-dissipating incoming flux
        # while dishing out sustained damage even without DEFENSE's own
        # maximum-tankiness profile.
        sustained_value, sustained_evidence = _capability_dim(capability, "SUSTAINED_PRESSURE")
        score = (
            0.50 * sustained_value + 0.25 * (1.0 if style == "HOLD_LINE" else 0.0)
            + 0.15 * scores["LINE_SHIP"]
            + 0.10 * _bucket(survivability, {"HIGH": 1.0, "MAXIMUM": 0.8, "MEDIUM": 0.5})
        )
        evidence = evidence + (sustained_evidence,)
    elif scenario == ScenarioCategory.LONG_RANGE_PRESSURE:
        # Real evidence: `CapabilityVector.LONG_RANGE_PRESSURE` (ARTILLERY
        # structural compatibility blended with the real existing-variant
        # long-range-weapon-band mounted fraction) -- the ARTILLERY
        # mechanical archetype is not referenced by any of the original
        # four categories at all.
        long_range_value, long_range_evidence = _capability_dim(capability, "LONG_RANGE_PRESSURE")
        score = (
            0.50 * long_range_value + 0.20 * (1.0 if style == "STAND_OFF" else 0.0)
            + 0.20 * (1.0 if target_range == "LONG" else 0.0)
            + 0.10 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
        )
        evidence = evidence + (long_range_evidence,)
    elif scenario == ScenarioCategory.MISSILE_STRIKE:
        # Real evidence: `CapabilityVector.MISSILE_PROJECTION` (MISSILE_SUPPORT
        # structural compatibility blended with the real existing-variant
        # MISSILE-mount-type fraction) plus `BURST_STRIKE` (alpha-strike
        # capacity) -- neither is referenced by the original four.
        missile_value, missile_evidence = _capability_dim(capability, "MISSILE_PROJECTION")
        burst_value, burst_evidence = _capability_dim(capability, "BURST_STRIKE")
        score = (
            0.50 * missile_value + 0.20 * (1.0 if style == "SALVO_SUPPORT" else 0.0)
            + 0.15 * (1.0 if "MISSILES" in priorities else 0.0) + 0.15 * burst_value
        )
        evidence = evidence + (missile_evidence, burst_evidence)
    elif scenario == ScenarioCategory.PD_SCREEN:
        # Real evidence: `CapabilityVector.PD_SCREENING` (PD_ESCORT structural
        # compatibility blended with the real existing-variant PD-tagged
        # mounted-weapon fraction) plus `FIGHTER_INTERCEPTION` (fighter-bay
        # interceptor capacity). Deliberately weighted AWAY from ESCORT's own
        # mobility/`SCREEN_ALLIES`-style/short-range terms (a heavy,
        # stationary PD platform holding a formation's flank is a genuinely
        # different real fit than a fast escort matching a convoy's speed),
        # so a hull can rank well for one without ranking well for the other.
        pd_value, pd_evidence = _capability_dim(capability, "PD_SCREENING")
        intercept_value, intercept_evidence = _capability_dim(capability, "FIGHTER_INTERCEPTION")
        score = (
            0.45 * pd_value + 0.25 * intercept_value
            + 0.15 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
            + 0.15 * (1.0 if style == "HOLD_LINE" else 0.0)
        )
        evidence = evidence + (pd_evidence, intercept_evidence)
    elif scenario == ScenarioCategory.CARRIER_SUPPORT:
        # Real evidence: `CapabilityVector.CARRIER_PROJECTION` (the best of
        # LIGHT_CARRIER/HEAVY_CARRIER/BATTLECARRIER structural compatibility)
        # plus `FIGHTER_INTERCEPTION` -- none of the carrier mechanical
        # archetypes are referenced anywhere in the original four categories.
        carrier_value, carrier_evidence = _capability_dim(capability, "CARRIER_PROJECTION")
        intercept_value, intercept_evidence = _capability_dim(capability, "FIGHTER_INTERCEPTION")
        score = 0.55 * carrier_value + 0.25 * intercept_value + 0.20 * (1.0 if style == "STAND_OFF" else 0.0)
        evidence = evidence + (carrier_evidence, intercept_evidence)
    elif scenario == ScenarioCategory.PURSUIT:
        # Real evidence: `CapabilityVector.PURSUIT` and `.MOBILITY`, both of
        # which fold in VERIFIED adapter-derived existing-variant effective
        # max_speed (`analysis/mobility_stats.py`, real applied hullmod
        # effects) when available -- a strictly stronger, independently
        # verified mobility signal than RAIDING's purely qualitative
        # structural/posture check, and RAIDING never reads
        # `CapabilityVector` at all. A hull can rank well for RAIDING
        # (short-range strike posture) without a verified mobility edge, or
        # rank well for PURSUIT (proven speed to run a target down) without
        # RAIDING's short-range/FLANK_AND_COMMIT requirement.
        pursuit_value, pursuit_evidence = _capability_dim(capability, "PURSUIT")
        mobility_value, mobility_evidence = _capability_dim(capability, "MOBILITY")
        score = (
            0.45 * pursuit_value + 0.30 * mobility_value + 0.15 * scores["STRIKER"]
            + 0.10 * (1.0 if target_range in ("MEDIUM", "LONG") else 0.0)
        )
        evidence = evidence + (pursuit_evidence, mobility_evidence)
    else:  # LOW_COST_REFIT_FRIENDLY
        # Real evidence: `HullFeatureVector.ordnance_points` (inverted --
        # lower OP is cheaper to build/supply/refit within budget, using the
        # exact same 200.0 reference `infer_mechanical_archetypes` already
        # normalizes OP against) and `.existing_variant_count` (a hull with
        # more real existing variants has more real starting points a Refit
        # Assistant pass can cheaply improve). This is a purely economic
        # axis -- OP cost and variant availability -- that no other category
        # in this module references at any weight, so it cannot duplicate
        # another category's ranking under a different name.
        op_value = 1.0 - _op_scale(mechanical.feature_vector.ordnance_points)
        variant_availability = min(1.0, mechanical.feature_vector.existing_variant_count / 3.0)
        score = (
            0.50 * op_value + 0.30 * variant_availability
            + 0.20 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
        )
        evidence = evidence + (
            (
                f"ordnance_points={mechanical.feature_vector.ordnance_points!r} (inverted op_value={op_value:.6f}); "
                f"existing_variant_count={mechanical.feature_vector.existing_variant_count!r} (variant_availability={variant_availability:.6f})."
            ),
        )
    return round(max(0.0, min(1.0, score)), 6), evidence


@dataclass(frozen=True)
class ScenarioRecommendation:
    """A heuristic `INFERRED_SCENARIO_OPTION` layered on top of one of the
    three real, evidence-based recommendation legs' own already-ranked
    `Hull + BuildArchetype` candidate. NEVER a replacement for, or dilution
    of, that leg's own `recommendation_score`/`confidence`:
    `base_recommendation_score`/`source_leg` cite exactly which real
    recommendation this option is layered onto, unchanged.
    """

    role: str
    scenario: str  # ScenarioCategory value
    hull_id: str
    build_archetype_id: str
    source_leg: str  # "NATIVE" | "RETROFIT" | "ACQUISITION" -- which real leg's own ranked candidate this reuses
    source_variant_id: str | None  # set only when source_leg == "RETROFIT"
    base_recommendation_score: float | None  # the cited leg's own real, unmodified recommendation_score
    scenario_fit_score: float  # 0.0-1.0 heuristic-only; never evidence, never legality
    scenario_recommendation_score: float  # base_recommendation_score * scenario_fit_score; ranking is local to this (role, scenario) shortlist only, never compared across legs or scenarios
    rank: int
    confidence: float  # bounded by scenario_confidence_cap -- a heuristic overlay is never reported as fully certain
    reason: str
    scenario_fit_evidence: tuple[str, ...] = ()
    kind: str = SCENARIO_RECOMMENDATION_KIND  # always "INFERRED_SCENARIO_OPTION"
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


def recommend_scenario_solutions(
    faction: Faction,
    registry: Registry,
    gap_result: GapRecommendationResult,
    scenario: ScenarioCategory,
    heuristic_set: str = "baseline_0.2",
    roles: tuple[str, ...] | None = None,
) -> dict[str, tuple[ScenarioRecommendation, ...]]:
    """Layer a heuristic scenario-fit overlay on top of `gap_result`'s
    ALREADY-RANKED Native/Retrofit/Acquisition `Hull + BuildArchetype`
    candidates for the given `scenario`.

    This never recomputes or reorders those legs: it reads their stored
    `hull_id`/`build_archetype_id`/`recommendation_score`/`confidence`
    directly (the same "read the stored evidence, don't reinfer"
    discipline `explain_build_candidate` already follows) and only ever
    ADDS a new, separately-reported `INFERRED_SCENARIO_OPTION` category
    alongside them -- `gap_result` itself is untouched. A hull/build pair
    that does not clear `scenario_fit_min_signal` is simply absent from the
    result, never padded in -- the same "no fabricated recommendation"
    discipline `unaddressed_gaps` already follows for the native leg.

    `roles` restricts the roles considered (default: every role appearing
    in any of the three legs of `gap_result`).
    """
    heuristics = get_heuristic_set(heuristic_set).values
    min_signal = heuristics.get("scenario_fit_min_signal", 0.30)
    confidence_cap = heuristics.get("scenario_confidence_cap", 0.75)
    max_recommendations = int(heuristics.get("scenario_recommendation_count", heuristics.get("gap_recommendation_count", 3.0)))

    target_roles = roles if roles is not None else tuple(sorted(
        set(gap_result.native_recommendations) | set(gap_result.retrofit_recommendations) | set(gap_result.acquisition_recommendations)
    ))

    results: dict[str, tuple[ScenarioRecommendation, ...]] = {}
    for role in target_roles:
        candidates: list[tuple[float, str, str, str, str | None, float | None, float, float, tuple[str, ...]]] = []
        seen: set[tuple[str, str, str]] = set()
        for leg_name, leg_items in (
            ("NATIVE", gap_result.native_recommendations.get(role, ())),
            ("RETROFIT", gap_result.retrofit_recommendations.get(role, ())),
            ("ACQUISITION", gap_result.acquisition_recommendations.get(role, ())),
        ):
            for item in leg_items:
                if not item.build_archetype_id:
                    continue  # no BuildArchetype -- nothing for a Hull + BuildArchetype + ScenarioObjective unit to attach to
                key = (item.hull_id, item.build_archetype_id, leg_name)
                if key in seen:
                    continue
                seen.add(key)
                hull = registry.hulls.by_id.get(item.hull_id)
                if hull is None:
                    continue
                build = next((b for b in infer_build_archetypes(hull, registry, heuristic_set) if b.build_id == item.build_archetype_id), None)
                if build is None:
                    continue
                mechanical = infer_mechanical_archetypes(hull, registry)
                capability = infer_hull_capability_vector(hull, registry)
                fit_score, fit_evidence = _scenario_fit_score(scenario, build, mechanical, capability)
                if fit_score < min_signal:
                    continue
                base_score = item.recommendation_score if item.recommendation_score is not None else item.capability_score
                scenario_score = round((base_score or 0.0) * fit_score, 6)
                confidence = round(min(item.confidence, build.confidence, confidence_cap), 3)
                variant_id = getattr(item, "variant_id", None)
                candidates.append((scenario_score, item.hull_id, build.build_id, leg_name, variant_id, base_score, fit_score, confidence, fit_evidence))
        candidates.sort(key=lambda entry: (-entry[0], entry[1], entry[3], entry[2]))
        shortlisted = candidates[:max_recommendations]
        results[role] = tuple(
            ScenarioRecommendation(
                role=role, scenario=scenario.value, hull_id=hull_id, build_archetype_id=build_id,
                source_leg=source_leg, source_variant_id=variant_id,
                base_recommendation_score=base_score, scenario_fit_score=fit_score,
                scenario_recommendation_score=scenario_score, rank=index + 1, confidence=confidence,
                reason=(
                    f"Heuristic scenario-fit overlay (not evidence-based): {scenario.value} fit score {fit_score:.3f} "
                    f"applied to the existing {source_leg} leg's own recommendation_score "
                    f"{(base_score if base_score is not None else 0.0):.6f} for {hull_id!r} ({build_id})."
                ),
                scenario_fit_evidence=fit_evidence,
            )
            for index, (scenario_score, hull_id, build_id, source_leg, variant_id, base_score, fit_score, confidence, fit_evidence) in enumerate(shortlisted)
        )
    return results


def scenario_fits_for_hull(
    faction: Faction,
    registry: Registry,
    gap_result: GapRecommendationResult,
    hull_id: str,
    heuristic_set: str = "baseline_0.2",
    roles: tuple[str, ...] | None = None,
    categories: tuple[ScenarioCategory, ...] | None = None,
) -> dict[str, tuple[ScenarioRecommendation, ...]]:
    """ROADMAP.md Phase 40 ("multiple genuinely different best builds per
    hull"): for one specific hull, every scenario category (default: all of
    `ScenarioCategory`) it has at least one real, shortlisted
    `INFERRED_SCENARIO_OPTION` recommendation for, across the requested
    roles (default: every role appearing in `gap_result`).

    `recommend_scenario_solutions` already supports "multiple best builds
    per hull" naturally: it is parameterized by `scenario`, and each call is
    an independent ranking over the same real Native/Retrofit/Acquisition
    evidence, so the exact same hull can legitimately receive a different
    top `Hull + BuildArchetype` for RAIDING than for DEFENSE -- there was
    never a single forced overall ranking to begin with. What was missing
    was a convenience for a caller that wants "every category this hull is
    a genuine option for" without hand-looping `ScenarioCategory` and
    filtering by `hull_id` itself. This function does exactly that and
    nothing more: it calls the real, unmodified `recommend_scenario_solutions`
    once per category and keeps only that hull's own entries -- it
    introduces no new ranking, scoring, or selection logic, and
    `recommend_scenario_solutions`'s own behavior/signature is completely
    unchanged by this addition.

    Note this reads each category's real, already-shortlisted
    (`scenario_recommendation_count`-capped, diversity-selected) results --
    the same "recommended" convention every other leg in this module uses --
    not every raw candidate merely above `scenario_fit_min_signal` before
    that cap. A hull that clears the signal floor but not the shortlist cap
    for a given (role, scenario) is reported by `explain_scenario_candidate`
    (`considered=True, recommended=False`), not by this function.
    """
    categories = categories or tuple(ScenarioCategory)
    result: dict[str, tuple[ScenarioRecommendation, ...]] = {}
    for scenario in categories:
        by_role = recommend_scenario_solutions(faction, registry, gap_result, scenario, heuristic_set, roles=roles)
        matches = tuple(item for entries in by_role.values() for item in entries if item.hull_id == hull_id)
        if matches:
            result[scenario.value] = matches
    return result


@dataclass(frozen=True)
class ScenarioWhyNotExplanation:
    """Why-Not counterpart for a heuristic `INFERRED_SCENARIO_OPTION`
    recommendation. ALWAYS textually and structurally distinguished from
    `explain_build_candidate`'s evidence-based `BuildWhyNotExplanation`:
    `reason` states plainly that scenario fit is a heuristic overlay, never
    a documented game mechanic or legality/evidence claim, and `underlying`
    carries the real evidence-based Hull + BuildArchetype explanation for
    the same (role, hull_id, build_archetype_id) as a separate, clearly
    labeled field rather than conflating the two.
    """

    role: str
    scenario: str
    hull_id: str
    build_archetype_id: str
    considered: bool  # was this hull/build pair present in ANY of the 3 underlying legs for this role?
    scenario_fit_score: float | None
    recommended: bool
    reason: str
    rank: int | None = None
    total_candidates: int = 0
    underlying: BuildWhyNotExplanation | None = None


def explain_scenario_candidate(
    faction: Faction,
    registry: Registry,
    gap_result: GapRecommendationResult,
    scenario: ScenarioCategory,
    role: str,
    hull_id: str,
    build_archetype_id: str,
    heuristic_set: str = "baseline_0.2",
) -> ScenarioWhyNotExplanation:
    """Answer "why wasn't <hull_id>/<build_archetype_id> given as an
    INFERRED_SCENARIO_OPTION for <scenario> on <role>?" using the exact
    same real ranking `recommend_scenario_solutions` already computes, so
    this cannot silently disagree with it -- the same discipline every
    other Why-Not function in this module follows. Deliberately a SEPARATE
    explanation type from `BuildWhyNotExplanation`: a scenario option is a
    heuristic overlay, never the same kind of claim as a direct
    evidence-based Native/Retrofit/Acquisition Why-Not.
    """
    underlying = explain_build_candidate(faction, registry, role, hull_id, build_archetype_id, heuristic_set)
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None or underlying.build is None:
        return ScenarioWhyNotExplanation(
            role, scenario.value, hull_id, build_archetype_id, False, None, False,
            "This heuristic scenario overlay only ever evaluates hull/build pairs the mechanical inference "
            "already supports; see `underlying` (the direct evidence-based Hull + BuildArchetype Why-Not) for "
            "why this pair is unavailable.",
            underlying=underlying,
        )
    ranked = recommend_scenario_solutions(faction, registry, gap_result, scenario, heuristic_set, roles=(role,))
    entries = ranked.get(role, ())
    matches = [item for item in entries if item.hull_id == hull_id and item.build_archetype_id == build_archetype_id]
    if matches:
        item = matches[0]
        reason = (
            f"Given as a heuristic INFERRED_SCENARIO_OPTION (not evidence-based): rank {item.rank} of "
            f"{len(entries)} scenario-fit candidates for {scenario.value}/{role}, scenario_fit_score={item.scenario_fit_score:.3f}."
        )
        return ScenarioWhyNotExplanation(role, scenario.value, hull_id, build_archetype_id, True, item.scenario_fit_score, True, reason, item.rank, len(entries), underlying)
    mechanical = infer_mechanical_archetypes(hull, registry)
    capability = infer_hull_capability_vector(hull, registry)
    fit_score, _ = _scenario_fit_score(scenario, underlying.build, mechanical, capability)
    heuristics = get_heuristic_set(heuristic_set).values
    min_signal = heuristics.get("scenario_fit_min_signal", 0.30)
    considered = any(
        recommendation.hull_id == hull_id and recommendation.build_archetype_id == build_archetype_id
        for leg in (gap_result.native_recommendations, gap_result.retrofit_recommendations, gap_result.acquisition_recommendations)
        for recommendation in leg.get(role, ())
    )
    if not considered:
        reason = (
            "Not considered for this heuristic scenario overlay: this Hull + BuildArchetype pair does not "
            "appear in any of the real Native/Retrofit/Acquisition recommendation lists for this role -- the "
            "scenario overlay only ever layers on top of those, it never introduces a new candidate."
        )
    elif fit_score < min_signal:
        reason = (
            f"Not given as an INFERRED_SCENARIO_OPTION: heuristic {scenario.value} scenario_fit_score "
            f"{fit_score:.3f} is below the minimum signal threshold {min_signal:.3f} -- a low heuristic fit, "
            "never a legality or evidence claim."
        )
    else:
        reason = (
            f"Not given as an INFERRED_SCENARIO_OPTION: heuristic scenario_fit_score {fit_score:.3f} clears "
            f"the minimum signal threshold but did not rank inside the top {len(entries)} shortlisted for this role/scenario."
        )
    return ScenarioWhyNotExplanation(role, scenario.value, hull_id, build_archetype_id, considered, fit_score, False, reason, None, len(entries), underlying)
