"""Pure, immutable edit-plan records, independent of fit legality."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .locators import ValueLocator


@dataclass(frozen=True)
class EditRequest:
    target: str
    value: int


@dataclass(frozen=True)
class PlannedChange:
    target: str
    old_value: str | None
    new_value: int
    replacement: str | None
    locator: ValueLocator | None
    outcome: str
    reason: str
    capacity_opt_in: bool = False


@dataclass(frozen=True)
class EditPlan:
    schema_version: str
    source_dir: str
    source_hashes: tuple[tuple[str, str], ...]
    catalog_evidence: tuple[tuple[str, str], ...]
    changes: tuple[PlannedChange, ...]
    ready_for_copy: bool
    write_gate_status: str
    notes: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SaveWriteGate:
    # Owner decision 2026-10-06: copies are written only for changes that stay within the saved
    # capacity. Over-capacity or unprovable changes remain NOT_DETERMINABLE and are never written;
    # overage consequences stay UNKNOWN until controlled evidence is recorded.
    status: str = "OPEN_WITHIN_CAPACITY"
    reason: str = ("OPEN_WITHIN_CAPACITY: a new copy is written only for ACCEPTED changes that stay within the saved "
                   "capacity; over-capacity or unprovable changes are refused and overage effects remain UNKNOWN.")


SAVE_WRITE_GATE = SaveWriteGate()
