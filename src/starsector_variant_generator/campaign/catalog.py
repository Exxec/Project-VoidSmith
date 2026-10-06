"""Read commodity membership from explicitly supplied installed source roots."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .format import _identity, _safe_path


@dataclass(frozen=True)
class CommodityCatalog:
    status: str
    identifiers: frozenset[str]
    evidence: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()


def read_commodity_catalog(source_roots: tuple[Path, ...]) -> CommodityCatalog:
    ids: set[str] = set()
    evidence: list[tuple[str, str]] = []
    try:
        if len(source_roots) > 512:
            raise ValueError("Source count exceeds catalog limit")
        for root in source_roots:
            path = _safe_path(root) / "data/campaign/commodities.csv"
            if not path.exists():
                continue
            path = _safe_path(path)
            if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("Commodity file exceeds catalog boundary")
            before = _identity(path.stat())
            with path.open("rb") as stream:
                if _identity(os.fstat(stream.fileno())) != before:
                    raise ValueError("Commodity source changed before reading")
                raw = stream.read(8 * 1024 * 1024 + 1)
                if _identity(os.fstat(stream.fileno())) != before:
                    raise ValueError("Commodity source changed while reading")
            if _identity(_safe_path(path).stat()) != before:
                raise ValueError("Commodity source changed after reading")
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("Commodity file grew beyond catalog limit")
            rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            if rows.fieldnames is None or rows.fieldnames.count("id") != 1:
                raise ValueError("Commodity table needs one id column")
            for row in rows:
                identifier = (row.get("id") or "").strip()
                if not identifier or identifier.startswith("#"):
                    continue
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", identifier):
                    raise ValueError("Commodity id is not recognized")
                ids.add(identifier)
            evidence.append((str(path), hashlib.sha256(raw).hexdigest()))
        return CommodityCatalog("PARSED" if evidence else "UNAVAILABLE", frozenset(ids), tuple(evidence))
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        return CommodityCatalog("UNAVAILABLE", frozenset(), (), (str(exc),))
