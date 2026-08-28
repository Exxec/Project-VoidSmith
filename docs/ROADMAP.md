# Roadmap: status, decisions, and what's next

> Current status and future plan are maintained in the root
> [`ROADMAP.md`](../ROADMAP.md). This document is retained as a historical
> implementation record; its older “open” items do not override the root
> roadmap's Phase 82 completion state or current bounded plan.

This is the authoritative, in-repo record of the five-tier gap-closing plan
first drafted 2026-08-22 and partially implemented the same day. It exists so
that a future contributor -- human or AI -- can pick up this work without
re-deriving the reasoning behind it. If you are an AI picking this up: read
this whole file before touching `validation/`, `scoring/`, or `analysis/
doctrine.py`; several design decisions here are load-bearing and not obvious
from the code alone.

Each tier below states: what gap it closes, whether it's **Done**,
**Deferred**, or **Blocked**, the exact files touched, and -- for anything
not done -- exactly what would unblock it. Do not re-attempt a Blocked item
without first satisfying its stated blocker; the blocker exists to prevent
fabricating game data this project's own rules (`Agent.md`) forbid.

## Doc set integration (2026-08-22, later same day)

A second planning pass produced a fuller doc set at repo root: `AGENTS.md`,
`FORMAL_SPECIFICATION.md`, `GUI.md`, `DATA_SCHEMA.md`, `HEURISTICS.md`,
`TEST_PLAN.md`, `ROADMAP.md`, `README.md`, plus `config/heuristics.default.json`
and `config/overrides/`. The project's eventual name is **VoidSmith** (per
`Forge formal spec.txt`'s title and confirmed directly).

These files initially arrived at repo root with **scrambled filenames**
(`FORMAL_SPECIFICATION.md` contained `AGENTS.md`'s text, `GUI.md` contained
`DATA_SCHEMA.md`'s text, etc.) -- a bug in whatever produced them, not a
deliberate rename. The correct, verified source is
`Starsector-Variant-Generator-Planning-Pack/` (still present in the repo
root as the reference copy). The root files have since been corrected to
match it; if any root `.md` file's content doesn't match its own top
heading again, re-copy from that pack rather than guessing.

Reconciliation findings, so this doesn't need re-deriving:

- **No new roadmap phases.** The pack's `ROADMAP.md` has the same 13 phases
  (0-12) as what's now in root `ROADMAP.md`, just with placeholder
  `NOT_STARTED` statuses everywhere; root `ROADMAP.md` has since been
  updated with real per-phase status and is strictly more current. Nothing
  to merge.
- **`FORMAL_SPECIFICATION.md` is a v0.2 revision of `Forge formal spec.txt`
  (v0.1).** It trims some v0.1 elaboration (the detailed legality/quality
  separation subsections 2.3.1/2.3.2, the versioned-heuristic-registry
  rules in old section 37.1, explicit NOT_DETERMINABLE handling detail).
  This is **not a reversal** of those rules: `AGENTS.md` is declared the
  highest-precedence document when files conflict (its own Section 50 /
  "DOCUMENT SET AND OWNERSHIP"), and `AGENTS.md` still states the same
  core rules ("Hard legality is separate from quality/scoring," "Do not
  invent undocumented Starsector behavior," "Keep tunable heuristics in a
  versioned registry"). Everything already implemented this session
  (three-state legality, the `baseline_0.1`/`baseline_0.2` immutability
  split, fail-closed uncertainty handling) remains fully compliant. Treat
  `Forge formal spec.txt`'s more detailed wording as still-valid elaboration
  of the same rules, not a competing spec.
- **New, genuinely additive content in `FORMAL_SPECIFICATION.md` v0.2**
  (sections 45-50, not present in v0.1):
  - Section 45 (Adapter/Plugin Layer) matches the `adapters/` package
    already built here, down to the `if mod_id == ...` anti-pattern it
    warns against. Suggests `adapters/base/` and `adapters/modded/`
    alongside the existing `adapters/vanilla/` -- not created yet, add
    when a second adapter consumer actually needs the shared shape.
  - Section 46 (**Manual Override Layer**) -- weapons scope now **done**;
    hulls/fighters/hullmods/factions still open. See the dedicated section
    below.
  - Section 48 (Continuous Implementation With Checkpoints) matches
    `AGENTS.md`'s Continuous Work Policy already being followed.
  - Section 49 (Build Inspector) describes `svg analyze-variant`'s intended
    role almost exactly; `--faction-id`/`--source-mod` were added later
    the same day (see below), so `faction_doctrine_match` now surfaces
    there too, not just in `svg generate`.
- **`GUI.md` is fully specified now** (PySide6/Qt, a "Ship Fitting Canvas"
  with callout/list views, `CurrentFitState` as the one authoritative
  fitting state, a 22-item Definition of Done). This **supersedes** the
  ad hoc web/local-HTTP-service GUI blueprint from the earlier planning
  Artifact in this session -- PySide6 desktop, not a browser client, is
  the decided direction. GUI.md's own Section 50 ("GUI Readiness Gate")
  independently states not to build production GUI features against
  unstable backend contracts, consistent with the gate already being
  honored here.

## Manual Override Layer (FORMAL_SPECIFICATION.md section 46)

**Weapons: Done.** `core/overrides.py` (`load_overrides`,
`apply_role_tag_override`) plus wiring in `cli/main.py`'s `query weapons`
handler.

The spec section names the files (`config/overrides/{hulls,weapons,
fighters,hullmods,factions}.json`) but doesn't pin an exact per-file JSON
schema -- only a single-entity example
(`config/overrides/weapons.example.json`) showing one entry's shape. This
implementation picks a concrete, defensible shape (a design decision, not
inferred from the spec): a JSON object keyed by entity id, `{"<id>":
{"role_tags": [...], "notes": "..."}, ...}` -- a lookup table, so a
duplicate id can't silently shadow an earlier entry. Also note: the
existing `.example.json` file is deliberately in the *single-entity*
shape (matching its role as documentation of one entry, not a literal
whole-file example) and is never picked up at runtime (`load_overrides`
looks for exactly `weapons.json`, not `weapons.example.json`).

Scope, and why it's this narrow:

- **Only affects classification tags, never legality.** `apply_role_tag_override`
  unions an override's `role_tags` into `classify_weapon`'s own tags --
  additive only, never a removal or replacement, so an override can't hide
  real parsed evidence. `validation/legality.py` never imports
  `core/overrides.py` at all -- the module has no path into a legality
  result, structurally, not by convention.
- **Wired into `svg query weapons` only, not yet into generation/export.**
  Before this, `classify_weapon`/`classify_hull`/etc. had *zero* CLI
  surface at all (only consumed internally by `generation/candidate.py`'s
  PD-priority sort and `output/writer.py`'s PD-vs-linked weapon-group
  split) -- there was nothing for a user-facing override to visibly affect
  yet. Query is now that surface: `role_tags`, `range_band`, and
  `role_tags_overridden` appear in every `svg query weapons` record.
  Live-verified: overriding a weapon added `TEST_MARKER` to its tags
  (unioned with the classifier's own `KINETIC_PRESSURE`/`PD`), and the
  `role_tags_overridden` flag correctly distinguished it from every other
  weapon in the same query.
- **Not yet wired into `generation/candidate.py` or `output/writer.py`'s
  own `classify_weapon` calls.** Doing so would let a user's override
  correct, say, a mod weapon missing a real "pd" tag and have that
  actually change `PD_ESCORT` generation or weapon-group export -- real
  additional value, but it means threading an `overrides` parameter
  through several already-large function signatures
  (`generate_conservative_candidate`, `generate_candidate_alternatives`,
  `_build_candidate`, `write_variant`, `write_compatibility_mod`). Left
  for a follow-up pass rather than done under time pressure in this one.
- **`hulls.json`/`fighters.json`/`hullmods.json`/`factions.json` are not
  implemented.** `load_overrides` is generic over `entity_kind`
  (`load_overrides(dir, "hulls")` already works mechanically), but no
  caller loads or applies them yet -- `classify_hull`/`classify_fighter`/
  `classify_hullmod` don't have an override-application call site the way
  `classify_weapon` now does in the query handler.
- **`ai_friendliness_score` (present in the example file) is not
  consumed anywhere.** No AI-friendliness scoring exists in this codebase
  (deliberately -- see docs/ROADMAP.md's future-roadmap notes on why an
  *automatic* AI-friendliness heuristic risks fabricating undocumented AI
  behavior). A user-*supplied* value carries no such risk since the tool
  never asserts it, only passes it through, but no report surfaces it yet.

## How field names and game facts in this document were verified

Two evidence sources were used, in order of preference -- never memory or
inference alone, per Agent.md:

1. **A real Starsector installation.** As of 2026-08-22 this project has
   read access to `C:\Program Files (x86)\Fractal Softworks\Starsector`
   (game) and `...\Starsector\mods` (installed mods), with permission to
   traverse both and to search the web. Anything claimed as a parsed field
   name or a config value in this document was checked directly against
   files under that path unless stated otherwise. A prior scan of the same
   (or a similar) installation is also preserved at
   `generated/starsector_scan_current/reports/scan_summary.json` -- a
   ~65MB JSON report whose `entities.hulls[*].raw` / `entities.weapons[*].raw`
   objects preserve every field the CSV/`.ship` parsers saw, including ones
   the typed dataclasses didn't capture at the time. That file is evidence,
   not a fixture -- do not delete it. Either source can go stale (a game
   update, a mod update); re-verify with a fresh `svg scan` or a fresh
   directory read before trusting a specific field name against a different
   installed version.
2. **Web search, for facts no local file documents.** Vent/capacitor OP cost
   and hull-size maximums (Tier 1.1) are engine-hardcoded, not present in
   any parseable file -- that fact was confirmed via
   https://starsector.wiki.gg/wiki/Flux, cross-checked against the
   installed `settings.json`'s related-but-different values
   (`fluxPerCapacitor`/`dissipationPerVent`) to gain confidence the wiki
   entry describes this exact game version before encoding it as a
   citation in `adapters/vanilla/`. Use this same cross-check pattern for
   Tier 1.2's still-empty hullmod-incompatibility table: a wiki or
   patch-note claim is more trustworthy once corroborated against
   something independently observable in the installed files.

## Tier 1 -- Legality completeness

### 1.1 Vent & capacitor OP validation -- **Done**

Files: `adapters/vanilla/__init__.py` (`FLUX_UNIT_COST`), `adapters/
__init__.py` (`flux_unit_cost`), `validation/legality.py`
(`FLUX_VENTS_EXCEED_HULL_MAXIMUM` / `FLUX_CAPACITORS_EXCEED_HULL_MAXIMUM`).

Unblocked 2026-08-22 once given access to a real installation
(`C:\Program Files (x86)\Fractal Softworks\Starsector`) and permission to
search the web. The cost turned out not to be a per-hull-size curve at all:
it's a flat **1 OP per vent, 1 OP per capacitor**, engine-hardcoded (not a
`settings.json` key -- that file only declares each unit's *effect*,
`fluxPerCapacitor`/`dissipationPerVent`), separately capped by a documented
per-hull-size maximum count (Frigate 10 / Destroyer 20 / Cruiser 30 /
Capital 50). Verified via https://starsector.wiki.gg/wiki/Flux and
cross-checked against the installed `settings.json`'s per-unit effect
values, which match the wiki exactly -- strong confirmation the citation
describes this exact game version. Lives in the adapter layer (like 1.2)
because it's documented, verified behavior rather than something parsed
from per-mod data.

`VENT_CAP_OP_UNKNOWN` still fires exactly as before for any hull whose
`source_mod` has no adapter entry (i.e. every installed mod, unless/until
one is separately confirmed to override vanilla's values) -- fail-closed
behavior for modded hulls was preserved, not weakened.

### 1.2 Hullmod incompatibility -- **Done** (mechanism), table intentionally empty

Files: `src/starsector_variant_generator/adapters/__init__.py`,
`adapters/vanilla/__init__.py`, `validation/legality.py`
(`HULLMOD_INCOMPATIBLE` check).

The adapter layer Agent.md requires now exists and is wired into legality.
`adapters/vanilla/INCOMPATIBLE_HULLMOD_PAIRS` is a tuple of `(a, b,
citation)` entries; legality fails a variant carrying both members of any
listed pair. The table ships **empty** -- no incompatibility pair was
verified against a citable source (a patch note, official changelog, or
verified tooltip text) during this work, and inventing one would be exactly
the kind of fabrication Agent.md forbids. An empty table asserts nothing; it
never confirms compatibility, it just has no rule to fail on yet.

**Unblock by:** adding entries to `INCOMPATIBLE_HULLMOD_PAIRS` (or a new
per-mod adapter module) once a real, citable source names a specific
mutually-exclusive pair. Test pattern for a new entry is in
`tests/test_legality.py::test_hullmod_incompatibility_pairs_are_illegal_when_documented`.

### 1.3 Fighter bay legality -- **Done**

Files: `validation/legality.py` (`FIGHTER_BAY_CAPACITY_EXCEEDED` /
`FIGHTER_BAY_CAPACITY_UNKNOWN`).

A variant assigning more fighter wings than `hull.launch_bay_slots` is
`ILLEGAL`. Capacity is only asserted when the hull actually has parsed
`.ship` data (`"ship_data" in hull.raw`); a hull with no parsed ship data is
`NOT_DETERMINABLE` for this check, not assumed to have zero bays -- "no
evidence of bays" and "evidence of zero bays" are different facts and the
check does not conflate them.

### 1.4 Built-in weapon preservation -- **Done**

Files: `core/models.py` (`Hull.built_in_weapons`), `parsers/entities.py`
(`hull_from_row`), `validation/legality.py`
(`BUILT_IN_WEAPON_OVERRIDDEN`).

Verified against the real scan: `.ship` files carry a `builtInWeapons`
object (`{mount_id: weapon_id}`) alongside `builtInMods`/`builtInWings`, for
mounts whose `weaponSlots` entry has `"type": "BUILT_IN"`. A variant that
assigns a *different* weapon to one of those mounts is `ILLEGAL`; omitting
the mount (letting the game auto-fill it) or assigning the exact declared
weapon is fine.

### 1.5 Mount-type compatibility matrix (not in the original 5 items) -- **Done**

Files: `core/mount_compatibility.py` (new), `validation/legality.py`,
`generation/candidate.py`.

Not one of the original Tier 1 items, but the single largest source of
false-positive `ILLEGAL` results this project ever produced: both legality
and generation only ever did an exact string match between a mount's `type`
and a weapon's `mount_type`. That's correct for `BALLISTIC`/`ENERGY`/
`MISSILE` mounts, but wrong for `HYBRID`/`COMPOSITE`/`SYNERGY`/`UNIVERSAL`
mounts, which accept documented *combinations* (e.g. a `HYBRID` mount takes
`BALLISTIC` or `ENERGY` weapons, not just weapons whose own `mount_type` is
literally `"HYBRID"`).

Verified via three independent, mutually corroborating sources: two
starsector.wiki.gg pages, and -- the strongest evidence -- an empirical
scan of every weapon-to-mount assignment across all 431 real,
developer-authored core variants in a live installation. All three agree
exactly. See SVG-013 in `docs/BUGS.md` for the full citation and numbers.

Re-verified against all 441 real core variants: `MOUNT_TYPE_MISMATCH`
dropped from 299 to 4 (98.7% reduction); `LEGAL` count rose from 162 to 293
(+81%). The 4 remaining are all `hull_size: FIGHTER` wings -- a genuinely
separate, still-undocumented fighter-internal mount-semantics question, not
folded into this matrix on weak evidence.

Fixing this also surfaced a related pre-existing bug: a hull-fixed
`BUILT_IN` mount's own `type` field (literally `"BUILT_IN"` in real data)
was being checked as if it were a weapon-compatibility category, which
would have made even the hull's own correct built-in weapon (whose real
`mount_type` is never `"BUILT_IN"`) fail the old exact-match check.
`validate_variant` now skips the generic size/mount-type checks entirely
for mounts present in `hull.built_in_weapons` -- legality for those is
governed solely by `BUILT_IN_WEAPON_OVERRIDDEN`.

## Tier 2 -- Flux scoring -- **Done**

Files: `core/models.py` (`Hull.flux_capacity`/`flux_dissipation`/
`shield_upkeep`, `Weapon.flux_per_shot`/`flux_per_second`),
`parsers/entities.py`, `core/heuristics.py` (`BASELINE_0_2`),
`scoring/candidate_score.py` (`_flux_component`).

Field names were verified, not guessed: the real scan's hull CSV rows carry
`max flux`, `flux dissipation`, `shield upkeep` columns; weapon CSV rows
carry `energy/shot` and `energy/second` -- Starsector labels flux generation
"energy" in this column regardless of the weapon's actual mount type
(a `BALLISTIC` weapon still has an `energy/shot` value; it is flux cost, not
a literal energy-type weapon marker).

Formula implemented exactly as specified in `Forge formal spec.txt`
(`sustained_flux_load`, `dissipation_ratio`, per-mode targets). When hull
dissipation or any mounted weapon's flux-per-second is unparsed, the
`flux_sustainability` component is **omitted from the score**, not
defaulted to zero -- missing data must not read as a bad candidate. See
`tests/test_scoring.py::test_missing_flux_data_is_excluded_from_the_score_not_penalized`.

**Explicitly not implemented:** the hullmod-dissipation-bonus term
(`effective_dissipation = hull.flux_dissipation + hullmod bonuses`) named in
the roadmap draft. It would need the same citable-adapter treatment as
1.2's incompatibility table (no hullmod's numeric dissipation bonus is in
parseable data either), and doing it well is more naturally a follow-on to
1.2 once that table has real entries. `_flux_component` currently uses
`hull.flux_dissipation` alone.

## Tier 3 -- Doctrine & role classification

### 3.1 `doctrine_match` -- **Done**

Files: `analysis/doctrine.py` (`doctrine_match`), `scoring/
candidate_score.py` (`faction_doctrine_match` component).

Compares a candidate's mounted-weapon average range and hullmod set against
one faction's `DoctrineEvidence` (already-existing evidence-only analysis).
Returns `None` -- not a low score -- when there's no usable evidence, so "no
signal" and "poor match" stay distinguishable in the score explanation.
Only applied when a resolved `Faction` is passed to `score_candidate`
(wired through `svg generate`'s existing `--faction-id` resolution; not
wired into `svg analyze-variant`, which has no faction concept in its CLI
surface today).

The internal weighting (50% range alignment, 50% hullmod overlap) is a
first-pass heuristic, versioned as `doctrine_range_weight` /
`doctrine_hullmod_overlap_weight` in `baseline_0.2`. It is intentionally not
tuned against real data -- that's Tier 5's benchmark/calibration suite, not
this pass.

### 3.2 Hull role classification -- **Already done before this roadmap**

`analysis/classification.py::classify_hull` already existed and does
exactly this (mount/OP/bay-derived, non-exclusive role-compatibility
scores). The original gap-audit that produced the five-tier plan
mis-flagged this as missing; it was verified present and left untouched.

## Tier 4 -- Generation breadth

| Item | Status | Note |
|---|---|---|
| Guided mode's "meaningful choice" | **Done** | `--flux-mode` (`SAFE`/`BALANCED`/`AGGRESSIVE`) on `svg generate` and `svg analyze-variant`, defaulted per `UserMode` in `profiles/modes.py::resolve_mode` (`ModeDefaults.flux_mode`). This reuses the exact `generate_candidate_alternatives` engine every mode already calls -- no duplicated logic. |
| Hullmod selector | **Done** | `generation/hullmods.py::select_hullmods`. Rather than fabricate "hullmod X suits profile Y" (a game-balance opinion with no documented basis), it mirrors the weapon selector's already-legitimate pattern: `preferred_hullmod_ids` in practice comes from a faction's real parsed `known_hullmods` (wired into `svg generate` exactly like the existing weapon preference), then cheapest-OP-first. Hidden and built-in-only hullmods are never selected; the logistics-tagged count respects `MAX_LOGISTICS_HULLMODS`. **`max_hullmods` defaults to 2, not "everything OP allows"**: a first pass with no cap produced a 20-hullmod frigate on live data. Checked against evidence instead of guessing -- all 324 real core variants with any hullmods have a median/mean of ~2 (88% have 1-3) -- and capped there. Stress-tested across all 158 real core combat hulls x 3 profiles: 471/474 (99.4%) LEGAL, remaining 3 trace to the pre-existing Universal-mount gap, not this feature. |
| Vent/cap allocator | **Done** | `generation/vent_cap.py::allocate_vents_and_capacitors`. Spends remaining OP on vents toward the profile's flux target (Tier 2), then capacitors with what's left, bounded by the same documented per-hull-size maximum the legality check enforces -- so a generated candidate cannot fail its own legality check for vent/cap reasons. Declines entirely (returns zeros) when flux data is incomplete or the source mod has no documented flux-unit cost. |
| Weapon groups | **Done** | `output/writer.py::_weapon_groups`, applied at export time (no new `Variant` field needed). Splits PD-tagged weapons (via the already-tested `classify_weapon` "PD" role tag) into an AUTOFIRE group, everything else into LINKED -- PD is conventionally autofire in Starsector; a single LINKED group would leave the player to fire it manually. Grounded in existing, tested evidence rather than a new fabricated rule. |
| Built-in-mount generation bug | **Found and fixed** | Not in the original Tier 4 scope, but surfaced by stress-testing the above: some real vanilla weapons declare `mountType` `"BUILT_IN"` themselves, making them spuriously "eligible" for any hull's `BUILT_IN`-type mount regardless of which specific weapon that hull actually hardwires there -- the generator had never explicitly excluded `BUILT_IN` mounts (only `UNIVERSAL`), so it would occasionally assign a wrong weapon there and get correctly caught by Tier 1.4's `BUILT_IN_WEAPON_OVERRIDDEN` legality check (53 occurrences across the same 474-candidate stress run). Fixed in `generation/candidate.py::_build_candidate`: a hull-fixed mount is now always left for the game to auto-fill, never guessed at. |
| Fighter-wing selector | **Done** | `generation/fighters.py::select_fighter_wings`, unblocked by Tier 1.3's `Hull.fighter_bays` fix. Unlike hullmods, fighter wings have a real physical capacity (`hull.fighter_bays`), so filling every available bay (subject to OP) is the natural conservative behavior -- no invented cap needed, unlike `select_hullmods`'s `max_hullmods`. `preferred_wing_ids` follows the same faction-evidence pattern (`known_fighters`), wired into `svg generate`. `CARRIER_SUPPORT` is no longer a weapon-only fallback. Stress-tested against all 19 real carrier-capable core hulls: 18/19 LEGAL (the 1 exception is the pre-existing Universal-mount gap), 0 exceptions; also verified `STRICT_FACTION`-style filtering restricts wings to a faction's real `known_fighters`. |
| Profile catalog expansion | **Done, beyond original scope** | Added `TANK` (hullmod selection prefers the hull's own real `uiTags` "Defenses" category first) and `PD_ESCORT` (weapon selection prefers weapons `classify_weapon`'s already-tested "PD" tag identifies first). Both reuse existing, tested evidence signals rather than a new fabricated per-item judgment -- `RoleProfile.hullmod_priority_tag`/`weapon_priority="PD_FIRST"` are documented-category preferences, not claims that a specific hullmod or weapon is "good." All 7 profiles (up from 5) stress-tested together across all 158 real core combat hulls (1,106 candidates): 157/158 (99.4%) LEGAL for every single profile, 0 exceptions. `docs/profiles.md` updated. |
| Richer bounded search | **Done** | `generate_candidate_alternatives` gained `search_depth` (default 1, exactly the original "one alternate rank per mount" bound -- byte-identical output verified for every existing caller, including the golden regression test). Higher values explore rank 2, 3, ... for every mount, breadth-first across ranks (every mount's rank-1 before any mount's rank-2), so the closest-to-baseline alternatives always sort first. Still strictly one mount changed at a time -- never a per-mount-*combination* search, so candidate count stays linear in mount count x depth, not combinatorial (Agent.md rule 11). Wired into `svg generate` as `--search-depth` (1-10) and recorded in the report's `bounded_search` block. Stress-tested at depth 3 on `lasher` (15/15 LEGAL, all distinct) and at depth 4 across 60 real hulls (788/788 LEGAL, 0 exceptions). |

## Tier 5 -- Infrastructure

| Item | Status | Note |
|---|---|---|
| CI | **Done** | `.github/workflows/tests.yml`: runs the unittest suite on Python 3.11 and 3.12 on push/PR, then `python -m build`. |
| SQLite cache | **Deliberately deferred** | The formal spec itself defers this until "the data model stabilizes." This pass changed the data model twice (Tier 1.4, Tier 2) -- exactly the condition the spec says to wait out. Revisit once Tier 1.1/1.2/4 stop changing `core/models.py`. |

## Heuristic registry: `baseline_0.2`

`baseline_0.1` was **not edited** -- it's immutable per Agent.md, and a
golden regression test (`tests/test_regression.py`) pins its exact output.
`baseline_0.2` is a new, additive registry entry:

- The three flux-target values (`beginner_flux_target` / `balanced_flux_target`
  / `aggressive_flux_target`) are **numerically unchanged** from `baseline_0.1`
  -- only their role changes, from documented-but-inert to actively consumed.
- Five new `weight_*` keys replace what were hardcoded `0.45/0.20/0.35`
  literals in `scoring/candidate_score.py`, plus two new weighted terms
  (`weight_flux_sustainability=0.20`, `weight_faction_doctrine=0.10`).
- Three new `doctrine_*` keys parameterize `doctrine_match`.

`scoring/candidate_score.py::score_candidate` branches on whether the
supplied `heuristic_set` has a `weight_range_coherence` key. If not (i.e.
`baseline_0.1`, or any future set that omits it), it reproduces the
original three-component formula **exactly** -- same weights, same two-line
explanation, same rounding. This is what makes the golden regression test
pass unchanged. Do not remove this branch to "simplify" the function; it is
the mechanism that keeps `baseline_0.1`-tagged historical reports
reproducible.

`core/config.py`'s `AppConfig` default and `profiles/modes.py::resolve_mode`
now both default to `"baseline_0.2"` (previously `"baseline_0.1"`) --
`tests/test_config_and_heuristics.py` was updated to expect this
deliberately, not as a side effect.

## GUI -- explicitly not built

Per `Agent.md` ("Do not add an AI/API dependency or a GUI before the core
engine is ready") and `docs/IMPLEMENTATION_STATUS.md` (v0.1 Definition of
Done still unmet), no GUI code was written in this pass. The blueprint
(architecture, API surface, screens, a player-facing user guide, and a
build spec for whichever agent eventually implements it) is preserved as a
published Artifact from the planning conversation that produced this
roadmap; ask the project owner for that link if you need it, or re-derive
it from this document's Tier list plus `Forge formal spec.txt` section 3
("A graphical UI is not required for the first usable milestone").

**Before starting GUI work:** confirm explicit sign-off from the project
owner. This is a deliberate gate, not an oversight.

**Update (2026-08-22, later):** the project owner explicitly asked to work
toward "a state where we could begin prototyping GUI" without asking for
GUI code itself. Per `GUI.md` section 50 (Readiness Gate), "a GUI prototype
may be built earlier using fixture data, but it must not become an
alternate rules engine" once backend contracts are stable enough. Still no
GUI code has been written. What was done instead, once toward that specific
readiness bar: `src/starsector_variant_generator/api.py`, an importable
service layer -- see the new section below.

## Future roadmap (beyond this pass)

**Corrected 2026-08-22 (later):** this list predates several later passes
in the same session and had gone stale -- 2 items below were already done
by the time this correction was made (struck through, not deleted, so the
history stays visible). Root `ROADMAP.md`'s 23-phase table is the
authoritative current status; this list is priority ordering for what's
still genuinely open.

Sequenced, not started unless noted, listed here only so priority order
survives context loss -- see the original planning Artifact for full
rationale on each:

1. Survivability scoring (hitpoints/armor/shield-efficiency composite) --
   unlocked now that Tier 2 added flux/shield fields to `Hull`; armor/
   hitpoints fields would need the same treatment.
2. ~~Full `STRICT_FACTION`/`FACTION_PLUS` enforcement extended to hullmods
   and fighter wings.~~ **Done** (same session, before this correction):
   `generation/hullmods.py`/`generation/fighters.py` both take
   `allowed_hullmod_ids`/`preferred_hullmod_ids` and
   `allowed_wing_ids`/`preferred_wing_ids`, wired into `svg generate` and
   `api.py::run_generate` from a faction's real `known_hullmods`/
   `known_fighters`, the same evidence pattern weapons already used.
3. `analysis/ai_heuristics.py` -- deterministic AI-friendliness proxies from
   documented behavior patterns only, never simulated combat.
4. ~~Richer bounded search (more than one next-ranked alternative per
   mount).~~ **Done** (same session, before this correction): `--search-depth`
   on `svg generate`, breadth-first across ranks, one mount changed at a
   time. See the Tier 4 section above.
5. S-mod scoring assumptions for Advanced mode (a static scoring input,
   distinct from the explicitly-banned "automatic S-mod progression
   planning").
6. Mod dependency-version compatibility and load-order resolution.
7. ~~A representative benchmark/regression suite... canonical hulls like
   Lasher/Hammerhead/Dominator/Heron/Onslaught as fixtures.~~ **Done** (same
   session, after the IP question below was flagged and answered by the
   project owner) -- see "Canonical benchmark suite" section below. Still
   open: calibrating `doctrine_match`'s weights specifically -- this
   benchmark suite covers legality/classification stability, not
   heuristic-weight calibration, which is a separate task.
8. Game-load verification for exports (still offline-only).
9. Batch CLI mode (`cli/batch` in the spec's proposed layout).

Still explicitly out of scope at any future point, per `Forge formal
spec.txt` section 4: machine learning, LLM/external API integration, combat
simulation, automatic piloting, real-time game memory access, save editing,
colony optimization, campaign fleet optimization, multiplayer.

## Second planning-pack refresh: v0.3, a major scope expansion (2026-08-22, evening)

The `Starsector-Variant-Generator-Planning-Pack/` refreshed itself (all
files grew substantially; one entirely new file, `HULLMODS_CIVILIAN_AND_
REFIT.md`, appeared). Root docs were re-synced from it (`AGENTS.md`,
`DATA_SCHEMA.md`, `FORMAL_SPECIFICATION.md`, `GUI.md`, `HEURISTICS.md`,
`README.md`, `ROADMAP.md`, `TEST_PLAN.md`, plus `config/overrides/
hullmod.example.json`). No filename/content scrambling this time --
verified each file's own top heading matches its filename before trusting
any of it, per the lesson from the first pack drop.

This is a real, large scope expansion, not a rewording: a new **Phase 4
(Hullmod Effect Engine)** -- typed `HullmodEffect`/`DerivedShipState`
modeling hullmods as structured stat modifiers, not tags -- a new **Phase
6 (Refit/Repair Assistant)** -- minimal-change improvement of an
*existing* variant, a genuinely different feature from full generation --
and **civilian/logistics ship support** threaded through Classifiers,
Scoring, and Modes (9 named roles: `FREIGHTER`/`TANKER`/`SALVAGE`/
`SURVEY`/`TROOP_TRANSPORT`/`FAST_LOGISTICS`/`STEALTH_LOGISTICS`/
`EXPEDITION_SUPPORT`/`GENERAL_SUPPORT`, plus `HYBRID` combat/civilian
profiles). Root `ROADMAP.md` now tracks 16 phases (0-15); it's been
updated with real status mapped onto the new numbering -- see that file
for the phase table, this file for the reasoning behind each status.

**Why nothing here attempts the full Hullmod Effect Engine yet:** it
requires per-hullmod numeric effect data (e.g. "+30% cargo capacity"),
which demands the same real-data-verification discipline used for flux/
mount-compatibility (SVG-009, SVG-013) -- but at a much larger scale (12
effect categories x ~146 core hullmods, before any mod hullmods). That's
a substantial standalone research effort, not something to rush. Two
concrete, low-risk pieces were pulled out and finished instead:

### Civilian role classification -- **Done, deliberately narrow**

Files: `core/models.py` (`Hull.cargo_capacity`/`fuel_capacity`/
`crew_min`/`crew_max`/`supplies_per_month`/`max_burn`/`hull_hints`),
`parsers/entities.py`, `analysis/classification.py`
(`classify_civilian_role`), `core/registry.py` (`hulls_matching`),
`cli/main.py` (`svg query hulls`, `--civilian-only`).

The hull CSV's own `hints` column carries real, documented role evidence
directly (verified across 211 live core hulls: `CIVILIAN` (17),
`FREIGHTER` (6), `TANKER` (4), `LINER` (4), `CARRIER` (9), `COMBAT` (6),
`TRANSPORT` (2), plus structural markers that aren't role signals at all
and are filtered out: `UNBOARDABLE`, `MODULE`, `STATION`,
`HIDE_IN_CODEX`). This is exposed as-is, evidence-only, matching every
other `classify_*` function's contract.

**Deliberately does not** compute numeric role-compatibility scores
across the spec's full 9-role taxonomy. A cargo/fuel-ratio secondary
signal (for hulls without an explicit hint) was tried and rejected on
real evidence: civilian- and combat-hinted hulls have nearly identical
cargo-capacity medians (95 vs 100 across all real core combat/civilian
hulls), so a numeric threshold would misclassify freely. `hints` also
only covers a subset of the spec's 9 named roles -- nothing in real data
currently distinguishes `SALVAGE`/`SURVEY`/`TROOP_TRANSPORT`/
`FAST_LOGISTICS`/`STEALTH_LOGISTICS`/`EXPEDITION_SUPPORT`/
`GENERAL_SUPPORT` from each other or from `FREIGHTER`. Mapping evidence
onto quality-scored per-role compatibility numbers for all 9 roles is a
real next step, not fabricated here on weak grounds.

Live-verified: `svg query hulls --civilian-only` against the real
install returns exactly 17 core civilian hulls (matching the hint count
above), with sensible per-role numbers -- e.g. `dram` (tagged `TANKER`)
has fuel=300 against cargo=15, `atlas` (tagged `FREIGHTER`) has
cargo=2000. Full suite: 112 tests passing (7 new).

### Manual Override Layer: hullmod effect schema -- **Not yet extended**

`config/overrides/hullmod.example.json` (from the pack) now shows a much
richer schema than weapons' `role_tags` -- typed `effects[]` entries with
`category`/`stat`/`operation`/`value`/`confidence_state`, matching
`DATA_SCHEMA.md`'s new `HullmodEffect` model. `core/overrides.py`
currently only supports the flat `role_tags` shape (weapons scope). Left
open rather than half-built: a typed-effects override loader is more
naturally a piece of the Hullmod Effect Engine (Phase 4) than a
standalone addition to the current override module -- building it first
would mean guessing at `DerivedShipState`'s shape before Phase 4 exists.

### What's still open from this expansion

- Phase 4 (Hullmod Effect Engine) -- **started**, narrowly. See below.
- Phase 6 (Refit/Repair Assistant) -- not started; a genuinely new
  feature (`RefitConstraintSet`/`RefitSuggestion` per `DATA_SCHEMA.md`),
  not an extension of the existing generator.
- Civilian scoring dimensions (`HEURISTICS.md`'s new
  `civilian.freighter.*`/`civilian.tanker.*`/etc. weight sets) --
  unconsumed; nothing in `scoring/` reads them yet, though
  `analysis/civilian.py`'s derived stats (below) are the raw inputs a
  future scoring pass would need.
- `Profile.domain` (`COMBAT`/`CIVILIAN`/`HYBRID` per `DATA_SCHEMA.md`) --
  the profile catalog (`profiles/catalog.py`) has no such field; all 7
  current profiles are implicitly combat-domain.

## Hullmod Effect Engine: a first, narrow slice -- **Done for 4 LOGISTICS hullmods**

Files: `adapters/vanilla/__init__.py` (`HullmodLogisticsEffect`,
`LOGISTICS_HULLMOD_EFFECTS`), `adapters/__init__.py`
(`logistics_hullmod_effects`), `analysis/civilian.py`
(`compute_derived_civilian_stats`), `analysis/variant.py` (wired into
`VariantAnalysis`).

Real hullmod `desc` text for logistics hullmods (`expanded_cargo_holds`,
`auxiliary_fuel_tanks`, `additional_berthing`, `augmentedengines`) turned
out to contain only unfilled `%s` template placeholders -- the actual
numeric bonuses are engine-hardcoded, confirmed absent from
`data/config/settings.json` too. Verified the real numbers from
https://starsector.wiki.gg/wiki (one fetch per hullmod, exact quotes in
`adapters/vanilla/__init__.py`), and did not trust any of it blind: cross-
checked each wiki page's claimed OP cost against this installation's own
already-parsed `Hullmod.op_cost_by_hull_size` (5/10/15/25 by hull size)
before trusting the cargo/fuel/crew bonus numbers from the same pages.

Modeled deliberately narrower than `DATA_SCHEMA.md`'s full `HullmodEffect`
(12 categories, 10 operation kinds): `HullmodLogisticsEffect` covers
exactly the one pattern 3 of 3 researched hullmods actually use ("flat
bonus by hull size, or a percent of the base stat, whichever is higher").
Generalizing to the full operation vocabulary before more categories are
researched would mean guessing at shapes no verified data supports yet.

**Real scope of "LOGISTICS" confirmed (2026-08-22, later):** the live
install's own `data/hullmods/hull_mods.csv` groups hullmods under a literal
`# logistics hullmods` comment marker, giving the authoritative, complete
real set rather than one assembled from memory: `additional_berthing`,
`augmentedengines`, `auxiliary_fuel_tanks`, `expanded_cargo_holds` (the 4
already covered above), plus `efficiency_overhaul`, `hiressensors`,
`insulatedengine`, `militarized_subsystems`, `solar_shielding`, and
`surveying_equipment` -- 6 more, not yet researched at the time this note
was written. Checked their mechanics are NOT the same "flat-by-size-or-
percent stat boost" pattern the first 4 share (they affect sensor range,
burn-level detection thresholds, CR near a star, survey speed, and (for
`efficiency_overhaul`) a percent *reduction* rather than increase --
distinct mechanics each) before assuming a batch add would be a small
extension; it isn't. Each needs its own individually-verified mechanic
and possibly its own `HullmodEffect`-family dataclass, the same
one-hullmod-at-a-time discipline used for the first 4.

**`efficiency_overhaul` done (2026-08-22, later still)** -- see the
dedicated section below. 5 of 10 real LOGISTICS hullmods now covered.

**Remaining 5 resolved (2026-08-22, later still)** -- see "Remaining
LOGISTICS hullmods: researched and resolved" below. `militarized_subsystems`
is now also modeled (6 of 10 covered); `hiressensors`/`insulatedengine`/
`solar_shielding`/`surveying_equipment` were researched and found
genuinely not modelable in this project's current scope, each for a
specific documented reason -- not a gap, a deliberate exclusion.

Two things were deliberately left unresolved rather than fabricated:
- **Stacking of multiple civilian maintenance penalties.**
  `DATA_SCHEMA.md`'s own stacking rules say not to assume ADDITIVE vs
  MULTIPLICATIVE without evidence; none was verified for *combined*
  penalties, so `compute_derived_civilian_stats` reports each applicable
  penalty as a separate note, never a fabricated combined
  `supplies_per_month` number.
- **The Manual Override Layer's typed-effects schema**
  (`config/overrides/hullmod.example.json`'s `effects[]`) is still not
  consumed anywhere -- `core/overrides.py` only supports weapons'
  `role_tags` shape.

Live-verified: `phantom_Elite` (a real core civilian variant, hull_size
`DESTROYER`) with `auxiliary_fuel_tanks` installed: base fuel 100, flat
bonus 60 vs 30%-of-100=30 -> flat wins -> derived 160, matching the
formula exactly. Stress-tested `analyze_variant` across all 5,137 real
variants in the live install (every mod, not just core): 0 exceptions,
all 4 effects fired correctly at least once. Full suite: 119 tests
passing (7 new: `tests/test_civilian.py` plus 1 in
`tests/test_variant_analysis.py`).

**Added since:** an OP-efficiency metric per `HULLMODS_CIVILIAN_AND_REFIT.md`
section 9's own suggested `cargo / OP_spent_on_logistics` formula, chosen
over a fabricated 0-100 "civilian quality score" for the same
no-defensible-normalization-scale reason survivability scoring was
rejected. `AppliedLogisticsEffect` (new dataclass) carries `op_cost` and
`efficiency` (gain per OP, `None` when OP cost isn't resolvable rather
than a fabricated 0) alongside each applied effect;
`compute_derived_civilian_stats` now takes a required `registry`
parameter to resolve real `Hullmod.op_cost_by_hull_size` data.
`applied_effect_hullmod_ids` became a computed property over the new
`applied_effects` tuple. Re-verified on the same real `phantom_Elite`
variant: `auxiliary_fuel_tanks` reports efficiency 6.0 (gain 60 / OP cost
10), and the unrelated `efficiency_overhaul` hullmod on that variant
stays correctly in `unverified_hullmod_ids`. This is still per-effect
data, not yet aggregated into `QualityAssessment`'s score (see "still
open" above). Full suite: 121 tests passing (2 new).

## Service layer for GUI readiness: `api.py` -- **Done**

Files: `src/starsector_variant_generator/api.py` (new), `cli/main.py`
(rewritten to call it).

`cli/main.py` had grown to ~200 lines of real orchestration logic inside
one `argparse`-dispatch function -- mode/advanced-request resolution,
faction restriction assembly (weapons/hullmods/fighters), candidate
generation + legal-before-quality ranking, faction disambiguation, report-
dict assembly -- contradicting `CLAUDE.md`'s own architecture description
("`cli/main.py` ... contains no business logic of its own beyond argument
validation and report serialization"). A GUI would have had to either
shell out to the `svg` CLI and re-parse its stdout/JSON files, or
re-implement all of that orchestration itself; `GUI.md` section 50's own
Readiness Gate says the production GUI "should bind to those services
directly" once contracts are stable, which presupposes such a binding
surface exists.

Extracted one function per CLI command into `api.py`
(`run_scan`/`run_query_weapons`/`run_query_hulls`/`run_query_variants`/
`run_query_faction_equipment`/`run_validate`/`run_generate`/`run_export`/
`run_doctrine`/`run_analyze_variant`/`run_check_export`, plus
`build_registry`/`resolve_faction` helpers). Each is read-only against
game/mod sources, returns the same dataclass/dict the CLI already
serialized, and raises `ValueError` on the same user-facing conditions the
CLI already checked (unknown/ambiguous variant or faction, invalid
profile, out-of-range `--max-candidates`/`--search-depth`, conflicting
advanced-request fields) -- callers decide presentation (CLI: exit code 2
via `parser.error`; a GUI: an error dialog). None of them print or write
report files; `cli/main.py` still owns that, so its role now matches what
`CLAUDE.md` already claimed it was.

This was a mechanical extraction, not a rewrite: every line of logic moved
verbatim, so CLI-observable behavior is unchanged by construction. Verified
rather than assumed: full suite still 121/121 passing byte-for-byte
(including the golden regression test), and re-ran live smoke tests
against the real install across `generate` (advanced mode, `lasher`),
`validate` (`apogee_Starting`), `doctrine` (`hegemony --source-mod core`),
`query hulls --civilian-only`, and `export` (`lasher`/`LINE_BRAWLER`) --
identical report paths and outcomes to before the refactor.

## Third planning-pack refresh: v0.4 (2026-08-22, later)

`Starsector-Variant-Generator-Planning-Pack/` was refreshed again, all 9
files bumped 0.3 -> 0.4. Checked every file's own top heading against its
filename first (per the standing reconciliation discipline) -- no
scrambling this time. Diffed every file against its currently-synced root
copy before trusting it: `DATA_SCHEMA.md`, `HEURISTICS.md`, `TEST_PLAN.md`,
`FORMAL_SPECIFICATION.md`, and `HULLMODS_CIVILIAN_AND_REFIT.md` had zero
removed/changed lines beyond the version bump (purely additive);
`README.md` was reorganized but not contradicted; `AGENTS.md` and `GUI.md`
each gained a large, purely-additive new section. Synced all 8 shared-name
root docs directly from the pack.

New scope, entirely unimplemented so far (see root `ROADMAP.md` phases 6,
7, 9, 10 for the reconciled status rows): a **Faction Capability
Analyzer** (strengths/weaknesses/gaps from parsed data alone), a
**Faction Knowledge Pack Framework** (optional, versioned, curated
doctrine/retrofit packs with a CURRENT/PARTIALLY_STALE/STALE/INCOMPATIBLE
freshness model -- explicitly distinct from the existing weapons-only
Manual Override Layer, since packs can never override hard legality), a
**Gap Recommendation Engine** (NATIVE/RETROFIT/ACQUISITION ranked
shortlists per gap), and **Recommendation Explainability** (separate
score/confidence, solution diversity, "Why wasn't this recommended?").
`GUI.md` also gained matching UI spec: 5 named top-level workspace tabs
(Ships/Retrofits/Faction/Data-Analysis/Settings-Export, section 55),
cross-workspace navigation rules (section 56), and the faction
recommendation/why-not/knowledge-pack-status presentation these new
engine phases would feed (sections 57-60).

Root `ROADMAP.md`'s phase table was reconciled from 16 phases (0-15) to
23 (0-22) to match, preserving this project's own real evidence-based
statuses on every carried-forward row and marking the new phases
NOT_STARTED (nothing in this scope has been built). `docs/
IMPLEMENTATION_STATUS.md`'s numbering-reconciliation note was updated to
match. No code changes were needed or made for this refresh -- it is pure
future scope, not a correction to already-implemented behavior.

## Faction Capability Analyzer: a first, narrow slice -- **Started**

Files: `analysis/faction_capability.py` (new), `api.py::run_faction_capability`
(new), `cli/main.py` (new `svg faction-capability <faction_id>` command).

Root `ROADMAP.md` phase 6, opened by the v0.4 refresh above. `AGENTS.md`'s
own wording leaves the methodology open ("build a useful faction
capability profile from installed mod data alone using parseable hulls,
weapons, fighters, variants, built-ins, known hullmod effects, and role
classifications") -- so rather than invent a new scoring mechanism, this
slice reuses two already-tested classifiers verbatim: `classify_hull`'s
non-exclusive `role_compatibility` dict (`CARRIER`/`BATTLE_CARRIER`/
`MISSILE_SUPPORT`/`LINE_ARTILLERY`/`LINE_BRAWLER`, each 0.0-1.0) and
`classify_civilian_role`'s hint-tag evidence, applied over a faction's
real, already-parsed `known_hulls`. For each role, it reports the single
best-scoring known hull and its score -- raw evidence, not a verdict.

Deliberately NOT attempted: a combined pass/fail "gap" verdict, a
confidence score, or NATIVE/RETROFIT/ACQUISITION shortlists. Those are
root `ROADMAP.md` phases 9 and 10 specifically, and each needs its own
defensible methodology (what threshold makes a 0.44 `MISSILE_SUPPORT`
score a "gap"? what does "confidence" even measure here?) -- answering
that now, on no real basis, would be exactly the kind of fabrication this
project has consistently avoided. Reporting the raw per-role evidence lets
a future caller apply its own threshold instead.

Live-verified against real Hegemony data (`svg faction-capability
hegemony --source-mod core`) and stress-tested across all 431 real
factions in the live install (every enabled mod, not just core): 0
exceptions. The live run also did real work beyond validating this
module: 9 of Hegemony's 28 `known_hulls` (`onslaught_xiv`,
`dominator_xiv`, `eagle_xiv`, `falcon_xiv`, `enforcer_xiv`, and four
faction-prefixed frigate ids) failed to resolve against the registry.
Traced this to a genuine unparsed data source rather than assuming it was
a bug in the new module: `data/hulls/skins/*.skin` files, confirmed
present in the live install (`starsector-core/data/hulls/skins/
onslaught_xiv.skin`), which declare a `skinHullId` derived from a real
`baseHullId` plus explicit override lists (`removeWeaponSlots`/
`removeBuiltInMods`/`builtInMods`/etc.) -- a real, parseable JSON format
the scanner has simply never ingested. Logged as SVG-014 (open, not
fixed here: parsing skins correctly means merging override lists onto a
base hull without guessing at unlisted fields, which is its own bounded
scanner feature, not a one-line patch). `unresolved_known_hull_ids`
existing at all is exactly what caught this -- silently dropping
unresolved ids instead would have hidden it. Full suite: 125 tests
passing (4 new: `tests/test_faction_capability.py`).

## SVG-014 fixed: `.skin` file ingestion -- **Done**

Files: `parsers/entities.py` (`hull_from_skin`, `_apply_id_list_override`),
`core/scanner.py` (`_scan_skin_files`, `_resolve_skins`),
`parsers/common.py` (`_relaxed_json` bare-leading-decimal fix).

Surveyed all 66 real core `.skin` files' field vocabulary before writing
any code (`baseHullId`/`skinHullId`/`hullName`/`ordnancePoints`/
`fighterBays`/`suppliesPerMonth`/`removeWeaponSlots`/`weaponSlotChanges`/
`removeEngineSlots`/`removeBuiltInMods`/`builtInMods`/
`removeBuiltInWeapons`/`builtInWeapons`/`builtInWings`/`removeHints`/
`addHints`, plus fields not yet modeled as typed `Hull` attributes:
`maxSpeed`/`shieldEfficiency`/`systemId`/`engineSlotChanges`/
`restoreToBaseHull`/`coversColor`/`style`/`descriptionId`/
`descriptionPrefix`/`spriteName`/`tags`/`tech`/`baseValueMult`/
`incompatibleWithBaseHull`/`suppliesToRecover`). `hull_from_skin` applies
only the fields with unambiguous, directly-declared semantics -- explicit
remove/add id-list pairs (mounts, built-in mods, built-in weapons, hints)
or a single scalar override -- and preserves everything else verbatim in
`raw` rather than guessing at fields this project doesn't model yet. The
remove/add pairing pattern (`removeBuiltInMods` + `builtInMods`, etc.) is
read as "remove-then-add" (additive after explicit removal) based on real
skin files that declare both, e.g. `onslaught_xiv.skin`'s
`"removeBuiltInMods":[]` next to `"builtInMods":["fourteenth"]`.

Resolution is deliberately deferred to a single pass after every mod
finishes scanning, not resolved per-mod: a skin's `baseHullId` can name a
hull from a *different* mod than the skin's own (a mod skinning a core
hull, for instance), so resolving early risks missing a base hull that
hasn't been scanned yet. Never guesses at an unresolved or ambiguous
(duplicate-id) base hull -- reports a warning naming the skin file and the
reason instead of silently dropping or arbitrarily picking one.

Live stress-tested against the full real 148-mod install: hull count rose
from 4,430 to 4,736 (+306 real skinned hulls -- every core `_d`/`_xiv`/
faction-variant ship, plus mod-added skins), 0 exceptions, `Registry`
indexing unaffected. Found only 2 genuine data-quality cases across the
entire install, both correctly surfaced as warnings rather than guessed
through: one skin (`wolf_d_pirates.skin` in a third-party mod) missing
`baseHullId`/`skinHullId` entirely, one (`nsp_fabricator_unit_player.skin`)
naming a `baseHullId` that's ambiguous across two mods.

A second, related real gap surfaced and was fixed in the same pass: the
first stress-test run had 29 `.skin` parse errors, 20 of them the exact
same "Expecting value" pattern. Traced to real core files
(`lasher_d.skin` and 19 others) using a bare leading-decimal numeric
literal (`"baseValueMult":.7`), which is invalid JSON but a real,
widespread convention in these files -- not a one-off typo. Extended
`_relaxed_json`'s existing HJSON-tolerance normalization (which already
handles comments/trailing commas/bare keys/single-quoted strings/numeric
`f`/`d` suffixes) with the same string-boundary-safe approach, following
the identical precedent already established for the numeric-suffix case.
Re-verified: parse errors dropped from 29 to 5, and the remaining 5 were
individually inspected and confirmed to be genuinely malformed source
files (an extra, mismatched closing brace, e.g. `manticore_pather.skin`
line 22) in their own right -- correctly left as errors rather than
guessed at, since silently "fixing" a brace mismatch risks producing a
plausible-looking but wrong merged hull.

Re-ran `svg faction-capability hegemony --source-mod core` after the fix:
`unresolved_known_hull_ids` dropped from 9 to 0 (37/37 known hulls now
resolve), and the `MISSILE_SUPPORT` role's best-evidence hull changed from
`enforcer` (0.44) to the now-resolved `kite_hegemony` (0.67) -- a real
accuracy improvement in existing Phase 6 output, not just a coverage
statistic. 11 new tests (7 for `hull_from_skin`, 2 scanner-integration
using new realistic `.skin` fixtures, 1 for the leading-decimal fix, plus
the pre-existing scanner hull-count assertion updated for the new hull).
Full suite: 135 tests passing.

End-to-end pipeline check (beyond parsing correctness): a scanner change
that adds 306 new real hulls could destabilize anything downstream that
enumerates or generates against all hulls, so stress-tested the full
pipeline against every one of the 306 real skinned hulls, not just the
parser output. `generate_candidate_alternatives` across all 306 skinned
hulls x 3 profiles (918 runs): 0 exceptions, 2,598 legal candidates
produced. `generate_conservative_candidate` -> `score_candidate` ->
`write_compatibility_mod` across the first 40 skinned hulls: 40/40
exported with 0 exceptions. The new hulls behave exactly like any other
real `Hull` entity through the rest of the pipeline, as expected since
they're materialized as ordinary `Hull` instances, not a special case.

## Canonical benchmark suite -- **Done**

Files: `tests/fixtures/synthetic/*.json` (5 archetypes), `tests/fixtures/schemas/*.schema.json`,
`tests/benchmark_support.py`, `tests/test_benchmark_portable.py`,
`tests/canonical/benchmark_manifest.json`, `tools/build_local_benchmarks.py`,
`tests/test_canonical_local.py`, `tests/local_fixtures/.gitignore`,
`tests/local_results/.gitignore`.

Resolves the IP question flagged earlier in this document (item 7 above):
whether copying real Starsector source-file content into this project's
committed test fixtures is appropriate. The project owner answered with a
specific three-layer design (quoted in full in the session that requested
it); this implements that design, adapted to two real constraints the
proposal didn't have in front of it -- this project's test runner is
`unittest`, not `pytest` (no `-m portable`/`-m canonical_local` markers;
used `unittest.SkipTest` in `setUpClass` instead, which gives the same
"skip cleanly with no local data" behavior), and the classifier vocabulary
actually implemented today is `classify_hull`'s five real
`role_compatibility` keys (`CARRIER`/`BATTLE_CARRIER`/`MISSILE_SUPPORT`/
`LINE_ARTILLERY`/`LINE_BRAWLER`), not the proposal's illustrative
`SKIRMISHER`/`ASSAULT`/`armor_profile_scores_high` examples, which don't
exist as classifier outputs here and weren't invented just to match the
example.

**Layer 1 -- synthetic archetypes (always run, no install needed).** Five
hand-authored hulls (`frigate_ballistic_aggressive`,
`destroyer_forward_mixed`, `cruiser_armor_artillery`,
`carrier_strike_support`, `capital_heavy_broadside`) with invented mount
counts/OP/flux values -- structural stand-ins for the five real classes,
not copies of any real ship's stats. `tests/test_benchmark_portable.py`
checks mount-class parsing, that each archetype's classifier scores rank
as expected relative to the others (capital highest `LINE_BRAWLER`,
armored cruiser highest `LINE_ARTILLERY`, only the carrier has `CARRIER`
evidence), that every archetype produces a `LEGAL` conservative candidate,
and that an energy weapon is correctly rejected on the frigate's
pure-ballistic mount. 6 new tests, always run, 0 real-data dependency.

**Layer 2 -- local extractor.** `tools/build_local_benchmarks.py
--starsector-path <path>` scans the user's own install and writes, per
canonical hull in the manifest: `tests/local_fixtures/<id>.generated.json`
(structural fields only -- hull size, mount id/type/size, fighter bay
count, hull hints; deliberately never name/description/sprite/tags/tech,
even though this directory is gitignored, on the "preserve only what's
needed" principle from the proposal) and
`tests/local_results/<id>_baseline.json` (this project's own computed
`classify_hull`/`classify_civilian_role`/legality output -- derived
behavior, not copied game data, though still kept local per the proposed
layout). Both directories ship a `.gitignore` (`*` plus an exception for
`.gitignore`/`.gitkeep` itself) since this project has no git repository
yet to test the ignore rule against, but the file is there for when one
exists.

**Layer 3 -- behavior manifest + local-only tests.**
`tests/canonical/benchmark_manifest.json` (committed) names 5 real hull
ids (`lasher`/`hammerhead`/`dominator`/`heron`/`onslaught`) with only
general, widely-documented archetype facts (hull size, one or two
well-known mount classes, which role(s) should score above zero) -- no
copied stat blocks. `tests/test_canonical_local.py` skips the whole class
with a clear message (naming the exact command to run) when no local data
exists, and otherwise checks each hull's real extracted data against its
manifest entry.

**Live-verified end to end**, including a real self-correction: ran the
extractor against the real install -- all 5 canonical hulls resolved. The
local test suite then failed on `canonical_frigate_lasher`: the manifest's
`expected_mount_classes` guessed `MEDIUM_BALLISTIC` from general
recollection, but the real extracted data showed Lasher is all
`SMALL_BALLISTIC` (5 mounts) plus `SMALL_MISSILE` (2) -- no medium mount
at all. Corrected the manifest to match the real data rather than trusting
the initial guess; the other 4 hulls' guessed facts (Hammerhead's medium
ballistic mounts, Dominator's 2 large ballistic mounts, Heron's 3 fighter
bays and `CARRIER` hint, Onslaught's 3 large ballistic mounts) all matched
real data exactly on the first run. This is exactly the failure mode the
three-layer design exists to catch -- a plausible-sounding assumption
about a real ship, caught by real data instead of shipping unverified.
Full suite: 142 tests passing (7 new: 6 portable + 1 local-canonical,
which only runs when local data is present -- skips cleanly otherwise, as
verified by running the suite both before and after generating local
data).

## Manual Override Layer extended: hulls, and wired into generation -- **Done**

Files: `core/overrides.py` (unchanged -- `load_overrides`/
`apply_role_tag_override` were already generic over entity kind),
`generation/candidate.py` (`weapon_role_overrides` parameter),
`analysis/variant.py` (`hull_role_override` parameter,
`civilian_role_tags_overridden` field), `api.py` (`run_generate`/
`run_query_hulls`/`run_analyze_variant` all gained/use `overrides_dir`),
`cli/main.py` (`--overrides-dir` added to `analyze-variant`; `generate`
and `query hulls` now actually use the flag they already had wiring for).

Two closely related but distinct gaps, both flagged in
`docs/IMPLEMENTATION_STATUS.md` since the override layer was first built:
"covers weapons only" and "isn't yet consumed by generation/export, only
by query." Addressed both: hulls now get the same `role_tags` override
shape weapons already had (`config/overrides/hulls.json`, additive-only,
same file), and the *existing* weapons override now actually changes
generated output, not just `query` reports -- `generation/candidate.py`'s
`PD_FIRST` weapon-priority sort (used by the `PD_ESCORT` profile) is the
one place `classify_weapon`'s role tags feed generation; a caller-supplied
override can now add a `PD` tag a mod's own data doesn't declare, sorting
that weapon first, same as real evidence would.

Deliberately did NOT extend overrides to fighters/hullmods/factions:
`classify_fighter`/`classify_hullmod` expose structural facts (a wing's
own declared role string; whether a hullmod's OP-cost table parsed) that
an override doesn't obviously make sense for -- overrides exist to
*supplement missing evidence* the way a weapon's real-but-untagged "PD"
behavior or a hull's real-but-unhinted "CIVILIAN" role does, not to
contest already-parsed structural facts. If a real need for fighter/
hullmod/faction overrides surfaces, it should be scoped from that real
need, not added reflexively for symmetry.

Both new backward-compatible parameters (`weapon_role_overrides` on
`generate_conservative_candidate`/`generate_candidate_alternatives`/
`_build_candidate`; `hull_role_override` on `analyze_variant`) default to
`None`, so every existing caller -- including the golden regression test
-- sees identical output; verified by the full suite passing unchanged
before adding new override-specific tests. 3 new tests (1 generation, 2
variant-analysis). Live-verified against the real install: a
`config/overrides/weapons.json` entry changed which weapon `svg generate
lasher --profile PD_ESCORT` selected; a `config/overrides/hulls.json`
entry adding `CIVILIAN` to `apogee` (not civilian-hinted in vanilla) made
it appear in `svg query hulls --civilian-only` and in `svg analyze-variant
apogee_Starting`'s `civilian_role_tags`, both correctly flagged
`..._overridden: true`. Full suite: 144 tests passing.

## Hullmod Effect Engine: `efficiency_overhaul` -- **Done**

Files: `adapters/vanilla/__init__.py` (`HullmodPercentReductionEffect`,
`EFFICIENCY_HULLMOD_EFFECTS`), `adapters/__init__.py`
(`efficiency_hullmod_effects`), `analysis/civilian.py`
(`AppliedReductionEffect`, `DerivedCivilianStats.applied_reduction_effects`/
`.supplies_per_month`/`.crew_min`).

The first of the 6 real LOGISTICS hullmods left unresearched (see the
"real scope of LOGISTICS confirmed" note above). Researched from
https://starsector.wiki.gg/wiki/Efficiency_Overhaul the same way as the
original 4: the hullmod's own `desc` field is an unfilled `%s` template
(numbers engine-hardcoded), so trusted the wiki only after cross-checking
its claimed OP cost (3/6/9/15) and base value (4,000 credits) exactly
against this installation's own already-parsed data.

The mechanic itself does NOT fit `HullmodLogisticsEffect`'s
"flat-by-size-or-percent-whichever-higher, applied as a gain" shape --
Efficiency Overhaul is a flat 20% *reduction* to supply use for
maintenance and minimum crew required. `max(flat, percent)` has no
sensible meaning for a reduction (there's no flat-vs-percent alternative
to pick the larger of; the whole percentage always applies), so rather
than bend the existing type to fit, added a second, explicitly distinct
type: `HullmodPercentReductionEffect` (a list of affected stats plus one
percent-reduction figure) and a matching `AppliedReductionEffect` result
type (no `efficiency` field -- gain-per-OP is meaningless for a
reduction). `compute_derived_civilian_stats` now checks both tables per
hullmod id in a single pass (an id unresolved in *either* table is
`unverified`, not silently treated as belonging to whichever table was
checked first).

Two of the wiki page's effects were explicitly NOT modeled, each noted in
the adapter's own citation rather than silently dropped: the separate
combat-readiness-recovery/repair-rate bonuses (this project has no CR or
repair-rate `Hull` stat at all) and the additional 10% S-mod-only
reduction (this project has no S-mod concept on `Variant` yet -- adding
one just for this would be scope creep into a feature area of its own).
Also explicitly not modeled: "fuel use" in the wiki's sense means fuel
consumed per day of travel, a different, currently-unmodeled stat from
`Hull.fuel_capacity` -- only `supplies_per_month`/`crew_min` (both fields
this project already tracked) are represented.

Fixing this surfaced (and fixed) a latent bug in
`DerivedCivilianStats.applied_effect_hullmod_ids`: a hullmod affecting two
stats at once (exactly what `efficiency_overhaul` does) would appear
twice in the property's output; it now deduplicates.

Live-verified against the same real `phantom_Elite` variant used to
validate the original engine (it has both `auxiliary_fuel_tanks` and
`efficiency_overhaul` installed): base `supplies_per_month` 10 -> 8 and
base `crew_min` 5 -> 4, both an exact 20% reduction; `efficiency_overhaul`
was previously the one entry in this variant's `unverified_hullmod_ids`
and is now correctly resolved. Stress-tested `analyze_variant` across all
5,606 real variants in the live install: 0 exceptions, `efficiency_overhaul`
fired on all 4 real variants that use it. 5 new tests. Full suite: 148
tests passing.

## Remaining LOGISTICS hullmods: researched and resolved -- **Done**

Files: `adapters/vanilla/__init__.py` (2 new `HullmodLogisticsEffect`
entries for `militarized_subsystems`, plus a documentation-only note for
the other 4), `analysis/civilian.py` (`compute_derived_civilian_stats`
now groups increase effects by hullmod id into a list, applying every
matching entry instead of assuming one per id).

Researched all 5 remaining real LOGISTICS-tagged hullmods
(`hiressensors`, `insulatedengine`, `militarized_subsystems`,
`solar_shielding`, `surveying_equipment` -- see the "real scope of
LOGISTICS confirmed" note above) via https://starsector.wiki.gg/wiki, one
fetch per hullmod, cross-checking every claimed OP cost and base value
against this installation's own parsed data before trusting anything
else on the page -- all 5 matched exactly. The outcome: 1 of the 5 is
fully modelable, 4 are not, each for a specific, verified reason (not
"not yet researched" -- actually investigated and excluded):

- **`hiressensors`** (High Resolution Sensors): its real effect is a
  *fleet-wide* campaign-map sensor-range bonus (+50/75/100/150 by hull
  size), not a per-ship stat at all. Root `ROADMAP.md`'s own "Current
  Scope Boundary" explicitly defers whole-fleet optimization. Its only
  per-ship effect is an S-mod-only in-combat vision bonus; this project
  has no S-mod concept on `Variant`.
- **`insulatedengine`** (Insulated Engine Assembly): three effects --
  engine durability +100% (no "engine" sub-stat exists anywhere in this
  project's `Hull` model), sensor profile -50% (a campaign-detection
  stat, not a CSV column, not modeled), and hull integrity +10% (the CSV
  *does* have a real, currently-unparsed `hitpoints` column this could
  theoretically map to -- deliberately not parsed just to support one
  tenth of one hullmod's effect with no other consumer anywhere in this
  project; that's the kind of premature schema growth Agent.md's
  discipline exists to prevent).
- **`solar_shielding`** (Solar Shielding): reduces a specific campaign
  hazard's CR penalty, plus a flat 10% in-combat energy-damage
  reduction. The damage-reduction effect specifically would mean
  modeling live combat damage math -- `Forge formal spec.txt` section 4
  rules out "combat simulation" at any future point, not just for v0.1.
- **`surveying_equipment`** (Surveying Equipment): reduces the resource
  cost of the campaign-map "survey a planet" action. Not a ship stat at
  all -- a campaign-action cost modifier, entirely outside this
  project's per-variant analysis scope.

All 4 exclusions are documented directly in `adapters/vanilla/__init__.py`
(with their cross-checked OP costs, not just the mechanic) specifically
so a future session doesn't re-research these from scratch, or worse,
assume the gap is an oversight and try to force-fit them.

**`militarized_subsystems`** (Militarized Subsystems) is the one that IS
modelable: flat +1 max burn level (all hull sizes) and a flat +100%
(doubled) minimum crew requirement -- both stats this project already
tracks (`max_burn`, `crew_min`), and both fit the existing
`HullmodLogisticsEffect` "flat-or-percent increase" shape perfectly (the
crew-doubling is `percent_bonus=1.0` with `flat_bonus_by_hull_size=0`,
i.e. `max(0, base*1.0) = base`, exactly doubling). The real CSV's own
`desc` field independently corroborates two separate effects even though
its `%s` placeholders are unfilled ("increases maximum burn level by %s
... Increases minimum crew required by %s"), matching the wiki's
two-effect claim from a second, independent source.

Implementing it surfaced a real, previously-unexercised limitation:
`LOGISTICS_HULLMOD_EFFECTS` was looked up as `{hullmod_id: effect}`, a
dict that silently keeps only the *last* entry if a hullmod_id appears
twice -- every hullmod researched before this one affected exactly one
stat, so the collision never came up. Fixed by grouping into
`{hullmod_id: [effects]}` and applying every matching entry per hullmod
id (an id is `unverified` only if *none* of its effects could be applied
to this specific hull, not if any single one couldn't).

Live-verified against the real `venture_Balanced` variant (the only real
core variant carrying `militarized_subsystems`): base `max_burn` 7 -> 8
(exact +1) and base `crew_min` 80 -> 160 (exact doubling). Stress-tested
`analyze_variant` across all 5,606 real variants in the live install: 0
exceptions, `militarized_subsystems` fired correctly on all 3 real
variants that use it. 6 new tests (2 for the two-effect case and its
partial-verification edge case, in `tests/test_civilian.py`). Full suite:
150 tests passing.

Real LOGISTICS hullmod coverage: **6 of 10** (`expanded_cargo_holds`,
`auxiliary_fuel_tanks`, `additional_berthing`, `augmentedengines`,
`efficiency_overhaul`, `militarized_subsystems`), with the remaining 4
(`hiressensors`/`insulatedengine`/`solar_shielding`/`surveying_equipment`)
resolved as deliberately out of scope rather than left open. This closes
the "6 remaining LOGISTICS hullmods" item from the "own priority"
recommendation list.

## Gap Recommendation Engine v1 (native-only) -- **Done**

Full design and traceability: root `GAP_RECOMMENDATION_ENGINE.md`
(project-authored, not synced from the pack). Short version: the project
owner supplied a detailed algorithm design and asked for a feasibility
assessment before building. Assessment found the full design sound and
consistent with the newly-landed `FACTION_KNOWLEDGE_PACKS.md`, but
structurally dependent on three unstarted phases (7 Knowledge Packs, 8
Equipment Access/Adaptive Autofit, 9 Refit Assistant) -- retrofit cost
specifically has nothing to diff against without a Refit Assistant. The
project owner chose to write the full spec now plus implement only the
native-only leg, which needs nothing beyond the already-partially-built
Faction Capability Analyzer.

`core/heuristics.py` gained gap-severity/count thresholds
(`gap_strong_threshold`/`gap_adequate_threshold`/`gap_weak_threshold`/
`gap_recommendation_count`, `baseline_0.2`); `analysis/gap_recommendation.py`
implements `detect_capability_gaps` (classifies each of `classify_hull`'s
5 real capability axes into STRONG/ADEQUATE/WEAK/GAP, returning only
WEAK/GAP as `CapabilityGap` records) and `recommend_native_solutions`
(ranks the faction's own known hulls per gap); wired into
`api.py::run_gap_recommendations` and `svg recommend <faction_id>`.

**A real design bug was caught by writing this engine's own tests before
any release**, not after: the initial formula mirrored the supplied
design's `capability_gain = candidate_score - faction_existing_coverage`
directly. For native search specifically this is structurally broken --
`faction_existing_coverage` is defined as the best score *within the
exact same native hull set* being ranked, so no native hull can ever
exceed a baseline derived from its own set's maximum; every candidate's
gain was <= 0 by construction, making the whole mechanism a silent
no-op. The first test written against it (three hulls at
0.125/0.25/0.375, expecting all three to rank) could not be satisfied.
Traced the root cause instead of weakening the test, and fixed both the
code (rank by raw `capability_score`) and the design doc itself -- with
the bug and its fix documented inline in `GAP_RECOMMENDATION_ENGINE.md`
section 6, not silently corrected. The `capability_gain` formula remains
correct and un-changed for the (not-yet-implemented) retrofit/acquisition
legs, where the candidate pool genuinely sits outside the baseline set.

9 new tests (`tests/test_gap_recommendation.py`). Full suite: 159 tests
passing. Live-verified against the real install: Hegemony (well-rounded
across all 5 axes) shows 0 gaps; Pirates shows a real `CARRIER` gap with
zero native solutions (`unaddressed_gaps` -- pirates genuinely field no
carrier-evidence hulls) alongside `BATTLE_CARRIER`/`LINE_ARTILLERY` weak
spots with ranked native alternatives (`atlas2`, `manticore_pirates`) --
matching real, well-known Starsector faction characteristics. Several
other core factions (Lion's Guard, Luddic Church, Sindrian Diktat,
Tritachyon) show a plausible `MISSILE_SUPPORT/WEAK` gap. Stress-tested
`recommend_native_solutions` across all 431 real factions in the live
install: 0 exceptions.

Retrofit, acquisition, retrofit cost, role distortion, the full
composite recommendation score, confidence propagation beyond evidence-
completeness, knowledge-pack doctrine bias, and Why-Not all remain
unimplemented -- each is a real, documented dependency on Phases 7-9,
not an oversight. See `GAP_RECOMMENDATION_ENGINE.md` section 2's
implementation-status table for the authoritative per-section breakdown.

## Equipment affinity classification (Phase 8, first slice) -- **Done**

Files: `analysis/equipment_affinity.py`, `api.py::run_query_weapons`
(now also `requesting_faction_id`-aware).

`EQUIPMENT_ACCESS_AND_AUTOFIT.md`'s affinity model
(`NATIVE`/`APPROVED`/`COMMON`/`UNALIGNED`/`FOREIGN`/`RESTRICTED`/
`UNKNOWN`) needs the `ADAPTIVE`/`STARSECTOR_STYLE` substitution engine
(sections 9-12) to be genuinely useful end to end, and that engine needs
a Refit Assistant (Phase 9, unstarted) to have anything to substitute
*within*. Rather than wait, pulled out the one piece groundable in real,
already-parsed data right now: classifying an item's real faction
ownership. `classify_equipment_affinity` checks every real faction's
`known_weapons`/`known_fighters`/`known_hullmods` (including
ambiguous-duplicate-id factions, so ownership evidence isn't silently
dropped the way `Registry.by_id` alone would) for membership, and maps
that into 4 of the spec's 7 affinity states: `NATIVE` (the requesting
faction owns it), `COMMON` (`common_threshold`, default 4, factions own
it -- a judgment call, not a documented game mechanic, kept as a
caller-overridable parameter rather than a versioned heuristic since it
classifies *evidence*, not a quality/legality outcome), `FOREIGN` (fewer
factions, not including the requester), `UNALIGNED` (no faction
references it at all). Deliberately does not produce `APPROVED`/
`RESTRICTED`/`UNKNOWN` -- section 8's own evidence order puts those above
"faction data references" (explicit override, knowledge pack), neither
of which exists in this project yet. Never infers affinity from
`source_mod_id` alone, matching section 8's explicit warning against
exactly that shortcut.

Wired into `svg query weapons --faction-id <id>` (the command's existing
faction-context flag, doing double duty as "requesting faction" for this
new field) as `faction_affinity`/`owning_faction_ids` per weapon record.
8 new tests covering each affinity outcome, the NATIVE-beats-COMMON
precedence, duplicate-id factions counting as evidence, and fighters/
hullmods using their own distinct known-lists (not falling back to
weapons'). Full suite: 167 tests passing.

Live-verified against the real install: querying all 3,193 real core+mod
weapons with `--faction-id hegemony` gave a plausible split (2,822
UNALIGNED, 270 FOREIGN, 59 NATIVE, 42 COMMON) -- e.g. `A_S-F_bramble`,
owned by all 9 core factions including Hegemony, correctly resolves
`NATIVE` (the requester's own ownership wins over the COMMON threshold)
rather than `COMMON`. Re-ran without a `--faction-id`: 0 NATIVE (no
requester to match) and a larger COMMON bucket (97, since items
previously NATIVE-to-Hegemony with 4+ total owners now fall through to
COMMON), exactly the expected degradation with no requesting-faction
context.

## Faction Knowledge Pack Framework, first slice -- **Done**

Files: `knowledge_packs/schema/faction_pack.schema.json`,
`knowledge_packs/examples/hmi.example.json`, `core/knowledge_packs.py`.

The project owner supplied a concrete three-artifact design directly
(schema as the machine contract, `FACTION_KNOWLEDGE_PACKS.md` -- already
synced -- as the human-readable semantics, a worked example as the
"how these pieces fit together" teaching document) rather than asking
this project to invent one from nothing, resolving exactly the gap
flagged when Phase 7 was first assessed ("no real bundled pack exists
anywhere to validate a manifest/freshness schema against").

Implemented faithfully to that design: `manifest.schema_version` /
`pack_version` / `target_mod_version` as three independent fields (the
owner's own reasoning -- "that distinction will save pain later" --
matches this project's existing `heuristic_set` vs. game-version
separation elsewhere); required-vs-optional top-level sections exactly as
specified (`manifest`+`faction` required; `hull_archetypes`/
`retrofit_templates`/`progression_tiers`/`capability_gap_guidance`/
`officer_guidance`/`notes` all optional, so a minimal weapon-doctrine-only
pack and a fully-detailed pack are both valid against the same schema);
IDs-not-display-names for every hull/weapon/hullmod/fighter/faction
reference; section-level `basis[]`+`confidence` provenance on every
guidance entry rather than one pack-wide confidence figure.

**Verified the example against real data before trusting it**, matching
this project's standing discipline for every other numeric or factual
claim this session: `roach_king` (the owner's example hull id) is
confirmed real -- "Roach King", a Heavy Junker Cruiser in the actually-
installed Hazard Mining Incorporated mod. The mod/faction id was
initially assumed to be lowercase `"hmi"` (a reasonable guess from the
mod's folder name) and corrected to the real uppercase `"HMI"` after
checking the live install's own `mod_info.json` (`"id":"HMI"`) and
`hmi.faction` (`"id":"HMI"`) -- exactly the kind of assumption this
project's verify-before-trust discipline exists to catch. The example's
`manifest.source_hashes` are the real SHA-256 hashes of this
installation's actual `hmi.faction` and `ship_data.csv` files (computed
directly, not invented), so the freshness-assessment code has something
genuine to check itself against.

**A second real bug was caught before any test ran**, this time in the
loader code itself rather than a test: the first draft of
`assess_pack_freshness` checked mod presence via `registry.mods`, which
does not exist -- `Registry` only ever stores entity indexes (hulls,
weapons, fighters, hullmods, variants, factions); `ScanResult.mods` (the
list of `ModInfo`) is discarded the moment `Registry.from_scan` finishes
building those indexes. A naive `hasattr` guard around that access would
have silently no-op'd the mod-presence check forever, always falling
through to "assume present." Fixed by deriving mod presence from real
evidence instead: does *any* entity in *any* index carry this
`source_mod`? Since the scanner only ever indexes enabled mods, a hit
there is proof the mod was both installed and enabled at scan time --
exactly the fact needed, recovered from data the registry already has
rather than data it doesn't.

Implemented the owner's explicit resilience rule ("pack can recommend
unavailable things, but loader must resolve them... skip or degrade only
affected guidance") in `resolve_knowledge_pack`: a `hull_archetypes` or
`retrofit_templates` entry whose `hull_id` doesn't resolve in the current
registry is dropped from the resolved view and recorded in
`unresolved_references` -- the whole pack is never rejected over one
stale reference.

14 new tests (`tests/test_knowledge_packs.py`), including one that loads
the real `hmi.example.json` file directly (not a synthetic copy) and
asserts on its real, verified content. Full suite: 181 tests passing.

**Live-verified end to end, and the result is itself informative**: the
real Hazard Mining Incorporated mod is present on disk in this
installation but genuinely *disabled* (absent from `mods/
enabled_mods.json`). Running the loader's full pipeline (load -> assess
freshness -> resolve references) against the real, full live scan
correctly produced `INCOMPATIBLE` (the target faction doesn't resolve
anywhere in this install's real data) and correctly listed both the
`hull_archetypes` and `retrofit_templates` entries as unresolved, rather
than crashing or fabricating a plausible-looking result for a mod that
isn't actually there. This exercises the exact real-world scenario the
freshness/resolution machinery exists for -- not a contrived one.

Deliberately not implemented in this slice: nothing yet *consumes* a
loaded pack's guidance anywhere in the pipeline. The natural consumer
(the Gap Recommendation Engine's retrofit/acquisition legs, per
`GAP_RECOMMENDATION_ENGINE.md` section 12's "Knowledge-pack doctrine
bias") doesn't exist yet -- wiring a pack's guidance into a recommendation
engine leg that isn't built would mean guessing at the interface. This
slice's job was making the pack format itself real, loadable, and
resilient; consuming it is real future work, correctly left open rather
than stubbed.

## Refit Assistant: `FIX_LEGALITY`, a first slice -- **Done**

Files: `generation/refit.py`, `core/heuristics.py` (5 new
`refit_cost_*`/`refit_max_changes` values), `api.py::run_fix_legality`,
`svg refit <variant_id>`.

`HULLMODS_CIVILIAN_AND_REFIT.md` sections 12-19 name 7 refit modes. Only
`FIX_LEGALITY` is implemented here, deliberately: the other 6
(`REDUCE_FLUX`/`IMPROVE_AI_FIT`/`IMPROVE_ROLE_MATCH`/`IMPROVE_LOGISTICS`/
`IMPROVE_SURVEY`/`IMPROVE_SALVAGE`/`BALANCED_IMPROVEMENT`) all mean
searching among several candidate *quality* improvements and picking the
one with the best gain-per-change-cost -- a real optimizer this project
doesn't have. `FIX_LEGALITY` doesn't need one: `validate_variant` already
gives an unambiguous mechanical target (LEGAL), not a heuristic one to
search toward, so a fixed, deterministic mapping from failure code to
minimal repair is enough.

Each real `LegalityFinding` failure code this project's own
`validate_variant` can produce maps to one dedicated fixer: unresolved
mount/weapon/hullmod/fighter references are removed; a `BUILT_IN_
WEAPON_OVERRIDDEN` explicit assignment is removed (letting the game
auto-fill the hull-fixed mount, exactly like the generator already does);
`WEAPON_TOO_LARGE`/`MOUNT_TYPE_MISMATCH` are repaired by replacing with
the cheapest documented-compatible weapon for that mount (reusing the
same `MOUNT_TYPE_COMPATIBILITY` matrix and eligibility logic
`generation/candidate.py` already uses for fresh generation), falling
back to removal only when no compatible weapon is known at all;
`LOGISTICS_HULLMOD_LIMIT_EXCEEDED`/`FIGHTER_BAY_CAPACITY_EXCEEDED` trim
only the excess (sorted by id for determinism), not everything;
`FLUX_VENTS`/`CAPACITORS_EXCEED_HULL_MAXIMUM` are clamped down to the
documented maximum, not zeroed; `OP_EXCEEDED` greedily removes the single
highest-OP unlocked item at a time, re-checking after each removal, so it
never removes more than necessary. Fixers run in dependency order
(reference cleanup before compatibility repair before category caps
before the OP budget, since earlier fixes already reduce OP incidentally)
and re-validate after each pass, capped by `refit_max_changes`
(`core/heuristics.py`, section 17's "No Silent Rebuild" rule: exceeding
it reports `rebuild_recommended` instead of continuing indefinitely or
quietly calling the full generator and passing the result off as a
"repair").

Locks (section 15) are honored structurally, not just by convention: a
locked mount/hullmod/fighter-wing id is never touched by any fixer, even
if that leaves the variant unable to reach LEGAL -- in that case the
result reports `rebuild_recommended=True` with the specific blocking
findings in `unresolved_failures`, matching section 15's "return a
clearly explained unsatisfied constraint rather than silently unlocking
it."

Deliberately unhandled: `HULLMOD_INCOMPATIBLE`. `adapters.vanilla.
INCOMPATIBLE_HULLMOD_PAIRS` has been empty by design since SVG-010 (no
documented vanilla pairwise hullmod exclusivity mechanic was ever found),
so this failure code never fires against real data, and a fixer for it
would be unverifiable against anything real.

11 new tests, all passing on the first run (`tests/test_refit.py`). Full
suite: 194 tests passing.

**Live-verified, including a real bug caught by the stress test before
release.** Corrupting the real `lasher_Standard` variant (swapping a real
energy weapon onto one of its ballistic mounts) produced exactly the
expected `MOUNT_TYPE_MISMATCH`, and `fix_legality` repaired it with
exactly one `WEAPON_REPLACED` change back to LEGAL. A broader stress test
-- 80 random real legal variants, each corrupted with one random weapon
substitution -- restored 66/80 to LEGAL and correctly declined to guess
on the other 8 rather than force a result: those 8 land in
`NOT_DETERMINABLE`, not `ILLEGAL`, because the corrupted mount happened to
be a real but undocumented type (`LAUNCH_BAY`/`DECORATIVE`/
`STATION_MODULE` -- the same "fighter-internal mount semantics are a
genuinely separate, undocumented area" finding from SVG-013, now
encountered again from a different angle). Investigating those 8 surfaced
a real reporting bug before this shipped: `RefitResult.unresolved_failures`
was built only from `assessment.failures`, so a `NOT_DETERMINABLE` result
(whose blocker lives in `.uncertainties`, since `NOT_DETERMINABLE` variants
have no `.failures` at all) silently reported zero unresolved reasons --
technically not wrong (`final_legality.uncertainties` still had the real
answer), but misleading for exactly the field meant to explain "why isn't
this legal." Fixed to include both `.failures` and `.uncertainties`; added
a dedicated regression test for it. Re-ran the same 80-variant stress
test after the fix: all 8 `NOT_DETERMINABLE` cases now correctly report
their real blocking finding. A larger, single-mechanism sweep -- injecting
a nonexistent weapon id into all 618 real legal variants with weapons in
the live install -- restored 618/618 (100%) to LEGAL, 0 exceptions.

## Adaptive Substitution scoring engine (Phase 8, second slice) -- **Done**

Files: `analysis/adaptive_substitution.py`, `core/heuristics.py` (11 new
`affinity_preference_*`/`substitution_weight_*` values).

`EQUIPMENT_ACCESS_AND_AUTOFIT.md` sections 9-12 describe the `ADAPTIVE`
retrofit mode's scoring: 8 named components (`role_match`/`range_match`/
`flux_match`/`damage_behavior_match`/`AI_friendliness`/`OP_efficiency`/
`affinity`/`confidence`), and `HEURISTICS.md` sections 12-13 (already
synced into this repo from the v0.5 pack) give concrete suggested
starting weights for them -- so unlike most heuristics added this
session, these weren't invented here at all, just transcribed verbatim
into `core/heuristics.py`'s versioned registry per Agent.md's rule.

Two of the 8 named components are deliberately not scored:

- **`AI_friendliness`** has no classifier anywhere in this project (no
  weapon field, no derived tag, nothing). Scoring it as 0 would read as
  "confidently unfriendly"; scoring it as 0.5 would read as "confidently
  neutral." Both are fabrications. Left out of the weighted average
  entirely, the same "absence of verified data is never treated as
  absence of effect" pattern already used throughout this project (the
  Hullmod Effect Engine's `unverified_hullmod_ids`, the Gap
  Recommendation Engine's `unaddressed_gaps`).
- **`confidence`** doesn't have a coherent meaning as an *input* --
  read literally it's "how reliable is this very score," and feeding a
  result's own reliability back into computing that result is circular.
  Computed instead as `SubstitutionScore.confidence`, an output: the
  fraction of the other 6 components that had real data for this
  specific pair. A candidate missing flux/damage-type data isn't scored
  0 on those axes; those axes are simply absent from
  `component_scores`, and `confidence` reflects that absence honestly.

The remaining 6 components all reuse already-tested classifiers rather
than inventing new inference: `role_match` (Jaccard overlap of
`classify_weapon`'s real `role_tags` between target and candidate) and
`affinity` (`classify_equipment_affinity`, mapped through `HEURISTICS.md`
section 12's own preference table) are the two genuinely new derivations;
`range_match`/`flux_match`/`op_efficiency` are straightforward normalized
differences on already-parsed numeric fields, and `damage_behavior_match`
is an exact `damage_type` comparison.

6 new tests. Full suite: 200 tests passing. Live-verified against the
real install: scored all 200 real weapons sharing `heavyblaster`'s real
mount type and size, ranked by `rank_substitution_candidates` -- the top
result (`phasebeam`) had a perfect range/damage/OP/affinity match, a
plausible outcome for a same-class energy weapon. Stress-tested scoring
across 60 real weapons against ~30 real same-class candidates each (1,800
total scoring calls spanning multiple real mods, not just core), 0
exceptions.

Deliberately not done in this slice: wiring the engine into anything.
`generation/refit.py::_fix_mount_compatibility` still picks the cheapest
compatible weapon, not the best-scoring one -- that selection strategy is
already tested and live-verified (the previous section's 618/618 sweep),
and swapping it for adaptive scoring is a real behavior change that
deserves its own opt-in path and its own verification pass, not a silent
substitution underneath already-shipped behavior. The engine exists,
tested and proven against real data, ready to be wired in as a deliberate
next step.

## Recommendation Explainability: "Why Not?" for the native leg -- **Done**

Files: `analysis/gap_recommendation.py` (`explain_native_candidate`,
`WhyNotExplanation`, `_rank_candidates_for_role` extracted as a shared
helper), `api.py::run_why_not`, `svg why-not <faction_id> <role>
<hull_id>`.

`GAP_RECOMMENDATION_ENGINE.md` section 13 originally marked Why-Not "not
implemented for v1," reasoning that native-only search has no real losing
candidates worth explaining beyond "ranked lower on this axis, which the
ranked list already shows." That was true only as long as the ranking
stayed an internal implementation detail inside
`recommend_native_solutions`, which computed the full real ranking every
time and then discarded everything past `gap_recommendation_count`.
Making that ranking queryable instead of throwaway is real, additive
work, not a re-derivation of something already visible -- so this phase
picked it up rather than leaving the original v1 note as a permanent
verdict.

Refactored the "score every known hull for one role" logic out of
`recommend_native_solutions` into a shared `_rank_candidates_for_role`
helper first, so `explain_native_candidate` answers from the *same* real
ranking the actual recommendations came from -- structurally unable to
disagree with them, rather than a second, parallel inference path that
could drift out of sync.

The "ranked lower" framing from the original v1 note turned out to
collapse three real, different situations a caller would want told apart:

- **Recommended** -- was inside the top N. Reports its real rank.
- **Ranked, but below the cutoff** -- has a real positive score that
  simply wasn't high enough. Reports the rank, the total candidate
  count, and the exact score gap to the last hull that *was*
  recommended -- not just "no," but "no, and by how much."
- **Zero real evidence** -- scores `0.0` on the role entirely, a
  materially different fact from "scored low" (no signal at all, not
  weak signal). Reported with its own distinct reason text.

An unresolved `hull_id` -- not a real, resolved known hull of this
faction -- is reported as `resolved=False`, never silently treated as "a
real hull that happens to score zero." Those are different claims about
different kinds of missing information (a name that doesn't exist here
at all, versus a real hull genuinely lacking the capability), and
conflating them would misrepresent which one is actually true.

4 new tests (`tests/test_gap_recommendation.py::WhyNotExplanationTests`).
Full suite: 204 tests passing.

Live-verified against real Pirates data (the same faction whose real
`CARRIER` gap validated Phase 10 originally): `why-not pirates
BATTLE_CARRIER atlas2` correctly reports "Recommended: ranked 1 of 2";
`why-not pirates BATTLE_CARRIER vanguard_pirates` (a real pirate hull
with no carrier-adjacent mounts at all) correctly reports "no real
evidence" rather than computing a misleading rank; `why-not pirates
CARRIER atlas2` correctly gives the same answer for the genuinely
unaddressed `CARRIER` gap, confirming the distinction holds even for the
faction's own best-scoring hull when the axis itself has zero coverage.
Stress-tested across every real faction's first 5 known hulls x all 5
capability roles (3,590 real calls) plus an explicit unresolved-hull-id
check per faction: 0 exceptions.

Not implemented: solution diversity (Pareto-style "best capability /
best practical / best native" framing from the original design) and
per-candidate confidence (today's `evidence_confidence` is per-gap, a
data-completeness figure, not a per-recommendation mechanical-certainty
one) -- both real, separate pieces of Phase 11 still open. Why-Not for
retrofit/acquisition candidates doesn't exist because those legs don't
(Phases 8/9's remaining wiring, not this phase's scope).

## Adaptive Substitution wired into the Refit Assistant -- **Done**

Files: `generation/refit.py` (`substitution_mode`/`requesting_faction_id`
params, `_FIXERS` -> `_build_fixers(...)` built per call, `_best_
compatible_weapon`), `api.py::run_fix_legality`, `svg refit
--substitution-mode adaptive --faction-id`.

Closes the same real gap from two directions at once: Phase 8's "the
substitution engine exists but isn't wired into anything" and Phase 9's
"not yet wired into ADAPTIVE substitution modes." In `adaptive` mode, a
mount-incompatible weapon is replaced with the real best role/range/flux/
damage/affinity match to the *original* weapon (via `analysis/
adaptive_substitution.py::rank_substitution_candidates`), preserving
fitting intent rather than just picking whatever is cheapest -- matching
`EQUIPMENT_ACCESS_AND_AUTOFIT.md` section 3's description of what
`ADAPTIVE` mode is supposed to do, using the scoring engine already built
and live-verified in the previous phase.

Backward compatibility was the main design constraint: `substitution_mode`
defaults to `"cheapest"`, byte-identical to every version of this module
that existed before today, so nothing that already depends on
`FIX_LEGALITY`'s tested selection behavior changes unless a caller
explicitly opts in. `_FIXERS` moved from a module-level constant to a
`_build_fixers(...)` function called once per `fix_legality` invocation,
since the mount-compatibility fixer now needs that call's
`substitution_mode`/`requesting_faction_id` bound in via
`functools.partial` -- every other fixer is completely unaffected by this
restructuring.

1 new test proving the two modes genuinely diverge in practice (a
cheap-but-poor-match candidate beats a pricier-but-better-match one only
under `cheapest`). Full suite: 205 tests passing -- critically, all 11
pre-existing refit tests passed completely unchanged, confirming the
default path really is untouched.

Live-verified against the real corrupted `lasher_Standard` (the same
mount-type-mismatch scenario used to first validate `FIX_LEGALITY`):
`cheapest` mode picked `SunriderAlliancePD`; `adaptive` mode picked a
genuinely different weapon, `mm_cryospoolpd` -- both reached LEGAL, but
via a materially different choice, confirming the engine is actually
being consulted, not silently falling back. Re-ran the same 74-real-
variant corruption stress test from the original `FIX_LEGALITY`
verification in adaptive mode: identical 66/74 legal rate (expected --
the 8 unfixable cases are `NOT_DETERMINABLE`, a data-completeness
problem unrelated to which substitution strategy is used), 0 exceptions.

## Civilian OP-efficiency aggregated into scoring -- **Done**

Files: `scoring/candidate_score.py` (`_civilian_efficiency_component`),
`core/heuristics.py` (`weight_civilian_efficiency`,
`civilian_efficiency_reference`).

Closed the exact gap Phase 4's own note named ("the per-effect
efficiency ratio is not yet aggregated into `QualityAssessment`'s
score"): `AppliedLogisticsEffect.efficiency` (gain per OP spent, already
computed and live-verified against real `phantom_Elite` data) is now
averaged across a variant's applied LOGISTICS effects and folded into the
weighted-average final score as a sixth component, exactly like
`flux_sustainability`/`faction_doctrine_match` before it: silently absent
(no component, no explanation line) rather than scored 0 when not
applicable, so the vast majority of combat variants -- which never carry
logistics hullmods at all -- see no change and no added noise.

`civilian_efficiency_reference` (the gain-per-OP value that maps to a
full 100 score) is a first-pass heuristic explicitly grounded in real
numbers already computed this session (`auxiliary_fuel_tanks` on
`phantom`, `expanded_cargo_holds` on a frigate test case, both 6.0), not
an idealized target -- there's no documented "correct" efficiency to
calibrate against, the same honest status `doctrine_match`'s weights
already carry.

`baseline_0.1`'s legacy 3-component branch is untouched by construction
(civilian scoring only enters the `baseline_0.2`+ code path); the golden
regression test confirms this unchanged. Deliberately not extended: the
existing "no weapons -> flat 0.0" early-return path, which some real
civilian ships with zero weapon mounts would hit, doesn't consider
civilian efficiency at all. Fixing that is a real, separate behavior
change to already-tested logic, not a natural part of "aggregate the
existing metric" -- flagged as a known scope boundary, not silently
expanded past what was asked.

4 new tests, including an exact-math check (gain 30 / OP 5 = 6.0
efficiency = exactly the reference value = a perfect 100.0 score) and a
dedicated `baseline_0.1`-unaffected check. Full suite: 208 tests passing.

## `doctrine_match` regression anchor -- **Done**

File: `tests/test_doctrine.py`
(`test_doctrine_match_baseline_0_2_partial_mismatch_is_pinned`).

Closed the specific gap Phase 16's own row named: existing doctrine
tests only covered the trivial ends of `doctrine_match`'s range (a
full 1.0 hullmod-overlap match, and the `None`-evidence early return),
never a partial-mismatch case that actually exercises `baseline_0.2`'s
weighted arithmetic across a real evidence spread (5 examined variants,
two repeated hullmods at different frequencies, a candidate matching
only one of them, and a weapon range mismatch against the doctrine's
average). The new test pins that scenario's score to exactly `0.562`,
hand-derived and then confirmed against the real, live computation --
so a future change to the weighting formula (intentional or not) will
be caught, the same protection the golden `baseline_0.1` scoring test
already gives the legacy branch.

This is deliberately framed as regression *stability*, not
*calibration*, matching the honest status already established for
`civilian_efficiency_reference` above: there is no labeled "this
variant doctrine-matches this faction well" dataset to calibrate
against, and building one without real player/community ground truth
would mean fabricating a standard this project has no way to verify.
Phase 16's row is updated to reflect this narrower, achievable claim
rather than closing the row outright -- true calibration remains a
genuinely open gap, not something this test pretends to solve.

No production code changed. Full suite: 209 tests passing.

## Refit Assistant: 4 quality-improvement modes -- **Done (4 of 6)**

Files: `generation/refit.py` (`improve_quality`, `QualityRefitResult`,
`UNIMPLEMENTED_QUALITY_MODES`), `core/heuristics.py`
(`refit_min_quality_gain`), `api.py` (`run_improve_quality`),
`cli/main.py` (`svg refit --mode ... --profile ...`).

Closed the largest remaining gap this session: root ROADMAP.md Phase 9
previously implemented only `FIX_LEGALITY`, the one mode with an
unambiguous mechanical target (`validate_variant` says LEGAL or it
doesn't). The other 6 named modes (HULLMODS_CIVILIAN_AND_REFIT.md section
13) don't have that -- they need a real quality target to search toward,
which is exactly what section 14 describes: greedily optimize
`quality_gain / change_cost` under a maximum-change budget.

Design decision: rather than invent a new scoring mechanism for refit,
`improve_quality` reuses `scoring/candidate_score.py::score_candidate`'s
existing, already-tested components directly as each mode's target
metric --

- `BALANCED_IMPROVEMENT` -> `final_score` (the full weighted score;
  literally what section 14 describes as the general algorithm)
- `REDUCE_FLUX` -> `flux_sustainability`, with a hard guard: a candidate
  is rejected outright if it would regress `role_match` or
  `range_coherence`, directly implementing section 13's "preserving
  role/range" wording rather than trusting the weighted average alone to
  respect it
- `IMPROVE_ROLE_MATCH` -> `role_match`
- `IMPROVE_LOGISTICS` -> `civilian_efficiency`, restricted to hulls with
  a documented CIVILIAN hint (`classify_civilian_role`)

Every candidate single-change is independently re-validated
`LEGAL` (`validate_variant`) before it is even scored -- quality search
can never trade away legality for a better number, the same hard
boundary `FIX_LEGALITY`'s fixers already respect and Agent.md's own rule
requires project-wide. Candidate generation mirrors `FIX_LEGALITY`'s own
mount-compatibility fixer for the 3 weapon-substitution modes (every
mount-eligible weapon on every unlocked, non-built-in mount) and reuses
`analysis/civilian.py`'s verified `LOGISTICS_HULLMOD_EFFECTS` table for
`IMPROVE_LOGISTICS` (adding one not-yet-installed, verified logistics
hullmod at a time) -- the logistics-hullmod cap and OP budget are never
re-implemented here, just left to the same `validate_variant` check every
other candidate goes through.

A new heuristic, `refit_min_quality_gain` (baseline_0.2, 0.5 score
points), stops the greedy search from accepting a change whose gain is
indistinguishable from rounding noise.

A real design bug was caught before shipping, not after: `IMPROVE_
LOGISTICS`'s starting `civilian_efficiency` is `None` (a real "not yet
applicable" absence, per `_civilian_efficiency_component`'s own
convention) on precisely the case this mode exists to help -- a civilian
hull with no logistics hullmod installed yet. An initial draft treated
any `None` starting metric as "nothing to improve" and returned
immediately, which would have made `IMPROVE_LOGISTICS` a permanent no-op
for its single most common real use case. Fixed by treating that specific
absence as a genuine `0.0` baseline to search upward from, for
`IMPROVE_LOGISTICS` only -- the other 3 modes still correctly treat a
`None` metric as "this can't be evaluated for this variant at all,"
which remains a real hard stop for them (e.g. `REDUCE_FLUX` on a hull
with undocumented flux data).

`IMPROVE_AI_FIT`, `IMPROVE_SURVEY`, and `IMPROVE_SALVAGE` remain
unimplemented, and `UNIMPLEMENTED_QUALITY_MODES` states why each one is
a genuine evidentiary gap rather than an oversight: no AI-friendliness
classifier exists anywhere in this project (the same reason it was
excluded from Adaptive Substitution scoring, Phase 8), and
`classify_civilian_role`'s real, scanned hull hints -- verified earlier
this session against all 211 real core hulls -- never produce SURVEY or
SALVAGE tags at all, so there is no real per-ship evidence for either
mode to search toward. Calling `improve_quality` with any of these three
(or with `FIX_LEGALITY`, which has its own function) raises a `ValueError`
naming the specific reason, rather than silently no-opping.

8 new tests in `tests/test_refit.py::ImproveQualityTests`, covering each
implemented mode's positive path, lock respect, illegal-candidate
rejection, the non-civilian-hull `IMPROVE_LOGISTICS` no-op, and the
unimplemented-mode `ValueError`. Live-verified against the real 148-mod
install: `lasher_Standard` under `REDUCE_FLUX` correctly reported "not
evaluated" (this hull's real flux data is not fully documented, the same
honest boundary `score_candidate` already has), while `BALANCED_
IMPROVEMENT` and `IMPROVE_ROLE_MATCH` both ran cleanly to a real,
unforced 0-change result (no legal single-mount swap actually improved
either metric for this specific real loadout); `phantom_Elite` under
`IMPROVE_LOGISTICS` likewise ran cleanly to a real 0-change result. A
full-install `BALANCED_IMPROVEMENT` run took roughly 15s wall time --
acceptable for a one-off CLI command, not a stress-sensitive path.

Inherited, not introduced: `IMPROVE_LOGISTICS`/`BALANCED_IMPROVEMENT`
still can't evaluate `civilian_efficiency` at all for a genuinely
unarmed hull, because `score_candidate`'s "no installed weapons" branch
returns early before reaching the extended-scoring block -- this was
already identified and explicitly deferred as a separate, real behavior
change during the civilian-efficiency-scoring work earlier this session
(see that section above), not something newly discovered or newly
punted here.

Full suite: 216 tests passing.

## Advanced mode: scoring weight overrides -- **Done**

Files: `profiles/advanced.py` (`_scoring_weight_overrides`,
`AdvancedGenerationRequest.scoring_weight_overrides`),
`scoring/candidate_score.py::score_candidate` (`weight_overrides`
parameter), `api.py::run_generate`, `cli/main.py` (report serialization).

Closed docs/IMPLEMENTATION_STATUS.md row 7's ("Modes") named gap:
"detailed scoring overrides." The scoring formula itself
(`score_candidate`) already exposes 6 named, independently-weighted
components (`range_coherence`/`op_efficiency`/`role_match`/`flux_
sustainability`/`faction_doctrine_match`/`civilian_efficiency`), each
with its own `weight_*` heuristic in `baseline_0.2` -- but until now a
user had no way to say "for this generation run, I care about flux
survivability more than range coherence" without editing the shared,
versioned registry itself, which would affect every other command and
every other user of that heuristic_set.

The design constraint driving this feature is Agent.md's own hard rule:
"All tunable heuristics live in a named, versioned registry... new or
changed heuristic values need a rationale, docs, regression coverage,
and (if released) a new registry identifier." A free-form per-request
override that could set *any* heuristic to *any* value would violate
that rule's spirit even if each individual request stayed logged --
thresholds and targets are calibration decisions this project has
already reasoned about (see e.g. `civilian_efficiency_reference`'s own
documented, if first-pass, justification), not something a single
generation request should silently redefine. The resolution: restrict
the override surface to exactly the 6 already-registered, already-
documented `weight_*` keys -- these are relative-importance dials by
design (the formula is a weighted average; any positive weights are
"valid" in the sense that none of them can produce nonsensical output),
not calibration constants. `profiles/advanced.py::_SCORING_WEIGHT_KEYS`
enforces this allow-list; naming any other key (a threshold, a target,
a completely made-up key) is rejected with a clear error listing exactly
which keys are supported, matching the existing Advanced-request pattern
for weapon restrictions ("reject anything unsupported rather than
ignoring it").

`score_candidate` itself stays a thin, trusting function here -- it
accepts a raw `Mapping[str, float] | None` and merges it into the
resolved heuristic values, the same way it already trusts its
`heuristic_set` string argument. All the actual governance (the
allow-list, the non-negative-value check) lives once, in
`profiles/advanced.py`, the only real producer of this mapping today.
`baseline_0.1`'s legacy 3-component branch is untouched by construction
(it returns before `weight_overrides` is ever consulted).

Auditability: an applied override is recorded as a new explanation line
("Scoring weight override(s) applied: ...") on every affected
`QualityAssessment`, and `run_generate`'s CLI report now serializes
`advanced_request.scoring_weight_overrides` alongside the other Advanced-
request fields -- satisfying Agent.md's "report the exact heuristic_set
and resolved values" rule the same way `heuristic_set` itself already is.

6 new tests: 4 in `tests/test_advanced.py` (loads valid overrides,
defaults to `None` when absent, rejects an unsupported key, rejects a
negative value) and 2 in `tests/test_scoring.py`, including an exact-math
regression: with the test fixture's default weights, `LINE_ARTILLERY`
scores 89.3; overriding `weight_op_efficiency` to 10.0 (making the
fixture's 0.0 op_efficiency component dominate) drops it to exactly 52.6
-- both values hand-derived and then confirmed against the real
computation, on the first run. Live-verified against the real 148-mod
install: `svg generate lasher --mode advanced --advanced-config <file>`
with `{"scoring_weight_overrides": {"weight_op_efficiency": 5.0}}`
produced a real, LEGAL candidate set whose top candidate's `quality.
explanation` correctly named the applied override and whose `final_score`
(4.5, dominated by a real 0.0 `op_efficiency` component) was visibly
different from an unoverridden run -- confirming the override reaches
real scoring end-to-end, not just the unit-test fixtures. The canonical
`docs/advanced-request.example.json` template was updated to demonstrate
the new field.

Deliberately not attempted: an interactive guided flow (the other half
of docs/IMPLEMENTATION_STATUS.md row 7's named gap). That specifically
borders on GUI scope -- a multi-step, stateful prompt sequence is a UI
concern Agent.md's own rule reserves for after the readiness gate
(root ROADMAP.md Phase 17), not something to build piecemeal into the
CLI ahead of it.

Full suite: 222 tests passing.

## Gap Recommendation Engine: retrofit and acquisition legs -- **Done**

File: `analysis/gap_recommendation.py` (`recommend_retrofit_solutions`,
`recommend_acquisition_solutions`, `recommend_gap_solutions`,
`RetrofitRecommendation`, `AcquisitionRecommendation`).
`analysis/equipment_affinity.py` (`entity_kind="hulls"`).

`GAP_RECOMMENDATION_ENGINE.md` sections 5 and 7 were marked "not
implemented -- structurally requires Phases 8 and 9" back when this
project's own status audit was written. Both landed earlier this
session, so this closed the two largest remaining named gaps in Phase
10.

**The retrofit leg required correcting a wrong assumption before any
code was written.** The natural first instinct -- "find a WEAK/GAP hull
and use the Refit Assistant to make it STRONG" -- doesn't work, because
`classify_hull`'s 5 capability axes (`analysis/classification.py`) are
purely structural: fraction of LARGE mounts, fraction of MISSILE mounts,
presence of fighter bays. No amount of refitting changes how many LARGE
mounts a hull physically has. Re-reading `FACTION_KNOWLEDGE_PACKS.md`
section 14 ("search native retrofit solutions," listed as step 2, after
native search and before acquisition) clarified the real, intended
meaning: among the hulls the native leg *already* found structurally
capable, is a *specific, real, currently-fitted variant* of that hull
actually realizing that potential, or is it sitting on unused headroom a
refit could close? This is honest, bounded, and reuses machinery that
already exists twice over: `_rank_candidates_for_role` (already shared
with `explain_native_candidate`) supplies the candidate hull pool, and
`generation/refit.py::improve_quality`'s `IMPROVE_ROLE_MATCH` mode
supplies the real, independently-validated quality delta. No new
inference mechanism was invented to make this work.

Doing this required one small piece of new plumbing: `_ROLE_TO_PROFILE`,
an explicit, documented, 5-entry mapping from `classify_hull`'s
capability-axis vocabulary (`CARRIER`/`BATTLE_CARRIER`/`MISSILE_SUPPORT`/
`LINE_ARTILLERY`/`LINE_BRAWLER`) to `profiles/catalog.py`'s profile-id
vocabulary (`CARRIER_SUPPORT`/`LINE_ARTILLERY`/`LINE_BRAWLER`/...) --
these two vocabularies existed independently and were never unified
before. `BATTLE_CARRIER` has no dedicated profile of its own; it maps to
`CARRIER_SUPPORT`, same as `CARRIER`, with the reasoning stated directly
in a code comment rather than left implicit.

For each gap, the search examines every real variant of each of the top
`gap_recommendation_count` structurally-capable hulls (not just one),
picks the variant with the single largest genuine `IMPROVE_ROLE_MATCH`
gain, and reports it -- a hull with no real variant, or whose real
variant(s) already realize their structural potential (gain below
`refit_min_quality_gain`), is simply absent from the result, never
padded with a fabricated recommendation.

**A real, previously-unknown limitation surfaced during live
verification, not hidden after the fact.** Live-testing against real
Pirates faction data showed 0 retrofit recommendations across all 3 of
its detected gaps, despite Pirates having real, fully-armed candidate
variants (e.g. `atlas2_Standard`, 14 mounted weapons). Investigating
*why* (rather than assuming the feature was broken or silently
shipping a suspiciously-empty result) traced to `score_candidate`'s own
`role_match` formula: `role_score = 100.0 if all(weapon range check)
else 70.0` is an all-or-nothing step function across every mounted
weapon. `improve_quality`'s greedy search only accepts a candidate
change with *strictly positive, immediate* gain -- but swapping just one
of several range-violating weapons produces zero measurable `role_match`
gain until the very last one is fixed, so the greedy search can never
find its way there for real multi-weapon combat ships. This is not a bug
in what was built here; it's an honest, correct consequence of an
existing formula (`score_candidate`, Phase 13) meeting an existing
search strategy (`improve_quality`, Phase 9) in a combination neither
was designed to solve together. Documented plainly rather than routed
around under time pressure, since fixing it would mean redesigning
`improve_quality`'s single-step search into a multi-step or
simultaneous-mount search -- a real, separate piece of future work,
not a quick patch, and `generation/refit.py` was mid-edit by concurrent
work at the time this was found besides.

The acquisition leg was comparatively simple once
`classify_equipment_affinity` was confirmed to generalize cleanly: a
hull's real ownership evidence (`Faction.known_hulls`) has exactly the
same shape as a weapon's (`known_weapons`), so `entity_kind="hulls"`
needed only a one-line addition to `_KNOWN_ID_SELECTORS` -- no new
classifier, no new mechanism. Ranking non-native hulls by
`capability_score * affinity_preference_<tier>` reuses the exact
`baseline_0.2` preference table (`affinity_preference_native/common/
unaligned/foreign`) Adaptive Substitution scoring (Phase 8) already
uses, directly implementing FACTION_KNOWLEDGE_PACKS.md section 9's
"foreign acquisitions normally need a clear capability advantage"
without inventing a new doctrine-strictness (LOOSE/BALANCED/STRICT)
mechanism that section 9 also names but this pass doesn't attempt.

`GapRecommendationResult` gained `retrofit_recommendations`,
`acquisition_recommendations`, and `fully_unaddressed_gaps` as new
fields with backward-compatible defaults -- `recommend_native_solutions`
itself, and every existing test calling it directly, are untouched
by construction. `unaddressed_gaps` keeps its original, narrower meaning
("no native solution") since that's real, distinct information in its
own right ("this faction's own hulls can't cover this at all," even if
something foreign could); `fully_unaddressed_gaps` is new and implements
section 15's own stated "full maturity" definition -- no solution across
all three legs -- properly, rather than redefining the existing field
underneath existing callers.

Live-verified against real Pirates faction data (`svg recommend pirates
--source-mod core`): 3 real capability gaps (BATTLE_CARRIER, CARRIER,
LINE_ARTILLERY), 1 without a native solution (CARRIER -- Pirates
genuinely have no native carrier hulls, matching prior Phase 10
verification), 0 gaps left fully unaddressed. Acquisition surfaced real
hulls from real installed mods with correct affinity classifications and
preference weights: `armaa_bassline`/`armaa_broadsword`/`armaa_caymon`
(COMMON, weight 0.75) for CARRIER; `SunriderACVengine`/`SunriderACVleft`/
`SunriderACVright` (UNALIGNED, weight 0.70) for BATTLE_CARRIER;
`IndEvo_artilleryStation_*` (UNALIGNED, weight 0.70) for LINE_ARTILLERY.

10 new tests across `tests/test_equipment_affinity.py` (1) and
`tests/test_gap_recommendation.py` (9), including a hand-computed
retrofit scenario (role_match 70.0 -> 100.0 via exactly 1 change) and an
integration test proving `fully_unaddressed_gaps` correctly excludes a
gap covered only by acquisition while `unaddressed_gaps` still correctly
includes it.

Not attempted in this pass, and explicitly left for later: extending
`explain_native_candidate`/Why-Not to retrofit/acquisition candidates
(Phase 11) -- real, buildable follow-on now that these legs exist, kept
separate to keep this change reviewable on its own.

Full suite: 247 tests passing (this change plus two others landed
concurrently -- see below).

## Hullmod Effect Engine: DEFENSE category -- **Done**

Files: `adapters/vanilla/__init__.py` (`DEFENSE_HULLMOD_EFFECTS`),
`adapters/__init__.py` (`defense_hullmod_effects`),
`analysis/combat_stats.py` (new module), `analysis/variant.py`
(`defense_stats` field).

Closed a real, named gap in Phase 4's own status row: LOGISTICS was the
only hullmod-effect category modeled, and all 10 of its real hullmods
were already fully researched (6 modeled, 4 correctly ruled out of
scope) -- there was nothing left to add there. This pass researched and
modeled a second category, DEFENSE (armor rating / hull HP), following
`compute_derived_civilian_stats`'s exact established discipline: only
verified, cross-checked effects are modeled; absence of a verified entry
is never treated as absence of effect.

4 real hullmods modeled -- `heavyarmor` (+150/300/400/500 armor rating by
hull size), `armoredweapons` (+10% armor rating), `reinforcedhull` (+40%
hull HP), `blast_doors` (+20% hull HP) -- each cross-checked two ways:
against the Starsector wiki (since, like LOGISTICS hullmods, these CSV
rows carry only an unfilled `%s` description template, not the real
number), and against the live install's own parsed `Hullmod.op_cost_by_
hull_size`, which matched exactly in every case. Base armor rating/hull
HP are read from `Hull.raw`'s CSV columns (not yet promoted to typed
`Hull` fields -- a real, separate future decision, not made here), with
a one-level fallback to a skin's base hull for `.skin`-derived hulls
(verified against real `afflictor_d_pirates` -> `afflictor` data).

The one real design question -- what happens when two independently-
verified hullmods both target the same stat (`reinforcedhull` and
`blast_doors` both modify hull HP) -- was resolved the same way
`compute_derived_civilian_stats` already resolves the analogous civilian
case: vanilla's real stacking rule for two percent-hull-HP hullmods
together (additive? multiplicative?) is not documented anywhere
verifiable, so no combined value is fabricated. `effective_hull_hp`
becomes `None` with an explanatory `stacking_notes` entry when this
happens; each hullmod's individual contribution against the true base
value remains visible in `applied_effects` regardless.

Surfaced via `svg analyze-variant`'s new `defense_stats` field (`analysis/
variant.py`), not left as inert, unread data. Stress-tested across all
5,526 real variants in the live install, 0 exceptions; the same-stat
stacking path was real (26 variants) and handled correctly, not just a
theoretical edge case.

Deliberately not wired into `scoring/candidate_score.py` or
`generation/refit.py` in this pass -- reserved as a separate integration
step (armor/HP differentiating candidates for the same hull is a
legitimate, real target for a future survivability scoring dimension,
reopening a door Phase 13 closed for *hull-constant* stats specifically,
but that's new scope for a later pass, not assumed here).

15 new tests (`tests/test_combat_stats.py`, plus one end-to-end wiring
test in `tests/test_variant_analysis.py`).

## Refit Assistant: EXACT and STARSECTOR_STYLE substitution modes -- **Done**

File: `generation/refit.py` (`_exact_compatible_weapon`,
`_template_compatible_weapon`, `_fix_mount_compatibility`'s substitution
branching), `cli/main.py` (`--substitution-mode` choices).

Closed the remaining half of Phase 9's substitution-mode gap: `cheapest`
and `adaptive` already existed; `EXACT` and `STARSECTOR_STYLE` were the
two still missing, per `EQUIPMENT_ACCESS_AND_AUTOFIT.md` section 9's own
named modes. Their real definitions were read from that document before
any code was written, per this project's "never infer undocumented
behavior" rule -- neither was guessed at from the name alone:

- `EXACT`: "Reproduce specified IDs exactly. No substitution. Missing
  items are reported." Implemented as a selector that always returns
  nothing -- the incompatible weapon is removed and reported missing,
  even when a real compatible substitute exists in the registry, exactly
  matching the spec's own wording.
- `STARSECTOR_STYLE`: "Preserve the target template and choose close
  available substitutes. Keep slot/category/group intent rather than
  redesigning the build." Implemented as a lighter mechanism than
  `ADAPTIVE`'s full weighted score: rank mount-eligible weapons by
  `classify_weapon` role-tag overlap with the original (its documented
  category, e.g. KINETIC_PRESSURE/PD/ARTILLERY), then exact range-band
  match, then closest ordnance-point cost -- a "close" substitute, not
  necessarily the cheapest one. No new heuristic was added for this: the
  tie-break is a plain lexicographic ordering over already-tested
  classification fields, and inventing a weight to combine "tag overlap"
  and "OP distance" into one number would need calibration this project
  has no basis for -- exactly the kind of fabricated tunable Agent.md's
  heuristic-registry rule exists to prevent.

`--substitution-mode` now accepts all 4 real modes:
`cheapest`/`exact`/`starsector_style`/`adaptive`. Live-verified against a
real `wasp_Interceptor` mount-type-mismatch case (`WS 002`, originally
`fragbomb`): all 4 modes produced genuinely distinct, individually
correct selections (cheapest OP pick, reported-missing removal, closest
category/OP match, and the full weighted match respectively), confirming
the modes are behaviorally real, not four names for the same logic.

2 new tests in `tests/test_refit.py`.

Full suite after all three concurrent changes (this section, the two
above): 247 tests passing, 0 failures.

## Recommendation Explainability: retrofit and acquisition Why-Not -- **Done**

File: `analysis/gap_recommendation.py` (`explain_retrofit_candidate`,
`explain_acquisition_candidate`, `explain_candidate`,
`CombinedWhyNotExplanation`).

Direct follow-on to the retrofit/acquisition legs landing (see the
section above): `explain_native_candidate` only ever answered "why
wasn't this hull recommended *natively*?" -- with two more real legs now
existing, a caller asking "why wasn't X recommended?" was getting an
incomplete, misleadingly narrow answer. Closed that.

`explain_retrofit_candidate` mirrors `recommend_retrofit_solutions`'s own
real logic exactly, for one (role, hull_id) pair: a hull outside the
native leg's own top-ranked shortlist was never even examined by
retrofit search (structurally can't be, since retrofit only operates on
hulls the native leg already found structurally capable) -- reported as
"not considered," distinct from a hull that *was* considered but had no
real variant, or had real variant(s) that already realize their own
potential (gain below `refit_min_quality_gain`). Unlike the native leg,
retrofit doesn't apply a further top-N cutoff beyond the native
shortlist itself, so there's no "ranked but below cutoff" case here --
every hull with a genuine positive-gain retrofit is included, and this
explanation says so honestly rather than forcing artificial parity with
the native leg's own richer 3-way distinction.

`explain_acquisition_candidate` mirrors `recommend_acquisition_solutions`
the same way: an unresolved hull id, an already-native hull (acquisition
structurally doesn't apply to it -- that's what native/retrofit are for),
a real hull with zero capability evidence for the role, and the full
ranked/cutoff distinction the native leg already has, now computed over
the non-native candidate pool with real affinity and
`affinity_preference_<tier>` values instead of raw capability_score.

`explain_candidate` combines all three into one `CombinedWhyNotExplanation`
-- a real caller asking "why wasn't this recommended?" wants the whole
picture in one call, not three separate lookups that could theoretically
disagree about which leg's ranking is authoritative for a given hull.
`api.py::run_why_not`'s return type changed accordingly; `svg why-not`'s
console output now prints all 3 legs' reasons plus the report path.
`explain_native_candidate` itself is completely unchanged, and every
existing test that calls it directly still passes unmodified.

Live-verified against real Pirates faction data, cross-checked for
consistency against `svg recommend pirates`'s own output for the same
faction (not just checked in isolation):

- `svg why-not pirates CARRIER armaa_bassline` -> native: "not a resolved
  known hull of this faction" (correct -- Pirates don't know it
  natively); retrofit: "not among the native leg's top structurally-
  capable candidates" (correct -- retrofit never examines non-shortlist
  hulls); acquisition: "ranked 1 of 826... common affinity" (correct --
  matches `armaa_bassline`'s real rank-1 CARRIER acquisition slot from
  `svg recommend`'s own output).
- `svg why-not pirates LINE_ARTILLERY atlas2` -> native: "ranked 1 of 2"
  (correct, matches the native recommendation list); retrofit: "2 real
  variant(s), but none improve role_match by at least 0.50" (correct --
  a live, real instance of the multi-weapon `role_match` all-or-nothing
  limitation already documented alongside the retrofit leg itself, not a
  new problem); acquisition: "already known natively... doesn't apply"
  (correct).

9 new tests in `tests/test_gap_recommendation.py` (`RetrofitWhyNot
ExplanationTests`, `AcquisitionWhyNotExplanationTests`,
`CombinedWhyNotExplanationTests`).

Full suite: 255 tests passing.

## Calibration scenario-profile resolution (2026-08-23)

`tools/resolve_scenario_calibration.py` now consumes either the initial
record-oriented calibration guide or the richer ship/scenario-profile form.
For every unambiguous locally scanned hull/scenario, it persists the source
expectation separately from mechanically generated legal alternatives:

- `SOURCE_EXPLICIT` retains raw source wording, explicitly named equipment,
  scenario basis, and review status without rewriting any expectation;
- `INFERRED_SCENARIO_OPTION` contains only candidates produced through the
  normal local legality-first generator, with an explicit unrestricted access
  policy that does not claim faction affinity;
- comparison records show recognized source IDs, inferred overlap, and source
  equipment not selected by the generated alternatives;
- unresolved names and ambiguous/unresolved hulls are reported rather than
  guessed.

Text scanning is intentionally conservative: display names shorter than three
characters are never inferred from prose. This avoids a source-text false
positive found during the first local pass. The resolver writes only to a
chosen local output path; its scan-derived report is not repository content.

## Composite structural profiles and shared evidence class (2026-08-23)

The Complex Hull Acceptance Matrix now has a bounded formal backend model:
`CompositeHullProfile` and per-slot `ModuleProfile`. It resolves declared
parent-slot to child-variant references only when locally unambiguous, records
repeated and asymmetric mappings as structure, and preserves unresolved parent,
child variant, and child hull states. Its fixed `STRUCTURAL_ONLY` analysis state
forbids parent aggregation of module mounts, systems, shields, survivability,
legality, or scoring. The local complex-hull audit serializes these profiles so
the boundary is reviewable.

`core.evidence.EvidenceClass` now provides the shared origin vocabulary for
direct data, source code, local config, adapter models, guidance, reviewer
expectations, mechanics inference, unknown, and conflict. `EvidenceRecord`
now carries that class; local Java hullmod extraction is the first migrated
producer (`LOCAL_SOURCE_CODE`). Other report producers retain their current
provenance until migrated deliberately rather than receiving guessed classes.

Calibration labels now have an explicit expectation kind: build, equipment,
faction, scenario, or negative. Negative labels treat their expected values as
a forbidden set, so a reviewer can encode a strong “do not normally recommend
this path” regression without requiring an exact substitute or turning an
opinion into a rules-engine constraint.

## GUI scan workflow and repeatable verification (2026-08-23)

The desktop Settings workspace now makes scan state visible with an
indeterminate progress dialog and compact local scan/report summary. Its
`Discard Results` action is intentionally not mislabeled as process
cancellation: the read-only worker completes, then the session declines to
adopt its outcome. `tools/verify_gui.ps1` batches syntax compilation, focused
GUI backend/canvas/presentation/session tests, and an offscreen smoke launch.
This preserves the GUI's backend-only rules boundary while making first-run
scan behavior, errors, and report availability clearer.

The Build Inspector also now renders a backend-supplied manual-fit summary
(legality plus weapon OP used/remaining) after a slot change. The GUI does not
recalculate these values. `tools/verify_project.ps1` is the single local batch
entry point for the full regression suite followed by GUI syntax/bridge/canvas/
presentation/session checks and an offscreen smoke launch.

## Evidence-class migration phase (2026-08-23)

The shared `EvidenceClass` now propagates through every major inference and
recommendation report: mechanical/build archetypes, capability evidence and
gaps, and Native/Retrofit/Acquisition recommendations. Deterministic derived
facts are explicitly `INFERRED_MECHANICS`; local Java hullmod extraction stays
`LOCAL_SOURCE_CODE`. This is provenance classification only: it cannot change
legality, score, confidence, or an underlying source fact.

## GUI functional phase completion (2026-08-23)

Settings persists fitting preferences; explicit availability and Strict Faction
slot filtering are backend supplied; selected weapons receive a logical
on-canvas marker at their parsed mount; and generation receives the selected
faction. Exact weapon-art placement and inline callout combo boxes remain
deferred because normalized source data does not yet expose reliable weapon
sprite/origin metadata. These limitations are visible rather than replaced by
per-ship UI guesses.

## Scenario-objective build phase (2026-08-23)

Every inferred `Hull + BuildArchetype` path now records explicit scenario
objectives and their support state. Existing optimizer behavior is reused only
for objectives grounded in current normalized signals: line holding, screening,
long-range pressure, missile/carrier projection, and breakthrough. Objectives
such as anti-armor and anti-frigate are carried as `UNSUPPORTED` rather than
being mistaken for equipment-selection rules. This makes scenario distinctions
auditable and creates a stable extension point without fabricating combat
mechanics.

## Product rename: VoidSmith (2026-08-23)

The user-facing product name is now **VoidSmith**. Packaging exposes
`voidsmith` and `voidsmith-gui`; `svg` and `svg-gui` remain compatibility
aliases. The desktop application, generated compatibility-mod metadata, and
Windows executable build name are aligned to VoidSmith. The internal package
namespace remains unchanged to avoid breaking imports and existing scripts.
