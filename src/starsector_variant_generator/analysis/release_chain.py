"""Optional source-to-published-asset evidence for a portable release."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = "voidsmith-release-chain-1"
STATES = {"PASS", "FAIL", "NOT_RUN", "UNKNOWN"}
GATES = ("source", "build", "tests", "native", "live", "rights", "publication")


def verify_release_chain(archive: Path, evidence_file: Path | None = None,
                         downloaded_asset: Path | None = None) -> dict[str, object]:
    """Check asserted evidence against supplied bytes; never infer an absent gate."""
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    gates: dict[str, dict[str, object]] = {name: {"state": "NOT_RUN", "evidence": None} for name in GATES}
    findings: list[str] = []
    if evidence_file is not None:
        raw = json.loads(evidence_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA:
            raise ValueError("Unsupported release-chain schema")
        if not isinstance(raw.get("gates", {}), dict):
            raise ValueError("Release-chain gates must be an object")
        if raw.get("archive_sha256") != archive_hash:
            findings.append("Evidence archive SHA-256 does not match supplied archive")
        source = raw.get("source")
        if not isinstance(source, dict) or not re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit", ""))):
            findings.append("Exact source commit is missing or invalid")
        elif source.get("clean") is not True:
            findings.append("Clean source input is not evidenced")
        else:
            gates["source"] = {"state": "UNKNOWN", "evidence": source,
                               "limitation": "Source record is hash-bound to this archive but not independently authenticated"}
        for name in GATES[1:]:
            item = (raw.get("gates") or {}).get(name)
            if item is None:
                continue
            if not isinstance(item, dict) or item.get("state") not in STATES:
                raise ValueError(f"Invalid {name} gate")
            gates[name] = {"state": item["state"], "evidence": item.get("evidence"), "date": item.get("date")}
            if item["state"] == "PASS" and (not item.get("evidence") or not item.get("date")):
                gates[name]["state"] = "UNKNOWN"
                findings.append(f"{name} PASS lacks dated evidence")
    if downloaded_asset is not None:
        downloaded_hash = hashlib.sha256(downloaded_asset.read_bytes()).hexdigest()
        gates["publication"] = {
            "state": "UNKNOWN" if downloaded_hash == archive_hash else "FAIL",
            "evidence": str(downloaded_asset), "sha256": downloaded_hash,
            "asset_bytes_match": downloaded_hash == archive_hash,
        }
        if downloaded_hash != archive_hash:
            findings.append("Downloaded asset differs from local archive")
    elif gates["publication"]["state"] == "PASS":
        gates["publication"]["state"] = "UNKNOWN"
        findings.append("Publication PASS requires a separately supplied downloaded asset")
    if findings:
        gates["build"]["state"] = "FAIL" if any("archive SHA-256" in item for item in findings) else gates["build"]["state"]
    return {"schema_version": SCHEMA, "archive_sha256": archive_hash, "gates": gates, "findings": findings}
