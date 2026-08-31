"""Portable reviewer-label calibration records for deterministic outputs.

Fixtures deliberately contain only entity fingerprints and reviewer labels, not
copied Starsector/mod records.  They measure whether a generated observation
agrees with a locally reviewed expectation; they never adjust heuristics by
themselves.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from starsector_variant_generator.core.evidence import EvidenceClass

CALIBRATION_SCHEMA_VERSION = "calibration-labels-0.1"


class CalibrationStrength(StrEnum):
    HARD_EXPECTATION = "HARD_EXPECTATION"
    SOFT_EXPECTATION = "SOFT_EXPECTATION"
    OBSERVATION = "OBSERVATION"


class CalibrationExpectationKind(StrEnum):
    BUILD_EXPECTATION = "BUILD_EXPECTATION"
    EQUIPMENT_EXPECTATION = "EQUIPMENT_EXPECTATION"
    FACTION_EXPECTATION = "FACTION_EXPECTATION"
    SCENARIO_EXPECTATION = "SCENARIO_EXPECTATION"
    NEGATIVE_EXPECTATION = "NEGATIVE_EXPECTATION"
    # ROADMAP.md Phase 39: "this candidate should rank among the top N real
    # results" rather than require one exact match. Additive -- every prior
    # kind's comparison rule (including NEGATIVE_EXPECTATION's forbidden-set
    # rule) is unchanged; only this kind reads `top_n`/`actual_rank` instead
    # of `expected`/`expected_any`/`actual`. See `evaluate_calibration`.
    EXPECTED_TOP_SET = "EXPECTED_TOP_SET"


@dataclass(frozen=True)
class CalibrationLabel:
    entity_key: str
    entity_hash: str
    label: str
    expected: str
    expectation_kind: CalibrationExpectationKind = CalibrationExpectationKind.BUILD_EXPECTATION
    expected_any: tuple[str, ...] = ()
    # EXPECTED_TOP_SET only: the candidate identified by `expected`/
    # `expected_any` must rank at or better than this 1-based position among
    # the real candidates an observer actually searched/ranked. Ignored by
    # every other expectation kind.
    top_n: int = 3
    # EQUIPMENT_EXPECTATION only: which mount's assigned weapon a runtime
    # observer should read (e.g. a `weapons_by_mount` key on a generated
    # variant). Ignored by every other expectation kind.
    mount_id: str | None = None
    strength: CalibrationStrength = CalibrationStrength.HARD_EXPECTATION
    note: str | None = None
    evidence_class: EvidenceClass = EvidenceClass.REVIEWER_EXPECTATION


@dataclass(frozen=True)
class CalibrationReport:
    schema_version: str
    fixture_id: str
    heuristic_set: str
    evaluated: int
    matched: int
    mismatched: int
    stale: int
    unsupported: int
    results: tuple[dict[str, object], ...]


def load_calibration_labels(path: Path) -> tuple[str, tuple[CalibrationLabel, ...]]:
    """Load a neutral local fixture, rejecting incomplete or unknown schemas."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise ValueError(f"Unsupported calibration fixture: {path}")
    fixture_id = raw.get("fixture_id")
    labels = raw.get("labels")
    if not isinstance(fixture_id, str) or not fixture_id or not isinstance(labels, list):
        raise ValueError("Calibration fixture requires fixture_id and labels")
    normalized: list[CalibrationLabel] = []
    for entry in labels:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) and entry[key] for key in ("entity_key", "entity_hash", "label", "expected")):
            raise ValueError("Each calibration label requires entity_key, entity_hash, label, and expected")
        expected_any = entry.get("expected_any", [])
        if not isinstance(expected_any, list) or not all(isinstance(item, str) and item for item in expected_any):
            raise ValueError("expected_any must be an array of non-empty strings")
        strength = entry.get("strength", CalibrationStrength.HARD_EXPECTATION)
        try: strength = CalibrationStrength(strength)
        except ValueError as exc: raise ValueError("Unknown calibration strength") from exc
        kind = entry.get("expectation_kind", CalibrationExpectationKind.BUILD_EXPECTATION)
        try: kind = CalibrationExpectationKind(kind)
        except ValueError as exc: raise ValueError("Unknown calibration expectation kind") from exc
        note = entry.get("note")
        if note is not None and not isinstance(note, str):
            raise ValueError("Calibration note must be text when supplied")
        top_n = entry.get("top_n", 3)
        if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
            raise ValueError("top_n must be a positive integer when supplied")
        mount_id = entry.get("mount_id")
        if mount_id is not None and not (isinstance(mount_id, str) and mount_id):
            raise ValueError("mount_id must be non-empty text when supplied")
        normalized.append(CalibrationLabel(
            entity_key=entry["entity_key"], entity_hash=entry["entity_hash"], label=entry["label"], expected=entry["expected"],
            expectation_kind=kind, expected_any=tuple(expected_any), top_n=top_n, mount_id=mount_id, strength=strength, note=note,
        ))
    return fixture_id, tuple(normalized)


def evaluate_calibration(
    fixture_id: str,
    labels: tuple[CalibrationLabel, ...],
    observations: dict[str, dict[str, Any]],
    heuristic_set: str,
) -> CalibrationReport:
    """Compare labels with caller-supplied normalized observations.

    An observation must provide the source hash used for review and may provide
    an ``actual`` value. Missing actual values are ``UNSUPPORTED``; a changed
    hash is ``STALE``. Neither is counted as a heuristic mismatch.
    """
    results: list[dict[str, object]] = []
    matched = mismatched = stale = unsupported = 0
    for label in labels:
        observation = observations.get(label.entity_key)
        top_set = label.expectation_kind is CalibrationExpectationKind.EXPECTED_TOP_SET
        if observation is None or observation.get("entity_hash") != label.entity_hash:
            status = "STALE"; stale += 1; actual = None
        elif top_set:
            # A rank-based comparison, not an exact-value one: the observer
            # supplies `actual_rank` (1-based position among the real
            # candidates it actually searched/ranked; a sentinel value
            # larger than any realistic `top_n` when the expected candidate
            # never appeared at all). Missing entirely means the observer
            # itself produced no ranking data -- UNSUPPORTED, same
            # "missing actual is not a false failure" rule every other kind
            # already follows.
            if "actual_rank" not in observation:
                status = "UNSUPPORTED"; unsupported += 1; actual = None
            else:
                rank = observation["actual_rank"]
                accepted = isinstance(rank, int) and not isinstance(rank, bool) and 1 <= rank <= label.top_n
                status = "MATCH" if accepted else "MISMATCH"
                actual = f"rank_{rank}"
                if status == "MATCH": matched += 1
                else: mismatched += 1
        elif "actual" not in observation:
            status = "UNSUPPORTED"; unsupported += 1; actual = None
        else:
            actual = str(observation["actual"])
            expected_values = set(label.expected_any) or {label.expected}
            accepted = actual not in expected_values if label.expectation_kind is CalibrationExpectationKind.NEGATIVE_EXPECTATION else actual in expected_values
            status = "MATCH" if accepted else "MISMATCH"
            if status == "MATCH": matched += 1
            else: mismatched += 1
        results.append({"entity_key": label.entity_key, "label": label.label, "expectation_kind": label.expectation_kind, "expected": label.expected, "expected_any": label.expected_any, "top_n": label.top_n if top_set else None, "strength": label.strength, "actual": actual, "status": status, "note": label.note})
    return CalibrationReport(CALIBRATION_SCHEMA_VERSION, fixture_id, heuristic_set, len(labels), matched, mismatched, stale, unsupported, tuple(results))


def confidence_weighted_summary(report: CalibrationReport, confidences: dict[str, float]) -> dict[str, object]:
    """Report MISMATCH severity weighted by the underlying recommendation's
    own confidence -- REPORTING nuance only (ROADMAP.md Phase 39 item 5).

    ``confidences`` is caller-supplied, keyed by ``entity_key`` (e.g. read
    from a real ``WhyNotExplanation.confidence``/``RetrofitWhyNotExplanation
    .confidence``/``AcquisitionWhyNotExplanation.confidence`` a runtime
    observer already computed -- see
    ``calibration_runner.collect_faction_and_scenario_observations``). This
    function never derives a confidence value itself, never changes
    ``report``'s own MATCH/MISMATCH classification, and never reads or
    writes ``core/heuristics.py``: it only buckets already-computed
    MISMATCH entries by an already-computed confidence so a reviewer can
    tell "the engine disagreed here, but was already reporting itself as
    unsure" apart from "the engine disagreed here while fully confident" --
    a low-confidence disagreement is *reported* as less concerning, nothing
    more. A MISMATCH with no supplied confidence is never assigned a
    fabricated default; it is reported separately as unknown.
    """
    entries: list[dict[str, object]] = []
    known: list[float] = []
    for result in report.results:
        if result["status"] != "MISMATCH":
            continue
        confidence = confidences.get(str(result["entity_key"]))
        if confidence is None:
            bucket = "UNKNOWN_CONFIDENCE_MISMATCH"
        else:
            known.append(confidence)
            if confidence >= 0.66:
                bucket = "HIGH_CONFIDENCE_MISMATCH"
            elif confidence >= 0.33:
                bucket = "MEDIUM_CONFIDENCE_MISMATCH"
            else:
                bucket = "LOW_CONFIDENCE_MISMATCH"
        entries.append({"entity_key": result["entity_key"], "label": result["label"], "confidence": confidence, "bucket": bucket})
    counts_by_bucket = {name: sum(1 for entry in entries if entry["bucket"] == name) for name in ("HIGH_CONFIDENCE_MISMATCH", "MEDIUM_CONFIDENCE_MISMATCH", "LOW_CONFIDENCE_MISMATCH", "UNKNOWN_CONFIDENCE_MISMATCH")}
    return {
        "fixture_id": report.fixture_id,
        "heuristic_set": report.heuristic_set,
        "total_mismatches": len(entries),
        "mean_confidence_of_mismatches": (sum(known) / len(known)) if known else None,
        "counts_by_bucket": counts_by_bucket,
        "entries": tuple(entries),
    }


def compare_calibration_reports(report_a: CalibrationReport, report_b: CalibrationReport) -> dict[str, object]:
    """Diff two ``CalibrationReport``s produced from the SAME fixture --
    normally the same real reviewer labels evaluated under two different,
    already-existing, human-authored heuristic sets (ROADMAP.md Phase 39
    item 5, "per-heuristic before/after comparison"). This is a pure
    regression/reporting diff: it never selects a "better" heuristic set,
    never blends the two, and never writes anything -- it only reports
    where two already-computed evaluations disagree, for a human to read
    and, if they judge it warranted, act on separately by authoring a new
    named heuristic set themselves.
    """
    if report_a.fixture_id != report_b.fixture_id:
        raise ValueError("Reports must be for the same fixture_id to compare")
    by_key_a = {str(result["entity_key"]): result for result in report_a.results}
    by_key_b = {str(result["entity_key"]): result for result in report_b.results}
    changed: list[dict[str, object]] = []
    for key in sorted(set(by_key_a) | set(by_key_b)):
        entry_a, entry_b = by_key_a.get(key), by_key_b.get(key)
        status_a = entry_a["status"] if entry_a else None
        status_b = entry_b["status"] if entry_b else None
        if status_a != status_b:
            # At least one entry exists whenever the two statuses differ:
            # both being absent means both statuses are `None`, which the
            # `!=` check above already excludes.
            label_source = entry_a or entry_b
            assert label_source is not None
            changed.append({"entity_key": key, "label": label_source["label"], "status_a": status_a, "status_b": status_b})
    return {
        "fixture_id": report_a.fixture_id,
        "heuristic_set_a": report_a.heuristic_set,
        "heuristic_set_b": report_b.heuristic_set,
        "counts_a": {"matched": report_a.matched, "mismatched": report_a.mismatched, "stale": report_a.stale, "unsupported": report_a.unsupported},
        "counts_b": {"matched": report_b.matched, "mismatched": report_b.mismatched, "stale": report_b.stale, "unsupported": report_b.unsupported},
        "changed_labels": tuple(changed),
        "matches_gained_by_b": tuple(entry for entry in changed if entry["status_b"] == "MATCH" and entry["status_a"] != "MATCH"),
        "matches_lost_by_b": tuple(entry for entry in changed if entry["status_a"] == "MATCH" and entry["status_b"] != "MATCH"),
    }
