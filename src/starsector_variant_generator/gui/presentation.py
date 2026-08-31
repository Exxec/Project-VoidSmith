"""Pure formatting helpers for GUI output; no scoring or rules live here."""
from __future__ import annotations

from typing import Any

from starsector_variant_generator.analysis.fleet_support import (
    FleetSupportRecommendation,
    FleetSupportResult,
    FleetSupportWhyNotExplanation,
)
from starsector_variant_generator.analysis.gap_recommendation import BuildWhyNotExplanation
from starsector_variant_generator.analysis.scenario_advisor import (
    ScenarioFleetAssessment,
)


def format_generation_results(assessed_candidates: list[dict[str, Any]], profile: str, flux_mode: str) -> str:
    """Render backend-supplied candidate evidence as compact, comparable cards."""
    lines = [f"PROFILE  {profile}    FLUX POSTURE  {flux_mode}", ""]
    if not assessed_candidates:
        return "\n".join([*lines, "No legal candidates were returned by the backend."])
    for index, item in enumerate(assessed_candidates, 1):
        build = item.get("build_archetype", {})
        label = item.get("recommendation_label") or build.get("role") or "Candidate"
        score = item.get("build_recommendation_score", item.get("quality", {}).get("final_score"))
        compatibility = build.get("compatibility")
        confidence = build.get("confidence")
        variant = item.get("variant", {}).get("id", "unknown")
        lines.append(f"{index}. {label}  |  {item.get('legality', 'UNKNOWN')}")
        lines.append(f"   Score: {score if score is not None else 'Unavailable'}   Compatibility: {compatibility if compatibility is not None else 'Unavailable'}   Confidence: {confidence if confidence is not None else 'Unavailable'}")
        lines.append(f"   Variant: {variant}")
        omissions = item.get("omissions")
        if omissions:
            lines.append(f"   Notes: {', '.join(str(value) for value in omissions)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_fleet_support_result(result: FleetSupportResult) -> str:
    """Present backend advisor evidence without recomputing any rule."""
    lines = ["FLEET SUPPORT ADVISOR", "Locked: " + ", ".join(f"{item.variant_id or item.hull_id} ×{item.count}" for item in result.profile.selections), ""]
    if result.profile.unresolved_hull_ids:
        lines.append("Unresolved selections: " + ", ".join(result.profile.unresolved_hull_ids))
    if result.profile.excluded_selection_hull_ids:
        lines.append("Structurally excluded selections: " + ", ".join(result.profile.excluded_selection_hull_ids))
    material_traits = [item for item in result.profile.composition_traits if item.score is not None and item.score > 0.0]
    if material_traits:
        lines.append("Composition traits: " + ", ".join(f"{item.name} {item.score:.3f} ({item.confidence:.3f})" for item in material_traits))
    if result.profile.support_needs:
        lines.extend(["Support needs:", *[f"  • {item.capability} ({item.category}, need {item.score:.2f}, confidence {item.confidence:.2f})" for item in result.profile.support_needs], ""])
    for shortlist in result.category_shortlists:
        lines.append(shortlist.category.replace("_", " "))
        if not shortlist.recommendations:
            lines.append("  No material candidates.")
        for item in shortlist.recommendations:
            lines.append(f"  {item.shortlist_order or '?'} . {item.hull_id} — {item.recommendation_type}; score {item.recommendation_score:.3f}, confidence {item.confidence:.3f}")
            lines.append(f"     Supports: {', '.join(item.supports)}")
            if item.support_purposes:
                lines.append(f"     Purposes: {', '.join(item.support_purposes)}")
            if item.score_components is not None:
                parts = item.score_components
                lines.append(f"     Components: support {parts.support_need_coverage:.3f}; doctrine {parts.doctrine_cohesion:.3f}; composition {parts.composition_synergy:.3f}; friction {parts.static_friction:.3f}.")
            lines.append(f"     {item.diversity_reason or 'Selected by score.'}")
    if result.unaddressed_support_needs:
        lines.extend(["", "No material recommendation:", *[f"  • {item.capability}" for item in result.unaddressed_support_needs]])
    lines.extend(["", "Limits: no concrete fit legality, campaign state, runtime phase behavior, fleet-wide sensor behavior, or hullmod-modified burn conclusion."])
    return "\n".join(lines)


def format_fleet_support_why_not(result: FleetSupportWhyNotExplanation) -> str:
    """Present a backend Why-Not record without attempting a ranking locally."""
    lines = [f"FLEET SUPPORT WHY-NOT — {result.hull_id}", result.reason]
    if result.recommendation_score is not None:
        lines.append(f"Score: {result.recommendation_score:.3f}    Confidence: {result.confidence if result.confidence is not None else 'Unavailable'}")
    if result.rank is not None:
        lines.append(f"Ranking: {result.rank} of {result.total_ranked_candidates}")
    if result.recommendation is not None:
        lines.append("Supports: " + ", ".join(result.recommendation.supports))
        if result.recommendation.support_purposes:
            lines.append("Purposes: " + ", ".join(result.recommendation.support_purposes))
        if result.recommendation.score_components is not None:
            parts = result.recommendation.score_components
            lines.append(f"Score components: support={parts.support_need_coverage:.3f}; doctrine={parts.doctrine_cohesion:.3f}; composition={parts.composition_synergy:.3f}; friction={parts.static_friction:.3f}; access={parts.access_affinity:.3f}.")
        lines.append("Friction: " + ", ".join(result.recommendation.friction.notes))
    return "\n".join(lines)


def format_fleet_support_comparison(items: tuple[FleetSupportRecommendation, ...]) -> str:
    """Show backend recommendation fields side by side without re-ranking."""
    lines = ["FLEET SUPPORT COMPARISON"]
    for item in items:
        lines.extend((
            "",
            f"{item.hull_id} — {item.category}",
            f"Score {item.recommendation_score:.3f} | Confidence {item.confidence:.3f}",
            "Supports: " + ", ".join(item.supports),
            "Purposes: " + (", ".join(item.support_purposes) or "No mapped support purpose."),
            "Components: " + (f"support {item.score_components.support_need_coverage:.3f} | doctrine {item.score_components.doctrine_cohesion:.3f} | composition {item.score_components.composition_synergy:.3f} | friction {item.score_components.static_friction:.3f} | access {item.score_components.access_affinity:.3f}" if item.score_components is not None else "Unavailable."),
            "Friction: " + (", ".join(item.friction.notes) or "No resolved static friction."),
            "Fit legality: " + item.fit_legality_status,
        ))
    return "\n".join(lines)


def format_build_why_not_comparison(items: tuple[BuildWhyNotExplanation, ...]) -> str:
    """Compare already-computed Build Why-Not evidence without re-ranking."""
    lines = ["BUILD PATH EXPLAINABILITY COMPARISON"]
    for item in items:
        lines.extend((
            "", f"{item.hull_id} / {item.build_archetype_id}",
            f"Resolved: {item.resolved} | Rank: {item.rank if item.rank is not None else 'Unavailable'} | Score: {item.recommendation_score if item.recommendation_score is not None else 'Unavailable'}",
            "Recommended legs: " + (", ".join(item.recommended_legs) or "None"),
            "Build evidence: " + (f"compatibility {item.build.compatibility:.3f}; confidence {item.build.confidence:.3f}; maturity {item.build.maturity}" if item.build is not None else "Unavailable."),
            "Components: " + (", ".join(f"{key}={value:.3f}" for key, value in sorted(item.scoring_components.items())) or "Unavailable."),
            "Reason: " + item.reason,
        ))
    return "\n".join(lines)


def format_scenario_fleet_assessment(result: ScenarioFleetAssessment) -> str:
    """Present backend scenario evidence without estimating battle outcomes."""
    lines = [f"SCENARIO ADVISOR — {result.scenario.display_name}", f"Mechanical alignment: {result.readiness}" + (f" ({result.readiness_score:.3f})" if result.readiness_score is not None else ""), f"Confidence: {result.confidence:.3f}", ""]
    if result.strengths:
        lines.extend(["Strong / adequate:", *[f"  • {item.capability}: {item.available:.3f} against target {item.target:.3f}" for item in result.strengths]])
    if result.deficiencies:
        lines.extend(["", "Weak:", *[f"  • {item.capability}: {item.available:.3f} against target {item.target:.3f}; gap {item.gap:.3f}" for item in result.deficiencies]])
    if result.unknowns:
        lines.extend(["", "Unknown:", *[f"  • {item.capability}" for item in result.unknowns]])
    if result.recommendations:
        lines.extend(["", "Individual additions with scenario-need coverage:"])
        for item in result.recommendations:
            lines.append(f"  • {item.hull_id}: {', '.join(item.support_purposes) or ', '.join(item.supports)}; score {item.recommendation_score:.3f}; confidence {item.confidence:.3f}")
    lines.extend(["", *result.evidence])
    return "\n".join(lines)
