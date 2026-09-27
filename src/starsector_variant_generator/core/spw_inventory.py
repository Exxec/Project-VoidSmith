"""Optional read-only SPW identity evidence; never changes scan or fit results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "spw-mod-inventory-1"


def review_spw_inventory(path: Path, installation: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA or not isinstance(raw.get("mods"), list):
        raise ValueError("Unsupported SPW mod inventory")
    root = installation.resolve()
    if Path(raw.get("installation_path", "")).resolve() != root:
        return {"status": "CHANGED_INSTALLATION", "mods": [], "limitations": ["Inventory was captured from another installation"]}
    enabled_file = root / "mods" / "enabled_mods.json"
    expected_enabled_hash = raw.get("enabled_mods_sha256")
    actual_enabled_hash = hashlib.sha256(enabled_file.read_bytes()).hexdigest() if enabled_file.is_file() else None
    if expected_enabled_hash != actual_enabled_hash:
        return {"status": "CHANGED_INSTALLATION", "mods": [], "limitations": ["Enabled-mod list changed since SPW inventory"]}
    reviewed = []
    ids = [mod.get("id") for mod in raw["mods"] if isinstance(mod, dict)]
    for mod in raw["mods"]:
        if not isinstance(mod, dict) or not isinstance(mod.get("relative_root"), str):
            raise ValueError("Invalid SPW mod record")
        rel = Path(mod["relative_root"])
        target = (root / rel).resolve()
        if rel.is_absolute() or not target.is_relative_to(root):
            raise ValueError("Unsafe SPW mod path")
        metadata = target / ("mod_info.json.disabled" if mod.get("metadata_status") == "DISABLED" else "mod_info.json")
        expected = mod.get("metadata_sha256")
        actual = hashlib.sha256(metadata.read_bytes()).hexdigest() if metadata.is_file() else None
        jars_match = True
        for jar in mod.get("jars", []):
            if not isinstance(jar, dict) or not isinstance(jar.get("path"), str):
                jars_match = False
                break
            jar_path = (root / jar["path"]).resolve()
            if not jar_path.is_relative_to(root) or not jar_path.is_file():
                jars_match = False
                break
            jars_match = jars_match and hashlib.sha256(jar_path.read_bytes()).hexdigest() == jar.get("sha256")
        valid_metadata = mod.get("metadata_status") in {"OK", "DISABLED"}
        state = "MATCH" if expected and expected == actual and jars_match and valid_metadata and ids.count(mod.get("id")) == 1 and not mod.get("duplicate_id") else "UNKNOWN"
        reviewed.append({"id": mod.get("id"), "relative_root": rel.as_posix(), "state": state,
                         "enabled": mod.get("enabled"), "reason": None if state == "MATCH" else "missing, changed or ambiguous metadata"})
    return {"status": "REVIEWED", "mods": reviewed, "limitations": ["Identity context only; no fit legality or recommendation claim"]}
