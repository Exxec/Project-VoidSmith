"""Bounded XML inspection under docs/CAMPAIGN_SAVE_FORMAT.md.

XStream objects are never instantiated and references are never interpreted.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from xml.parsers import expat

from .models import CampaignFact, FactStatus, SaveInspection

MAX_CAMPAIGN_BYTES = 256 * 1024 * 1024
MAX_DESCRIPTOR_BYTES = 1024 * 1024
MAX_DEPTH = 256
MAX_ELEMENTS = 5_000_000
SUPPORTED_VERSION = ("0.98a-RC8", "0.6")
FIELDS = ("characterName", "gameVersion", "saveFileVersion", "compressed")


class InspectionRefusal(ValueError):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status


def _safe_path(path: Path) -> Path:
    # Check before resolve: resolving first hides linked ancestors.
    if ".." in path.parts:
        raise InspectionRefusal("UNSAFE_PATH", "Parent traversal is refused")
    absolute = Path(os.path.abspath(path))
    for part in (*reversed(absolute.parents), absolute):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InspectionRefusal("UNSAFE_PATH", "Links and reparse points are refused")
    return absolute


def _identity(info: os.stat_result) -> tuple:
    # Windows creation-time metadata can differ between stat and fstat for a
    # just-created file; it is not a content-change signal.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_xml(path: Path, root: str, limit: int, fields: tuple[str, ...], *, observer=None) -> tuple[dict[str, str], str]:
    safe = _safe_path(path)
    before = safe.stat()
    if not stat.S_ISREG(before.st_mode):
        raise InspectionRefusal("NOT_A_SAVE", "Expected regular XML file")
    if before.st_size > limit:
        raise InspectionRefusal("LIMIT_EXCEEDED", "XML file exceeds documented size limit")
    parser = expat.ParserCreate("UTF-8")
    stack: list[str] = []
    values: dict[str, str] = {}
    text_parts: list[str] = []
    count = 0
    text_length = 0

    def refuse_declaration(*_args):
        raise InspectionRefusal("UNSAFE_XML", "DOCTYPE and entity declarations are refused")

    def start(name, _attrs):
        nonlocal count, text_parts, text_length
        if not stack and name != root:
            raise InspectionRefusal("NOT_A_SAVE", "Unrecognized XML root")
        stack.append(name)
        count += 1
        if len(stack) > MAX_DEPTH or count > MAX_ELEMENTS:
            raise InspectionRefusal("LIMIT_EXCEEDED", "XML structural limit exceeded")
        if len(stack) == 2 and name in fields:
            if name in values:
                raise InspectionRefusal("MALFORMED", "Duplicate descriptor field")
            text_parts = []
            text_length = 0
        if len(stack) > 2 and stack[1] in fields:
            raise InspectionRefusal("MALFORMED", "Descriptor scalar contains nested data")
        if observer is not None:
            observer.start(name, _attrs, tuple(stack), parser.CurrentByteIndex)

    def chars(value):
        nonlocal text_length
        if observer is not None:
            observer.chars(value, tuple(stack), parser.CurrentByteIndex)
        if len(stack) == 2 and stack[-1] in fields:
            text_length += len(value)
            if text_length > 4096:
                raise InspectionRefusal("LIMIT_EXCEEDED", "Descriptor scalar exceeds limit")
            text_parts.append(value)

    def end(name):
        if observer is not None:
            observer.end(name, tuple(stack), parser.CurrentByteIndex)
        if len(stack) == 2 and name in fields:
            values[name] = "".join(text_parts).strip()
        stack.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.StartDoctypeDeclHandler = refuse_declaration
    parser.EntityDeclHandler = refuse_declaration
    parser.ExternalEntityRefHandler = refuse_declaration
    def declaration(_version, encoding, _standalone):
        if encoding is not None and encoding.upper() not in ("UTF-8", "UTF8"):
            raise InspectionRefusal("UNSUPPORTED_FORMAT", "Only UTF-8 XML is supported")
    parser.XmlDeclHandler = declaration
    digest = hashlib.sha256()
    total = 0
    with safe.open("rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise InspectionRefusal("SOURCE_CHANGED", "Source changed before inspection")
        prefix = stream.read(256)
        # Explicit UTF-8 profile avoids declaration filtering bypasses in UTF-16.
        if b"\x00" in prefix or prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise InspectionRefusal("UNSUPPORTED_FORMAT", "Only UTF-8 XML is supported")
        chunk = prefix
        while chunk:
            total += len(chunk)
            if total > limit:
                raise InspectionRefusal("LIMIT_EXCEEDED", "XML file grew beyond size limit")
            digest.update(chunk)
            parser.Parse(chunk, False)
            chunk = stream.read(64 * 1024)
        parser.Parse(b"", True)
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise InspectionRefusal("SOURCE_CHANGED", "Source changed during inspection")
    if _identity(_safe_path(path).stat()) != _identity(before):
        raise InspectionRefusal("SOURCE_CHANGED", "Source was replaced during inspection")
    return values, digest.hexdigest()


def inspect_save(save_dir: Path) -> SaveInspection:
    """Read only an explicitly selected directory. Write no files or logs."""
    hashes: list[tuple[str, str]] = []
    facts: list[CampaignFact] = []
    try:
        directory = _safe_path(save_dir)
        if not directory.is_dir():
            raise InspectionRefusal("NOT_A_SAVE", "Select a save directory")
        selected = (directory / "descriptor.xml", directory / "campaign.xml")
        snapshots = tuple(_identity(_safe_path(path).stat()) for path in selected)
        descriptor, digest = _read_xml(directory / "descriptor.xml", "SaveGameData", MAX_DESCRIPTOR_BYTES, FIELDS)
        hashes.append(("descriptor.xml", digest))
        version = descriptor.get("gameVersion"), descriptor.get("saveFileVersion")
        if version != SUPPORTED_VERSION:
            raise InspectionRefusal("UNSUPPORTED_VERSION", "Only game 0.98a-RC8 / save 0.6 is qualified")
        if descriptor.get("compressed") != "false":
            raise InspectionRefusal("UNSUPPORTED_FORMAT", "Only explicitly uncompressed saves are qualified")
        _, digest = _read_xml(directory / "campaign.xml", "CampaignEngine", MAX_CAMPAIGN_BYTES, ())
        hashes.append(("campaign.xml", digest))
        if tuple(_identity(_safe_path(path).stat()) for path in selected) != snapshots:
            raise InspectionRefusal("SOURCE_CHANGED", "Save files changed across inspection")
        for name in FIELDS:
            value = descriptor.get(name)
            facts.append(CampaignFact(name, value, FactStatus.PARSED if value is not None else FactStatus.UNAVAILABLE,
                                      f"descriptor.xml:/SaveGameData/{name}"))
        for name in ("credits", "story_points", "cargo", "capacity", "enabled_mods"):
            facts.append(CampaignFact(name, None, FactStatus.UNAVAILABLE, "No qualified semantic locator"))
        facts.append(CampaignFact("capacity_overage_effects", None, FactStatus.UNKNOWN, "No controlled runtime evidence"))
        return SaveInspection("campaign-inspection-v1", "READABLE", tuple(facts), tuple(hashes),
                              ("XML structure inspected; campaign resource semantics are not interpreted.",
                               "No save modified. READABLE does not prove that the game can load this save."))
    except InspectionRefusal as exc:
        return SaveInspection("campaign-inspection-v1", exc.status, (), tuple(hashes), (str(exc),))
    except expat.ExpatError:
        return SaveInspection("campaign-inspection-v1", "MALFORMED", (), tuple(hashes), ("Malformed or truncated XML",))
    except OSError:
        return SaveInspection("campaign-inspection-v1", "NOT_A_SAVE", (), tuple(hashes), ("Required save files are missing or unreadable",))
    except ValueError:
        return SaveInspection("campaign-inspection-v1", "UNSAFE_PATH", (), tuple(hashes), ("Invalid save path",))
