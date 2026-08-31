from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from starsector_variant_generator.analysis.civilian import (
    compute_derived_civilian_stats,
)
from starsector_variant_generator.analysis.classification import (
    classify_civilian_role,
    classify_weapon,
)
from starsector_variant_generator.analysis.combat_stats import (
    compute_derived_defense_stats,
)
from starsector_variant_generator.analysis.doctrine import (
    analyze_faction_doctrine,
    doctrine_match,
)
from starsector_variant_generator.analysis.flux_stats import compute_derived_flux_stats
from starsector_variant_generator.analysis.weapon_range_stats import (
    compute_derived_combat_stats,
)
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Faction, Hull, Variant, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.profiles.catalog import get_profile
from starsector_variant_generator.validation.legality import (
    LegalityResult,
    validate_variant,
)

_FLUX_TARGET_KEY = {"SAFE": "beginner_flux_target", "BALANCED": "balanced_flux_target", "AGGRESSIVE": "aggressive_flux_target"}

# Component weights as they were hardcoded prior to baseline_0.2. Preserved
# here, not deleted, so a candidate scored under baseline_0.1 (or any future
# heuristic_set that omits the weight_* keys) produces byte-identical output
# to the original formula -- old reports stay reproducible against the
# heuristic_set they actually recorded. See docs/ROADMAP.md Tier 2/3.
_LEGACY_WEIGHTS = {"range_coherence": 0.45, "op_efficiency": 0.20, "role_match": 0.35}


@dataclass(frozen=True)
class QualityAssessment:
    status: str
    final_score: float | None
    components: dict[str, float]
    explanation: tuple[str, ...]
    legality: LegalityResult


def _hullmod_adjusted_stat(
    stat_name: str, base_value: float | None, effective_value: float | None,
    applied_effects: tuple, stacking_notes: tuple[str, ...],
) -> tuple[float | None, str | None]:
    """Resolve one FLUX stat under baseline_0.8's opt-in hullmod-adjusted
    scoring, given `analysis/flux_stats.py::DerivedFluxStats` output for it.

    `effective_value` is None either because `base_value` itself is None
    (nothing to adjust) or because 2+ verified hullmods collided on this
    stat (compute_derived_flux_stats refuses to fabricate a combined
    number in that case -- see its own docstring). Both leave the raw
    base value in place; only the stacking case additionally explains why
    in the returned note, per this task's documented decision (a): fall
    back to the raw value, never guess a number between the two verified
    ones.
    """
    if base_value is None:
        return base_value, None
    if effective_value is None:
        stacking_note = next((note for note in stacking_notes if note.startswith(stat_name)), None)
        if stacking_note is None:
            return base_value, None
        return base_value, f"{stat_name} hullmod stacking is unrepresentable, using unmodified base value: {stacking_note}"
    if effective_value == base_value:
        return base_value, None
    hullmod_ids = ", ".join(effect.hullmod_id for effect in applied_effects if effect.stat == stat_name)
    return effective_value, f"{stat_name} hullmod-adjusted for scoring: {base_value:.2f} -> {effective_value:.2f} via {hullmod_ids}."


def _combat_adjusted_ranges(
    hull: Hull, variant: Variant, mount_ids: list[str], weapons: list[Weapon],
    heuristics: dict[str, float], registry: Registry | None,
) -> tuple[list[float | None], list[str]]:
    """Resolve each equipped weapon's range under baseline_0.9's opt-in
    COMBAT-hullmod-adjusted scoring, given
    analysis/weapon_range_stats.py::compute_derived_combat_stats output.

    Same fallback discipline as `_hullmod_adjusted_stat`, but per equipped
    mount instead of per hull-level stat: the verified COMBAT effect
    (targetingunit/dedicated_targeting_core) grants a percent range bonus to
    each individually equipped BALLISTIC/ENERGY weapon, not to a single
    hull-level number. A mount absent from `effective_range_by_mount` had no
    verified hullmod apply to it (e.g. any MISSILE-mount weapon, or a
    BALLISTIC/ENERGY mount with neither hullmod installed) -- its weapon's
    own base range is used unmodified, not a penalty, just not applicable.
    A mount mapped to `None` had 2+ verified hullmods collide on it
    (`compute_derived_combat_stats` refuses to fabricate a combined value,
    since the combination rule is undocumented and the two hullmods are
    mutually illegal in vanilla in the first place); that also falls back
    to the raw base range, with an explanation.
    """
    base_ranges = [weapon.range for weapon in weapons]
    if "combat_hullmod_adjustment_enabled" not in heuristics or registry is None:
        return base_ranges, []

    derived = compute_derived_combat_stats(hull, variant, registry)
    adjusted: list[float | None] = []
    adjustment_lines: dict[tuple[str, float, float], int] = {}
    stacking_notes_seen: set[str] = set()
    for mount_id, weapon, base_range in zip(mount_ids, weapons, base_ranges):
        if base_range is None or mount_id not in derived.effective_range_by_mount:
            adjusted.append(base_range)
            continue
        effective = derived.effective_range_by_mount[mount_id]
        if effective is None:
            stacking_note = next((note for note in derived.stacking_notes if note.startswith(f"mount {mount_id} ")), None)
            if stacking_note is not None and stacking_note not in stacking_notes_seen:
                stacking_notes_seen.add(stacking_note)
            adjusted.append(base_range)
            continue
        adjusted.append(effective)
        if effective != base_range:
            adjustment_lines[(weapon.id, base_range, effective)] = adjustment_lines.get((weapon.id, base_range, effective), 0) + 1

    notes: list[str] = []
    for stacking_note in stacking_notes_seen:
        notes.append(f"Weapon range hullmod stacking is unrepresentable, using unmodified base range: {stacking_note}")
    for (weapon_id, base_range, effective), count in adjustment_lines.items():
        suffix = f" (x{count} mounts)" if count > 1 else ""
        notes.append(f"{weapon_id} range hullmod-adjusted for scoring{suffix}: {base_range:.0f} -> {effective:.0f}.")
    return adjusted, notes


def _flux_component(
    hull: Hull, weapons: list[Weapon], heuristics: dict[str, float], flux_mode: str,
    hullmod_ids: tuple[str, ...] = (), registry: Registry | None = None,
) -> tuple[float | None, str | None]:
    if hull.flux_dissipation is None:
        return None, "Hull flux dissipation is not parsed: flux_sustainability is not evaluated."
    missing = [weapon.id for weapon in weapons if weapon.flux_per_second is None]
    if missing:
        return None, f"Flux data missing for mounted weapon(s) {', '.join(sorted(missing))}: flux_sustainability is not evaluated."

    flux_dissipation = hull.flux_dissipation
    shield_upkeep = hull.shield_upkeep or 0.0
    adjustment_notes: list[str] = []
    if "flux_hullmod_adjustment_enabled" in heuristics and registry is not None:
        # Opt-in only (baseline_0.8+, see core/heuristics.py); absent under
        # baseline_0.7 and earlier, so their flux_sustainability output is
        # untouched -- the hull's raw, unmodified stats are used exactly as
        # before.
        derived = compute_derived_flux_stats(hull, hullmod_ids, registry)
        adjusted_dissipation, fd_note = _hullmod_adjusted_stat(
            "flux_dissipation", hull.flux_dissipation, derived.effective_flux_dissipation,
            derived.applied_effects, derived.stacking_notes,
        )
        # `_hullmod_adjusted_stat` only returns `None` when its `base_value`
        # argument (here `hull.flux_dissipation`) is itself `None` -- already
        # ruled out by the completeness guard at the top of this function.
        assert adjusted_dissipation is not None
        flux_dissipation = adjusted_dissipation
        if fd_note:
            adjustment_notes.append(fd_note)
        if hull.shield_upkeep is not None:
            adjusted_upkeep, su_note = _hullmod_adjusted_stat(
                "shield_upkeep", hull.shield_upkeep, derived.effective_shield_upkeep,
                derived.applied_effects, derived.stacking_notes,
            )
            shield_upkeep = adjusted_upkeep if adjusted_upkeep is not None else shield_upkeep
            if su_note:
                adjustment_notes.append(su_note)

    weapon_flux_per_second = sum(weapon.flux_per_second or 0.0 for weapon in weapons)
    sustained_flux_load = weapon_flux_per_second + shield_upkeep
    note_suffix = (" " + " ".join(adjustment_notes)) if adjustment_notes else ""
    if sustained_flux_load <= 0:
        return 100.0, "No sustained flux load: full flux_sustainability score." + note_suffix
    dissipation_ratio = flux_dissipation / sustained_flux_load
    target = heuristics[_FLUX_TARGET_KEY[flux_mode]]
    score = 100.0 if dissipation_ratio >= target else max(0.0, 100.0 * dissipation_ratio / target)
    return round(score, 1), f"Dissipation ratio {dissipation_ratio:.2f} against {flux_mode} target {target:.2f}." + note_suffix


def _civilian_efficiency_component(hull: Hull, variant: Variant, registry: Registry, heuristics: dict[str, float]) -> tuple[float | None, str | None]:
    """`AppliedLogisticsEffect.efficiency` (gain per OP spent -- see
    analysis/civilian.py, HULLMODS_CIVILIAN_AND_REFIT.md section 9)
    aggregated into a 0-100 score, exactly like every other component
    here. Silently absent (None, None) for a variant with no verified
    LOGISTICS hullmod effects applied at all -- not a penalty for combat
    variants that were never going to carry cargo/fuel/crew hullmods,
    just not applicable, so it never adds explanation noise to the vast
    majority of combat-profile reports.
    """
    civilian = classify_civilian_role(hull)
    stats = compute_derived_civilian_stats(hull, variant.hullmods, registry, civilian.is_civilian)
    if not stats.applied_effects:
        return None, None
    efficiencies = [effect.efficiency for effect in stats.applied_effects if effect.efficiency is not None]
    if not efficiencies:
        return None, "Logistics hullmod effect(s) applied, but OP cost is unknown for all of them: civilian_efficiency is not evaluated."
    mean_efficiency = sum(efficiencies) / len(efficiencies)
    reference = heuristics["civilian_efficiency_reference"]
    score = min(100.0, 100.0 * mean_efficiency / reference) if reference else 0.0
    return round(score, 1), f"Civilian logistics OP-efficiency (mean gain per OP spent across {len(efficiencies)} effect(s)): {mean_efficiency:.2f}, against a reference of {reference:.1f}."


def _survivability_component(hull: Hull, variant: Variant, registry: Registry, heuristics: dict[str, float]) -> tuple[float | None, str | None]:
    """`AppliedDefenseEffect.efficiency` (gain per OP spent -- see
    analysis/combat_stats.py) aggregated into a 0-100 score, exactly like
    _civilian_efficiency_component. Silently absent (None, None) for a
    variant with no verified DEFENSE hullmod effects applied at all -- not
    a penalty for variants that were never going to carry armor/hull-HP
    hullmods, just not applicable, so it never adds explanation noise to
    variants without any of heavyarmor/armoredweapons/reinforcedhull/
    blast_doors equipped.
    """
    stats = compute_derived_defense_stats(hull, variant.hullmods, registry)
    if not stats.applied_effects:
        return None, None
    efficiencies = [effect.efficiency for effect in stats.applied_effects if effect.efficiency is not None]
    if not efficiencies:
        return None, "Defense hullmod effect(s) applied, but OP cost is unknown for all of them: survivability is not evaluated."
    mean_efficiency = sum(efficiencies) / len(efficiencies)
    reference = heuristics["survivability_reference"]
    score = min(100.0, 100.0 * mean_efficiency / reference) if reference else 0.0
    return round(score, 1), f"Defense hullmod OP-efficiency (mean gain per OP spent across {len(efficiencies)} effect(s)): {mean_efficiency:.2f}, against a reference of {reference:.1f}."


def score_candidate(
    variant: Variant,
    registry: Registry,
    profile_id: str,
    heuristic_set: str = "baseline_0.2",
    flux_mode: str = "BALANCED",
    faction: Faction | None = None,
    weight_overrides: Mapping[str, float] | None = None,
) -> QualityAssessment:
    """Score only a LEGAL candidate; this function cannot override legality.

    `weight_overrides` (Phase 14, Advanced mode's `scoring_weight_overrides`):
    lets a caller rebalance the final weighted average's own named component
    weights (`weight_range_coherence`/`weight_op_efficiency`/`weight_role_
    match`/`weight_flux_sustainability`/`weight_faction_doctrine`/`weight_
    civilian_efficiency`/`weight_survivability`) without minting a new heuristic_set identifier for
    a one-off request. Deliberately does NOT let a caller touch any other
    heuristic (thresholds, targets, ...) -- `profiles/advanced.py` is the
    only producer of this mapping and restricts it to exactly those 6 keys,
    per Agent.md's "no undocumented/unaudited heuristic" rule; this function
    trusts its caller the same way it already trusts `heuristic_set` itself.
    Only applies under a heuristic_set that defines weight_* keys at all
    (baseline_0.2+) -- `baseline_0.1`'s legacy 3-component formula doesn't
    use them and stays untouched, exactly as before.
    """
    legality = validate_variant(variant, registry).result
    if legality != LegalityResult.LEGAL:
        return QualityAssessment("NOT_EVALUATED", None, {}, ("Quality scoring requires a LEGAL candidate.",), legality)
    hull = registry.hulls.by_id[variant.hull_id or ""]
    profile = get_profile(profile_id)
    mount_ids = list(variant.weapons_by_mount.keys())
    weapons = [registry.weapons.by_id[weapon_id] for weapon_id in variant.weapons_by_mount.values()]
    if not weapons:
        return QualityAssessment(
            "EVALUATED", 0.0,
            {"range_coherence": 0.0, "op_efficiency": 0.0, "role_match": 0.0},
            ("No installed weapons: this legal empty loadout receives no quality recommendation.",), legality,
        )
    heuristics = dict(get_heuristic_set(heuristic_set).values)
    if weight_overrides:
        heuristics.update(weight_overrides)
    adjusted_ranges, combat_notes = _combat_adjusted_ranges(hull, variant, mount_ids, weapons, heuristics, registry)
    ranges = [r for r in adjusted_ranges if r is not None]
    spread = max(ranges) - min(ranges) if len(ranges) > 1 else 0.0
    if spread <= heuristics["range_mismatch_minor"]:
        range_score = 100.0
    elif spread <= heuristics["range_mismatch_moderate"]:
        range_score = 80.0
    elif spread <= heuristics["range_mismatch_severe"]:
        range_score = 55.0
    else:
        range_score = 25.0
    spent = sum(weapon.ordnance_points or 0 for weapon in weapons)
    op_score = min(100.0, (spent / hull.ordnance_points * 100.0) if hull.ordnance_points else 0.0)
    if profile.role_signal == "LONG_RANGE":
        role_score = 100.0 if all((r or 0) >= heuristics["artillery_min_range"] for r in adjusted_ranges) else 70.0
    elif profile.role_signal == "SHORT_RANGE":
        role_score = 100.0 if all((r or 0) <= heuristics["brawler_max_range"] for r in adjusted_ranges) else 70.0
    else:
        role_score = 70.0

    explanation = [f"Primary range spread: {spread:.0f}.", f"Weapon OP: {spent}/{hull.ordnance_points}."]
    explanation.extend(combat_notes)
    supports_extended_scoring = "weight_range_coherence" in heuristics
    if not supports_extended_scoring:
        # heuristic_set predates flux/doctrine scoring (e.g. baseline_0.1):
        # reproduce the original three-component formula exactly.
        final = round(range_score * _LEGACY_WEIGHTS["range_coherence"] + op_score * _LEGACY_WEIGHTS["op_efficiency"] + role_score * _LEGACY_WEIGHTS["role_match"], 1)
        return QualityAssessment(
            "EVALUATED", final,
            {"range_coherence": range_score, "op_efficiency": op_score, "role_match": role_score},
            tuple(explanation), legality,
        )
    if weight_overrides:
        explanation.append(f"Scoring weight override(s) applied: {', '.join(f'{key}={value}' for key, value in sorted(weight_overrides.items()))}.")

    flux_score, flux_note = _flux_component(hull, weapons, heuristics, flux_mode, variant.hullmods, registry)
    if flux_note:
        explanation.append(flux_note)

    doctrine_score: float | None = None
    if faction is None:
        explanation.append("No faction supplied: faction_doctrine_match is not evaluated.")
    else:
        evidence = analyze_faction_doctrine(faction, registry)
        doctrine_score = doctrine_match(variant, registry, evidence, heuristic_set)
        if doctrine_score is None:
            explanation.append(f"No usable doctrine evidence for faction {faction.id}: faction_doctrine_match is not evaluated.")
        else:
            explanation.append(f"Faction doctrine match against {faction.id}: {doctrine_score:.2f}.")

    civilian_score, civilian_note = _civilian_efficiency_component(hull, variant, registry, heuristics)
    if civilian_note:
        explanation.append(civilian_note)

    survivability_score, survivability_note = _survivability_component(hull, variant, registry, heuristics)
    if survivability_note:
        explanation.append(survivability_note)

    pd_score: float | None = None
    missile_score: float | None = None
    if profile.identifier == "PD_ESCORT" and "weight_pd_coverage" in heuristics:
        pd_score = round(100.0 * sum("PD" in classify_weapon(weapon).role_tags for weapon in weapons) / len(weapons), 1)
        explanation.append(f"PD coverage: {pd_score:.1f}% of mounted weapons have documented PD tags.")
    if profile.identifier == "MISSILE_SUPPORT" and "weight_missile_pressure" in heuristics:
        missile_score = round(100.0 * sum((weapon.mount_type or "").upper() == "MISSILE" for weapon in weapons) / len(weapons), 1)
        explanation.append(f"Missile pressure: {missile_score:.1f}% of mounted weapons use documented missile mounts.")

    weighted = [
        ("range_coherence", range_score, heuristics["weight_range_coherence"]),
        ("op_efficiency", op_score, heuristics["weight_op_efficiency"]),
        ("role_match", role_score, heuristics["weight_role_match"]),
        ("flux_sustainability", flux_score, heuristics["weight_flux_sustainability"]),
        ("faction_doctrine_match", doctrine_score, heuristics["weight_faction_doctrine"]),
        ("civilian_efficiency", civilian_score, heuristics["weight_civilian_efficiency"]),
        ("survivability", survivability_score, heuristics["weight_survivability"]),
    ]
    if "weight_pd_coverage" in heuristics:
        weighted.append(("pd_coverage", pd_score, heuristics["weight_pd_coverage"]))
    if "weight_missile_pressure" in heuristics:
        weighted.append(("missile_pressure", missile_score, heuristics["weight_missile_pressure"]))
    usable = [(name, score, weight) for name, score, weight in weighted if score is not None]
    total_weight = sum(weight for _, _, weight in usable)
    final = round(sum(score * weight for _, score, weight in usable) / total_weight, 1) if total_weight else 0.0
    components = {name: score for name, score, _ in weighted if score is not None}
    return QualityAssessment("EVALUATED", final, components, tuple(explanation), legality)
