"""Version-qualified resource projections; never instantiate saved objects.

Alias/type evidence: docs/CAMPAIGN_SAVE_RESOURCES.md. All projections run
through the same bounded, entity-refusing XML reader as S1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.parsers import expat

from .format import MAX_CAMPAIGN_BYTES, InspectionRefusal, _read_xml, _safe_path
from .models import SaveInspection


@dataclass(frozen=True)
class ValueLocator:
    start: int
    end: int
    original: str
    stored_type: str
    evidence: str


@dataclass(frozen=True)
class ResourceValue:
    target: str
    value: str
    locator: ValueLocator
    max_stack: str | None = None
    cargo_space_per_unit: str | None = None


@dataclass(frozen=True)
class ResourceSnapshot:
    schema_version: str
    status: str
    source_hashes: tuple[tuple[str, str], ...]
    resources: tuple[ResourceValue, ...]
    capacities: tuple[tuple[str, str], ...]
    notes: tuple[str, ...]
    unmodeled_cargo_state: bool = False


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    start: int
    end: int = 0
    text: str = ""
    children: list[_Node] = field(default_factory=list)
    has_nested: bool = False
    coverage: tuple[tuple[str, ...], ...] = ()


class _Projection:
    def __init__(self, selector: tuple[str, str | int] | None, paths: tuple[tuple[str, ...], ...]):
        self.selector = selector
        self.paths = paths
        self.matches: list[_Node] = []
        self.base: tuple[str, ...] | None = None
        self.active: dict[int, _Node] = {}
        self.nodes = 0

    def start(self, tag, attrs, path, offset):
        parent_node = self.active.get(len(path) - 1)
        if parent_node is not None:
            parent_node.has_nested = True
        selected = (self.selector is None and len(path) == 1 or
                    self.selector is not None and self.selector[0] == "ref" and attrs.get("z") == self.selector[1] or
                    self.selector is not None and self.selector[0] == "offset" and offset == self.selector[1])
        if selected:
            if self.matches:
                raise InspectionRefusal("AMBIGUOUS_RESOURCE", "Object identifier is duplicated")
            self.base = path
            node = _Node(tag, dict(attrs), offset, coverage=self.paths)
            self.matches.append(node)
            self.active[len(path)] = node
        elif self.base is not None and path[:len(self.base)] == self.base:
            relative = path[len(self.base):]
            if relative in self.paths:
                covered = tuple(p[len(relative):] for p in self.paths if p[:len(relative)] == relative and len(p) > len(relative))
                node = _Node(tag, dict(attrs), offset, coverage=covered)
                parent = self.active.get(len(path) - 1)
                if parent is None:
                    raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Resource projection lost its parent")
                parent.children.append(node)
                self.active[len(path)] = node
                self.nodes += 1
                if self.nodes > 10000:
                    raise InspectionRefusal("LIMIT_EXCEEDED", "Resource projection exceeds node limit")

    def chars(self, value, path, _offset):
        node = self.active.get(len(path))
        if node is not None:
            node.text += value
            if len(node.text) > 4096:
                raise InspectionRefusal("LIMIT_EXCEEDED", "Resource scalar exceeds limit")

    def end(self, _tag, path, offset):
        node = self.active.pop(len(path), None)
        if node is not None:
            node.end = offset
        if self.base == path:
            self.base = None


def _project(path: Path, expected_hash: str, selector, paths) -> _Node:
    projection = _Projection(selector, tuple(tuple(p.split("/")) for p in paths))
    _, digest = _read_xml(path, "CampaignEngine", MAX_CAMPAIGN_BYTES, (), observer=projection)
    if digest != expected_hash:
        raise InspectionRefusal("SOURCE_CHANGED", "Campaign changed since inspection")
    if len(projection.matches) != 1:
        raise InspectionRefusal("UNAVAILABLE_RESOURCE", "Referenced resource object was not found")
    return projection.matches[0]


def _one(node: _Node, tag: str) -> _Node:
    matches = [child for child in node.children if child.tag == tag]
    if len(matches) != 1:
        raise InspectionRefusal("UNAVAILABLE_RESOURCE", "Expected one unambiguous resource child")
    return matches[0]


def _resolve(path, digest, node, paths):
    seen = set()
    for _ in range(8):
        ref = node.attrs.get("ref")
        if ref is None:
            if all(tuple(p.split("/")) in node.coverage for p in paths):
                return node
            return _project(path, digest, ("offset", node.start), paths)
        if node.attrs.get("z") or node.children or node.text.strip() or ref in seen:
            raise InspectionRefusal("AMBIGUOUS_RESOURCE", "Invalid or cyclic object reference")
        seen.add(ref)
        node = _project(path, digest, ("ref", ref), paths)
    raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Reference chain exceeds limit")


def _number(value: str) -> Decimal:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value) or len(value) > 128:
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Resource numeric encoding exceeds the qualified profile")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Resource is not numeric") from exc
    if not result.is_finite() or result < 0:
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Resource must be finite and non-negative")
    if result > Decimal("3.4028234663852886E38"):
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Resource exceeds float32 storage")
    return result


def _attribute(path: Path, node: _Node, name: str, kind: str, evidence: str) -> ValueLocator:
    # Read only the opening tag, with a second handle; byte offsets come from Expat.
    with _safe_path(path).open("rb") as stream:
        stream.seek(node.start)
        raw = stream.read(16384)
    quote = None
    end = None
    for i, byte in enumerate(raw):
        if quote is None and byte in (34, 39):
            quote = byte
        elif byte == quote:
            quote = None
        elif quote is None and byte == 62:
            end = i + 1
            break
    if end is None:
        raise InspectionRefusal("LIMIT_EXCEEDED", "Opening tag exceeds locator limit")
    pattern = rb'\s+([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?:"([^"]*)"|\x27([^\x27]*)\x27)'
    matches = [match for match in re.finditer(pattern, raw[:end]) if match.group(1) == name.encode("ascii")]
    if len(matches) != 1:
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Attribute byte span is ambiguous")
    match = matches[0]
    group = 2 if match.group(2) is not None else 3
    value = match.group(group).decode("ascii")
    if value != node.attrs.get(name):
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Encoded or inconsistent numeric attribute")
    _number(value)
    return ValueLocator(node.start + match.start(group), node.start + match.end(group), value, kind, evidence)


def _scalar(path: Path, node: _Node, kind: str, evidence: str) -> ValueLocator:
    if node.has_nested or node.attrs or node.end - node.start > 8192:
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Value is not a plain scalar")
    with _safe_path(path).open("rb") as stream:
        stream.seek(node.start)
        raw = stream.read(node.end - node.start)
    prefix = ("<" + node.tag + ">").encode("ascii")
    if not raw.startswith(prefix):
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Scalar byte span is not recognized")
    value = raw[len(prefix):].decode("ascii")
    if value != node.text or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value):
        raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Scalar encoding is not a plain non-negative number")
    _number(value)
    return ValueLocator(node.start + len(prefix), node.end, value, kind, evidence)


def locate_resources(save_dir: Path, inspection: SaveInspection) -> ResourceSnapshot:
    if inspection.status != "READABLE":
        return ResourceSnapshot("campaign-resources-v1", inspection.status, inspection.source_hashes, (), (), inspection.notes)
    path = _safe_path(save_dir) / "campaign.xml"
    digest = dict(inspection.source_hashes)["campaign.xml"]
    resources: list[ResourceValue] = []
    capacities: list[tuple[str, str]] = []
    notes: list[str] = ["Capacity fields are saved figures; current runtime capacity and overage consequences are UNKNOWN."]
    unmodeled_cargo_state = False
    try:
        root = _project(path, digest, None, ("playerFleet", "characterData", "characterData/person", "characterData/person/stats"))
        # Each domain can be unavailable independently; no partial edit guesses.
        try:
            cargo_paths = ("c", "c/value", "s", "s/CIStack", "s/CIStack/d", "s/CIStack/c", "partials", "partials/entry")
            data_paths = ("cargo", *("cargo/" + p for p in cargo_paths))
            fleet_paths = ("fD", *("fD/" + p for p in data_paths))
            fleet = _resolve(path, digest, _one(root, "playerFleet"), fleet_paths)
            data = _resolve(path, digest, _one(fleet, "fD"), data_paths)
            cargo = _resolve(path, digest, _one(data, "cargo"), cargo_paths)
            for field_name, normalized in (("mC", "cargo"), ("mF", "fuel"), ("mP", "personnel"), ("sU", "space_used")):
                if field_name in cargo.attrs:
                    _number(cargo.attrs[field_name])
                    capacities.append((normalized, cargo.attrs[field_name]))
            credit = _resolve(path, digest, _one(cargo, "c"), ("value",))
            locator = _scalar(path, _one(credit, "value"), "FLOAT32", "RC8-CREDITS: playerFleet -> fD -> cargo -> c/value")
            resources.append(ResourceValue("credits", locator.original, locator))
            stack_list = _resolve(path, digest, _one(cargo, "s"), ("CIStack", "CIStack/d", "CIStack/c"))
            seen = set()
            for stack in stack_list.children:
                if stack.attrs.get("t") != "RESOURCES":
                    continue
                if stack.attrs.get("ref"):
                    raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Referenced cargo stacks are not qualified")
                item = _one(stack, "d")
                if item.attrs.get("cl") != "st" or item.attrs.get("ref") or item.has_nested:
                    raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Resource identifier is not an inline string")
                identifier = item.text
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", identifier) or identifier in seen:
                    raise InspectionRefusal("AMBIGUOUS_RESOURCE", "Duplicate or unrecognized commodity stack")
                seen.add(identifier)
                locator = _attribute(path, stack, "s", "FLOAT32", f"RC8-STACK: player cargo /s/CIStack[d={identifier}]/@s")
                maximum = stack.attrs.get("mS")
                unit = stack.attrs.get("cSPU")
                if maximum is not None:
                    _number(maximum)
                if unit is not None:
                    _number(unit)
                resources.append(ResourceValue("commodity:" + identifier, locator.original, locator, maximum, unit))
            if any(child.tag == "partials" for child in cargo.children):
                partials = _resolve(path, digest, _one(cargo, "partials"), ("entry",))
                if partials.children:
                    unmodeled_cargo_state = True
                    notes.append("Cargo partials exist; commodity edits require unmodeled-state refusal.")
        except InspectionRefusal as exc:
            if exc.status == "SOURCE_CHANGED":
                raise
            notes.append("Cargo domain unavailable: " + str(exc))
            resources = []
            capacities = []
        try:
            character = _resolve(path, digest, _one(root, "characterData"), ("person", "person/stats"))
            person = _resolve(path, digest, _one(character, "person"), ("stats",))
            stats = _resolve(path, digest, _one(person, "stats"), ())
            locator = _attribute(path, stats, "sp", "INT32", "RC8-STORY: characterData -> person -> stats/@sp")
            if _number(locator.original) > 2**31 - 1 or _number(locator.original) != int(_number(locator.original)):
                raise InspectionRefusal("UNSUPPORTED_RESOURCE", "Story points are not integral")
            resources.append(ResourceValue("story_points", locator.original, locator))
        except InspectionRefusal as exc:
            if exc.status == "SOURCE_CHANGED":
                raise
            notes.append("Story-point domain unavailable: " + str(exc))
        # Descriptor may also have changed while projections ran.
        from .format import FIELDS, MAX_DESCRIPTOR_BYTES
        _, descriptor_hash = _read_xml(_safe_path(save_dir) / "descriptor.xml", "SaveGameData", MAX_DESCRIPTOR_BYTES, FIELDS)
        if descriptor_hash != dict(inspection.source_hashes)["descriptor.xml"]:
            raise InspectionRefusal("SOURCE_CHANGED", "Descriptor changed during resource inspection")
        _, final_digest = _read_xml(path, "CampaignEngine", MAX_CAMPAIGN_BYTES, ())
        if final_digest != digest:
            raise InspectionRefusal("SOURCE_CHANGED", "Campaign changed during resource location")
        return ResourceSnapshot("campaign-resources-v1", "READABLE", inspection.source_hashes, tuple(resources), tuple(capacities), tuple(notes), unmodeled_cargo_state)
    except (InspectionRefusal, OSError, ValueError) as exc:
        status = exc.status if isinstance(exc, InspectionRefusal) else "UNSAFE_RESOURCE"
        return ResourceSnapshot("campaign-resources-v1", status, inspection.source_hashes, (), (), (str(exc),))
    except expat.ExpatError:
        return ResourceSnapshot("campaign-resources-v1", "MALFORMED", inspection.source_hashes, (), (), ("Campaign XML became malformed",))
