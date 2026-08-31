from __future__ import annotations

import weakref
from dataclasses import dataclass
from statistics import mean

from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Faction, Variant
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class DoctrineEvidence:
    faction_id: str
    variants_examined: int
    average_weapon_range: float | None
    repeated_hullmods: tuple[tuple[str, int], ...]
    notes: tuple[str, ...]
    # ROADMAP.md Phase 29 (Evidence/Provenance Unification): this evidence is
    # always a statistical aggregate over real, already-parsed variants
    # (AGENTS.md's adapter-layer ladder tier 5, "existing variant/use
    # evidence -- statistical only, never hard truth"), which maps onto the
    # shared `EvidenceClass` vocabulary as `INFERRED_MECHANICS` -- a real
    # usage pattern inferred from many variants, not a single directly-read
    # fact (`DIRECT_DATA`) or an unverifiable claim. `UNKNOWN` when zero
    # variants were examined, since there is then no pattern to infer from
    # at all. Additive: `notes` (the pre-existing free-text caveat) is left
    # exactly as-is alongside this new structured field.
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


# Scan-local memoization, keyed on the real `Registry` object's identity via
# a genuine weak reference (never a manually tracked `id()` alone, which can
# be silently reused once an object is garbage-collected) so a distinct
# scan's registry can never serve another scan's cached evidence, and a
# registry that goes out of scope drops its cache entry automatically rather
# than leaking. `Registry` is a plain (non-frozen) dataclass, so it isn't
# hashable and can't be a `WeakKeyDictionary` key directly; `id(registry)`
# indexes the outer dict instead, but every entry also carries the real
# `weakref.ref` and is only trusted when that reference still resolves to
# the *same* registry object -- the weakref's own finalizer callback removes
# the entry as soon as that registry is collected, so a later, unrelated
# object reusing the same `id()` can never find a stale entry still present.
# `analyze_faction_doctrine`'s only real inputs are `faction.id` (label
# only) and `faction.source_mod` (the actual filter) -- no other Faction
# field is read here -- so those two strings are the only inner key needed.
# This mirrors `analysis/hullmod_static_analysis.py::_java_sources`'s own
# "in-memory scan-local cache, not a persistent cache" precedent.
#
# Found live against the real 148-mod install: a single faction's retrofit
# leg of the Gap Recommendation Engine (`generation/refit.py::improve_quality`
# via `scoring/candidate_score.py::score_candidate`) can re-derive this exact
# same evidence tens of thousands of times across one search (44,076 calls /
# ~26s observed for one small faction) even though the faction and registry
# never change across that search -- this cache removes that pure, repeated
# recomputation without altering any result.
_DOCTRINE_CACHE: dict[int, tuple[weakref.ReferenceType[Registry], dict[tuple[str, str | None], DoctrineEvidence]]] = {}


def _doctrine_cache_for_registry(registry: Registry) -> dict[tuple[str, str | None], DoctrineEvidence]:
    key = id(registry)
    entry = _DOCTRINE_CACHE.get(key)
    if entry is not None and entry[0]() is registry:
        return entry[1]
    inner: dict[tuple[str, str | None], DoctrineEvidence] = {}

    def _cleanup(_ref: weakref.ReferenceType[Registry], _key: int = key) -> None:
        _DOCTRINE_CACHE.pop(_key, None)

    _DOCTRINE_CACHE[key] = (weakref.ref(registry, _cleanup), inner)
    return inner


def analyze_faction_doctrine(faction: Faction, registry: Registry) -> DoctrineEvidence:
    """Summarize existing source-variant evidence; never infer game legality."""
    per_registry = _doctrine_cache_for_registry(registry)
    cache_key = (faction.id, faction.source_mod)
    cached = per_registry.get(cache_key)
    if cached is not None:
        return cached
    evidence = _compute_faction_doctrine(faction, registry)
    per_registry[cache_key] = evidence
    return evidence


def _compute_faction_doctrine(faction: Faction, registry: Registry) -> DoctrineEvidence:
    variants = [variant for variant in registry.variants.by_id.values() if variant.source_mod == faction.source_mod]
    ranges: list[float] = []
    hullmod_counts: dict[str, int] = {}
    for variant in variants:
        for weapon_id in variant.weapons_by_mount.values():
            weapon = registry.weapons.by_id.get(weapon_id)
            if weapon and weapon.range is not None:
                ranges.append(weapon.range)
        for hullmod in variant.hullmods:
            hullmod_counts[hullmod] = hullmod_counts.get(hullmod, 0) + 1
    repeated = tuple(sorted(hullmod_counts.items(), key=lambda item: (-item[1], item[0]))[:10])
    return DoctrineEvidence(
        faction.id, len(variants), round(mean(ranges), 1) if ranges else None, repeated,
        ("Existing variants are descriptive evidence, not a legality rule or optimality proof.",),
        evidence_class=EvidenceClass.INFERRED_MECHANICS if variants else EvidenceClass.UNKNOWN,
    )


def doctrine_match(candidate: Variant, registry: Registry, evidence: DoctrineEvidence, heuristic_set: str = "baseline_0.2") -> float | None:
    """Score how closely a candidate resembles one faction's observed evidence.

    Returns None -- not a low score -- when there is no usable evidence, so
    callers can tell "no signal" apart from "poor match" instead of the
    absence of data silently reading as a bad match. This is a quality
    heuristic only: it must never be consulted by validate_variant, and a
    low or missing match must never suppress or reinterpret a legality
    result. The exact weighting is a first-pass heuristic, versioned under
    `heuristic_set` and intended to be tuned by a future benchmark suite
    (see docs/ROADMAP.md, "Benchmark & calibration suite").
    """
    if evidence.variants_examined == 0:
        return None
    heuristics = get_heuristic_set(heuristic_set).values
    weapons = [registry.weapons.by_id[weapon_id] for weapon_id in candidate.weapons_by_mount.values() if weapon_id in registry.weapons.by_id]
    ranges = [weapon.range for weapon in weapons if weapon.range is not None]
    range_component = None
    if ranges and evidence.average_weapon_range is not None:
        candidate_average = mean(ranges)
        tolerance = max(evidence.average_weapon_range * heuristics["doctrine_range_tolerance_fraction"], 1.0)
        deviation = abs(candidate_average - evidence.average_weapon_range)
        range_component = max(0.0, 1.0 - max(0.0, deviation - tolerance) / evidence.average_weapon_range)
    repeated_ids = {hullmod_id for hullmod_id, _ in evidence.repeated_hullmods}
    overlap_component = (len(set(candidate.hullmods) & repeated_ids) / len(repeated_ids)) if repeated_ids else None
    parts = [
        (range_component, heuristics["doctrine_range_weight"]),
        (overlap_component, heuristics["doctrine_hullmod_overlap_weight"]),
    ]
    usable = [(value, weight) for value, weight in parts if value is not None]
    if not usable:
        return None
    total_weight = sum(weight for _, weight in usable)
    return round(sum(value * weight for value, weight in usable) / total_weight, 3)
