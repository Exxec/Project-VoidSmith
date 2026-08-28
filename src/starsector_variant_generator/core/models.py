from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SourceType(StrEnum):
    CORE = "CORE"
    MOD = "MOD"


@dataclass(frozen=True)
class ScanProgress:
    """Aggregate read-only scan progress suitable for a UI or CLI."""

    stage: str
    completed_sources: int = 0
    total_sources: int = 0
    entities_found: int = 0
    warnings: int = 0
    errors: int = 0
    # Human-readable name of the source (core, or a mod's own display name)
    # currently being fingerprinted/parsed, or the one that just finished --
    # "" when a stage has no single associated source (DISCOVERING,
    # RESOLVING_REFERENCES, COMPLETE). Lets a UI show real, specific "what's
    # happening right now" feedback instead of only an aggregate count.
    current_source: str = ""


@dataclass(frozen=True)
class ScanMetrics:
    """Workload telemetry used to guide performance work, never scoring."""

    stage_seconds: dict[str, float] = field(default_factory=dict)
    sources_scanned: int = 0
    files_hashed: int = 0
    bytes_hashed: int = 0
    sources_reused: int = 0
    sources_recomputed: int = 0
    parallel_workers: int = 1
    # sources_reused / sources_scanned, or 0.0 when nothing was scanned --
    # a caller previously had to divide the two counts above itself to see
    # cache effectiveness at a glance; this is that same ratio, precomputed
    # once so every report/log surfaces it identically.
    cache_hit_rate: float = 0.0


@dataclass(frozen=True)
class ModInfo:
    mod_id: str
    mod_name: str
    version: str | None
    path: Path
    enabled: bool | None
    dependencies: tuple[str, ...] = ()
    load_order: int | None = None
    source_type: SourceType = SourceType.MOD


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    source_mod: str
    source_path: Path
    source_hash: str | None = None
    source_mod_version: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Hull(Entity):
    hull_size: str | None = None
    ordnance_points: int | None = None
    weapon_mounts: tuple[dict[str, Any], ...] = ()
    built_in_hullmods: tuple[str, ...] = ()
    built_in_fighter_wings: tuple[str, ...] = ()
    launch_bay_slots: tuple[str, ...] = ()
    # Mount id -> weapon id for mounts the hull hardwires (weaponSlots entries
    # with type "BUILT_IN"). Verified against a live scan's ship_data.builtInWeapons;
    # see docs/ROADMAP.md Tier 1.4.
    built_in_weapons: dict[str, str] = field(default_factory=dict)
    flux_capacity: float | None = None
    flux_dissipation: float | None = None
    shield_upkeep: float | None = None
    # Authoritative fighter-bay capacity from the hull CSV's "fighter bays"
    # column. Not derivable from len(launch_bay_slots): a single weaponSlot
    # entry of type LAUNCH_BAY can represent multiple physical bays via a
    # multi-pair "locations" array (verified against the real Condor-class
    # hull, which has one LAUNCH_BAY slot but "fighter bays":2). See
    # docs/ROADMAP.md Tier 1.3.
    fighter_bays: int | None = None
    # Civilian/logistics stats (DATA_SCHEMA.md v0.3's Hull.cargo_capacity
    # etc.) and the hull CSV's own "hints" column, e.g. "CIVILIAN,
    # FREIGHTER" or "CARRIER, COMBAT" -- a real, documented per-hull role
    # signal, not an inferred one. See docs/ROADMAP.md's civilian
    # classification section for why role scoring is grounded in this
    # field rather than cargo/fuel-ratio thresholds (verified unreliable:
    # civilian- and combat-hinted hulls have nearly identical cargo
    # medians in real data).
    cargo_capacity: float | None = None
    fuel_capacity: float | None = None
    crew_min: int | None = None
    crew_max: int | None = None
    supplies_per_month: float | None = None
    max_burn: float | None = None
    # Direct hull CSV strategic signature evidence.  This remains a raw
    # static value: campaign, hullmod, and fleet-wide sensor mechanics are
    # deliberately not inferred from it.
    sensor_profile: float | None = None
    hull_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class Weapon(Entity):
    size: str | None = None
    mount_type: str | None = None
    ordnance_points: int | None = None
    range: float | None = None
    damage_type: str | None = None
    # Flux generated per shot / per second of sustained fire. Starsector's
    # weapon_data.csv labels these columns "energy/shot" and "energy/second"
    # regardless of the weapon's mount_type (BALLISTIC weapons still cost
    # flux); verified against a live scan, see docs/ROADMAP.md Tier 2.1.
    flux_per_shot: float | None = None
    flux_per_second: float | None = None


@dataclass(frozen=True)
class FighterWing(Entity):
    role: str | None = None
    op_cost: int | None = None


@dataclass(frozen=True)
class Hullmod(Entity):
    hidden: bool | None = None
    built_in_only: bool | None = None
    op_cost_by_hull_size: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Variant(Entity):
    hull_id: str | None = None
    weapons_by_mount: dict[str, str] = field(default_factory=dict)
    hullmods: tuple[str, ...] = ()
    fighter_wings: tuple[str, ...] = ()
    flux_vents: int | None = None
    flux_capacitors: int | None = None


@dataclass(frozen=True)
class Faction(Entity):
    known_hulls: tuple[str, ...] = ()
    known_weapons: tuple[str, ...] = ()
    known_fighters: tuple[str, ...] = ()
    known_hullmods: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass
class ScanResult:
    mods: list[ModInfo] = field(default_factory=list)
    hulls: list[Hull] = field(default_factory=list)
    weapons: list[Weapon] = field(default_factory=list)
    fighters: list[FighterWing] = field(default_factory=list)
    hullmods: list[Hullmod] = field(default_factory=list)
    variants: list[Variant] = field(default_factory=list)
    factions: list[Faction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_entities: list[str] = field(default_factory=list)
    # Structured, non-fatal source-data coercion diagnostics. Kept separate
    # from free-text warnings so consumers can filter by field/type safely.
    parse_warnings: list[dict[str, object]] = field(default_factory=list)
    scan_metrics: ScanMetrics | None = None

    def report(self, heuristic_set: str, include_entities: bool = True) -> dict[str, Any]:
        """Return a portable scan summary, optionally including raw entities.

        Diagnostic summaries intentionally omit raw mod/game-derived records so
        they remain compact and avoid duplicating local source content.
        """
        report = {
            "heuristic_set": heuristic_set,
            "counts": {key: len(getattr(self, key)) for key in ("mods", "hulls", "weapons", "fighters", "hullmods", "variants", "factions")},
            "warnings": self.warnings,
            "errors": self.errors,
            "skipped_entities": self.skipped_entities,
            "parse_warnings": self.parse_warnings,
        }
        if self.scan_metrics is not None:
            report["scan_metrics"] = asdict(self.scan_metrics)
        if include_entities:
            report["entities"] = {key: [asdict(value) for value in getattr(self, key)] for key in ("mods", "hulls", "weapons", "fighters", "hullmods", "variants", "factions")}
        return report
