"""Expected in-game fingerprint of a written save copy, and its comparison with the probe's log (ROADMAP item 79.3).

BridgeForge's probe fingerprints a save in game: per section a canonical text (lines sorted, joined with a newline) and a
64-bit FNV-1a digest over its UTF-16 code units (two bytes each, low byte first); floats are written as integer hundredths
with Java's float arithmetic (`Math.round(value * 100f)`). This module reproduces that form exactly for the sections the
Workshop's own readers can supply, and refuses to cover any section it cannot reproduce. Nothing is approximated, and
nothing here writes a save: the only file written is the expectation, inside a copy the Workshop has just created.
"""
from __future__ import annotations

import json
import math
import re
import struct
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

from .edit_plan import EditPlan
from .format import _safe_path, inspect_save
from .locators import ResourceSnapshot, locate_resources

EXPECTED_FILE = "voidsmith_expected_fingerprint.json"
SCHEMA_VERSION = "voidsmith-expected-fingerprint-v1"
REPORT_SCHEMA_VERSION = "voidsmith-verify-ingame-v1"
PROBE_SECTIONS = ("markets", "systems", "rings", "fleets", "player", "cargo", "mod", "totals")
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_EXPECTED_BYTES = 8 * 1024 * 1024
_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASK = (1 << 64) - 1
_INT_MIN, _INT_MAX = -(2**31), 2**31 - 1
_MAX_F32_BITS = 0x7F7FFFFF
_CAPACITY_FIELDS = (("cargo", "mC"), ("fuel", "mF"), ("personnel", "mP"))
_NOT_COVERED = {
    "player": ("the Workshop's readers project only player cargo, credits and story points; fleet members (member id, hull id, "
               "variant id, CR, hull fractions, armor damage, module slots) are not parsed, so their canonical text cannot be produced"),
    "markets": "no market data is parsed from a save",
    "systems": "no star-system data is parsed from a save",
    "rings": "no ring-band data is parsed from a save",
    "fleets": "no other-fleet data is parsed from a save",
    "mod": "derives from markets, systems and fleets filtered by the probe's mod configuration; none is parsed",
    "totals": "counts of markets, systems, planets, fleets and player members; none is parsed",
}


def fnv64(text: str) -> str:
    """The probe's FingerprintSections.fnv64: FNV-1a over UTF-16 code units, low byte then high byte, 16 lowercase hex digits."""
    value = _FNV_OFFSET
    for byte in text.encode("utf-16-le"):
        value = ((value ^ byte) * _FNV_PRIME) & _MASK
    return f"{value:016x}"


def _nearest_float32(value: Fraction) -> Fraction | None:
    """The float32 nearest to an exact value (ties to even), or None beyond float32 range; avoids double rounding."""
    if value == 0:
        return Fraction(0)
    try:
        bits = struct.unpack("<I", struct.pack("<f", float(value)))[0]
    except OverflowError:
        return None
    best = None
    for candidate in (bits - 1, bits, bits + 1):
        if 0 <= candidate <= _MAX_F32_BITS:
            exact = Fraction(struct.unpack("<f", struct.pack("<I", candidate))[0])
            key = (abs(exact - value), candidate & 1)
            if best is None or key < best[0]:
                best = (key, exact)
    return None if best is None else best[1]


def hundredths(value: str | Decimal) -> str | None:
    """Java `String.valueOf(Math.round(floatValue * 100f))` for a stored non-negative decimal; None when not reproducible."""
    try:
        exact = Fraction(Decimal(value))
    except (InvalidOperation, ValueError):
        return None
    stored = _nearest_float32(exact)
    product = None if stored is None else _nearest_float32(stored * 100)
    if product is None:
        return None
    return str(max(_INT_MIN, min(_INT_MAX, math.floor(product + Fraction(1, 2)))))


def _cargo_line(capacities: dict[str, str], stacks: dict[str, str], space_used: str | Decimal) -> str | None:
    """The probe's `cargo` line, or None when any field cannot be produced exactly."""
    try:
        crew = Decimal(stacks.get("crew", "0"))
    except InvalidOperation:
        return None
    if crew != crew.to_integral_value():
        return None  # the probe writes getCrew() without hundredths; a fractional crew stack is not reproducible
    parts = [(name, hundredths(capacities[key]) if key in capacities else None) for key, name in _CAPACITY_FIELDS]
    parts += [("spaceUsed", hundredths(space_used)), ("fuel", hundredths(stacks.get("fuel", "0"))),
              ("crew", str(int(crew))), ("supplies", hundredths(stacks.get("supplies", "0")))]
    if any(value is None for _, value in parts):
        return None
    return ";".join(f"{name}={value}" for name, value in parts)


def _section(text: str) -> dict[str, object]:
    return {"text": text, "count": 0 if not text else len(text.split("\n")), "len": len(text), "fnv": fnv64(text)}


def _stacks(snapshot: ResourceSnapshot) -> dict[str, str]:
    return {r.target.removeprefix("commodity:"): r.value for r in snapshot.resources if r.target.startswith("commodity:")}


def _line_for(snapshot: ResourceSnapshot, space_used: str | Decimal | None = None,
              capacities: dict[str, str] | None = None) -> str | None:
    caps = dict(snapshot.capacities)
    if any(name not in caps for name in ("cargo", "fuel", "personnel", "space_used")):
        return None
    return _cargo_line(capacities or caps, _stacks(snapshot), caps["space_used"] if space_used is None else space_used)


def _variants(copy: ResourceSnapshot, source: ResourceSnapshot, plan: EditPlan, text: str) -> tuple[dict[str, dict], list[str]]:
    """Alternative cargo texts for the two things a load might recompute: space used, and any capacity this copy edited."""
    variants: dict[str, dict] = {}
    caps_copy, caps_source = dict(copy.capacities), dict(source.capacities)
    delta = Decimal(0)
    for change in plan.changes:
        unit = next((r.cargo_space_per_unit for r in copy.resources if r.target == change.target), None)
        if unit is not None and change.old_value is not None and change.target.startswith("commodity:"):
            delta += (Decimal(change.new_value) - Decimal(change.old_value)) * Decimal(unit)
    if delta != 0:
        by_delta = _line_for(copy, Decimal(caps_copy["space_used"]) + delta)
        if by_delta is not None and by_delta != text:
            variants["space_used_recomputed_by_delta"] = _section(by_delta)
    edited = [name for key, name in _CAPACITY_FIELDS if caps_copy.get(key) != caps_source.get(key)]
    if edited:
        restored = {**caps_copy, **{k: caps_source[k] for k, n in _CAPACITY_FIELDS if n in edited and k in caps_source}}
        reverted = _line_for(copy, capacities=restored)
        if reverted is not None and reverted != text:
            variants["capacity_as_source"] = _section(reverted)
    return variants, edited


def build_expected(source_dir: Path, copy_dir: Path, plan: EditPlan) -> dict[str, object]:
    """The expected fingerprint document for a copy written from `plan`; read-only on both folders."""
    source = locate_resources(_safe_path(source_dir), inspect_save(_safe_path(source_dir)))
    copy = locate_resources(_safe_path(copy_dir), inspect_save(_safe_path(copy_dir)))
    sections: dict[str, object] = {}
    not_covered = dict(_NOT_COVERED)
    changed: list[str] = []
    text = _line_for(copy) if copy.status == "READABLE" and source.status == "READABLE" else None
    if text is None:
        not_covered["cargo"] = ("a capacity or space-used figure is missing from the save, the crew stack is fractional, or a value "
                                "cannot be rendered as the probe does, so the cargo line is not reproducible exactly")
    else:
        section = _section(text)
        section["variants"], section["edited_capacity_fields"] = _variants(copy, source, plan, text)
        section["assumptions"] = ["crew is rendered as a plain integer, as the probe concatenates getCrew() without hundredths",
                                  "spaceUsed is the copy's stored figure; a load that recomputes it shows as a variant match or DIFFERS"]
        sections["cargo"] = section
        if _line_for(source) != text:
            changed.append("cargo")
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "FNV-1a 64-bit over UTF-16LE code units; floats as integer hundredths (float32 arithmetic, Math.round)",
        "edited_targets": [change.target for change in plan.changes],
        "sections": sections,
        "intentionally_changed": changed,
        "must_leave_unchanged": [name for name in PROBE_SECTIONS if name != "cargo"],
        "not_covered": not_covered,
        "notes": ["Written with the copy; the copy has NOT been loaded in the game.",
                  "Sections in must_leave_unchanged are compared with the pre-edit digest the probe stored in the same log "
                  "(phase=before, source=file); no expected text exists for them."],
    }


def write_expected(source_dir: Path, copy_dir: Path, plan: EditPlan) -> Path:
    """Create the expectation file inside a copy this run made; never overwrites."""
    document = build_expected(source_dir, copy_dir, plan)
    target = _safe_path(copy_dir) / EXPECTED_FILE
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return target


# --- comparison with a probe log -------------------------------------------------------------------------------------

_LINE = re.compile(r"BF-PROBE\|[^|]*\|fingerprint\|[A-Z]+\|(?P<subject>[^|]*)\|(?P<detail>[^|\r\n]*)")


def _fields(detail: str) -> dict[str, str]:
    return {key: value for key, _, value in (part.partition("=") for part in detail.split(";") if "=" in part)}


def parse_probe_log(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """(before, after) section digests; a before line with source=file (the stored pre-edit digest) wins over any other."""
    before: dict[str, str] = {}
    from_file: dict[str, str] = {}
    after: dict[str, str] = {}
    for match in _LINE.finditer(text):
        fields = _fields(match.group("detail"))
        section, digest = fields.get("section"), fields.get("fnv", "").lower()
        if section not in PROBE_SECTIONS or not re.fullmatch(r"[0-9a-f]{16}", digest):
            continue
        subject = match.group("subject")
        if subject == "phase=after":
            after[section] = digest
        elif subject == "phase=before":
            (from_file if fields.get("source") == "file" else before)[section] = digest
    return {**before, **from_file}, after


def _read_text(path: Path, limit: int) -> str:
    if path.stat().st_size > limit:
        raise ValueError(f"{path.name} exceeds the {limit} byte limit")
    return path.read_text(encoding="utf-8", errors="replace")


def _row(section: str, status: str, detail: str, **extra: object) -> dict[str, object]:
    return {"section": section, "status": status, "detail": detail, **extra}


def _cargo_row(entry: dict, after: dict[str, str]) -> dict[str, object]:
    digest = after.get("cargo")
    if digest is None:
        return _row("cargo", "NOT_IN_LOG", "no phase=after cargo line in the log", expected=entry["fnv"])
    if digest == entry["fnv"]:
        return _row("cargo", "MATCH", "the game reports the copy's stored cargo figures", expected=entry["fnv"], observed=digest)
    for name, variant in entry.get("variants", {}).items():
        if digest == variant["fnv"]:
            return _row("cargo", "DIFFERS", f"matches the variant {name}: the game recomputed rather than kept the stored figure",
                        expected=entry["fnv"], observed=digest, matched_variant=name)
    return _row("cargo", "DIFFERS", "matches neither the stored figures nor a modeled recompute; a digest cannot say which field differs",
                expected=entry["fnv"], observed=digest)


def _unchanged_row(section: str, before: dict[str, str], after: dict[str, str]) -> dict[str, object]:
    if section not in after or section not in before:
        return _row(section, "NOT_IN_LOG", "needs a stored pre-edit digest and a phase=after digest in the log", basis="pre-edit digest")
    return _row(section, "MATCH" if before[section] == after[section] else "DIFFERS",
                "the edit must not change this section; compared with the stored pre-edit digest",
                expected=before[section], observed=after[section], basis="pre-edit digest")


def _capacity_result(entry: dict | None, row: dict[str, object] | None) -> dict[str, object] | None:
    if entry is None or row is None:
        return None
    edited = list(entry.get("edited_capacity_fields", []))
    if not edited:
        return {"edited_fields": [], "result": "NOT_EXERCISED",
                "detail": "this copy did not edit mC/mF/mP, so it cannot show whether a load recomputes an edited capacity"}
    if row["status"] == "MATCH":
        return {"edited_fields": edited, "result": "KEPT", "detail": "edited capacity came back as edited: the load did not recompute it"}
    if row["status"] == "NOT_IN_LOG":
        return {"edited_fields": edited, "result": "UNDETERMINED", "detail": "no cargo digest in the log"}
    return {"edited_fields": edited, "result": "RECOMPUTED",
            "detail": "cargo DIFFERS with the capacity edit expected: the load recomputed the capacity"}


def verify_ingame(copy_dir: Path, log_path: Path) -> dict[str, object]:
    """Compare the probe's phase=after digests of a loaded copy with the expectation written beside the copy."""
    expected = json.loads(_read_text(_safe_path(copy_dir) / EXPECTED_FILE, MAX_EXPECTED_BYTES))
    if expected.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported expectation schema {expected.get('schema_version')!r}")
    before, after = parse_probe_log(_read_text(log_path, MAX_LOG_BYTES))
    base = {"schema_version": REPORT_SCHEMA_VERSION, "not_covered": sorted(expected.get("not_covered", {}))}
    if not after:
        return {**base, "verdict": "FAIL", "sections": [], "capacity": None,
                "reasons": ["the log has no phase=after fingerprint line; the copy was not loaded with the probe's save-reload stage"]}
    rows: list[dict[str, object]] = []
    for section in PROBE_SECTIONS:
        entry = expected["sections"].get(section)
        if section == "cargo" and entry is not None:
            rows.append(_cargo_row(entry, after))
        elif section in expected["must_leave_unchanged"]:
            rows.append(_unchanged_row(section, before, after))
    cargo = next((r for r in rows if r["section"] == "cargo"), None)
    reasons = [f"{r['section']}: {r['status']}" for r in rows if r["status"] != "MATCH"]
    broke_untouched = any(r["status"] == "DIFFERS" and r.get("basis") for r in rows)
    verdict = "FAIL" if broke_untouched else ("PASS" if not reasons else "REVIEW")
    return {**base, "verdict": verdict, "sections": rows, "reasons": reasons,
            "capacity": _capacity_result(expected["sections"].get("cargo"), cargo)}
