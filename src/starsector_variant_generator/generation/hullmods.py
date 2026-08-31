from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.analysis.combat_stats import (
    compute_derived_defense_stats,
)
from starsector_variant_generator.core.models import Hull, Hullmod
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class HullmodSelection:
    hullmod_ids: tuple[str, ...]
    op_spent: int
    note: str


def select_hullmods(
    hull: Hull,
    registry: Registry,
    remaining_op: int,
    allowed_hullmod_ids: set[str] | None = None,
    preferred_hullmod_ids: set[str] | None = None,
    denied_hullmod_ids: set[str] | None = None,
    max_hullmods: int = 2,
    priority_tag: str | None = None,
) -> HullmodSelection:
    """Select a conservative, evidence-bound set of additional hullmods.

    There is no per-mount compatibility filter for hullmods the way there is
    for weapons (mount type/size), so this deliberately does not try to
    judge which hullmod "suits" a role -- that would mean fabricating a
    game-balance opinion this project has no documented basis for. Instead
    it mirrors the weapon selector's existing, already-legitimate pattern:
    `preferred_hullmod_ids` (in practice, a faction's own parsed
    `known_hullmods` -- real evidence, not invented) sorts first.  For a
    `Defenses` profile priority, an installed hullmod with an actually
    applicable, verified DEFENSE adapter effect sorts next.  "Applicable"
    is intentionally checked through `compute_derived_defense_stats`, so a
    missing base stat or an unknown/mod-scripted effect does not acquire a
    preference merely because its name or ui tag sounds defensive. Then, if
    the calling profile declares a `priority_tag` (RoleProfile's
    `hullmod_priority_tag`, e.g. "Defenses" for TANK, "Fighters" for
    CARRIER_SUPPORT), a hullmod whose parsed `uiTags` CSV column contains
    that tag sorts next -- a documented *category* preference, not a claim
    about any specific hullmod; then lowest OP cost, matching the same
    conservative-baseline bias weapon selection already uses. Every result
    is independently re-validated by
    validate_variant exactly like every other candidate, so a bug here can
    only ever produce a candidate ranked lower or marked ILLEGAL/
    NOT_DETERMINABLE -- never a falsely-LEGAL one.

    `max_hullmods` defaults to 2, not an unbounded "take everything OP
    allows": a live-scan check of all 324 real core (vanilla) variants that
    carry any hullmods found a median and mean of ~2 hullmods per variant
    (88% have 1-3; only one variant in the whole set had more than 7). An
    OP-bounded-only selector was tried first and produced a 20-hullmod
    frigate on live data -- unrealistic and not representative of how any
    real variant is actually built -- which is why this cap exists and is
    evidence-derived rather than an arbitrary guess. See docs/ROADMAP.md
    Tier 4.

    Hidden hullmods (story/dev/quest-restricted, per Hullmod.hidden) are
    never selected: GUI.md's own "Hidden/Secret Equipment" principle
    (default OFF, must not silently appear) applies just as much to
    generation as to a GUI dropdown. Built-in hullmods the hull already has
    for free are skipped as redundant. Hullmods tagged "Logistics" (uiTags)
    are capped at the same documented maximum
    (adapters.vanilla.MAX_LOGISTICS_HULLMODS) legality itself enforces, so
    this selector cannot hand back a candidate that fails its own
    LOGISTICS_HULLMOD_LIMIT_EXCEEDED check for a reason it could have
    avoided.
    """
    from starsector_variant_generator.adapters import max_logistics_hullmods

    denied_hullmod_ids = denied_hullmod_ids or set()
    preferred_hullmod_ids = preferred_hullmod_ids or set()

    eligible: list[Hullmod] = []
    for hullmod in registry.hullmods.by_id.values():
        if hullmod.id in hull.built_in_hullmods or hullmod.id in denied_hullmod_ids:
            continue
        if hullmod.hidden is True or hullmod.built_in_only is True:
            continue
        if allowed_hullmod_ids is not None and hullmod.id not in allowed_hullmod_ids:
            continue
        cost = hullmod.op_cost_by_hull_size.get(hull.hull_size or "")
        if cost is None:
            continue
        eligible.append(hullmod)

    verified_defense_ids: frozenset[str] = frozenset()
    if priority_tag == "Defenses":
        # Do not infer an effect from a ui tag or an ID.  The adapter plus
        # derived-state calculation is the sole positive evidence here and
        # also handles skin hulls' documented base-stat fallback.
        verified_defense_ids = frozenset(
            hullmod.id
            for hullmod in eligible
            if compute_derived_defense_stats(hull, (hullmod.id,), registry).applied_effects
        )

    eligible.sort(key=lambda hullmod: (
        0 if hullmod.id in preferred_hullmod_ids else 1,
        0 if hullmod.id in verified_defense_ids else 1,
        0 if priority_tag and priority_tag in str(hullmod.raw.get("uiTags", "")) else 1,
        hullmod.op_cost_by_hull_size[hull.hull_size or ""],
        hullmod.id,
    ))

    selected: list[str] = []
    spent = 0
    logistics_count = 0
    max_logistics = max_logistics_hullmods()
    for hullmod in eligible:
        if len(selected) >= max_hullmods:
            break
        cost = hullmod.op_cost_by_hull_size[hull.hull_size or ""]
        if spent + cost > remaining_op:
            continue
        is_logistics = "Logistics" in str(hullmod.raw.get("uiTags", ""))
        if is_logistics and logistics_count >= max_logistics:
            continue
        selected.append(hullmod.id)
        spent += cost
        if is_logistics:
            logistics_count += 1

    return HullmodSelection(
        tuple(sorted(selected)), spent,
        f"Selected {len(selected)} hullmod(s) within {remaining_op} remaining OP." if selected else "No eligible hullmods within remaining OP.",
    )
