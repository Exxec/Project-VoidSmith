"""Normalize the `version` field of a mod's mod_info.json to a display string.

Starsector mods declare the version either as a plain string (`"1.7.1"`), a bare number, or an object of parts
(`{"major": 1, "minor": 7, "patch": 1}`) whose parts may themselves be strings or numbers. Every reader in VoidSmith
uses this one function so the same mod always compares equal across scans and baselines.
"""

from __future__ import annotations

import json
from typing import Any

VERSION_PART_KEYS: tuple[str, ...] = ("major", "minor", "patch")
MISSING_VERSION_PART = "0"


def _normalize_part(value: Any) -> str | None:
    """Return a version part as text, or None when it is not a usable scalar."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, str)):
        text = str(value).strip()
        return text or None
    return None


def normalize_mod_version(value: Any) -> str | None:
    """Return `major.minor.patch` for an object version, or the scalar text for any other version.

    * `None` and absent versions stay `None`.
    * A string or number is returned as text (surrounding whitespace removed).
    * An object is joined as `major.minor.patch`; a missing or unusable part counts as `0`. An object with no usable part
      at all is treated as an absent version.
    * Other shapes (lists, booleans) are serialized as compact JSON so they remain distinguishable and stable.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        parts = [_normalize_part(value.get(key)) for key in VERSION_PART_KEYS]
        if all(part is None for part in parts):
            return None
        return ".".join(part if part is not None else MISSING_VERSION_PART for part in parts)
    if isinstance(value, (list, tuple, bool)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _normalize_part(value)
