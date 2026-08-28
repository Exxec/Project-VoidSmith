# VoidSmith User Guide

## What VoidSmith does

VoidSmith analyzes locally installed Starsector core/mod data and produces
explainable ship fits, refit suggestions, and faction capability reports. It is
an offline, deterministic assistant, not a combat simulator. It reads source
data only; generated output is written below your selected output folder.

### Support status

| Area | Status | What that means now |
| --- | --- | --- |
| Scanning and normalized data | Supported | Core/enabled mods, plus optional extra mods, are scanned without changing sources. |
| Normal ship legality and fitting | Supported | Mounts, OP, bays, built-ins, vents/caps, and documented references are checked. |
| Build generation/export | Supported | Bounded deterministic legal candidates and compatibility-mod export. |
| Refit | Supported/partial | Minimal legality repair and several quality modes; unsupported quality modes are rejected. |
| Faction capability and Why-Not | Supported | Native, retrofit, and acquisition legs, score/confidence, and explanation paths. |
| Scripts and custom mechanics | Partial | Static metadata and local readable Java can be analyzed; unknown remainder stays unknown. |
| Modules, stations, fighter-like hulls | Partial | Structure is recognized; aggregate combat behavior is not modeled. |
| AI/player behavior | Partial | Static suitability signals/evidence can be shown; runtime AI is never guessed. |
| Warfare posture and entity labels | Experimental | Advisory scored profiles; they do not yet change recommendation ranking. |

## Scanning your installation

In the GUI choose **Settings / Export**, select the installation and output
folder, then use **Scan Installed Data**. The scan is read-only. Reports,
caches, and logs remain under the output folder. The GUI can also receive a mod
folder or archive by drag-and-drop; it is treated as an extra source and is not
installed or modified.

Console equivalent:

```powershell
voidsmith scan --starsector-path C:\Starsector --output-dir D:\VoidSmithOutput
```

Use `--all-installed-mods` for a read-only diagnostic that includes disabled
installed mods. Use `--summary-only` when you want scan/cache/impact summaries
without optional per-entity analysis reports.

The scanner records parser warnings rather than crashing on malformed optional
numbers. A malformed mod file can still appear in errors; it is not silently
rewritten.

## Ships, variants, and legality

The **Ships** workspace displays scanned hulls and a fitting canvas. Selecting
a mount uses backend legality filtering; built-in mounts are shown but are not
editable. If art is unavailable, the canvas uses a geometry outline. Mount
markers are based on parsed `.ship` geometry, not hardcoded locations.

`voidsmith validate VARIANT_ID --starsector-path C:\Starsector` validates an
existing variant. `analyze-variant` adds quality and available derived stats:

```powershell
voidsmith analyze-variant VARIANT_ID --profile LINE_BRAWLER `
  --flux-mode BALANCED --starsector-path C:\Starsector
```

Legality is deliberately separate from quality:

- `LEGAL`: all supported hard checks pass.
- `ILLEGAL`: a supported hard check fails.
- `NOT_DETERMINABLE`: required legality depends on unavailable evidence.

Warnings such as weak flux, incomplete script coverage, or a role mismatch do
not make a legal build illegal.

## Generating a build

Generation fills normal supported mounts conservatively, can select supported
hullmods/fighter wings, allocates vents/capacitors, validates the result, and
scores legal candidates. It produces a bounded shortlist rather than an
exhaustive combinatorial search.

```powershell
voidsmith generate HULL_ID --profile LINE_ARTILLERY --mode guided `
  --faction-id hegemony --faction-mode FACTION_PLUS `
  --flux-mode SAFE --max-candidates 5 --search-depth 2 `
  --starsector-path C:\Starsector --output-dir generated
```

Available modes are `beginner`, `guided`, and `advanced`. Flux targets are
`SAFE`, `BALANCED`, and `AGGRESSIVE`. `STRICT_FACTION`, `FACTION_PLUS`, and
`UNRESTRICTED` control access policy; they never override legality.

Without `--profile`, generation may explore a bounded number of inferred build
paths (`--build-alternatives`). `voidsmith list-profiles` lists the current
quality profiles.

### Confidence, unknown effects, and omissions

Every recommendation keeps confidence separate from its recommendation score.
Confidence is reduced by incomplete data/evidence; it is not a hidden score
penalty pretending a build is illegal.

`UNKNOWN_SCRIPTED_EFFECT` means a hullmod/system/other mechanic could not be
reliably modeled from static data or readable local Java. `COMPILED_ONLY_SCRIPT`
means a declared script has JAR artifacts but no readable matching source; no
JAR is executed or decompiled.

Complex hull slots may produce `STRUCTURAL_SLOT_OMITTED` for a station module,
launch bay, or fixed built-in slot. This is distinct from
`UNSUPPORTED_MOUNT_SEMANTICS`. The generator leaves these alone rather than
inventing a fit.

## Refit / Repair Assistant

The **Retrofits** workspace can suggest a legality repair or a limited quality
improvement. Source variants remain read-only; the result is a suggested new
variant.

```powershell
voidsmith refit VARIANT_ID --mode FIX_LEGALITY --lock-mount "WS 001" `
  --substitution-mode adaptive --faction-id hegemony `
  --starsector-path C:\Starsector
```

Quality modes are `REDUCE_FLUX`, `IMPROVE_ROLE_MATCH`, `IMPROVE_LOGISTICS`, and
`BALANCED_IMPROVEMENT`; they require `--profile`. Locks are repeatable:
`--lock-mount`, `--lock-hullmod`, and `--lock-wing`. For legality repair,
substitution can be `cheapest`, `exact`, `starsector_style`, or `adaptive`.
`exact` never substitutes.

## Factions, gaps, and Why-Not

The **Faction** workspace reports a faction's parsed known hull capability,
doctrine evidence from existing variants, and detected gaps. Recommendation
results distinguish:

- `NATIVE`: a hull already known by the faction;
- `RETROFIT`: an existing variant improved with bounded changes;
- `ACQUISITION`: a non-native candidate with access/affinity context.

```powershell
voidsmith recommend faction_id --no-foreign-hulls `
  --exclude-experimental-builds --campaign-stage MID `
  --starsector-path C:\Starsector

voidsmith why-not faction_id LINE_BRAWLER HULL_ID `
  --build-archetype TANK --starsector-path C:\Starsector
```

Why-Not uses the same ranking/audit context as recommendation generation. It
can tell you whether a hull was ineligible, below cutoff, displaced by
diversity, or not considered for a supported reason.

Knowledge packs are optional advisory files (`--knowledge-pack`). They may
affect guidance, access affinity, and confidence, never hard legality.

## Entity type, composite ships, and warfare posture

The Data/Analysis surfaces distinguish ordinary ships from composite parents,
modules, fighter-like hulls, unboardable entities, and explicit mech/drone/
strikecraft hints. `CombatEntityKind` says what an entity is; `DeploymentModel`
says how much deployment evidence is known. Fighter-sized geometry alone does
not prove wing membership.

Ordinary recommendation pools exclude fighter-like and module/composite
entities because their independent or aggregate fitting semantics are not fully
modeled. This is an eligibility boundary, not a legality verdict.

The experimental six-axis warfare profile reports scored battlefield function,
engagement position, tactical style, tempo, commitment, and fleet dependence.
It only uses parsed defenses, flux, mobility, mounts/arcs, bays, and observed
variant weapon mix. It does **not** infer ramming, reserve/sweeper use, custom
AI behavior, ammo/rearm cycles, or fleet doctrine from flavor text.

## AI/player suitability and calibration evidence

Static control-suitability signals can describe range coherence, flux stability,
burst/missile proxies, mobility versus engagement range, system complexity,
weapon-group complexity, and defensive posture when parseable. They are not a
combat outcome prediction. A custom combat AI source can be detected, but its
behavior remains unknown unless supported by static evidence.

Calibration uses local, hash-bound reviewer/observation evidence. It is
advisory evaluation of registered heuristics, not automatic self-training or a
network service. The repository does not include real game/mod benchmark data.

## Export and checking exports

`export` generates a legal conservative candidate and writes a compatibility
mod under the output location. It does not modify the original variant.

```powershell
voidsmith export HULL_ID --profile LINE_BRAWLER `
  --starsector-path C:\Starsector --output-dir generated
voidsmith check-export generated/path/to/manifest.json `
  --starsector-path C:\Starsector --output-dir generated
```

`check-export` rescans read-only and compares the export manifest's source
hashes with current input data so you can see whether an export is stale.

## Useful queries

`query` creates JSON reports below `<output-dir>/reports`:

```powershell
voidsmith query hulls --hull-size CRUISER --starsector-path C:\Starsector
voidsmith query fighters --role bomber --starsector-path C:\Starsector
voidsmith query faction-equipment --faction-id faction_id --starsector-path C:\Starsector
```

Hull records include civilian tags, structural recommendation eligibility, and
the experimental warfare profile. Fighter records include source-role and
entity/deployment profiles.

## Unsupported / future work

VoidSmith does not yet simulate combat, run scripts, model all runtime
load-order overrides, optimize a whole fleet, read campaign saves/inventory,
verify market availability, or claim full support for every mod. Treat
unknown/partial findings as useful boundaries, not hidden assumptions.
