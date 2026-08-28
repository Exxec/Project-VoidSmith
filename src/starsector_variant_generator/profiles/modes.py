from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UserMode(StrEnum):
    BEGINNER = "beginner"
    GUIDED = "guided"
    ADVANCED = "advanced"


@dataclass(frozen=True)
class ModeDefaults:
    # No heuristic_set field: it used to be hardcoded "baseline_0.2" here
    # regardless of mode, but nothing in the real call chain ever actually
    # read it -- every real caller (api.py, cli/main.py) uses the session's
    # real AppConfig.heuristic_set (core/config.py::DEFAULT_HEURISTIC_SET,
    # "baseline_0.7") instead. A stale, never-consulted field is worse than
    # no field: it looks authoritative enough that a future caller could
    # reasonably assume it reflects the active session heuristic set, when
    # it never did. Removed rather than fixed-in-place for exactly that
    # reason -- there is no "current" value for it to hold.
    profile_id: str
    faction_mode: str
    control: str
    flux_mode: str


def resolve_mode(mode: UserMode, requested_profile: str | None = None) -> ModeDefaults:
    profile = requested_profile or "LINE_BRAWLER"
    if mode == UserMode.BEGINNER:
        return ModeDefaults(profile, "FACTION_PLUS", "AI", "SAFE")
    if mode == UserMode.GUIDED:
        # Guided mode's one concrete "meaningful choice" over Beginner today is an
        # explicit flux-sustainability target; see docs/ROADMAP.md Tier 4.
        return ModeDefaults(profile, "FACTION_PLUS", "EITHER", "BALANCED")
    return ModeDefaults(profile, "UNRESTRICTED", "EITHER", "AGGRESSIVE")
