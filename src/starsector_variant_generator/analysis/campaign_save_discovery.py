"""Strictly read-only boundary for explicitly user-selected campaign folders.

Starsector campaign-save layout and semantics are not normalized by this
project. This module consequently does *not* look for a presumed install save
location, decide which entry is a campaign save, or open entry contents. It
only inventories direct filesystem entries in a directory the user supplied,
so a later documented parser has an explicit, safe acquisition boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CampaignDirectoryEntry:
    """Filesystem metadata only; this is not a parsed or validated save."""
    name: str
    kind: str  # FILE | DIRECTORY
    bytes: int | None


@dataclass(frozen=True)
class CampaignSaveDiscovery:
    """`CAMPAIGN_SAVE_UNINSPECTED` discovery result with no save semantics."""
    directory: Path
    status: str  # DIRECTORY_EMPTY | DIRECTORY_ENTRIES_FOUND
    entries: tuple[CampaignDirectoryEntry, ...]
    notes: tuple[str, ...]


def discover_campaign_directory(directory: Path) -> CampaignSaveDiscovery:
    """Inventory a user-selected directory without reading any entry content.

    Symlinks are deliberately excluded. This avoids escaping the user's
    explicit directory boundary and avoids treating a link target as campaign
    evidence. Recursive scanning is likewise intentionally absent.
    """
    try:
        resolved = directory.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Campaign discovery requires an existing directory selected by the user") from exc
    if not resolved.is_dir():
        raise ValueError("Campaign discovery requires an existing directory selected by the user")
    entries: list[CampaignDirectoryEntry] = []
    for path in sorted(resolved.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
        if path.is_symlink():
            continue
        if path.is_file():
            entries.append(CampaignDirectoryEntry(path.name, "FILE", path.stat().st_size))
        elif path.is_dir():
            entries.append(CampaignDirectoryEntry(path.name, "DIRECTORY", None))
    return CampaignSaveDiscovery(
        directory=resolved,
        status="DIRECTORY_ENTRIES_FOUND" if entries else "DIRECTORY_EMPTY",
        entries=tuple(entries),
        notes=(
            "CAMPAIGN_SAVE_UNINSPECTED: entries are listed only because the user selected this directory.",
            "No save file format, campaign inventory, officer state, market state, deployment points, or runtime data was read or inferred.",
        ),
    )
