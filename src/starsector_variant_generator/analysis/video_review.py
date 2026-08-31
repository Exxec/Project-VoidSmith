"""Ingest timestamped creator gameplay observations without treating them as mechanics.

Claims cannot affect legality or candidate scoring. Consumers must resolve a
conflict through the shared provenance precedence before presenting advice.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from starsector_variant_generator.core.evidence import EvidenceClass, EvidenceRecord
from starsector_variant_generator.core.registry import Registry

VIDEO_REVIEW_SCHEMA_NAME = "video_reviewer_calibration"


@dataclass(frozen=True)
class ControlSuitabilityEvidence:
    """A separate player/AI observed-gameplay claim for a future control layer."""

    hull_display_name: str
    player_suitability_claim: str | None
    ai_suitability_claim: str | None
    timestamp_range: str
    source: EvidenceRecord
    # A caller may set this only after resolving exactly one local hull.
    hull_id: str | None = None
    resolution_status: str = "UNRESOLVED"


def load_video_review_transcript(path: Path) -> tuple[ControlSuitabilityEvidence, ...]:
    """Load provisional ``VIDEO_REVIEW_TRANSCRIPT`` JSON evidence.

    Only explicit player/AI claims are emitted. Display names deliberately stay
    unresolved until a caller binds them to exactly one locally scanned hull.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_name") != VIDEO_REVIEW_SCHEMA_NAME:
        raise ValueError(f"Unsupported video review transcript: {path}")
    source = raw.get("source")
    if not isinstance(source, dict) or source.get("source_type") != EvidenceClass.VIDEO_REVIEW_TRANSCRIPT.value:
        raise ValueError("Video review source_type must be VIDEO_REVIEW_TRANSCRIPT")
    transcript_hash = source.get("transcript_sha256")
    records = raw.get("records")
    if not isinstance(transcript_hash, str) or not transcript_hash or not isinstance(records, list):
        raise ValueError("Video review transcript requires transcript_sha256 and records")
    normalized: list[ControlSuitabilityEvidence] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("Video review record must be an object")
        display, timestamp = record.get("ship_display"), record.get("timestamp_range")
        if not isinstance(display, str) or not display or not isinstance(timestamp, str) or not timestamp:
            raise ValueError("Video review record requires ship_display and timestamp_range")
        player = _explicit_claim(record.get("player_suitability_claim"))
        ai = _explicit_claim(record.get("ai_suitability_claim"))
        if player is None and ai is None:
            continue
        normalized.append(ControlSuitabilityEvidence(
            hull_display_name=display, player_suitability_claim=player, ai_suitability_claim=ai, timestamp_range=timestamp,
            source=EvidenceRecord(
                evidence_id=f"video-review:{transcript_hash}:{index}", entity_id=display, source_file=str(path),
                source_class=str(source.get("creator") or "VIDEO_CREATOR"), source_line_or_symbol=timestamp,
                evidence_type="CONTROL_SUITABILITY_OBSERVED_GAMEPLAY", extracted_value={"player": player, "ai": ai},
                confidence=0.5, parser_or_adapter="video_review_transcript_loader",
                evidence_class=EvidenceClass.VIDEO_REVIEW_TRANSCRIPT,
            ),
        ))
    return tuple(normalized)


def _explicit_claim(value: object) -> str | None:
    return value if isinstance(value, str) and value and value != "UNKNOWN" else None


def resolve_control_suitability_evidence(
    evidence: tuple[ControlSuitabilityEvidence, ...], registry: Registry,
) -> tuple[ControlSuitabilityEvidence, ...]:
    """Bind only exact, unique local display-name matches.

    A fuzzy match would turn third-party commentary into an assertion about the
    wrong hull.  Unmatched and duplicate local names therefore remain explicit
    review work instead of being guessed at.
    """
    by_name: dict[str, list[str]] = {}
    for hull in registry.hulls.by_id.values():
        if hull.name:
            by_name.setdefault(hull.name.casefold(), []).append(hull.id)
    resolved: list[ControlSuitabilityEvidence] = []
    for item in evidence:
        matches = sorted(by_name.get(item.hull_display_name.casefold(), ()))
        if len(matches) == 1:
            resolved.append(ControlSuitabilityEvidence(
                hull_display_name=item.hull_display_name,
                player_suitability_claim=item.player_suitability_claim,
                ai_suitability_claim=item.ai_suitability_claim,
                timestamp_range=item.timestamp_range,
                source=item.source,
                hull_id=matches[0],
                resolution_status="RESOLVED_EXACT_LOCAL_NAME",
            ))
        else:
            resolved.append(ControlSuitabilityEvidence(
                hull_display_name=item.hull_display_name,
                player_suitability_claim=item.player_suitability_claim,
                ai_suitability_claim=item.ai_suitability_claim,
                timestamp_range=item.timestamp_range,
                source=item.source,
                resolution_status="UNRESOLVED_NO_LOCAL_MATCH" if not matches else "UNRESOLVED_AMBIGUOUS_LOCAL_NAME",
            ))
    return tuple(resolved)
