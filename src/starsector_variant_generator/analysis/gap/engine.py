"""Gap recommendation engine responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from dataclasses import replace as dataclass_replace
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack, officer_guidance
from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import Registry
from .acquisition import recommend_acquisition_solutions
from .models import GapRecommendationResult, RecommendationConstraints
from .native import recommend_native_solutions
from .retrofit import recommend_retrofit_solutions

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
