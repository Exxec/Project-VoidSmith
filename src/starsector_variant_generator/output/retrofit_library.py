"""User-owned editable retrofit copies; scanned game/mod variants stay read-only."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from starsector_variant_generator.analysis.mechanical_archetypes import (
    infer_mechanical_archetypes,
)
from starsector_variant_generator.core.models import Variant
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.candidate import (
    generate_conservative_candidate,
)
from starsector_variant_generator.output.writer import _weapon_groups, write_variant
from starsector_variant_generator.parsers.entities import variant_from_file
from starsector_variant_generator.validation.legality import (
    LegalityResult,
    validate_variant,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class RetrofitAvailability:
    hull_id: str
    existing_variants: tuple[Variant, ...] = ()
    generated_paths: tuple[Path, ...] = ()
    attempted_profiles: tuple[str, ...] = ()
    generated_profiles: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class EditableRetrofitRecord:
    path: Path
    variant_id: str | None
    legality: str | None
    message: str | None = None


def variants_for_hull(registry: Registry, hull_id: str) -> tuple[Variant, ...]:
    """Read-only indexed variants for one hull, in stable order."""
    return tuple(sorted(registry.variants_for_hull(hull_id), key=lambda item: item.id))


def starter_profiles_for_hull(registry: Registry, hull_id: str) -> tuple[str, ...]:
    """Choose up to three existing profiles from static hull compatibility.

    This is a deterministic profile routing convenience, not a combat outcome
    prediction. It uses only the already explainable mechanical-archetype
    compatibility scores and falls back conservatively when source fields are
    insufficient to favor a profile.
    """
    hull = registry.hulls.by_id.get(hull_id)
    if hull is None:
        return ()
    scores = infer_mechanical_archetypes(hull, registry).compatibility_scores
    mapping = (
        ("CARRIER_SUPPORT", max(scores["LIGHT_CARRIER"], scores["HEAVY_CARRIER"], scores["BATTLECARRIER"])),
        ("MISSILE_SUPPORT", scores["MISSILE_SUPPORT"]),
        ("PD_ESCORT", scores["PD_ESCORT"]),
        ("LINE_ARTILLERY", scores["ARTILLERY"]),
        ("FAST_STRIKE", max(scores["SKIRMISHER"], scores["STRIKER"])),
        ("TANK", max(scores["ARMOR_BRAWLER"], scores["SHIELD_BRAWLER"])),
        ("LINE_BRAWLER", scores["LINE_SHIP"]),
    )
    chosen = [profile for profile, score in sorted(mapping, key=lambda item: (-item[1], item[0])) if score >= .2]
    return tuple(dict.fromkeys([*chosen, "LINE_BRAWLER", "LINE_ARTILLERY", "FAST_STRIKE"]))[:3]


def working_copy_path(output_root: Path, variant_id: str) -> Path:
    if not _SAFE_ID.fullmatch(variant_id):
        raise ValueError("Unsafe variant id for local retrofit library")
    return output_root / "editable_retrofits" / f"{variant_id}.variant"


def _backup_local_copy(target: Path) -> Path | None:
    """Keep a content-addressed local history copy before explicit replace."""
    if not target.exists():
        return None
    contents = target.read_bytes()
    digest = hashlib.sha256(contents).hexdigest()[:16]
    history = target.parent / ".history" / target.stem / f"{digest}.variant"
    if not history.exists():
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_bytes(contents)
    return history


def copy_existing_retrofit(variant: Variant, output_root: Path, *, replace: bool = False) -> Path:
    """Copy a parsed source variant verbatim into the user-owned library.

    This is deliberately a copy operation, never an in-place edit of the
    scanned source.  ``replace`` is only meaningful for the same local path
    selected by the user through the UI.
    """
    target = working_copy_path(output_root, variant.id)
    if target.exists() and not replace:
        return target
    if replace:
        _backup_local_copy(target)
    try:
        content = variant.source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read scanned source variant {variant.id}: {exc}") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def save_editable_variant(variant: Variant, registry: Registry, output_root: Path, *, replace: bool = False) -> Path:
    """Write one legal canvas/edit result to the local working library only."""
    target = working_copy_path(output_root, variant.id)
    if target.exists() and not replace:
        raise FileExistsError(f"Editable retrofit already exists: {target}")
    if replace:
        _backup_local_copy(target)
    # Reuse the normal export's legality boundary and serializable weapon
    # group construction, but intentionally keep this outside a source mod.
    from starsector_variant_generator.validation.legality import validate_variant
    assessment = validate_variant(variant, registry)
    if assessment.result is not LegalityResult.LEGAL:
        raise ValueError(f"Refusing to save editable retrofit: {assessment.result}")
    payload: dict[str, object] = {"variantId": variant.id, "displayName": variant.name, "hullId": variant.hull_id, "weaponGroups": _weapon_groups(variant, registry), "mods": list(variant.hullmods), "wings": list(variant.fighter_wings)}
    if variant.flux_vents is not None: payload["fluxVents"] = variant.flux_vents
    if variant.flux_capacitors is not None: payload["fluxCapacitors"] = variant.flux_capacitors
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def load_editable_retrofit(path: Path, output_root: Path) -> Variant:
    """Parse only a user-owned library file, never an arbitrary source path."""
    library = (output_root / "editable_retrofits").resolve()
    candidate = path.resolve()
    if not candidate.is_relative_to(library):
        raise ValueError("Editable retrofit must be loaded from the configured output library")
    if candidate.suffix.casefold() != ".variant" or not candidate.is_file():
        raise ValueError("Editable retrofit file is missing or is not a .variant file")
    return variant_from_file(candidate, "USER_EDITABLE")


def inspect_editable_retrofit(path: Path, output_root: Path, registry: Registry) -> EditableRetrofitRecord:
    """Parse and validate a local copy while retaining malformed-file evidence."""
    try:
        variant = load_editable_retrofit(path, output_root)
        assessment = validate_variant(variant, registry)
        messages = tuple(item.message for item in (*assessment.failures, *assessment.uncertainties))
        return EditableRetrofitRecord(path.resolve(), variant.id, assessment.result.value, "; ".join(messages) or None)
    except (ValueError, OSError) as exc:
        return EditableRetrofitRecord(path.resolve(), None, None, str(exc))


def restore_editable_retrofit_history(history_path: Path, output_root: Path) -> Path:
    """Restore one local history version after preserving the current copy."""
    library = (output_root / "editable_retrofits").resolve()
    candidate = history_path.resolve()
    history_root = library / ".history"
    if not candidate.is_relative_to(history_root) or candidate.suffix.casefold() != ".variant" or not candidate.is_file():
        raise ValueError("Restore source must be a local editable-retrofit history file")
    variant_id = candidate.parent.name
    target = working_copy_path(output_root, variant_id)
    _backup_local_copy(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(candidate.read_bytes())
    return target


def publish_editable_retrofit(path: Path, output_root: Path, *, replace: bool = False) -> Path:
    """Publish one local copy in a separate output-only compatibility mod."""
    variant = load_editable_retrofit(path, output_root)
    target_root = output_root / "VoidSmith Editable Retrofits"
    target = target_root / "data" / "variants" / f"{variant.id}.variant"
    contents = path.read_bytes()
    if target.exists():
        if target.read_bytes() == contents:
            return target
        if not replace:
            raise FileExistsError(f"Published retrofit differs: {target}")
        _backup_local_copy(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(contents)
    mod_info = target_root / "mod_info.json"
    mod_payload = '{\n  "id": "voidsmith_editable_retrofits",\n  "name": "VoidSmith Editable Retrofits",\n  "version": "0.1.0",\n  "author": "VoidSmith"\n}\n'
    if mod_info.exists() and mod_info.read_text(encoding="utf-8") != mod_payload:
        raise ValueError(f"Refusing to replace unrelated compatibility-mod manifest: {mod_info}")
    mod_info.write_text(mod_payload, encoding="utf-8")
    return target


def populate_variations_if_missing(registry: Registry, hull_id: str, output_root: Path, *, heuristic_set: str = "baseline_0.2") -> RetrofitAvailability:
    """Create deterministic local starter fits only when the hull has none.

    Generated fits are validated before writing.  Profiles are deliberately a
    small, ship-agnostic starter set; unavailable/illegal fits are omitted
    rather than fabricated.
    """
    existing = variants_for_hull(registry, hull_id)
    if existing:
        return RetrofitAvailability(hull_id, existing_variants=existing, note="Existing scanned retrofit(s) found; no generated variation was needed.")
    paths: list[Path] = []
    profiles = starter_profiles_for_hull(registry, hull_id)
    generated_profiles: list[str] = []
    for profile in profiles:
        result = generate_conservative_candidate(hull_id, profile, registry, heuristic_set=heuristic_set)
        if result.legality is LegalityResult.LEGAL:
            paths.append(write_variant(result.variant, registry, output_root / "editable_retrofits"))
            generated_profiles.append(profile)
    return RetrofitAvailability(hull_id, generated_paths=tuple(paths), attempted_profiles=profiles, generated_profiles=tuple(generated_profiles), note="Generated legal local starter variation(s)." if paths else "No legal starter variation could be generated from the available normalized data.")
