"""Offline static recognition of a bounded subset of HullMod Java effects.

Evidence-tier note (see AGENTS.md's "Scripted-mechanic analyzer hierarchy"
and ROADMAP.md Phase 28): this module is tier 2 (local source static
analysis) combined with tier 3 (a versioned known-API-call registry --
`API_EFFECT_REGISTRY_VERSION`/`_CALLS` below). Recognized effects are
resolved from two sub-tiers, both still local-source-only and never a
guess:

  1. A bare numeric literal or a single already-declared `static final`
     constant used directly as the modifier's value argument (e.g.
     `modifyFlat(id, 20f)` or `modifyPercent(id, SPEED_BONUS)`).
  2. A bounded arithmetic expression built only from numeric literals and
     locally-declared constants -- `+`, `-`, `*`, `/`, and unary +/- only
     (e.g. `modifyPercent(id, -HULL_PENALTY)` or
     `modifyMult(id, 1f - (0.01f * RECOIL_BONUS))`). See
     `_fold_constant_expression`. Measured against this project's own real
     149-mod local install (2026-08-25), counting only calls to the
     registered `_CALLS` stat accessors above (the same scope this
     analyzer already recognized, not every `stats.getX()` call in the
     install): of 2,776 real `stats.get<RegisteredAccessor>().
     modifyFlat/Percent/Mult(...)` calls found across all installed mods'
     Java source, the prior single-token-only logic (sub-tier 1) recognized
     1,144 (41%); this expression-folding extension (sub-tier 2) recognizes
     491 more (18%, ~43% relative increase) across 247 distinct files,
     while the remaining 1,141 correctly stay unresolved because they
     reference a genuine runtime value (a method parameter, an instance
     field, a loop variable) that cannot be a compile-time constant --
     never guessed at, exactly like sub-tier 1 already refused to guess at
     a bare unresolvable identifier. One concrete real example: the
     "1130的蔚蓝联邦 translated" mod's real `AF_OpenAmmoDepot` hullmod
     (`data.hullmods.AF_OpenAmmoDepot`) declares
     `public static final float HULL_PENALTY = 25f;` and applies
     `stats.getHullBonus().modifyPercent(id, -HULL_PENALTY);` -- entirely
     unrecognized before this change (a unary-minus expression, not a bare
     literal or identifier), now recognized as `hull_hp PERCENT_ADD -25.0`
     at confidence 0.85.

Any name the expression folder cannot resolve to a local constant --
including a constant declared in a *different* file (tier 4, "referenced
local config/constants", genuinely still unimplemented) or any method
call/attribute access/comparison -- makes the whole expression unresolved
rather than partially guessed, so `UNKNOWN_SCRIPTED_EFFECT` remains the
honest fallback exactly as before.

Known simplification: `_CONSTANT` (and this expression folder) treats
every locally declared `int`/`float`/`double` constant as a Python float,
so a real Java *integer* division between two `int` constants (which
truncates in Java) would be folded here using true division instead. No
real occurrence of that specific shape was found in the measurement above
(every real division case in the local install already carries an
explicit `f`/`F`/`d`/`D` float suffix on at least one literal operand,
matching Java's own promotion-to-float rule), but this remains a
documented, not fully eliminated, edge case rather than a fixed one.

ROADMAP Phase 38 (round 2) extends this same module along three axes,
each measured against this project's own real 149-mod local install
(2026-08-25), never against every `stats.getX()` call in the install --
the same "only the scope this analyzer already recognizes" measurement
discipline `-0.3`'s own docstring above already established:

  1. Registry coverage (`API_EFFECT_REGISTRY_VERSION` bumped to
     `starsector-api-effects-0.4`): 15 further real, documented
     `MutableShipStatsAPI` stat-modifier accessors added to `_CALLS`,
     chosen from real, non-trivial call-site frequency in the local
     install (`getBallisticRoFMult` 212 real calls down to
     `getRecoilPerShotMult` 36) and independently verified real,
     documented semantics for each -- weapon-type rate-of-fire
     (`getBallisticRoFMult`/`getEnergyRoFMult`/`getMissileRoFMult`),
     weapon-type range bonus (`getBallisticWeaponRangeBonus`/
     `getEnergyWeaponRangeBonus`), damage-type-taken multipliers
     (`getShieldDamageTakenMult`/`getArmorDamageTakenMult`/
     `getHullDamageTakenMult`/`getEmpDamageTakenMult`), combat-readiness
     (`getMaxCombatReadiness`, directly confirmed against real vanilla
     `Automated.java` source; `getPeakCRDuration`), and three further
     single-stat accessors (`getZeroFluxSpeedBoost`, `getRecoilPerShotMult`,
     `getSensorProfile`, `getVentRateMult`). Every one's real,
     documented one-line meaning was independently confirmed (never
     guessed) via the official Starfarer API method-name/return-type
     surface plus a maintained third-party Starsector hullmod-modding
     guide's explicit per-method descriptions, matching the same
     evidentiary bar Phase 4's `adapters/vanilla` tables were held to.
  2. Cross-class constant resolution (`_cross_file_constants`): a
     same-source-root (never cross-mod), per-file-stem-as-class-name
     lookup table built once per scan from the same `_java_sources`
     listing this module already indexes, resolving a
     `ClassName.CONSTANT_NAME`-qualified `static final` reference (e.g.
     `Constants.HULL_PENALTY`) declared in a *different* local `.java`
     file within the same mod/core source root -- the tier 4 gap `-0.3`
     explicitly left open. Deliberately stays qualified-reference-only;
     a bare identifier resolved only via a Java `import static` (no
     class qualifier at the use site) is a distinct, still-unimplemented
     pattern, named as a remaining gap below rather than silently
     guessed at. A resolution that touches this table is recorded at a
     new, lower confidence tier (0.75) than either sub-tier already
     documented above, reflecting the added uncertainty of the
     file-stem-as-class-name assumption (Java's own one-public-class-
     per-file convention, which this module also already relies on for
     `DECLARED_SCRIPT_CLASS` association -- not a new assumption, reused
     consistently).
  3. Explicit `UNSUPPORTED_SCRIPTED_EFFECT` vs `UNKNOWN_SCRIPTED_EFFECT`:
     a new `unsupported_scripted_portions` field, populated only when a
     call site already matched a real, registered `_CALLS` accessor but
     its value argument could not be resolved to a concrete number (a
     runtime variable, a cross-mod reference, an unfoldable expression,
     or a call whose argument list this module's single-line parser
     could not extract at all) -- distinct from `unknown_scripted_portions`,
     now reserved for a call/reference this module has no registry entry
     for whatsoever (or a structural no-source/no-class state). This is
     purely a re-classification of which branch an already-computed
     unresolved case fell into, never new inference -- see
     `analyze_hullmod_sources`'s branch comments.

Documented, not-eliminated remaining gaps after this round: bare
`import static`-qualified cross-file constant references (see item 2
above); a `.java` file declaring more than one top-level/nested class
under one file stem (the same simplification `DECLARED_SCRIPT_CLASS`
association already carries, now also inherited by cross-file constant
lookup); and every gap `-0.3`'s own docstring already named that this
round did not target (local mod-specific config/CSV reference
resolution, ship-system-effect interpretation, and partial per-method
extraction from a mixed known/unknown script body).
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from starsector_variant_generator.core.evidence import EvidenceClass, EvidenceRecord
from starsector_variant_generator.core.models import Hullmod

API_EFFECT_REGISTRY_VERSION = "starsector-api-effects-0.4"
_CALLS = {
    "getMaxSpeed": ("max_speed", "SELF"), "getAcceleration": ("acceleration", "SELF"),
    "getDeceleration": ("deceleration", "SELF"), "getTurnAcceleration": ("turn_acceleration", "SELF"),
    "getMaxTurnRate": ("max_turn_rate", "SELF"), "getFluxDissipation": ("flux_dissipation", "SELF"),
    "getFluxCapacity": ("flux_capacity", "SELF"), "getArmorBonus": ("armor_rating", "SELF"),
    "getHullBonus": ("hull_hp", "SELF"), "getSuppliesPerMonth": ("supplies_per_month", "SELF"),
    "getBallisticWeaponFluxCostMod": ("ballistic_weapon_flux_cost", "SELF"),
    "getEnergyWeaponFluxCostMod": ("energy_weapon_flux_cost", "SELF"),
    "getMissileWeaponFluxCostMod": ("missile_weapon_flux_cost", "SELF"),
    "getWeaponTurnRateBonus": ("weapon_turn_rate", "SELF"), "getSightRadiusMod": ("sight_radius", "SELF"),
    # Added in `-0.4` (ROADMAP Phase 38 round 2), all real, documented
    # `MutableShipStatsAPI` accessors verified against real, non-trivial
    # call-site frequency in this project's own local 149-mod install and
    # independently confirmed real semantics (official Starfarer API
    # method surface plus a maintained third-party Starsector hullmod-
    # modding guide's explicit per-method descriptions; `getMaxCombatReadiness`
    # additionally confirmed directly against real vanilla `Automated.java`
    # source, `stats.getMaxCombatReadiness().modifyFlat(id, -MAX_CR_PENALTY, ...)`).
    # See the module docstring's Phase 38 section for the full citation summary.
    "getBallisticRoFMult": ("ballistic_weapon_rate_of_fire", "SELF"),
    "getEnergyRoFMult": ("energy_weapon_rate_of_fire", "SELF"),
    "getMissileRoFMult": ("missile_weapon_rate_of_fire", "SELF"),
    "getBallisticWeaponRangeBonus": ("ballistic_weapon_range", "SELF"),
    "getEnergyWeaponRangeBonus": ("energy_weapon_range", "SELF"),
    "getShieldDamageTakenMult": ("shield_damage_taken", "SELF"),
    "getArmorDamageTakenMult": ("armor_damage_taken", "SELF"),
    "getHullDamageTakenMult": ("hull_damage_taken", "SELF"),
    "getEmpDamageTakenMult": ("emp_damage_taken", "SELF"),
    "getMaxCombatReadiness": ("max_combat_readiness", "SELF"),
    "getPeakCRDuration": ("peak_combat_readiness_duration", "SELF"),
    "getZeroFluxSpeedBoost": ("zero_flux_speed_boost", "SELF"),
    "getRecoilPerShotMult": ("recoil_per_shot", "SELF"),
    "getSensorProfile": ("sensor_profile", "SELF"),
    "getVentRateMult": ("vent_rate", "SELF"),
}
_CALL_START = re.compile(r"stats\.(get\w+)\(\)\.(modifyFlat|modifyPercent|modifyMult)\(")
_CONSTANT = re.compile(r"(?:static\s+final\s+)?(?:float|double|int)\s+(\w+)\s*=\s*([-+]?\d+(?:\.\d+)?)")
_HULL_SIZE = re.compile(r"ShipAPI\.HullSize\.([A-Z_]+)")
_JAVA_NUMERIC_SUFFIX = re.compile(r"(\d)[fFdD](?!\w)")
_BARE_NUMERIC_LITERAL = re.compile(r"[-+]?\d+(?:\.\d+)?$")
_BARE_IDENTIFIER = re.compile(r"[A-Za-z_]\w*$")


class _UnresolvedExpression(Exception):
    """Raised internally when an expression node is not a compile-time constant."""


_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)

# Confidence tiers, from most to least directly evidenced. "BARE" (a bare
# numeric literal or a single already-declared same-file constant) and
# "EXPRESSION" (same-file-only constant-expression folding) are the two
# sub-tiers `-0.3` already established; "CROSS_FILE" is new in `-0.4` --
# see `_cross_file_constants` and the module docstring's Phase 38 section.
_CONFIDENCE_BY_TIER = {"BARE": 0.9, "EXPRESSION": 0.85, "CROSS_FILE": 0.75}


def _eval_constant_node(node: ast.AST, constants: Mapping[str, float], cross_file_constants: Mapping[str, Mapping[str, float]], used_cross_file: list[bool]) -> float:
    """Evaluate a restricted arithmetic AST node against known local constants.

    Only numeric literals, resolved names, a same-source-root qualified
    `ClassName.CONSTANT` attribute reference, unary +/-, and +/-/*// between
    two already-resolved operands are supported -- no calls, subscripts,
    comparisons, or any other node type. Anything else (including a name
    this file never declared as a constant, or a qualifier this source
    root's own `.java` files never declare) raises `_UnresolvedExpression`
    rather than being approximated. `used_cross_file` is a single-element
    mutable out-parameter (`[bool]`) set True the moment any qualified
    cross-file reference is actually resolved, so the caller can apply the
    lower `CROSS_FILE` confidence tier to the whole expression even when a
    same-file constant or literal also participates in it.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in constants:
            return constants[node.id]
        raise _UnresolvedExpression(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        # A qualified reference, e.g. `Constants.HULL_PENALTY` -- resolved
        # only against this same source root's own per-file-stem constant
        # table (never a different mod's files; see `_cross_file_constants`).
        class_table = cross_file_constants.get(node.value.id)
        if class_table is not None and node.attr in class_table:
            used_cross_file[0] = True
            return class_table[node.attr]
        raise _UnresolvedExpression(f"{node.value.id}.{node.attr}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_constant_node(node.operand, constants, cross_file_constants, used_cross_file)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _eval_constant_node(node.left, constants, cross_file_constants, used_cross_file)
        right = _eval_constant_node(node.right, constants, cross_file_constants, used_cross_file)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise _UnresolvedExpression("division by zero")
        return left / right
    raise _UnresolvedExpression(type(node).__name__)


def _fold_constant_expression(expr: str, constants: Mapping[str, float], cross_file_constants: Mapping[str, Mapping[str, float]]) -> tuple[float | None, bool]:
    """Constant-fold a bounded arithmetic expression, or return `(None, False)`.

    `None` covers both a genuinely unresolvable name/qualifier and a Python
    syntax error (e.g. a Java-only construct this restricted grammar
    doesn't parse at all) -- both are treated identically as "not
    statically resolvable", never a guess. The second element is True iff
    resolution actually used `cross_file_constants` for some part of the
    expression, letting the caller pick the correct confidence tier.
    """
    normalized = _JAVA_NUMERIC_SUFFIX.sub(r"\1", expr)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        return None, False
    used_cross_file = [False]
    try:
        return _eval_constant_node(tree.body, constants, cross_file_constants, used_cross_file), used_cross_file[0]
    except _UnresolvedExpression:
        return None, False


def _resolve_modifier_value(raw_expr: str, constants: Mapping[str, float], cross_file_constants: Mapping[str, Mapping[str, float]]) -> tuple[float | None, str]:
    """Resolve a modifier call's value argument to a float, if possible.

    Returns `(value, tier)`, `tier` one of `_CONFIDENCE_BY_TIER`'s keys:
    `"BARE"` for a bare numeric literal or a single already-declared
    same-file constant (the original, narrowest recognition this analyzer
    always supported), `"EXPRESSION"` for a multi-term arithmetic
    expression resolved only from same-file constants/literals, and
    `"CROSS_FILE"` for any expression whose resolution touched
    `cross_file_constants` for at least one name. A `None` value paired
    with `"BARE"` means a single unqualified identifier that isn't a
    known same-file constant (never attempted as a class-qualified
    reference, since it has no `.`); a `None` value paired with anything
    else means expression folding itself failed.
    """
    token = raw_expr.strip()
    bare_numeric = _JAVA_NUMERIC_SUFFIX.sub(r"\1", token)
    if _BARE_NUMERIC_LITERAL.fullmatch(bare_numeric):
        return float(bare_numeric), "BARE"
    if _BARE_IDENTIFIER.fullmatch(token):
        value = constants.get(token)
        return value, "BARE"
    value, used_cross_file = _fold_constant_expression(token, constants, cross_file_constants)
    return value, ("CROSS_FILE" if used_cross_file else "EXPRESSION")


def _extract_call_arguments(line: str, args_start: int) -> list[str] | None:
    """Split a call's argument list on top-level commas, honoring nested parens.

    `args_start` is the index of the character immediately after the
    call's opening `(`. Returns `None` if the matching closing paren is
    not found on this same line -- this analyzer is deliberately
    single-line/bounded (matching its prior line-by-line design), so a
    genuinely multi-line call falls through to the existing "unrecognized
    API modifier expression" evidence rather than being guessed at.
    """
    depth = 1
    args: list[str] = []
    current = ""
    for ch in line[args_start:]:
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            if depth == 0:
                if current.strip():
                    args.append(current.strip())
                return args
            current += ch
        elif ch == "," and depth == 1:
            args.append(current.strip())
            current = ""
        else:
            current += ch
    return None


@lru_cache(maxsize=256)
def _java_sources(source_root: str) -> tuple[tuple[Path, str], ...]:
    """Read each local Java source once per scan process/source root.

    This is deliberately an in-memory scan-local cache, not a persistent cache:
    source files remain the source of truth for each independent scan.
    """
    root = Path(source_root)
    sources: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*.java")):
        try:
            sources.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError):
            continue
    return tuple(sources)


@lru_cache(maxsize=256)
def _cross_file_constants(source_root: str) -> Mapping[str, Mapping[str, float]]:
    """Build a same-source-root `{class_name: {constant_name: value}}` table.

    "Class name" here is a file's own stem, matching Java's standard
    one-public-class-per-file convention -- the same simplification
    `analyze_hullmod_sources`'s own `DECLARED_SCRIPT_CLASS` association
    already relies on (`path.stem == script_class`), reused consistently
    rather than invented fresh for this table. A file declaring more than
    one top-level/nested class, or a class whose name genuinely differs
    from its file's stem, is a known, documented edge case this table can
    misattribute -- not silently assumed correct.

    Built once per source root per scan process (cached like
    `_java_sources`, which this reuses directly rather than re-reading
    every `.java` file a second time), never across scans and never across
    source roots -- a qualified reference can only ever resolve against
    constants declared somewhere in this exact mod's (or the core game's)
    own `.java` tree, never a different mod's, by construction.
    """
    table: dict[str, dict[str, float]] = {}
    for path, text in _java_sources(source_root):
        constants = {name: float(value) for name, value in _CONSTANT.findall(text)}
        if constants:
            table.setdefault(path.stem, {}).update(constants)
    return table

@dataclass(frozen=True)
class HullmodEffectRecord:
    target_stat: str
    operation: str
    numeric_value: float
    applicability: str
    condition: str | None
    source_location: str
    confidence: float
    api_registry_version: str
    hull_size: str | None = None

@dataclass(frozen=True)
class HullmodStaticAnalysis:
    hullmod_id: str
    source_files: tuple[str, ...]
    source_association: str
    recognized_effects: tuple[HullmodEffectRecord, ...]
    unknown_scripted_portions: tuple[str, ...]
    confidence: float
    evidence: tuple[EvidenceRecord, ...] = ()
    # Added in `-0.4` (ROADMAP Phase 38 round 2): a call site the registry
    # DID recognize (`call_match.group(1) in _CALLS`) but whose value
    # argument could not be resolved to a concrete number -- a real
    # runtime variable, a cross-mod reference, an unfoldable expression,
    # or an argument list this module's single-line parser couldn't even
    # extract. Distinct from `unknown_scripted_portions`, now reserved for
    # a call/reference this module has no registry entry for at all (or a
    # structural no-source/no-class state). Defaulted to `()` so every
    # existing positional-argument construction above in this module, and
    # any external caller already matching the prior 7-field signature,
    # keeps working unchanged.
    unsupported_scripted_portions: tuple[str, ...] = ()
    # Distinguishes unavailable readable source from source that was read but
    # could not be normalized. Neither state implies a mechanic.
    analysis_state: str = "SOURCE_ANALYZED"  # SOURCE_ANALYZED | COMPILED_ONLY_SCRIPT | NO_READABLE_SOURCE | NO_ASSOCIATED_CLASS
    static_effect_coverage: str = "AVAILABLE"  # AVAILABLE | UNAVAILABLE

def analyze_hullmod_sources(hullmod: Hullmod, source_root: Path | None) -> HullmodStaticAnalysis:
    if source_root is None or not source_root.is_dir():
        return HullmodStaticAnalysis(hullmod.id, (), "NO_LOCAL_SOURCE", (), ("UNKNOWN_SCRIPTED_EFFECT: no readable local Java source root.",), 0.0, (), (), "NO_READABLE_SOURCE", "UNAVAILABLE")
    script = str(hullmod.raw.get("script", hullmod.raw.get("scriptClass", "")))
    script_class = script.rsplit(".", 1)[-1] if script else ""
    resolved_root = str(source_root.resolve())
    declared_candidates: list[tuple[Path, str]] = []
    reference_candidates: list[tuple[Path, str]] = []
    for path, text in _java_sources(resolved_root):
        # The CSV script class is the authoritative local association.  Do not
        # merge classes that merely mention a hullmod ID when that class exists:
        # doing so makes unrelated API calls look like hullmod effects.
        if script_class and path.stem == script_class:
            declared_candidates.append((path, text))
        elif hullmod.id in text:
            reference_candidates.append((path, text))
    candidates = declared_candidates or reference_candidates
    association = "DECLARED_SCRIPT_CLASS" if declared_candidates else "ID_REFERENCE_FALLBACK"
    if not candidates:
        compiled_only = bool(script_class and any(source_root.rglob("*.jar")))
        reason = "UNKNOWN_SCRIPTED_EFFECT: declared script has no readable local source; compiled JAR artifacts are present." if compiled_only else "UNKNOWN_SCRIPTED_EFFECT: no local Java class could be associated with this hullmod."
        return HullmodStaticAnalysis(
            hullmod.id, (), "COMPILED_ONLY_SCRIPT" if compiled_only else "NO_ASSOCIATED_CLASS", (), (reason,), 0.0, (), (),
            "COMPILED_ONLY_SCRIPT" if compiled_only else "NO_ASSOCIATED_CLASS", "UNAVAILABLE",
        )
    effects, unknown, unsupported, evidence = [], [], [], []
    if association == "ID_REFERENCE_FALLBACK":
        unknown.append("UNKNOWN_SCRIPTED_EFFECT: source association is an ID-reference fallback, not a declared script class.")
    cross_file_constants = _cross_file_constants(resolved_root)
    for path, text in candidates:
        constants = {name: float(value) for name, value in _CONSTANT.findall(text)}
        lines = text.splitlines()
        for line_no, line in enumerate(lines, 1):
            call_match = _CALL_START.search(line)
            if call_match and call_match.group(1) in _CALLS:
                call_args = _extract_call_arguments(line, call_match.end())
                if call_args is not None and len(call_args) >= 2:
                    raw_value_expr = call_args[1]
                    value, tier = _resolve_modifier_value(raw_value_expr, constants, cross_file_constants)
                    if value is None:
                        # This call site matched a real, registered `_CALLS`
                        # accessor -- the registry recognizes it -- but its
                        # argument could not be resolved to a concrete
                        # value, so this is UNSUPPORTED, not UNKNOWN.
                        kind = "non-literal modifier value" if tier == "BARE" else "modifier value expression"
                        unsupported.append(f"UNSUPPORTED_SCRIPTED_EFFECT: {path}:{line_no}: {kind} {raw_value_expr!r} is not statically resolvable.")
                        continue
                    operation = {"modifyFlat": "FLAT_ADD", "modifyPercent": "PERCENT_ADD", "modifyMult": "MULTIPLY"}[call_match.group(2)]
                    stat, applicability = _CALLS[call_match.group(1)]
                    location = f"{path}:{line_no}"
                    hull_size = _enclosing_hull_size(lines, line_no - 1)
                    condition = f"ShipAPI.HullSize.{hull_size}" if hull_size else ("conditional context not statically interpreted" if "if (" in line else None)
                    confidence = _CONFIDENCE_BY_TIER[tier]
                    effect = HullmodEffectRecord(stat, operation, value, applicability, condition, location, confidence, API_EFFECT_REGISTRY_VERSION, hull_size)
                    effects.append(effect)
                    evidence.append(EvidenceRecord(
                        evidence_id=f"hullmod:{hullmod.id}:java:{path.stem}:{line_no}:{stat}", entity_id=hullmod.id,
                        source_file=str(path), source_class=path.stem, source_line_or_symbol=str(line_no),
                        evidence_type="HULLMOD_EFFECT", extracted_value=asdict(effect), confidence=confidence,
                        parser_or_adapter=f"api-effect-registry:{API_EFFECT_REGISTRY_VERSION}",
                        evidence_class=EvidenceClass.LOCAL_SOURCE_CODE,
                    ))
                else:
                    # A recognized accessor, but this module's deliberately
                    # single-line argument parser couldn't extract usable
                    # arguments (e.g. a genuinely multi-line call) --
                    # UNSUPPORTED, not UNKNOWN, per the same "registry
                    # recognized it" rule above.
                    unsupported.append(f"UNSUPPORTED_SCRIPTED_EFFECT: {path}:{line_no}: unrecognized API modifier expression.")
            elif ".modify" in line or "stats." in line and "get" in line:
                # Either no `_CALL_START` match at all, or a `stats.getX()`
                # accessor the registry has no `_CALLS` entry for -- the
                # registry never recognized this call, so it stays UNKNOWN.
                unknown.append(f"UNKNOWN_SCRIPTED_EFFECT: {path}:{line_no}: unrecognized API modifier expression.")
    if not effects and not unknown and not unsupported:
        unknown.append("UNKNOWN_SCRIPTED_EFFECT: associated local Java class contains no recognized normalized stat modifier.")
    confidence = .9 if effects and not unknown and not unsupported else (.6 if effects else .2)
    return HullmodStaticAnalysis(hullmod.id, tuple(str(path) for path, _ in candidates), association, tuple(effects), tuple(unknown), confidence, tuple(evidence), tuple(unsupported), "SOURCE_ANALYZED", "AVAILABLE")

def static_analysis_record(analysis: HullmodStaticAnalysis) -> dict:
    return asdict(analysis)


def _enclosing_hull_size(lines: list[str], line_index: int) -> str | None:
    """Find the nearest simple local hull-size branch without interpreting code flow.

    This is deliberately bounded to the current lexical block. Nested control
    flow, variables, and method calls remain represented by the separate
    condition/unknown evidence rather than being guessed.
    """
    depth = 0
    for source in reversed(lines[:line_index]):
        depth += source.count("}") - source.count("{")
        match = _HULL_SIZE.search(source)
        if match and "if" in source and depth <= 1:
            return match.group(1)
        if depth > 1:
            break
    return None
