"""Gap recommendation native responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.analysis.combat_entity import recommendation_eligibility
from starsector_variant_generator.analysis.faction_capability import analyze_faction_capability
from starsector_variant_generator.analysis.mechanical_archetypes import infer_mechanical_archetypes
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack
from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import Registry
from .models import GapRecommendationResult, NativeRecommendation, RecommendationAudit, RecommendationConstraints, _recommendation_confidence, _require_selection_order, detect_capability_gaps
from .ranking import _diverse_build_shortlist, _jaccard, _rank_build_candidates_for_role

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
