from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from starsector_variant_generator.analysis.classification import classify_weapon
from starsector_variant_generator.analysis.build_archetypes import BuildArchetypeProfile, infer_build_archetypes, profile_id_for_build
from starsector_variant_generator.analysis.scenario_objectives import ScenarioObjective
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Variant, Weapon
from starsector_variant_generator.core.mount_compatibility import MOUNT_TYPE_COMPATIBILITY
from starsector_variant_generator.core.overrides import EntityOverride, apply_role_tag_override
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.result_cache import AnalysisContextFingerprint, CacheReadiness
from starsector_variant_generator.generation.fighters import select_fighter_wings
from starsector_variant_generator.generation.hullmods import select_hullmods
from starsector_variant_generator.generation.vent_cap import allocate_vents_and_capacitors
from starsector_variant_generator.profiles.catalog import get_profile
from starsector_variant_generator.validation.legality import LegalityResult, validate_variant


_SIZE_ORDER = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}


@dataclass(frozen=True)
class CandidateResult:
    variant: Variant
    legality: LegalityResult
    omissions: tuple[str, ...]
    omission_records: tuple["CandidateOmission", ...] = ()


@dataclass(frozen=True)
class CandidateOmission:
    """A machine-readable omission; never a legality or scoring adjustment."""

    code: str  # STRUCTURAL_SLOT_OMITTED | UNSUPPORTED_MOUNT_SEMANTICS | ...
    mount_id: str
    mount_type: str | None
    detail: str


@dataclass(frozen=True)
class BuildCandidateResult:
    """One independently generated fit for a Hull + BuildArchetype path."""

    build: BuildArchetypeProfile
    profile_id: str
    candidate: CandidateResult


def generate_conservative_candidate(
    hull_id: str,
    profile_id: str,
    registry: Registry,
    allowed_weapon_ids: set[str] | None = None,
    preferred_weapon_ids: set[str] | None = None,
    denied_weapon_ids: set[str] | None = None,
    locked_weapons_by_mount: dict[str, str] | None = None,
    empty_mount_ids: set[str] | None = None,
    flux_mode: str = "BALANCED",
    allowed_hullmod_ids: set[str] | None = None,
    preferred_hullmod_ids: set[str] | None = None,
    denied_hullmod_ids: set[str] | None = None,
    allowed_wing_ids: set[str] | None = None,
    preferred_wing_ids: set[str] | None = None,
    denied_wing_ids: set[str] | None = None,
    weapon_role_overrides: dict[str, EntityOverride] | None = None,
    heuristic_set: str = "baseline_0.2",
) -> CandidateResult:
    """Build one deterministic, evidence-bound weapon-only candidate.

    This intentionally leaves unsupported mounts empty rather than guessing at
    compatibility or scripted mechanics. Hullmods (generation/hullmods.py),
    fighter wings (generation/fighters.py), vents, and capacitors
    (generation/vent_cap.py) are added additively when the relevant data is
    documented; otherwise none are added, matching the legacy weapon-only
    behavior exactly.

    `heuristic_set` governs only `generation/vent_cap.py::allocate_vents_and_capacitors`
    (its flux-sustainability target). It defaults to "baseline_0.2" -- the
    value every caller of this function got implicitly before this parameter
    existed -- so an existing caller that doesn't pass it sees byte-for-byte
    identical output.
    """
    hull = registry.hulls.by_id.get(hull_id)
    profile = get_profile(profile_id)
    if hull is None:
        variant = Variant(f"{hull_id}_{profile_id}_svg", "Unknown Hull", "generated", Path("generated"), hull_id=hull_id)
        return CandidateResult(variant, LegalityResult.ILLEGAL, ("Hull not indexed.",))
    return _build_candidate(
        hull_id, profile_id, registry, allowed_weapon_ids, preferred_weapon_ids,
        denied_weapon_ids, locked_weapons_by_mount, empty_mount_ids, {}, flux_mode=flux_mode,
        allowed_hullmod_ids=allowed_hullmod_ids, preferred_hullmod_ids=preferred_hullmod_ids, denied_hullmod_ids=denied_hullmod_ids,
        allowed_wing_ids=allowed_wing_ids, preferred_wing_ids=preferred_wing_ids, denied_wing_ids=denied_wing_ids,
        weapon_role_overrides=weapon_role_overrides, heuristic_set=heuristic_set,
    )


def generate_candidate_alternatives(
    hull_id: str,
    profile_id: str,
    registry: Registry,
    allowed_weapon_ids: set[str] | None = None,
    preferred_weapon_ids: set[str] | None = None,
    denied_weapon_ids: set[str] | None = None,
    locked_weapons_by_mount: dict[str, str] | None = None,
    empty_mount_ids: set[str] | None = None,
    max_candidates: int = 5,
    flux_mode: str = "BALANCED",
    allowed_hullmod_ids: set[str] | None = None,
    preferred_hullmod_ids: set[str] | None = None,
    denied_hullmod_ids: set[str] | None = None,
    allowed_wing_ids: set[str] | None = None,
    preferred_wing_ids: set[str] | None = None,
    denied_wing_ids: set[str] | None = None,
    search_depth: int = 1,
    weapon_role_overrides: dict[str, EntityOverride] | None = None,
    heuristic_set: str = "baseline_0.2",
) -> tuple[CandidateResult, ...]:
    """Return a capped, deterministic set of independently validated choices.

    This is intentionally a bounded search rather than an exhaustive loadout
    optimizer.  Each seed asks one documented mount to use its Nth-ranked
    eligible weapon (N up to `search_depth`); the remaining mounts retain
    the conservative greedy policy.  No quality heuristic is used here, so
    choice construction cannot change legality.

    `search_depth` defaults to 1 -- exactly the original "one alternate
    rank per mount" bound -- for full backward compatibility (existing
    reports, the golden regression test, and every caller that doesn't
    pass it explicitly see identical output to before this parameter
    existed). Raising it explores rank 2, 3, ... for every mount, but
    still one mount changed at a time: this stays a per-mount bounded
    search, not a per-mount-combination one, so the candidate count never
    grows combinatorially with mount count -- Agent.md's "avoid
    brute-force combinatorial generation" rule. See docs/ROADMAP.md
    "richer bounded search."

    `heuristic_set` is forwarded to every `_build_candidate` call below and,
    through it, to `allocate_vents_and_capacitors` (see that function's own
    `heuristic_set` parameter). It defaults to "baseline_0.2" -- the value
    every candidate built here got implicitly before this parameter existed
    -- so a caller that doesn't pass it explicitly sees byte-for-byte
    identical output to before. `candidate_alternatives_fingerprint` below
    must be called with this same value whenever `AnalysisResultCache` is in
    use, so a cached result is never served across two different
    `heuristic_set` values.
    """
    if max_candidates < 1:
        raise ValueError("max_candidates must be at least 1")
    if search_depth < 1:
        raise ValueError("search_depth must be at least 1")
    baseline = _build_candidate(
        hull_id, profile_id, registry, allowed_weapon_ids, preferred_weapon_ids,
        denied_weapon_ids, locked_weapons_by_mount, empty_mount_ids, {}, flux_mode=flux_mode,
        allowed_hullmod_ids=allowed_hullmod_ids, preferred_hullmod_ids=preferred_hullmod_ids, denied_hullmod_ids=denied_hullmod_ids,
        allowed_wing_ids=allowed_wing_ids, preferred_wing_ids=preferred_wing_ids, denied_wing_ids=denied_wing_ids,
        weapon_role_overrides=weapon_role_overrides, heuristic_set=heuristic_set,
    )
    results = [baseline]
    seen = {tuple(sorted(baseline.variant.weapons_by_mount.items()))}
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None:
        return tuple(results)
    mount_ids = [str(mount.get("id", "")) for mount in sorted(hull.weapon_mounts, key=lambda item: str(item.get("id", ""))) if mount.get("id")]
    # Breadth-first across ranks: every mount's rank-1 alternative before
    # any mount's rank-2, so the closest-to-baseline alternatives always
    # sort first regardless of how deep the search is allowed to go.
    for rank in range(1, search_depth + 1):
        if len(results) >= max_candidates:
            break
        for mount_id in mount_ids:
            if len(results) >= max_candidates:
                break
            candidate = _build_candidate(
                hull_id, profile_id, registry, allowed_weapon_ids, preferred_weapon_ids,
                denied_weapon_ids, locked_weapons_by_mount, empty_mount_ids, {mount_id: rank},
                alternative_number=len(results), flux_mode=flux_mode,
                allowed_hullmod_ids=allowed_hullmod_ids, preferred_hullmod_ids=preferred_hullmod_ids, denied_hullmod_ids=denied_hullmod_ids,
                allowed_wing_ids=allowed_wing_ids, preferred_wing_ids=preferred_wing_ids, denied_wing_ids=denied_wing_ids,
                weapon_role_overrides=weapon_role_overrides, heuristic_set=heuristic_set,
            )
            key = tuple(sorted(candidate.variant.weapons_by_mount.items()))
            if key not in seen:
                seen.add(key)
                results.append(candidate)
    return tuple(results)


def generate_build_archetype_candidates(
    hull_id: str,
    registry: Registry,
    heuristic_set: str = "baseline_0.4",
    include_experimental: bool = True,
    max_candidates: int = 8,
    alternatives_per_build: int = 2,
    search_depth: int = 1,
    **generation_options: object,
) -> tuple[BuildCandidateResult, ...]:
    """Generate one conservative fit per viable Hull + BuildArchetype path.

    This is deliberately a build-path search, not a combinatorial cross-product.
    Each eligible path is generated and later scored independently.  Near
    duplicates collapse using deterministic build/variant distance before being
    returned; an Experimental path remains visibly Experimental.
    """
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None:
        return ()
    if max_candidates < 1 or alternatives_per_build < 1 or search_depth < 1:
        raise ValueError("max_candidates, alternatives_per_build, and search_depth must be at least 1")
    builds = infer_build_archetypes(hull, registry, heuristic_set)
    if not include_experimental:
        builds = tuple(build for build in builds if build.maturity == "VIABLE")
    # Each build receives its conservative baseline before any build receives
    # an alternate. This prevents a high-branching hull profile from consuming
    # the global cap and hiding another viable tactical solution.
    per_build: list[tuple[BuildArchetypeProfile, str, tuple[CandidateResult, ...]]] = []
    for build in builds[:max_candidates]:
        profile_id = profile_id_for_build(build.build_id)
        # heuristic_set is bound above as this function's own named
        # parameter, so it is never part of **generation_options and must
        # be forwarded explicitly here -- otherwise generate_candidate_alternatives
        # (and, through it, allocate_vents_and_capacitors) would silently
        # fall back to its own default regardless of what the caller of
        # generate_build_archetype_candidates actually selected, the same
        # gap this parameter was added to close.
        alternatives = generate_candidate_alternatives(
            hull_id, profile_id, registry, max_candidates=alternatives_per_build,
            search_depth=search_depth, heuristic_set=heuristic_set, **generation_options,
        )
        per_build.append((build, profile_id, alternatives))
    generated: list[BuildCandidateResult] = []
    for alternative_index in range(alternatives_per_build):
        for build, profile_id, alternatives in per_build:
            if len(generated) >= max_candidates:
                break
            if alternative_index < len(alternatives):
                generated.append(BuildCandidateResult(build, profile_id, alternatives[alternative_index]))
        if len(generated) >= max_candidates:
            break
    return tuple(_collapse_near_duplicates(generated, registry, heuristic_set))


def variant_distance(left: BuildCandidateResult, right: BuildCandidateResult, registry: Registry) -> float:
    """0=same fit, 1=meaningfully different Hull + BuildArchetype fit."""
    role_distance = 0.0 if left.build.role == right.build.role else 1.0
    style_distance = 0.0 if left.build.tactical_style == right.build.tactical_style else 1.0
    range_distance = 0.0 if left.build.target_range == right.build.target_range else 1.0
    left_weapons = set(left.candidate.variant.weapons_by_mount.values())
    right_weapons = set(right.candidate.variant.weapons_by_mount.values())
    weapon_distance = 1.0 - _jaccard(left_weapons, right_weapons)
    left_roles = _weapon_role_distribution(left.candidate.variant, registry)
    right_roles = _weapon_role_distribution(right.candidate.variant, registry)
    weapon_role_distance = 1.0 - _jaccard(set(left_roles), set(right_roles))
    hullmod_distance = 1.0 - _jaccard(set(left.candidate.variant.hullmods), set(right.candidate.variant.hullmods))
    flux_distance = 0.0 if left.build.flux_posture == right.build.flux_posture else 1.0
    survivability_distance = 0.0 if left.build.survivability_posture == right.build.survivability_posture else 1.0
    missile_pd_distance = (abs(left_roles.get("MISSILE", 0.0) - right_roles.get("MISSILE", 0.0)) + abs(left_roles.get("PD", 0.0) - right_roles.get("PD", 0.0))) / 2.0
    # No normalized variant mobility-allocation statistic exists yet. Tactical
    # style is retained as the evidence-backed mobility-proxy; unknown is not
    # fabricated into a distinct investment score.
    return round((role_distance + style_distance + range_distance + weapon_distance + weapon_role_distance + hullmod_distance + flux_distance + survivability_distance + missile_pd_distance) / 9.0, 6)


def _collapse_near_duplicates(items: list[BuildCandidateResult], registry: Registry, heuristic_set: str) -> list[BuildCandidateResult]:
    threshold = get_heuristic_set(heuristic_set).values["variant_diversity_near_duplicate_threshold"]
    kept: list[BuildCandidateResult] = []
    for item in items:
        similar = next((existing for existing in kept if 1.0 - variant_distance(item, existing, registry) >= threshold), None)
        if similar is None:
            kept.append(item)
    return kept


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 1.0


def _weapon_role_distribution(variant: Variant, registry: Registry) -> dict[str, float]:
    weapons = [registry.weapons.by_id[weapon_id] for weapon_id in variant.weapons_by_mount.values() if weapon_id in registry.weapons.by_id]
    if not weapons:
        return {}
    pd = sum("PD" in classify_weapon(weapon).role_tags for weapon in weapons) / len(weapons)
    missile = sum((weapon.mount_type or "").upper() == "MISSILE" for weapon in weapons) / len(weapons)
    artillery = sum("ARTILLERY" in classify_weapon(weapon).role_tags for weapon in weapons) / len(weapons)
    return {name: value for name, value in {"PD": pd, "MISSILE": missile, "ARTILLERY": artillery}.items() if value > 0.0}


def _build_candidate(
    hull_id: str,
    profile_id: str,
    registry: Registry,
    allowed_weapon_ids: set[str] | None,
    preferred_weapon_ids: set[str] | None,
    denied_weapon_ids: set[str] | None,
    locked_weapons_by_mount: dict[str, str] | None,
    empty_mount_ids: set[str] | None,
    rank_offsets: dict[str, int],
    alternative_number: int = 0,
    flux_mode: str = "BALANCED",
    allowed_hullmod_ids: set[str] | None = None,
    preferred_hullmod_ids: set[str] | None = None,
    denied_hullmod_ids: set[str] | None = None,
    allowed_wing_ids: set[str] | None = None,
    preferred_wing_ids: set[str] | None = None,
    denied_wing_ids: set[str] | None = None,
    weapon_role_overrides: dict[str, EntityOverride] | None = None,
    heuristic_set: str = "baseline_0.2",
) -> CandidateResult:
    hull = registry.hulls.by_id.get(hull_id)
    profile = get_profile(profile_id)
    if hull is None:
        variant = Variant(f"{hull_id}_{profile_id}_svg", "Unknown Hull", "generated", Path("generated"), hull_id=hull_id)
        return CandidateResult(variant, LegalityResult.ILLEGAL, ("Hull not indexed.",))
    selected: dict[str, str] = {}
    locked_weapons_by_mount = locked_weapons_by_mount or {}
    empty_mount_ids = empty_mount_ids or set()
    denied_weapon_ids = denied_weapon_ids or set()
    omissions: list[str] = []
    omission_records: list[CandidateOmission] = []
    spent = 0
    op_limit = hull.ordnance_points or 0
    # Precomputed once per candidate build instead of once per mount: the
    # mount loop below previously rescanned every registry weapon (with a
    # fresh .upper() normalization each time) for every mount on the hull,
    # an O(mounts * total_weapons) scan. Grouping by normalized mount_type
    # up front makes the per-mount lookup touch only the weapons that could
    # ever be eligible for that mount's compatible types. This is a pure
    # restructuring of the same filter -- membership in
    # `compatible_weapon_types`, size rank, ordnance_points presence -- not
    # a behavior change; see docs/WORK_LOG.md for the measured effect.
    weapons_by_mount_type: dict[str, list[tuple[Weapon, int]]] = {}
    for weapon in registry.weapons.by_id.values():
        if not weapon.mount_type or weapon.ordnance_points is None:
            continue
        size_rank = _SIZE_ORDER.get((weapon.size or "").upper(), 99)
        weapons_by_mount_type.setdefault(weapon.mount_type.upper(), []).append((weapon, size_rank))
    for mount in sorted(hull.weapon_mounts, key=lambda item: str(item.get("id", ""))):
        mount_id = str(mount.get("id", ""))
        mount_type = str(mount.get("type", "")).upper()
        mount_size = _SIZE_ORDER.get(str(mount.get("size", "")).upper())
        if mount_id and mount_id in hull.built_in_weapons:
            # Checked before the generic compatibility lookup below: a
            # hull-fixed mount's own "type" (often literally "BUILT_IN" in
            # real data) isn't a normal weapon-compatibility category, and
            # some real weapons declare mountType "BUILT_IN" themselves,
            # which would otherwise make them spuriously "eligible" for any
            # such mount regardless of which specific weapon this hull
            # actually hardwires there. Leaving it out of `selected` lets
            # the game auto-fill it, exactly like an omitted mount already
            # does. See validation/legality.py's BUILT_IN_WEAPON_OVERRIDDEN.
            omissions.append(f"{mount_id}: hull-fixed built-in weapon, left for the game to auto-fill")
            omission_records.append(CandidateOmission(
                "STRUCTURAL_SLOT_OMITTED", mount_id, mount_type,
                "Hull-fixed built-in weapon left for the game auto-fill path.",
            ))
            continue
        if mount_type in {"STATION_MODULE", "LAUNCH_BAY", "BUILT_IN"}:
            detail = f"Positively identified structural {mount_type} slot excluded from candidate weapon fitting."
            omissions.append(f"{mount_id or '<unknown mount>'}: structural slot omitted ({mount_type})")
            omission_records.append(CandidateOmission("STRUCTURAL_SLOT_OMITTED", mount_id or "<unknown mount>", mount_type, detail))
            continue
        compatible_weapon_types = MOUNT_TYPE_COMPATIBILITY.get(mount_type)
        if not mount_id or not mount_size or compatible_weapon_types is None:
            omissions.append(f"{mount_id or '<unknown mount>'}: unsupported mount semantics")
            omission_records.append(CandidateOmission(
                "UNSUPPORTED_MOUNT_SEMANTICS", mount_id or "<unknown mount>", mount_type or None,
                "Mount has no documented generic weapon-compatibility semantics.",
            ))
            continue
        if mount_id in empty_mount_ids:
            omissions.append(f"{mount_id}: explicitly left empty by advanced request")
            continue
        eligible = [
            weapon for mtype in compatible_weapon_types
            for weapon, size_rank in weapons_by_mount_type.get(mtype, ())
            if size_rank <= mount_size
            and (allowed_weapon_ids is None or weapon.id in allowed_weapon_ids)
            and weapon.id not in denied_weapon_ids
        ]
        if mount_id in locked_weapons_by_mount:
            locked_id = locked_weapons_by_mount[mount_id]
            eligible = [weapon for weapon in eligible if weapon.id == locked_id]
            if not eligible:
                omissions.append(f"{mount_id}: locked weapon {locked_id} lacks documented compatibility or is denied")
                continue
        native_sort = lambda weapon: 0 if preferred_weapon_ids is not None and weapon.id in preferred_weapon_ids else 1
        if profile.weapon_priority == "LONG_RANGE":
            eligible.sort(key=lambda weapon: (native_sort(weapon), -(weapon.range or 0), weapon.ordnance_points or 0, weapon.id))
        elif profile.weapon_priority == "PD_FIRST":
            # "PD" comes from classify_weapon's already-tested tag (a real
            # parsed-tags signal, analysis/classification.py), not a new
            # inference -- same evidence-category pattern as
            # hullmod_priority_tag, applied to weapons instead. A caller-
            # supplied override (core/overrides.py, additive-only) can add
            # a "PD" tag a mod's own data doesn't declare -- this is the
            # first place the Manual Override Layer affects generated
            # output, not just `svg query weapons`; it still can't touch
            # legality, only which weapon this quality heuristic prefers.
            pd_first = lambda weapon: 0 if "PD" in apply_role_tag_override(
                classify_weapon(weapon).role_tags, (weapon_role_overrides or {}).get(weapon.id)
            ) else 1
            eligible.sort(key=lambda weapon: (native_sort(weapon), pd_first(weapon), weapon.ordnance_points or 0, weapon.id))
        else:
            eligible.sort(key=lambda weapon: (native_sort(weapon), weapon.ordnance_points or 0, weapon.id))
        affordable = [item for item in eligible if spent + (item.ordnance_points or 0) <= op_limit]
        offset = rank_offsets.get(mount_id, 0)
        weapon = affordable[offset] if offset < len(affordable) else None
        if weapon is None:
            suffix = " at requested bounded-search rank" if offset else ""
            omissions.append(f"{mount_id}: no documented compatible weapon within OP limit{suffix}")
            continue
        selected[mount_id] = weapon.id
        spent += weapon.ordnance_points or 0
    # Hullmods, fighter wings, vents, and capacitors are additive to the
    # weapon-only baseline above, not something that can leave a mount
    # unfilled -- reported via the variant's own fields, not `omissions`
    # (which is reserved for mounts the generator could not fill).
    hullmod_selection = select_hullmods(
        hull, registry, op_limit - spent, allowed_hullmod_ids, preferred_hullmod_ids, denied_hullmod_ids,
        priority_tag=profile.hullmod_priority_tag,
    )
    spent += hullmod_selection.op_spent
    wing_selection = select_fighter_wings(
        hull, registry, op_limit - spent, allowed_wing_ids, preferred_wing_ids, denied_wing_ids,
    )
    spent += wing_selection.op_spent
    mounted_weapons = [registry.weapons.by_id[weapon_id] for weapon_id in selected.values() if weapon_id in registry.weapons.by_id]
    # hullmod_selection is finalized above (before this call), so its
    # hullmod_ids -- the same value that becomes variant.hullmods below --
    # is already available here for baseline_0.10's opt-in hullmod-aware
    # vent/capacitor allocation (generation/vent_cap.py). Ignored unless
    # that heuristic_set's gate flag is present; see allocate_vents_and_capacitors's
    # own docstring.
    allocation = allocate_vents_and_capacitors(
        hull, mounted_weapons, op_limit - spent, flux_mode, heuristic_set,
        hullmod_ids=hullmod_selection.hullmod_ids, registry=registry,
    )
    variant = Variant(
        id=f"{hull_id}_{profile_id}_svg" + (f"_alt{alternative_number}" if alternative_number else ""),
        name=f"{hull.name} {profile_id}" + (f" alternative {alternative_number}" if alternative_number else ""), source_mod="generated",
        source_path=Path("generated"), hull_id=hull.id, weapons_by_mount=selected,
        fighter_wings=wing_selection.wing_ids,
        hullmods=hullmod_selection.hullmod_ids,
        flux_vents=allocation.vents or None, flux_capacitors=allocation.capacitors or None,
    )
    assessment = validate_variant(variant, registry)
    return CandidateResult(variant, assessment.result, tuple(omissions), tuple(omission_records))


# --- Result-cache reuse (core/result_cache.py) --------------------------
#
# Both generate_candidate_alternatives and generate_build_archetype_candidates
# are deterministic, read-only searches over one target hull plus the whole
# weapon/hullmod/fighter registry -- see _candidate_generation_entity_hashes
# below for why eligibility scans are never narrowed to a hull-specific
# subset. Repeated calls for the same hull/profile/constraints (a GUI user
# reopening the same hull, or a batch evaluation across runs) can safely
# reuse a prior result -- but only when every real input is honestly
# captured, following analysis/gap_recommendation.py::recommend_gap_solutions'
# already-proven fingerprint/payload pattern. `_build_candidate`'s own
# internals (the mount-eligibility loop's algorithmic speedup applied
# earlier) are untouched by any of this -- only the two outer search
# functions below are wrapped from the caller side (api.py::run_generate).

# `_build_candidate`'s call into
# generation/vent_cap.py::allocate_vents_and_capacitors now receives a real,
# caller-controlled `heuristic_set`, forwarded from
# generate_conservative_candidate / generate_candidate_alternatives /
# generate_build_archetype_candidates (all three default to "baseline_0.2"
# for full backward compatibility -- the value every one of them used
# implicitly before this parameter existed). This used to be a permanently
# fixed value (the former CANDIDATE_GENERATION_FIXED_VENT_CAP_HEURISTIC_SET
# constant, removed once the parameter became real) specifically so that a
# constant, non-varying marker could stand in for it in
# candidate_alternatives_fingerprint / build_archetype_candidates_fingerprint.
# Both fingerprint functions now fold the real `heuristic_set` value into
# their returned AnalysisContextFingerprint.heuristic_set instead -- see each
# function's own docstring below. No registry entry currently varies
# beginner_flux_target/balanced_flux_target/aggressive_flux_target (the only
# heuristic values allocate_vents_and_capacitors reads) across baseline_0.1
# through baseline_0.8, so this is a correctness/plumbing fix with no
# currently observable output difference -- but the fingerprint must still
# treat it as a real, varying input so a future registry entry that does
# change one of those values (or a differently configured heuristic set)
# can never have its vent/capacitor allocation served from a cache entry
# populated under a different heuristic_set.

# Bump if generation's adapter-derived static tables (adapters.flux_unit_cost,
# adapters.hullmod_incompatibility_pairs, adapters.max_logistics_hullmods, and
# analysis/combat_stats.py's compute_derived_defense_stats -- all consulted
# by _build_candidate / select_hullmods / allocate_vents_and_capacitors) ever
# change value or coverage -- mirrors GAP_RECOMMENDATION_ADAPTER_VERSION in
# analysis/gap_recommendation.py for the same reason.
CANDIDATE_GENERATION_ADAPTER_VERSION = "vanilla_static_adapters-1"


def _candidate_generation_entity_hashes(hull_id: str, registry: Registry) -> tuple[str, ...] | None:
    """The target hull's own hash plus every weapon/hullmod/fighter's hash,
    or ``None`` if incomplete.

    `_build_candidate`'s weapon-eligibility scan, `select_hullmods`, and
    `select_fighter_wings` all iterate the *entire* weapon/hullmod/fighter
    registry (never narrowed to a hull-specific subset -- see their own
    docstrings), so the honest dependency surface is the whole of those
    three indexes, not just entities this hull's mounts happen to use
    today. `registry.hulls` (beyond the one target hull), `registry.variants`,
    and `registry.factions` are excluded: `validate_variant`
    (validation/legality.py) only ever looks up `variant.hull_id` in
    `registry.hulls`, never any other hull, and nothing in this module or
    its helpers consults `registry.variants` or `registry.factions` at all.
    Any entity missing a source hash fails this closed rather than guessing
    the real surface is narrower.
    """
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None or hull.source_hash is None:
        return None
    hashes = [hull.source_hash]
    for index in (registry.weapons, registry.hullmods, registry.fighters):
        for entity in index.by_id.values():
            if entity.source_hash is None:
                return None
            hashes.append(entity.source_hash)
    return tuple(sorted(hashes))


def _hash_json(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sorted_or_none(values: set[str] | None) -> list[str] | None:
    return sorted(values) if values is not None else None


def _weapon_role_overrides_hash(weapon_role_overrides: dict[str, EntityOverride] | None) -> str:
    """A complete, stable hash of every field `EntityOverride` actually
    carries. `EntityOverride` (core/overrides.py) is a plain frozen
    dataclass of (entity_id: str, role_tags: tuple[str, ...], notes:
    str | None) -- a trivially complete JSON round-trip, unlike a parameter
    whose type has no obvious stable serialization."""
    if not weapon_role_overrides:
        return "NONE"
    payload = {
        entity_id: {"role_tags": list(override.role_tags), "notes": override.notes}
        for entity_id, override in weapon_role_overrides.items()
    }
    return _hash_json(payload)


def candidate_alternatives_fingerprint(
    hull_id: str,
    profile_id: str,
    registry: Registry,
    allowed_weapon_ids: set[str] | None = None,
    preferred_weapon_ids: set[str] | None = None,
    denied_weapon_ids: set[str] | None = None,
    locked_weapons_by_mount: dict[str, str] | None = None,
    empty_mount_ids: set[str] | None = None,
    max_candidates: int = 5,
    flux_mode: str = "BALANCED",
    allowed_hullmod_ids: set[str] | None = None,
    preferred_hullmod_ids: set[str] | None = None,
    denied_hullmod_ids: set[str] | None = None,
    allowed_wing_ids: set[str] | None = None,
    preferred_wing_ids: set[str] | None = None,
    denied_wing_ids: set[str] | None = None,
    search_depth: int = 1,
    weapon_role_overrides: dict[str, EntityOverride] | None = None,
    heuristic_set: str = "baseline_0.2",
) -> AnalysisContextFingerprint:
    """Declare `generate_candidate_alternatives`'s (and, for a single
    depth-1 baseline, `generate_conservative_candidate`'s) real, complete
    dependency context.

    `hull_id` is folded into `constraints_hash` (not just relied on as the
    cache's `target_id`) for the same collision-safety reason
    `gap_recommendation_fingerprint` folds `faction.id` in:
    `AnalysisResultCache.key` only hashes the declared context, and its
    table's real primary key is `cache_key` alone -- two different hulls
    evaluated with an otherwise-identical registry/profile/constraints
    could otherwise coincide in context hash and collide in that
    single-column primary key.

    `heuristic_set` is a real, consumed parameter now (not a fixed marker):
    it is `_build_candidate`'s own default and, through it, governs
    `allocate_vents_and_capacitors`'s flux-sustainability target. It MUST be
    passed the exact same value the matching `generate_candidate_alternatives`
    / `generate_conservative_candidate` call receives -- a caller that
    fingerprints one heuristic_set but generates with another would produce
    a cache entry that silently serves a different heuristic_set's result
    on the next lookup for the mismatched one, exactly the staleness this
    fingerprint exists to prevent.
    """
    entity_hashes = _candidate_generation_entity_hashes(hull_id, registry)
    constraints_payload = {
        "hull_id": hull_id,
        "profile_id": profile_id,
        "allowed_weapon_ids": _sorted_or_none(allowed_weapon_ids),
        "preferred_weapon_ids": _sorted_or_none(preferred_weapon_ids),
        "denied_weapon_ids": _sorted_or_none(denied_weapon_ids),
        "locked_weapons_by_mount": dict(sorted((locked_weapons_by_mount or {}).items())),
        "empty_mount_ids": _sorted_or_none(empty_mount_ids),
        "max_candidates": max_candidates,
        "flux_mode": flux_mode,
        "allowed_hullmod_ids": _sorted_or_none(allowed_hullmod_ids),
        "preferred_hullmod_ids": _sorted_or_none(preferred_hullmod_ids),
        "denied_hullmod_ids": _sorted_or_none(denied_hullmod_ids),
        "allowed_wing_ids": _sorted_or_none(allowed_wing_ids),
        "preferred_wing_ids": _sorted_or_none(preferred_wing_ids),
        "denied_wing_ids": _sorted_or_none(denied_wing_ids),
        "search_depth": search_depth,
    }
    complete = entity_hashes is not None
    return AnalysisContextFingerprint(
        operation="candidate_alternatives",
        entity_hashes=entity_hashes if entity_hashes is not None else (),
        heuristic_set=heuristic_set,
        adapter_versions=(CANDIDATE_GENERATION_ADAPTER_VERSION,),
        override_hash=_weapon_role_overrides_hash(weapon_role_overrides),
        constraints_hash=_hash_json(constraints_payload),
        readiness=CacheReadiness.CACHE_SAFE if complete else CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT,
    )


def build_archetype_candidates_fingerprint(
    hull_id: str,
    registry: Registry,
    heuristic_set: str = "baseline_0.4",
    include_experimental: bool = True,
    max_candidates: int = 8,
    alternatives_per_build: int = 2,
    search_depth: int = 1,
    allowed_weapon_ids: set[str] | None = None,
    preferred_weapon_ids: set[str] | None = None,
    denied_weapon_ids: set[str] | None = None,
    locked_weapons_by_mount: dict[str, str] | None = None,
    empty_mount_ids: set[str] | None = None,
    flux_mode: str = "BALANCED",
    allowed_hullmod_ids: set[str] | None = None,
    preferred_hullmod_ids: set[str] | None = None,
    denied_hullmod_ids: set[str] | None = None,
    allowed_wing_ids: set[str] | None = None,
    preferred_wing_ids: set[str] | None = None,
    denied_wing_ids: set[str] | None = None,
    weapon_role_overrides: dict[str, EntityOverride] | None = None,
) -> AnalysisContextFingerprint:
    """Declare `generate_build_archetype_candidates`'s real, complete
    dependency context.

    `heuristic_set` here is a real, consumed parameter in two independent
    ways: `infer_build_archetypes`'s build inference and
    `_collapse_near_duplicates`'s diversity threshold both read it directly,
    AND `generate_build_archetype_candidates` forwards this exact same value
    into every per-build `generate_candidate_alternatives` call it makes
    (see that function's own comment), which in turn governs
    `allocate_vents_and_capacitors`'s flux-sustainability target for every
    generated build path. Because it is the identical parameter value in
    both roles, the single `heuristic_set=heuristic_set` field below already
    covers both dependency surfaces honestly -- there is no separate fixed
    vent/capacitor marker to track here (unlike `candidate_alternatives_fingerprint`
    before this parameter became real everywhere).
    """
    entity_hashes = _candidate_generation_entity_hashes(hull_id, registry)
    constraints_payload = {
        "hull_id": hull_id,
        "include_experimental": include_experimental,
        "max_candidates": max_candidates,
        "alternatives_per_build": alternatives_per_build,
        "search_depth": search_depth,
        "allowed_weapon_ids": _sorted_or_none(allowed_weapon_ids),
        "preferred_weapon_ids": _sorted_or_none(preferred_weapon_ids),
        "denied_weapon_ids": _sorted_or_none(denied_weapon_ids),
        "locked_weapons_by_mount": dict(sorted((locked_weapons_by_mount or {}).items())),
        "empty_mount_ids": _sorted_or_none(empty_mount_ids),
        "flux_mode": flux_mode,
        "allowed_hullmod_ids": _sorted_or_none(allowed_hullmod_ids),
        "preferred_hullmod_ids": _sorted_or_none(preferred_hullmod_ids),
        "denied_hullmod_ids": _sorted_or_none(denied_hullmod_ids),
        "allowed_wing_ids": _sorted_or_none(allowed_wing_ids),
        "preferred_wing_ids": _sorted_or_none(preferred_wing_ids),
        "denied_wing_ids": _sorted_or_none(denied_wing_ids),
    }
    complete = entity_hashes is not None
    return AnalysisContextFingerprint(
        operation="build_archetype_candidates",
        entity_hashes=entity_hashes if entity_hashes is not None else (),
        heuristic_set=heuristic_set,
        adapter_versions=(CANDIDATE_GENERATION_ADAPTER_VERSION,),
        override_hash=_weapon_role_overrides_hash(weapon_role_overrides),
        constraints_hash=_hash_json(constraints_payload),
        readiness=CacheReadiness.CACHE_SAFE if complete else CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT,
    )


def _variant_to_payload(variant: Variant) -> dict[str, Any]:
    """JSON-safe serialization. `AnalysisResultCache.put` calls
    `json.dumps` with no `default=` fallback, so `Path` fields (unlike a
    plain dataclass's other fields) must be converted explicitly -- a bare
    `dataclasses.asdict(variant)` would leave `source_path` as a `Path`
    object and fail to serialize."""
    return {
        "id": variant.id, "name": variant.name, "source_mod": variant.source_mod,
        "source_path": str(variant.source_path), "source_hash": variant.source_hash,
        "source_mod_version": variant.source_mod_version, "raw": variant.raw,
        "hull_id": variant.hull_id, "weapons_by_mount": dict(variant.weapons_by_mount),
        "hullmods": list(variant.hullmods), "fighter_wings": list(variant.fighter_wings),
        "flux_vents": variant.flux_vents, "flux_capacitors": variant.flux_capacitors,
    }


def _variant_from_payload(data: dict[str, Any]) -> Variant:
    return Variant(
        id=data["id"], name=data["name"], source_mod=data["source_mod"],
        source_path=Path(data["source_path"]), source_hash=data.get("source_hash"),
        source_mod_version=data.get("source_mod_version"), raw=dict(data.get("raw") or {}),
        hull_id=data.get("hull_id"), weapons_by_mount=dict(data.get("weapons_by_mount") or {}),
        hullmods=tuple(data.get("hullmods") or ()), fighter_wings=tuple(data.get("fighter_wings") or ()),
        flux_vents=data.get("flux_vents"), flux_capacitors=data.get("flux_capacitors"),
    )


def candidate_result_to_payload(result: CandidateResult) -> dict[str, Any]:
    return {
        "variant": _variant_to_payload(result.variant),
        "legality": result.legality.value,
        "omissions": list(result.omissions),
        "omission_records": [asdict(item) for item in result.omission_records],
    }


def candidate_result_from_payload(data: dict[str, Any]) -> CandidateResult:
    return CandidateResult(
        variant=_variant_from_payload(data["variant"]),
        legality=LegalityResult(data["legality"]),
        omissions=tuple(data.get("omissions") or ()),
        omission_records=tuple(CandidateOmission(**item) for item in data.get("omission_records", ()) if isinstance(item, dict)),
    )


def candidate_alternatives_result_to_payload(results: tuple[CandidateResult, ...]) -> dict[str, Any]:
    return {"candidates": [candidate_result_to_payload(item) for item in results]}


def candidate_alternatives_result_from_payload(payload: dict[str, Any]) -> tuple[CandidateResult, ...]:
    """Reverses `candidate_alternatives_result_to_payload` field-for-field --
    every tuple-typed field is rebuilt explicitly so a cache hit compares
    equal (`==`) to the same fresh computation, matching
    `gap_recommendation_result_from_payload`'s own equality guarantee."""
    return tuple(candidate_result_from_payload(item) for item in payload.get("candidates", ()))


def _restore_scenario_objective(data: dict[str, Any]) -> ScenarioObjective:
    return ScenarioObjective(
        objective_id=data["objective_id"], support_state=data["support_state"],
        required_signals=tuple(data.get("required_signals") or ()), note=data["note"],
    )


def _restore_build_archetype_profile(data: dict[str, Any]) -> BuildArchetypeProfile:
    return BuildArchetypeProfile(
        hull_id=data["hull_id"], build_id=data["build_id"], role=data["role"],
        tactical_style=data["tactical_style"], compatibility=data["compatibility"],
        confidence=data["confidence"], maturity=data["maturity"], target_range=data["target_range"],
        flux_posture=data["flux_posture"], survivability_posture=data["survivability_posture"],
        equipment_priorities=tuple(data.get("equipment_priorities") or ()),
        ai_suitability=data["ai_suitability"], player_suitability=data["player_suitability"],
        strengths=tuple(data.get("strengths") or ()), weaknesses=tuple(data.get("weaknesses") or ()),
        supporting_evidence=tuple(data.get("supporting_evidence") or ()),
        scenario_objectives=tuple(_restore_scenario_objective(item) for item in data.get("scenario_objectives") or ()),
        evidence_class=EvidenceClass(data.get("evidence_class") or EvidenceClass.INFERRED_MECHANICS.value),
    )


def build_candidate_result_to_payload(result: BuildCandidateResult) -> dict[str, Any]:
    return {
        "build": asdict(result.build), "profile_id": result.profile_id,
        "candidate": candidate_result_to_payload(result.candidate),
    }


def build_candidate_result_from_payload(data: dict[str, Any]) -> BuildCandidateResult:
    return BuildCandidateResult(
        build=_restore_build_archetype_profile(data["build"]), profile_id=data["profile_id"],
        candidate=candidate_result_from_payload(data["candidate"]),
    )


def build_archetype_candidates_result_to_payload(results: tuple[BuildCandidateResult, ...]) -> dict[str, Any]:
    return {"candidates": [build_candidate_result_to_payload(item) for item in results]}


def build_archetype_candidates_result_from_payload(payload: dict[str, Any]) -> tuple[BuildCandidateResult, ...]:
    return tuple(build_candidate_result_from_payload(item) for item in payload.get("candidates", ()))
