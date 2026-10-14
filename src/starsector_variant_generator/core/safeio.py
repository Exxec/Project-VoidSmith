"""Atomic writes and guarded deletes (docs/AUTOMATION_PLAN.md V0.2; AGENTS.md section 12).

Files are written to a temp file in the same folder and swapped in with `os.replace`, so an interrupted run leaves the old file or the
new one, never half of either. Deletes go through `safe_rmtree` / `safe_unlink`, which refuse paths outside the roots the caller
names, refuse the roots themselves, and never follow a symlink or Windows junction out of them (deleting through a junction removes
the target's files). Semantics follow the sister project's `safeio` module.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT


class UnsafePathError(ValueError):
    """A delete was refused: outside the allowed roots, a root itself, or reaching outside through a link."""


def atomic_write_bytes(path: Path | str, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8", newline: str | None = None) -> Path:
    """Write `text` atomically. `newline=""` writes it as given; None keeps `Path.write_text`'s platform translation."""
    data = text.encode(encoding) if newline == "" else text.replace("\r\n", "\n").replace("\n", os.linesep).encode(encoding)
    return atomic_write_bytes(path, data)


def atomic_write_json(path: Path | str, data: object, *, indent: int | None = 2, **dumps: object) -> Path:
    """Serialise with `json.dumps` and write atomically (no trailing newline added, matching the earlier `write_text` output)."""
    return atomic_write_text(path, json.dumps(data, indent=indent, **dumps))  # type: ignore[arg-type]


def is_link(path: Path | str) -> bool:
    """True for a symlink or a Windows junction/reparse point (Path.is_junction only exists from Python 3.12)."""
    path = Path(path)
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None:
        return bool(is_junction())
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _REPARSE_POINT)


def _resolved(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _lexically_inside(raw: Path, allowed_roots: Iterable[Path | str]) -> None:
    lexical = Path(os.path.abspath(raw))
    roots = [Path(os.path.abspath(Path(r).expanduser())) for r in allowed_roots]
    if not any(_inside(lexical, root) and lexical != root for root in roots):
        raise UnsafePathError(f"{lexical} is outside the allowed roots")


def check_deletable(path: Path | str, allowed_roots: Iterable[Path | str]) -> Path:
    """The resolved path if it may be deleted: strictly inside an allowed root, and where it leads is inside one too."""
    roots = [_resolved(r) for r in allowed_roots]
    if not roots:
        raise UnsafePathError("no allowed roots were given")
    raw = Path(path).expanduser()
    target = _resolved(raw)
    if any(target == root for root in roots):
        raise UnsafePathError(f"{target} is an allowed root itself, not something inside one")
    lexical = Path(os.path.abspath(raw))
    if not any(_inside(lexical, root) or _inside(lexical, Path(os.path.abspath(root))) for root in roots):
        raise UnsafePathError(f"{lexical} is outside the allowed roots: {', '.join(str(r) for r in roots)}")
    if not any(_inside(target, root) for root in roots):
        raise UnsafePathError(f"{lexical} leads to {target}, which is outside the allowed roots (a link out of them)")
    return target


def _remove_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
    else:
        os.rmdir(link)  # a junction: removes the link only, never its target


def safe_unlink(path: Path | str, allowed_roots: Iterable[Path | str], missing_ok: bool = True) -> bool:
    """Delete one file (or remove one link). True when something was removed."""
    raw = Path(path)
    if is_link(raw):
        _lexically_inside(raw, allowed_roots)
        _remove_link(raw)
        return True
    if not raw.exists():
        if missing_ok:
            return False
        raise FileNotFoundError(str(raw))
    target = check_deletable(raw, allowed_roots)
    if target.is_dir():
        raise UnsafePathError(f"{target} is a folder; use safe_rmtree")
    target.unlink()
    return True


def safe_rmtree(path: Path | str, allowed_roots: Iterable[Path | str], missing_ok: bool = True) -> bool:
    """Delete a folder tree. A link is removed as a link and its target is never entered. True when removed."""
    raw = Path(path)
    if is_link(raw):
        _lexically_inside(raw, allowed_roots)
        _remove_link(raw)
        return True
    if not raw.exists():
        if missing_ok:
            return False
        raise FileNotFoundError(str(raw))
    target = check_deletable(raw, allowed_roots)
    if not target.is_dir():
        raise UnsafePathError(f"{target} is a file; use safe_unlink")
    for current, dirs, _files in os.walk(target):
        for name in list(dirs):
            child = Path(current) / name
            if is_link(child):
                _remove_link(child)
                dirs.remove(name)
    shutil.rmtree(target)
    return True
