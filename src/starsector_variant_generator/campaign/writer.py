"""Write one new, verified copy of a save with only planned byte spans changed.

Contract (docs/SAVE_WORKSHOP_DESIGN.md, write pipeline): the original is hashed and never modified, the copy goes
to a new directory below the configured output directory (never overwriting), and the copy is re-read and
verified; any failure removes the copy. Only changes the plan ACCEPTED within the saved capacity are written:
an over-capacity or unprovable change is refused even when the plan carries the capacity opt-in.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

from starsector_variant_generator.core.safeio import UnsafePathError, safe_rmtree

from .edit_plan import SAVE_WRITE_GATE, EditPlan
from .format import MAX_CAMPAIGN_BYTES, _safe_path, inspect_save
from .verify import VerificationReport, file_hashes, planned_spans, verify_copy

OUTPUT_SUBDIRECTORY = "save_workshop"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
NOT_LOADED_NOTICE = ("The copy has NOT been loaded in the game. A successful re-read is not proof that the game accepts "
                     "it: move it into the saves folder yourself and try it on a throwaway first. The copy keeps the original's "
                     "character and slot identity, and the game saves to the folder for that identity (observed 2026-10-06), so "
                     "loading the copy and saving can overwrite the original save: keep a backup of the original first.")


@dataclass(frozen=True)
class SaveWriteResult:
    status: str  # WRITTEN, REFUSED, FAILED_VERIFICATION or FAILED
    reason: str
    copy_dir: str | None
    verification: VerificationReport | None
    notes: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def _refused(reason: str) -> SaveWriteResult:
    return SaveWriteResult("REFUSED", reason, None, None, ("No files written.",))


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def default_copy_name(plan: EditPlan) -> str:
    """Deterministic name: source folder name plus a short digest of the source hashes and planned values."""
    digest = hashlib.sha256()
    for name, value in plan.source_hashes:
        digest.update(f"{name}={value};".encode())
    for change in plan.changes:
        digest.update(f"{change.target}={change.new_value};".encode())
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(plan.source_dir).name)[:90].lstrip("._-") or "save"
    return f"{base}_voidsmith_{digest.hexdigest()[:10]}"


def _output_target(output_dir: Path, name: str, source: Path) -> Path:
    if ".." in Path(output_dir).parts:
        raise ValueError("Parent traversal is refused in the output directory")
    root = Path(os.path.abspath(output_dir))
    for part in (*reversed(root.parents), root):
        if part.exists() and _is_link(part.lstat()):
            raise ValueError("Links and reparse points are refused in the output directory")
    if root == source or source in root.parents or root in source.parents:
        raise ValueError("The output directory must be separate from the selected save and its parents")
    if not _NAME.fullmatch(name):
        raise ValueError("Copy name must be 1-120 characters of letters, digits, '_', '.' or '-'")
    return root / OUTPUT_SUBDIRECTORY / name


def _discard_copy(target: Path) -> None:
    """Remove a copy this run created; never raises, never follows a link, only deletes inside the output directory."""
    try:
        safe_rmtree(target, [target.parent])
    except (OSError, UnsafePathError):
        pass


def write_save_copy(plan: EditPlan, output_dir: Path, *, name: str | None = None) -> SaveWriteResult:
    if plan.write_gate_status != SAVE_WRITE_GATE.status:
        return _refused(f"Write gate is {plan.write_gate_status}, not {SAVE_WRITE_GATE.status}")
    if not plan.changes:
        return _refused("The plan has no changes")
    for change in plan.changes:
        if change.outcome != "ACCEPTED":
            extra = " Over-capacity writes are not enabled even with the plan's capacity opt-in." if change.outcome == "NOT_DETERMINABLE" else ""
            return _refused(f"{change.target} is {change.outcome}: {change.reason}.{extra}")
        if change.locator is None or change.replacement is None:
            return _refused(f"{change.target} has no exact locator or replacement")
    spans = planned_spans(plan)
    if not spans:
        return _refused("Every requested value already equals the saved value; there is nothing to write")
    try:
        source = _safe_path(Path(plan.source_dir))
        target = _output_target(output_dir, default_copy_name(plan) if name is None else name, source)
    except ValueError as exc:
        return _refused(str(exc))
    except OSError:
        return _refused("The selected save or output directory is not accessible")
    inspection = inspect_save(source)
    if inspection.status != "READABLE" or inspection.source_hashes != plan.source_hashes:
        return _refused(f"SOURCE_CHANGED: the save is {inspection.status} or no longer matches the plan's hashes")
    entries = sorted(source.iterdir(), key=lambda p: p.name)
    if any(not entry.is_file() or _is_link(entry.lstat()) for entry in entries):
        return _refused("The save folder holds a subfolder, link or unusual entry; only flat folders are qualified")
    campaign = source / "campaign.xml"
    if campaign.stat().st_size > MAX_CAMPAIGN_BYTES:
        return _refused("campaign.xml exceeds the documented size limit")
    raw = campaign.read_bytes()
    if hashlib.sha256(raw).hexdigest() != dict(plan.source_hashes)["campaign.xml"]:
        return _refused("SOURCE_CHANGED: campaign.xml changed after planning")
    for start, end, _replacement, change_target in spans:
        located = next(c.locator for c in plan.changes if c.target == change_target)
        if located is None or raw[start:end].decode("ascii", "replace") != located.original:
            return _refused(f"The bytes at the planned span for {change_target} are not the located value")
    original_hashes = file_hashes(source)
    patched = bytearray(raw)
    previous = len(raw)
    for start, end, replacement, change_target in reversed(spans):
        if end > previous:
            return _refused(f"Planned spans overlap ({change_target})")
        patched[start:end] = replacement
        previous = start
    parent = target.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if _is_link(parent.lstat()):
            return _refused("Links and reparse points are refused in the output directory")
        target.mkdir()
    except FileExistsError:
        return _refused(f"The target already exists and is never overwritten: {target}")
    except OSError as exc:
        return _refused(f"The output directory could not be prepared: {exc}")
    try:
        for entry in entries:
            with (target / entry.name).open("xb") as out:
                if entry.name == "campaign.xml":
                    out.write(patched)
                else:
                    with entry.open("rb") as stream:
                        shutil.copyfileobj(stream, out)
        report = verify_copy(source, target, plan, original_hashes)
    except Exception as exc:  # noqa: BLE001 - any failure must remove the copy; the original is never touched
        _discard_copy(target)
        return SaveWriteResult("FAILED", f"{type(exc).__name__}: {exc}", None, None,
                               ("The partial copy was removed.", "The original save was not modified."))
    if report.status != "VERIFIED":
        _discard_copy(target)
        return SaveWriteResult("FAILED_VERIFICATION", "; ".join(report.problems), None, report,
                               ("The copy was removed.", "The original save was not modified."))
    return SaveWriteResult("WRITTEN", "Verified copy written", str(target), report,
                           (NOT_LOADED_NOTICE, "Saved capacity figures are not runtime-verified; overage effects stay UNKNOWN.",
                            "The original save was hashed before and after and is unchanged."))
