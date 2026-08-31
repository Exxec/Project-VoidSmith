"""Ship Fitting Canvas: the QGraphicsView-based technical fitting diagram.

Extracted from `gui/main_window.py` (Phase 35, GUI modularization) with no
behavior change -- `TechnicalCanvas` and its module-level constants/helpers
moved here verbatim; `main_window.py` re-imports the names it still needs
(`TechnicalCanvas`, `MOUNT_TYPE_COLORS`, `_detect_mirror_mount_pairs`) so
external references (including `tests/test_gui_canvas.py`, which imports
`TechnicalCanvas` and `_detect_mirror_mount_pairs` directly from
`starsector_variant_generator.gui.main_window`) keep working unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from starsector_variant_generator.core.models import Hull, Weapon
from starsector_variant_generator.gui.resources import (
    HullSpriteCache,
    WeaponSpriteCache,
)

# Real Starsector mount `type` values (core/mount_compatibility.py); colors
# chosen only for visual distinction, not a data claim. HYBRID/COMPOSITE/
# SYNERGY share a color family (all multi-type-accepting mounts) so the
# genuinely single-type BALLISTIC/ENERGY/MISSILE colors stay unambiguous.
MOUNT_TYPE_COLORS: dict[str, str] = {
    "BALLISTIC": "#e8743b", "ENERGY": "#24aaf2", "MISSILE": "#d69b27",
    "HYBRID": "#b967ff", "COMPOSITE": "#9d5ce0", "SYNERGY": "#7f4fd1", "UNIVERSAL": "#d7e4ee",
}
_MOUNT_TYPE_COLOR_FALLBACK = "#7d93a3"
# Box half-extent in scene units by declared weapon size -- a UI legibility
# choice, not a claim about real in-game hardpoint dimensions.
_MOUNT_BOX_HALF_EXTENT: dict[str, float] = {"SMALL": 9.0, "MEDIUM": 14.0, "LARGE": 20.0}
_MOUNT_BOX_HALF_EXTENT_FALLBACK = 11.0
_WEAPON_PREVIEW_MAX_EXTENT: dict[str, int] = {"SMALL": 28, "MEDIUM": 42, "LARGE": 60}
_NON_WEAPON_SLOT_TYPES = frozenset({"LAUNCH_BAY", "DECORATIVE"})


class TechnicalCanvas(QGraphicsView):
    """Weapon mounts render as clickable, type-colored boxes directly on the
    hull sprite -- clicking one opens the same backend-filtered weapon
    picker the (now-removed) side list used to, via `slot_clicked`."""

    slot_clicked = Signal(str)

    def __init__(self) -> None:
        self.scene_ = QGraphicsScene()
        super().__init__(self.scene_)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        # Panning remains available with drag; permanent scrollbars distract
        # from the technical view and were especially noisy for side stacks.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sprites = HullSpriteCache()
        self._weapon_sprites = WeaponSpriteCache()
        # scene-space (x1, y1, x2, y2) hit boxes for slots that accept a
        # click -- built-in mounts are shown but omitted here, so clicking
        # one falls through to the normal view-drag/pan behavior instead.
        self._slot_hit_boxes: dict[str, tuple[float, float, float, float]] = {}
        self.show_empty()

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            for slot_id, (x1, y1, x2, y2) in self._slot_hit_boxes.items():
                if x1 <= point.x() <= x2 and y1 <= point.y() <= y2:
                    self.slot_clicked.emit(slot_id)
                    return
        super().mousePressEvent(event)

    def reset_view(self) -> None:
        self.resetTransform()
        bounds = self.scene_.itemsBoundingRect()
        if not bounds.isNull():
            self.fitInView(bounds.adjusted(-35, -35, 35, 35), Qt.KeepAspectRatio)

    def zoom_in(self) -> None:
        self.scale(1.15, 1.15)

    def zoom_out(self) -> None:
        self.scale(1 / 1.15, 1 / 1.15)

    def show_empty(self) -> None:
        self.scene_.clear()
        text = self.scene_.addText("Select a scanned hull to inspect normalized fitting data")
        text.setDefaultTextColor(QColor("#91a8b7"))

    def show_hull(self, hull: Hull, weapons: dict[str, str] | None = None, weapon_by_id: Mapping[str, Weapon] | None = None) -> None:
        self.scene_.clear()
        self.resetTransform()
        self._slot_hit_boxes = {}
        sprite = self._sprites.sprite_for(hull)
        ship_data = hull.raw.get("ship_data", {}) if isinstance(hull.raw.get("ship_data"), dict) else {}
        declared_width, declared_height = ship_data.get("width"), ship_data.get("height")
        has_declared_dimensions = isinstance(declared_width, (int, float)) and isinstance(declared_height, (int, float)) and declared_width > 0 and declared_height > 0
        width, height = _number(declared_width, 320.0), _number(declared_height, 180.0)
        center = ship_data.get("center", [0.0, 0.0])
        center_x = _number(center[0], 0.0) if isinstance(center, list) and len(center) >= 2 else 0.0
        center_y = _number(center[1], 0.0) if isinstance(center, list) and len(center) >= 2 else 0.0
        # Per the Starsector modding wiki (File overview: ship /
        # Modding:Weapon Slots): "the defined center of the ship is defined
        # as a set of Cartesian coordinates relative to the most bottom-left
        # pixel of the sprite. The defined center point is the relative
        # reference point for ... weaponSlots" -- i.e. weapon locations are
        # ALREADY given relative to `center` (not needing a further
        # subtraction of it, which the previous code did, silently shifting
        # every mount off the ship), and `center` itself is measured
        # bottom-left-origin/Y-up in sprite pixels, not the naive
        # top-left/Y-down of a raw QPixmap. Confirmed against a real
        # screenshot of a live 25-mount capital hull whose mount boxes
        # rendered nowhere near the ship under the old (wrong) formula.
        if sprite is not None:
            image = self.scene_.addPixmap(sprite)
            # Weapon locations and center live in the `.ship` geometry's
            # declared width/height coordinate space. Mods may supply art at
            # a different texture resolution; drawing the raw QPixmap made
            # every mount drift proportionally (often looking like a rotated
            # hull had horizontal mounts). Map the art into that same logical
            # space before placing its origin. Do not scale when dimensions
            # are absent: the raw sprite is then the only honest geometry.
            scale_x, scale_y = _sprite_geometry_scale(sprite.width(), sprite.height(), width, height, has_declared_dimensions)
            image.setTransform(QTransform.fromScale(scale_x, scale_y))
            image.setOffset(-center_x / scale_x, (center_y - height) / scale_y)
            top_edge = center_y - height if has_declared_dimensions else center_y - sprite.height()
        else:
            outline = self.scene_.addRect(-center_x, center_y - height, width, height, QPen(QColor("#28536b"), 2))
            outline.setToolTip("Local hull sprite unavailable; geometry outline only.")
            top_edge = center_y - height
        # Positioned above the sprite's real top edge (not the scene origin,
        # which sits at the ship's declared center and would otherwise be
        # drawn over by the sprite itself, added after this text -- a real,
        # previously-invisible rendering bug found by comparing a live
        # screenshot against this code).
        visible_mounts = _displayable_weapon_mounts(hull)
        bay_count = len(hull.launch_bay_slots)
        title_detail = f"{len(visible_mounts)} selectable weapon mounts"
        if bay_count:
            title_detail += f" • {bay_count} launch bay{'s' if bay_count != 1 else ''}"
        title = self.scene_.addText(f"{hull.name or hull.id}\n{title_detail}")
        title.setDefaultTextColor(QColor("#d7e4ee")); title.setPos(-title.boundingRect().width() / 2, top_edge - 46)
        plotted = 0
        for slot in visible_mounts:
            loc = slot.get("locations")
            if not isinstance(loc, list) or len(loc) < 2 or not all(isinstance(x, (float, int)) for x in loc[:2]):
                continue
            # Starsector's ship geometry takes +X as forward and +Y as its
            # lateral axis. The fitting canvas presents art upright, so
            # forward maps to screen-up and lateral +Y maps to screen-right.
            # The previous direct X/Y overlay quarter-turned every hull.
            x, y = _mount_scene_position(loc)
            mount_type = str(slot.get("type", "")).upper()
            mount_size = str(slot.get("size", "")).upper()
            color = QColor(MOUNT_TYPE_COLORS.get(mount_type, _MOUNT_TYPE_COLOR_FALLBACK))
            half = _MOUNT_BOX_HALF_EXTENT.get(mount_size, _MOUNT_BOX_HALF_EXTENT_FALLBACK)
            slot_id = str(slot.get("id", "slot"))
            selected_weapon = (weapons or {}).get(slot_id)
            built_in = slot_id in hull.built_in_weapons
            if built_in:
                box = self.scene_.addRect(x - half, y - half, half * 2, half * 2, QPen(QColor("#465866"), 1, Qt.DashLine))
                box.setToolTip(f"{slot_id}: built-in mount, filled automatically -- not selectable ({mount_type or 'UNKNOWN'}).")
            else:
                fill = QColor(color); fill.setAlpha(80 if selected_weapon else 0)
                box = self.scene_.addRect(x - half, y - half, half * 2, half * 2, QPen(color, 2), fill)
                action = f"click to change (currently {selected_weapon})" if selected_weapon else "click to assign a weapon"
                box.setToolTip(f"{slot_id}: {mount_type or 'UNKNOWN'} {mount_size or 'UNKNOWN'} mount -- {action}")
                self._slot_hit_boxes[slot_id] = (x - half, y - half, x + half, y + half)
            weapon = weapon_by_id.get(selected_weapon) if selected_weapon and weapon_by_id is not None else None
            if weapon is not None:
                self._add_weapon_preview(weapon, str(slot.get("mount", "")), mount_size, _number(slot.get("angle"), 0.0), x, y)
            plotted += 1
        if bay_count:
            self._add_launch_bay_stack(hull, width - center_x + 28, top_edge)
        # No external leader-line callouts (removed): on a hull with many
        # mounts (confirmed on a real 25-mount capital hull) they sprawled
        # far enough past the ship that fitInView had to zoom out to fit
        # them all, shrinking the actual ship -- and the clickable boxes on
        # it -- to a barely-visible speck. The boxes' color/size/tooltip
        # already carry the same information the callouts duplicated.
        complex_note = "  •  Composite module behavior is not modeled." if "SHIP_WITH_MODULES" in {hint.upper() for hint in hull.hull_hints} else ""
        note = self.scene_.addText(("Click a highlighted mount to assign a weapon." if self._slot_hit_boxes else ("No parsed slot geometry available." if not plotted else "All parsed mounts are built-in.")) + complex_note)
        note.setDefaultTextColor(QColor("#91a8b7")); note.setPos(-note.boundingRect().width() / 2, -top_edge + 14)
        self.reset_view()

    def _add_weapon_preview(self, weapon: Weapon, mount_kind: str, mount_size: str, angle: float, x: float, y: float) -> None:
        """Show declared static weapon art without claiming combat accuracy."""
        sprite = self._weapon_sprites.sprite_for(weapon, mount_kind)
        if sprite is None:
            return
        preview = _scaled_weapon_preview(sprite, _WEAPON_PREVIEW_MAX_EXTENT.get(mount_size, 32))
        item = self.scene_.addPixmap(preview)
        item.setOffset(-preview.width() / 2, -preview.height() / 2)
        item.setPos(x, y)
        # Angle zero points forward (+X) in game geometry; forward is up in
        # this upright preview. This is rendering-only and never affects fit.
        item.setRotation(_mount_scene_rotation(angle))
        item.setToolTip(f"{weapon.name or weapon.id}: static sprite preview")

    def _add_launch_bay_stack(self, hull: Hull, x: float, y: float) -> None:
        """Render carrier capacity beside the hull, never as a weapon slot."""
        bay_ids = tuple(slot_id for slot_id in hull.launch_bay_slots if slot_id)
        display_count = hull.fighter_bays if hull.fighter_bays is not None else len(bay_ids)
        row_height, panel_width = 22, 126
        panel_height = 28 + row_height * max(1, len(bay_ids))
        panel = self.scene_.addRect(x, y, panel_width, panel_height, QPen(QColor("#567587"), 1), QBrush(QColor("#0b1b26")))
        panel.setToolTip("Carrier launch-bay structure. These are not selectable weapon mounts.")
        heading = self.scene_.addText(f"Fighter bays ({display_count})")
        heading.setDefaultTextColor(QColor("#d7e4ee")); heading.setPos(x + 8, y + 4)
        for index, bay_id in enumerate(bay_ids):
            marker_y = y + 29 + index * row_height
            marker = self.scene_.addRect(x + 8, marker_y, 13, 13, QPen(QColor("#d69b27"), 1), QBrush(QColor("#45361d")))
            marker.setToolTip(f"{bay_id}: declared launch-bay geometry, not a weapon mount.")
            label = self.scene_.addText(str(bay_id))
            label.setDefaultTextColor(QColor("#a9bfca")); label.setPos(x + 28, marker_y - 4)

    def drawBackground(self, painter: QPainter, rect: Any) -> None:  # type: ignore[override]
        painter.fillRect(rect, QColor("#061019")); painter.setPen(QPen(QColor("#10293a"), 1))
        for x in range(int(rect.left()) - int(rect.left()) % 32, int(rect.right()), 32):
            painter.drawLine(x, rect.top(), x, rect.bottom())
        for y in range(int(rect.top()) - int(rect.top()) % 32, int(rect.bottom()), 32):
            painter.drawLine(rect.left(), y, rect.right(), y)


def _number(value: object, fallback: float) -> float:
    return float(value) if isinstance(value, (int, float)) else fallback


def _mount_scene_position(locations: list[object]) -> tuple[float, float]:
    """Map Starsector forward/lateral coordinates onto the upright canvas.

    Every real caller already validated `locations[:2]` as `(float, int)`
    (see the `isinstance` guard just before this is called), so `_number`'s
    fallback is never actually exercised -- it is used here only for the
    same disciplined "never trust an untyped `object` blindly" narrowing
    `_number` already provides everywhere else in this module.
    """
    return _number(locations[1], 0.0), -_number(locations[0], 0.0)


def _mount_scene_rotation(angle: float) -> float:
    """Map a parsed slot angle through the same axis transform as its point.

    QGraphics rotations operate in the canvas' Y-down coordinate system.
    The source vector (cos(angle), sin(angle)) is mapped by
    :func:`_mount_scene_position` to (sin(angle), -cos(angle)), which is a
    clockwise ``angle - 90`` rotation for art whose declared neutral forward
    axis is +X.  Keeping this helper beside the position mapping prevents a
    later axis change from leaving weapon previews quarter-turned.
    """
    return angle - 90.0


def _displayable_weapon_mounts(hull: Hull) -> tuple[dict[str, Any], ...]:
    """Return real weapon slots, excluding carrier/decorative geometry.

    `.ship` weaponSlots also declares multi-point launch-bay and decorative
    anchors. They are required source evidence but are neither player-fit
    slots nor reliable weapon-art locations, so the canvas must not draw them
    as selectable weapons.
    """
    return tuple(slot for slot in hull.weapon_mounts if _is_displayable_weapon_mount(slot))


def _is_displayable_weapon_mount(slot: Mapping[str, Any]) -> bool:
    return (
        str(slot.get("type", "")).upper() not in _NON_WEAPON_SLOT_TYPES
        and str(slot.get("mount", "")).upper() != "HIDDEN"
    )


def _scaled_weapon_preview(sprite: QPixmap, maximum_extent: int) -> QPixmap:
    """Bound optional art to its slot's visual footprint, preserving ratio."""
    return sprite.scaled(maximum_extent, maximum_extent, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _sprite_geometry_scale(
    sprite_width: int, sprite_height: int, declared_width: float, declared_height: float, has_declared_dimensions: bool,
) -> tuple[float, float]:
    """Scale art into `.ship` geometry units, guarding incomplete metadata."""
    if not has_declared_dimensions or sprite_width <= 0 or sprite_height <= 0:
        return 1.0, 1.0
    return declared_width / sprite_width, declared_height / sprite_height


_MIRROR_MATCH_TOLERANCE = 0.75


def _detect_mirror_mount_pairs(hull: Hull) -> dict[str, str]:
    """Detect left/right mirror-symmetric weapon-mount pairs from a hull's
    real parsed `.ship` geometry (`weaponSlots`' `locations`/`angle`/`arc`/
    `size`/`type`/`mount` fields -- the same raw data the canvas already
    reads to place slot markers).

    Starsector hulls are built bow/stern-asymmetric (a distinct nose and
    engine block, never a fore-aft mirror image), so only a left/right axis
    is ever geometrically meaningful here -- there is no equivalent
    "horizontal" mirror to detect. A mount pairs with another only when its
    position, angle, arc, size, mount kind, and weapon type all match the
    exact mirror image of another mount's (x unchanged, y negated, angle
    negated mod 360), within a small tolerance for non-integer coordinates.
    Centerline mounts (y == 0) and mounts with no matching counterpart are
    left unpaired -- Mirror is then a no-op for that slot, not a guess.
    Verified against real hulls: Hammerhead's 8 mounts pair perfectly (4
    pairs); Odyssey's 19 mounts produce exactly 1 real pair, correctly
    leaving the rest -- deliberately scattered, unique turret placements --
    unpaired rather than forcing a false match.
    """
    entries: list[tuple[str, float, float, float, Any, Any, Any, Any]] = []
    for slot in _displayable_weapon_mounts(hull):
        slot_id = slot.get("id")
        loc = slot.get("locations")
        if not slot_id or not isinstance(loc, list) or len(loc) < 2:
            continue
        try:
            x, y = float(loc[0]), float(loc[1])
            angle = float(slot.get("angle", 0.0))
        except (TypeError, ValueError):
            continue
        entries.append((str(slot_id), x, y, angle, slot.get("arc"), slot.get("size"), slot.get("type"), slot.get("mount")))

    pairs: dict[str, str] = {}
    for i, (id_a, x_a, y_a, angle_a, arc_a, size_a, type_a, mount_a) in enumerate(entries):
        if id_a in pairs or abs(y_a) < _MIRROR_MATCH_TOLERANCE:
            continue
        for id_b, x_b, y_b, angle_b, arc_b, size_b, type_b, mount_b in entries[i + 1:]:
            if id_b in pairs:
                continue
            if abs(x_a - x_b) > _MIRROR_MATCH_TOLERANCE or abs(y_a + y_b) > _MIRROR_MATCH_TOLERANCE:
                continue
            if arc_a != arc_b or size_a != size_b or type_a != type_b or mount_a != mount_b:
                continue
            angle_sum = (angle_a + angle_b) % 360.0
            if angle_sum > _MIRROR_MATCH_TOLERANCE and angle_sum < 360.0 - _MIRROR_MATCH_TOLERANCE:
                continue
            pairs[id_a] = id_b
            pairs[id_b] = id_a
            break
    return pairs
