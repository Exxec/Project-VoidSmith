"""Small deterministic SQLite cache for derived analysis results.

Entries are reusable only for an exact serialized context key. This module is
output-directory infrastructure; it never reads/writes game or mod sources.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from starsector_variant_generator.analysis.change_impact import ChangeImpactReport

CACHE_SCHEMA_VERSION = "analysis-cache-0.1"


class CacheReadiness(StrEnum):
    """Whether an operation has declared enough inputs for safe reuse."""

    CACHE_SAFE = "CACHE_SAFE"
    CACHE_UNSAFE_INCOMPLETE_CONTEXT = "CACHE_UNSAFE_INCOMPLETE_CONTEXT"
    CACHE_DISABLED = "CACHE_DISABLED"


@dataclass(frozen=True)
class AnalysisContextFingerprint:
    """Declared inputs required for safely reusing a derived operation."""
    operation: str
    entity_hashes: tuple[str, ...]
    heuristic_set: str
    adapter_versions: tuple[str, ...] = ()
    override_hash: str | None = None
    knowledge_pack_freshness: str | None = None
    constraints_hash: str | None = None
    readiness: CacheReadiness = CacheReadiness.CACHE_UNSAFE_INCOMPLETE_CONTEXT

    def context(self) -> dict[str, Any]:
        return asdict(self)

    def reusable(self) -> bool:
        """Fail closed: only fully declared operation contexts may be reused."""
        return self.readiness is CacheReadiness.CACHE_SAFE


def resolve_cache_status(
    result_cache: AnalysisResultCache | None,
    fingerprint: AnalysisContextFingerprint | None,
) -> CacheReadiness:
    """The real, inspectable reason a cache decision landed where it did.

    Distinct from an implicit hit/miss: this reports whether reuse was even
    *attempted safely*, not whether a matching row happened to already exist.

    - `CACHE_DISABLED`: no `AnalysisResultCache` instance was supplied for
      this call at all (`result_cache is None`) -- a real, common path today
      (e.g. the GUI's generation/recommendation calls, or any direct
      `api.py`/library caller that does not opt in). No lookup or store was
      even attempted.
    - `CACHE_UNSAFE_INCOMPLETE_CONTEXT`: a cache was supplied, but the
      operation's `AnalysisContextFingerprint` could not be fully declared
      (e.g. a consumed entity had no real `source_hash`), so the lookup/store
      was skipped even though a cache was available -- different from a
      genuine miss against a complete context.
    - `CACHE_SAFE`: a cache was supplied and the fingerprint's context was
      completely declared, so a lookup was safely attempted (whether it hit
      an existing entry or missed and stored a fresh one).

    Callers already compute `fingerprint` immediately before a `get`/`put`
    pair (see `api.py::run_generate`/`run_gap_recommendations`); this just
    names the same decision explicitly instead of leaving it implicit.
    """
    if result_cache is None or fingerprint is None:
        return CacheReadiness.CACHE_DISABLED
    return fingerprint.readiness


class AnalysisResultCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        db = self._connect()
        try:
            db.execute("CREATE TABLE IF NOT EXISTS entries (cache_key TEXT PRIMARY KEY, target_kind TEXT NOT NULL, target_id TEXT NOT NULL, context_json TEXT NOT NULL, payload_json TEXT NOT NULL)")
            db.commit()
        finally:
            db.close()
    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
    @staticmethod
    def key(context: dict[str, Any]) -> str:
        canonical = json.dumps({"schema_version": CACHE_SCHEMA_VERSION, **context}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    @classmethod
    def fingerprint_key(cls, fingerprint: AnalysisContextFingerprint) -> str:
        return cls.key(fingerprint.context())
    def get_fingerprint(self, target_kind: str, target_id: str, fingerprint: AnalysisContextFingerprint) -> dict[str, Any] | None:
        return self.get(target_kind, target_id, fingerprint.context()) if fingerprint.reusable() else None
    def put_fingerprint(self, target_kind: str, target_id: str, fingerprint: AnalysisContextFingerprint, payload: dict[str, Any]) -> None:
        if fingerprint.reusable(): self.put(target_kind, target_id, fingerprint.context(), payload)
    def get(self, target_kind: str, target_id: str, context: dict[str, Any]) -> dict[str, Any] | None:
        key = self.key(context)
        db = self._connect()
        try:
            row = db.execute("SELECT payload_json FROM entries WHERE cache_key=? AND target_kind=? AND target_id=?", (key, target_kind, target_id)).fetchone()
        finally:
            db.close()
        return json.loads(row[0]) if row else None
    def put(self, target_kind: str, target_id: str, context: dict[str, Any], payload: dict[str, Any]) -> None:
        key = self.key(context)
        db = self._connect()
        try:
            db.execute("INSERT OR REPLACE INTO entries(cache_key,target_kind,target_id,context_json,payload_json) VALUES(?,?,?,?,?)", (key, target_kind, target_id, json.dumps(context, sort_keys=True), json.dumps(payload, sort_keys=True)))
            db.commit()
        finally:
            db.close()
    def invalidate(self, impact: ChangeImpactReport) -> int:
        exact = [(item.kind, item.target_id) for item in impact.impacts if item.certainty == "EXACT"]
        db = self._connect()
        try:
            count = sum(db.execute("DELETE FROM entries WHERE target_kind=? AND target_id=?", item).rowcount for item in exact)
            db.commit()
        finally:
            db.close()
        return count
