from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class RoleProfile:
    """A deterministic quality intent, never a source of game-rule legality."""

    identifier: str
    display_name: str
    weapon_priority: str
    role_signal: str
    description: str
    # Soft secondary sort key for generation/hullmods.py::select_hullmods:
    # among otherwise-tied eligible hullmods, one whose parsed `uiTags` CSV
    # column contains this string sorts first. This is a values/priority
    # statement about a documented *category* the game itself assigns
    # (Defenses, Fighters, Weapons, ...), not a claim that any specific
    # hullmod is "good" -- the latter would be an undocumented game-balance
    # opinion this project has no basis to assert. None means no category
    # preference (cheapest-eligible-first only, as before).
    hullmod_priority_tag: str | None = None


_PROFILES = (
    RoleProfile("LINE_BRAWLER", "Line Brawler", "LOW_OP", "SHORT_RANGE", "Conservative close-range line fitting preference."),
    RoleProfile("LINE_ARTILLERY", "Line Artillery", "LONG_RANGE", "LONG_RANGE", "Long-range line fitting preference."),
    RoleProfile("FAST_STRIKE", "Fast Strike", "LOW_OP", "SHORT_RANGE", "Light, compact weapon-package preference."),
    RoleProfile("TANK", "Tank", "LOW_OP", "SHORT_RANGE", "Durability-focused close-range preference: weapon selection is the same conservative low-OP policy as Line Brawler, but hullmod selection prefers the hull's own \"Defenses\"-tagged options first.", hullmod_priority_tag="Defenses"),
    RoleProfile("PD_ESCORT", "Point Defense Escort", "PD_FIRST", "NEUTRAL", "Prefers weapons classify_weapon already tags \"PD\" (point defense) for each mount before falling back to the conservative low-OP policy; intended for a fleet-escort role rather than a primary line combatant."),
    RoleProfile("MISSILE_SUPPORT", "Missile Support", "LOW_OP", "NEUTRAL", "Weapon-only fitting; missile mounts fill through the same generic mount-type matching every other weapon type uses. Ammo/reload-aware missile curation is not implemented -- see docs/ROADMAP.md."),
    RoleProfile("CARRIER_SUPPORT", "Carrier Support", "LOW_OP", "NEUTRAL", "Weapon and fighter-wing fitting: fighter wings fill available bays up to the hull's documented capacity (generation/fighters.py); hullmod selection prefers the hull's own \"Fighters\"-tagged options first.", hullmod_priority_tag="Fighters"),
)

PROFILE_REGISTRY: Mapping[str, RoleProfile] = MappingProxyType({profile.identifier: profile for profile in _PROFILES})


def get_profile(identifier: str) -> RoleProfile:
    try:
        return PROFILE_REGISTRY[identifier]
    except KeyError as exc:
        raise ValueError(f"Unknown profile: {identifier}") from exc


def available_profiles() -> tuple[RoleProfile, ...]:
    return _PROFILES
