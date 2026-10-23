"""Gap recommendation ranking responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from starsector_variant_generator.analysis.build_archetypes import BuildArchetypeProfile, infer_build_archetypes
from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.analysis.mechanical_archetypes import infer_mechanical_archetypes
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack, build_archetype_preference, progression_guidance_confidence, progression_hull_ids
from starsector_variant_generator.core.registry import Registry

def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 1.0


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
