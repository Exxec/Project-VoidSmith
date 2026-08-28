# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

VoidSmith (package `starsector_variant_generator`; CLI entry points `svg`/`voidsmith`; optional GUI entry points `svg-gui`/`voidsmith-gui`): an offline, deterministic Starsector data scanner, variant validator, conservative candidate generator, scorer, refit/repair assistant, faction capability-gap recommendation engine, and compatibility-mod exporter. It reads a Starsector installation and its mods without modifying them; generated files are written only beneath a selected `--output-dir` (CLI) or the configured cache/log directories (GUI).

Read `AGENTS.md` first — it is kept in sync with this file and states the required reading order: `AGENTS.md` → `FORMAL_SPECIFICATION.md` → `DATA_SCHEMA.md` → (as relevant) `GAP_RECOMMENDATION_ENGINE.md`, `FACTION_KNOWLEDGE_PACKS.md`, `EQUIPMENT_ACCESS_AND_AUTOFIT.md`, `HULLMODS_CIVILIAN_AND_REFIT.md` → `TEST_PLAN.md` → `HEURISTICS.md` → `GUI.md` (only when touching `gui/`) → `ROADMAP.md`. `docs/IMPLEMENTATION_STATUS.md` is the evidence-based status audit; `docs/BUGS.md` and `docs/WORK_LOG.md` are the bug tracker and audit trail — check them before assuming behavior is unimplemented or working.

## Commands

Run tests (full suite, mirrors CI):

```
uv run --no-project --with-editable . python -m unittest discover -s tests -v
```

Run a single test module/case:

```
uv run --no-project --with-editable . python -m unittest tests.test_generation -v
uv run --no-project --with-editable . python -m unittest tests.test_generation.TestGeneration.test_name -v
```

`tests/test_benchmark_portable.py` (synthetic archetype hulls, invented values) always runs as part of the suite above. `tests/test_canonical_local.py` (real named canonical hulls: Lasher/Hammerhead/Dominator/Heron/Onslaught) skips itself cleanly unless local data has been generated first — no real Starsector data is committed to this repo:

```
uv run --no-project --with-editable . python tools/build_local_benchmarks.py --starsector-path C:\path\to\Starsector
```

This writes structural-only fixtures and this project's own computed classifier/legality baselines under `tests/local_fixtures/` and `tests/local_results/` (both gitignored).

CLI usage (requires a real or fixture Starsector installation path):

```
svg scan --starsector-path C:\path\to\Starsector --output-dir generated\scan
svg validate <variant_id> --starsector-path C:\path\to\Starsector
svg analyze-variant <variant_id> --starsector-path C:\path\to\Starsector
svg list-profiles
svg query {weapons|hulls|fighters|hullmods|variants|faction-equipment} ... --starsector-path C:\path\to\Starsector
svg generate <hull_id> --mode {beginner|guided|advanced} --max-candidates 5 --starsector-path C:\path\to\Starsector
svg generate <hull_id> --mode advanced --advanced-config docs\advanced-request.example.json --starsector-path C:\path\to\Starsector
svg doctrine <faction_id> --starsector-path C:\path\to\Starsector
svg faction-capability <faction_id> --starsector-path C:\path\to\Starsector
svg recommend <faction_id> --starsector-path C:\path\to\Starsector
svg why-not <faction_id> <role> <hull_id> --starsector-path C:\path\to\Starsector
svg refit <variant_id> --mode {FIX_LEGALITY|REDUCE_FLUX|IMPROVE_ROLE_MATCH|IMPROVE_LOGISTICS|BALANCED_IMPROVEMENT} --starsector-path C:\path\to\Starsector
svg export <hull_id> --profile LINE_ARTILLERY --starsector-path C:\path\to\Starsector
svg check-export <generation_manifest.json> --starsector-path C:\path\to\Starsector
```

`scan` can instead take `--config path.toml` (see `config.example.toml` for the schema: `starsector_path`, `output_dir`, `log_dir`, `heuristic_set`).

GUI (optional install, `pip install -e .[gui]`): `svg-gui --starsector-path C:\path\to\Starsector`. Windows portable executable: run `dist\build_voidsmith.bat` from a checkout — it drives the reproducible PyInstaller pipeline and writes only local build artifacts (`dist\VoidSmith.exe`); it packages neither Starsector nor mod content.

There is no configured lint/format step beyond the `unittest` suite above; `pyproject.toml` carries a `[tool.mypy]` config, but it is not documented anywhere in this repo as a required check.

## Hard rules (from AGENTS.md)

- Source game and mod files are strictly read-only. Never write outside the configured output/log/cache directories; treat mod data as untrusted input and sanitize paths.
- No AI/LLM/API dependency. The core engine must stay offline, deterministic, explainable, and testable without AI.
- Do not infer undocumented Starsector behavior. Use only documented, parseable data and preserve raw evidence (`Entity.raw`). Unknown or scripted mechanics stay `UNKNOWN` / `UNKNOWN_SCRIPTED_EFFECT`; if legality can't be determined without guessing, the result is `NOT_DETERMINABLE`.
- **Legality vs. quality is a hard boundary, enforced throughout the pipeline:**
  - Only `validation/legality.py` produces `LEGAL` / `ILLEGAL` / `NOT_DETERMINABLE`. It must never use heuristics, doctrine inference, preferences, or scores.
  - `scoring/` and every `analysis/` module may only describe compatibility/quality for candidates already determined `LEGAL` — never a legality claim.
  - A quality score or warning must never conceal or reclassify an illegal/indeterminate candidate (ranking always sorts legal-before-illegal first, score second — see `api.py`'s `run_generate`).
- All tunable heuristics live in a named, versioned registry (`core/heuristics.py::REGISTRY`; current default `baseline_0.7`, every prior version kept for reproducibility). Report the exact `heuristic_set` and resolved values in reports/exports. New or changed heuristic values need a rationale, docs, regression coverage, and (if released) a new registry identifier.
- Custom/mod-specific mechanics belong in the adapter layer (`adapters/vanilla/` is the only populated adapter today — add `adapters/<mod>/` the same way for a mod-specific mechanic), never inferred generic rules.
- Distribution boundary: never commit or package Starsector/mod assets, extracted scan output, real entity identifiers/lists, mod-specific knowledge packs, or copied descriptions. Tests and fixtures use neutral synthetic data only. A benchmark selecting real, locally-installed entities belongs in an ignored local manifest, generated at run time from the user's own installation.
- Add tests alongside any parser/scanner/analysis change. Log unknown/skipped inputs without crashing rather than dropping them silently.

## Architecture

Everything flows through one pipeline, all under `src/starsector_variant_generator/`:

```
core/scanner.py (Scanner)         -- read-only walk of core + enabled mods -> ScanResult
        v
core/models.py                    -- frozen dataclasses: Entity subclasses (Hull, Weapon,
                                      FighterWing, Hullmod, Variant, Faction) + ScanResult
        v
core/registry.py (Registry)       -- Registry.from_scan(): builds EntityIndex per entity type
                                      (by_id + duplicates, never guesses at collisions),
                                      resolves variant->hull/weapon/hullmod references and
                                      mod dependency presence into UnresolvedReference /
                                      MissingDependency lists
        v
   +----+-------------+-------------------+------------------+
   v                   v                   v                  v
validation/         analysis/           generation/         scoring/
legality.py         (many independent,  (candidate.py,      (candidate_score.py:
(validate_variant)  evidence-based      refit.py, hullmods.py, score_candidate --
LEGAL/ILLEGAL/       analyzers -- see    fighters.py,        LEGAL candidates only)
NOT_DETERMINABLE     below; no legality  vent_cap.py)
only)                claims)
   v
output/writer.py (write_compatibility_mod) -- exports LEGAL-only .variant + compatibility
output/staleness.py (check_generation_manifest) -- mod, with a per-variant generation
                                                     manifest (source hashes, heuristic_set,
                                                     profile, faction mode, timestamp) used
                                                     to detect stale exports on rescan
```

`api.py` is an importable service layer, one function per command (`run_scan`, `run_query_*`, `run_validate`, `run_generate`, `run_export`, `run_doctrine`, `run_faction_capability`, `run_gap_recommendations`, `run_why_not`, `run_fix_legality`, `run_improve_quality`, `run_analyze_variant`, `run_check_export`, ...), each wiring the pipeline above together and raising `ValueError` on user-facing error conditions instead of exiting. Both front ends bind to it directly rather than re-implementing orchestration: `cli/main.py` is a single `argparse` dispatcher (`svg <command>`) with no business logic beyond argument validation and report serialization; `gui/` (PySide6, optional install) calls the same `api.py` functions from `main_window.py` and background `QThread` workers in `gui/workers/` so long scans don't block the UI — read `GUI.md` before changing anything under `gui/`.

Key architectural points:

- **Everything is read fresh per command.** There is no persistent database; each invocation re-scans (`Scanner(...).scan()`) and rebuilds a `Registry` in memory. `core/cache.py`/`core/result_cache.py` only track staleness (source hashes), not a queryable cache.
- **Entities are immutable and carry provenance.** Every `Entity` (`core/models.py`) keeps `source_mod`, `source_path`, `source_hash`, and a `raw` dict of unrecognized fields — parsers never discard unknown data.
- **Duplicate/ambiguous IDs are never silently resolved.** `EntityIndex.build` (`core/registry.py`) pops an ID out of `by_id` into `duplicates` the moment a second entity claims it; callers (CLI, GUI, faction lookup, etc.) must handle ambiguity explicitly (e.g. `--source-mod` overrides for factions).
- **`analysis/` is a family of independent, single-purpose evidence analyzers, not one monolith.** Examples: `classification.py` (hull/weapon/fighter/hullmod tags), `doctrine.py` (faction weapon/hullmod usage patterns), `civilian.py`/`combat_stats.py`/`mobility_stats.py` (derived per-ship stats from verified adapter-layer hullmod effects, aggregated in `derived_ship_state.py`), `mechanical_archetypes.py`/`build_archetypes.py`/`capability_vector.py` (non-exclusive, evidence-only hull/build compatibility scoring — deliberately never a canonical "this hull is an X" claim), `equipment_affinity.py` (NATIVE/COMMON/FOREIGN/UNALIGNED from real faction `known_*` lists, never `source_mod_id`), `faction_capability.py`/`gap_recommendation.py` (per-faction capability gaps and native/retrofit/acquisition recommendations — `GAP_RECOMMENDATION_ENGINE.md`), and `calibration.py`/`calibration_runner.py` (compares generated output against locally reviewer-labeled fixtures; never adjusts heuristics itself). Every one follows the same rule as validation: describe compatibility/evidence, never legality, never a number without a citable source.
- **`core/overrides.py` (Manual Override Layer) and `core/knowledge_packs.py` (Faction Knowledge Packs, `FACTION_KNOWLEDGE_PACKS.md`)** are both additive-only, structurally excluded from legality: overrides supplement missing classifier evidence for one weapon/hull id; knowledge packs are curated per-faction guidance loaded from `knowledge_packs/`, degrading gracefully (never rejecting the whole pack) on a stale or unresolved reference.
- **Generation is a capped, deterministic search**, not an optimizer: a conservative baseline candidate plus a bounded number of next-ranked documented weapon alternatives per mount (`generation/candidate.py`, `--search-depth`). Every alternative is independently re-validated for legality before being ranked or scored — quality can never promote a non-legal candidate. `generation/refit.py` is a separate, narrower "change as little as possible" pass over an *existing* variant (`FIX_LEGALITY` plus quality-improvement modes) — not the same search as full generation.
- **Profiles** (`profiles/catalog.py`, `profiles/modes.py`, `profiles/advanced.py`) are deterministic *quality* intents only and are never consulted by validation. Advanced-mode requests accept only implemented, auditable restrictions and reject anything unsupported rather than ignoring it.
- **Parsers** (`parsers/common.py`, `parsers/entities.py`) handle vanilla `.ship`/`.wpn`/`.variant`/`.faction`/JSON/CSV plus a relaxed-JSON (HJSON-like) mode for common modded syntax deviations (comments, trailing commas, bare keys, single-quoted strings, etc.) — see `docs/BUGS.md` for the specific tolerated forms and why.
