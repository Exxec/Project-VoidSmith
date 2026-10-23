"""Gap recommendation scenario responsibility; algorithms preserved from the original facade."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from starsector_variant_generator.analysis.build_archetypes import BuildArchetypeProfile, infer_build_archetypes
from starsector_variant_generator.analysis.capability_vector import CapabilityVector, infer_hull_capability_vector
from starsector_variant_generator.analysis.mechanical_archetypes import MechanicalArchetypeProfile, infer_mechanical_archetypes
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Faction
from starsector_variant_generator.core.registry import Registry
from .explanations import BuildWhyNotExplanation, explain_build_candidate
from .models import GapRecommendationResult

# --- Scenario-Aware Recommendations (ROADMAP.md Phase 31, Charter -------
# Priority 9) ---------------------------------------------------------------
#
# Extends ranking from `Hull + BuildArchetype` to `Hull + BuildArchetype +
# ScenarioObjective` units, e.g. "this hull is a good RAIDING pick," not
# just "this hull is a good LINE_ARTILLERY pick." Everything below is
# strictly additive: it reads the ALREADY-RANKED, ALREADY-LEGAL
# Native/Retrofit/Acquisition records a `GapRecommendationResult` already
# carries (never recomputes or reorders them) and produces a brand new,
# separately-reported category, every record of which is tagged
# `SCENARIO_RECOMMENDATION_KIND` ("INFERRED_SCENARIO_OPTION") so it can
# never be confused with the mature, direct role-gap evidence the rest of
# this module produces. `recommend_gap_solutions` itself is left completely
# unmodified -- nothing here is wired into its output; a caller who wants
# scenario options calls `recommend_scenario_solutions` explicitly with an
# already-computed `GapRecommendationResult`.
#
# Naming note: `analysis/scenario_objectives.py::ScenarioObjective` is an
# unrelated, earlier-landed concept (which generation-time coverage
# objectives, e.g. LINE_HOLD/BREAKTHROUGH, a single build archetype already
# supports -- a generation-presentation detail). `ScenarioCategory` below is
# a different, new concept (faction-level recommendation scenario, e.g.
# RAIDING/DEFENSE) and deliberately uses a different name to avoid
# colliding with that existing, actively-imported class.

SCENARIO_RECOMMENDATION_KIND = "INFERRED_SCENARIO_OPTION"


class ScenarioCategory(StrEnum):
    """A small, explicitly synthetic set of fleet-deployment scenario intents.

    Checked against real data before inventing this: no parseable Starsector
    hull/variant/faction field in this project's schema records a
    documented "mission role," "deployment points," or comparable in-game
    scenario tag (see `DATA_SCHEMA.md`; the closest real data is the hull
    CSV `hints` column already consumed by `classify_civilian_role`/
    `infer_mechanical_archetypes`, which covers civilian/logistics roles
    only, not combat deployment intent). This set is therefore an explicit,
    honestly-labeled heuristic taxonomy -- never a documented game
    mechanic, never legality, never evidence -- kept deliberately small.
    Every recommendation this taxonomy produces carries
    `SCENARIO_RECOMMENDATION_KIND` so it is structurally impossible to
    mistake for evidence-based output.

    ROADMAP.md Phase 40 (user "Phase 4") extended the original four
    (RAIDING/DEFENSE/ESCORT/PATROL, Phase 31) with nine further categories,
    each backed by a genuinely distinct real signal from
    `analysis/capability_vector.py::CapabilityVector` (real, mostly
    existing-variant-mounted-weapon evidence, distinct from the purely
    structural `MechanicalArchetypeProfile`/`BuildArchetypeProfile` fields
    the original four use exclusively) and/or `HullFeatureVector` fields --
    see `_scenario_fit_score`'s per-branch comments for the exact citation
    per category. Two of the task's eleven suggested categories were
    deliberately NOT added: BREAKTHROUGH (its natural formula -- HE
    burst/armor-breaking plus mobility -- would have reused ANTI_ARMOR's own
    `ARMOR_BREAKING`/`STRIKER` terms at similar weights, producing a
    near-duplicate ranking under a different name, which this phase's own
    instruction explicitly forbids) and ENDURANCE (no real per-hull ammo/
    fight-duration-endurance signal exists in this project's current schema
    distinct from what LINE_HOLDING's `SUSTAINED_PRESSURE` or DEFENSE's
    survivability terms already cover; a formula built only from those same
    inputs would again just be a relabeled duplicate).
    """

    RAIDING = "RAIDING"
    DEFENSE = "DEFENSE"
    ESCORT = "ESCORT"
    PATROL = "PATROL"
    ANTI_ARMOR = "ANTI_ARMOR"
    ANTI_SHIELD = "ANTI_SHIELD"
    LINE_HOLDING = "LINE_HOLDING"
    LONG_RANGE_PRESSURE = "LONG_RANGE_PRESSURE"
    MISSILE_STRIKE = "MISSILE_STRIKE"
    PD_SCREEN = "PD_SCREEN"
    CARRIER_SUPPORT = "CARRIER_SUPPORT"
    PURSUIT = "PURSUIT"
    LOW_COST_REFIT_FRIENDLY = "LOW_COST_REFIT_FRIENDLY"


def _bucket(value: str | None, weights: dict[str, float]) -> float:
    return weights.get(value or "", 0.0)


def _capability_dim(capability: CapabilityVector | None, name: str) -> tuple[float, str]:
    """Real `CapabilityVector` dimension value plus a citable evidence line.

    Returns `(0.0, "...no resolved evidence...")` rather than fabricating a
    value when the dimension has no score (e.g. a weapon-mounted-evidence
    dimension like `ARMOR_BREAKING`/`KINETIC_PRESSURE` for a hull with no
    resolved existing-variant weapons) -- the same honest-absence discipline
    the rest of this module follows.
    """
    if capability is None:
        return 0.0, f"capability_vector unavailable for {name} (no registry/hull context supplied)."
    evidence = capability.dimensions.get(name)
    if evidence is None or evidence.score is None:
        availability = evidence.availability if evidence is not None else "UNKNOWN"
        return 0.0, f"capability_vector[{name}]: no resolved evidence (availability={availability})."
    return evidence.score, f"capability_vector[{name}]: score={evidence.score:.6f}, confidence={evidence.confidence:.3f}, availability={evidence.availability}."


def _op_scale(value: float | None, reference: float = 200.0) -> float:
    # Mirrors `analysis/mechanical_archetypes.py::infer_mechanical_archetypes`'s
    # own `op = _scale(f.ordnance_points, 200.0)` normalization exactly, so
    # this module's OP-based term uses the same reference the rest of the
    # codebase already established rather than inventing a new constant.
    return max(0.0, min(1.0, float(value) / reference)) if value is not None else 0.0


def _scenario_fit_score(
    scenario: ScenarioCategory,
    build: BuildArchetypeProfile,
    mechanical: MechanicalArchetypeProfile,
    capability: CapabilityVector | None = None,
) -> tuple[float, tuple[str, ...]]:
    """A bounded [0.0, 1.0] heuristic scenario-fit strength.

    Every input term is a real, already-computed structural/build/capability
    signal (`MechanicalArchetypeProfile.compatibility_scores`,
    `BuildArchetypeProfile`'s own tactical/range/survivability/flux posture
    fields, and -- for the nine categories added in ROADMAP.md Phase 40 --
    `CapabilityVector` dimensions, which additionally fold in real
    existing-variant mounted-weapon evidence such as damage type and mount
    type) -- nothing here invents a new game fact. `capability` is optional
    and defaults to `None` so the original four categories (RAIDING/
    DEFENSE/ESCORT/PATROL, ROADMAP.md Phase 31), which never reference it,
    are computed byte-identically to before this phase. The *combination
    weights* below are a first-pass, honestly-labeled heuristic overlay
    (the same status as this module's other first-pass weights, e.g.
    `gap_strong_threshold`), never a citable game mechanic, and are never
    consulted by legality or by the mature Native/Retrofit/Acquisition
    ranking this function only reads from.
    """
    scores = mechanical.compatibility_scores
    style = build.tactical_style
    target_range = build.target_range
    survivability = build.survivability_posture
    flux = build.flux_posture
    priorities = set(build.equipment_priorities)
    # Explicitly `tuple[str, ...]`, not the 2-element shape inferred from
    # this literal alone: every scenario branch below appends further
    # evidence lines onto this same name (`evidence = evidence + (...)`,
    # 1 to 2 more strings depending on the category), which is a real,
    # deliberate variable-length accumulation matching this function's
    # `tuple[str, ...]` return type -- not an inconsistent shape.
    evidence: tuple[str, ...] = (
        f"tactical_style={style}; target_range={target_range}; survivability_posture={survivability}; flux_posture={flux}; equipment_priorities={build.equipment_priorities!r}",
        (
            f"mechanical_archetype_scores: STRIKER={scores['STRIKER']:.3f}, SKIRMISHER={scores['SKIRMISHER']:.3f}, "
            f"ARMOR_BRAWLER={scores['ARMOR_BRAWLER']:.3f}, SHIELD_BRAWLER={scores['SHIELD_BRAWLER']:.3f}, "
            f"LINE_SHIP={scores['LINE_SHIP']:.3f}, PD_ESCORT={scores['PD_ESCORT']:.3f}"
        ),
    )
    if scenario == ScenarioCategory.RAIDING:
        # Mobility/strike-oriented, short-range, willing to forgo maximum
        # survivability for the ability to disengage -- a raider that can't
        # leave is just a slow brawler.
        score = (
            0.35 * scores["STRIKER"] + 0.25 * scores["SKIRMISHER"]
            + 0.20 * (1.0 if style == "FLANK_AND_COMMIT" else 0.0)
            + 0.10 * (1.0 if target_range == "SHORT" else 0.0)
            + 0.10 * _bucket(survivability, {"MEDIUM": 1.0, "HIGH": 0.5})
        )
    elif scenario == ScenarioCategory.DEFENSE:
        # Hold-the-line, maximum survivability, conservative flux posture.
        score = (
            0.30 * scores["ARMOR_BRAWLER"] + 0.25 * scores["SHIELD_BRAWLER"]
            + 0.20 * (1.0 if style == "HOLD_LINE" else 0.0)
            + 0.15 * _bucket(survivability, {"MAXIMUM": 1.0, "HIGH": 0.7, "MEDIUM": 0.3})
            + 0.10 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
        )
    elif scenario == ScenarioCategory.ESCORT:
        # Point-defense/screening for allied ships, with enough mobility to
        # reposition alongside whatever it is escorting.
        score = (
            0.40 * scores["PD_ESCORT"] + 0.20 * (1.0 if style == "SCREEN_ALLIES" else 0.0)
            + 0.15 * (1.0 if "PD" in priorities else 0.0) + 0.15 * scores["SKIRMISHER"]
            + 0.10 * (1.0 if target_range in ("SHORT", "MEDIUM") else 0.0)
        )
    elif scenario == ScenarioCategory.PATROL:
        # General-purpose sustained-coverage posture: moderate everything,
        # line-ship/skirmisher qualities rather than a specialist extreme.
        score = (
            0.30 * scores["LINE_SHIP"] + 0.25 * scores["SKIRMISHER"]
            + 0.15 * (1.0 if style in ("STAND_OFF", "HOLD_LINE") else 0.0)
            + 0.15 * (1.0 if target_range == "MEDIUM" else 0.0)
            + 0.15 * _bucket(survivability, {"HIGH": 1.0, "MEDIUM": 0.7, "MAXIMUM": 0.5})
        )
    elif scenario == ScenarioCategory.ANTI_ARMOR:
        # Real evidence: `CapabilityVector.ARMOR_BREAKING`, the fraction of
        # this hull's real existing-variant mounted weapons dealing HE
        # damage (armor's specific counter in Starsector's damage-type
        # system) -- distinct from every original-four term, none of which
        # reference weapon damage type at all. Structural STRIKER/
        # ARMOR_BRAWLER terms reflect the survivability/mobility needed to
        # close to an HE weapon's effective range and stay there.
        armor_breaking_value, armor_breaking_evidence = _capability_dim(capability, "ARMOR_BREAKING")
        score = 0.55 * armor_breaking_value + 0.25 * scores["STRIKER"] + 0.20 * scores["ARMOR_BRAWLER"]
        evidence = evidence + (armor_breaking_evidence,)
    elif scenario == ScenarioCategory.ANTI_SHIELD:
        # Real evidence: `CapabilityVector.KINETIC_PRESSURE`, the real
        # existing-variant mounted-weapon kinetic-damage fraction (shields'
        # specific counter) -- the direct complement of ANTI_ARMOR above,
        # backed by a different real weapon-damage-type fact, not a
        # relabeling of it. LINE_SHIP/conservative-flux terms reflect the
        # sustained fire needed to keep shields down rather than a single
        # burst.
        kinetic_value, kinetic_evidence = _capability_dim(capability, "KINETIC_PRESSURE")
        score = 0.55 * kinetic_value + 0.25 * scores["LINE_SHIP"] + 0.20 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.6})
        evidence = evidence + (kinetic_evidence,)
    elif scenario == ScenarioCategory.LINE_HOLDING:
        # Real evidence: `CapabilityVector.SUSTAINED_PRESSURE` (LINE_SHIP
        # structural compatibility blended with documented flux
        # dissipation) -- an OUTPUT-endurance signal, distinct from
        # DEFENSE's SURVIVABILITY-weighted ARMOR_BRAWLER/SHIELD_BRAWLER
        # terms: a ship can hold a line by out-dissipating incoming flux
        # while dishing out sustained damage even without DEFENSE's own
        # maximum-tankiness profile.
        sustained_value, sustained_evidence = _capability_dim(capability, "SUSTAINED_PRESSURE")
        score = (
            0.50 * sustained_value + 0.25 * (1.0 if style == "HOLD_LINE" else 0.0)
            + 0.15 * scores["LINE_SHIP"]
            + 0.10 * _bucket(survivability, {"HIGH": 1.0, "MAXIMUM": 0.8, "MEDIUM": 0.5})
        )
        evidence = evidence + (sustained_evidence,)
    elif scenario == ScenarioCategory.LONG_RANGE_PRESSURE:
        # Real evidence: `CapabilityVector.LONG_RANGE_PRESSURE` (ARTILLERY
        # structural compatibility blended with the real existing-variant
        # long-range-weapon-band mounted fraction) -- the ARTILLERY
        # mechanical archetype is not referenced by any of the original
        # four categories at all.
        long_range_value, long_range_evidence = _capability_dim(capability, "LONG_RANGE_PRESSURE")
        score = (
            0.50 * long_range_value + 0.20 * (1.0 if style == "STAND_OFF" else 0.0)
            + 0.20 * (1.0 if target_range == "LONG" else 0.0)
            + 0.10 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
        )
        evidence = evidence + (long_range_evidence,)
    elif scenario == ScenarioCategory.MISSILE_STRIKE:
        # Real evidence: `CapabilityVector.MISSILE_PROJECTION` (MISSILE_SUPPORT
        # structural compatibility blended with the real existing-variant
        # MISSILE-mount-type fraction) plus `BURST_STRIKE` (alpha-strike
        # capacity) -- neither is referenced by the original four.
        missile_value, missile_evidence = _capability_dim(capability, "MISSILE_PROJECTION")
        burst_value, burst_evidence = _capability_dim(capability, "BURST_STRIKE")
        score = (
            0.50 * missile_value + 0.20 * (1.0 if style == "SALVO_SUPPORT" else 0.0)
            + 0.15 * (1.0 if "MISSILES" in priorities else 0.0) + 0.15 * burst_value
        )
        evidence = evidence + (missile_evidence, burst_evidence)
    elif scenario == ScenarioCategory.PD_SCREEN:
        # Real evidence: `CapabilityVector.PD_SCREENING` (PD_ESCORT structural
        # compatibility blended with the real existing-variant PD-tagged
        # mounted-weapon fraction) plus `FIGHTER_INTERCEPTION` (fighter-bay
        # interceptor capacity). Deliberately weighted AWAY from ESCORT's own
        # mobility/`SCREEN_ALLIES`-style/short-range terms (a heavy,
        # stationary PD platform holding a formation's flank is a genuinely
        # different real fit than a fast escort matching a convoy's speed),
        # so a hull can rank well for one without ranking well for the other.
        pd_value, pd_evidence = _capability_dim(capability, "PD_SCREENING")
        intercept_value, intercept_evidence = _capability_dim(capability, "FIGHTER_INTERCEPTION")
        score = (
            0.45 * pd_value + 0.25 * intercept_value
            + 0.15 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
            + 0.15 * (1.0 if style == "HOLD_LINE" else 0.0)
        )
        evidence = evidence + (pd_evidence, intercept_evidence)
    elif scenario == ScenarioCategory.CARRIER_SUPPORT:
        # Real evidence: `CapabilityVector.CARRIER_PROJECTION` (the best of
        # LIGHT_CARRIER/HEAVY_CARRIER/BATTLECARRIER structural compatibility)
        # plus `FIGHTER_INTERCEPTION` -- none of the carrier mechanical
        # archetypes are referenced anywhere in the original four categories.
        carrier_value, carrier_evidence = _capability_dim(capability, "CARRIER_PROJECTION")
        intercept_value, intercept_evidence = _capability_dim(capability, "FIGHTER_INTERCEPTION")
        score = 0.55 * carrier_value + 0.25 * intercept_value + 0.20 * (1.0 if style == "STAND_OFF" else 0.0)
        evidence = evidence + (carrier_evidence, intercept_evidence)
    elif scenario == ScenarioCategory.PURSUIT:
        # Real evidence: `CapabilityVector.PURSUIT` and `.MOBILITY`, both of
        # which fold in VERIFIED adapter-derived existing-variant effective
        # max_speed (`analysis/mobility_stats.py`, real applied hullmod
        # effects) when available -- a strictly stronger, independently
        # verified mobility signal than RAIDING's purely qualitative
        # structural/posture check, and RAIDING never reads
        # `CapabilityVector` at all. A hull can rank well for RAIDING
        # (short-range strike posture) without a verified mobility edge, or
        # rank well for PURSUIT (proven speed to run a target down) without
        # RAIDING's short-range/FLANK_AND_COMMIT requirement.
        pursuit_value, pursuit_evidence = _capability_dim(capability, "PURSUIT")
        mobility_value, mobility_evidence = _capability_dim(capability, "MOBILITY")
        score = (
            0.45 * pursuit_value + 0.30 * mobility_value + 0.15 * scores["STRIKER"]
            + 0.10 * (1.0 if target_range in ("MEDIUM", "LONG") else 0.0)
        )
        evidence = evidence + (pursuit_evidence, mobility_evidence)
    else:  # LOW_COST_REFIT_FRIENDLY
        # Real evidence: `HullFeatureVector.ordnance_points` (inverted --
        # lower OP is cheaper to build/supply/refit within budget, using the
        # exact same 200.0 reference `infer_mechanical_archetypes` already
        # normalizes OP against) and `.existing_variant_count` (a hull with
        # more real existing variants has more real starting points a Refit
        # Assistant pass can cheaply improve). This is a purely economic
        # axis -- OP cost and variant availability -- that no other category
        # in this module references at any weight, so it cannot duplicate
        # another category's ranking under a different name.
        op_value = 1.0 - _op_scale(mechanical.feature_vector.ordnance_points)
        variant_availability = min(1.0, mechanical.feature_vector.existing_variant_count / 3.0)
        score = (
            0.50 * op_value + 0.30 * variant_availability
            + 0.20 * _bucket(flux, {"CONSERVATIVE": 1.0, "BALANCED": 0.5})
        )
        evidence = evidence + (
            (
                f"ordnance_points={mechanical.feature_vector.ordnance_points!r} (inverted op_value={op_value:.6f}); "
                f"existing_variant_count={mechanical.feature_vector.existing_variant_count!r} (variant_availability={variant_availability:.6f})."
            ),
        )
    return round(max(0.0, min(1.0, score)), 6), evidence


@dataclass(frozen=True)
class ScenarioRecommendation:
    """A heuristic `INFERRED_SCENARIO_OPTION` layered on top of one of the
    three real, evidence-based recommendation legs' own already-ranked
    `Hull + BuildArchetype` candidate. NEVER a replacement for, or dilution
    of, that leg's own `recommendation_score`/`confidence`:
    `base_recommendation_score`/`source_leg` cite exactly which real
    recommendation this option is layered onto, unchanged.
    """

    role: str
    scenario: str  # ScenarioCategory value
    hull_id: str
    build_archetype_id: str
    source_leg: str  # "NATIVE" | "RETROFIT" | "ACQUISITION" -- which real leg's own ranked candidate this reuses
    source_variant_id: str | None  # set only when source_leg == "RETROFIT"
    base_recommendation_score: float | None  # the cited leg's own real, unmodified recommendation_score
    scenario_fit_score: float  # 0.0-1.0 heuristic-only; never evidence, never legality
    scenario_recommendation_score: float  # base_recommendation_score * scenario_fit_score; ranking is local to this (role, scenario) shortlist only, never compared across legs or scenarios
    rank: int
    confidence: float  # bounded by scenario_confidence_cap -- a heuristic overlay is never reported as fully certain
    reason: str
    scenario_fit_evidence: tuple[str, ...] = ()
    kind: str = SCENARIO_RECOMMENDATION_KIND  # always "INFERRED_SCENARIO_OPTION"
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


def recommend_scenario_solutions(
    faction: Faction,
    registry: Registry,
    gap_result: GapRecommendationResult,
    scenario: ScenarioCategory,
    heuristic_set: str = "baseline_0.2",
    roles: tuple[str, ...] | None = None,
) -> dict[str, tuple[ScenarioRecommendation, ...]]:
    """Layer a heuristic scenario-fit overlay on top of `gap_result`'s
    ALREADY-RANKED Native/Retrofit/Acquisition `Hull + BuildArchetype`
    candidates for the given `scenario`.

    This never recomputes or reorders those legs: it reads their stored
    `hull_id`/`build_archetype_id`/`recommendation_score`/`confidence`
    directly (the same "read the stored evidence, don't reinfer"
    discipline `explain_build_candidate` already follows) and only ever
    ADDS a new, separately-reported `INFERRED_SCENARIO_OPTION` category
    alongside them -- `gap_result` itself is untouched. A hull/build pair
    that does not clear `scenario_fit_min_signal` is simply absent from the
    result, never padded in -- the same "no fabricated recommendation"
    discipline `unaddressed_gaps` already follows for the native leg.

    `roles` restricts the roles considered (default: every role appearing
    in any of the three legs of `gap_result`).
    """
    heuristics = get_heuristic_set(heuristic_set).values
    min_signal = heuristics.get("scenario_fit_min_signal", 0.30)
    confidence_cap = heuristics.get("scenario_confidence_cap", 0.75)
    max_recommendations = int(heuristics.get("scenario_recommendation_count", heuristics.get("gap_recommendation_count", 3.0)))

    target_roles = roles if roles is not None else tuple(sorted(
        set(gap_result.native_recommendations) | set(gap_result.retrofit_recommendations) | set(gap_result.acquisition_recommendations)
    ))

    results: dict[str, tuple[ScenarioRecommendation, ...]] = {}
    for role in target_roles:
        candidates: list[tuple[float, str, str, str, str | None, float | None, float, float, tuple[str, ...]]] = []
        seen: set[tuple[str, str, str]] = set()
        for leg_name, leg_items in (
            ("NATIVE", gap_result.native_recommendations.get(role, ())),
            ("RETROFIT", gap_result.retrofit_recommendations.get(role, ())),
            ("ACQUISITION", gap_result.acquisition_recommendations.get(role, ())),
        ):
            for item in leg_items:
                if not item.build_archetype_id:
                    continue  # no BuildArchetype -- nothing for a Hull + BuildArchetype + ScenarioObjective unit to attach to
                key = (item.hull_id, item.build_archetype_id, leg_name)
                if key in seen:
                    continue
                seen.add(key)
                hull = registry.hulls.by_id.get(item.hull_id)
                if hull is None:
                    continue
                build = next((b for b in infer_build_archetypes(hull, registry, heuristic_set) if b.build_id == item.build_archetype_id), None)
                if build is None:
                    continue
                mechanical = infer_mechanical_archetypes(hull, registry)
                capability = infer_hull_capability_vector(hull, registry)
                fit_score, fit_evidence = _scenario_fit_score(scenario, build, mechanical, capability)
                if fit_score < min_signal:
                    continue
                base_score = item.recommendation_score if item.recommendation_score is not None else item.capability_score
                scenario_score = round((base_score or 0.0) * fit_score, 6)
                confidence = round(min(item.confidence, build.confidence, confidence_cap), 3)
                variant_id = getattr(item, "variant_id", None)
                candidates.append((scenario_score, item.hull_id, build.build_id, leg_name, variant_id, base_score, fit_score, confidence, fit_evidence))
        candidates.sort(key=lambda entry: (-entry[0], entry[1], entry[3], entry[2]))
        shortlisted = candidates[:max_recommendations]
        results[role] = tuple(
            ScenarioRecommendation(
                role=role, scenario=scenario.value, hull_id=hull_id, build_archetype_id=build_id,
                source_leg=source_leg, source_variant_id=variant_id,
                base_recommendation_score=base_score, scenario_fit_score=fit_score,
                scenario_recommendation_score=scenario_score, rank=index + 1, confidence=confidence,
                reason=(
                    f"Heuristic scenario-fit overlay (not evidence-based): {scenario.value} fit score {fit_score:.3f} "
                    f"applied to the existing {source_leg} leg's own recommendation_score "
                    f"{(base_score if base_score is not None else 0.0):.6f} for {hull_id!r} ({build_id})."
                ),
                scenario_fit_evidence=fit_evidence,
            )
            for index, (scenario_score, hull_id, build_id, source_leg, variant_id, base_score, fit_score, confidence, fit_evidence) in enumerate(shortlisted)
        )
    return results


def scenario_fits_for_hull(
    faction: Faction,
    registry: Registry,
    gap_result: GapRecommendationResult,
    hull_id: str,
    heuristic_set: str = "baseline_0.2",
    roles: tuple[str, ...] | None = None,
    categories: tuple[ScenarioCategory, ...] | None = None,
) -> dict[str, tuple[ScenarioRecommendation, ...]]:
    """ROADMAP.md Phase 40 ("multiple genuinely different best builds per
    hull"): for one specific hull, every scenario category (default: all of
    `ScenarioCategory`) it has at least one real, shortlisted
    `INFERRED_SCENARIO_OPTION` recommendation for, across the requested
    roles (default: every role appearing in `gap_result`).

    `recommend_scenario_solutions` already supports "multiple best builds
    per hull" naturally: it is parameterized by `scenario`, and each call is
    an independent ranking over the same real Native/Retrofit/Acquisition
    evidence, so the exact same hull can legitimately receive a different
    top `Hull + BuildArchetype` for RAIDING than for DEFENSE -- there was
    never a single forced overall ranking to begin with. What was missing
    was a convenience for a caller that wants "every category this hull is
    a genuine option for" without hand-looping `ScenarioCategory` and
    filtering by `hull_id` itself. This function does exactly that and
    nothing more: it calls the real, unmodified `recommend_scenario_solutions`
    once per category and keeps only that hull's own entries -- it
    introduces no new ranking, scoring, or selection logic, and
    `recommend_scenario_solutions`'s own behavior/signature is completely
    unchanged by this addition.

    Note this reads each category's real, already-shortlisted
    (`scenario_recommendation_count`-capped, diversity-selected) results --
    the same "recommended" convention every other leg in this module uses --
    not every raw candidate merely above `scenario_fit_min_signal` before
    that cap. A hull that clears the signal floor but not the shortlist cap
    for a given (role, scenario) is reported by `explain_scenario_candidate`
    (`considered=True, recommended=False`), not by this function.
    """
    categories = categories or tuple(ScenarioCategory)
    result: dict[str, tuple[ScenarioRecommendation, ...]] = {}
    for scenario in categories:
        by_role = recommend_scenario_solutions(faction, registry, gap_result, scenario, heuristic_set, roles=roles)
        matches = tuple(item for entries in by_role.values() for item in entries if item.hull_id == hull_id)
        if matches:
            result[scenario.value] = matches
    return result


@dataclass(frozen=True)
class ScenarioWhyNotExplanation:
    """Why-Not counterpart for a heuristic `INFERRED_SCENARIO_OPTION`
    recommendation. ALWAYS textually and structurally distinguished from
    `explain_build_candidate`'s evidence-based `BuildWhyNotExplanation`:
    `reason` states plainly that scenario fit is a heuristic overlay, never
    a documented game mechanic or legality/evidence claim, and `underlying`
    carries the real evidence-based Hull + BuildArchetype explanation for
    the same (role, hull_id, build_archetype_id) as a separate, clearly
    labeled field rather than conflating the two.
    """

    role: str
    scenario: str
    hull_id: str
    build_archetype_id: str
    considered: bool  # was this hull/build pair present in ANY of the 3 underlying legs for this role?
    scenario_fit_score: float | None
    recommended: bool
    reason: str
    rank: int | None = None
    total_candidates: int = 0
    underlying: BuildWhyNotExplanation | None = None


def explain_scenario_candidate(
    faction: Faction,
    registry: Registry,
    gap_result: GapRecommendationResult,
    scenario: ScenarioCategory,
    role: str,
    hull_id: str,
    build_archetype_id: str,
    heuristic_set: str = "baseline_0.2",
) -> ScenarioWhyNotExplanation:
    """Answer "why wasn't <hull_id>/<build_archetype_id> given as an
    INFERRED_SCENARIO_OPTION for <scenario> on <role>?" using the exact
    same real ranking `recommend_scenario_solutions` already computes, so
    this cannot silently disagree with it -- the same discipline every
    other Why-Not function in this module follows. Deliberately a SEPARATE
    explanation type from `BuildWhyNotExplanation`: a scenario option is a
    heuristic overlay, never the same kind of claim as a direct
    evidence-based Native/Retrofit/Acquisition Why-Not.
    """
    underlying = explain_build_candidate(faction, registry, role, hull_id, build_archetype_id, heuristic_set)
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None or underlying.build is None:
        return ScenarioWhyNotExplanation(
            role, scenario.value, hull_id, build_archetype_id, False, None, False,
            "This heuristic scenario overlay only ever evaluates hull/build pairs the mechanical inference "
            "already supports; see `underlying` (the direct evidence-based Hull + BuildArchetype Why-Not) for "
            "why this pair is unavailable.",
            underlying=underlying,
        )
    ranked = recommend_scenario_solutions(faction, registry, gap_result, scenario, heuristic_set, roles=(role,))
    entries = ranked.get(role, ())
    matches = [item for item in entries if item.hull_id == hull_id and item.build_archetype_id == build_archetype_id]
    if matches:
        item = matches[0]
        reason = (
            f"Given as a heuristic INFERRED_SCENARIO_OPTION (not evidence-based): rank {item.rank} of "
            f"{len(entries)} scenario-fit candidates for {scenario.value}/{role}, scenario_fit_score={item.scenario_fit_score:.3f}."
        )
        return ScenarioWhyNotExplanation(role, scenario.value, hull_id, build_archetype_id, True, item.scenario_fit_score, True, reason, item.rank, len(entries), underlying)
    mechanical = infer_mechanical_archetypes(hull, registry)
    capability = infer_hull_capability_vector(hull, registry)
    fit_score, _ = _scenario_fit_score(scenario, underlying.build, mechanical, capability)
    heuristics = get_heuristic_set(heuristic_set).values
    min_signal = heuristics.get("scenario_fit_min_signal", 0.30)
    considered = any(
        recommendation.hull_id == hull_id and recommendation.build_archetype_id == build_archetype_id
        for leg in (gap_result.native_recommendations, gap_result.retrofit_recommendations, gap_result.acquisition_recommendations)
        for recommendation in leg.get(role, ())
    )
    if not considered:
        reason = (
            "Not considered for this heuristic scenario overlay: this Hull + BuildArchetype pair does not "
            "appear in any of the real Native/Retrofit/Acquisition recommendation lists for this role -- the "
            "scenario overlay only ever layers on top of those, it never introduces a new candidate."
        )
    elif fit_score < min_signal:
        reason = (
            f"Not given as an INFERRED_SCENARIO_OPTION: heuristic {scenario.value} scenario_fit_score "
            f"{fit_score:.3f} is below the minimum signal threshold {min_signal:.3f} -- a low heuristic fit, "
            "never a legality or evidence claim."
        )
    else:
        reason = (
            f"Not given as an INFERRED_SCENARIO_OPTION: heuristic scenario_fit_score {fit_score:.3f} clears "
            f"the minimum signal threshold but did not rank inside the top {len(entries)} shortlisted for this role/scenario."
        )
    return ScenarioWhyNotExplanation(role, scenario.value, hull_id, build_archetype_id, considered, fit_score, False, reason, None, len(entries), underlying)
