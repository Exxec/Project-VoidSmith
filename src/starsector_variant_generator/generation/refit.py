"""Refit Assistant: FIX_LEGALITY (`fix_legality`) plus 4 of the 6 remaining
quality-improvement modes (`improve_quality`).

See HULLMODS_CIVILIAN_AND_REFIT.md sections 12-19. Full purpose: "Improve
this existing variant while changing as little as possible" -- distinct
from the full generator ("build a good variant for this role").
FIX_LEGALITY has an unambiguous, mechanically-verified target
(`validate_variant` says LEGAL or it doesn't); the other modes don't, so
`improve_quality` instead greedily searches for the best real
`quality_gain / change_cost` (section 14) at each step, using
`scoring/candidate_score.py::score_candidate`'s own components as the
target metric -- never inventing a new one. Implemented:
BALANCED_IMPROVEMENT (final_score), REDUCE_FLUX (flux_sustainability,
guarded against regressing role_match/range_coherence), IMPROVE_ROLE_MATCH
(role_match), IMPROVE_LOGISTICS (civilian_efficiency, civilian hulls
only). Not implemented -- genuinely no real evidence to search toward,
not merely unstarted: IMPROVE_AI_FIT (no AI-friendliness classifier
exists anywhere in this project), IMPROVE_SURVEY/IMPROVE_SALVAGE (no
per-ship SURVEY/SALVAGE evidence is ever scanned; see
`UNIMPLEMENTED_QUALITY_MODES`).

Locks (section 15): honors locked mount ids, hullmod ids, and fighter
wing ids -- a locked item is never touched, even if that leaves the
variant unable to reach LEGAL (`fix_legality`) or excludes it from the
quality search entirely (`improve_quality`). Per section 15's own rule,
an unsatisfied constraint is reported explicitly
(`RefitResult.rebuild_recommended` plus the remaining
`unresolved_failures`), never silently unlocked.

No Silent Rebuild (section 17): if `fix_legality` still isn't LEGAL, or
`improve_quality` still had a further positive-gain change available,
after `refit_max_changes` individual changes, both stop and report that a
larger rebuild may be needed rather than continuing indefinitely or
quietly calling the full generator.

Deliberately unhandled: `HULLMOD_INCOMPATIBLE`. `adapters.vanilla.
INCOMPATIBLE_HULLMOD_PAIRS` is empty by design (SVG-010 -- no documented
vanilla pairwise exclusivity mechanic was ever found), so this code
never fires against real data today; a fixer for it would be unverifiable
against anything. If that table is ever populated with real evidence, add
a fixer here at the same time, not before.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, replace as dataclass_replace

from starsector_variant_generator.adapters import defense_hullmod_effects, flux_unit_cost, logistics_hullmod_effects, max_logistics_hullmods
from starsector_variant_generator.analysis.adaptive_substitution import rank_substitution_candidates
from starsector_variant_generator.analysis.classification import classify_civilian_role, classify_weapon
from starsector_variant_generator.analysis.combat_stats import compute_derived_defense_stats
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Faction, Variant
from starsector_variant_generator.core.mount_compatibility import MOUNT_TYPE_COMPATIBILITY
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.profiles.catalog import get_profile
from starsector_variant_generator.scoring.candidate_score import QualityAssessment, score_candidate
from starsector_variant_generator.validation.legality import LegalityAssessment, LegalityFinding, LegalityResult, validate_variant

_SIZE_ORDER = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}


@dataclass(frozen=True)
class RefitChange:
    kind: str  # "WEAPON_REMOVED" | "WEAPON_REPLACED" | "HULLMOD_REMOVED" | "HULLMOD_ADDED" | "FIGHTER_REMOVED" | "VENTS_REDUCED" | "CAPACITORS_REDUCED"
    target_id: str  # mount id, hullmod id, or fighter wing id
    old_value: str | None
    new_value: str | None
    reason: str
    cost: float


@dataclass(frozen=True)
class RefitResult:
    original_variant: Variant
    refitted_variant: Variant
    changes: tuple[RefitChange, ...]
    final_legality: LegalityAssessment
    total_change_cost: float
    rebuild_recommended: bool
    unresolved_failures: tuple[LegalityFinding, ...]


def fix_legality(
    variant: Variant,
    registry: Registry,
    heuristic_set: str = "baseline_0.2",
    locked_mount_ids: frozenset[str] = frozenset(),
    locked_hullmod_ids: frozenset[str] = frozenset(),
    locked_wing_ids: frozenset[str] = frozenset(),
    substitution_mode: str = "cheapest",
    requesting_faction_id: str | None = None,
) -> RefitResult:
    """`substitution_mode` (EQUIPMENT_ACCESS_AND_AUTOFIT.md section 9's four
    Retrofit Application Modes, applied only where a mount-incompatible
    weapon needs a replacement -- section 9 itself, plus section 18's GUI
    listing "Exact / Starsector-Style / Adaptive"):

    - "cheapest" (default, unchanged since this module's first version --
      picks the lowest-OP mount-compatible weapon; not itself one of
      section 9's three named modes, kept as the pre-existing default so
      every caller predating this parameter sees byte-identical behavior).
    - "exact" (section 9's `EXACT`: "Reproduce specified IDs exactly. No
      substitution. Missing items are reported." -- never looks for a
      replacement; the incompatible weapon is always removed and reported,
      even when a compatible substitute exists in the registry).
    - "starsector_style" (section 9's `STARSECTOR_STYLE`: "Preserve the
      target template and choose close available substitutes. Keep
      slot/category/group intent rather than redesigning the build." --
      picks the mount-compatible weapon that best preserves the original's
      documented category/group tags (`analysis/classification.py`'s
      `classify_weapon` role_tags + range_band), breaking ties by the
      closest ordnance-point cost to the original rather than ADAPTIVE's
      full weighted role/range/flux/damage/affinity score).
    - "adaptive" (section 9's `ADAPTIVE`, "Recommended project default" --
      uses `analysis/adaptive_substitution.py`'s real scoring engine to
      pick the compatible weapon that best preserves the original's
      role/range/flux/damage/affinity profile, not just the cheapest one
      or the closest category match).

    Defaults to "cheapest" so every existing caller sees byte-identical
    behavior; the other three are opt-in.
    """
    heuristics = get_heuristic_set(heuristic_set).values
    max_changes = int(heuristics["refit_max_changes"])
    current = variant
    changes: list[RefitChange] = []
    assessment = validate_variant(current, registry)
    fixers = _build_fixers(substitution_mode, requesting_faction_id, heuristic_set)

    # One ordered pass through every fixable failure category is logically
    # sufficient (structural reference issues first, then category limits,
    # OP budget last since earlier passes already reduce OP incidentally);
    # looped defensively in case a fix ever surfaces an unexpected new
    # failure, capped by refit_max_changes either way (section 17).
    for _ in range(3):
        if assessment.result == LegalityResult.LEGAL or len(changes) >= max_changes:
            break
        codes_present = {finding.code for finding in assessment.failures}
        made_progress = False
        for fixer in fixers:
            if len(changes) >= max_changes:
                break
            if fixer.codes & codes_present:
                current, applied = fixer.apply(current, registry, heuristics, locked_mount_ids, locked_hullmod_ids, locked_wing_ids, max_changes - len(changes))
                if applied:
                    changes.extend(applied)
                    made_progress = True
        assessment = validate_variant(current, registry)
        if not made_progress:
            break

    total_cost = sum(change.cost for change in changes)
    rebuild_recommended = assessment.result != LegalityResult.LEGAL
    # A non-LEGAL result can be blocked by either .failures (ILLEGAL) or
    # .uncertainties (NOT_DETERMINABLE, e.g. an undocumented mount type
    # like LAUNCH_BAY/DECORATIVE) -- report whichever is actually why this
    # didn't reach LEGAL, not just .failures, or a NOT_DETERMINABLE result
    # would misleadingly report zero unresolved reasons.
    unresolved = (assessment.failures + assessment.uncertainties) if rebuild_recommended else ()
    return RefitResult(variant, current, tuple(changes), assessment, total_cost, rebuild_recommended, unresolved)


@dataclass(frozen=True)
class _Fixer:
    codes: frozenset[str]
    apply: object  # Callable[[Variant, Registry, dict, frozenset, frozenset, frozenset, int], tuple[Variant, list[RefitChange]]]


def _fix_unresolved_weapon_refs(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    weapon_cost = heuristics["refit_cost_weapon_change"]
    weapons = dict(variant.weapons_by_mount)
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    mount_ids = {str(mount.get("id")) for mount in (hull.weapon_mounts if hull else ())}
    changes = []
    for mount_id, weapon_id in list(weapons.items()):
        if len(changes) >= budget:
            break
        if mount_id in locked_mounts:
            continue
        if mount_id not in mount_ids:
            del weapons[mount_id]
            changes.append(RefitChange("WEAPON_REMOVED", mount_id, weapon_id, None, "Mount is not defined by this hull.", weapon_cost))
        elif weapon_id not in registry.weapons.by_id:
            del weapons[mount_id]
            changes.append(RefitChange("WEAPON_REMOVED", mount_id, weapon_id, None, "Weapon is not indexed (removed or renamed upstream).", weapon_cost))
    return dataclass_replace(variant, weapons_by_mount=weapons), changes


def _fix_built_in_override(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    weapon_cost = heuristics["refit_cost_weapon_change"]
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None:
        return variant, []
    weapons = dict(variant.weapons_by_mount)
    changes = []
    for mount_id, fixed_weapon_id in hull.built_in_weapons.items():
        if len(changes) >= budget:
            break
        assigned = weapons.get(mount_id)
        if assigned is not None and assigned != fixed_weapon_id and mount_id not in locked_mounts:
            del weapons[mount_id]
            changes.append(RefitChange("WEAPON_REMOVED", mount_id, assigned, None, f"Mount is hull-fixed to {fixed_weapon_id!r}; the game auto-fills it.", weapon_cost))
    return dataclass_replace(variant, weapons_by_mount=weapons), changes


def _fix_mount_compatibility(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget, substitution_mode="cheapest", requesting_faction_id=None, heuristic_set="baseline_0.2"):
    weapon_cost = heuristics["refit_cost_weapon_change"]
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None:
        return variant, []
    mounts = {str(mount.get("id")): mount for mount in hull.weapon_mounts if mount.get("id")}
    weapons = dict(variant.weapons_by_mount)
    changes = []
    for mount_id, weapon_id in list(weapons.items()):
        if len(changes) >= budget:
            break
        if mount_id in locked_mounts or mount_id in hull.built_in_weapons:
            continue
        mount = mounts.get(mount_id)
        weapon = registry.weapons.by_id.get(weapon_id)
        if mount is None or weapon is None:
            continue
        mount_size = _SIZE_ORDER.get(str(mount.get("size", "")).upper())
        weapon_size = _SIZE_ORDER.get((weapon.size or "").upper())
        compatible_types = MOUNT_TYPE_COMPATIBILITY.get(str(mount.get("type", "")).upper())
        size_ok = mount_size is not None and weapon_size is not None and weapon_size <= mount_size
        type_ok = compatible_types is not None and weapon.mount_type is not None and weapon.mount_type.upper() in compatible_types
        if size_ok and type_ok:
            continue
        removal_reason = "Not compatible with this mount, and no documented compatible replacement was found."
        if substitution_mode == "adaptive":
            replacement = _best_compatible_weapon(mount, registry, weapon, requesting_faction_id, heuristic_set)
            reason = "Original weapon is not compatible with this mount's documented size/type; replaced with the best real role/range/flux/damage/affinity match (ADAPTIVE mode, EQUIPMENT_ACCESS_AND_AUTOFIT.md)."
        elif substitution_mode == "starsector_style":
            replacement = _template_compatible_weapon(mount, registry, weapon)
            reason = "Original weapon is not compatible with this mount's documented size/type; replaced with the closest available substitute that preserves its documented category/group intent (STARSECTOR_STYLE mode, EQUIPMENT_ACCESS_AND_AUTOFIT.md)."
        elif substitution_mode == "exact":
            replacement = _exact_compatible_weapon()
            removal_reason = "Original weapon is not compatible with this mount's documented size/type; EXACT mode reproduces specified IDs only and never substitutes (EQUIPMENT_ACCESS_AND_AUTOFIT.md), so it is removed and reported as missing rather than replaced."
            reason = ""  # unreachable: _exact_compatible_weapon always returns None
        else:
            replacement = _cheapest_compatible_weapon(mount, registry)
            reason = "Original weapon is not compatible with this mount's documented size/type."
        if replacement is not None:
            weapons[mount_id] = replacement.id
            changes.append(RefitChange("WEAPON_REPLACED", mount_id, weapon_id, replacement.id, reason, weapon_cost))
        else:
            del weapons[mount_id]
            changes.append(RefitChange("WEAPON_REMOVED", mount_id, weapon_id, None, removal_reason, weapon_cost))
    return dataclass_replace(variant, weapons_by_mount=weapons), changes


def _cheapest_compatible_weapon(mount: dict, registry: Registry):
    mount_size = _SIZE_ORDER.get(str(mount.get("size", "")).upper())
    compatible_types = MOUNT_TYPE_COMPATIBILITY.get(str(mount.get("type", "")).upper())
    if mount_size is None or compatible_types is None:
        return None
    eligible = [
        weapon for weapon in registry.weapons.by_id.values()
        if weapon.mount_type and weapon.mount_type.upper() in compatible_types
        and _SIZE_ORDER.get((weapon.size or "").upper(), 99) <= mount_size
        and weapon.ordnance_points is not None
    ]
    eligible.sort(key=lambda weapon: (weapon.ordnance_points, weapon.id))
    return eligible[0] if eligible else None


def _best_compatible_weapon(mount: dict, registry: Registry, target_weapon, requesting_faction_id, heuristic_set):
    """ADAPTIVE mode: rank every mount-eligible weapon against the
    original (incompatible) weapon's own role/range/flux/damage profile
    -- preserving the fitting's intent, per EQUIPMENT_ACCESS_AND_AUTOFIT.md
    section 3's "Starsector-Style"/"Adaptive" description -- rather than
    just picking whatever is cheapest."""
    mount_size = _SIZE_ORDER.get(str(mount.get("size", "")).upper())
    compatible_types = MOUNT_TYPE_COMPATIBILITY.get(str(mount.get("type", "")).upper())
    if mount_size is None or compatible_types is None:
        return None
    eligible = [
        weapon for weapon in registry.weapons.by_id.values()
        if weapon.mount_type and weapon.mount_type.upper() in compatible_types
        and _SIZE_ORDER.get((weapon.size or "").upper(), 99) <= mount_size
        and weapon.ordnance_points is not None
    ]
    if not eligible:
        return None
    ranked = rank_substitution_candidates(target_weapon, eligible, registry, requesting_faction_id, heuristic_set)
    return registry.weapons.by_id.get(ranked[0].candidate_id) if ranked else None


def _exact_compatible_weapon():
    """EXACT mode: EQUIPMENT_ACCESS_AND_AUTOFIT.md section 9's `EXACT` --
    "Reproduce specified IDs exactly. No substitution. Missing items are
    reported." There is no weapon to select: this always returns None so
    `_fix_mount_compatibility` removes the incompatible weapon and reports
    it as missing rather than replacing it, even when a mount-compatible
    substitute exists in the registry (see
    `test_exact_mode_never_substitutes_even_when_a_compatible_weapon_exists`)."""
    return None


def _template_compatible_weapon(mount: dict, registry: Registry, target_weapon):
    """STARSECTOR_STYLE mode: EQUIPMENT_ACCESS_AND_AUTOFIT.md section 9's
    `STARSECTOR_STYLE` -- "Preserve the target template and choose close
    available substitutes. Keep slot/category/group intent rather than
    redesigning the build." Unlike ADAPTIVE's full weighted role/range/
    flux/damage/affinity score, this only keeps the original's documented
    category/group tags (`classify_weapon`'s role_tags -- KINETIC_PRESSURE/
    ARMOR_BREAKER/PD/MISSILE_PRESSURE/ARTILLERY -- and range_band), then
    breaks ties by the closest ordnance-point cost to the original (a
    "close available substitute", not necessarily the cheapest one --
    that's `_cheapest_compatible_weapon`'s job)."""
    mount_size = _SIZE_ORDER.get(str(mount.get("size", "")).upper())
    compatible_types = MOUNT_TYPE_COMPATIBILITY.get(str(mount.get("type", "")).upper())
    if mount_size is None or compatible_types is None:
        return None
    eligible = [
        weapon for weapon in registry.weapons.by_id.values()
        if weapon.mount_type and weapon.mount_type.upper() in compatible_types
        and _SIZE_ORDER.get((weapon.size or "").upper(), 99) <= mount_size
        and weapon.ordnance_points is not None
    ]
    if not eligible:
        return None
    target_classification = classify_weapon(target_weapon)
    target_tags = set(target_classification.role_tags)
    target_op = target_weapon.ordnance_points

    def _sort_key(weapon):
        candidate_classification = classify_weapon(weapon)
        candidate_tags = set(candidate_classification.role_tags)
        union = target_tags | candidate_tags
        tag_jaccard = (len(target_tags & candidate_tags) / len(union)) if union else 0.0
        range_band_mismatch = 0 if candidate_classification.range_band == target_classification.range_band else 1
        op_distance = abs(weapon.ordnance_points - target_op) if target_op is not None else 0
        return (-tag_jaccard, range_band_mismatch, op_distance, weapon.id)

    eligible.sort(key=_sort_key)
    return eligible[0]


def _fix_unresolved_hullmods(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    hullmod_cost = heuristics["refit_cost_hullmod_change"]
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    hullmods = list(variant.hullmods)
    changes = []
    for hullmod_id in list(hullmods):
        if len(changes) >= budget:
            break
        if hullmod_id in locked_hullmods or (hull and hullmod_id in hull.built_in_hullmods):
            continue
        if hullmod_id not in registry.hullmods.by_id:
            hullmods.remove(hullmod_id)
            changes.append(RefitChange("HULLMOD_REMOVED", hullmod_id, hullmod_id, None, "Hullmod is not indexed (removed or renamed upstream).", hullmod_cost))
    return dataclass_replace(variant, hullmods=tuple(hullmods)), changes


def _fix_logistics_limit(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None:
        return variant, []
    hullmod_cost = heuristics["refit_cost_hullmod_change"]
    logistics_ids = sorted(
        hullmod_id for hullmod_id in variant.hullmods
        if hullmod_id not in hull.built_in_hullmods
        and (hullmod := registry.hullmods.by_id.get(hullmod_id)) is not None
        and "Logistics" in str(hullmod.raw.get("uiTags", ""))
    )
    limit = max_logistics_hullmods()
    excess = [hullmod_id for hullmod_id in logistics_ids[limit:] if hullmod_id not in locked_hullmods]
    hullmods = list(variant.hullmods)
    changes = []
    for hullmod_id in excess:
        if len(changes) >= budget:
            break
        hullmods.remove(hullmod_id)
        changes.append(RefitChange("HULLMOD_REMOVED", hullmod_id, hullmod_id, None, f"Exceeds the documented maximum of {limit} logistics hullmods.", hullmod_cost))
    return dataclass_replace(variant, hullmods=tuple(hullmods)), changes


def _fix_unresolved_wings(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    fighter_cost = heuristics["refit_cost_fighter_change"]
    wings = list(variant.fighter_wings)
    changes = []
    for wing_id in list(wings):
        if len(changes) >= budget:
            break
        if wing_id in locked_wings:
            continue
        if wing_id not in registry.fighters.by_id:
            wings.remove(wing_id)
            changes.append(RefitChange("FIGHTER_REMOVED", wing_id, wing_id, None, "Fighter wing is not indexed (removed or renamed upstream).", fighter_cost))
    return dataclass_replace(variant, fighter_wings=tuple(wings)), changes


def _fix_bay_capacity(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None or hull.fighter_bays is None:
        return variant, []
    fighter_cost = heuristics["refit_cost_fighter_change"]
    ordered = sorted(variant.fighter_wings)
    excess = [wing_id for wing_id in ordered[hull.fighter_bays:] if wing_id not in locked_wings]
    wings = list(variant.fighter_wings)
    changes = []
    for wing_id in excess:
        if len(changes) >= budget:
            break
        wings.remove(wing_id)
        changes.append(RefitChange("FIGHTER_REMOVED", wing_id, wing_id, None, f"Exceeds hull {hull.id}'s {hull.fighter_bays} documented fighter bay(s).", fighter_cost))
    return dataclass_replace(variant, fighter_wings=tuple(wings)), changes


def _fix_flux_maximums(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None:
        return variant, []
    flux_cost = flux_unit_cost(hull.source_mod)
    if flux_cost is None:
        return variant, []
    vent_cap_cost = heuristics["refit_cost_vent_cap_change"]
    changes = []
    vents, capacitors = variant.flux_vents, variant.flux_capacitors
    max_vents = flux_cost.max_vents_by_hull_size.get(hull.hull_size or "")
    max_capacitors = flux_cost.max_capacitors_by_hull_size.get(hull.hull_size or "")
    if vents and max_vents is not None and vents > max_vents and len(changes) < budget:
        changes.append(RefitChange("VENTS_REDUCED", "flux_vents", str(vents), str(max_vents), f"Exceeds the documented maximum of {max_vents} for hull size {hull.hull_size} ({flux_cost.citation}).", vent_cap_cost))
        vents = max_vents
    if capacitors and max_capacitors is not None and capacitors > max_capacitors and len(changes) < budget:
        changes.append(RefitChange("CAPACITORS_REDUCED", "flux_capacitors", str(capacitors), str(max_capacitors), f"Exceeds the documented maximum of {max_capacitors} for hull size {hull.hull_size} ({flux_cost.citation}).", vent_cap_cost))
        capacitors = max_capacitors
    return dataclass_replace(variant, flux_vents=vents, flux_capacitors=capacitors), changes


def _fix_op_exceeded(variant, registry, heuristics, locked_mounts, locked_hullmods, locked_wings, budget):
    """Greedily remove the single highest-OP unlocked item at a time until
    the variant's total OP is back within the hull's budget, re-checking
    after every removal so this never removes more than necessary."""
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None or hull.ordnance_points is None:
        return variant, []
    weapon_cost = heuristics["refit_cost_weapon_change"]
    hullmod_cost = heuristics["refit_cost_hullmod_change"]
    fighter_cost = heuristics["refit_cost_fighter_change"]
    current = variant
    changes: list[RefitChange] = []
    while len(changes) < budget:
        total = _total_op(current, hull, registry)
        if total is None or total <= hull.ordnance_points:
            break
        candidates: list[tuple[int, str, str, str]] = []  # (op_cost, kind, target_id, old_value)
        for mount_id, weapon_id in current.weapons_by_mount.items():
            if mount_id in locked_mounts or mount_id in hull.built_in_weapons:
                continue
            weapon = registry.weapons.by_id.get(weapon_id)
            if weapon and weapon.ordnance_points is not None:
                candidates.append((weapon.ordnance_points, "WEAPON_REMOVED", mount_id, weapon_id))
        for hullmod_id in current.hullmods:
            if hullmod_id in locked_hullmods or hullmod_id in hull.built_in_hullmods:
                continue
            hullmod = registry.hullmods.by_id.get(hullmod_id)
            cost = hullmod.op_cost_by_hull_size.get(hull.hull_size or "") if hullmod else None
            if cost is not None:
                candidates.append((cost, "HULLMOD_REMOVED", hullmod_id, hullmod_id))
        for wing_id in current.fighter_wings:
            if wing_id in locked_wings:
                continue
            wing = registry.fighters.by_id.get(wing_id)
            if wing and wing.op_cost is not None:
                candidates.append((wing.op_cost, "FIGHTER_REMOVED", wing_id, wing_id))
        if not candidates:
            break
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        op_cost, kind, target_id, old_value = candidates[0]
        cost_weight = {"WEAPON_REMOVED": weapon_cost, "HULLMOD_REMOVED": hullmod_cost, "FIGHTER_REMOVED": fighter_cost}[kind]
        if kind == "WEAPON_REMOVED":
            weapons = dict(current.weapons_by_mount)
            del weapons[target_id]
            current = dataclass_replace(current, weapons_by_mount=weapons)
        elif kind == "HULLMOD_REMOVED":
            current = dataclass_replace(current, hullmods=tuple(h for h in current.hullmods if h != target_id))
        else:
            current = dataclass_replace(current, fighter_wings=tuple(w for w in current.fighter_wings if w != target_id))
        changes.append(RefitChange(kind, target_id, old_value, None, f"Total OP {total} exceeds hull OP {hull.ordnance_points}; this was the highest-OP unlocked item ({op_cost} OP).", cost_weight))
    return current, changes


def _total_op(variant: Variant, hull, registry: Registry) -> int | None:
    total = 0
    for weapon_id in variant.weapons_by_mount.values():
        weapon = registry.weapons.by_id.get(weapon_id)
        if weapon is None or weapon.ordnance_points is None:
            return None
        total += weapon.ordnance_points
    for hullmod_id in variant.hullmods:
        if hullmod_id in hull.built_in_hullmods:
            continue
        hullmod = registry.hullmods.by_id.get(hullmod_id)
        cost = hullmod.op_cost_by_hull_size.get(hull.hull_size or "") if hullmod else None
        if cost is None:
            return None
        total += cost
    for wing_id in variant.fighter_wings:
        wing = registry.fighters.by_id.get(wing_id)
        if wing is None or wing.op_cost is None:
            return None
        total += wing.op_cost
    flux_cost = flux_unit_cost(hull.source_mod)
    if variant.flux_vents or variant.flux_capacitors:
        if flux_cost is None:
            return None
        total += ((variant.flux_vents or 0) + (variant.flux_capacitors or 0)) * flux_cost.op_cost_per_unit
    return total


@dataclass(frozen=True)
class QualityRefitResult:
    """Result of a quality-improvement refit mode (section 13's modes other
    than FIX_LEGALITY). Distinct from RefitResult: there is no single
    unambiguous target like LEGAL to search toward, so this reports a
    quality_gain on the mode's own named metric instead of a legality
    verdict. Every candidate change is independently re-validated LEGAL
    (validate_variant) before it is even considered -- quality search can
    never trade away legality for a better score, the same hard boundary
    FIX_LEGALITY's fixers already respect.
    """

    original_variant: Variant
    refitted_variant: Variant
    changes: tuple[RefitChange, ...]
    mode: str
    metric_name: str | None
    before_score: float | None
    after_score: float | None
    total_change_cost: float
    rebuild_recommended: bool
    note: str | None


_QUALITY_MODE_METRICS = {
    "BALANCED_IMPROVEMENT": None,  # special-cased below: uses the full weighted final_score
    "REDUCE_FLUX": "flux_sustainability",
    "IMPROVE_ROLE_MATCH": "role_match",
    "IMPROVE_LOGISTICS": "civilian_efficiency",
}

# Named per HULLMODS_CIVILIAN_AND_REFIT.md section 13, but genuinely
# unimplementable today without fabricating a metric -- not merely
# unstarted by choice. See root ROADMAP.md Phase 9.
UNIMPLEMENTED_QUALITY_MODES = {
    "IMPROVE_AI_FIT": "No AI-friendliness classifier exists anywhere in this project (deliberately excluded from adaptive substitution scoring for the same reason -- see analysis/adaptive_substitution.py); there is no real metric to search toward.",
    "IMPROVE_SURVEY": "classify_civilian_role's real, scanned hull hints (analysis/classification.py) never include SURVEY -- there is no real per-ship evidence to build a target metric from.",
    "IMPROVE_SALVAGE": "classify_civilian_role's real, scanned hull hints (analysis/classification.py) never include SALVAGE -- there is no real per-ship evidence to build a target metric from.",
}


def _metric_value(assessment: QualityAssessment, mode: str) -> float | None:
    if mode == "BALANCED_IMPROVEMENT":
        return assessment.final_score
    return assessment.components.get(_QUALITY_MODE_METRICS[mode])


def _role_match_progress(variant: Variant, registry: Registry, profile_id: str, heuristics: dict[str, float]) -> tuple[int, int] | None:
    """Return (weapons meeting the profile's range condition, total weapons).

    `score_candidate` intentionally keeps role_match as a simple 70/100
    contract: every weapon must satisfy the profile range condition.  The
    Refit Assistant nevertheless needs an explainable intermediate signal
    when several swaps are required before that public metric can change.
    This helper does not create a new quality score or heuristic; it reports
    the exact count of weapons already satisfying the existing condition.
    """
    profile = get_profile(profile_id)
    if profile.role_signal == "LONG_RANGE":
        predicate = lambda weapon: (weapon.range or 0) >= heuristics["artillery_min_range"]
    elif profile.role_signal == "SHORT_RANGE":
        predicate = lambda weapon: (weapon.range or 0) <= heuristics["brawler_max_range"]
    else:
        return None
    weapons = [registry.weapons.by_id.get(weapon_id) for weapon_id in variant.weapons_by_mount.values()]
    if not weapons or any(weapon is None for weapon in weapons):
        return None
    return sum(1 for weapon in weapons if predicate(weapon)), len(weapons)


def improve_quality(
    variant: Variant,
    registry: Registry,
    mode: str,
    profile_id: str,
    heuristic_set: str = "baseline_0.2",
    locked_mount_ids: frozenset[str] = frozenset(),
    locked_hullmod_ids: frozenset[str] = frozenset(),
    locked_wing_ids: frozenset[str] = frozenset(),
    flux_mode: str = "BALANCED",
    faction: Faction | None = None,
) -> QualityRefitResult:
    """Quality-improvement refit (HULLMODS_CIVILIAN_AND_REFIT.md section 13's
    other modes): "Improve this existing variant while changing as little
    as possible", greedily searching for the change with the best
    `quality_gain / change_cost` (section 14) at each step, under a
    maximum-change budget (section 17, "No Silent Rebuild" -- exhausting
    the budget while a further positive-gain change still existed sets
    `rebuild_recommended`, exactly like FIX_LEGALITY).

    Only 4 of the 7 non-FIX_LEGALITY modes have a real metric to search
    toward today: BALANCED_IMPROVEMENT (the full weighted score),
    REDUCE_FLUX (flux_sustainability, guarded so a candidate change is
    rejected if it would regress role_match or range_coherence --
    "preserving role/range" per section 13's own wording),
    IMPROVE_ROLE_MATCH (role_match), and IMPROVE_LOGISTICS
    (civilian_efficiency; only applies to hulls with a documented CIVILIAN
    hint). The other 3 raise ValueError -- see UNIMPLEMENTED_QUALITY_MODES.

    `locked_wing_ids` is accepted for interface symmetry with
    `fix_legality` but unused: none of the 4 implemented modes generate
    fighter-wing changes.
    """
    if mode == "FIX_LEGALITY":
        raise ValueError("FIX_LEGALITY is handled by fix_legality(), not improve_quality().")
    if mode in UNIMPLEMENTED_QUALITY_MODES:
        raise ValueError(f"Refit mode {mode} is not implemented: {UNIMPLEMENTED_QUALITY_MODES[mode]}")
    if mode not in _QUALITY_MODE_METRICS:
        raise ValueError(f"Unknown refit mode: {mode}")

    heuristics = get_heuristic_set(heuristic_set).values
    max_changes = int(heuristics["refit_max_changes"])
    min_gain = heuristics["refit_min_quality_gain"]
    metric_label = "final_score" if mode == "BALANCED_IMPROVEMENT" else _QUALITY_MODE_METRICS[mode]

    def _assess(candidate: Variant) -> QualityAssessment:
        return score_candidate(candidate, registry, profile_id, heuristic_set, flux_mode, faction)

    start_assessment = _assess(variant)
    if start_assessment.status != "EVALUATED":
        return QualityRefitResult(variant, variant, (), mode, metric_label, None, None, 0.0, False, "Starting variant is not a legal, scoreable candidate: nothing to improve.")
    if mode == "IMPROVE_LOGISTICS":
        hull = registry.hulls.by_id.get(variant.hull_id or "")
        if hull is None or not classify_civilian_role(hull).is_civilian:
            return QualityRefitResult(variant, variant, (), mode, metric_label, None, None, 0.0, False, "IMPROVE_LOGISTICS only applies to hulls with a documented CIVILIAN hint; this hull has none.")

    start_metric = _metric_value(start_assessment, mode)
    if start_metric is None:
        if mode != "IMPROVE_LOGISTICS":
            return QualityRefitResult(variant, variant, (), mode, metric_label, None, None, 0.0, False, f"{metric_label} is not evaluated for this variant (missing documented data, or not applicable): nothing to improve.")
        # civilian_efficiency is absent (not None-as-error) precisely when no
        # LOGISTICS hullmod effect is applied yet -- IMPROVE_LOGISTICS's own
        # starting point, not missing data. Treat as a real 0.0 baseline to
        # search upward from, per analysis/civilian.py's own "no applied
        # effects" convention.
        start_metric = 0.0

    current, current_assessment, current_metric = variant, start_assessment, start_metric
    changes: list[RefitChange] = []
    rebuild_recommended = False
    while True:
        if len(changes) >= max_changes:
            rebuild_recommended = True
            break
        # The public role_match metric is deliberately all-or-nothing: it
        # cannot increase until the final out-of-range weapon is replaced.
        # For that mode alone, rank legal moves by their documented-range
        # progress first, then normal quality and stable identifiers.  This
        # allows a bounded series of necessary, individually-neutral swaps
        # without weakening the score contract or accepting an illegal state.
        current_role_progress = _role_match_progress(current, registry, profile_id, heuristics) if mode == "IMPROVE_ROLE_MATCH" else None
        best = None  # (selection, change, new_variant, new_assessment, new_metric)
        for change, candidate in _quality_moves(current, registry, mode, locked_mount_ids, locked_hullmod_ids, heuristics):
            if validate_variant(candidate, registry).result != LegalityResult.LEGAL:
                continue
            candidate_assessment = _assess(candidate)
            candidate_metric = _metric_value(candidate_assessment, mode)
            if candidate_metric is None:
                continue
            if mode == "REDUCE_FLUX" and (
                candidate_assessment.components.get("role_match", 0.0) < current_assessment.components.get("role_match", 0.0)
                or candidate_assessment.components.get("range_coherence", 0.0) < current_assessment.components.get("range_coherence", 0.0)
            ):
                continue
            gain = candidate_metric - current_metric
            if mode == "IMPROVE_ROLE_MATCH" and current_role_progress is not None:
                candidate_role_progress = _role_match_progress(candidate, registry, profile_id, heuristics)
                if candidate_role_progress is None:
                    continue
                progress_gain = candidate_role_progress[0] - current_role_progress[0]
                if progress_gain <= 0:
                    continue
                # More range-compliant mounts is the only intermediate
                # objective.  The ordinary final score is strictly a
                # deterministic tie-breaker; it never makes an illegal move
                # eligible or changes score_candidate's public metric.
                selection = (
                    progress_gain,
                    candidate_assessment.final_score if candidate_assessment.final_score is not None else -1.0,
                    -change.cost,
                    change.target_id,
                    change.new_value or "",
                )
            else:
                if gain < min_gain:
                    continue
                selection = (gain / change.cost,)
            if best is None or selection > best[0]:
                best = (selection, change, candidate, candidate_assessment, candidate_metric)
        if best is None:
            break
        _, change, current, current_assessment, current_metric = best
        changes.append(change)

    total_cost = sum(change.cost for change in changes)
    # Do not present a partial all-or-nothing role_match refit as a quality
    # improvement.  Its changes remain visible with an explicit rebuild
    # recommendation when the maximum-change budget blocked completion.
    note = None
    if mode == "IMPROVE_ROLE_MATCH" and current_metric - start_metric < min_gain and changes:
        note = "Range-compliant replacement progress was made, but the all-weapons role_match target was not reached within the change budget."
        rebuild_recommended = True
    return QualityRefitResult(variant, current, tuple(changes), mode, metric_label, start_metric, current_metric, total_cost, rebuild_recommended, note)


def _quality_moves(variant: Variant, registry: Registry, mode: str, locked_mount_ids: frozenset[str], locked_hullmod_ids: frozenset[str], heuristics: dict[str, float]):
    """Candidate single-changes for the quality-improvement search.

    Weapon-substitution modes explore every mount-eligible weapon on every
    unlocked, non-built-in mount (the same size/type compatibility rule
    FIX_LEGALITY's own mount-compatibility fixer uses); IMPROVE_LOGISTICS
    instead explores adding one not-yet-installed, verified LOGISTICS
    hullmod (analysis/civilian.py's own effect table for this hull's
    source mod). BALANCED_IMPROVEMENT additionally explores a verified,
    applicable DEFENSE hullmod addition. It does not infer effects from
    `uiTags` or names: both the source-specific adapter and
    `compute_derived_defense_stats` must positively establish an effect.
    Legality (the logistics-hullmod cap, OP budget, ...) is left entirely
    to the caller's validate_variant check on each yielded candidate --
    never re-implemented here.
    """
    hull = registry.hulls.by_id.get(variant.hull_id or "")
    if hull is None:
        return
    if mode == "IMPROVE_LOGISTICS":
        hullmod_cost = heuristics["refit_cost_hullmod_change"]
        installed = set(variant.hullmods)
        candidate_ids = sorted({effect.hullmod_id for effect in logistics_hullmod_effects(hull.source_mod)})
        for hullmod_id in candidate_ids:
            if hullmod_id in installed or hullmod_id in locked_hullmod_ids or hullmod_id not in registry.hullmods.by_id:
                continue
            new_variant = dataclass_replace(variant, hullmods=variant.hullmods + (hullmod_id,))
            yield RefitChange("HULLMOD_ADDED", hullmod_id, None, hullmod_id, "Adds a verified logistics effect to improve civilian_efficiency.", hullmod_cost), new_variant
        return

    if mode == "BALANCED_IMPROVEMENT":
        hullmod_cost = heuristics["refit_cost_hullmod_change"]
        installed = set(variant.hullmods)
        candidate_ids = sorted({effect.hullmod_id for effect in defense_hullmod_effects(hull.source_mod)})
        for hullmod_id in candidate_ids:
            if hullmod_id in installed or hullmod_id in locked_hullmod_ids or hullmod_id not in registry.hullmods.by_id:
                continue
            new_variant = dataclass_replace(variant, hullmods=variant.hullmods + (hullmod_id,))
            # A table entry is not enough: the hull needs the documented
            # base stat (including the skin fallback) for this exact effect
            # to be computable. Otherwise leave it UNKNOWN rather than
            # proposing it as an improvement.
            if not compute_derived_defense_stats(hull, new_variant.hullmods, registry).applied_effects:
                continue
            yield RefitChange(
                "HULLMOD_ADDED", hullmod_id, None, hullmod_id,
                "Adds a verified, applicable defense effect for balanced quality improvement.",
                hullmod_cost,
            ), new_variant

    weapon_cost = heuristics["refit_cost_weapon_change"]
    mounts = {str(mount.get("id")): mount for mount in hull.weapon_mounts if mount.get("id")}
    for mount_id, current_weapon_id in variant.weapons_by_mount.items():
        if mount_id in locked_mount_ids or mount_id in hull.built_in_weapons:
            continue
        mount = mounts.get(mount_id)
        if mount is None:
            continue
        mount_size = _SIZE_ORDER.get(str(mount.get("size", "")).upper())
        compatible_types = MOUNT_TYPE_COMPATIBILITY.get(str(mount.get("type", "")).upper())
        if mount_size is None or compatible_types is None:
            continue
        for weapon in registry.weapons.by_id.values():
            if weapon.id == current_weapon_id or weapon.ordnance_points is None:
                continue
            if weapon.mount_type is None or weapon.mount_type.upper() not in compatible_types:
                continue
            if _SIZE_ORDER.get((weapon.size or "").upper(), 99) > mount_size:
                continue
            weapons = dict(variant.weapons_by_mount)
            weapons[mount_id] = weapon.id
            new_variant = dataclass_replace(variant, weapons_by_mount=weapons)
            metric_label = "the overall quality score" if mode == "BALANCED_IMPROVEMENT" else _QUALITY_MODE_METRICS[mode]
            reason = f"Replaces {current_weapon_id!r} with {weapon.id!r} to improve {metric_label}."
            yield RefitChange("WEAPON_REPLACED", mount_id, current_weapon_id, weapon.id, reason, weapon_cost), new_variant


def _build_fixers(substitution_mode: str, requesting_faction_id: str | None, heuristic_set: str) -> tuple[_Fixer, ...]:
    """Built per `fix_legality` call (not a module-level constant) since
    the mount-compatibility fixer needs that call's `substitution_mode`/
    `requesting_faction_id` bound in -- every other fixer is unaffected
    and behaves identically regardless of these parameters."""
    mount_compatibility_fixer = functools.partial(
        _fix_mount_compatibility, substitution_mode=substitution_mode,
        requesting_faction_id=requesting_faction_id, heuristic_set=heuristic_set,
    )
    return (
        _Fixer(frozenset({"MOUNT_NOT_FOUND", "WEAPON_NOT_FOUND"}), _fix_unresolved_weapon_refs),
        _Fixer(frozenset({"BUILT_IN_WEAPON_OVERRIDDEN"}), _fix_built_in_override),
        _Fixer(frozenset({"WEAPON_TOO_LARGE", "MOUNT_TYPE_MISMATCH"}), mount_compatibility_fixer),
        _Fixer(frozenset({"HULLMOD_NOT_FOUND"}), _fix_unresolved_hullmods),
        _Fixer(frozenset({"LOGISTICS_HULLMOD_LIMIT_EXCEEDED"}), _fix_logistics_limit),
        _Fixer(frozenset({"FIGHTER_WING_NOT_FOUND"}), _fix_unresolved_wings),
        _Fixer(frozenset({"FIGHTER_BAY_CAPACITY_EXCEEDED"}), _fix_bay_capacity),
        _Fixer(frozenset({"FLUX_VENTS_EXCEED_HULL_MAXIMUM", "FLUX_CAPACITORS_EXCEED_HULL_MAXIMUM"}), _fix_flux_maximums),
        _Fixer(frozenset({"OP_EXCEEDED"}), _fix_op_exceeded),
    )
