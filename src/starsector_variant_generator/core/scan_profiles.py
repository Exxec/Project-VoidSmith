"""Read-only persisted scan contexts; never mod-manager loadouts.

Profiles record the source context that an analysis used. They are stored under
the application output directory and may be compared with a later scan, but
there is deliberately no operation that writes a game's enabled-mod settings.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from starsector_variant_generator.core.cache import build_manifest
from starsector_variant_generator.core.models import ScanResult, SourceType

SCAN_PROFILE_SCHEMA_VERSION = "scan-profile-0.1"


@dataclass(frozen=True)
class ScanProfile:
    profile_id: str
    name: str
    installation_path: str
    enabled_mod_ids: tuple[str, ...]
    manifest_hash: str
    created_at: str
    updated_at: str
    schema_version: str = SCAN_PROFILE_SCHEMA_VERSION


@dataclass(frozen=True)
class ScanProfileDiff:
    profile_id: str
    status: str  # UNCHANGED | CHANGED_INSTALLATION | CHANGED_LOADOUT | CHANGED_SOURCES
    added_mod_ids: tuple[str, ...]
    removed_mod_ids: tuple[str, ...]
    manifest_changed: bool


@dataclass(frozen=True)
class ExternalModProfilePreview:
    """Explicit import preview for a third-party profile; never an activator."""
    provider: str
    profile_name: str
    mod_ids: tuple[str, ...]
    ignored_variant_metadata: tuple[str, ...]


def create_scan_profile(name: str, installation_path: Path, scan: ScanResult, now: datetime | None = None) -> ScanProfile:
    if not name.strip():
        raise ValueError("Scan profile name must not be empty")
    timestamp = (now or datetime.now(UTC)).isoformat()
    return ScanProfile(str(uuid4()), name.strip(), str(installation_path.resolve()), _enabled_mod_ids(scan), _manifest_hash(scan), timestamp, timestamp)


def diff_scan_profile(profile: ScanProfile, installation_path: Path, scan: ScanResult) -> ScanProfileDiff:
    current_ids = _enabled_mod_ids(scan)
    added = tuple(sorted(set(current_ids) - set(profile.enabled_mod_ids)))
    removed = tuple(sorted(set(profile.enabled_mod_ids) - set(current_ids)))
    manifest_changed = profile.manifest_hash != _manifest_hash(scan)
    if Path(profile.installation_path) != installation_path.resolve():
        status = "CHANGED_INSTALLATION"
    elif added or removed:
        status = "CHANGED_LOADOUT"
    elif manifest_changed:
        status = "CHANGED_SOURCES"
    else:
        status = "UNCHANGED"
    return ScanProfileDiff(profile.profile_id, status, added, removed, manifest_changed)


def save_scan_profiles(path: Path, profiles: tuple[ScanProfile, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": SCAN_PROFILE_SCHEMA_VERSION, "profiles": [asdict(profile) for profile in profiles]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_scan_profiles(path: Path) -> tuple[ScanProfile, ...]:
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != SCAN_PROFILE_SCHEMA_VERSION or not isinstance(raw.get("profiles"), list):
        raise ValueError(f"Unsupported scan profile file: {path}")
    profiles: list[ScanProfile] = []
    required = {"profile_id", "name", "installation_path", "enabled_mod_ids", "manifest_hash", "created_at", "updated_at"}
    for record in raw["profiles"]:
        if not isinstance(record, dict) or not required.issubset(record) or not all(isinstance(record[key], str) for key in required - {"enabled_mod_ids"}):
            raise ValueError("Invalid scan profile record")
        ids = record["enabled_mod_ids"]
        if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
            raise ValueError("Scan profile enabled_mod_ids must be text")
        profiles.append(ScanProfile(**{**record, "enabled_mod_ids": tuple(ids)}))
    return tuple(profiles)


def import_trios_profile(path: Path, profile_name: str | None = None) -> ExternalModProfilePreview:
    """Read current TriOS v2 profile JSON as an analysis-only ID preview.

    This reads no TriOS app settings/install metadata and never writes the
    imported file. Variant/version tokens remain non-authoritative audit notes
    because the scanner's membership key is a mod ID.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    profiles = raw.get("modProfiles") if isinstance(raw, dict) else None
    if not isinstance(profiles, list):
        raise TypeError("TriOS modProfiles must be a list")
    choices = [item for item in profiles if isinstance(item, dict) and isinstance(item.get("name"), str)]
    if profile_name is not None:
        choices = [item for item in choices if item["name"] == profile_name]
    if len(choices) != 1:
        raise ValueError(f"TriOS profile not found or ambiguous: {profile_name or '(select a unique profile)'}")
    selected = choices[0]
    variants = selected.get("enabledModVariants")
    if not isinstance(variants, list):
        raise TypeError("TriOS enabledModVariants must be a list")
    mod_ids: list[str] = []
    ignored: list[str] = []
    for variant in variants:
        if not isinstance(variant, dict) or not isinstance(variant.get("modId"), str) or not variant["modId"]:
            ignored.append("invalid variant record")
            continue
        mod_ids.append(variant["modId"])
        token = variant.get("smolVariantId")
        if isinstance(token, str) and token:
            ignored.append(f"{variant['modId']}: external variant token preserved as non-authoritative")
    return ExternalModProfilePreview("TriOS", selected["name"], tuple(sorted(set(mod_ids))), tuple(ignored))


def _enabled_mod_ids(scan: ScanResult) -> tuple[str, ...]:
    return tuple(sorted(source.mod_id for source in scan.mods if source.source_type is SourceType.MOD and source.enabled is True))


def _manifest_hash(scan: ScanResult) -> str:
    canonical = json.dumps(build_manifest(scan), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
