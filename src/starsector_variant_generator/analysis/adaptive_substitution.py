"""Adaptive substitution scoring: EQUIPMENT_ACCESS_AND_AUTOFIT.md sections 9-12, first slice.

Scores how well a candidate weapon preserves a target weapon's role/range/
flux/damage/cost/provenance, per section 11's named component list.
Weights are `HEURISTICS.md` section 13's own suggested starting values,
transcribed verbatim into `core/heuristics.py` rather than re-invented.

Two of the 8 named components are deliberately not computed as scored
inputs:

- `AI_friendliness`: no classifier for this exists anywhere in this
  project. Fabricating one now, just to fill this slot, would be exactly
  the kind of unverifiable guess this project's discipline exists to
  avoid. Left out of the weighted average entirely (not scored as 0,
  which would look like a real, low, unfriendly rating rather than "no
  data").
- `confidence`: read literally, this is the *reliability of the score
  itself* (how many of the other components had real data), not a
  property of the candidate being scored -- feeding a result's own
  confidence back into computing that result doesn't have a coherent
  meaning. Computed here as `SubstitutionScore.confidence`, an output
  describing the result, not a weighted input to it.

`role_match` and `damage_behavior_match` reuse `classify_weapon` (already
tested elsewhere); `affinity` reuses `classify_equipment_affinity`
(same). Nothing here is a new, unverified inference -- every component is
built from data this project already parses and already trusts.
"""

from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.analysis.classification import classify_weapon
from starsector_variant_generator.analysis.equipment_affinity import classify_equipment_affinity
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack

_AFFINITY_HEURISTIC_KEYS = {
    "NATIVE": "affinity_preference_native",
    "APPROVED": "affinity_preference_approved",
    "COMMON": "affinity_preference_common",
    "UNALIGNED": "affinity_preference_unaligned",
    "FOREIGN": "affinity_preference_foreign",
}

_COMPONENT_WEIGHT_KEYS = {
    "role_match": "substitution_weight_role_match",
    "range_match": "substitution_weight_range_match",
    "flux_match": "substitution_weight_flux_match",
    "damage_behavior_match": "substitution_weight_damage_behavior_match",
    "op_efficiency": "substitution_weight_op_efficiency",
    "affinity": "substitution_weight_affinity",
}


@dataclass(frozen=True)
class SubstitutionScore:
    candidate_id: str
    component_scores: dict[str, float]  # only components with real data to compute; missing keys, not zeros
    overall_score: float
    confidence: float  # fraction of the 6 scorable components that had real data for this pair


def _range_match(target: Weapon, candidate: Weapon) -> float | None:
    if target.range is None or candidate.range is None:
        return None
    return max(0.0, 1.0 - abs(target.range - candidate.range) / max(target.range, 1.0))


def _flux_match(target: Weapon, candidate: Weapon) -> float | None:
    if target.flux_per_shot is None or candidate.flux_per_shot is None:
        return None
    return max(0.0, 1.0 - abs(target.flux_per_shot - candidate.flux_per_shot) / max(target.flux_per_shot, 1.0))


def _damage_behavior_match(target: Weapon, candidate: Weapon) -> float | None:
    if not target.damage_type or not candidate.damage_type:
        return None
    return 1.0 if target.damage_type.upper() == candidate.damage_type.upper() else 0.0


def _op_efficiency(target: Weapon, candidate: Weapon) -> float | None:
    if target.ordnance_points is None or candidate.ordnance_points is None:
        return None
    if candidate.ordnance_points <= target.ordnance_points:
        return 1.0
    return max(0.0, 1.0 - (candidate.ordnance_points - target.ordnance_points) / max(target.ordnance_points, 1.0))


def _role_match(target: Weapon, candidate: Weapon) -> float | None:
    target_tags = set(classify_weapon(target).role_tags)
    candidate_tags = set(classify_weapon(candidate).role_tags)
    if not target_tags and not candidate_tags:
        return None
    union = target_tags | candidate_tags
    if not union:
        return None
    return len(target_tags & candidate_tags) / len(union)


def score_substitution_candidate(
    target: Weapon, candidate: Weapon, registry: Registry,
    requesting_faction_id: str | None = None, heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> SubstitutionScore:
    heuristics = get_heuristic_set(heuristic_set).values
    components: dict[str, float] = {}
    role_match = _role_match(target, candidate)
    if role_match is not None:
        components["role_match"] = role_match
    range_match = _range_match(target, candidate)
    if range_match is not None:
        components["range_match"] = range_match
    flux_match = _flux_match(target, candidate)
    if flux_match is not None:
        components["flux_match"] = flux_match
    damage_match = _damage_behavior_match(target, candidate)
    if damage_match is not None:
        components["damage_behavior_match"] = damage_match
    op_efficiency = _op_efficiency(target, candidate)
    if op_efficiency is not None:
        components["op_efficiency"] = op_efficiency
    affinity_classification = classify_equipment_affinity(candidate.id, "weapons", registry, requesting_faction_id, knowledge_pack=knowledge_pack)
    affinity = affinity_classification.affinity
    components["affinity"] = heuristics[_AFFINITY_HEURISTIC_KEYS[affinity]]

    weighted_sum = sum(components[name] * heuristics[_COMPONENT_WEIGHT_KEYS[name]] for name in components)
    total_weight = sum(heuristics[_COMPONENT_WEIGHT_KEYS[name]] for name in components)
    overall = weighted_sum / total_weight if total_weight else 0.0
    confidence = len(components) / len(_COMPONENT_WEIGHT_KEYS)
    if affinity_classification.guidance_confidence is not None:
        confidence *= affinity_classification.guidance_confidence
    return SubstitutionScore(candidate.id, components, overall, confidence)


def rank_substitution_candidates(
    target: Weapon, candidates: list[Weapon], registry: Registry,
    requesting_faction_id: str | None = None, heuristic_set: str = "baseline_0.2",
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> tuple[SubstitutionScore, ...]:
    """Highest overall_score first; ties broken by candidate id for determinism."""
    scores = [score_substitution_candidate(target, candidate, registry, requesting_faction_id, heuristic_set, knowledge_pack) for candidate in candidates]
    return tuple(sorted(scores, key=lambda score: (-score.overall_score, score.candidate_id)))
