# VoidSmith Developer Guide

## Scope and authority

Read `AGENTS.md` first, then the formal/schema/engine documents named there.
The core is offline, deterministic, explainable, and source-read-only. Do not
commit Starsector/mod data, extracted reports, entity lists, or real benchmarks.

Implementation and tests are authoritative when older planning/status prose
disagrees. `ROADMAP.md` and older historical status entries contain planned or
superseded material and need periodic cleanup.

## Architecture and data flow

```text
installed core + mods (read-only)
  -> Scanner/parsers -> ScanResult + provenance/warnings
  -> Registry (duplicate/reference/dependency resolution)
  -> classifiers / analyzers / validation
  -> generation, refit, faction recommendations, reports, GUI/API
  -> configured output only (reports, cache, logs, exports)
```

Key boundaries:

- `parsers/`: untrusted CSV/JSON/HJSON/ship/skin/variant input normalization.
- `core/models.py`: normalized entities and scan results.
- `core/registry.py`: deterministic entity indexes, dependency checks, duplicate
  identity, and declared-reference trace resolution.
- `validation/`: only owner of `LEGAL`, `ILLEGAL`, and `NOT_DETERMINABLE`.
- `analysis/`: classifiers and evidence-bound derived analysis.
- `generation/`, `scoring/`, `profiles/`: candidate construction and quality.
- `output/`: reports, manifests, staleness, and compatibility-mod writer.
- `gui/`: PySide6 presentation calling API/backend services; never a rules
  engine.

## Normalization, evidence, and provenance

Parsers preserve raw evidence alongside typed fields. Use
`parsers.common.parse_int`/`parse_float` for parsed numeric data; malformed
values produce structured parse warnings instead of raising. Unknown data must
stay absent/unknown, never become a favorable zero.

Use `EvidenceClass`/`EvidenceRecord` where a producer makes a claim. The
important distinction is direct parsed data, local static source, adapter model,
curated guidance, reviewer evidence, inference, and unknown/conflict. Manual
overrides supplement non-legality metadata only and cannot bypass validation.

## Registry identity and references

`EntityIndex` retains duplicate IDs. Hullmod duplicate identity is separately
reported as `DUPLICATE_IDENTICAL` or `DUPLICATE_DIVERGENT` with semantic hashes.
Identical definitions are canonicalized (core preferred) while retaining
provenance. Divergent definitions remain global conflicts.

For a variant hullmod reference, `Registry.trace_reference()` applies declared
provenance scope: same mod, one declared dependency, then unique core fallback.
Unrelated definitions are recorded as shadowed `NOT_CONTEXT_RELEVANT` entries.
Multiple relevant divergent definitions are `AMBIGUOUS_CONFLICT`. This is
declared-reference resolution, not a model of Starsector's runtime-effective
load order.

## Heuristics, caches, and invalidation

All tunable shipped heuristics live in `core/heuristics.py` as named versioned
sets. Propagate `heuristic_set` through generation, scoring, recommendation,
cache fingerprints, reports, and output metadata. New released tuning requires
rationale, documentation, regression coverage, and a new set identifier.

The scanner stores per-source normalized snapshots only under the configured
output cache. Result caching uses exact context fingerprints: consumed entities,
heuristic set, constraints, packs, adapters, and overrides. Report fragments
fail closed on version/fingerprint mismatches. `analysis_reports.py` has its own
report schema version and local-Java source fingerprinting.

## Static mechanics and structural analysis

`analysis/hullmod_static_analysis.py` reads local Java source only. It records
recognized API effects, unsupported resolvable-accessor expressions, unknown
script portions, source association, and availability state. It never executes
scripts or decompiles JARs. A declared class with JARs but no readable matching
source is `COMPILED_ONLY_SCRIPT`.

Composite records in `analysis/composite_hulls.py` preserve parent/module
relationships as `STRUCTURAL_ONLY`. Never aggregate module weapons, shields,
systems, durability, or legality into a parent without a dedicated evidence
contract.

`analysis/combat_entity.py` separates structural entity kind from deployment;
`analysis/combat_doctrine.py` is an experimental, advisory six-axis profile:
battlefield function, engagement position, tactical style, tempo, commitment,
and fleet dependence. The axes are multi-valued and evidence-bound rather than
a replacement for one large role enum.

Neither classification system changes legality. Hull size describes geometry;
entity kind describes what an entity is; deployment records what is actually
known about how it enters combat; doctrine describes supported warfare posture.
Do not promote custom AI, fighter geometry, names, flavor text, or unsupported
script behavior into runtime behavior.

## Recommendations, confidence, and calibration

Gap recommendations have separate Native, Retrofit, and Acquisition legs.
Legality filters candidates before scoring. Recommendation score and confidence
are distinct. `RecommendationAudit` is shared by rank and Why-Not paths to
prevent drift. Structural eligibility is separate from legality.

Calibration modules consume local hash-bound fixtures/observations and compare
registered heuristics. They do not automatically modify heuristic values. Real
mod/local benchmark manifests remain ignored user data.

For unfamiliar mods, prefer a generic qualification pass before proposing an
adapter. Record what is understood, partial, compiled-only, structurally
unsupported, or runtime-dependent. Fix recurring generic weaknesses in the core
when evidence supports it; add a mod-specific adapter only for genuinely
mod-specific semantics. A lower interpretation percentage is acceptable when
unknown behavior is preserved honestly.

## API, CLI, GUI, and tests

`api.py` is the service boundary used by the CLI and GUI. Keep CLI orchestration
thin and serialize dataclasses through explicit API/result payload helpers where
caches need round trips. CLI commands are implemented in `cli/main.py`; run
`voidsmith --help` and per-command `--help` before documenting or changing
options.

The GUI entry point is `voidsmith-gui`. Keep scan/generation work off the UI
thread. `gui/resources.py` resolves art only beneath a scanned source root;
the canvas maps sprite texture dimensions into `.ship` geometry coordinates.

Run the portable suite:

```powershell
uv run --no-project --with-editable . python -m unittest discover -s tests -v
```

Use synthetic fixtures in `tests/fixtures/` for portable coverage. Local real
qualification/audit outputs belong below ignored `generated/`. Add focused
parser, registry, validator, adapter/analyzer, scoring, and GUI tests when a
change crosses those boundaries.

## Build and release

`dist/build_voidsmith.bat` invokes `tools/build_gui_exe.ps1` for a local
one-file GUI build. `tools/build_portable_release.ps1` produces the portable
PyInstaller onedir/zip release. Both use locked/offline dependencies by default
and package no game/mod data. The one-file script bumps the patch version and
matching local lock metadata by default (`-NoVersionBump` opts out); the
portable-release script uses an explicit `-Version` or the version already in
`pyproject.toml`.

Before release, run tests, build through the appropriate script, and inspect
the generated manifest/artifact. Do not add source data, logs, cache databases,
or generated reports to distribution.

## Documentation consistency audit (2026-08-26)

Verified from code/tests: CLI command names/options in `cli/main.py`, entry
points in `pyproject.toml`, GUI workspace/button labels in `gui/main_window.py`,
`AppConfig` TOML fields, output-root report/cache/log behavior, and build
scripts named above.

Items requiring follow-up rather than a claim of support:

- GUI availability depends on the optional PySide6 dependency and local display
  environment; this guide does not assert a packaged binary is present.
- Some historical `README.md`, `ROADMAP.md`, `WORK_LOG.md`, and
  `IMPLEMENTATION_STATUS.md` entries retain older test counts/planned language.
- Exact report filenames vary by command/entity and are intentionally not all
  enumerated here; CLI output reports the actual path.
- Runtime mod load-order override semantics, system-spawn deployment, and
  custom AI behavior cannot be verified statically and remain unsupported.
