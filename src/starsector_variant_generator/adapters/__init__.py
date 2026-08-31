"""Adapter layer for custom/undocumented per-source-mod mechanics.

Per Agent.md: "Custom mechanics must use an adapter layer rather than
inferred generic rules." Each submodule here corresponds to one source mod
(or "vanilla" for core game data) and exposes only explicitly curated,
citable facts -- never inference from names, tags, or apparent behavior.

validation/legality.py is the only consumer; it must treat a missing or
empty adapter table as "no rule available", never as a compatibility
guarantee.
"""
from __future__ import annotations

from starsector_variant_generator.adapters import vanilla
from starsector_variant_generator.adapters.vanilla import (
    FluxUnitCost,
    HullmodCombatEffect,
    HullmodDefenseEffect,
    HullmodFluxEffect,
    HullmodIncompatibility,
    HullmodLogisticsEffect,
    HullmodMobilityEffect,
    HullmodPercentReductionEffect,
)

# Starsector's own data uses "core" as the source_mod for base-game entities
# (see core/models.py SourceType.CORE); "vanilla" is the human name for that
# same data and is what Agent.md's proposed layout names the adapter for it.
_ADAPTERS_BY_SOURCE_MOD = {"core": vanilla}


def hullmod_incompatibility_pairs(source_mod: str) -> tuple[HullmodIncompatibility, ...]:
    """Return the citable incompatibility table for one source mod, or () if none exists."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return adapter.INCOMPATIBLE_HULLMOD_PAIRS if adapter is not None else ()


def flux_unit_cost(source_mod: str) -> FluxUnitCost | None:
    """Return the citable vent/capacitor OP-cost table for one source mod, or None if undocumented."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return getattr(adapter, "FLUX_UNIT_COST", None)


def logistics_hullmod_effects(source_mod: str) -> tuple[HullmodLogisticsEffect, ...]:
    """Return the citable logistics-effect table for one source mod, or () if none exists."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return getattr(adapter, "LOGISTICS_HULLMOD_EFFECTS", ()) if adapter is not None else ()


def efficiency_hullmod_effects(source_mod: str) -> tuple[HullmodPercentReductionEffect, ...]:
    """Return the citable percent-reduction-effect table for one source mod, or () if none exists."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return getattr(adapter, "EFFICIENCY_HULLMOD_EFFECTS", ()) if adapter is not None else ()


def defense_hullmod_effects(source_mod: str) -> tuple[HullmodDefenseEffect, ...]:
    """Return the citable DEFENSE-category armor/hull-HP effect table for one source mod, or () if none exists."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return getattr(adapter, "DEFENSE_HULLMOD_EFFECTS", ()) if adapter is not None else ()


def mobility_hullmod_effects(source_mod: str) -> tuple[HullmodMobilityEffect, ...]:
    """Return citable per-ship MOBILITY effects, or no facts when unknown."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return getattr(adapter, "MOBILITY_HULLMOD_EFFECTS", ()) if adapter is not None else ()


def flux_hullmod_effects(source_mod: str) -> tuple[HullmodFluxEffect, ...]:
    """Return the citable FLUX-category effect table for one source mod, or () if none exists."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return getattr(adapter, "FLUX_HULLMOD_EFFECTS", ()) if adapter is not None else ()


def combat_hullmod_effects(source_mod: str) -> tuple[HullmodCombatEffect, ...]:
    """Return the citable COMBAT-category (per-weapon `range`) effect table for one source mod, or () if none exists."""
    adapter = _ADAPTERS_BY_SOURCE_MOD.get(source_mod)
    return getattr(adapter, "COMBAT_HULLMOD_EFFECTS", ()) if adapter is not None else ()


def max_logistics_hullmods() -> int:
    """Return the engine-wide cap on logistics-tagged hullmods per ship.

    Unlike hullmod_incompatibility_pairs/flux_unit_cost, this is not looked
    up per source_mod: it is a single engine setting (settings.json's
    maxLogisticsHullmods), not something an individual hull's source mod
    can vary. See adapters/vanilla/__init__.py for the citation.
    """
    return vanilla.MAX_LOGISTICS_HULLMODS
