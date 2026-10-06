from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class FactStatus(str, Enum):
    PARSED = "PARSED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CampaignFact:
    name: str
    value: str | None
    status: FactStatus
    evidence: str


@dataclass(frozen=True)
class SaveInspection:
    schema_version: str
    status: str
    facts: tuple[CampaignFact, ...]
    source_hashes: tuple[tuple[str, str], ...]
    notes: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
