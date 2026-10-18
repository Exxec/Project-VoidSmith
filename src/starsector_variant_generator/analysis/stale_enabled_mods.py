"""Enabled mod ids with no installed folder, plus the closest installed folder (docs/AUTOMATION_PLAN.md V1.4, bug SVG-004).

Information only. `enabled_mods.json` is never edited and nothing here decides that an installed mod IS the missing one: the
nearest candidate is a hint with its similarity score and the field that matched, from a deterministic string comparison of the
normalised id against each installed (not already enabled) mod's id, folder name and display name.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from starsector_variant_generator.core.models import ModInfo, ScanResult, SourceType

MIN_SIMILARITY = 0.6
_PREFIX = "Enabled mod not discovered: "
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class StaleEnabledMod:
    enabled_id: str
    closest_mod_id: str | None
    closest_folder: str | None
    closest_name: str | None
    matched_field: str | None  # mod_id | folder | name
    similarity: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalise(text: str) -> str:
    return _NON_ALNUM.sub("", text.lower())


def _best_match(enabled_id: str, candidates: Sequence[ModInfo]) -> tuple[ModInfo, str, float] | None:
    wanted = _normalise(enabled_id)
    best: tuple[ModInfo, str, float] | None = None
    for mod in candidates:
        fields = (("mod_id", mod.mod_id), ("folder", mod.path.name), ("name", mod.mod_name))
        for field_name, value in fields:
            score = SequenceMatcher(None, wanted, _normalise(value)).ratio() if wanted and _normalise(value) else 0.0
            # ties keep the earliest (candidates arrive sorted), so the result is deterministic
            if best is None or score > best[2]:
                best = (mod, field_name, score)
    return best if best is not None and best[2] >= MIN_SIMILARITY else None


def find_stale_enabled_mods(scan: ScanResult, installed: Sequence[ModInfo] = ()) -> list[StaleEnabledMod]:
    """Each 'Enabled mod not discovered' scan note with its closest installed, not-enabled mod when one is close enough.

    `installed` is every mod folder found on disk (the scan's own `mods` lists only the scanned ones); without it the scan's mods
    are used.
    """
    stale_ids = [message[len(_PREFIX):] for message in scan.skipped_entities if message.startswith(_PREFIX)]
    pool = installed or scan.mods
    candidates = sorted(
        (mod for mod in pool if mod.source_type is SourceType.MOD and mod.enabled is not True),
        key=lambda mod: (mod.mod_id.lower(), str(mod.path)),
    )
    results: list[StaleEnabledMod] = []
    for enabled_id in sorted(set(stale_ids)):
        match = _best_match(enabled_id, candidates)
        if match is None:
            results.append(StaleEnabledMod(enabled_id, None, None, None, None, None))
        else:
            mod, field_name, score = match
            results.append(StaleEnabledMod(enabled_id, mod.mod_id, mod.path.name, mod.mod_name, field_name, round(score, 3)))
    return results


def format_stale_line(entry: StaleEnabledMod | dict[str, object]) -> str:
    data = entry.to_dict() if isinstance(entry, StaleEnabledMod) else entry
    line = f"Enabled but not installed: {data['enabled_id']}"
    if data.get("closest_mod_id"):
        line += f" (closest installed: {data['closest_mod_id']} in folder {data['closest_folder']}, {data['matched_field']} match {data['similarity']})"
    return line + " [information only; enabled_mods.json is never edited]"
