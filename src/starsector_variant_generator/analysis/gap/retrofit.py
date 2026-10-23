"""Gap recommendation retrofit responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from dataclasses import dataclass
from starsector_variant_generator.analysis.build_archetypes import BuildArchetypeProfile, profile_id_for_build
from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.analysis.mechanical_archetypes import infer_mechanical_archetypes
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack, retrofit_template_ids
from starsector_variant_generator.core.models import Faction, Variant
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.refit import QualityRefitResult, improve_quality
from .models import CapabilityGap, RecommendationAudit, RecommendationConstraints, RetrofitRecommendation, _recommendation_confidence, _require_selection_order
from .native import _diverse_hull_shortlist, _rank_candidates_for_role, _resolved_known_hulls
from .ranking import _ROLE_TO_PROFILE, _diverse_build_shortlist, _rank_build_candidates_for_role

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
