"""Offline verification for a VoidSmith portable release archive.

The verifier reads an archive and its optional adjacent checksum without
extracting or executing either.  It verifies the package's own inventory,
which intentionally excludes Starsector and mod data.
"""
from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


RELEASE_MANIFEST_SCHEMA = "voidsmith-portable-release-1"


@dataclass(frozen=True)
class ReleaseVerification:
    archive: Path
    archive_sha256: str
    platform: str | None
    version: str | None
    manifest_found: bool
    manifest_valid: bool
    checksum_status: str
    inventory_status: str
    findings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.manifest_valid and self.checksum_status in {"MATCH", "NOT_PROVIDED"} and self.inventory_status == "MATCH"


def verify_portable_release(archive: Path, checksum: Path | None = None) -> ReleaseVerification:
    """Verify a ZIP or tar.gz portable archive without writing to disk."""
    archive = archive.resolve()
    if not archive.is_file():
        raise ValueError(f"Release archive does not exist: {archive}")
    payloads = _archive_files(archive)
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_name = next((name for name in sorted(payloads) if name.endswith("/release-manifest.json") or name == "release-manifest.json"), None)
    findings: list[str] = []
    if manifest_name is None:
        return ReleaseVerification(archive, archive_hash, None, None, False, False, _checksum_status(archive, archive_hash, checksum), "NOT_CHECKED", ("release-manifest.json is missing.",))
    try:
        manifest = json.loads(payloads[manifest_name].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return ReleaseVerification(archive, archive_hash, None, None, True, False, _checksum_status(archive, archive_hash, checksum), "NOT_CHECKED", (f"release-manifest.json is unreadable: {exc}",))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        findings.append("Unsupported release manifest schema.")
    if manifest.get("product") != "VoidSmith":
        findings.append("Manifest product is not VoidSmith.")
    platform = manifest.get("platform") if isinstance(manifest.get("platform"), str) else None
    version = manifest.get("version") if isinstance(manifest.get("version"), str) else None
    if platform not in {"windows-x64", "linux-x64"}:
        findings.append("Manifest platform is missing or unsupported.")
    if not version:
        findings.append("Manifest version is missing.")
    inventory_status = _verify_inventory(payloads, manifest_name, manifest, findings)
    checksum_status = _checksum_status(archive, archive_hash, checksum)
    if checksum_status == "MISMATCH":
        findings.append("Archive SHA-256 does not match the supplied checksum file.")
    if checksum_status == "INVALID":
        findings.append("Checksum file does not contain a valid SHA-256 entry for this archive.")
    manifest_valid = (
        isinstance(manifest, dict)
        and manifest.get("schema_version") == RELEASE_MANIFEST_SCHEMA
        and manifest.get("product") == "VoidSmith"
        and platform in {"windows-x64", "linux-x64"}
        and bool(version)
        and isinstance(manifest.get("files"), list)
    )
    return ReleaseVerification(archive, archive_hash, platform, version, True, manifest_valid, checksum_status, inventory_status, tuple(findings))


def _archive_files(archive: Path) -> dict[str, bytes]:
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as package:
            return {entry.filename: package.read(entry) for entry in package.infolist() if not entry.is_dir()}
    if archive.name.endswith(".tar.gz") or archive.suffix.lower() in {".tgz", ".tar"}:
        with tarfile.open(archive, "r:*") as package:
            files: dict[str, bytes] = {}
            for entry in package.getmembers():
                if entry.isfile():
                    extracted = package.extractfile(entry)
                    assert extracted is not None
                    files[entry.name] = extracted.read()
            return files
    raise ValueError("Release archive must be .zip, .tar.gz, .tgz, or .tar")


def _verify_inventory(payloads: dict[str, bytes], manifest_name: str, manifest: dict[str, object], findings: list[str]) -> str:
    records = manifest.get("files")
    if not isinstance(records, list):
        findings.append("Manifest has no file inventory.")
        return "INVALID"
    root = manifest_name.removesuffix("release-manifest.json")
    expected: dict[str, tuple[int, str]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("bytes"), int) or not isinstance(record.get("sha256"), str):
            findings.append("Manifest contains an invalid inventory record.")
            return "INVALID"
        path = record["path"]
        if path.startswith("/") or ".." in Path(path).parts:
            findings.append("Manifest contains an unsafe inventory path.")
            return "INVALID"
        expected[path] = (record["bytes"], record["sha256"].lower())
    actual = {name.removeprefix(root): data for name, data in payloads.items() if name != manifest_name and name.startswith(root)}
    if set(actual) != set(expected):
        findings.append("Archive contents do not match the manifest inventory.")
        return "MISMATCH"
    for path, data in actual.items():
        expected_size, expected_hash = expected[path]
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_hash:
            findings.append(f"Inventory hash mismatch: {path}")
            return "MISMATCH"
    return "MATCH"


def _checksum_status(archive: Path, archive_hash: str, checksum: Path | None) -> str:
    if checksum is None:
        return "NOT_PROVIDED"
    if not checksum.is_file():
        return "INVALID"
    tokens = checksum.read_text(encoding="ascii", errors="replace").strip().split()
    if not tokens or len(tokens[0]) != 64 or any(char not in "0123456789abcdefABCDEF" for char in tokens[0]):
        return "INVALID"
    if len(tokens) > 1 and tokens[1].lstrip("*") != archive.name:
        return "INVALID"
    return "MATCH" if tokens[0].lower() == archive_hash else "MISMATCH"
