"""A first, narrow slice of `AGENTS.md`'s "Automatic Faction Capability Analysis".

Root `ROADMAP.md` phase 6. The spec's own wording: "build a useful faction
capability profile from installed mod data alone using parseable hulls,
weapons, fighters, variants, built-ins, known hullmod effects, and role
classifications." This module does exactly that and nothing more -- it
reuses `classify_hull`'s already-tested, non-exclusive role-compatibility
scores and `classify_civilian_role`'s hint-based evidence tags over a
faction's own parsed `known_hulls`, rather than inventing a new scoring
mechanism.

Deliberately NOT attempted here (left for later, evidence-gated
phases -- see root `ROADMAP.md` phases 6/9/10): a single combined
"gap" verdict, a confidence score, NATIVE/RETROFIT/ACQUISITION shortlists,
or "why not" explanations. Those need their own defensible methodology;
reporting raw per-role best-hull evidence lets a caller (or a future GUI)
apply its own threshold without this module fabricating one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from starsector_variant_generator.analysis.capability_vector import (
    CapabilityEvidence,
    infer_hull_capability_vector,
)
from starsector_variant_generator.analysis.classification import (
    classify_civilian_role,
    classify_hull,
)
from starsector_variant_generator.core.heuristics import get_heuristic_set
from starsector_variant_generator.core.models import Faction, Hull
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class RoleCapability:
    role: str
    best_hull_id: str | None
    best_score: float
    hulls_examined: int


@dataclass(frozen=True)
class FactionCapabilityProfile:
    faction_id: str
    known_hulls_examined: int
    unresolved_known_hull_ids: tuple[str, ...]
    role_capabilities: tuple[RoleCapability, ...]
    civilian_role_coverage: tuple[str, ...]
    capability_vector: dict[str, CapabilityEvidence] = field(default_factory=dict)
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    capability_gaps: tuple[str, ...] = ()


def analyze_faction_capability(faction: Faction, registry: Registry, heuristic_set: str = "baseline_0.5") -> FactionCapabilityProfile:
    """Score a faction's real known hulls against `classify_hull`'s role-compatibility axes.

    A hull id in `faction.known_hulls` that isn't indexed (a real gap in
    scanned data, not a faction with no capability) is reported in
    `unresolved_known_hull_ids` rather than silently treated as absent.
    """
    resolved: list[tuple[str, Hull]] = []
    unresolved: list[str] = []
    for hull_id in faction.known_hulls:
        hull = registry.hulls.by_id.get(hull_id)
        if hull is None:
            unresolved.append(hull_id)
        else:
            resolved.append((hull_id, hull))

    role_scores: dict[str, list[tuple[float, str]]] = {}
    civilian_roles: set[str] = set()
    for hull_id, hull in resolved:
        for role, score in classify_hull(hull).role_compatibility.items():
            role_scores.setdefault(role, []).append((score, hull_id))
        civilian_roles.update(classify_civilian_role(hull).role_tags)

    role_capabilities = tuple(
        _best_role_capability(role, scores)
        for role, scores in sorted(role_scores.items())
    )
    capability_vector = _aggregate_capability_vectors([hull for _, hull in resolved], registry)
    heuristics = get_heuristic_set(heuristic_set).values
    strengths = tuple(sorted(name for name, evidence in capability_vector.items() if evidence.score is not None and evidence.score >= heuristics["gap_strong_threshold"]))
    weaknesses = tuple(sorted(name for name, evidence in capability_vector.items() if evidence.score is not None and heuristics["gap_weak_threshold"] <= evidence.score < heuristics["gap_adequate_threshold"]))
    gaps = tuple(sorted(name for name, evidence in capability_vector.items() if evidence.score is not None and evidence.score < heuristics["gap_weak_threshold"]))
    return FactionCapabilityProfile(
        faction_id=faction.id,
        known_hulls_examined=len(resolved),
        unresolved_known_hull_ids=tuple(unresolved),
        role_capabilities=role_capabilities,
        civilian_role_coverage=tuple(sorted(civilian_roles)),
        capability_vector=capability_vector,
        strengths=strengths,
        weaknesses=weaknesses,
        capability_gaps=gaps,
    )


def _best_role_capability(role: str, scores: list[tuple[float, str]]) -> RoleCapability:
    best_score = max(score for score, _ in scores)
    # Deterministic tie-break: highest score, then lowest hull id.
    best_hull_id = min(hull_id for score, hull_id in scores if score == best_score)
    return RoleCapability(role, best_hull_id, best_score, len(scores))


def _aggregate_capability_vectors(hulls: list[Hull], registry: Registry) -> dict[str, CapabilityEvidence]:
    per_dimension: dict[str, list[tuple[CapabilityEvidence, str]]] = {}
    for hull in hulls:
        for name, evidence in infer_hull_capability_vector(hull, registry).dimensions.items():
            per_dimension.setdefault(name, []).append((evidence, hull.id))
    aggregate: dict[str, CapabilityEvidence] = {}
    for name, candidates in sorted(per_dimension.items()):
        available = [(evidence, hull_id) for evidence, hull_id in candidates if evidence.score is not None]
        if not available:
            aggregate[name] = CapabilityEvidence(None, 0.0, "UNKNOWN", ("No faction hull supplied available evidence for this capability.",))
            continue
        best, hull_id = max(available, key=lambda item: (item[0].score or 0.0, item[0].confidence, item[1]))
        aggregate[name] = CapabilityEvidence(best.score, best.confidence, "AVAILABLE", (f"Best faction hull: {hull_id}.", *best.supporting_evidence))
    return aggregate
