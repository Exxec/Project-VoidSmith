from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from starsector_variant_generator.adapters import defense_hullmod_effects
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.parsers.common import optional_float

# The hull CSV column names backing each stat this module models. Neither
# is a typed Hull dataclass field (core/models.py) -- see
# adapters/vanilla/__init__.py's DEFENSE_HULLMOD_EFFECTS docstring for why.
_DEFENSE_STAT_CSV_COLUMNS = {"armor_rating": "armor rating", "hull_hp": "hitpoints"}


@dataclass(frozen=True)
class AppliedDefenseEffect:
    """One verified DEFENSE hullmod effect actually applied.

    `gain` is always computed against the hull's true, unmodified base
    value (never a running total updated by a previously-applied hullmod),
    so the order `hullmod_ids` are supplied in never changes the result --
    unlike compute_derived_civilian_stats, which does update a running
    total (safe there only because no two of its LOGISTICS hullmods ever
    target the same stat with a percent component; two DEFENSE hullmods
    routinely do -- see DerivedDefenseStats.stacking_notes).
    """

    hullmod_id: str
    stat: str
    base_value: float
    gain: float
    op_cost: int | None
    efficiency: float | None
    # ROADMAP.md Phase 29 (Evidence/Provenance Unification): always sourced
    # from a verified adapters.defense_hullmod_effects table entry --
    # AGENTS.md's adapter-layer ladder tier 6, ADAPTER_MODELED. Always
    # correct by construction; a hullmod without a verified entry never
    # produces one of these records.
    evidence_class: EvidenceClass = EvidenceClass.ADAPTER_MODELED


@dataclass(frozen=True)
class DerivedDefenseStats:
    """A first slice of DATA_SCHEMA.md v0.3's DerivedShipState covering the
    DEFENSE hullmod category: a hull's base armor rating and hull hitpoints
    ("hull integrity" in the game's own hullmod description text), as
    modified by verified DEFENSE hullmods (adapters.defense_hullmod_effects).

    Exactly like DerivedCivilianStats: a hullmod without a verified entry
    contributes nothing here -- absence of verified data is never treated
    as absence of effect. `effective_armor_rating`/`effective_hull_hp` are
    None whenever the base value itself is unknown (hull.raw is missing
    the CSV column, e.g. for a skin whose base hull couldn't be resolved)
    OR whenever more than one verified hullmod targets that stat (see
    `stacking_notes`) -- in the latter case each contribution is still
    available individually in `applied_effects`.
    """

    armor_rating_base: float | None
    hull_hp_base: float | None
    effective_armor_rating: float | None
    effective_hull_hp: float | None
    applied_effects: tuple[AppliedDefenseEffect, ...]
    unverified_hullmod_ids: tuple[str, ...]
    stacking_notes: tuple[str, ...]

    @property
    def applied_effect_hullmod_ids(self) -> tuple[str, ...]:
        """Unique hullmod ids with at least one applied effect, in first-seen order."""
        seen: dict[str, None] = {}
        for effect in self.applied_effects:
            seen.setdefault(effect.hullmod_id, None)
        return tuple(seen)


def _base_defense_stat(hull: Hull, registry: Registry, stat: str) -> float | None:
    """Read one DEFENSE base stat from the hull's own raw CSV row.

    Falls back to the base hull's raw for a skin-derived Hull, whose own
    `raw` holds only `skin_data`/`base_hull_id`/`base_hull_source_mod`, not
    the CSV row (see hull_from_skin in parsers/entities.py). Never guesses
    beyond that one level -- `_resolve_skins` in core/scanner.py only ever
    resolves a skin against a non-skin base hull, so one level is always
    sufficient; if the base can't be found (ambiguous/missing id), the
    stat is left unavailable rather than assumed.
    """
    column = _DEFENSE_STAT_CSV_COLUMNS[stat]
    value = optional_float(hull.raw.get(column))
    if value is not None:
        return value
    base_hull_id = hull.raw.get("base_hull_id")
    if isinstance(base_hull_id, str):
        base_hull = registry.hulls.by_id.get(base_hull_id)
        if base_hull is not None:
            return optional_float(base_hull.raw.get(column))
    return None


def compute_derived_defense_stats(hull: Hull, hullmod_ids: Iterable[str], registry: Registry) -> DerivedDefenseStats:
    """Apply verified DEFENSE hullmod effects to a hull's base armor rating and hull HP.

    Deliberately does not compute a single combined effective value when
    more than one applied hullmod targets the same stat (e.g.
    `reinforcedhull` + `blast_doors`, both percent bonuses to hull_hp):
    whether vanilla stacks multiple hull-HP-percent hullmods additively or
    multiplicatively is not documented anywhere this project can verify,
    so guessing would violate Agent.md's "do not infer undocumented
    behavior" rule. Each contribution is reported individually in
    `applied_effects` instead, with an explanatory note in
    `stacking_notes` -- the same approach `compute_derived_civilian_stats`
    already uses for combined civilian maintenance penalties.
    """
    effects_by_hullmod: dict[str, list] = {}
    for effect in defense_hullmod_effects(hull.source_mod):
        effects_by_hullmod.setdefault(effect.hullmod_id, []).append(effect)

    base_values: dict[str, float | None] = {
        "armor_rating": _base_defense_stat(hull, registry, "armor_rating"),
        "hull_hp": _base_defense_stat(hull, registry, "hull_hp"),
    }
    applied_by_stat: dict[str, list[AppliedDefenseEffect]] = {"armor_rating": [], "hull_hp": []}
    unverified: list[str] = []

    for hullmod_id in hullmod_ids:
        effect_list = effects_by_hullmod.get(hullmod_id)
        if not effect_list:
            unverified.append(hullmod_id)
            continue
        any_applied = False
        for effect in effect_list:
            base = base_values.get(effect.stat)
            if base is None:
                continue
            if effect.flat_bonus_by_hull_size is not None:
                gain = effect.flat_bonus_by_hull_size.get(hull.hull_size or "")
            elif effect.percent_bonus is not None:
                gain = base * effect.percent_bonus
            else:
                gain = None
            if gain is None:
                continue
            registry_hullmod = registry.hullmods.by_id.get(hullmod_id)
            op_cost = registry_hullmod.op_cost_by_hull_size.get(hull.hull_size or "") if registry_hullmod else None
            efficiency = (gain / op_cost) if op_cost else None
            applied_by_stat[effect.stat].append(AppliedDefenseEffect(hullmod_id, effect.stat, base, gain, op_cost, efficiency))
            any_applied = True
        if not any_applied:
            unverified.append(hullmod_id)

    effective: dict[str, float | None] = {}
    stacking_notes: list[str] = []
    for stat, base in base_values.items():
        appliers = applied_by_stat[stat]
        if base is None:
            effective[stat] = None
        elif not appliers:
            effective[stat] = base
        elif len(appliers) == 1:
            effective[stat] = base + appliers[0].gain
        else:
            effective[stat] = None
            ids = ", ".join(effect.hullmod_id for effect in appliers)
            stacking_notes.append(
                f"{stat}: {len(appliers)} verified hullmods apply ({ids}) -- combined stacking behavior across "
                "multiple hullmods on the same stat is not documented, so no combined effective value is "
                "computed; see applied_effects for each hullmod's individual contribution against the base value."
            )

    return DerivedDefenseStats(
        armor_rating_base=base_values["armor_rating"], hull_hp_base=base_values["hull_hp"],
        effective_armor_rating=effective["armor_rating"], effective_hull_hp=effective["hull_hp"],
        applied_effects=tuple(applied_by_stat["armor_rating"] + applied_by_stat["hull_hp"]),
        unverified_hullmod_ids=tuple(unverified),
        stacking_notes=tuple(stacking_notes),
    )
