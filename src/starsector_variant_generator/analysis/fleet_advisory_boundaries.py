"""Evidence-limited fleet advisory views, separate from recommendation logic.

Neither result below changes legality, Fleet Support ranking, fitting score, or
combat-outcome claims. They expose the exact boundary of data that is present
today so callers do not turn an absent campaign/stat field into a guessed zero.
"""
from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.analysis.fleet_support import FleetSelection
from starsector_variant_generator.core.knowledge_packs import ResolvedKnowledgePack, officer_guidance
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class DeploymentPointAdvisory:
    """A deliberately unavailable view until DP is a normalized source field."""
    status: str  # NOT_DETERMINABLE
    total_deployment_points: None
    selected_entries: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class OfficerGuidanceEntry:
    role: str | None
    notes: str | None
    confidence: float


@dataclass(frozen=True)
class OfficerGuidanceAdvisory:
    status: str  # PACK_GUIDANCE_AVAILABLE | NOT_DETERMINABLE
    entries: tuple[OfficerGuidanceEntry, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class FleetAdvisoryBoundaries:
    deployment_points: DeploymentPointAdvisory
    officer_guidance: OfficerGuidanceAdvisory


def fleet_advisory_boundaries(
    selections: tuple[FleetSelection, ...], registry: Registry,
    faction_id: str | None = None, knowledge_pack: ResolvedKnowledgePack | None = None,
) -> FleetAdvisoryBoundaries:
    """Return only direct/curated advisory evidence currently modeled."""
    labels = tuple(selection.variant_id or selection.hull_id or "<empty>" for selection in selections)
    deployment = DeploymentPointAdvisory(
        "NOT_DETERMINABLE", None, labels,
        ("Deployment points are not a normalized field in the current hull schema; no total or budget fit was inferred.",),
    )
    raw_guidance = officer_guidance(knowledge_pack, faction_id) if faction_id else ()
    entries = tuple(
        OfficerGuidanceEntry(
            item.get("role") if isinstance(item.get("role"), str) else None,
            item.get("notes") if isinstance(item.get("notes"), str) else None,
            float(item["guidance_confidence"]),
        )
        for item in raw_guidance
        if isinstance(item.get("guidance_confidence"), (int, float))
    )
    officers = OfficerGuidanceAdvisory(
        "PACK_GUIDANCE_AVAILABLE" if entries else "NOT_DETERMINABLE", entries,
        ("Officer entries are optional knowledge-pack guidance only; campaign officer, skill, and assignment state was not read or inferred.",),
    )
    return FleetAdvisoryBoundaries(deployment, officers)
