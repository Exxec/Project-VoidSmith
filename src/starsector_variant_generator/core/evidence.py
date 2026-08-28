"""Shared, serializable provenance and uncertainty vocabulary."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EvidenceClass(StrEnum):
    """How a fact was obtained, distinct from whether it is available."""

    DIRECT_DATA = "DIRECT_DATA"
    LOCAL_SOURCE_CODE = "LOCAL_SOURCE_CODE"
    LOCAL_CONFIG = "LOCAL_CONFIG"
    ADAPTER_MODELED = "ADAPTER_MODELED"
    # A timestamped claim from a creator describing observed play. It is
    # advisory evidence, never a mechanical fact or a legality input.
    VIDEO_REVIEW_TRANSCRIPT = "VIDEO_REVIEW_TRANSCRIPT"
    CURATED_GUIDANCE = "CURATED_GUIDANCE"
    REVIEWER_EXPECTATION = "REVIEWER_EXPECTATION"
    GENERIC_UNSOURCED_GUIDANCE = "GENERIC_UNSOURCED_GUIDANCE"
    INFERRED_MECHANICS = "INFERRED_MECHANICS"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


# Provenance precedence only. It neither computes quality nor changes
# validation: local mechanical evidence wins over observed-gameplay transcript
# claims, which in turn win over generic guidance with no source.
_PRECEDENCE: dict[EvidenceClass, int] = {
    EvidenceClass.DIRECT_DATA: 700,
    EvidenceClass.LOCAL_SOURCE_CODE: 690,
    EvidenceClass.LOCAL_CONFIG: 680,
    EvidenceClass.ADAPTER_MODELED: 670,
    EvidenceClass.INFERRED_MECHANICS: 660,
    EvidenceClass.VIDEO_REVIEW_TRANSCRIPT: 500,
    EvidenceClass.CURATED_GUIDANCE: 400,
    EvidenceClass.REVIEWER_EXPECTATION: 300,
    EvidenceClass.GENERIC_UNSOURCED_GUIDANCE: 100,
    EvidenceClass.UNKNOWN: 0,
    EvidenceClass.CONFLICTING: 0,
}


def evidence_precedence(evidence_class: EvidenceClass) -> int:
    """Return non-legality provenance precedence for conflict resolution."""
    return _PRECEDENCE[evidence_class]

@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    entity_id: str
    source_file: str | None
    source_class: str | None
    source_line_or_symbol: str | None
    evidence_type: str
    extracted_value: Any
    confidence: float
    parser_or_adapter: str
    evidence_class: EvidenceClass = EvidenceClass.UNKNOWN
