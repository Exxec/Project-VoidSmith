"""Read-only verdict on one mod folder, for a sister project to read before archiving (docs/AUTOMATION_PLAN.md V4.1).

Runs the V1.1 variant validation and the V1.3 parse-failure locations on the entities that come from ONE mod folder, against a
context: `core` (the default; the core data plus that mod only) or `enabled` (core plus every enabled mod, which is what the
game would see). The mod is identified by folder, not by id, so a working copy of an installed mod is never mixed up with the
installed one. VoidSmith reads only: it never edits the mod, and the verdict is a JSON document the caller reads.

Verdict (legality is only ever taken from validation/legality.py; nothing here judges quality):
- FAIL: a parse failure in the mod, an unreadable mod_info.json, or a variant that names a missing weapon (a Fatal dialog at New
  Game, BridgeForge RC8 behaviour live-proven 2026-09-27).
- REVIEW: any other ILLEGAL or NOT_DETERMINABLE variant, or a missing hull mod in a variant (dropped silently, same evidence).
- PASS: none of those. PASS is not proof of in-game behaviour.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from starsector_variant_generator.analysis.parse_diagnostics import locate_parse_failures
from starsector_variant_generator.analysis.validate_all import RUNTIME_SEVERITY, validate_all
from starsector_variant_generator.core.models import Entity, ScanResult
from starsector_variant_generator.core.registry import Registry

SCHEMA_VERSION = "check-mod-0.1"
CONTEXTS = ("core", "enabled")
_ENTITY_KINDS = ("hulls", "weapons", "fighters", "hullmods", "variants", "factions")
_FATAL = "FATAL_AT_NEW_GAME"


def _under(entity: Entity, root: Path) -> bool:
    try:
        entity.source_path.resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def restrict_to_mod(scan: ScanResult, mod_root: Path, context: str) -> ScanResult:
    """Entities of the mod folder, plus core (context `core`) or everything else scanned (context `enabled`)."""
    if context not in CONTEXTS:
        raise ValueError(f"Unknown context {context!r}; use core or enabled.")
    root = mod_root.resolve()
    def keep(kind: str) -> list[Any]:
        return [e for e in getattr(scan, kind) if _under(e, root) or context == "enabled" or e.source_mod == "core"]

    mods = [mod for mod in scan.mods if context == "enabled" or mod.mod_id == "core" or mod.path.resolve() == root]
    return ScanResult(
        mods=mods, hulls=keep("hulls"), weapons=keep("weapons"), fighters=keep("fighters"), hullmods=keep("hullmods"),
        variants=keep("variants"), factions=keep("factions"), warnings=list(scan.warnings), errors=list(scan.errors),
        skipped_entities=list(scan.skipped_entities),
    )


def check_mod(scan: ScanResult, mod_root: Path, *, mod_id: str | None, mod_name: str | None, context: str = "core") -> dict[str, Any]:
    root = mod_root.resolve()
    restricted = restrict_to_mod(scan, root, context)
    registry = Registry.from_scan(restricted)
    target = ScanResult(variants=[v for v in restricted.variants if _under(v, root)])
    validation = validate_all(target, registry, "all")
    mod_errors = [message for message in scan.errors if str(root) in message or str(mod_root) in message]
    failures = [failure.to_dict() for failure in locate_parse_failures(ScanResult(errors=mod_errors))]
    unlocated = [message for message in mod_errors if not any(f["message"] == message for f in failures)]
    by_code = validation["by_code"]
    assert isinstance(by_code, dict)
    reasons: list[str] = []
    verdict = "PASS"
    if mod_id is None:
        reasons.append("mod_info.json is missing or unreadable")
        verdict = "FAIL"
    if failures:
        reasons.append(f"{len(failures)} located parse failure(s)")
        verdict = "FAIL"
    if any(info["runtime_severity"] == _FATAL for info in by_code.values()):
        reasons.append("a variant names a weapon that is not found (Fatal at New Game, BridgeForge RC8 evidence)")
        verdict = "FAIL"
    results = validation["results"]
    assert isinstance(results, dict)
    if verdict != "FAIL" and (results.get("ILLEGAL") or results.get("NOT_DETERMINABLE") or unlocated):
        reasons.append("variants with ILLEGAL or NOT_DETERMINABLE findings, or other scan errors, need a person's review")
        verdict = "REVIEW"
    if verdict == "PASS" and "HULLMOD_NOT_FOUND" in by_code:
        reasons.append("a variant names a missing hull mod (dropped silently)")
        verdict = "REVIEW"
    return {
        "schema_version": SCHEMA_VERSION, "verdict": verdict, "reasons": reasons, "read_only": True, "context": context,
        "mod": {"id": mod_id, "name": mod_name, "path": str(root)},
        "entity_counts": {kind: sum(1 for e in getattr(restricted, kind) if _under(e, root)) for kind in _ENTITY_KINDS},
        "validate_all": validation, "parse_failures": failures, "other_scan_errors": unlocated,
        "severity_evidence": {code: {"runtime_severity": severity, "evidence": evidence} for code, (severity, evidence) in RUNTIME_SEVERITY.items()},
        "scope_note": "Legality comes only from validation/legality.py. PASS means none of the listed problems were found, not that the mod works in game.",
    }
