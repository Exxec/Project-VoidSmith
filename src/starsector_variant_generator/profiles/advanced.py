from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from starsector_variant_generator.profiles.catalog import get_profile

_ALLOWED_FIELDS = frozenset({
    "profile", "faction_mode", "allowed_weapon_ids", "denied_weapon_ids",
    "locked_weapons_by_mount", "empty_mount_ids", "scoring_weight_overrides",
})
_FACTION_MODES = frozenset({"STRICT_FACTION", "FACTION_PLUS", "UNRESTRICTED"})

# The only heuristics an Advanced request may rebalance (Phase 14): the
# final weighted average's own component weights, from `core/heuristics.py`
# baseline_0.2+. Deliberately excludes every other heuristic (thresholds,
# targets, ...) -- Agent.md requires every consulted heuristic to live in
# the named, versioned registry, so a request may only reweight components
# the registry already defines and documents, never introduce a new one.
_SCORING_WEIGHT_KEYS = frozenset({
    "weight_range_coherence", "weight_op_efficiency", "weight_role_match",
    "weight_flux_sustainability", "weight_faction_doctrine", "weight_civilian_efficiency",
    "weight_survivability",
})


@dataclass(frozen=True)
class AdvancedGenerationRequest:
    profile_id: str
    faction_mode: str
    allowed_weapon_ids: frozenset[str] | None
    denied_weapon_ids: frozenset[str]
    locked_weapons_by_mount: dict[str, str]
    empty_mount_ids: frozenset[str]
    scoring_weight_overrides: dict[str, float] | None


def load_advanced_request(path: Path, default_profile: str = "LINE_BRAWLER") -> AdvancedGenerationRequest:
    """Load only implemented, user-authored candidate restrictions.

    This schema intentionally rejects fields for game mechanics not yet modeled,
    rather than accepting options the generator cannot honor.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Advanced request cannot be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Advanced request must be a JSON object.")
    unknown = set(raw) - _ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"Advanced request has unsupported fields: {', '.join(sorted(unknown))}")
    profile_id = raw.get("profile", default_profile)
    if not isinstance(profile_id, str):
        raise ValueError("Advanced request profile must be a string.")
    get_profile(profile_id)
    faction_mode = raw.get("faction_mode", "UNRESTRICTED")
    if faction_mode not in _FACTION_MODES:
        raise ValueError("Advanced request faction_mode must be STRICT_FACTION, FACTION_PLUS, or UNRESTRICTED.")
    allowed = _string_set(raw, "allowed_weapon_ids", nullable=True)
    denied = _string_set(raw, "denied_weapon_ids") or frozenset()
    empty = _string_set(raw, "empty_mount_ids") or frozenset()
    locks = raw.get("locked_weapons_by_mount", {})
    if not isinstance(locks, dict) or not all(isinstance(mount, str) and isinstance(weapon, str) for mount, weapon in locks.items()):
        raise ValueError("Advanced request locked_weapons_by_mount must map string mount IDs to string weapon IDs.")
    conflicting = set(locks) & set(empty)
    if conflicting:
        raise ValueError(f"Advanced request cannot lock and empty the same mount: {', '.join(sorted(conflicting))}")
    weight_overrides = _scoring_weight_overrides(raw)
    return AdvancedGenerationRequest(profile_id, faction_mode, allowed, denied, dict(locks), empty, weight_overrides)


def _scoring_weight_overrides(raw: dict[str, object]) -> dict[str, float] | None:
    if "scoring_weight_overrides" not in raw:
        return None
    overrides = raw["scoring_weight_overrides"]
    if not isinstance(overrides, dict) or not overrides:
        raise ValueError("Advanced request scoring_weight_overrides must be a non-empty JSON object.")
    unknown = set(overrides) - _SCORING_WEIGHT_KEYS
    if unknown:
        raise ValueError(f"Advanced request scoring_weight_overrides has unsupported keys: {', '.join(sorted(unknown))}. Only {', '.join(sorted(_SCORING_WEIGHT_KEYS))} may be overridden.")
    for key, value in overrides.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"Advanced request scoring_weight_overrides[{key!r}] must be a non-negative number.")
    return {key: float(value) for key, value in overrides.items()}


def _string_set(raw: dict[str, object], field: str, nullable: bool = False) -> frozenset[str] | None:
    if field not in raw:
        return None if nullable else frozenset()
    value = raw[field]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Advanced request {field} must be an array of strings.")
    return frozenset(value)
