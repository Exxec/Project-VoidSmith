"""Read-only Qt resource resolution for locally scanned hull artwork."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPixmap

from starsector_variant_generator.core.models import Hull, Weapon


class HullSpriteCache:
    """Resolve a hull's declared local sprite without copying or exporting it."""

    def __init__(self) -> None:
        self._cache: dict[Path, QPixmap | None] = {}

    def sprite_for(self, hull: Hull) -> QPixmap | None:
        sprite_name = hull.raw.get("ship_data", {}).get("spriteName") if isinstance(hull.raw.get("ship_data"), dict) else None
        if not isinstance(sprite_name, str) or not sprite_name.strip():
            return None
        sprite_source = hull.raw.get("sprite_source_path")
        source_root = _source_root(Path(sprite_source) if isinstance(sprite_source, str) else hull.source_path)
        candidate = _safe_sprite_path(source_root, sprite_name)
        if candidate is None:
            return None
        if candidate not in self._cache:
            pixmap = QPixmap(str(candidate)) if candidate.is_file() else QPixmap()
            self._cache[candidate] = pixmap if not pixmap.isNull() else None
        return self._cache[candidate]


class WeaponSpriteCache:
    """Resolve optional, declared weapon art from a weapon's own source."""

    def __init__(self) -> None:
        self._cache: dict[Path, QPixmap | None] = {}

    def sprite_for(self, weapon: Weapon, mount_kind: str | None) -> QPixmap | None:
        spec = weapon.raw.get("weapon_spec")
        if not isinstance(spec, dict):
            return None
        key = "hardpointSprite" if str(mount_kind).upper() == "HARDPOINT" else "turretSprite"
        sprite_name = spec.get(key) or spec.get("turretSprite") or spec.get("hardpointSprite")
        if not isinstance(sprite_name, str) or not sprite_name.strip():
            return None
        candidate = _safe_sprite_path(_source_root(weapon.source_path), sprite_name)
        if candidate is None:
            return None
        if candidate not in self._cache:
            pixmap = QPixmap(str(candidate)) if candidate.is_file() else QPixmap()
            self._cache[candidate] = pixmap if not pixmap.isNull() else None
        return self._cache[candidate]


def _source_root(source_path: Path) -> Path:
    """Return a scanned entity's ``<core-or-mod>/`` source root defensively."""
    # CSV entities live below <root>/data/<category>/; skins live one level
    # deeper. Find the actual data directory rather than assuming a fixed
    # parent count, then fall back safely for malformed/fixture paths.
    for ancestor in source_path.parents:
        if ancestor.name.casefold() == "data":
            return ancestor.parent
    return source_path.parents[2] if len(source_path.parents) >= 3 else source_path.parent


def _safe_sprite_path(source_root: Path, sprite_name: str) -> Path | None:
    """Accept only a sprite path physically beneath the scanned source root."""
    try:
        # Starsector declarations use either separator. Normalize to the
        # host path syntax so a valid forward-slash asset path works on Linux
        # and a backslash traversal attempt cannot become one literal filename.
        relative = Path(sprite_name.replace("\\", "/"))
        candidates: tuple[Path, ...]
        if relative.suffix:
            candidates = (relative,)
        else:
            candidates = (relative.with_suffix(".png"), relative.with_suffix(".jpg"))
        root = source_root.resolve()
        for item in candidates:
            candidate = (root / item).resolve()
            if candidate.is_relative_to(root):
                return candidate
    except (OSError, ValueError):
        return None
    return None
