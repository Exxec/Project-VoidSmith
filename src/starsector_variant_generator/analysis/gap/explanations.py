"""Gap recommendation explanations responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from dataclasses import dataclass, field
from starsector_variant_generator.analysis.build_archetypes import BuildArchetypeProfile, infer_build_archetypes
from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.analysis.faction_capability import analyze_faction_capability
from starsector_variant_generator.analysis.mechanical_archetypes import infer_mechanical_archetypes
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack
from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import Registry
from .acquisition import _acquisition_audit_trail
from .engine import recommend_gap_solutions
from .models import RecommendationConstraints, _capability_gap_confidence_inputs, _recommendation_confidence_from_values
from .native import _native_audit_trail, _native_hull_level_lookup, _resolved_known_hulls
from .ranking import _ROLE_TO_PROFILE, _diverse_build_shortlist, _rank_build_candidates_for_role
from .retrofit import _retrofit_audit_trail, _variants_for_hull

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
