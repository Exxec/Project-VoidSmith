"""Independent verification of a written save copy (docs/SAVE_WORKSHOP_DESIGN.md, write pipeline step 5).

Nothing here trusts the writer: the original is re-hashed, the copy's campaign bytes are walked against the
planned spans with their own offset arithmetic, and the copy is re-read through the same qualified readers.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from .edit_plan import EditPlan
from .fingerprint import EXPECTED_FILE
from .format import _safe_path, inspect_save
from .locators import locate_resources


@dataclass(frozen=True)
class VerificationReport:
    status: str  # VERIFIED or FAILED
    original_unchanged: bool
    only_planned_spans_differ: bool
    copy_readable: bool
    changed: tuple[tuple[str, str, str], ...]  # target, original value, value re-read from the copy
    problems: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def file_hashes(folder: Path) -> dict[str, str]:
    """SHA-256 of every regular file in a flat save folder; anything else is reported by the caller."""
    result = {}
    for entry in sorted(folder.iterdir(), key=lambda p: p.name):
        digest = hashlib.sha256()
        with entry.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        result[entry.name] = digest.hexdigest()
    return result


def planned_spans(plan: EditPlan) -> list[tuple[int, int, bytes, str]]:
    """The byte spans that really change (a replacement equal to the original bytes is a no-op)."""
    spans = []
    for change in plan.changes:
        if change.locator is not None and change.replacement is not None and change.replacement != change.locator.original:
            spans.append((change.locator.start, change.locator.end, change.replacement.encode("ascii"), change.target))
    return sorted(spans)


def _spans_only(original: bytes, copy: bytes, spans: list[tuple[int, int, bytes, str]]) -> str | None:
    """Return a problem description, or None when the copy is the original with exactly these spans replaced."""
    position = 0  # offset in the original
    shift = 0     # copy offset minus original offset
    previous_end = 0
    for start, end, replacement, target in spans:
        if start < previous_end or end < start or end > len(original):
            return f"planned spans overlap or leave the file ({target})"
        if copy[position + shift:start + shift] != original[position:start]:
            return f"bytes outside the planned spans differ before {target}"
        if copy[start + shift:start + shift + len(replacement)] != replacement:
            return f"planned span for {target} does not hold the planned value"
        shift += len(replacement) - (end - start)
        position = previous_end = end
    if copy[position + shift:] != original[position:]:
        return "bytes after the last planned span differ"
    return None


def verify_copy(source_dir: Path, copy_dir: Path, plan: EditPlan, original_hashes: dict[str, str]) -> VerificationReport:
    problems: list[str] = []
    source = _safe_path(source_dir)
    copy = _safe_path(copy_dir)
    original_unchanged = file_hashes(source) == original_hashes
    if not original_unchanged:
        problems.append("The original save changed while the copy was written")
    source_names = sorted(p.name for p in source.iterdir())
    copy_names = sorted(p.name for p in copy.iterdir() if p.name != EXPECTED_FILE)  # the Workshop's own expectation file
    if source_names != copy_names:
        problems.append("The copy's file list differs from the original's")
    copy_hashes = file_hashes(copy)
    for name, digest in original_hashes.items():
        if name != "campaign.xml" and copy_hashes.get(name) != digest:
            problems.append(f"{name} differs from the original but no edit plans it")
    spans = planned_spans(plan)
    only_planned = False
    if "campaign.xml" in copy_hashes:
        problem = _spans_only((source / "campaign.xml").read_bytes(), (copy / "campaign.xml").read_bytes(), spans)
        only_planned = problem is None
        if problem:
            problems.append(problem)
    inspection = inspect_save(copy)
    snapshot = locate_resources(copy, inspection)
    copy_readable = snapshot.status == "READABLE"
    changed: list[tuple[str, str, str]] = []
    if not copy_readable:
        problems.append(f"The copy is not readable by the qualified readers ({snapshot.status})")
    else:
        original = {r.target: r.value for r in locate_resources(source, inspect_save(source)).resources}
        reread = {r.target: r.value for r in snapshot.resources}
        planned = {c.target: c for c in plan.changes if c.locator is not None and c.replacement is not None
                   and c.replacement != c.locator.original}
        for target, value in reread.items():
            if target in planned:
                changed.append((target, original.get(target, ""), value))
                if Decimal(value) != Decimal(planned[target].new_value):
                    problems.append(f"{target} re-reads as {value}, not the planned {planned[target].new_value}")
            elif original.get(target) != value:
                problems.append(f"{target} changed in the copy without a plan")
        if set(original) != set(reread):
            problems.append("The set of readable resources differs between the original and the copy")
        if snapshot.capacities != locate_resources(source, inspect_save(source)).capacities:
            problems.append("Saved capacity figures differ between the original and the copy")
    return VerificationReport("VERIFIED" if not problems else "FAILED", original_unchanged, only_planned,
                              copy_readable, tuple(changed), tuple(problems))
