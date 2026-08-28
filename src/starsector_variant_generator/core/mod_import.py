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

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from starsector_variant_generator.parsers.common import json_file


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
    if target.exists():
        shutil.rmtree(target)
    try:
        with zipfile.ZipFile(archive) as zf:
            _safe_extract(zf, target)
    except zipfile.BadZipFile as exc:
        return ModImportResult(None, None, None, f"Could not read {archive.name!r} as a zip archive: {exc}")
    except ValueError as exc:
        return ModImportResult(None, None, None, str(exc))
    except OSError as exc:
        return ModImportResult(None, None, None, f"Could not extract {archive.name!r}: {exc}")
    return _locate_mod_info(target)


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    """Reject any entry that would extract outside `target` (zip-slip) before writing anything."""
    target.mkdir(parents=True, exist_ok=True)
    resolved_target = target.resolve()
    for member in zf.infolist():
        member_path = (target / member.filename).resolve()
        if member_path != resolved_target and resolved_target not in member_path.parents:
            raise ValueError(f"Archive entry escapes the extraction directory: {member.filename!r}")
    zf.extractall(target)
