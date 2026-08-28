"""Run reviewer calibration labels against a current local scan.

This module deliberately evaluates reviewer-authored expectations only.  It
never creates labels, changes heuristics, or treats its own output as ground
truth.  A label whose exact source hull cannot be generated safely remains
``UNSUPPORTED`` rather than selecting a same-ID entity from another mod.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starsector_variant_generator import api
from starsector_variant_generator.analysis.calibration import (
    CalibrationExpectationKind,
    CalibrationLabel,
)
from starsector_variant_generator.analysis.gap_recommendation import (
    ScenarioCategory,
    explain_native_candidate,
    explain_scenario_candidate,
    recommend_gap_solutions,
)
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack
from starsector_variant_generator.core.models import Hull, ScanResult
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class CalibrationRun:
    """Normalized observations and non-authoritative execution diagnostics."""

    observations: dict[str, dict[str, Any]]
    diagnostics: tuple[dict[str, str], ...]
    # Optional, additive: `entity_key -> confidence` from a real recommendation
    # Why-Not explanation (ROADMAP.md Phase 39 item 5, "confidence-weighted
    # calibration"). Empty for observers that don't compute a confidence
    # (e.g. `collect_build_observations`). Never influences MATCH/MISMATCH --
    # only usable via `calibration.confidence_weighted_summary` as separate,
    # explicit reporting nuance.
    confidences: dict[str, float] = field(default_factory=dict)


def _hull_by_source_and_id(scan: ScanResult, source_mod: str, hull_id: str) -> Hull | None:
    matches = [hull for hull in scan.hulls if hull.source_mod == source_mod and hull.id == hull_id]
    return matches[0] if len(matches) == 1 else None


def _source_hull(label: CalibrationLabel, scan: ScanResult) -> Hull | None:
    """Resolve only a fully-qualified ``hull:<source_mod>:<id>`` key."""
    parts = label.entity_key.split(":", 2)
    if len(parts) != 3 or parts[0] != "hull":
        return None
    return _hull_by_source_and_id(scan, parts[1], parts[2])


def _parse_prefixed_key(entity_key: str, prefix: str, field_count: int) -> tuple[str, ...] | None:
    """Split a colon-delimited ``<prefix>:...`` entity_key into exactly
    ``field_count`` fields (the final field absorbs any remaining colons),
    or ``None`` if the prefix or field count doesn't match."""
    parts = entity_key.split(":", field_count - 1)
    if len(parts) != field_count or parts[0] != prefix:
        return None
    return tuple(parts)


def _legal_candidates(outcome: api.GenerateOutcome) -> list[dict[str, Any]]:
    """Real LEGAL candidates in `run_generate`'s own ranked order (legal
    before illegal, score second, per CLAUDE.md/`api.py::run_generate` --
    never re-sorted here)."""
    return [candidate for candidate in outcome.assessed_candidates if candidate.get("legality") == "LEGAL"]


def _build_actual(legal_candidates: list[dict[str, Any]]) -> str | None:
    """Return the best independently generated build ID, if one exists."""
    for candidate in legal_candidates:
        build = candidate.get("build_archetype")
        if isinstance(build, dict) and isinstance(build.get("build_id"), str):
            return build["build_id"]
    return None


# EXPECTED_TOP_SET sentinel for "the expected candidate never appeared
# anywhere in the real, bounded set of candidates an observer actually
# searched/ranked" -- deliberately a real, comparable integer larger than
# any realistic `top_n` rather than `None`, so `evaluate_calibration` reports
# it as a genuine MISMATCH (real evidence the expectation did not hold
# against what was actually searched), not UNSUPPORTED (which means no
# ranking data exists at all -- see `calibration.evaluate_calibration`).
NOT_IN_RANKED_SET = 10**6


def _build_rank(legal_candidates: list[dict[str, Any]], accepted: set[str]) -> int:
    """1-based rank of the first LEGAL candidate whose build_id is in
    `accepted`, within the real candidates `run_generate` actually searched
    (bounded by its own `max_candidates`/`search_depth` -- this is a rank
    within what was actually searched, not a claim of exhaustive ranking)."""
    for index, candidate in enumerate(legal_candidates, start=1):
        build = candidate.get("build_archetype")
        if isinstance(build, dict) and build.get("build_id") in accepted:
            return index
    return NOT_IN_RANKED_SET


def _mounted_equipment(legal_candidates: list[dict[str, Any]], mount_id: str) -> str | None:
    """The weapon id assigned to `mount_id` on the best (first) LEGAL
    candidate's own variant, if any real candidate exists."""
    if not legal_candidates:
        return None
    variant = legal_candidates[0].get("variant")
    if not isinstance(variant, dict):
        return None
    weapons_by_mount = variant.get("weapons_by_mount")
    if not isinstance(weapons_by_mount, dict):
        return None
    return weapons_by_mount.get(mount_id, "EMPTY_MOUNT")


def collect_build_observations(
    labels: tuple[CalibrationLabel, ...],
    scan: ScanResult,
    registry: Registry,
    heuristic_set: str,
) -> CalibrationRun:
    """Generate hash-bound observations for supported hull-level expectations:
    the best generated build (BUILD_EXPECTATION/NEGATIVE_EXPECTATION), its
    rank within the real generated candidate set (EXPECTED_TOP_SET), and a
    specific mount's assigned weapon (EQUIPMENT_EXPECTATION, using
    `CalibrationLabel.mount_id`).

    The global registry intentionally refuses ambiguous IDs.  Consequently a
    label for a source-qualified hull with a duplicated global ID is retained
    with its hash but no ``actual``/``actual_rank`` result; the evaluator
    will report it as ``UNSUPPORTED``.  This is fail-closed and prevents
    accidental cross-mod calibration.
    """
    observations: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, str]] = []
    supported_kinds = {
        CalibrationExpectationKind.BUILD_EXPECTATION,
        CalibrationExpectationKind.NEGATIVE_EXPECTATION,
        CalibrationExpectationKind.EXPECTED_TOP_SET,
        CalibrationExpectationKind.EQUIPMENT_EXPECTATION,
    }
    # Real reviewer fixtures commonly carry several labels for the same real
    # hull (e.g. two milestone-guide roles for one ship). Memoize the one
    # real generation call per entity_key: without this, a later label
    # sharing the same key -- even an unsupported-kind one that never
    # generates anything -- would silently overwrite (and lose) an earlier
    # label's already-computed ``actual`` in ``observations``, and every
    # label past the first would re-run generation for no reason.
    generated: dict[str, tuple[list[dict[str, Any]], str | None]] = {}
    for label in labels:
        hull = _source_hull(label, scan)
        if hull is None:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "entity_key_not_a_unique_local_hull"})
            continue
        if not hull.source_hash:
            # No verifiable local hash to bind an observation to -- never
            # fabricate one. Leaving no entry for this key means the
            # evaluator reports STALE, matching how a hash mismatch is
            # already handled below.
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "hull_has_no_local_source_hash"})
            continue
        entry = observations.setdefault(label.entity_key, {"entity_hash": hull.source_hash})
        if label.expectation_kind not in supported_kinds:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "expectation_kind_has_no_registered_runtime_observer"})
            continue
        if label.expectation_kind is CalibrationExpectationKind.EQUIPMENT_EXPECTATION and not label.mount_id:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "equipment_expectation_missing_mount_id"})
            continue
        if hull.id not in registry.hulls.by_id:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "hull_id_is_ambiguous_in_registry"})
            continue
        if label.entity_key not in generated:
            try:
                legal_candidates = _legal_candidates(api.run_generate(registry, heuristic_set, hull.id, "guided"))
                generated[label.entity_key] = (legal_candidates, None if legal_candidates else "no_legal_build_candidate")
            except (ValueError, KeyError) as exc:
                generated[label.entity_key] = ([], f"generation_failed:{type(exc).__name__}")
        legal_candidates, failure_reason = generated[label.entity_key]
        if not legal_candidates:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": failure_reason})
            continue
        if label.expectation_kind is CalibrationExpectationKind.EXPECTED_TOP_SET:
            accepted = set(label.expected_any) or {label.expected}
            entry["actual_rank"] = _build_rank(legal_candidates, accepted)
            diagnostics.append({"entity_key": label.entity_key, "status": "OBSERVED", "reason": "build_archetype_rank_in_generated_candidates"})
            continue
        if label.expectation_kind is CalibrationExpectationKind.EQUIPMENT_EXPECTATION:
            equipped = _mounted_equipment(legal_candidates, label.mount_id)  # type: ignore[arg-type]
            if equipped is None:
                diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "no_variant_on_best_candidate"})
                continue
            entry["actual"] = equipped
            diagnostics.append({"entity_key": label.entity_key, "status": "OBSERVED", "reason": "weapon_on_requested_mount_of_best_candidate"})
            continue
        actual = _build_actual(legal_candidates)
        if actual is None:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "no_legal_build_candidate"})
            continue
        entry["actual"] = actual
        diagnostics.append({"entity_key": label.entity_key, "status": "OBSERVED", "reason": "best_legal_build_archetype"})
    return CalibrationRun(observations, tuple(diagnostics))


def collect_faction_and_scenario_observations(
    labels: tuple[CalibrationLabel, ...],
    scan: ScanResult,
    registry: Registry,
    heuristic_set: str,
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> CalibrationRun:
    """Generate hash-bound observations for FACTION_EXPECTATION and
    SCENARIO_EXPECTATION labels (ROADMAP.md Phase 39 items 1/3), plus
    EXPECTED_TOP_SET/NEGATIVE_EXPECTATION labels that use either scheme.

    Reuses the real, already-audited Why-Not machinery
    (`explain_native_candidate`/`explain_scenario_candidate`, ROADMAP.md
    Phase 32/40) rather than re-deriving ranking logic of its own -- the
    same "read the real audited result, never reconstruct it" discipline
    every other Why-Not consumer in this codebase follows, and the same
    discipline `collect_build_observations` already follows for
    `api.run_generate`.

    entity_key conventions (separate from `collect_build_observations`'s
    `hull:<source_mod>:<hull_id>` build-level keys, so the two observers'
    ``observations`` dicts can be merged without collision -- see
    `collect_all_observations`):

    ``faction:<faction_id>:<role>:<source_mod>:<hull_id>``
        "should <hull_id> be recommended for <role> under <faction_id>?"
        Plain FACTION_EXPECTATION: `expected`/`expected_any` is
        ``"RECOMMENDED"`` or ``"NOT_RECOMMENDED"``. EXPECTED_TOP_SET:
        ranks against `WhyNotExplanation.rank` (1-based among every real
        known hull scoring above zero for this role).

    ``scenario:<faction_id>:<scenario_category>:<role>:<source_mod>:<hull_id>:<build_archetype_id>``
        "should this Hull + BuildArchetype be an INFERRED_SCENARIO_OPTION
        for <scenario_category>/<role>?" Same RECOMMENDED/NOT_RECOMMENDED
        or EXPECTED_TOP_SET conventions, against `explain_scenario_candidate`.

    Both hash-bind to the referenced hull's own `source_hash`, the same
    convention `collect_build_observations` uses: a rescan that changes
    only the faction's OTHER known hulls (not this specific hull) is not
    currently detected as stale by this hash alone -- a real, documented
    limitation, not a silent assumption of exactness.

    A label is UNSUPPORTED (never a fabricated MISMATCH) only when there is
    genuinely no real evidence to compare: an unresolved faction/hull, an
    unknown scenario category, or (native) the hull not a real known hull
    of this faction at all / (scenario) the build_archetype never inferred
    for this hull at all. A hull that IS a real candidate but scores zero,
    or a Hull+Build pair that IS real but was never shortlisted by any leg,
    is real negative evidence -- reported as NOT_RECOMMENDED / the
    EXPECTED_TOP_SET "not in ranked set" sentinel, eligible for a genuine
    MISMATCH, not silently treated as missing data.
    """
    observations: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, str]] = []
    confidences: dict[str, float] = {}
    gap_result_cache: dict[str, Any] = {}
    supported_kinds = {
        CalibrationExpectationKind.FACTION_EXPECTATION,
        CalibrationExpectationKind.SCENARIO_EXPECTATION,
        CalibrationExpectationKind.EXPECTED_TOP_SET,
        CalibrationExpectationKind.NEGATIVE_EXPECTATION,
    }

    for label in labels:
        faction_parts = _parse_prefixed_key(label.entity_key, "faction", 5)
        scenario_parts = None if faction_parts else _parse_prefixed_key(label.entity_key, "scenario", 7)
        if faction_parts is None and scenario_parts is None:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "entity_key_not_a_faction_or_scenario_key"})
            continue
        if label.expectation_kind not in supported_kinds:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "expectation_kind_has_no_registered_runtime_observer"})
            continue

        if faction_parts is not None:
            _, faction_id, role, source_mod, hull_id = faction_parts
            build_archetype_id = None
            scenario_value = None
        else:
            _, faction_id, scenario_value, role, source_mod, hull_id, build_archetype_id = scenario_parts  # type: ignore[misc]

        hull = _hull_by_source_and_id(scan, source_mod, hull_id)
        if hull is None:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "referenced_hull_not_a_unique_local_hull"})
            continue
        if not hull.source_hash:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "hull_has_no_local_source_hash"})
            continue
        entry = observations.setdefault(label.entity_key, {"entity_hash": hull.source_hash})

        faction = registry.resolve_faction(faction_id)
        if faction is None:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "faction_id_not_resolved"})
            continue
        if hull.id not in registry.hulls.by_id:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "hull_id_is_ambiguous_in_registry"})
            continue

        try:
            if faction_parts is not None:
                explanation = explain_native_candidate(faction, registry, role, hull.id, heuristic_set)
                has_evidence, rank, recommended, confidence = explanation.resolved, explanation.rank, explanation.recommended, explanation.confidence
            else:
                try:
                    scenario_enum = ScenarioCategory(scenario_value)
                except ValueError:
                    diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "unknown_scenario_category"})
                    continue
                if faction.id not in gap_result_cache:
                    gap_result_cache[faction.id] = recommend_gap_solutions(faction, registry, heuristic_set, knowledge_pack)
                gap_result = gap_result_cache[faction.id]
                explanation = explain_scenario_candidate(faction, registry, gap_result, scenario_enum, role, hull.id, build_archetype_id, heuristic_set)
                # `scenario_fit_score is None` only on the early-return path
                # (hull/build_archetype_id could not even be resolved) --
                # distinct from a real, computed `considered=False` (a real
                # Hull+Build pair simply never shortlisted by any leg),
                # which IS real negative evidence, not missing data.
                has_evidence, rank, recommended, confidence = explanation.scenario_fit_score is not None, explanation.rank, explanation.recommended, None
        except (ValueError, KeyError) as exc:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": f"recommendation_lookup_failed:{type(exc).__name__}"})
            continue

        if not has_evidence:
            diagnostics.append({"entity_key": label.entity_key, "status": "UNSUPPORTED", "reason": "hull_not_a_real_candidate_for_this_role"})
            continue
        if confidence is not None:
            confidences[label.entity_key] = confidence
        if label.expectation_kind is CalibrationExpectationKind.EXPECTED_TOP_SET:
            entry["actual_rank"] = rank if rank is not None else NOT_IN_RANKED_SET
        else:
            entry["actual"] = "RECOMMENDED" if recommended else "NOT_RECOMMENDED"
        diagnostics.append({"entity_key": label.entity_key, "status": "OBSERVED", "reason": "recommendation_audit_lookup"})

    return CalibrationRun(observations, tuple(diagnostics), confidences)


def collect_all_observations(
    labels: tuple[CalibrationLabel, ...],
    scan: ScanResult,
    registry: Registry,
    heuristic_set: str,
    knowledge_pack: ResolvedKnowledgePack | None = None,
) -> CalibrationRun:
    """Combine every registered runtime observer into one `CalibrationRun`.

    Each label is handled by exactly one observer, dispatched purely by its
    own entity_key prefix (`hull:` -> `collect_build_observations`;
    `faction:`/`scenario:` -> `collect_faction_and_scenario_observations`)
    -- the two observers' `observations` dicts never collide on a key, so
    merging them is safe. `diagnostics` are simply concatenated: a label
    only one observer recognizes will also carry a harmless
    "not this scheme" entry from the other, which is honest (each observer
    genuinely did not act on that label) rather than a real error.
    This function performs no ranking/comparison/generation of its own.
    """
    build_run = collect_build_observations(labels, scan, registry, heuristic_set)
    faction_scenario_run = collect_faction_and_scenario_observations(labels, scan, registry, heuristic_set, knowledge_pack)
    return CalibrationRun(
        {**build_run.observations, **faction_scenario_run.observations},
        (*build_run.diagnostics, *faction_scenario_run.diagnostics),
        {**build_run.confidences, **faction_scenario_run.confidences},
    )
