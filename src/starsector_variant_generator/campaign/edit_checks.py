"""Workshop checks only; never call fitting validation or quality services."""
from __future__ import annotations

import struct
from collections import Counter
from decimal import Decimal

from .catalog import CommodityCatalog
from .edit_plan import SAVE_WRITE_GATE, EditPlan, EditRequest, PlannedChange
from .locators import ResourceSnapshot

# Tier-1 contract, not a catalog: membership must still come from installed CSV.
TIER1_COMMODITIES = frozenset(("supplies", "fuel", "crew", "marines", "heavy_machinery"))


def build_edit_plan(source_dir: str, snapshot: ResourceSnapshot, requests: tuple[EditRequest, ...],
                    catalog: CommodityCatalog, *, allow_unknown_capacity: bool = False) -> EditPlan:
    if type(allow_unknown_capacity) is not bool:
        raise ValueError("Capacity opt-in must be an explicit boolean")
    if not requests or len(requests) > 7:
        raise ValueError("Plan needs one to seven tier-1 requests")
    if any(not isinstance(request, EditRequest) or not isinstance(request.target, str) for request in requests):
        raise ValueError("Plan accepts typed resource requests only")
    resources = {resource.target: resource for resource in snapshot.resources}
    duplicates = Counter(request.target for request in requests)
    changes: list[PlannedChange] = []
    rows: list = []
    for request in requests:
        resource = resources.get(request.target)
        outcome, reason, replacement = "ACCEPTED", "Whole non-negative quantity fits the qualified stored type", None
        commodity = request.target.removeprefix("commodity:") if request.target.startswith("commodity:") else None
        if request.target not in ("credits", "story_points") and commodity not in TIER1_COMMODITIES:
            outcome, reason = "REFUSED", "Target is outside tier 1"
        elif duplicates[request.target] != 1:
            outcome, reason = "REFUSED", "Duplicate request target"
        elif type(request.value) is not int or request.value < 0:
            outcome, reason = "REFUSED", "Quantity must be a whole non-negative integer"
        elif snapshot.status != "READABLE" or resource is None:
            outcome, reason = "REFUSED", "No qualified locator; missing stacks are never invented"
        elif commodity is not None and (catalog.status != "PARSED" or commodity not in catalog.identifiers):
            outcome, reason = "REFUSED", "Commodity id is not proven in installed core or enabled mods"
        elif commodity is not None and snapshot.unmodeled_cargo_state:
            outcome, reason = "REFUSED", "Cargo partial quantities remain unmodeled"
        elif resource.locator.stored_type == "INT32":
            if request.value > 2**31 - 1:
                outcome, reason = "REFUSED", "Quantity exceeds signed 32-bit storage"
            else:
                replacement = str(request.value)
        elif resource.locator.stored_type == "FLOAT32":
            try:
                round_trip = struct.unpack('!f', struct.pack('!f', request.value))[0]
                if not round_trip.is_integer() or int(round_trip) != request.value:
                    raise OverflowError
                replacement = str(request.value) + ".0"
            except (OverflowError, struct.error):
                outcome, reason = "REFUSED", "Quantity cannot be represented exactly in float32 storage"
        else:
            outcome, reason = "REFUSED", "Stored numeric type is not qualified"
        if outcome == "ACCEPTED" and commodity is not None and resource is not None:
            if resource.max_stack is None:
                outcome, reason = "REFUSED", "Stored stack maximum is unavailable"
            elif Decimal(request.value) > Decimal(resource.max_stack):
                outcome, reason = "REFUSED", "Quantity exceeds the stored stack maximum"
        if outcome != "REFUSED" and resource is not None and Decimal(request.value) == Decimal(resource.value):
            replacement = resource.locator.original
        rows.append([request, resource, commodity, outcome, reason, replacement])
    # Capacity is judged per dimension after every request is known, so a combined edit is checked once.
    verdicts = _capacity_verdicts(snapshot, resources, rows)
    for request, resource, commodity, outcome, reason, replacement in rows:
        if request.target in verdicts:
            outcome, reason = verdicts[request.target]
        changes.append(PlannedChange(request.target, resource.value if resource else None, request.value,
                                     replacement if outcome != "REFUSED" else None,
                                     resource.locator if resource else None, outcome, reason,
                                     bool(outcome == "NOT_DETERMINABLE" and allow_unknown_capacity)))
    ready = all(change.outcome == "ACCEPTED" or change.capacity_opt_in for change in changes)
    return EditPlan("campaign-edit-plan-v1", source_dir, snapshot.source_hashes, catalog.evidence, tuple(changes), ready,
                    SAVE_WRITE_GATE.status, ("Plan only: no files written.",
                    "Writing needs every change ACCEPTED (within the saved capacity); the plan's capacity opt-in never enables an over-capacity write.",
                    "Saved capacity figures are not runtime-verified. Game acceptance is untested. Legality and recommendation engines do not consume this plan."))


_PERSONNEL = ("commodity:crew", "commodity:marines")


def _capacity_verdicts(snapshot: ResourceSnapshot, resources: dict, rows: list) -> dict[str, tuple[str, str]]:
    """Judge changed commodity quantities against the saved capacity figures, per dimension.

    Cargo: saved space used plus the change times each stack's saved space per unit, against saved cargo
    capacity. Fuel: the fuel stack against saved fuel capacity. Personnel: crew plus marines against saved
    personnel capacity. Anything over, or unprovable from the save, is NOT_DETERMINABLE (never written).
    """
    capacity = {name: Decimal(value) for name, value in snapshot.capacities}
    pending = {request.target: Decimal(request.value) for request, resource, commodity, outcome, _r, _x in rows
               if outcome == "ACCEPTED" and commodity is not None and Decimal(request.value) != Decimal(resource.value)}
    verdicts: dict[str, tuple[str, str]] = {}

    def settle(targets, ok: bool, detail: str) -> None:
        for target in targets:
            verdicts[target] = (("ACCEPTED", "Within the saved capacity: " + detail) if ok else
                                ("NOT_DETERMINABLE", "Over or unprovable against the saved capacity (overage effects UNKNOWN): " + detail))

    def unit_space(target: str) -> Decimal | None:
        value = resources[target].cargo_space_per_unit
        return None if value is None else Decimal(value)

    fuel = [t for t in pending if t == "commodity:fuel"]
    personnel = [t for t in pending if t in _PERSONNEL]
    cargo = [t for t in pending if t not in fuel and t not in personnel]
    for target in fuel + personnel:
        if unit_space(target) != 0:
            settle([target], False, "stack is not a zero-space commodity as modeled")
    fuel = [t for t in fuel if t not in verdicts]
    personnel = [t for t in personnel if t not in verdicts]
    if fuel:
        if "fuel" not in capacity:
            settle(fuel, False, "saved fuel capacity unavailable")
        else:
            settle(fuel, pending[fuel[0]] <= capacity["fuel"], f"fuel {pending[fuel[0]]} against capacity {capacity['fuel']}")
    if personnel:
        if "personnel" not in capacity or "commodity:crew" not in resources:
            settle(personnel, False, "saved personnel capacity or crew stack unavailable")
        else:
            total = sum((pending.get(t, Decimal(resources[t].value)) for t in _PERSONNEL if t in resources), Decimal(0))
            settle(personnel, total <= capacity["personnel"], f"crew + marines {total} against capacity {capacity['personnel']}")
    if cargo:
        spaces = {t: unit_space(t) for t in cargo}
        if "cargo" not in capacity or "space_used" not in capacity or any(s is None for s in spaces.values()):
            settle(cargo, False, "saved cargo capacity, space used or stack space per unit unavailable")
        else:
            stacks = Decimal(0)
            for stack in resources.values():
                if stack.target.startswith("commodity:") and stack.cargo_space_per_unit is not None:
                    stacks += Decimal(stack.value) * Decimal(stack.cargo_space_per_unit)
            if capacity["space_used"] < stacks:
                # Saved space used cannot be below what the saved stacks occupy; the figure is stale or unmodeled.
                settle(cargo, False, f"saved space used {capacity['space_used']} is below the {stacks} its stacks occupy")
            else:
                used = capacity["space_used"]
                for t in cargo:
                    unit = spaces[t]
                    if unit is not None:
                        used += (pending[t] - Decimal(resources[t].value)) * unit
                settle(cargo, 0 <= used <= capacity["cargo"], f"cargo space {used} against capacity {capacity['cargo']}")
    return verdicts
