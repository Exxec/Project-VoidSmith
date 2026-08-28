"""Read-only audit of the deliberately bounded complex-hull acceptance model.

The audit does not infer a module graph for gameplay.  It only reports whether
parseable source structures remain within :mod:`complex_hulls`' explicit
acceptance boundary.  This keeps diagnostics useful without turning raw
variant ``modules`` records into composite scoring or legality evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from starsector_variant_generator.analysis.complex_hulls import (
    COMPLEX_HULL_ACCEPTANCE_MATRIX,
    ComplexHullAcceptance,
)
from starsector_variant_generator.analysis.composite_hulls import (
    build_composite_hull_definitions,
    build_composite_ship_profiles,
    classify_hull_definition,
)
from starsector_variant_generator.core.models import ScanResult, Variant
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class ComplexHullAuditFinding:
    """A compact, local-only audit observation without copied source records."""

    severity: str  # INFO | WARNING
    code: str
    source_mod: str
    hull_id: str | None
    variant_id: str | None
    detail: str


def audit_complex_hulls(scan: ScanResult, registry: Registry) -> dict[str, Any]:
    """Audit parseable module references without resolving composite behavior.

    Variant module maps are intentionally inspected only as provenance.  A
    referenced child variant is checked for an unambiguous, separately parsed
    hull; missing/ambiguous children are warnings, never guesses.
    """
    findings: list[ComplexHullAuditFinding] = []
    # HullDefinition formalizes what used to be four independent inline
    # hull_hints string-matching comprehensions (Phase 27) into one
    # classification per hull, computed once and reused for every grouping
    # below -- see analysis/composite_hulls.py's module docstring.
    hull_definitions = [classify_hull_definition(hull) for hull in scan.hulls]
    parents = [hull for hull, definition in zip(scan.hulls, hull_definitions) if definition.is_parent]
    modules = [hull for hull, definition in zip(scan.hulls, hull_definitions) if definition.is_module]
    under_parent = [hull for hull, definition in zip(scan.hulls, hull_definitions) if definition.is_under_parent]
    stations = [hull for hull, definition in zip(scan.hulls, hull_definitions) if definition.is_station]

    for hull in parents:
        if hull.id in registry.hulls.duplicates:
            findings.append(ComplexHullAuditFinding(
                "WARNING", "AMBIGUOUS_COMPLEX_PARENT", hull.source_mod, hull.id, None,
                "Parent hull ID has multiple installed source records; no source is selected by guessing.",
            ))

    composite_profiles = build_composite_ship_profiles(scan, registry)
    module_variants = len(composite_profiles)
    module_mappings = sum(len(profile.modules) for profile in composite_profiles)
    repeated_mappings = 0
    unresolved_child_variants = 0
    unresolved_child_hulls = 0
    parent_without_hint = 0
    for variant in scan.variants:
        mappings = _module_targets(variant)
        if mappings is None:
            continue
        if variant.hull_id:
            parent = registry.hulls.by_id.get(variant.hull_id)
            if parent is None:
                if variant.hull_id in registry.hulls.duplicates:
                    findings.append(ComplexHullAuditFinding(
                        "WARNING", "AMBIGUOUS_MODULE_PARENT", variant.source_mod, variant.hull_id, variant.id,
                        "Variant declares module mappings, but the parent hull is ambiguous.",
                    ))
                else:
                    findings.append(ComplexHullAuditFinding(
                        "WARNING", "MISSING_MODULE_PARENT", variant.source_mod, variant.hull_id, variant.id,
                        "Variant declares module mappings, but its parent hull was not parsed.",
                    ))
            elif not classify_hull_definition(parent).is_parent:
                parent_without_hint += 1
                findings.append(ComplexHullAuditFinding(
                    "WARNING", "MODULE_MAP_WITHOUT_PARENT_HINT", variant.source_mod, variant.hull_id, variant.id,
                    "Variant declares module mappings without the parent SHIP_WITH_MODULES structural hint.",
                ))
        if len(mappings) != len(set(mappings)):
            repeated_mappings += 1
            findings.append(ComplexHullAuditFinding(
                "INFO", "REPEATED_MODULE_MAPPING", variant.source_mod, variant.hull_id, variant.id,
                "Repeated child references are retained only as raw provenance; multiplicity is not scored.",
            ))
        for child_variant_id in mappings:
            child_variant = registry.variants.by_id.get(child_variant_id)
            if child_variant is None:
                unresolved_child_variants += 1
                findings.append(ComplexHullAuditFinding(
                    "WARNING", "UNRESOLVED_MODULE_VARIANT", variant.source_mod, variant.hull_id, variant.id,
                    "A module mapping references a missing or ambiguous child variant; no child behavior is inferred.",
                ))
                continue
            if not child_variant.hull_id or child_variant.hull_id not in registry.hulls.by_id:
                unresolved_child_hulls += 1
                findings.append(ComplexHullAuditFinding(
                    "WARNING", "UNRESOLVED_MODULE_HULL", variant.source_mod, variant.hull_id, variant.id,
                    "A child variant lacks an unambiguous separately parsed hull; local module fitting is unavailable.",
                ))

    # Hull-type-level composite declarations (Phase 27, additive):
    # CompositeHullDefinition ties each parent hull's declared structural
    # hint to the observed evidence (how many of its own variants actually
    # carry module maps, and which distinct child hull ids they reference),
    # separate from CompositeShipProfile's per-ship-instance records above.
    hull_definitions_composite = build_composite_hull_definitions(scan, registry)

    return {
        "schema_version": "complex-hull-audit-0.3",
        "acceptance": {entry.feature.value: entry.acceptance.value for entry in COMPLEX_HULL_ACCEPTANCE_MATRIX},
        "summary": {
            "parent_hulls_with_structural_hint": len(parents),
            "module_hulls": len(modules),
            "under_parent_hulls": len(under_parent),
            "station_hulls": len(stations),
            "variants_with_module_maps": module_variants,
            "module_mappings": module_mappings,
            "repeated_module_mappings": repeated_mappings,
            "module_maps_without_parent_hint": parent_without_hint,
            "unresolved_child_variants": unresolved_child_variants,
            "unresolved_child_hulls": unresolved_child_hulls,
            "warning_count": sum(finding.severity == "WARNING" for finding in findings),
        },
        "findings": [asdict(finding) for finding in findings],
        "structural_profiles": [asdict(profile) for profile in composite_profiles],
        "composite_hull_definitions": [asdict(definition) for definition in hull_definitions_composite],
        "scope_note": (
            "Composite profiles record structural parent-slot-child references only. This audit does not merge "
            "child mounts, systems, shields, or survivability into a parent and does not execute scripts."
        ),
    }


def _module_targets(variant: Variant) -> list[str] | None:
    raw_modules = variant.raw.get("modules")
    # Empty arrays are common normal variant serialization and do not mean the
    # variant has a module relationship.  Audit only an actual mapping.
    if not isinstance(raw_modules, list) or not raw_modules:
        return None
    targets: list[str] = []
    for mapping in raw_modules:
        if not isinstance(mapping, dict):
            continue
        targets.extend(str(target) for target in mapping.values() if isinstance(target, str) and target)
    return targets
