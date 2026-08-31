"""Explicit local recommendation feedback; never an automatic ranking input."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


FEEDBACK_SCHEMA_VERSION = "voidsmith-recommendation-feedback-0.1"


class FeedbackKind(StrEnum):
    KEEP = "KEEP"
    DISLIKE = "DISLIKE"
    TOO_FLUX_HUNGRY = "TOO_FLUX_HUNGRY"
    TOO_FRAGILE = "TOO_FRAGILE"
    TOO_SHORT_RANGE = "TOO_SHORT_RANGE"
    TOO_SLOW = "TOO_SLOW"
    AI_BAD = "AI_BAD"
    PLAYER_ONLY = "PLAYER_ONLY"


@dataclass(frozen=True)
class RecommendationFeedback:
    feedback: FeedbackKind
    recommendation_id: str
    hull_id: str
    source_mod_id: str | None = None
    note: str | None = None
    recorded_at: str = ""


def append_feedback(output_dir: Path, entry: RecommendationFeedback) -> Path:
    """Append one bounded feedback record below the caller's output root."""
    if not entry.recommendation_id or not entry.hull_id:
        raise ValueError("Feedback requires a recommendation id and hull id")
    if entry.note is not None and len(entry.note) > 2000:
        raise ValueError("Feedback note exceeds 2000 characters")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = (output_dir / "recommendation-feedback.json").resolve()
    if path.parent != output_dir:
        raise ValueError("Feedback path escaped the configured output directory")
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != FEEDBACK_SCHEMA_VERSION or not isinstance(raw.get("entries"), list):
            raise ValueError("Existing feedback file has an unsupported schema")
        entries = raw["entries"]
    else:
        entries = []
    data = asdict(entry)
    data["feedback"] = entry.feedback.value
    if not data["recorded_at"]:
        data["recorded_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    entries.append(data)
    path.write_text(json.dumps({"schema_version": FEEDBACK_SCHEMA_VERSION, "entries": entries, "policy": "Review material only; never auto-applied to legality, ranking, or heuristics."}, indent=2, sort_keys=True), encoding="utf-8")
    return path
