"""Fleet Support Advisor -- advisory additions for a locked player selection.

This is deliberately not a fleet optimizer.  It neither selects quantities,
replaces a selected hull, reads a campaign save, nor evaluates fleet-wide game
mechanics.  It aggregates only normalized, per-hull evidence and ranks one
independently deployable candidate at a time.  A candidate has no concrete
fit here, so fit legality is intentionally *not evaluated*; structural
recommendation eligibility and access policy are separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from starsector_variant_generator.analysis.capability_vector import CapabilityEvidence, CapabilityVector, infer_hull_capability_vector
from starsector_variant_generator.analysis.combat_doctrine import CombatDoctrineProfile, DoctrineAxisProfile, infer_combat_doctrine
from starsector_variant_generator.analysis.combat_entity import recommendation_eligibility
from starsector_variant_generator.analysis.equipment_affinity import classify_equipment_affinity
from starsector_variant_generator.analysis.mechanical_archetypes import infer_hull_feature_vector
from starsector_variant_generator.analysis.mechanical_archetypes import infer_mechanical_archetypes
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Faction, Hull, Variant
from starsector_variant_generator.core.registry import Registry


class SupportFocus(StrEnum):
    BALANCED = "BALANCED"
    COMBAT = "COMBAT"
    LOGISTICS = "LOGISTICS"
    SURVIVABILITY = "SURVIVABILITY"
    PURSUIT = "PURSUIT"
    LONG_ENGAGEMENTS = "LONG_ENGAGEMENTS"
    STEALTH = "STEALTH"


class RecommendationReason(StrEnum):
    SYNERGY = "SYNERGY"
    GAP_FILL = "GAP_FILL"
    SYNERGY_AND_GAP_FILL = "SYNERGY_AND_GAP_FILL"


_COMBAT_NEEDS = ("SUSTAINED_PRESSURE", "PD_SCREENING", "FIGHTER_INTERCEPTION", "KINETIC_PRESSURE", "ARMOR_BREAKING", "FINISHING_POWER", "MISSILE_PROJECTION", "CARRIER_PROJECTION", "MOBILITY", "PURSUIT", "ARMOR_TANKING", "SHIELD_TANKING")
_LOGISTICS_NEEDS = ("FREIGHTER", "TANKER", "SALVAGE_SUPPORT", "SURVEY_SUPPORT")
_SUPPORT_FIT_PROFILE_BY_PURPOSE = {
    "PD_SCREEN": "PD_ESCORT",
    "FIGHTER_SCREEN": "CARRIER_SUPPORT",
    "CARRIER_SUPPORT": "CARRIER_SUPPORT",
    "MISSILE_SUPPORT": "MISSILE_SUPPORT",
    "LINE_ANCHOR": "TANK",
    "ARMOR_BREAKER": "LINE_ARTILLERY",
    "SUSTAINED_FIRE": "LINE_ARTILLERY",
    "SHIELD_PRESSURE": "LINE_ARTILLERY",
    "FINISHER": "FAST_STRIKE",
    "PURSUIT_SUPPORT": "FAST_STRIKE",
}


@dataclass(frozen=True)
class FleetSelection:
    """Player intent: selected hulls are locked and are never candidates."""
    hull_id: str | None = None
    count: int = 1
    variant_id: str | None = None


def parse_fleet_selections(tokens: tuple[str, ...]) -> tuple[FleetSelection, ...]:
    """Parse explicit player selections: ``hull_id`` or ``hull_id*count``.

    This is input convenience only; counts remain player-declared locked
    instances and are never recommendation quantities.
    """
    selections: list[FleetSelection] = []
    for token in tokens:
        hull_id, separator, count_text = token.strip().rpartition("*")
        if not separator:
            hull_id, count = token.strip(), 1
        else:
            if not hull_id or not count_text.isdecimal() or int(count_text) < 1:
                raise ValueError(f"Invalid fleet selection {token!r}; use hull_id or hull_id*positive_count")
            count = int(count_text)
        if not hull_id:
            raise ValueError("Fleet selection hull id cannot be empty")
        selections.append(FleetSelection(variant_id=hull_id[8:] if hull_id.startswith("variant:") else None, hull_id=None if hull_id.startswith("variant:") else hull_id, count=count))
    if not selections:
        raise ValueError("Fleet Support Advisor requires at least one selected hull")
    return tuple(selections)


def fleet_support_request_to_payload(selections: tuple[FleetSelection, ...], constraints: FleetSupportConstraints) -> dict[str, object]:
    """Portable user-owned request only; contains no scanned game/mod facts."""
    return {"schema_version": "fleet_support_request_1", "selections": [{"hull_id": item.hull_id, "variant_id": item.variant_id, "count": item.count} for item in selections], "constraints": {"access_mode": constraints.access_mode, "allow_foreign_hulls": constraints.allow_foreign_hulls, "include_hidden_hulls": constraints.include_hidden_hulls, "focus": constraints.focus.value, "recommendation_count": constraints.recommendation_count}}


def fleet_support_request_from_payload(payload: dict[str, object]) -> tuple[tuple[FleetSelection, ...], FleetSupportConstraints]:
    if payload.get("schema_version") != "fleet_support_request_1":
        raise ValueError("Unsupported Fleet Support Advisor request snapshot schema")
    selections = tuple(FleetSelection(item.get("hull_id") if isinstance(item.get("hull_id"), str) else None, int(item.get("count", 1)), item.get("variant_id") if isinstance(item.get("variant_id"), str) else None) for item in payload.get("selections", []) if isinstance(item, dict))
    data = payload.get("constraints")
    if not isinstance(data, dict):
        raise ValueError("Fleet Support Advisor request snapshot lacks constraints")
    return selections, FleetSupportConstraints(str(data.get("access_mode", "FACTION_PLUS")), bool(data.get("allow_foreign_hulls", True)), bool(data.get("include_hidden_hulls", False)), SupportFocus(str(data.get("focus", "BALANCED"))), data.get("recommendation_count") if isinstance(data.get("recommendation_count"), int) else None)


@dataclass(frozen=True)
class FleetSupportConstraints:
    access_mode: str = "FACTION_PLUS"
    allow_foreign_hulls: bool = True
    include_hidden_hulls: bool = False
    focus: SupportFocus = SupportFocus.BALANCED
    recommendation_count: int | None = None


@dataclass(frozen=True)
class FleetSupportNeed:
    capability: str
    score: float
    confidence: float
    category: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FleetCompatibilityProfile:
    mobility_match: float | None
    engagement_position_match: float | None
    tactical_style_match: float | None
    tempo_match: float | None
    defensive_doctrine_match: float | None
    deployment_position_match: float | None
    support_need_match: float
    logistics_match: float | None
    faction_affinity: float
    burn_speed_match: float | None = None
    range_match: float | None = None
    sensor_profile_match: float | None = None
    phase_trait_match: float | None = None
    unknown_dimensions: tuple[str, ...] = ("range_match", "sensor_profile_match")


@dataclass(frozen=True)
class FleetCompositionTrait:
    """Count-aware direct or normalized evidence about locked selections."""
    name: str
    score: float | None
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CompositionSynergyProfile:
    """Compatibility that preserves fleet character, distinct from doctrine."""
    phase_match: float | None
    sensor_match: float | None
    burn_match: float | None
    mobility_character_match: float | None
    score: float
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FleetSupportScoreComponents:
    support_need_coverage: float
    doctrine_cohesion: float
    composition_synergy: float
    static_friction: float
    access_affinity: float
    recommendation_score: float


@dataclass(frozen=True)
class FleetFriction:
    speed_mismatch: float | None
    engagement_position_mismatch: float | None
    tempo_mismatch: float | None
    logistics_mismatch: float | None
    range_mismatch: float | None = None
    sensor_penalty: None = None
    burn_penalty: float | None = None
    deployment_cost_pressure: None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FleetSupportRecommendation:
    hull_id: str
    recommendation_type: RecommendationReason
    category: str
    recommendation_score: float
    confidence: float
    supports: tuple[str, ...]
    compatibility: FleetCompatibilityProfile
    friction: FleetFriction
    access_affinity: str
    evidence: tuple[str, ...]
    composition_synergy: CompositionSynergyProfile | None = None
    score_components: FleetSupportScoreComponents | None = None
    support_purposes: tuple[str, ...] = ()
    mechanical_archetypes: tuple[str, ...] = ()
    diversity_reason: str | None = None
    shortlist_order: int | None = None
    fit_legality_status: str = "NOT_EVALUATED_NO_CONCRETE_FIT"


@dataclass(frozen=True)
class PlayerFleetProfile:
    selections: tuple[FleetSelection, ...]
    resolved_hull_ids: tuple[str, ...]
    unresolved_hull_ids: tuple[str, ...]
    excluded_selection_hull_ids: tuple[str, ...]
    capability_vector: dict[str, CapabilityEvidence]
    doctrine: dict[str, DoctrineAxisProfile]
    support_needs: tuple[FleetSupportNeed, ...]
    declared_traits: tuple[str, ...]
    composition_traits: tuple[FleetCompositionTrait, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FleetSupportResult:
    profile: PlayerFleetProfile
    recommendations: tuple[FleetSupportRecommendation, ...]
    category_shortlists: tuple["FleetSupportCategoryShortlist", ...]
    unaddressed_support_needs: tuple[FleetSupportNeed, ...]
    excluded_candidates: tuple[tuple[str, str], ...]
    heuristic_set: str


@dataclass(frozen=True)
class FleetSupportCategoryShortlist:
    category: str
    support_needs: tuple[str, ...]
    recommendations: tuple[FleetSupportRecommendation, ...]


@dataclass(frozen=True)
class FleetSupportWhyNotExplanation:
    hull_id: str
    resolved: bool
    recommended: bool
    rank: int | None
    total_ranked_candidates: int
    recommendation_score: float | None
    confidence: float | None
    reason: str
    recommendation: FleetSupportRecommendation | None = None


def analyze_player_fleet(selections: tuple[FleetSelection, ...], registry: Registry, heuristic_set: str = "baseline_0.14", focus: SupportFocus = SupportFocus.BALANCED) -> PlayerFleetProfile:
    """Aggregate locked hull evidence. Duplicate selections intentionally add
    representation but do not invent fleet-wide combat outcome predictions."""
    if not selections:
        raise ValueError("Fleet Support Advisor requires at least one selected hull")
    resolved: list[tuple[Hull, tuple[Variant, ...] | None]] = []
    unresolved: list[str] = []
    excluded: list[str] = []
    for selection in selections:
        label = selection.variant_id or selection.hull_id or "<empty>"
        if selection.count < 1:
            raise ValueError(f"Fleet selection count must be positive: {label}")
        if selection.variant_id:
            variant = registry.variants.by_id.get(selection.variant_id)
            hull = registry.hulls.by_id.get(variant.hull_id or "") if variant else None
        else:
            hull = registry.hulls.by_id.get(selection.hull_id or "")
        if hull is None:
            unresolved.append(label)
        elif recommendation_eligibility(hull).eligible:
            # A selected variant is concrete observed fitting evidence. A
            # hull-ID selection deliberately keeps the prior aggregate-of-
            # indexed-variants behavior.
            observed = (variant,) if selection.variant_id and variant is not None else None
            resolved.extend([(hull, observed)] * selection.count)
        else:
            excluded.append(selection.hull_id)
    vectors = [infer_hull_capability_vector(hull, registry, variants) for hull, variants in resolved]
    doctrines = [infer_combat_doctrine(hull, registry, variants) for hull, variants in resolved]
    capabilities = _aggregate_capabilities(vectors)
    doctrine = _aggregate_doctrine(doctrines)
    needs = _support_needs(capabilities, focus, heuristic_set)
    return PlayerFleetProfile(
        selections, tuple(sorted({hull.id for hull, _ in resolved})), tuple(sorted(set(unresolved))), tuple(sorted(set(excluded))),
        capabilities, doctrine, needs, _fleet_declared_traits(selections, registry), _composition_traits(resolved, vectors, doctrines),
        ("Selected ships remain locked; this advisor only ranks possible additions.",
         "Runtime phase behavior, fleet-wide sensor behavior, hullmod-modified burn, deployment-point totals, and concrete candidate fit legality are not modeled by this advisory analysis."),
    )


def recommend_fleet_support(
    selections: tuple[FleetSelection, ...], registry: Registry, faction: Faction | None = None,
    heuristic_set: str = "baseline_0.14", constraints: FleetSupportConstraints = FleetSupportConstraints(),
    additional_needs: tuple[FleetSupportNeed, ...] = (),
    replace_support_needs: bool = False,
) -> FleetSupportResult:
    if constraints.access_mode not in {"STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"}:
        raise ValueError(f"Unknown fleet support access mode: {constraints.access_mode}")
    profile, ranked, excluded = _rank_fleet_support(selections, registry, faction, heuristic_set, constraints, additional_needs, replace_support_needs)
    values = get_heuristic_set(heuristic_set).values
    count = constraints.recommendation_count or int(values.get("fleet_support_recommendation_count", 3.0))
    selected = tuple(item for item, _ in _diverse_fleet_support_shortlist(ranked, registry, count, heuristic_set))
    surfaced_capabilities = {capability for item in ranked for capability in item.supports}
    unaddressed = tuple(need for need in profile.support_needs if need.capability not in surfaced_capabilities)
    category_shortlists = _category_shortlists(profile, ranked, registry, count, heuristic_set)
    return FleetSupportResult(profile, selected, category_shortlists, unaddressed, tuple(excluded), heuristic_set)


def explain_fleet_support_candidate(
    selections: tuple[FleetSelection, ...], registry: Registry, hull_id: str, faction: Faction | None = None,
    heuristic_set: str = "baseline_0.14", constraints: FleetSupportConstraints = FleetSupportConstraints(),
) -> FleetSupportWhyNotExplanation:
    """Explain one possible addition from the exact advisor ranking path."""
    profile, ranked, excluded = _rank_fleet_support(selections, registry, faction, heuristic_set, constraints)
    candidate = registry.hulls.by_id.get(hull_id)
    if candidate is None:
        return FleetSupportWhyNotExplanation(hull_id, False, False, None, len(ranked), None, None, "Hull is not a resolved, unambiguous indexed hull.")
    exclusion = dict(excluded).get(hull_id)
    if exclusion is not None:
        return FleetSupportWhyNotExplanation(hull_id, True, False, None, len(ranked), None, None, f"Excluded before ranking: {exclusion}.")
    item = next((record for record in ranked if record.hull_id == hull_id), None)
    if item is None:
        return FleetSupportWhyNotExplanation(hull_id, True, False, None, len(ranked), None, None, "No material match for the selected fleet's currently evidenced support needs.")
    rank = ranked.index(item) + 1
    count = constraints.recommendation_count or int(get_heuristic_set(heuristic_set).values.get("fleet_support_recommendation_count", 3.0))
    selected = _diverse_fleet_support_shortlist(ranked, registry, count, heuristic_set)
    selected_records = {record.hull_id: record for record, _ in selected}
    if hull_id in selected_records:
        selected_item = selected_records[hull_id]
        return FleetSupportWhyNotExplanation(hull_id, True, True, rank, len(ranked), item.recommendation_score, item.confidence, f"Recommended: {selected_item.diversity_reason}", selected_item)
    cutoff = min((record.recommendation_score for record, _ in selected), default=None)
    reason = "Ranked below the diversity-aware shortlist cutoff."
    if cutoff is not None:
        reason = f"Ranked below the diversity-aware shortlist cutoff; score is {cutoff - item.recommendation_score:.6f} below the lowest selected score."
    return FleetSupportWhyNotExplanation(hull_id, True, False, rank, len(ranked), item.recommendation_score, item.confidence, reason, item)


def _rank_fleet_support(
    selections: tuple[FleetSelection, ...], registry: Registry, faction: Faction | None,
    heuristic_set: str, constraints: FleetSupportConstraints, additional_needs: tuple[FleetSupportNeed, ...] = (), replace_support_needs: bool = False,
) -> tuple[PlayerFleetProfile, list[FleetSupportRecommendation], list[tuple[str, str]]]:
    if constraints.access_mode not in {"STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"}:
        raise ValueError(f"Unknown fleet support access mode: {constraints.access_mode}")
    if constraints.recommendation_count is not None and constraints.recommendation_count < 1:
        raise ValueError("Fleet Support Advisor recommendation_count must be positive")
    profile = analyze_player_fleet(selections, registry, heuristic_set, constraints.focus)
    if additional_needs:
        profile = replace(profile, support_needs=additional_needs if replace_support_needs else _merged_support_needs(profile.support_needs, additional_needs))
    values = get_heuristic_set(heuristic_set).values
    selected = set(profile.resolved_hull_ids)
    excluded: list[tuple[str, str]] = []
    ranked: list[FleetSupportRecommendation] = []
    for hull in sorted(registry.hulls.by_id.values(), key=lambda item: item.id):
        if hull.id in selected:
            excluded.append((hull.id, "LOCKED_PLAYER_SELECTION"))
            continue
        eligibility = recommendation_eligibility(hull)
        if not eligibility.eligible:
            excluded.append((hull.id, eligibility.reason))
            continue
        affinity = classify_equipment_affinity(hull.id, "hulls", registry, faction.id if faction else None).affinity
        if not _allowed(affinity, hull, faction, constraints):
            excluded.append((hull.id, f"ACCESS_POLICY_{affinity}"))
            continue
        recommendation = _score_candidate(hull, registry, profile, affinity, constraints, values)
        if recommendation is not None:
            ranked.append(recommendation)
    ranked.sort(key=lambda item: (-item.recommendation_score, -item.confidence, item.hull_id))
    return profile, ranked, excluded


def _merged_support_needs(existing: tuple[FleetSupportNeed, ...], extra: tuple[FleetSupportNeed, ...]) -> tuple[FleetSupportNeed, ...]:
    """Combine externally declared mission needs without inventing evidence."""
    selected: dict[str, FleetSupportNeed] = {item.capability: item for item in existing}
    for item in extra:
        prior = selected.get(item.capability)
        if prior is None or item.score > prior.score:
            selected[item.capability] = item
    return tuple(sorted(selected.values(), key=lambda item: (-item.score, item.capability)))


def _allowed(affinity: str, hull: Hull, faction: Faction | None, constraints: FleetSupportConstraints) -> bool:
    if not constraints.include_hidden_hulls and bool(hull.raw.get("hidden", False)):
        return False
    if constraints.access_mode == "UNRESTRICTED":
        return True
    if faction is None:
        return constraints.access_mode == "FACTION_PLUS" and (constraints.allow_foreign_hulls or affinity != "FOREIGN")
    if constraints.access_mode == "STRICT_FACTION":
        return hull.id in faction.known_hulls
    return constraints.allow_foreign_hulls or affinity != "FOREIGN"


def _diverse_fleet_support_shortlist(
    ranked: list[FleetSupportRecommendation], registry: Registry, count: int, heuristic_set: str,
) -> list[tuple[FleetSupportRecommendation, str]]:
    """Keep score-leading additions while selecting competitive distinct families.

    This is an advisory presentation decision; it never admits an excluded or
    low-signal candidate because `ranked` already contains only such candidates.
    """
    values = get_heuristic_set(heuristic_set).values
    if not values.get("fleet_support_diversity_enabled", 0.0) or not ranked:
        return [(replace(item, shortlist_order=index + 1, diversity_reason="Selected by recommendation score."), "Selected by recommendation score.") for index, item in enumerate(ranked[:count])]
    threshold = values.get("recommendation_diversity_min_archetype_compatibility", .2)
    tolerance = values.get("recommendation_diversity_material_score_tolerance", .1)
    penalty = values.get("recommendation_diversity_similarity_penalty", .15)
    profiles = {item.hull_id: {name for name, score in infer_mechanical_archetypes(registry.hulls.by_id[item.hull_id], registry).compatibility_scores.items() if score >= threshold} for item in ranked}
    selected: list[tuple[FleetSupportRecommendation, str]] = []
    remaining = list(ranked)
    best_score = ranked[0].recommendation_score
    while remaining and len(selected) < count:
        if not selected:
            choice, reason = remaining[0], "Highest Fleet Support Advisor score."
        else:
            competitive = [item for item in remaining if item.recommendation_score >= best_score * (1 - tolerance)]
            pool = competitive or remaining
            selected_ids = [item.hull_id for item, _ in selected]
            def key(item: FleetSupportRecommendation) -> tuple[float, float, str]:
                similarity = max((_jaccard(profiles[item.hull_id], profiles[other]) for other in selected_ids), default=0.0)
                return (item.recommendation_score - penalty * similarity * best_score, 1 - similarity, item.hull_id)
            choice = max(pool, key=key)
            reason = "Selected as a mechanically distinct, score-competitive support family." if choice in competitive else "Selected by score because no remaining score-competitive distinct family was available."
        order = len(selected) + 1
        selected.append((replace(choice, mechanical_archetypes=tuple(sorted(profiles[choice.hull_id])), diversity_reason=reason, shortlist_order=order), reason))
        remaining.remove(choice)
    return selected


def _category_shortlists(
    profile: PlayerFleetProfile, ranked: list[FleetSupportRecommendation], registry: Registry,
    count: int, heuristic_set: str,
) -> tuple[FleetSupportCategoryShortlist, ...]:
    result: list[FleetSupportCategoryShortlist] = []
    for category in ("COMBAT", "LOGISTICS"):
        needs = tuple(need.capability for need in profile.support_needs if need.category == category)
        if not needs:
            continue
        category_ranked = [item for item in ranked if set(item.supports) & set(needs)]
        selected = tuple(item for item, _ in _diverse_fleet_support_shortlist(category_ranked, registry, count, heuristic_set))
        result.append(FleetSupportCategoryShortlist(f"{category}_SUPPORT", needs, selected))
    return tuple(result)


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 1.0


def _score_candidate(hull: Hull, registry: Registry, profile: PlayerFleetProfile, affinity: str, constraints: FleetSupportConstraints, values: dict[str, float]) -> FleetSupportRecommendation | None:
    vector = infer_hull_capability_vector(hull, registry)
    doctrine = infer_combat_doctrine(hull, registry)
    relevant_needs = list(profile.support_needs)
    satisfactions = [(need, vector.dimensions[need.capability]) for need in relevant_needs if vector.dimensions[need.capability].score is not None]
    if not satisfactions:
        return None
    support_match = sum(need.score * (evidence.score or 0.0) for need, evidence in satisfactions) / sum(need.score for need, _ in satisfactions)
    if support_match < values.get("fleet_support_min_signal", .15):
        return None
    cohesion = _cohesion(profile.doctrine, doctrine)
    candidate_speed = infer_hull_feature_vector(hull, registry).max_speed
    fleet_speed = _fleet_speed(profile.selections, registry)
    speed_match = None if candidate_speed is None or fleet_speed is None else _clamp(1 - abs(candidate_speed - fleet_speed) / 120.0)
    fleet_burn = _fleet_min_burn(profile.selections, registry)
    burn_match = None if hull.max_burn is None or fleet_burn is None else _clamp(min(hull.max_burn, fleet_burn) / max(hull.max_burn, fleet_burn))
    candidate_range = _variant_weapon_range(hull, registry)
    fleet_range = _fleet_variant_weapon_range(profile.selections, registry)
    range_match = None if candidate_range is None or fleet_range is None else _clamp(1 - abs(candidate_range - fleet_range) / max(candidate_range, fleet_range, 1.0))
    candidate_sensor = hull.sensor_profile
    fleet_sensor = _fleet_sensor_profile(profile.selections, registry)
    sensor_match = None if candidate_sensor is None or fleet_sensor is None else _clamp(1 - abs(candidate_sensor - fleet_sensor) / max(abs(candidate_sensor), abs(fleet_sensor), 1.0))
    phase_match = _phase_trait_match(profile.composition_traits, hull)
    logistics_match = _mean([(evidence.score or 0.0) for need, evidence in satisfactions if need.category == "LOGISTICS"])
    affinity_score = {"NATIVE": 1.0, "APPROVED": .9, "COMMON": .75, "UNALIGNED": .7, "FOREIGN": .4}.get(affinity, .3)
    compatibility = FleetCompatibilityProfile(
        speed_match, _axis_match(profile.doctrine.get("engagement_position"), doctrine.engagement_position),
        _axis_match(profile.doctrine.get("tactical_style"), doctrine.tactical_style), _axis_match(profile.doctrine.get("tempo"), doctrine.tempo),
        _defensive_match(profile, vector), _axis_match(profile.doctrine.get("engagement_position"), doctrine.engagement_position),
        round(support_match, 6), logistics_match, affinity_score, burn_match, range_match, sensor_match, phase_match,
    )
    friction = FleetFriction(
        speed_mismatch=None if speed_match is None else round(1 - speed_match, 6),
        engagement_position_mismatch=None if compatibility.engagement_position_match is None else round(1 - compatibility.engagement_position_match, 6),
        tempo_mismatch=None if compatibility.tempo_match is None else round(1 - compatibility.tempo_match, 6),
        logistics_mismatch=None if logistics_match is None else round(1 - logistics_match, 6),
        range_mismatch=None if range_match is None else round(1 - range_match, 6),
        burn_penalty=None if burn_match is None else round(1 - burn_match, 6),
        notes=("Range cohesion uses resolved existing-variant weapon ranges only; it does not predict a future fit. Sensor and phase matches use normalized static sensor data and direct hull hints only. Static base max-burn mismatch is shown; hullmod-modified and campaign-specific burn behavior is not modeled. Formation and deployment-cost friction require additional data.",),
    )
    complement = support_match
    composition = _composition_synergy(profile.composition_traits, phase_match, sensor_match, burn_match, vector, values)
    static_friction = _mean([value for value in (friction.speed_mismatch, friction.engagement_position_mismatch, friction.tempo_mismatch, friction.range_mismatch) if value is not None], 0.0) or 0.0
    score = _clamp(values.get("fleet_support_complement_weight", .65) * complement + values.get("fleet_support_cohesion_weight", .35) * cohesion + values.get("fleet_support_composition_synergy_weight", 0.0) * composition.score + values.get("fleet_support_access_affinity_weight", 0.0) * affinity_score - values.get("fleet_support_friction_weight", .15) * static_friction)
    supports = tuple(sorted(need.capability for need, evidence in satisfactions if (evidence.score or 0.0) * need.score >= .12))
    if not supports:
        return None
    supported_categories = {need.category for need, _ in satisfactions if need.capability in supports}
    category = "COMBAT_AND_LOGISTICS_SUPPORT" if supported_categories == {"COMBAT", "LOGISTICS"} else "LOGISTICS_SUPPORT" if supported_categories == {"LOGISTICS"} else "COMBAT_SUPPORT"
    kind = RecommendationReason.SYNERGY_AND_GAP_FILL if max(cohesion, composition.score) >= .5 and complement >= .35 else RecommendationReason.SYNERGY if max(cohesion, composition.score) > complement else RecommendationReason.GAP_FILL
    confidence = _mean([need.confidence * evidence.confidence for need, evidence in satisfactions] + [composition.confidence], 0.0)
    purposes = _support_purposes(supports)
    components = FleetSupportScoreComponents(round(complement, 6), round(cohesion, 6), round(composition.score, 6), round(static_friction, 6), round(affinity_score, 6), round(score, 6))
    return FleetSupportRecommendation(hull.id, kind, category, round(score, 6), round(confidence, 6), supports, compatibility, friction, affinity,
                                      (f"Supports fleet need(s): {', '.join(supports)}.", f"Cohesion={cohesion:.3f}; composition={composition.score:.3f}; complement={complement:.3f}; affinity={affinity}."), composition, components, purposes)


def _aggregate_capabilities(vectors: list[CapabilityVector]) -> dict[str, CapabilityEvidence]:
    if not vectors:
        return {}
    result: dict[str, CapabilityEvidence] = {}
    for name in vectors[0].dimensions:
        known = [vector.dimensions[name] for vector in vectors if vector.dimensions[name].score is not None]
        if not known:
            result[name] = CapabilityEvidence(None, 0.0, "UNKNOWN", ("No selected hull has available evidence for this capability.",))
            continue
        best = max(known, key=lambda item: ((item.score or 0.0), item.confidence))
        result[name] = CapabilityEvidence(best.score, best.confidence, "AVAILABLE", ("Best selected-hull evidence; this is coverage, not a fleet outcome prediction.", *best.supporting_evidence))
    return result


def _aggregate_doctrine(doctrines: list[CombatDoctrineProfile]) -> dict[str, DoctrineAxisProfile]:
    if not doctrines:
        return {}
    axes = ("battlefield_function", "engagement_position", "tactical_style", "tempo", "commitment", "fleet_dependence")
    result: dict[str, DoctrineAxisProfile] = {}
    for name in axes:
        source = [getattr(profile, name) for profile in doctrines]
        labels = {label for axis in source for label in axis.scores}
        result[name] = DoctrineAxisProfile({label: round(sum(axis.scores.get(label, 0.0) for axis in source) / len(source), 6) for label in sorted(labels)}, round(sum(axis.confidence for axis in source) / len(source), 6), ("Mean selected-hull doctrine posture; not a tactical simulation.",))
    return result


def _support_needs(capabilities: dict[str, CapabilityEvidence], focus: SupportFocus, heuristic_set: str) -> tuple[FleetSupportNeed, ...]:
    threshold = get_heuristic_set(heuristic_set).values.get("fleet_support_need_threshold", .35)
    if focus is SupportFocus.LOGISTICS:
        names = _LOGISTICS_NEEDS
    elif focus is SupportFocus.SURVIVABILITY:
        names = ("ARMOR_TANKING", "SHIELD_TANKING")
    elif focus is SupportFocus.PURSUIT:
        names = ("PURSUIT", "MOBILITY")
    elif focus is SupportFocus.LONG_ENGAGEMENTS:
        names = ("SUSTAINED_PRESSURE",)
    elif focus is SupportFocus.STEALTH:
        # Sensor/phase-signature mechanics are not a normalized per-hull
        # capability in this project. An empty need list is more honest than
        # silently treating a combat proxy as stealth evidence.
        names = ()
    elif focus is SupportFocus.COMBAT:
        names = _COMBAT_NEEDS
    else:
        names = _COMBAT_NEEDS + _LOGISTICS_NEEDS
    needs = []
    for name in names:
        evidence = capabilities.get(name)
        if evidence is None or evidence.score is None:
            continue
        score = _clamp(1 - evidence.score)
        if score >= threshold:
            needs.append(FleetSupportNeed(name, round(score, 6), evidence.confidence, "LOGISTICS" if name in _LOGISTICS_NEEDS else "COMBAT", evidence.supporting_evidence))
    return tuple(sorted(needs, key=lambda item: (-item.score, item.capability)))


def _cohesion(fleet: dict[str, DoctrineAxisProfile], candidate: CombatDoctrineProfile) -> float:
    matches = [_axis_match(fleet.get("engagement_position"), candidate.engagement_position), _axis_match(fleet.get("tactical_style"), candidate.tactical_style), _axis_match(fleet.get("tempo"), candidate.tempo)]
    return _mean([item for item in matches if item is not None], 0.0)


def _axis_match(fleet: DoctrineAxisProfile | None, candidate: DoctrineAxisProfile) -> float | None:
    if fleet is None:
        return None
    labels = set(fleet.scores) | set(candidate.scores)
    return _clamp(sum(min(fleet.scores.get(label, 0.0), candidate.scores.get(label, 0.0)) for label in labels) / max(sum(fleet.scores.values()), 1e-9))


def _defensive_match(profile: PlayerFleetProfile, candidate: CapabilityVector) -> float:
    fleet_defense = _mean([(profile.capability_vector.get(name).score or 0.0) for name in ("ARMOR_TANKING", "SHIELD_TANKING") if profile.capability_vector.get(name) is not None], 0.0)
    candidate_defense = _mean([(candidate.dimensions[name].score or 0.0) for name in ("ARMOR_TANKING", "SHIELD_TANKING")], 0.0)
    return _clamp(1 - abs(candidate_defense - fleet_defense))


def _fleet_speed(selections: tuple[FleetSelection, ...], registry: Registry) -> float | None:
    speeds = [infer_hull_feature_vector(hull, registry).max_speed for selection in selections if (hull := _selection_hull(selection, registry)) is not None for _ in range(selection.count)]
    return _mean([speed for speed in speeds if speed is not None])


def _fleet_min_burn(selections: tuple[FleetSelection, ...], registry: Registry) -> float | None:
    burns = [hull.max_burn for selection in selections if (hull := _selection_hull(selection, registry)) is not None and hull.max_burn is not None]
    return min(burns) if burns else None


def _variant_weapon_range(hull: Hull, registry: Registry) -> float | None:
    ranges = [registry.weapons.by_id[weapon_id].range for variant in registry.variants_for_hull(hull.id) for weapon_id in variant.weapons_by_mount.values() if weapon_id in registry.weapons.by_id and registry.weapons.by_id[weapon_id].range is not None]
    return _mean(ranges)


def _fleet_variant_weapon_range(selections: tuple[FleetSelection, ...], registry: Registry) -> float | None:
    ranges = [_selection_weapon_range(selection, registry) for selection in selections for _ in range(selection.count)]
    return _mean([item for item in ranges if item is not None])


def _selection_hull(selection: FleetSelection, registry: Registry) -> Hull | None:
    if selection.variant_id:
        variant = registry.variants.by_id.get(selection.variant_id)
        return registry.hulls.by_id.get(variant.hull_id or "") if variant else None
    return registry.hulls.by_id.get(selection.hull_id or "")


def _selection_weapon_range(selection: FleetSelection, registry: Registry) -> float | None:
    if selection.variant_id:
        variant = registry.variants.by_id.get(selection.variant_id)
        ranges = [registry.weapons.by_id[weapon_id].range for weapon_id in variant.weapons_by_mount.values() if weapon_id in registry.weapons.by_id and registry.weapons.by_id[weapon_id].range is not None] if variant else []
        return _mean(ranges)
    hull = _selection_hull(selection, registry)
    return _variant_weapon_range(hull, registry) if hull else None


def _fleet_declared_traits(selections: tuple[FleetSelection, ...], registry: Registry) -> tuple[str, ...]:
    return tuple(sorted({trait for selection in selections if (hull := _selection_hull(selection, registry)) is not None for trait in _declared_traits(hull)}))


def _declared_traits(hull: Hull) -> tuple[str, ...]:
    hints = {hint.upper() for hint in hull.hull_hints}
    return ("PHASE_HULL_HINT",) if "PHASE" in hints else ()


def _phase_trait_match(fleet_traits: tuple[FleetCompositionTrait, ...], hull: Hull) -> float | None:
    phase = next((trait for trait in fleet_traits if trait.name == "PHASE_ORIENTED"), None)
    if phase is None or phase.score is None or phase.score <= 0.0:
        return None
    return 1.0 if "PHASE_HULL_HINT" in _declared_traits(hull) else 0.0


def _fleet_sensor_profile(selections: tuple[FleetSelection, ...], registry: Registry) -> float | None:
    values = [hull.sensor_profile for selection in selections if (hull := _selection_hull(selection, registry)) is not None for _ in range(selection.count)]
    return _mean([value for value in values if value is not None])


def _composition_traits(resolved: list[tuple[Hull, tuple[Variant, ...] | None]], vectors: list[CapabilityVector], doctrines: list[CombatDoctrineProfile]) -> tuple[FleetCompositionTrait, ...]:
    if not resolved:
        return ()
    direct_phase = [1.0 if "PHASE_HULL_HINT" in _declared_traits(hull) else 0.0 for hull, _ in resolved]
    sensor_values = [hull.sensor_profile for hull, _ in resolved if hull.sensor_profile is not None]
    civilian = [1.0 if "CIVILIAN" in {hint.upper() for hint in hull.hull_hints} else 0.0 for hull, _ in resolved]
    traits: list[FleetCompositionTrait] = [
        FleetCompositionTrait("PHASE_ORIENTED", round(_mean(direct_phase, 0.0) or 0.0, 6), 1.0, (f"{int(sum(direct_phase))}/{len(direct_phase)} selected locked instances have a direct PHASE hull hint.",)),
        FleetCompositionTrait("CIVILIAN_HEAVY", round(_mean(civilian, 0.0) or 0.0, 6), 1.0, (f"{int(sum(civilian))}/{len(civilian)} selected locked instances have a direct CIVILIAN hull hint.",)),
    ]
    if sensor_values:
        traits.append(FleetCompositionTrait("SENSOR_PROFILE", round(_mean(sensor_values, 0.0) or 0.0, 6), len(sensor_values) / len(resolved), (f"Direct normalized sensor-profile values are available for {len(sensor_values)}/{len(resolved)} selected locked instances.",)))
    for name in ("CARRIER_PROJECTION", "MISSILE_PROJECTION", "MOBILITY"):
        values = [vector.dimensions[name] for vector in vectors if vector.dimensions[name].score is not None]
        if values:
            traits.append(FleetCompositionTrait({"CARRIER_PROJECTION": "CARRIER_ORIENTED", "MISSILE_PROJECTION": "MISSILE_ORIENTED", "MOBILITY": "HIGH_MOBILITY"}[name], round(_mean([item.score or 0.0 for item in values], 0.0) or 0.0, 6), round(_mean([item.confidence for item in values], 0.0) or 0.0, 6), (f"Derived from normalized {name} capability across selected locked instances.",)))
    for label, name in (("LINE_ANCHOR", "HEAVY_LINE"), ("ARTILLERY", "LONG_RANGE"), ("STRIKE", "SHORT_RANGE_ASSAULT")):
        values = [doctrine.battlefield_function.scores.get(label, 0.0) for doctrine in doctrines]
        traits.append(FleetCompositionTrait(name, round(_mean(values, 0.0) or 0.0, 6), round(_mean([doctrine.battlefield_function.confidence for doctrine in doctrines], 0.0) or 0.0, 6), (f"Derived from normalized battlefield-function evidence for {label}.",)))
    return tuple(traits)


def _composition_synergy(traits: tuple[FleetCompositionTrait, ...], phase_match: float | None, sensor_match: float | None, burn_match: float | None, vector: CapabilityVector, values: dict[str, float]) -> CompositionSynergyProfile:
    lookup = {trait.name: trait for trait in traits}
    mobility = lookup.get("HIGH_MOBILITY")
    candidate_mobility = vector.dimensions["MOBILITY"]
    mobility_match = None if mobility is None or mobility.score is None or candidate_mobility.score is None else _clamp(1 - abs(mobility.score - candidate_mobility.score))
    parts = [item for item in (phase_match, sensor_match, burn_match, mobility_match) if item is not None]
    confidence_parts = [lookup["PHASE_ORIENTED"].confidence] if phase_match is not None and "PHASE_ORIENTED" in lookup else []
    if sensor_match is not None and "SENSOR_PROFILE" in lookup: confidence_parts.append(lookup["SENSOR_PROFILE"].confidence)
    if burn_match is not None: confidence_parts.append(1.0)
    if mobility_match is not None: confidence_parts.append(candidate_mobility.confidence * (mobility.confidence if mobility else 0.0))
    evidence = ["Composition synergy uses only available static/direct evidence; unavailable dimensions are ignored, not treated as mismatch."]
    for label, value in (("phase", phase_match), ("sensor", sensor_match), ("base burn", burn_match), ("mobility character", mobility_match)):
        if value is not None: evidence.append(f"{label} match={value:.3f}.")
    return CompositionSynergyProfile(phase_match, sensor_match, burn_match, mobility_match, round(_mean(parts, 0.0) or 0.0, 6), round(_mean(confidence_parts, 0.0) or 0.0, 6), tuple(evidence))


def _support_purposes(supports: tuple[str, ...]) -> tuple[str, ...]:
    mapping = {"SUSTAINED_PRESSURE": "SUSTAINED_FIRE", "PD_SCREENING": "PD_SCREEN", "FIGHTER_INTERCEPTION": "FIGHTER_SCREEN", "KINETIC_PRESSURE": "SHIELD_PRESSURE", "ARMOR_BREAKING": "ARMOR_BREAKER", "FINISHING_POWER": "FINISHER", "MISSILE_PROJECTION": "MISSILE_SUPPORT", "CARRIER_PROJECTION": "CARRIER_SUPPORT", "MOBILITY": "PURSUIT_SUPPORT", "PURSUIT": "PURSUIT_SUPPORT", "ARMOR_TANKING": "LINE_ANCHOR", "SHIELD_TANKING": "LINE_ANCHOR", "FREIGHTER": "CARGO_SUPPORT", "TANKER": "FUEL_SUPPORT", "SALVAGE_SUPPORT": "SALVAGE_SUPPORT", "SURVEY_SUPPORT": "SURVEY_SUPPORT"}
    return tuple(sorted({mapping[name] for name in supports if name in mapping}))


def support_fit_profile(recommendation: FleetSupportRecommendation) -> tuple[str, str] | None:
    """Choose an existing bounded generator profile for a ranked purpose.

    Logistics-only purposes intentionally return ``None``: the current
    generator has no logistics-specific fit profile, and substituting a combat
    profile would fabricate a mission it does not model.
    """
    for purpose in recommendation.support_purposes:
        profile = _SUPPORT_FIT_PROFILE_BY_PURPOSE.get(purpose)
        if profile is not None:
            return purpose, profile
    return None


def _mean(values: list[float], default: float | None = None) -> float | None:
    return sum(values) / len(values) if values else default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
