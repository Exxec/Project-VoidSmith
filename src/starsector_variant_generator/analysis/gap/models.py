"""Gap recommendation models responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from starsector_variant_generator.analysis.build_archetypes import BuildArchetypeProfile
from starsector_variant_generator.analysis.faction_capability import FactionCapabilityProfile
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack, capability_gap_guidance
from starsector_variant_generator.core.result_cache import CacheReadiness

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
