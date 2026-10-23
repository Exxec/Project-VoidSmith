"""Gap recommendation acquisition responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from starsector_variant_generator.analysis.build_archetypes import BuildArchetypeProfile, infer_build_archetypes
from starsector_variant_generator.analysis.classification import classify_hull
from starsector_variant_generator.analysis.combat_entity import recommendation_eligibility
from starsector_variant_generator.analysis.equipment_affinity import classify_equipment_affinity
from starsector_variant_generator.analysis.mechanical_archetypes import infer_mechanical_archetypes
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack
from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import Registry
from .models import AcquisitionRecommendation, CapabilityGap, RecommendationAudit, RecommendationConstraints, _recommendation_confidence, _require_selection_order
from .native import _diverse_hull_shortlist
from .ranking import _ROLE_TO_BUILD_IDS, _diverse_build_shortlist

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
