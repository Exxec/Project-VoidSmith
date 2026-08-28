"""Evidence-bounded multidimensional warfare posture for a hull.

This is descriptive analysis, not a combat simulator, legality rule, or
recommendation score input.  Each axis is multi-valued and retains the raw
structural facts that support it.  Labels needing runtime AI, weapon ammo,
ship-system, or fleet-composition behavior are intentionally absent.
"""
from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.analysis.mechanical_archetypes import HullFeatureVector, infer_hull_feature_vector
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Variant
from starsector_variant_generator.core.registry import Registry


@dataclass(frozen=True)
class DoctrineAxisProfile:
    scores: dict[str, float]
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CombatDoctrineProfile:
    hull_id: str
    battlefield_function: DoctrineAxisProfile
    engagement_position: DoctrineAxisProfile
    tactical_style: DoctrineAxisProfile
    tempo: DoctrineAxisProfile
    commitment: DoctrineAxisProfile
    fleet_dependence: DoctrineAxisProfile
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


def infer_combat_doctrine(
    hull: Hull, registry: Registry | None = None, variants: tuple[Variant, ...] | None = None,
) -> CombatDoctrineProfile:
    """Infer only posture that follows directly from parsed static evidence."""
    f = infer_hull_feature_vector(hull, registry, variants)
    total = max(f.mount_count, 1)
    heavy = _clamp((f.medium_mounts + f.large_mounts) / total)
    small = _clamp(f.small_mounts / total)
    large = _clamp(f.large_mounts / total)
    missile = _clamp(f.missile_mounts / total)
    narrow = f.narrow_arc_mount_fraction or 0.0
    armor = _scale(f.armor_rating, 1500.0)
    integrity = _scale(f.hull_hitpoints, 15000.0)
    defense = (armor + integrity) / 2.0
    flux = _mean(_scale(f.flux_capacity, 20000.0), _scale(f.flux_dissipation, 1500.0))
    speed = _scale(f.max_speed, 120.0)
    maneuver = _mean(_scale(f.acceleration, 100.0), _scale(f.max_turn_rate, 100.0), _scale(f.turn_acceleration, 100.0))
    long_range = f.variant_long_range_weapon_fraction or 0.0
    pd = f.variant_pd_weapon_fraction or 0.0
    bays = _clamp((f.fighter_bays or 0) / 4.0)
    sustained = _mean(_scale(f.flux_dissipation, 1500.0), _scale(f.flux_capacity, 20000.0), heavy)
    facts = _facts(f)
    structural_confidence = _known_fraction(f.armor_rating, f.hull_hitpoints, f.max_speed, f.flux_dissipation, f.mount_count)
    variant_confidence = 1.0 if f.existing_variant_count else 0.55

    battlefield = {
        "LINE_ANCHOR": _clamp(.38 * defense + .25 * flux + .22 * heavy + .15 * (1.0 - speed)),
        "FIRE_SUPPORT": _clamp(.45 * long_range + .25 * large + .20 * flux + .10 * (1.0 - speed)),
        "SCREENING": _clamp(.42 * small + .36 * pd + .12 * speed + .10 * maneuver),
        "FLANKING": _clamp(.58 * speed + .32 * maneuver + .10 * heavy),
        "PURSUIT": _clamp(.65 * speed + .35 * maneuver),
        "STRIKE": _clamp(.30 * heavy + .25 * narrow + .25 * speed + .20 * maneuver),
        "CARRIER_SUPPORT": _clamp(.75 * bays + .15 * defense + .10 * pd),
        "SUPPRESSION": _clamp(.48 * long_range + .28 * flux + .24 * missile),
    }
    position = {
        "FRONT_LINE": _clamp(.42 * defense + .28 * flux + .20 * heavy + .10 * (1.0 - speed)),
        "SECOND_LINE": _clamp(.46 * long_range + .24 * flux + .18 * heavy + .12 * defense),
        "BACK_LINE": _clamp(.50 * long_range + .28 * bays + .22 * missile),
        "FLANK": _clamp(.60 * speed + .30 * maneuver + .10 * narrow),
        "FREE_ROAM": _clamp(.55 * speed + .35 * maneuver + .10 * flux),
    }
    style = {
        "SUSTAINED_ASSAULT": _clamp(.45 * sustained + .25 * heavy + .20 * defense + .10 * flux),
        "STANDOFF": _clamp(.60 * long_range + .20 * large + .20 * flux),
        "ARTILLERY": _clamp(.48 * long_range + .30 * large + .22 * narrow),
        "SKIRMISH": _clamp(.55 * speed + .35 * maneuver + .10 * flux),
        "MISSILE_ALPHA": _clamp(.70 * missile + .30 * (f.variant_missile_mount_fraction or 0.0)),
    }
    # Ammo, cooldown, and system cycles are not normalized, so BURST,
    # AMMO_LIMITED, and SYSTEM_DEPENDENT are deliberately not emitted.
    tempo = {"SUSTAINED": round(sustained, 6)}
    commitment = {
        "LOW_COMMITMENT": _clamp(.60 * speed + .40 * maneuver),
        "HIGH_COMMITMENT": _clamp(.35 * (1.0 - speed) + .25 * (1.0 - maneuver) + .25 * narrow + .15 * heavy),
    }
    fleet = {
        "INDEPENDENT": _clamp(.55 * speed + .30 * maneuver + .15 * flux),
        "FORMATION_DEPENDENT": _clamp(.36 * (1.0 - speed) + .28 * defense + .20 * heavy + .16 * long_range),
        "CARRIER_DEPENDENT": round(bays, 6),
    }
    return CombatDoctrineProfile(
        hull.id,
        _axis(battlefield, min(structural_confidence, variant_confidence), facts + (f"existing_variants={f.existing_variant_count}",)),
        _axis(position, structural_confidence, facts),
        _axis(style, min(structural_confidence, variant_confidence), facts + (f"long_range_variant_fraction={f.variant_long_range_weapon_fraction!r}",)),
        _axis(tempo, _known_fraction(f.flux_capacity, f.flux_dissipation, f.mount_count), facts),
        _axis(commitment, _known_fraction(f.max_speed, f.acceleration, f.max_turn_rate, f.mount_count), facts),
        _axis(fleet, min(structural_confidence, variant_confidence), facts + (f"fighter_bays={f.fighter_bays!r}",)),
    )


def _axis(scores: dict[str, float], confidence: float, evidence: tuple[str, ...]) -> DoctrineAxisProfile:
    return DoctrineAxisProfile({key: round(_clamp(value), 6) for key, value in scores.items()}, round(confidence, 6), evidence)


def _facts(f: HullFeatureVector) -> tuple[str, ...]:
    return (f"mounts={f.mount_count}; heavy={f.medium_mounts + f.large_mounts}; missile={f.missile_mounts}", f"armor={f.armor_rating!r}; hull={f.hull_hitpoints!r}; flux=(capacity={f.flux_capacity!r}, dissipation={f.flux_dissipation!r})", f"mobility=(speed={f.max_speed!r}, acceleration={f.acceleration!r}, turn_rate={f.max_turn_rate!r})")


def _scale(value: float | int | None, reference: float) -> float:
    return _clamp(float(value) / reference) if value is not None else 0.0


def _mean(*values: float) -> float:
    return sum(values) / len(values) if values else 0.0


def _known_fraction(*values: object) -> float:
    return sum(value is not None for value in values) / len(values) if values else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
