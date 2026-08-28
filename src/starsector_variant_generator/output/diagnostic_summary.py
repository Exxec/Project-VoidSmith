"""Compact, conservative classification for read-only scan diagnostics."""
from __future__ import annotations

from collections import Counter

from starsector_variant_generator.core.models import ScanResult


def summarize_scan_issues(scan: ScanResult) -> dict[str, object]:
    """Classify only the scanner's own explicit messages, never source semantics."""
    return {
        "error_categories": dict(sorted(Counter(_error_category(error) for error in scan.errors).items())),
        "warning_categories": dict(sorted(Counter(_warning_category(warning) for warning in scan.warnings).items())),
        "environment_categories": dict(sorted(Counter(_environment_category(item) for item in scan.skipped_entities).items())),
    }


def _error_category(message: str) -> str:
    if "codec can't decode" in message:
        return "UNSUPPORTED_ENCODING"
    if "Extra data:" in message:
        return "MALFORMED_OR_CONCATENATED_DATA"
    if "Expecting value:" in message:
        return "MALFORMED_VALUE"
    return "OTHER_PARSE_ERROR"


def _warning_category(message: str) -> str:
    if "baseHullId" in message and "unresolved" in message:
        return "UNRESOLVED_SKIN_BASE_HULL"
    if "baseHullId" in message and "ambiguous" in message:
        return "AMBIGUOUS_SKIN_BASE_HULL"
    return "OTHER_WARNING"


def _environment_category(message: str) -> str:
    if message.startswith("Enabled mod not discovered:"):
        return "STALE_ENABLED_MOD_REFERENCE"
    if " row without a stable id skipped" in message:
        return "MISSING_STABLE_ID_ROW"
    return "OTHER_SKIPPED_ENTITY"
