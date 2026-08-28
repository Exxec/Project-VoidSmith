"""Qt-independent presentation state derived from normalized backend data."""
from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.core.models import Faction, Hull, ScanResult


@dataclass(frozen=True)
class HullListRecord:
    hull_id: str
    name: str
    hull_size: str
    source_mod: str
    role_hints: tuple[str, ...]


class HullCatalog:
    """Search/filter adapter only; it neither infers roles nor validates fits."""

    def __init__(self, hulls: tuple[Hull, ...], factions: tuple[Faction, ...] = ()) -> None:
        self._hulls = hulls
        self._factions = factions
        self._faction_keys_by_hull_id = {
            hull_id: tuple((faction.id, faction.source_mod) for faction in factions if hull_id in faction.known_hulls)
            for hull_id in {hull.id for hull in hulls}
        }

    @classmethod
    def from_scan(cls, scan: ScanResult) -> HullCatalog:
        return cls(tuple(sorted(scan.hulls, key=lambda hull: (hull.name.casefold(), hull.source_mod, hull.id))), tuple(scan.factions))

    def hull_sizes(self) -> tuple[str, ...]:
        return tuple(sorted({hull.hull_size for hull in self._hulls if hull.hull_size}))

    def source_mods(self) -> tuple[str, ...]:
        return tuple(sorted({hull.source_mod for hull in self._hulls}))

    def factions(self) -> tuple[Faction, ...]:
        """Parsed factions that declare at least one currently scanned hull."""
        hull_ids = {hull.id for hull in self._hulls}
        return tuple(sorted((faction for faction in self._factions if hull_ids.intersection(faction.known_hulls)), key=lambda faction: (faction.name.casefold(), faction.source_mod, faction.id)))

    def faction_labels_for(self, hull: Hull) -> tuple[str, ...]:
        keys = set(self._faction_keys_by_hull_id.get(hull.id, ()))
        return tuple(faction.name for faction in self._factions if (faction.id, faction.source_mod) in keys)

    def filter(self, text: str = "", hull_size: str | None = None, source_mod: str | None = None, faction_key: tuple[str, str] | None = None) -> tuple[Hull, ...]:
        needle = text.strip().casefold()
        return tuple(hull for hull in self._hulls if
                     (not needle or needle in hull.name.casefold() or needle in hull.id.casefold()) and
                     (hull_size is None or hull.hull_size == hull_size) and
                     (source_mod is None or hull.source_mod == source_mod) and
                     (faction_key is None or faction_key in self._faction_keys_by_hull_id.get(hull.id, ())))
