from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.core.models import FighterWing, Hull
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class FighterWingSelection:
    wing_ids: tuple[str, ...]
    op_spent: int
    note: str


def select_fighter_wings(
    hull: Hull,
    registry: Registry,
    remaining_op: int,
    allowed_wing_ids: set[str] | None = None,
    preferred_wing_ids: set[str] | None = None,
    denied_wing_ids: set[str] | None = None,
) -> FighterWingSelection:
    """Select fighter wings up to the hull's documented bay capacity.

    Unlike hullmods (generation/hullmods.py), fighter wings have a real,
    directly-parsed physical capacity -- `hull.fighter_bays` (Tier 1.3) --
    so there is no need to invent an evidence-derived cap the way
    `select_hullmods`'s `max_hullmods` was: filling every available bay
    (subject to OP) is the natural conservative behavior, not an
    unrealistic maximum. When `hull.fighter_bays` is unparsed (None), no
    wings are selected at all -- adding any would risk exceeding an unknown
    capacity, exactly mirroring FIGHTER_BAY_CAPACITY_UNKNOWN's fail-closed
    legality behavior for the same missing data.

    `preferred_wing_ids` follows the same evidence pattern as weapons and
    hullmods: in practice a faction's real parsed `known_fighters`, not an
    invented "good fighter" judgment.
    """
    if not hull.fighter_bays:
        return FighterWingSelection((), 0, "No documented fighter-bay capacity for this hull; no fighter wings selected.")

    denied_wing_ids = denied_wing_ids or set()
    preferred_wing_ids = preferred_wing_ids or set()

    eligible: list[FighterWing] = []
    for wing in registry.fighters.by_id.values():
        if wing.id in hull.built_in_fighter_wings or wing.id in denied_wing_ids:
            continue
        if allowed_wing_ids is not None and wing.id not in allowed_wing_ids:
            continue
        if wing.op_cost is None:
            continue
        eligible.append(wing)

    eligible.sort(key=lambda wing: (
        0 if wing.id in preferred_wing_ids else 1,
        wing.op_cost or 0,
        wing.id,
    ))

    selected: list[str] = []
    spent = 0
    for wing in eligible:
        if len(selected) >= hull.fighter_bays:
            break
        cost = wing.op_cost or 0
        if spent + cost > remaining_op:
            continue
        selected.append(wing.id)
        spent += cost

    return FighterWingSelection(
        tuple(selected), spent,
        f"Selected {len(selected)} fighter wing(s) within {hull.fighter_bays} documented bay(s) and {remaining_op} remaining OP." if selected else "No eligible fighter wings within capacity/OP.",
    )
