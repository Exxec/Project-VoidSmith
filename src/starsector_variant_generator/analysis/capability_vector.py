"""Normalized, evidence-preserving capability vectors for hulls.

Scores describe compatibility, never legality or a claim that an unfitted hull
already carries a particular weapon package. Variant-mounted weapons are
descriptive statistical evidence; structural mechanics remain independent.
"""

from __future__ import annotations

from dataclasses import dataclass

from starsector_variant_generator.analysis.classification import classify_civilian_role, classify_weapon
from starsector_variant_generator.analysis.mechanical_archetypes import infer_mechanical_archetypes
from starsector_variant_generator.analysis.mobility_stats import compute_derived_mobility_stats
from starsector_variant_generator.core.models import Hull, Variant
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.registry import Registry


CAPABILITY_DIMENSIONS = (
    "LONG_RANGE_PRESSURE", "KINETIC_PRESSURE", "ARMOR_BREAKING", "FINISHING_POWER",
    "SUSTAINED_PRESSURE", "BURST_STRIKE", "PD_SCREENING", "FIGHTER_INTERCEPTION",
    "MISSILE_PROJECTION", "ARMOR_TANKING", "SHIELD_TANKING", "MOBILITY", "PURSUIT",
    "CARRIER_PROJECTION", "FREIGHTER", "TANKER", "SALVAGE_SUPPORT", "SURVEY_SUPPORT",
)


@dataclass(frozen=True)
class CapabilityEvidence:
    score: float | None
    confidence: float
    availability: str  # AVAILABLE | UNKNOWN
    supporting_evidence: tuple[str, ...]
    evidence_class: EvidenceClass = EvidenceClass.INFERRED_MECHANICS


@dataclass(frozen=True)
class CapabilityVector:
    subject_id: str
    dimensions: dict[str, CapabilityEvidence]


def infer_hull_capability_vector(
    hull: Hull, registry: Registry, variants: tuple[Variant, ...] | None = None,
) -> CapabilityVector:
    profile = infer_mechanical_archetypes(hull, registry, variants)
    f = profile.feature_vector
    variants = variants if variants is not None else registry.variants_for_hull(hull.id)
    weapon_ids = [weapon_id for variant in variants for weapon_id in variant.weapons_by_mount.values() if weapon_id in registry.weapons.by_id]
    weapons = [registry.weapons.by_id[weapon_id] for weapon_id in weapon_ids]
    weapon_confidence = 1.0 if weapons else 0.35
    total = len(weapons)
    weapon_fraction = lambda predicate: sum(predicate(weapon) for weapon in weapons) / total if total else None
    armor_breaking = weapon_fraction(lambda weapon: (weapon.damage_type or "").upper() in {"HE", "HIGH_EXPLOSIVE"})
    kinetic = weapon_fraction(lambda weapon: (weapon.damage_type or "").upper() == "KINETIC")
    pd = weapon_fraction(lambda weapon: "PD" in classify_weapon(weapon).role_tags)
    long_range = weapon_fraction(lambda weapon: classify_weapon(weapon).range_band == "LONG")
    missile = weapon_fraction(lambda weapon: (weapon.mount_type or "").upper() == "MISSILE")
    civilian = classify_civilian_role(hull)
    verified_variant_speeds = [
        derived.effective_values["max_speed"]
        for variant in variants
        if (derived := compute_derived_mobility_stats(hull, variant.hullmods, registry)).applied_effects
        and any(effect.stat == "max_speed" for effect in derived.applied_effects)
        and derived.effective_values["max_speed"] is not None
    ]
    mobility_score = max(_scale(f.max_speed, 120.0), _scale(max(verified_variant_speeds), 120.0) if verified_variant_speeds else 0.0)
    mobility_evidence = (f"max_speed={f.max_speed!r}",)
    if verified_variant_speeds:
        mobility_evidence += (f"Verified existing-variant effective max_speed={max(verified_variant_speeds):.6f} from adapter-backed hullmod effects.",)

    def structural(score: float, *evidence: str) -> CapabilityEvidence:
        return CapabilityEvidence(round(score, 6), _structural_confidence(f), "AVAILABLE", tuple(evidence))

    def mounted(score: float | None, label: str) -> CapabilityEvidence:
        if score is None:
            return CapabilityEvidence(None, 0.0, "UNKNOWN", (f"No resolved existing-variant weapons for {label}; no weapon behavior inferred.",))
        return CapabilityEvidence(round(score, 6), weapon_confidence, "AVAILABLE", (f"Existing variants: {total} resolved mounted weapon(s); {label} fraction={score:.6f}.",))

    dimensions = {
        "LONG_RANGE_PRESSURE": structural(max(profile.compatibility_scores["ARTILLERY"], long_range or 0.0), *profile.evidence_by_archetype["ARTILLERY"]),
        "KINETIC_PRESSURE": mounted(kinetic, "kinetic-pressure"),
        "ARMOR_BREAKING": mounted(armor_breaking, "armor-breaking"),
        "FINISHING_POWER": structural(profile.compatibility_scores["STRIKER"], *profile.evidence_by_archetype["STRIKER"]),
        "SUSTAINED_PRESSURE": structural(min(1.0, (profile.compatibility_scores["LINE_SHIP"] + _scale(f.flux_dissipation, 1500.0)) / 2), "Line-ship mechanics plus documented flux dissipation."),
        "BURST_STRIKE": structural(profile.compatibility_scores["STRIKER"], *profile.evidence_by_archetype["STRIKER"]),
        "PD_SCREENING": structural(max(profile.compatibility_scores["PD_ESCORT"], pd or 0.0), *profile.evidence_by_archetype["PD_ESCORT"]),
        "FIGHTER_INTERCEPTION": structural(min(1.0, (f.fighter_bays or 0) / 2.0), f"fighter_bays={f.fighter_bays!r}"),
        "MISSILE_PROJECTION": structural(max(profile.compatibility_scores["MISSILE_SUPPORT"], missile or 0.0), *profile.evidence_by_archetype["MISSILE_SUPPORT"]),
        "ARMOR_TANKING": structural(profile.compatibility_scores["ARMOR_BRAWLER"], *profile.evidence_by_archetype["ARMOR_BRAWLER"]),
        "SHIELD_TANKING": structural(profile.compatibility_scores["SHIELD_BRAWLER"], *profile.evidence_by_archetype["SHIELD_BRAWLER"]),
        "MOBILITY": structural(max(profile.compatibility_scores["SKIRMISHER"], mobility_score), *mobility_evidence),
        "PURSUIT": structural(max(profile.compatibility_scores["SKIRMISHER"], profile.compatibility_scores["STRIKER"]), "Skirmisher/striker structural compatibility."),
        "CARRIER_PROJECTION": structural(max(profile.compatibility_scores["LIGHT_CARRIER"], profile.compatibility_scores["HEAVY_CARRIER"], profile.compatibility_scores["BATTLECARRIER"]), f"fighter_bays={f.fighter_bays!r}"),
        "FREIGHTER": structural(profile.compatibility_scores["FREIGHTER"], f"civilian_hints={civilian.role_tags!r}"),
        "TANKER": structural(profile.compatibility_scores["TANKER"], f"civilian_hints={civilian.role_tags!r}"),
        "SALVAGE_SUPPORT": structural(profile.compatibility_scores["SALVAGE_SUPPORT"], f"civilian_hints={civilian.role_tags!r}"),
        "SURVEY_SUPPORT": structural(profile.compatibility_scores["SURVEY_SUPPORT"], f"civilian_hints={civilian.role_tags!r}"),
    }
    return CapabilityVector(hull.id, dimensions)


def _scale(value: float | int | None, reference: float) -> float:
    return min(1.0, max(0.0, float(value) / reference)) if value is not None else 0.0


def _structural_confidence(vector: object) -> float:
    # Availability-aware confidence: absent raw fields reduce confidence but
    # never turn an unavailable property into a favorable score.
    missing = sum(getattr(vector, name) is None for name in ("armor_rating", "hull_hitpoints", "has_shield", "max_speed", "flux_dissipation"))
    return round(max(0.5, 1.0 - missing * 0.05), 3)
