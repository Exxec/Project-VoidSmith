from __future__ import annotations

import hashlib
import json
import logging
import marshal
import re
import sys
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import cast

from starsector_variant_generator.core.models import (
    Entity,
    Faction,
    FighterWing,
    Hull,
    Hullmod,
    ModInfo,
    ScanMetrics,
    ScanProgress,
    ScanResult,
    SourceType,
    Variant,
    Weapon,
)
from starsector_variant_generator.parsers.common import csv_rows, json_file
from starsector_variant_generator.parsers.entities import (
    faction_from_file,
    fighter_from_row,
    hull_from_row,
    hull_from_skin,
    hullmod_from_row,
    variant_from_file,
    weapon_from_row,
    weapon_spec_fields,
)

Parser = Callable[..., Entity]


class ScanCancelled(Exception):
    """Raised from `Scanner.scan()` when a caller-supplied `cancel_check`
    reports a cancellation request. Checked cooperatively between sources
    (fingerprinting and parsing are both per-source loops), not
    preemptively -- a single source's own fingerprint/parse still runs to
    completion once started, so cancellation is bounded to roughly one
    source's worth of time rather than instant, but no longer requires
    waiting for the entire remaining scan."""


@dataclass(frozen=True)
class SourceScanFragment:
    """Independent, mergeable output of parsing one core/mod source.

    Workers never mutate the parent scan result.  The coordinator merges these
    fragments in the already-discovered stable source order, preserving output,
    warning, and error determinism even when filesystem reads overlap.
    """

    result: ScanResult
    pending_skins: tuple[tuple[str, str | None, Path, dict], ...]


# ``marshal`` snapshots are local implementation caches, not exchange files:
# Python-major/minor-specific encoding is intentional. They avoid paying JSON
# parse/serialization cost for thousands of already-normalized local records.
SOURCE_CACHE_SCHEMA = f"source-scan-cache-5-py{sys.version_info.major}.{sys.version_info.minor}"


class Scanner:
    """Read-only scanner for standard data locations in core and installed mods."""

    def __init__(
        self,
        game_root: Path,
        logger: logging.Logger | None = None,
        include_disabled_mods: bool = False,
        progress_callback: Callable[[ScanProgress], None] | None = None,
        cache_dir: Path | None = None,
        max_workers: int | None = None,
        extra_mod_paths: tuple[Path, ...] = (),
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.game_root = game_root
        self.include_disabled_mods = include_disabled_mods
        # Cooperative cancellation only: checked between sources, never
        # preemptively. See ScanCancelled's docstring.
        self._cancel_check = cancel_check
        # Additional mod directories scanned alongside the normal core +
        # enabled-mods set, always treated as enabled regardless of
        # `mods/enabled_mods.json`. Each is read the same way an installed
        # mod is (a `mod_info.json` at its root), so it need not live under
        # `game_root/mods/` at all -- this is how a user-supplied (e.g.
        # drag-and-dropped) mod folder or extracted archive joins the scan
        # without needing to be installed first.
        self.extra_mod_paths = extra_mod_paths
        self.discovery_skipped: list[str] = []
        self._hash_cache: dict[Path, str] = {}
        self._hash_bytes = 0
        self._progress_callback = progress_callback
        # Snapshots contain only normalized records derived from the user's
        # local source files. They are optional, output-local, hash-verified,
        # and never written beside a game/mod source.
        self.cache_dir = cache_dir
        # Local Starsector installs are commonly disk-bound. The real-install
        # benchmark keeps serial parsing as the default; callers can opt into
        # a measured bounded value (up to eight) through ``max_workers``.
        self.max_workers = max(1, min(max_workers if max_workers is not None else 1, 8))
        # (mod_id, mod_version, skin_path, raw_skin_dict) -- resolved against
        # every mod's hulls only after the full scan loop finishes, since a
        # skin's baseHullId may belong to a mod scanned later. See SVG-014.
        self._pending_skins: list[tuple[str, str | None, Path, dict]] = []
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger("svg.scanner")
            self.logger.propagate = False
            if not self.logger.handlers:
                self.logger.addHandler(logging.NullHandler())

    def enabled_mod_ids(self) -> list[str] | None:
        candidates = (self.game_root / "mods" / "enabled_mods.json", self.game_root / "settings.json")
        for settings in candidates:
            if not settings.exists():
                continue
            try:
                data = json_file(settings)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.logger.warning("Unable to read enabled mods from %s: %s", settings, exc)
                self.discovery_skipped.append(f"Enabled-mod configuration unreadable: {settings}: {exc}")
                continue
            value = data.get("enabledMods")
            if isinstance(value, list):
                return [str(item) for item in value]
        return None

    def discover_sources(self, enabled: list[str] | None = None) -> list[ModInfo]:
        core_path = self.game_root / "starsector-core"
        if not core_path.is_dir():
            core_path = self.game_root
        sources = [ModInfo("core", "Starsector Core", None, core_path, True, source_type=SourceType.CORE)]
        if enabled is None:
            enabled = self.enabled_mod_ids()
        mods_dir = self.game_root / "mods"
        installed_ids: set[str] = set()
        if mods_dir.exists():
            for index, child in enumerate(sorted(path for path in mods_dir.iterdir() if path.is_dir())):
                info = self._mod_info_from_dir(child, index, enabled)
                if info is not None:
                    installed_ids.add(info.mod_id)
                    sources.append(info)
        for index, extra_path in enumerate(self.extra_mod_paths):
            # An extra path is always treated as enabled, since the user
            # explicitly supplied it to be scanned -- `enabled_mods.json`
            # says nothing about it either way. A path that happens to
            # duplicate an already-installed mod id is scanned as its own
            # independent source anyway: `Registry` already surfaces
            # same-id collisions explicitly rather than guessing.
            info = self._mod_info_from_dir(extra_path, len(installed_ids) + index, None)
            if info is not None:
                sources.append(replace(info, enabled=True))
            else:
                self.discovery_skipped.append(f"No mod_info.json found for dropped path: {extra_path}")
        return sources

    def _mod_info_from_dir(self, child: Path, load_order: int, enabled: list[str] | None) -> ModInfo | None:
        info_path = child / "mod_info.json"
        if not info_path.exists():
            return None
        try:
            raw = json_file(info_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.logger.warning("Skipping malformed mod info %s: %s", info_path, exc)
            self.discovery_skipped.append(f"Malformed mod metadata skipped: {info_path}: {exc}")
            return None
        mod_id = str(raw.get("id", child.name))
        dependencies = self._dependency_ids(raw.get("dependencies", []), info_path)
        version = json.dumps(raw["version"], sort_keys=True, separators=(",", ":")) if isinstance(raw.get("version"), (dict, list)) else (str(raw["version"]) if "version" in raw else None)
        return ModInfo(
            mod_id=mod_id, mod_name=str(raw.get("name", mod_id)), version=version, path=child,
            enabled=(mod_id in enabled) if enabled is not None else None, dependencies=dependencies,
            load_order=load_order, source_type=SourceType.MOD,
        )

    def _dependency_ids(self, value: object, info_path: Path) -> tuple[str, ...]:
        """Extract only explicitly declared dependency IDs; ignore version semantics."""
        if not isinstance(value, list):
            self.discovery_skipped.append(f"Non-list dependency declaration skipped: {info_path}")
            return ()
        dependency_ids: list[str] = []
        for item in value:
            if isinstance(item, str) and item:
                dependency_ids.append(item)
            elif isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
                dependency_ids.append(item["id"])
            else:
                self.discovery_skipped.append(f"Dependency entry without explicit string id skipped: {info_path}")
        return tuple(dependency_ids)

    def scan(self) -> ScanResult:
        result = ScanResult()
        self.discovery_skipped = []
        self._pending_skins = []
        self._hash_cache = {}
        self._hash_bytes = 0
        timings: dict[str, float] = {}
        self.logger.info("Starting read-only scan of %s", self.game_root)
        started = perf_counter()
        self._emit_progress("DISCOVERING", result)
        enabled = self.enabled_mod_ids()
        if enabled is None and (self.game_root / "mods").is_dir():
            result.warnings.append("Enabled-mod configuration unavailable; scanning all discovered installed mods.")
        sources = self.discover_sources(enabled)
        timings["discovery"] = perf_counter() - started
        result.skipped_entities.extend(self.discovery_skipped)
        discovered_ids = {source.mod_id for source in sources}
        if enabled is not None:
            for mod_id in enabled:
                if mod_id not in discovered_ids:
                    result.skipped_entities.append(f"Enabled mod not discovered: {mod_id}")
        scan_sources = [source for source in sources if source.source_type is not SourceType.MOD or source.enabled is not False or self.include_disabled_mods]
        parsing_started = perf_counter()
        self._emit_progress("PARSING", result, total_sources=len(scan_sources))
        scanned_sources = 0
        entities_seen = 0
        reusable_fragments: dict[int, SourceScanFragment] = {}
        source_fingerprints: dict[int, str | None] = {}
        sources_to_parse: list[tuple[int, ModInfo]] = []
        # Checking each source's cache fingerprint (hashing its files) runs
        # here, before any real parsing starts. It's normally fast, but on a
        # large install it's still real, reportable work -- a cache hit
        # completes "instantly" from the caller's perspective, so it's
        # reported as done the moment it's found rather than silently.
        #
        # On a cache MISS -- every source, on a genuinely first-ever scan,
        # which is exactly what a new user's first "Scan Installed Data"
        # click produces -- nothing below this loop reports anything until
        # a source's real parse future resolves. Measured against the real
        # 148-mod install with a cold cache: this loop alone (just hashing
        # files to check cache eligibility, before any real parsing) can
        # take upwards of a minute with the "PARSING 0/119" event as the
        # only prior progress report, indistinguishable from the original
        # end-of-scan-burst bug this project already fixed once. Emitting a
        # dedicated FINGERPRINTING progress event per source here (hit or
        # miss) closes that gap; PARSING's own 0..len(scan_sources) count
        # then starts fresh once this loop finishes, unaffected.
        fingerprint_total = len(sources)
        fingerprinting_started = perf_counter()
        # Fingerprinting is many small, independent file-hash reads spread
        # across (potentially) hundreds of sources -- a different shape of
        # work than PARSING (measured disk-I/O-bound; serial is already
        # optimal there, see the worker-count benchmark in this project's
        # WORK_LOG). This one measurably benefits from overlapping those
        # reads. Two independent real measurements against the local
        # 149-mod install, both correctness-checked (parallel fingerprints
        # identical to serial output):
        #   1) isolated `_source_fingerprint` calls in a microbenchmark --
        #      serial median 8.67s (min 8.46s) across 3 runs; 2 workers
        #      6.70s; 3 workers 5.99s; 4 workers median 5.53s (min 5.23s,
        #      the consistent best); 6 and 8 workers both measured
        #      slightly worse than 4.
        #   2) a direct same-harness A/B on the real `Scanner.scan()` path
        #      itself (`tools/profile_scan.py`, 3 runs each, temporarily
        #      forcing this pool to 1 worker for the "before" figure):
        #      warm-cache total dropped from median 5.89s (fingerprinting
        #      alone 5.78s) to median 3.84s (fingerprinting alone 3.68s)
        #      -- roughly a 35% cut, and since a warm scan's remaining
        #      cost is now almost entirely fingerprinting (PARSING is
        #      ~0s on a cache hit), this is the dominant real lever for
        #      warm-start latency; a cold run improved too, 20.72s -> 17.56s,
        #      a smaller relative gain since PARSING still dominates there.
        # Dispatched to its own bounded pool sized independently of
        # `max_workers` (which stays 1 by default, calibrated for the
        # separate, already-decided PARSING question) since this is a
        # distinct, positively-measured improvement rather than shared
        # tuning -- enabled unconditionally since both measurements agree
        # and the source order this loop reports progress/results in is
        # unaffected (see below).
        #
        # Every future is submitted up front so the real hashing work
        # starts immediately and runs concurrently regardless of harvest
        # order; this loop still walks `sources` in fixed index order and
        # blocks on each index's own future in turn (returning instantly
        # once that source's hashing already finished in the background),
        # so FINGERPRINTING progress events keep reporting in the exact
        # same deterministic per-source order and cadence as before.
        fingerprint_targets = [
            (index, source) for index, source in enumerate(sources)
            if not (source.source_type is SourceType.MOD and source.enabled is False and not self.include_disabled_mods)
        ]
        fingerprint_worker_count = min(4, max(1, len(fingerprint_targets)))
        fingerprint_futures: dict[int, Future[tuple[str | None, dict[Path, str], int]]] = {}
        fingerprint_executor = ThreadPoolExecutor(
            max_workers=fingerprint_worker_count, thread_name_prefix="voidsmith-fingerprint",
        ) if fingerprint_targets else None
        if fingerprint_executor is not None:
            fingerprint_futures = {
                index: fingerprint_executor.submit(self._source_fingerprint_isolated, source)
                for index, source in fingerprint_targets
            }
        try:
            for index, source in enumerate(sources):
                if self._cancel_check is not None and self._cancel_check():
                    raise ScanCancelled("Scan cancelled by user request during fingerprinting.")
                result.mods.append(source)
                source_label = source.mod_name or source.mod_id
                # A "starting" event with the real source name, before any work on
                # it happens -- not just the "done" event below. A single source's
                # own fingerprint/parse can itself take real, visible time on a
                # large mod, so a UI showing only post-completion counts still
                # looks frozen while that one source is in progress; naming it up
                # front is what actually lets a user see "it's working on X right
                # now" rather than just a number ticking up.
                self._emit_progress("FINGERPRINTING", result, index, fingerprint_total, current_source=source_label)
                if source.source_type is SourceType.MOD and source.enabled is False and not self.include_disabled_mods:
                    self.logger.info("Skipping disabled mod %s", source.mod_id)
                    self._emit_progress("FINGERPRINTING", result, index + 1, fingerprint_total, current_source=source_label)
                    continue
                # Timestamped start/end pair for this specific source, at INFO
                # level (already written to <output_dir>/logs/svg.log by
                # configure_logging). If a scan ever appears to hang again, the
                # log's last unmatched "fingerprinting" line -- with no matching
                # "took Ns" line after it -- names exactly which source and how
                # long it had been running when the log was last read, without
                # needing to reproduce the issue live to diagnose it. Under the
                # concurrent dispatch above, "took Ns" reflects how long this
                # loop waited on this source's future, not necessarily that
                # source's own isolated hashing time (it may have already
                # finished in the background before its turn came up).
                fp_started = perf_counter()
                self.logger.info("Fingerprinting source %d/%d: %s", index + 1, fingerprint_total, source_label)
                fingerprint, worker_hash_cache, worker_hash_bytes = fingerprint_futures[index].result()
                self._hash_cache.update(worker_hash_cache)
                self._hash_bytes += worker_hash_bytes
                source_fingerprints[index] = fingerprint
                self.logger.info("Fingerprinted %s in %.2fs", source_label, perf_counter() - fp_started)
                self._emit_progress("FINGERPRINTING", result, index + 1, fingerprint_total, current_source=source_label)
                cached = self._load_source_fragment(source, fingerprint)
                if cached is None:
                    sources_to_parse.append((index, source))
                else:
                    reusable_fragments[index] = cached
                    scanned_sources += 1
                    entities_seen += self._fragment_entity_count(cached)
                    self._emit_progress("PARSING", result, scanned_sources, len(scan_sources), entities_seen, current_source=source_label)
        finally:
            if fingerprint_executor is not None:
                # Same bounded-cancellation contract as the PARSING pool
                # below: not-yet-started futures are dropped, anything
                # already running finishes in the background rather than
                # being forcibly killed, and is no longer waited on beyond
                # the one already in flight.
                fingerprint_executor.shutdown(wait=True, cancel_futures=True)
        timings["fingerprinting"] = perf_counter() - fingerprinting_started
        source_parsing_started = perf_counter()
        parsed_fragments: dict[int, SourceScanFragment] = {}
        if sources_to_parse:
            # Individual sources are independent until the dedicated serial
            # skin/reference-resolution stage below. Each worker owns its hash
            # cache and pending-skin list; the coordinator merges by source
            # order below (the loop after this block), never completion
            # order -- Registry construction and report output must stay
            # reproducible regardless of which source happens to finish first.
            #
            # Harvesting used to block on `futures[index].result()` in
            # submission order: `for index, source in sources_to_parse`. That
            # kept behavior identical to a single-worker scan, but under a
            # caller-supplied `max_workers > 1` it meant progress reporting
            # (and this source's cache write) stalled behind whichever
            # earlier-submitted source happened to still be running, even
            # after a later-submitted, faster source had already finished --
            # e.g. a huge core scan submitted first blocking a tiny mod
            # submitted second from ever showing "done" until the core
            # finished, even though the tiny mod finished in a fraction of
            # the time. `as_completed()` reports each source's progress and
            # persists its cache snapshot the moment it is genuinely done, in
            # true completion order, while `parsed_fragments` is still keyed
            # by source index so the merge loop below stays in fixed,
            # deterministic source order no matter what order this harvests
            # in. See test_scanner.py's
            # `test_parse_futures_harvest_in_completion_order_but_merge_stays_
            # deterministic` for a regression proving both properties.
            worker_count = min(self.max_workers, len(sources_to_parse))
            executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="voidsmith-scan")
            try:
                future_to_index = {
                    executor.submit(self._scan_source_fragment, source): index
                    for index, source in sources_to_parse
                }
                source_by_index = dict(sources_to_parse)
                for future in as_completed(future_to_index):
                    index = future_to_index[future]
                    source = source_by_index[index]
                    if self._cancel_check is not None and self._cancel_check():
                        raise ScanCancelled("Scan cancelled by user request during parsing.")
                    source_label = source.mod_name or source.mod_id
                    fragment = future.result()
                    parsed_fragments[index] = fragment
                    self._store_source_fragment(source, source_fingerprints[index], fragment)
                    scanned_sources += 1
                    entities_seen += self._fragment_entity_count(fragment)
                    self.logger.info("Parsed %s (%d/%d)", source_label, scanned_sources, len(scan_sources))
                    self._emit_progress("PARSING", result, scanned_sources, len(scan_sources), entities_seen, current_source=source_label)
            finally:
                # Any future not yet started is cancelled outright; a future
                # already running (at most one, under the settled serial
                # default) still finishes in the background rather than
                # being forcibly killed -- Python threads cannot be
                # preempted safely -- but is no longer waited on for every
                # remaining source, only the one already in flight.
                executor.shutdown(wait=True, cancel_futures=True)
        timings["source_parsing"] = perf_counter() - source_parsing_started
        for index, source in [(index, source) for index, source in enumerate(sources)
                              if not (source.source_type is SourceType.MOD and source.enabled is False and not self.include_disabled_mods)]:
            fragment = reusable_fragments.get(index) or parsed_fragments[index]
            self._merge_fragment(result, fragment)
            self._pending_skins.extend(fragment.pending_skins)
        timings["parsing"] = perf_counter() - parsing_started
        resolving_started = perf_counter()
        self._emit_progress("RESOLVING_REFERENCES", result, scanned_sources, len(scan_sources))
        self._resolve_skins(result)
        timings["reference_resolution"] = perf_counter() - resolving_started
        timings["total"] = perf_counter() - started
        result.scan_metrics = ScanMetrics(
            stage_seconds={key: round(value, 6) for key, value in timings.items()},
            sources_scanned=scanned_sources,
            files_hashed=len(self._hash_cache),
            bytes_hashed=self._hash_bytes,
            sources_reused=len(reusable_fragments),
            sources_recomputed=len(parsed_fragments),
            parallel_workers=min(self.max_workers, max(1, len(sources_to_parse))),
            cache_hit_rate=round(len(reusable_fragments) / scanned_sources, 6) if scanned_sources else 0.0,
        )
        self._emit_progress("COMPLETE", result, scanned_sources, len(scan_sources))
        self.logger.info(
            "Completed read-only scan: %d hulls, %d weapons, %d variants, %d errors",
            len(result.hulls), len(result.weapons), len(result.variants), len(result.errors),
        )
        return result

    def scan_single_mod(self, mod_root: Path) -> tuple[ModInfo, SourceScanFragment] | None:
        """Parse exactly one mod directory in isolation (e.g. a user-dropped
        mod not yet part of a full scan), without touching any other
        source. Returns `None` if `mod_root` doesn't contain a valid
        `mod_info.json` a real installed mod would have; otherwise the
        resolved `ModInfo` (always `enabled=True`, matching how
        `extra_mod_paths` are already treated) alongside its parsed
        fragment. Public, unlike `_scan_source_fragment`, so a caller
        outside this class (see `api.py::run_incremental_mod_scan`)
        doesn't have to reach into a private method to scan one arbitrary
        mod path -- this is the supported entry point for that."""
        info = self._mod_info_from_dir(mod_root, load_order=0, enabled=None)
        if info is None:
            return None
        info = replace(info, enabled=True)
        return info, self._scan_source_fragment(info)

    def _scan_source_fragment(self, source: ModInfo) -> SourceScanFragment:
        """Parse one source without sharing mutable scan state with workers."""
        worker = Scanner(
            self.game_root,
            logger=self.logger,
            include_disabled_mods=self.include_disabled_mods,
            cache_dir=None,
            max_workers=1,
        )
        # Source fingerprints pre-populate the coordinator hash cache. A worker
        # may still encounter a malformed/unexpected local path; it hashes that
        # path locally rather than sharing mutable accounting state.
        worker._hash_cache = dict(self._hash_cache)
        fragment_result = ScanResult()
        worker._scan_source(source, fragment_result)
        return SourceScanFragment(fragment_result, tuple(worker._pending_skins))

    @staticmethod
    def _merge_fragment(result: ScanResult, fragment: SourceScanFragment) -> None:
        for field in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions", "warnings", "errors", "skipped_entities", "parse_warnings"):
            getattr(result, field).extend(getattr(fragment.result, field))

    @staticmethod
    def _fragment_entity_count(fragment: SourceScanFragment) -> int:
        """Same entity fields `_emit_progress`'s own count covers, for one
        not-yet-merged fragment -- lets progress report a real, incrementally
        growing entity count as each source finishes, without merging (and
        therefore without needing merge's own guaranteed stable order) early."""
        return sum(len(getattr(fragment.result, field)) for field in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions"))

    def _source_files(self, source: ModInfo) -> list[Path]:
        """All local inputs consumed while parsing one source, in stable order."""
        paths: set[Path] = set()
        for relative in (
            "mod_info.json",
            "data/hulls/ship_data.csv",
            "data/weapons/weapon_data.csv",
            "data/hulls/wing_data.csv",
            "data/fighters/wing_data.csv",
            "data/hullmods/hull_mods.csv",
        ):
            path = source.path / relative
            if path.is_file():
                paths.add(path)
        for relative, pattern in (
            ("data/hulls", "*.ship"),
            ("data/hulls/skins", "*.skin"),
            ("data/weapons", "*.wpn"),
            ("data/variants", "*.variant"),
            ("data/world/factions", "*.faction"),
        ):
            directory = source.path / relative
            if directory.is_dir():
                paths.update(path for path in directory.rglob(pattern) if path.is_file())
        return sorted(paths, key=lambda path: path.relative_to(source.path).as_posix())

    def _source_fingerprint(self, source: ModInfo) -> str | None:
        """Exact content fingerprint for an optional normalized source snapshot."""
        try:
            digest = hashlib.sha256()
            digest.update(SOURCE_CACHE_SCHEMA.encode("ascii"))
            digest.update(source.mod_id.encode("utf-8"))
            digest.update((source.version or "").encode("utf-8"))
            for path in self._source_files(source):
                digest.update(path.relative_to(source.path).as_posix().encode("utf-8"))
                digest.update((self._hash_file(path)).encode("ascii"))
            return digest.hexdigest()
        except OSError as exc:
            self.logger.warning("Source cache disabled for %s: %s", source.path, exc)
            return None

    def _source_fingerprint_isolated(self, source: ModInfo) -> tuple[str | None, dict[Path, str], int]:
        """Compute one source's fingerprint against a private hash cache.

        Called from `scan()`'s bounded fingerprinting thread pool. Each
        parallel job gets its own throwaway `Scanner` (mirroring
        `_scan_source_fragment`'s existing isolation for the PARSING pool)
        so concurrent hashing never shares -- and therefore never races on
        -- `self._hash_cache`/`self._hash_bytes`. The caller merges the
        returned per-file hashes and byte count back into its own totals
        once harvested, in the same deterministic source order it always
        used, so `ScanMetrics.files_hashed`/`bytes_hashed` stay accurate
        and later stages (PARSING's own `_scan_source_fragment` workers,
        which are seeded from `self._hash_cache`) still see every file
        this pass already hashed rather than re-reading it from disk.
        """
        worker = Scanner(self.game_root, logger=self.logger, max_workers=1)
        fingerprint = worker._source_fingerprint(source)
        return fingerprint, worker._hash_cache, worker._hash_bytes

    def _source_cache_path(self, source: ModInfo) -> Path | None:
        if self.cache_dir is None:
            return None
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.mod_id).strip("._") or "source"
        # Mod IDs may legitimately collide across unusual local layouts. Keep
        # cache names stable for one installation without treating an ID alone
        # as a globally unique source key.
        source_key = hashlib.sha256(str(source.path.resolve()).encode("utf-8")).hexdigest()[:12]
        return self.cache_dir / "source_snapshots" / f"{safe_id}-{source.source_type.value.lower()}-{source_key}.bin"

    def _load_source_fragment(self, source: ModInfo, fingerprint: str | None) -> SourceScanFragment | None:
        path = self._source_cache_path(source)
        if path is None or fingerprint is None or not path.is_file():
            return None
        try:
            payload = marshal.loads(path.read_bytes())
            if not isinstance(payload, dict) or payload.get("schema_version") != SOURCE_CACHE_SCHEMA:
                return None
            if payload.get("source_id") != source.mod_id or payload.get("source_fingerprint") != fingerprint:
                return None
            fragment = payload.get("fragment")
            if not isinstance(fragment, dict):
                return None
            return _fragment_from_json(fragment)
        except (OSError, EOFError, UnicodeError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
            self.logger.warning("Ignoring unreadable source snapshot %s: %s", path, exc)
            return None

    def _store_source_fragment(self, source: ModInfo, fingerprint: str | None, fragment: SourceScanFragment) -> None:
        path = self._source_cache_path(source)
        if path is None or fingerprint is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": SOURCE_CACHE_SCHEMA,
                "source_id": source.mod_id,
                "source_fingerprint": fingerprint,
                "fragment": _fragment_to_json(fragment),
            }
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(marshal.dumps(payload))
            temporary.replace(path)
        except (OSError, TypeError, ValueError) as exc:
            self.logger.warning("Unable to persist source snapshot %s: %s", path, exc)

    def _emit_progress(
        self, stage: str, result: ScanResult, completed_sources: int = 0, total_sources: int = 0,
        entities_found: int | None = None, current_source: str = "",
    ) -> None:
        if self._progress_callback is None:
            return
        # `result` itself isn't populated with an in-progress PARSING call's
        # entities yet (merging happens later, in guaranteed stable order) --
        # an explicit `entities_found` lets a caller report a real running
        # count from not-yet-merged fragments instead. Only RESOLVING_
        # REFERENCES/COMPLETE (after merge) rely on the `result`-based fallback.
        if entities_found is None:
            entities_found = sum(len(getattr(result, field)) for field in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions"))
        self._progress_callback(ScanProgress(
            stage=stage,
            completed_sources=completed_sources,
            total_sources=total_sources,
            entities_found=entities_found,
            warnings=len(result.warnings),
            errors=len(result.errors),
            current_source=current_source,
        ))

    def _scan_source(self, source: ModInfo, result: ScanResult) -> None:
        jobs: tuple[tuple[str, str, Parser], ...] = (
            ("data/hulls/ship_data.csv", "hulls", hull_from_row),
            ("data/weapons/weapon_data.csv", "weapons", weapon_from_row),
            ("data/hulls/wing_data.csv", "fighters", fighter_from_row),
            ("data/fighters/wing_data.csv", "fighters", fighter_from_row),
            ("data/hullmods/hull_mods.csv", "hullmods", hullmod_from_row),
        )
        # The second wing location supports mods that keep fighter data separately.
        seen: set[tuple[str, str]] = set()
        first_weapon_index = len(result.weapons)
        for relative, destination, parser in jobs:
            file_path = source.path / relative
            key = (destination, str(file_path))
            if key in seen or not file_path.exists():
                continue
            seen.add(key)
            try:
                for row in csv_rows(file_path):
                    try:
                        warning_start = len(result.parse_warnings)
                        id_columns = {
                            "hulls": ("id", "hullId"),
                            "weapons": ("id", "weaponId"),
                            "fighters": ("id", "wingId"),
                            "hullmods": ("id", "hullmodId"),
                        }[destination]
                        if not any(row.get(column) for column in id_columns):
                            result.skipped_entities.append(f"{file_path}: {destination.rstrip('s')} row without a stable id skipped")
                            continue
                        if destination == "hulls":
                            hull_id = row.get("id") or row.get("hullId")
                            ship_path = source.path / "data" / "hulls" / f"{hull_id}.ship" if hull_id else None
                            entity = parser(row, source.mod_id, file_path, ship_path, numeric_warnings=result.parse_warnings)
                        else:
                            ship_path = None
                            entity = parser(row, source.mod_id, file_path, numeric_warnings=result.parse_warnings)
                        for warning in result.parse_warnings[warning_start:]:
                            warning.update({"source_path": str(file_path), "source_mod": source.mod_id, "entity_id": getattr(entity, "id", None)})
                        getattr(result, destination).append(replace(entity, source_hash=self._hash_file(file_path), source_mod_version=source.version))
                    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                        result.errors.append(f"{ship_path or file_path}: {exc}")
            except (OSError, UnicodeError, ValueError) as exc:
                result.errors.append(f"{file_path}: {exc}")
        self._enrich_weapons_from_specs(source, result, first_weapon_index)
        self._scan_json_files(source, result, "data/variants", "*.variant", "variants", variant_from_file)
        self._scan_json_files(source, result, "data/world/factions", "*.faction", "factions", faction_from_file)
        self._scan_skin_files(source, result)

    def _scan_json_files(self, source: ModInfo, result: ScanResult, relative: str, pattern: str, destination: str, parser: Parser) -> None:
        directory = source.path / relative
        if not directory.exists():
            return
        for path in sorted(directory.rglob(pattern)):
            try:
                warning_start = len(result.parse_warnings)
                entity = parser(path, source.mod_id, numeric_warnings=result.parse_warnings)
                for warning in result.parse_warnings[warning_start:]:
                    warning.update({"source_path": str(path), "source_mod": source.mod_id, "entity_id": getattr(entity, "id", None)})
                getattr(result, destination).append(replace(entity, source_hash=self._hash_file(path), source_mod_version=source.version))
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                result.errors.append(f"{path}: {exc}")

    def _hash_file(self, path: Path) -> str:
        if path not in self._hash_cache:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    self._hash_bytes += len(chunk)
                    digest.update(chunk)
            self._hash_cache[path] = digest.hexdigest()
        return self._hash_cache[path]

    def _scan_skin_files(self, source: ModInfo, result: ScanResult) -> None:
        directory = source.path / "data" / "hulls" / "skins"
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.skin")):
            try:
                raw = json_file(path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                result.errors.append(f"{path}: {exc}")
                continue
            self._pending_skins.append((source.mod_id, source.version, path, raw))

    def _resolve_skins(self, result: ScanResult) -> None:
        """Materialize every collected skin against the fully-scanned hull set.

        Deferred to the end of `scan()` (not resolved per-mod) because a
        skin's `baseHullId` can belong to a mod scanned earlier or later
        than the skin's own mod -- e.g. a mod skinning a core hull. Never
        guesses at an ambiguous or missing base hull id; see SVG-014.
        """
        id_counts: dict[str, int] = {}
        for hull in result.hulls:
            id_counts[hull.id] = id_counts.get(hull.id, 0) + 1
        by_id = {hull.id: hull for hull in result.hulls if id_counts[hull.id] == 1}
        for mod_id, version, skin_path, raw in self._pending_skins:
            base_hull_id = raw.get("baseHullId")
            base = by_id.get(base_hull_id) if isinstance(base_hull_id, str) else None
            if base is None:
                reason = "ambiguous" if isinstance(base_hull_id, str) and id_counts.get(base_hull_id, 0) > 1 else "unresolved"
                result.warnings.append(f"{skin_path}: skin's baseHullId {base_hull_id!r} is {reason}; skin not materialized as a hull.")
                continue
            warning_start = len(result.parse_warnings)
            entity = hull_from_skin(base, raw, mod_id, skin_path, numeric_warnings=result.parse_warnings)
            if entity is None:
                result.warnings.append(f"{skin_path}: skin has no usable skinHullId; skipped.")
                continue
            for warning in result.parse_warnings[warning_start:]:
                warning.update({"source_path": str(skin_path), "source_mod": mod_id, "entity_id": entity.id})
            result.hulls.append(replace(entity, source_hash=self._hash_file(skin_path), source_mod_version=version))

    def _enrich_weapons_from_specs(self, source: ModInfo, result: ScanResult, first_weapon_index: int) -> None:
        weapon_dir = source.path / "data" / "weapons"
        if not weapon_dir.exists():
            return
        fields_by_id: dict[str, dict[str, str]] = {}
        for path in weapon_dir.glob("*.wpn"):
            try:
                fields = weapon_spec_fields(path)
            except (OSError, UnicodeError) as exc:
                result.errors.append(f"{path}: {exc}")
                continue
            if fields.get("id"):
                fields_by_id[fields["id"]] = fields
        # Only weapons parsed for this source can be enriched here. Iterating
        # every already-seen weapon once per mod was quadratic in large installs.
        for index in range(first_weapon_index, len(result.weapons)):
            weapon = result.weapons[index]
            if weapon.id not in fields_by_id:
                continue
            fields = fields_by_id[weapon.id]
            raw = dict(weapon.raw)
            raw["weapon_spec"] = fields
            result.weapons[index] = replace(
                weapon,
                mount_type=fields.get("type", weapon.mount_type),
                size=fields.get("size", weapon.size),
                raw=raw,
            )


def _json_safe(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _fragment_to_json(fragment: SourceScanFragment) -> dict[str, object]:
    result = fragment.result
    return {
        "entities": {
            field: [_json_safe(asdict(entity)) for entity in getattr(result, field)]
            for field in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions")
        },
        "warnings": list(result.warnings),
        "errors": list(result.errors),
        "skipped_entities": list(result.skipped_entities),
        "parse_warnings": _json_safe(result.parse_warnings),
        "pending_skins": [
            {"mod_id": mod_id, "version": version, "path": str(path), "raw": _json_safe(raw)}
            for mod_id, version, path, raw in fragment.pending_skins
        ],
    }


def _fragment_from_json(payload: dict[str, object]) -> SourceScanFragment:
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        raise ValueError("source snapshot has no entity document")
    result = ScanResult(
        hulls=[cast(Hull, _entity_from_json("hulls", item)) for item in _json_list(entities.get("hulls"))],
        weapons=[cast(Weapon, _entity_from_json("weapons", item)) for item in _json_list(entities.get("weapons"))],
        fighters=[cast(FighterWing, _entity_from_json("fighters", item)) for item in _json_list(entities.get("fighters"))],
        hullmods=[cast(Hullmod, _entity_from_json("hullmods", item)) for item in _json_list(entities.get("hullmods"))],
        variants=[cast(Variant, _entity_from_json("variants", item)) for item in _json_list(entities.get("variants"))],
        factions=[cast(Faction, _entity_from_json("factions", item)) for item in _json_list(entities.get("factions"))],
        warnings=[str(item) for item in _json_list(payload.get("warnings"))],
        errors=[str(item) for item in _json_list(payload.get("errors"))],
        skipped_entities=[str(item) for item in _json_list(payload.get("skipped_entities"))],
        parse_warnings=[dict(item) for item in _json_list(payload.get("parse_warnings")) if isinstance(item, dict)],
    )
    pending: list[tuple[str, str | None, Path, dict]] = []
    for item in _json_list(payload.get("pending_skins")):
        if not isinstance(item, dict) or not isinstance(item.get("mod_id"), str) or not isinstance(item.get("path"), str) or not isinstance(item.get("raw"), dict):
            raise ValueError("invalid pending skin snapshot record")
        version = item.get("version")
        pending.append((item["mod_id"], str(version) if version is not None else None, Path(item["path"]), dict(item["raw"])))
    return SourceScanFragment(result, tuple(pending))


def _json_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("source snapshot field is not a list")
    return value


def _entity_from_json(kind: str, payload: object) -> object:
    if not isinstance(payload, dict):
        raise ValueError(f"invalid {kind} snapshot entity")
    data = dict(payload)
    if not isinstance(data.get("source_path"), str):
        raise ValueError(f"{kind} snapshot entity has no source path")
    data["source_path"] = Path(data["source_path"])
    if kind == "hulls":
        for field in ("weapon_mounts", "built_in_hullmods", "built_in_fighter_wings", "launch_bay_slots", "hull_hints"):
            data[field] = tuple(data.get(field, ()))
        from starsector_variant_generator.core.models import Hull
        return Hull(**data)
    if kind == "weapons":
        from starsector_variant_generator.core.models import Weapon
        return Weapon(**data)
    if kind == "fighters":
        from starsector_variant_generator.core.models import FighterWing
        return FighterWing(**data)
    if kind == "hullmods":
        from starsector_variant_generator.core.models import Hullmod
        return Hullmod(**data)
    if kind == "variants":
        for field in ("hullmods", "fighter_wings"):
            data[field] = tuple(data.get(field, ()))
        from starsector_variant_generator.core.models import Variant
        return Variant(**data)
    if kind == "factions":
        for field in ("known_hulls", "known_weapons", "known_fighters", "known_hullmods", "tags"):
            data[field] = tuple(data.get(field, ()))
        from starsector_variant_generator.core.models import Faction
        return Faction(**data)
    raise ValueError(f"unsupported source snapshot entity kind: {kind}")
