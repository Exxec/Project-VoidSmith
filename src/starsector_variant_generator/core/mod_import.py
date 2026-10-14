"""Resolve a user-supplied (e.g. drag-and-dropped) mod folder or `.zip`
archive into a scannable mod directory.

This never touches the Starsector installation or any existing mod: an
archive is extracted only into a program-controlled cache directory
(`AppConfig.output_dir`-scoped), never beside game/mod sources. Read-only
otherwise. A dropped item is added to the scan's source pool (see
`AppConfig.extra_mod_paths`, `core/scanner.py::Scanner.extra_mod_paths`) --
it is never treated as replacing the normal core + enabled-mods set.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from starsector_variant_generator.core.safeio import (
    UnsafePathError,
    is_link,
    safe_rmtree,
)
from starsector_variant_generator.parsers.common import json_file

MAX_ENTRY_BYTES = 200 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MIN_RATIO_CHECK_BYTES = 1024 * 1024  # tiny entries (a few KB of repeated text) may legitimately exceed the ratio


@dataclass(frozen=True)
class ModImportResult:
    mod_root: Path | None
    mod_id: str | None
    mod_name: str | None
    error: str | None


def resolve_dropped_mod(source: Path, extraction_root: Path) -> ModImportResult:
    """`source` is exactly what the user dropped: a mod folder, or a `.zip`
    archive of one. `extraction_root` is a cache directory an archive is
    extracted into -- one subfolder per archive, refreshed on every drop so
    re-dropping an updated archive never leaves stale extracted files behind.
    """
    if source.is_dir():
        return _locate_mod_info(source)
    if source.is_file() and source.suffix.lower() == ".zip":
        return _extract_and_locate(source, extraction_root)
    return ModImportResult(None, None, None, f"Unsupported drop: {source.name!r} is neither a folder nor a .zip archive.")


def _locate_mod_info(directory: Path) -> ModImportResult:
    direct = directory / "mod_info.json"
    if direct.is_file():
        return _read_mod_info(directory, direct)
    # A dropped archive commonly wraps the mod in one extra top-level folder
    # (matching the archive name); the same is true if a user drags in a
    # parent folder containing the mod folder directly. Only descend when
    # EXACTLY one subdirectory contains mod_info.json -- never guess among
    # several real candidates.
    candidates = [child for child in directory.iterdir() if child.is_dir() and (child / "mod_info.json").is_file()]
    if len(candidates) == 1:
        return _read_mod_info(candidates[0], candidates[0] / "mod_info.json")
    if len(candidates) > 1:
        return ModImportResult(None, None, None, f"Multiple mod_info.json files found under {directory.name!r}; drop a single mod's own folder or archive.")
    return ModImportResult(None, None, None, f"No mod_info.json found in {directory.name!r} (or immediately below it) -- this doesn't look like a Starsector mod.")


def _read_mod_info(mod_root: Path, info_path: Path) -> ModImportResult:
    try:
        raw = json_file(info_path)
    except (OSError, UnicodeError, ValueError) as exc:
        return ModImportResult(None, None, None, f"{info_path.name} could not be read: {exc}")
    mod_id = raw.get("id")
    mod_name = raw.get("name")
    return ModImportResult(mod_root, str(mod_id) if mod_id else None, str(mod_name) if mod_name else None, None)


def _extract_and_locate(archive: Path, extraction_root: Path) -> ModImportResult:
    target = extraction_root / archive.stem
    try:
        if is_link(extraction_root) or is_link(target):
            return ModImportResult(None, None, None, f"Refusing to extract through a link or junction: {target}")
        safe_rmtree(target, [extraction_root])
        with zipfile.ZipFile(archive) as zf:
            _safe_extract(zf, target)
    except zipfile.BadZipFile as exc:
        return ModImportResult(None, None, None, f"Could not read {archive.name!r} as a zip archive: {exc}")
    except (ValueError, UnsafePathError) as exc:
        return ModImportResult(None, None, None, str(exc))
    except OSError as exc:
        return ModImportResult(None, None, None, f"Could not extract {archive.name!r}: {exc}")
    return _locate_mod_info(target)


def check_archive_limits(zf: zipfile.ZipFile) -> None:
    """Refuse an archive whose declared sizes break the limits, before anything is extracted (docs/AUTOMATION_PLAN.md V0.3)."""
    total = 0
    for member in zf.infolist():
        if member.is_dir():
            continue
        if member.file_size > MAX_ENTRY_BYTES:
            raise ValueError(f"Archive entry {member.filename!r} is {member.file_size} bytes uncompressed; the limit is {MAX_ENTRY_BYTES}.")
        total += member.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"Archive expands past the {MAX_TOTAL_BYTES}-byte total limit.")
        if member.file_size > MIN_RATIO_CHECK_BYTES and member.file_size > MAX_COMPRESSION_RATIO * max(member.compress_size, 1):
            raise ValueError(f"Archive entry {member.filename!r} has a compression ratio over {MAX_COMPRESSION_RATIO}; refusing a possible zip bomb.")


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    """Reject oversized, bomb-like or escaping entries before writing anything, then extract with a hard byte cap per entry."""
    check_archive_limits(zf)
    target.mkdir(parents=True, exist_ok=True)
    resolved_target = target.resolve()
    members = zf.infolist()
    for member in members:
        member_path = (target / member.filename).resolve()
        if member_path != resolved_target and resolved_target not in member_path.parents:
            raise ValueError(f"Archive entry escapes the extraction directory: {member.filename!r}")
        if member.external_attr >> 16 & 0o170000 == 0o120000:
            raise ValueError(f"Archive entry is a symbolic link: {member.filename!r}")
    # The declared sizes in the zip directory can lie; count the bytes actually read.
    for member in members:
        destination = target / member.filename
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with zf.open(member) as source, destination.open("wb") as out:
            while chunk := source.read(1 << 20):
                written += len(chunk)
                if written > MAX_ENTRY_BYTES or written > MAX_COMPRESSION_RATIO * max(member.compress_size, 1) + MIN_RATIO_CHECK_BYTES:
                    raise ValueError(f"Archive entry {member.filename!r} expands past the limits while reading.")
                out.write(chunk)
