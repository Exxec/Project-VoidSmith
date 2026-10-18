"""Show the recorded consequences of an over-capacity edit; never enables a write (docs/AUTOMATION_PLAN.md V3.2).

Only two effects are evidenced, both measured by the sister project on build 0.98a-RC8 and cited by their row ids in its
`docs/RC8_BEHAVIOUR.md`:

- RC8-34: each unit over cargo, fuel or personnel capacity costs 0.1 supplies per day, capped at 50 per resource; the costs add.
- RC8-35: travel speed is 20 x the burn level, and the burn level becomes max(1, round(base burn x (2 - r))) for the worst used /
  capacity ratio r above 1. The base burn is not stored in a way this tool reads, so only r and the factor (2 - r) are shown.

Anything else about an overage stays UNKNOWN. A preview does not change an outcome: over-capacity changes remain NOT_DETERMINABLE
and are never written (AGENTS.md section 3).
"""
from __future__ import annotations

from decimal import Decimal

UNIT_COST = Decimal("0.1")
COST_CAP = Decimal("50")
COST_ROW = "RC8-34"
SPEED_ROW = "RC8-35"
SAVE_ROW = "RC8-36"
BUILD = "0.98a-RC8"
DIMENSIONS = ("cargo", "fuel", "personnel")


def _plain(value: Decimal) -> str:
    """Fixed-point text without trailing zeros (Decimal arithmetic leaves 300.00 and 20.000)."""
    return format(value.normalize(), "f")


def overage_preview(usage: dict[str, Decimal], capacity: dict[str, Decimal]) -> tuple[dict[str, object], ...]:
    """One entry per dimension whose planned usage exceeds the saved capacity; empty when none does."""
    entries: list[dict[str, object]] = []
    ratios: list[Decimal] = []
    for dimension in DIMENSIONS:
        used, limit = usage.get(dimension), capacity.get(dimension)
        if used is None or limit is None or limit <= 0 or used <= limit:
            continue
        excess = used - limit
        ratio = used / limit
        ratios.append(ratio)
        entries.append({
            "dimension": dimension, "used": _plain(used), "capacity": _plain(limit), "excess": _plain(excess),
            "supplies_per_day": _plain(min(COST_CAP, UNIT_COST * excess)), "capped": UNIT_COST * excess > COST_CAP,
            "ratio": f"{ratio:.4f}", "rows": [COST_ROW],
        })
    if not entries:
        return ()
    worst = max(ratios)
    entries.append({
        "dimension": "speed", "worst_ratio": f"{worst:.4f}", "burn_factor": f"{Decimal(2) - worst:.4f}",
        "formula": f"burn level = max(1, round(base burn x {Decimal(2) - worst:.4f})); base burn is not read from the save",
        "rows": [SPEED_ROW],
    })
    return tuple(entries)


def format_overage_lines(preview: tuple[dict[str, object], ...]) -> list[str]:
    if not preview:
        return []
    lines = [f"OVERAGE PREVIEW (recorded behaviour of build {BUILD}; the write stays refused):"]
    for entry in preview:
        if entry["dimension"] == "speed":
            lines.append(f"  speed [{SPEED_ROW}]: worst ratio {entry['worst_ratio']}; {entry['formula']}")
        else:
            cap = " (capped)" if entry["capped"] else ""
            lines.append(f"  {entry['dimension']} [{COST_ROW}]: {entry['used']} against {entry['capacity']}, "
                         f"{entry['excess']} over, +{entry['supplies_per_day']} supplies per day{cap}")
    lines.append(f"  Saved capacity figures are written at save time [{SAVE_ROW}]; whether a load recomputes an edited figure is unmeasured. All other overage effects are UNKNOWN.")
    return lines
