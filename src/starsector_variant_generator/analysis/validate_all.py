"""Validate every shipped variant in one pass (docs/AUTOMATION_PLAN.md V1.1).

Each variant goes through `validation/legality.py`, the sole legality source; this module only groups what it returns. The result
table is grouped by finding code and by source mod.

Severity of a finding follows recorded runtime evidence only (AGENTS.md section 7; BridgeForge CLAUDE.md "RC8 content behaviour,
live-proven 2026-09-27"): a variant naming a missing weapon is a Fatal dialog at New Game, a missing hull mod in a variant is
dropped silently. No other code has recorded runtime evidence, so every other code carries `NOT_RECORDED` rather than a guess.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from starsector_variant_generator.core.models import ScanResult, Variant
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.validation.legality import validate_variant

SCHEMA_VERSION = "validate-all-0.1"
CORE_SOURCE = "core"
RUNTIME_SEVERITY: dict[str, tuple[str, str]] = {
    "WEAPON_NOT_FOUND": ("FATAL_AT_NEW_GAME", "BridgeForge CLAUDE.md, RC8 content behaviour live-proven 2026-09-27"),
    "HULLMOD_NOT_FOUND": ("DROPPED_SILENTLY", "BridgeForge CLAUDE.md, RC8 content behaviour live-proven 2026-09-27"),
}
NOT_RECORDED = ("NOT_RECORDED", "no recorded runtime evidence for this code")
_MOD_SOURCE = re.compile(r"^mod:(?P<id>.+)$")


@dataclass(frozen=True)
class VariantRow:
    variant_id: str
    source_mod: str
    hull_id: str | None
    result: str
    failure_codes: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]


def select_variants(scan: ScanResult, source: str) -> list[Variant]:
    """`all`, `core` or `mod:<id>`; anything else is a ValueError."""
    if source == "all":
        return list(scan.variants)
    if source == CORE_SOURCE:
        return [variant for variant in scan.variants if variant.source_mod == CORE_SOURCE]
    match = _MOD_SOURCE.match(source)
    if match is None:
        raise ValueError(f"Unknown source {source!r}; use all, core or mod:<id>.")
    return [variant for variant in scan.variants if variant.source_mod == match.group("id")]


def validate_all(
    scan: ScanResult, registry: Registry, source: str = "all",
    on_source_done: Callable[[int, int, str, int, float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, object]:
    """Validate the selected variants. `on_source_done(index, total, mod, variant_count, seconds)` fires per source mod."""
    import time
    now = clock or time.perf_counter
    variants = select_variants(scan, source)
    by_mod: dict[str, list[Variant]] = defaultdict(list)
    for variant in variants:
        by_mod[variant.source_mod].append(variant)
    rows: list[VariantRow] = []
    mods = sorted(by_mod, key=str.lower)
    for index, mod in enumerate(mods, start=1):
        started = now()
        for variant in sorted(by_mod[mod], key=lambda item: (item.id.lower(), str(item.source_path))):
            assessment = validate_variant(variant, registry)
            rows.append(VariantRow(
                variant.id, mod, variant.hull_id, str(assessment.result.value),
                tuple(sorted({item.code for item in assessment.failures})),
                tuple(sorted({item.code for item in assessment.uncertainties})),
            ))
        if on_source_done is not None:
            on_source_done(index, len(mods), mod, len(by_mod[mod]), now() - started)
    return _summarise(rows, source)


def _summarise(rows: list[VariantRow], source: str) -> dict[str, object]:
    results = Counter(row.result for row in rows)
    codes: dict[str, dict[str, object]] = {}
    for kind, getter in (("failure", lambda row: row.failure_codes), ("uncertainty", lambda row: row.uncertainty_codes)):
        grouped: dict[str, list[VariantRow]] = defaultdict(list)
        for row in rows:
            for code in getter(row):
                grouped[code].append(row)
        for code, members in grouped.items():
            severity, evidence = RUNTIME_SEVERITY.get(code, NOT_RECORDED) if kind == "failure" else NOT_RECORDED
            codes[code] = {
                "kind": kind, "runtime_severity": severity, "severity_evidence": evidence, "count": len(members),
                "mods": dict(sorted(Counter(member.source_mod for member in members).items())),
                "variants": [f"{member.source_mod}:{member.variant_id}" for member in members],
            }
    per_mod: dict[str, dict[str, object]] = {}
    for mod in sorted({row.source_mod for row in rows}, key=str.lower):
        mine = [row for row in rows if row.source_mod == mod]
        per_mod[mod] = {
            "variants": len(mine), "results": dict(sorted(Counter(row.result for row in mine).items())),
            "codes": dict(sorted(Counter(code for row in mine for code in (*row.failure_codes, *row.uncertainty_codes)).items())),
        }
    return {
        "schema_version": SCHEMA_VERSION, "source": source, "variants_validated": len(rows),
        "results": dict(sorted(results.items())),
        "by_code": dict(sorted(codes.items(), key=lambda item: (-int(str(item[1]["count"])), item[0]))),
        "by_mod": per_mod,
        "rows": [
            {"variant_id": r.variant_id, "source_mod": r.source_mod, "hull_id": r.hull_id, "result": r.result,
             "failure_codes": list(r.failure_codes), "uncertainty_codes": list(r.uncertainty_codes)}
            for r in rows
        ],
        "scope_note": "Legality comes only from validation/legality.py. Runtime severity is shown only where recorded evidence exists.",
    }


def to_markdown(report: dict[str, object]) -> str:
    """Markdown tables: totals, findings by code, and mods by result."""
    lines = [f"# validate-all ({report['source']})", "", f"Variants validated: {report['variants_validated']}", ""]
    results = report["results"]
    assert isinstance(results, dict)
    lines += ["| Result | Variants |", "| --- | ---: |", *[f"| {name} | {count} |" for name, count in results.items()], ""]
    by_code = report["by_code"]
    assert isinstance(by_code, dict)
    lines += ["## By code", "", "| Code | Kind | Runtime severity | Variants | Mods |", "| --- | --- | --- | ---: | ---: |"]
    for code, info in by_code.items():
        lines.append(f"| {code} | {info['kind']} | {info['runtime_severity']} | {info['count']} | {len(info['mods'])} |")
    by_mod = report["by_mod"]
    assert isinstance(by_mod, dict)
    lines += ["", "## By mod", "", "| Mod | Variants | LEGAL | ILLEGAL | NOT_DETERMINABLE |", "| --- | ---: | ---: | ---: | ---: |"]
    for mod, info in by_mod.items():
        counts = info["results"]
        lines.append(f"| {mod} | {info['variants']} | {counts.get('LEGAL', 0)} | {counts.get('ILLEGAL', 0)} | {counts.get('NOT_DETERMINABLE', 0)} |")
    return "\n".join(lines) + "\n"
