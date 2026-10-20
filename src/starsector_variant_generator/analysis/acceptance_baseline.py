"""Mod acceptance with a baseline, progress lines and a resumable checkpoint (docs/AUTOMATION_PLAN.md V1.2).

Wraps `analysis/mod_acceptance.audit_mod_acceptance` (the classification rules live there and are unchanged): mods are audited in
small chunks so each finished mod can be reported as it completes and an interrupted run resumes from a `*.partial.jsonl`
checkpoint whose header names the inputs (a different scan starts over). The per-mod verdict (classification plus the codes of its
findings) is compared with a baseline file written by a person's explicit `--write-baseline`; only changes are reported.

Classification is a diagnostic sweep, never legality (`validation/legality.py` stays the sole legality source).
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from starsector_variant_generator.analysis.complex_hull_audit import audit_complex_hulls
from starsector_variant_generator.analysis.mod_acceptance import (
    FAIL,
    PARTIAL,
    PASS,
    PASS_WITH_UNKNOWNS,
    audit_mod_acceptance,
)
from starsector_variant_generator.core.models import ScanResult, SourceType
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.safeio import atomic_write_json, safe_unlink

BASELINE_SCHEMA = "acceptance-baseline-0.1"
CHECKPOINT_SCHEMA = "acceptance-checkpoint-0.1"
DEFAULT_CHUNK_SIZE = 8
_RANK = {PASS: 0, PASS_WITH_UNKNOWNS: 1, PARTIAL: 2, FAIL: 3}
# Codes that are informational by design; their appearing or vanishing is a change but never a regression.
_INFO_CODES = frozenset({"UNKNOWN_HULLMOD_EFFECTS", "ADAPTER_MODELED_HULLMODS_USED"})

ProgressCallback = Callable[[int, int, str, str, float], None]


def inputs_fingerprint(scan: ScanResult, scope: str) -> dict[str, Any]:
    mods = sorted((mod.mod_id, mod.version or "", mod.path.name) for mod in scan.mods)
    digest = hashlib.sha256(json.dumps(mods, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "schema": CHECKPOINT_SCHEMA, "scope": scope, "mods_sha256": digest,
        "counts": {kind: len(getattr(scan, kind)) for kind in ("hulls", "weapons", "fighters", "hullmods", "variants", "factions")},
        "errors": len(scan.errors), "skipped": len(scan.skipped_entities),
    }


def verdict(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": record["mod_name"], "version": record["version"], "classification": record["classification"],
        "codes": sorted({finding["code"] for finding in record["findings"]}),
    }


def _load_checkpoint(path: Path, header: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Records already finished by an earlier run over the same inputs (empty when absent, stale or unreadable)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or json.loads(lines[0]) != header:
            return {}
        done: dict[str, dict[str, Any]] = {}
        for line in lines[1:]:
            entry = json.loads(line)
            for record in entry["records"]:
                done[record["mod_id"]] = record
        return done
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _append_checkpoint(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps({"records": records}, sort_keys=True, default=str) + "\n")
        out.flush()


def run_acceptance(
    scan: ScanResult, registry: Registry, *, scope: str = "ENABLED_ONLY", chunk_size: int = DEFAULT_CHUNK_SIZE,
    checkpoint_path: Path | None = None, progress: ProgressCallback | None = None, enabled_file: str | None = None,
) -> dict[str, Any]:
    """Audit every mod chunk by chunk; returns the audit dict (same shape as `audit_mod_acceptance`) with `resumed_mods` added."""
    header = inputs_fingerprint(scan, scope)
    done: dict[str, dict[str, Any]] = {}
    if checkpoint_path is not None:
        done = _load_checkpoint(checkpoint_path, header)
        if not done:
            atomic_write_json(checkpoint_path, header, indent=None)
            with checkpoint_path.open("a", encoding="utf-8", newline="\n") as out:
                out.write("\n")
    mod_ids = sorted((mod.mod_id for mod in scan.mods if mod.source_type is SourceType.MOD), key=str.lower)
    complex_audit = audit_complex_hulls(scan, registry)
    resumed = [mod_id for mod_id in mod_ids if mod_id in done]
    pending = [mod_id for mod_id in mod_ids if mod_id not in done]
    total = len(mod_ids)
    finished = len(resumed)
    for start in range(0, len(pending), max(1, chunk_size)):
        chunk = pending[start:start + max(1, chunk_size)]
        began = time.perf_counter()
        part = audit_mod_acceptance(scan, registry, only_mod_ids=frozenset(chunk), complex_audit=complex_audit, include_synthetic=False)
        seconds = (time.perf_counter() - began) / len(chunk)
        for record in part["records"]:
            done[record["mod_id"]] = record
            finished += 1
            if progress is not None:
                progress(finished, total, record["mod_id"], record["classification"], seconds)
        if checkpoint_path is not None:
            _append_checkpoint(checkpoint_path, part["records"])
    final = audit_mod_acceptance(scan, registry, only_mod_ids=frozenset(), complex_audit=complex_audit, enabled_file=enabled_file)
    records = sorted([*done.values(), *final["records"]], key=lambda record: record["mod_id"].lower())
    summary = {name: 0 for name in (PASS, PASS_WITH_UNKNOWNS, PARTIAL, FAIL)}
    for record in records:
        summary[record["classification"]] += 1
    audit = {**final, "records": records, "summary": {"mods_classified": len(records), "by_classification": summary},
             "resumed_mods": resumed, "scan_scope": scope}
    if checkpoint_path is not None:
        safe_unlink(checkpoint_path, [checkpoint_path.parent])
    return audit


def baseline_from_audit(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": BASELINE_SCHEMA, "scope": audit.get("scan_scope"),
        "mods": {record["mod_id"]: verdict(record) for record in audit["records"]},
    }


def load_baseline(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f"Baseline {path} is unreadable: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != BASELINE_SCHEMA or not isinstance(data.get("mods"), dict):
        raise ValueError(f"Baseline {path} is not a {BASELINE_SCHEMA} file.")
    return data


def compare_with_baseline(baseline: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    """Changes only, sorted by mod id. `regression` is true when a mod got worse or gained a non-informational code."""
    old, new = baseline["mods"], current["mods"]
    changes: list[dict[str, Any]] = []
    for mod_id in sorted(set(old) | set(new), key=str.lower):
        before, after = old.get(mod_id), new.get(mod_id)
        if before is None:
            changes.append({"mod_id": mod_id, "change": "ADDED", "to": after["classification"], "codes_added": after["codes"], "regression": after["classification"] in (PARTIAL, FAIL)})
        elif after is None:
            changes.append({"mod_id": mod_id, "change": "REMOVED", "from": before["classification"], "regression": False})
        else:
            added = sorted(set(after["codes"]) - set(before["codes"]))
            removed = sorted(set(before["codes"]) - set(after["codes"]))
            moved = before["classification"] != after["classification"]
            if not (moved or added or removed):
                continue
            worse = _RANK[after["classification"]] > _RANK[before["classification"]]
            changes.append({
                "mod_id": mod_id, "change": "CHANGED", "from": before["classification"], "to": after["classification"],
                "codes_added": added, "codes_removed": removed, "version_from": before["version"], "version_to": after["version"],
                "regression": worse or any(code not in _INFO_CODES for code in added),
            })
    return changes


def format_change(change: dict[str, Any]) -> str:
    if change["change"] == "ADDED":
        return f"ADDED   {change['mod_id']}: {change['to']}" + (f" [{', '.join(change['codes_added'])}]" if change["codes_added"] else "")
    if change["change"] == "REMOVED":
        return f"REMOVED {change['mod_id']}: was {change['from']}"
    parts = [f"{change['from']} -> {change['to']}"] if change["from"] != change["to"] else []
    parts += [f"+{code}" for code in change["codes_added"]] + [f"-{code}" for code in change["codes_removed"]]
    if change["version_from"] != change["version_to"]:
        parts.append(f"version {change['version_from']} -> {change['version_to']}")
    return f"CHANGED {change['mod_id']}: " + ", ".join(parts) + ("  [REGRESSION]" if change["regression"] else "")
