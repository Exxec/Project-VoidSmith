# GUI.md
# VoidSmith GUI Design Contract
Version 0.5

This document defines the GUI architecture, interaction rules, rendering behavior, and user experience requirements for VoidSmith.

It is intended to be read by Codex and other implementation agents before modifying GUI-related code.

## 1. Authority and Precedence

This document governs GUI behavior and presentation.

If this file conflicts with:
1. `AGENTS.md`
2. the formal Starsector Variant Generator specification
3. backend data-model or validation contracts

then `AGENTS.md` and the formal specification take precedence unless this document explicitly records an approved architectural change.

The GUI must never redefine game rules, legality rules, scoring rules, or generation rules that belong to the backend engine.

## 2. GUI Framework

Use **PySide6 / Qt** for the desktop GUI.

Do not use Tkinter unless explicitly requested.

The GUI should be a conventional desktop utility, not a web dashboard.

Preferred Qt concepts include:
- `QMainWindow`
- `QSplitter`
- `QTabWidget`
- `QTableView`
- `QTreeView`
- model/view separation
- custom graphics widgets
- `QGraphicsView` / `QGraphicsScene`
- worker threads/tasks for expensive operations

The GUI must remain responsive during Starsector/mod scanning, database rebuilds, candidate generation, and batch analysis.

Do not perform expensive work on the main UI thread.

## 3. Core GUI Principles

The GUI should be:
- dense but readable
- practical
- desktop-oriented
- scalable to large modpacks
- transparent about why a build was chosen
- safe around source files
- useful for beginners without hiding expert functionality

Avoid oversized cards, excessive whitespace, decorative animation, unnecessary full-screen transitions, duplicated backend logic, UI-only legality rules, and silent modification of source data.

Prefer split panes, tabs, tables, collapsible advanced panels, tooltips, sortable lists, clear warnings, visible source/mod attribution, context menus, and persistent user preferences.

## 4. User Modes

The GUI must expose:
1. **Beginner**
2. **Guided**
3. **Advanced / Manual**

All three must use the same underlying Profile object and generation engine.

### Beginner
Required controls:
- hull
- role/profile
- faction/equipment mode
- generate

Defaults should favor AI friendliness, flux safety, range coherence, survivability, faction-appropriate equipment, and low micromanagement.

Output:
- one recommended build
- up to two alternatives
- simple explanation
- important warnings only

### Guided
Expose:
- hull
- role
- Safe / Balanced / Aggressive
- AI / Player
- Strict Faction / Faction+ / Unrestricted
- short / balanced / long-range preference
- defense / balanced / damage preference

### Advanced / Manual
Expose:
- scoring weights
- range targets
- minimum/maximum acceptable range
- flux tolerance
- allowed overflux
- PD budget
- missile budget
- OP reserve
- required/forbidden weapons
- required/forbidden hullmods
- locked mounts
- mounts allowed to remain empty
- fighter restrictions
- faction purity
- mod allowlist/denylist
- S-mod assumptions
- officer skills/personality
- AI/player assumption
- candidate count
- search depth
- deterministic seed

### Open in Advanced
Every Beginner or Guided build must support **Open in Advanced**.

It must preserve the exact profile values and fitting state. It must not silently regenerate or change the build.

## 5. Main Application Views

Initial major views:
1. Home / Scan Status
2. Hull Browser
3. Existing Variant Browser
4. Ship Fitting Canvas
5. Beginner Generator
6. Guided Generator
7. Advanced Generator
8. Candidate Comparison
9. Faction Doctrine Viewer
10. Settings
11. Export / Compatibility Mod Builder

## 6. Ship Fitting Canvas

The Ship Fitting Canvas is a primary GUI feature.

It must provide a large, interactive, resizable visual representation of the selected ship.

The target experience is an **annotated technical / exploded fitting view** where weapon slots connect to controls with callout/leader lines.

### 6.1 Canvas Layout
- Display the selected ship in a central canvas.
- Render it enlarged enough to inspect weapon slots clearly.
- Resize with the application window.
- Support zoom in/out.
- Support panning.
- Center the ship by default.
- Preserve sprite sharpness as much as practical.
- Keep slot anchors aligned during zoom, resize, and pan.

The canvas uses drag panning without persistent scrollbars, preserving the
technical-view presentation while retaining navigation at any zoom level.

Recommended implementation:
- `QGraphicsView`
- `QGraphicsScene`
- custom graphics items for hull sprite, weapon sprite, slot marker, callout anchor, callout line, selection highlight

### 6.2 Rendering Layers
Suggested order:
1. background/grid if enabled
2. hull sprite
3. built-in visual elements
4. weapon-slot markers
5. selected weapon sprites
6. selection highlights
7. callout anchors
8. callout/leader lines
9. transient hover indicators

Weapon and marker positions must come from hull data, not per-ship hardcoding.
Carrier launch-bay anchors, hidden anchors, and decorative slots are retained
as parsed structure but are not displayed as selectable weapon markers.
When a hull declares launch bays, the canvas instead presents a compact,
non-selectable **Fighter bays** stack beside the hull. It reports parsed bay
IDs/capacity without pretending that a launch-point coordinate is a weapon
mount or that fighter-wing fitting is already editable on the canvas.

### 6.3 Weapon Slot Anchors
Each slot anchor should know:
- slot ID
- slot size
- slot type
- position
- angle
- arc if available
- built-in status
- selected weapon if any

Hovering or clicking a slot must synchronize with its matching callout and List View row.

### 6.4 Callout / Leader Lines
Each visible slot should have a callout containing:
- slot ID/readable name
- slot size
- slot type
- selected weapon
- dropdown/combo box

Leader lines must update during resize, zoom, pan, and callout rearrangement.

### 6.5 Callout Placement
Prefer callouts around the outside of the ship:
- left slots -> left column
- right slots -> right column
- center/front/rear -> choose the side that minimizes crossing

Support:
- scrollable callout panes
- collapsible slot groups
- automatic packing
- temporary focus mode for selected slots

## 7. Callout View and List View

Provide both:
1. **Callout View**
2. **List View**

List View suggested columns:

| Slot | Size | Type | Current Weapon | OP | Range | Source Mod |
|---|---|---|---|---|---|---|

Both views must operate on the same authoritative fitting state. Changing one updates the other immediately.

## 8. Weapon Dropdown Rules

Each slot dropdown must show only legal and permitted weapons.

Filtering order:
1. slot legality
2. equipment/faction mode
3. hidden/secret visibility
4. user allowlist/denylist
5. text search
6. sorting

The GUI must not invent mount legality independently of the backend.

### 8.1 Slot Size
- Small -> Small weapons only
- Medium -> Medium weapons only
- Large -> Large weapons only

Do not automatically allow smaller weapons in larger slots unless the backend says Starsector permits it.

### 8.2 Slot Type
Examples:
- Large Energy -> legal Large Energy weapons
- Medium Ballistic -> legal Medium Ballistic weapons
- Small Missile -> legal Small Missile weapons
- Small Universal -> any legal Small weapon type
- Hybrid / Synergy / Composite -> follow backend Starsector legality mapping

## 9. Equipment Access Modes

Supported:
- **Strict Faction**
- **Faction+**
- **Unrestricted**

### Strict Faction
Only show legal faction-native/approved equipment. If no suitable weapon exists, leave the slot empty rather than silently broadening access.

### Faction+
Prefer faction-native equipment but allow approved fallback equipment. Fallback items should be visually marked.

### Unrestricted
Allow any installed legal weapon passing all other filters. Show source mod/faction clearly.

## 10. Hidden / Secret Equipment

Support a global/session option:

**Show Hidden / Secret Equipment**

Default: OFF

When OFF:
- hidden/secret/dev/unobtainable equipment must not appear

When ON:
- allow it
- clearly mark it as hidden/restricted
- do not imply it is normally player-obtainable

If the backend cannot determine the exact reason, label it `Hidden / Restricted`.

## 11. Dropdown Usability

Large modpacks require searchable selectors.

Support:
- text search
- sorting
- category filtering
- source-mod filtering
- range display
- OP display
- damage type
- optional role tags

Advanced sorting may include name, OP, range, DPS, flux efficiency, source mod, faction affinity, and generator score.

## 12. Live Weapon Rendering

Selecting a weapon must immediately update the ship preview.

This is a hard requirement.

When selected:
- render the weapon in the matching slot if sprite data exists
- position at slot coordinates
- rotate according to slot orientation
- preserve alignment through zoom/pan/resize

If the sprite is missing:
- keep the logical fit
- render a placeholder
- show a warning/tool tip
- do not invalidate an otherwise legal fit

## 13. Built-In Weapons

Built-ins must:
- render normally
- be clearly marked
- disable replacement controls if immutable
- show a tooltip explaining built-in status

## 14. Hover and Selection Synchronization

Hover/click state must synchronize between:
- ship slot
- weapon sprite
- callout
- List View row
- weapon detail panel

## 15. Weapon Details Panel

Show:
- name
- size
- type
- OP
- range
- damage type
- DPS
- flux/sec
- damage/flux
- ammo
- role tags
- source mod
- faction affinity
- hidden/restricted status
- current-profile generator score
- reason it is legal for the slot

Advanced mode may expose additional raw values.

## 16. Live Build Metrics

Changing equipment should immediately update:
- OP used / available
- vents
- capacitors
- estimated weapon flux/sec
- effective dissipation
- range coherence
- role balance
- PD score
- AI friendliness
- legality state
- warnings

These must come from backend analysis services.

The current implementation surfaces backend-authoritative legality and weapon
OP used/remaining after each manual slot edit. More complete flux, role, and
equipment-access metrics remain dependent on the shared fitting-state contract;
the GUI must not calculate substitutes itself.

The current canvas displays a logical selected-weapon marker at a parsed mount
when no normalized weapon sprite reference is available. This is deliberate
fallback rendering, not a claim of exact weapon-art placement.

For conventional `.wpn` files, the scanner also preserves declared
`turretSprite` and `hardpointSprite` paths as local rendering metadata. The
canvas renders that art immediately after selection when the local file can be
resolved. It maps Starsector's forward/lateral mount coordinates into the
upright fitting view and scales weapon art to a readable slot preview; missing
or non-standard weapon art falls back to the logical marker without changing
legality. This is a static preview, not a model of animated turret state or
pixel-perfect combat placement.

## 17. Legality Feedback

Show one of:
- LEGAL
- LEGAL
- INLEGAL

Avoid relying on color alone.

Invalid builds should show exact reasons.

## 18. Empty Slots

Include `<Empty>` where legal.

The generator and user may intentionally leave slots empty for OP, flux, range coherence, or AI behavior.

## 19. Weapon Groups

Reserve support for weapon-group editing, but it should not block the first fitting-canvas milestone.

Future fields:
- group number
- mounts/weapons
- linked/alternating
- autofire

## 20. Hullmods / Fighters / Flux Layout

Reserve panels for:
- hullmods
- S-mods
- fighter wings
- vents
- capacitors
- officer assumptions
- variant score

Suggested overall layout:

```text
+-------------------------------------------------------------+
| Hull / Variant / Mode controls                              |
+----------------------+----------------------+---------------+
|                      |                      |               |
| Left Callouts        |   Ship Canvas        | Right Callouts|
|                      |                      |               |
+----------------------+----------------------+---------------+
| Hullmods | Fighters | Flux | Groups | Analysis | Warnings   |
+-------------------------------------------------------------+
```

Use resizable splitters where appropriate.

## 21. Resizing and Persistence

Remember:
- window size
- splitter positions
- selected mode
- last hull
- callout/list preference
- Starsector path
- equipment mode
- Show Hidden setting
- Advanced profile values
- recent exports

## 22. Zoom and Pan

Minimum controls:
- mouse-wheel zoom
- zoom in
- zoom out
- reset zoom
- fit ship to view
- drag/pan
- optional zoom percentage

Zoom must not alter logical slot coordinates.

## 23. Sprite Loading

Use a dedicated resource layer.

It should:
- resolve core/mod-relative sprite paths
- cache images
- report missing images
- avoid reparsing mod data
- handle duplicate references safely

Widgets should not hardcode sprite paths.

## 24. Rendering Accuracy

Use slot position, slot angle/orientation, sprite dimensions, and weapon origin metadata when available.

Hull art must be transformed into the declared `.ship` width/height coordinate
space before slot positions are overlaid. A sprite texture's native resolution
is not itself mount geometry; when declared dimensions are absent, retain raw
sprite placement and identify the result as approximate rather than inventing
dimensions.

Distinguish turret/hardpoint where data supports it.

If exact rendering data is unavailable:
- use best-known placement
- mark visual positioning approximate if necessary
- never alter legality because of missing rendering metadata

## 25. Authoritative Fitting State

Maintain one authoritative fitting state, conceptually:

```text
CurrentFitState
    hull_id
    profile_id
    faction_mode
    show_hidden
    selected_weapons_by_slot
    selected_hullmods
    selected_fighters
    vents
    capacitors
    officer_assumption
    locked_slots
    dirty_state
```

Canvas, List View, scoring, and export must observe this same state.

## 26. Modified State

Manual edits to generated builds must mark them as modified.

Provide:
- Reset to Generated
- Save as New Candidate
- Export Current
- Open in Advanced

Do not silently overwrite the original generated candidate.

## 27. Candidate Comparison

Support side-by-side/table comparison with:
- total score
- role match
- flux sustainability
- range coherence
- AI friendliness
- survivability
- PD
- faction match
- OP used

Selecting a candidate should preview it on the fitting canvas.

## 28. Beginner Presentation

Beginner mode should summarize rather than flood the user with numbers.

Examples:
- Good range match
- Safe flux
- Strong shield pressure
- Good AI fit

Plain-language warnings are preferred.

## 29. Advanced Presentation

Expose detailed diagnostics:
- score breakdown
- role weights
- range distribution
- flux calculation
- weapon-role contribution
- faction doctrine contribution
- candidate pruning explanation
- legality details

Advanced users should be able to understand why an item was excluded.

## 30. Tooltips

Explain unfamiliar concepts such as Range Coherence, Faction+, Hidden Weapon, Flux Safety, and AI Friendliness.

Keep tooltips concise.

## 31. Search and Filtering

Hull filters:
- faction
- source mod
- hull size
- role
- ship name
- carrier capability
- vanilla/modded

Faction and source-mod filters are independent. Faction membership comes only
from parsed faction `knownShips` evidence, so a hull supplied by a different
mod may appear under a faction that explicitly lists it. A hull with no such
parsed evidence remains visibly unassigned rather than being guessed from its
source mod.

Weapon filters:
- size
- type
- range
- damage type
- source mod
- faction
- hidden status
- role tags

## 32. Source Visibility

Always show the source mod/faction for modded entities.

This is especially important in Unrestricted mode.

## 33. Performance

Do not block the UI during:
- scans
- parsing
- cache rebuilds
- candidate generation
- doctrine analysis

Use worker threads/tasks.

Long operations should provide progress and cancellation where practical.

Hull-name filtering is debounced before rebuilding the browser list. Background
analysis results are request-token gated so a stale completion cannot overwrite
a newer request; this is result adoption control, not unsafe forced cancellation
of backend work.

Where a backend operation has no safe interruption point, the GUI must name
the distinction precisely. The scan UI may offer **Discard Results**: the
read-only background scan completes, but its result is not adopted by the
session. It must not imply that a parser has been forcibly terminated.

The Ship Fitting Canvas should remain interactive during background analysis.

## 34. Error Handling

Normal users should not see raw stack traces by default.

Error dialogs should include:
- concise description
- affected file/entity
- recommended action if known
- Copy Details button

Detailed traces belong in logs.

## 35. Source Safety

Clearly distinguish:
- source variants
- generated variants
- modified generated variants

Source variants are read-only.

Generated content may only be written to configured generated-output/compatibility-mod paths.

## 36. Export

Before export:
- validate
- warn on valid-with-warnings
- block clearly invalid export unless explicit developer/debug mode is enabled

Never overwrite source files.

Include metadata such as generator version, profile, faction mode, source hashes, and fitting selections.

## 37. Accessibility / Readability

Support:
- light/dark themes
- non-color-only warnings
- readable scaling
- keyboard navigation where practical
- meaningful focus states
- high-contrast selection markers
- scalable canvas labels

Do not assume 100% Windows display scaling.

## 38. GUI Architecture

Recommended structure:

```text
gui/
    main_window/
    views/
        home/
        hull_browser/
        variant_browser/
        fitting/
        doctrine/
        settings/

    widgets/
        ship_canvas/
        slot_callout/
        weapon_selector/
        weapon_details/
        score_panel/
        warning_panel/

    models/
        qt_hull_model/
        qt_weapon_model/
        qt_candidate_model/

    controllers/
        fitting_controller/
        generation_controller/
        export_controller/

    workers/
        scan_worker/
        generation_worker/
        analysis_worker/

    resources/
        sprite_cache/
        icon_loader/
```

The backend must remain testable without Qt.

## 39. No Backend Duplication

The GUI must call backend services for:
- slot legality
- faction filtering
- hidden filtering
- OP calculations
- flux analysis
- scoring
- role classification
- generation
- validation

The GUI must not become a second rules engine.

## 40. Unknown / Scripted Mechanics

When the backend flags `UNKNOWN_SCRIPTED_EFFECT`, show a warning that scoring may be incomplete.

Do not pretend certainty.

## 41. First Ship Canvas Milestone

Required:
- load one selected hull
- render hull sprite
- zoom
- pan
- display slot anchors
- display per-slot dropdowns
- filter by slot legality
- filter by Strict Faction / Faction+ / Unrestricted
- filter hidden equipment
- render selected weapon sprites
- update OP/legality display

Built, then deliberately removed once real usage exposed a problem
(`TechnicalCanvas.show_hull`, `main_window.py`): external leader-line
callouts and a separate slot List View. On a real 25-mount capital hull the
callout lines sprawled far enough past the ship that `fitInView` had to zoom
out to fit them, shrinking the ship (and its clickable mount boxes) to a
barely-visible speck; the boxes' own color/size/tooltip already carried the
same information the callouts duplicated. Slots are now chosen by clicking
directly on the highlighted mount box on the canvas itself, with no separate
list to keep in sync.

Not required initially:
- weapon-group editing
- animated turrets
- firing arcs
- combat simulation
- hullmod visual effects
- fighter rendering
- officer visualization

## 42. Second Ship Canvas Milestone

After the first is stable:
- ~~automatic callout packing~~ / ~~line-crossing reduction~~ -- moot: leader-line
  callouts were removed entirely (section 41)
- candidate preview switching -- implemented (`_preview_candidate`,
  `main_window.py`)
- mirror-symmetric mount-pair detection and linked fitting -- implemented
  (`_detect_mirror_mount_pairs`, "Mirror fitting" toggle), though this is
  pair-based, not the general slot-grouping this line originally meant
- weapon detail popovers
- mount-arc overlays
- optional grid/rulers
- improved sprite anchoring
- keyboard navigation

## 43. Optional Future Enhancements

Possible later features:
- drag-and-drop weapons
- radial mount selection
- side-by-side ship comparison
- hull opacity slider
- firing-arc overlays
- DPS/flux heatmaps
- armor/shield overlays
- doctrine overlays
- fleet fitting view
- saved GUI workspaces
- plugin-specific render adapters
- build-card screenshots

These must not block the initial GUI.

## 44. Codex GUI Implementation Rules

1. Read `AGENTS.md`.
2. Read the formal specification.
3. Read this `GUI.md`.
4. Do not modify backend rules to make GUI work easier.
5. Do not duplicate validation logic.
6. Do not hardcode per-ship slot positions.
7. Keep source files read-only.
8. Add GUI/controller tests where practical.
9. Keep expensive work off the UI thread.
10. Preserve deterministic backend behavior.
11. Stop after the requested GUI milestone.
12. Write a short completion report.
13. Document known rendering limitations.
14. Do not add decorative features before core fitting interaction works.

## 45. Initial GUI Definition of Done

- [ ] PySide6 application launches reliably.
- [ ] Starsector installation can be selected.
- [ ] parsed hulls can be browsed.
- [ ] a hull can be opened in Ship Fitting Canvas.
- [ ] hull sprite renders.
- [ ] zoom and pan work.
- [ ] weapon slots align with hull data.
- [ ] callout lines remain aligned during resize/zoom/pan.
- [ ] each slot has a synchronized weapon selector.
- [ ] selectors enforce slot legality.
- [ ] selectors respect Strict Faction / Faction+ / Unrestricted.
- [ ] hidden equipment is excluded by default.
- [ ] hidden equipment can be enabled and is clearly marked.
- [ ] selected weapon sprites render in slots when available.
- [ ] List View and Callout View share the same state.
- [ ] OP and legality update live.
- [ ] Beginner/Guided/Advanced use the same backend profile model.
- [ ] Open in Advanced preserves build state.
- [ ] source variants remain read-only.
- [ ] generated output is written only to safe output paths.
- [ ] long operations do not freeze the GUI.
- [ ] missing sprites and unknown scripted effects produce clear warnings.
- [ ] GUI logic remains separate from backend generation and validation logic.

## 46. Summary

The central interaction model is:

```text
Select hull
    |
    v
Display enlarged ship
    |
    v
Show weapon-slot anchors
    |
    v
Connect slots to callout selectors
    |
    v
Filter weapons by legality + faction mode + hidden status
    |
    v
Render selected weapons live
    |
    v
Update OP / flux / legality / scores
    |
    v
Compare candidates
    |
    v
Export safely
```

The fitting canvas should feel like an interactive technical diagram rather than a simple spreadsheet.

**One fitting state. One backend rules engine. Multiple GUI presentations.**

Callout View, List View, Beginner, Guided, and Advanced modes should all operate on the same data and the same validated build state.


## 47. Data Contract Dependencies

GUI controls must consume normalized contracts from `DATA_SCHEMA.md`.

Weapon selectors should receive backend-resolved values for:

- slot legality
- equipment-access classification
- hidden/restricted state
- source mod
- faction affinity
- sprite resource
- scripted-effect confidence

The GUI must not rescan source files to rediscover these rules.

## 48. Override and Adapter Visibility

Advanced mode should expose provenance when a displayed value came from:

- a manual override
- a mod adapter
- inferred data
- unknown/incomplete analysis

Examples:

`AI Friendliness: 0.85 [Manual Override]`

`Ammo Endurance: Adapter-modeled`

## 49. Confidence States

The GUI should recognize:

- KNOWN
- INFERRED
- OVERRIDDEN
- ADAPTER_MODELED
- UNKNOWN

Unknown information must not be presented as an exact fact.

## 50. GUI Readiness Gate

Do not implement production GUI features against unstable backend contracts.

A GUI prototype may be built earlier using fixture data, but it must not become
an alternate rules engine.

When backend contracts become stable, the production GUI should bind to those
services directly.


## 51. Build Inspector and Refit Assistant

The Existing Variant Browser should support opening a variant in a Build
Inspector.

Build Inspector should show:
- legality: LEGAL / ILLEGAL / NOT_DETERMINABLE
- legality reasons
- OP use
- weapons and groups
- hullmods/S-mods
- fighters
- vents/caps
- DerivedShipState metrics
- warnings
- unknown scripted effects
- provenance

Actions:
- Suggest Legality Fix
- Improve Build
- Lock Selected Components
- Compare Before / After

Refit suggestions must show each proposed change and its reason.

## 52. Civilian / Logistics Presentation

When a civilian profile is active, the primary analysis panel should prioritize:
- cargo
- fuel
- crew/capacity where applicable
- monthly maintenance
- fuel efficiency
- burn
- sensor metrics where known
- survey utility where known
- salvage utility where known
- survivability
- role match

Combat metrics remain available in a secondary tab.

The GUI must not display whole-fleet optimization recommendations in the current
scope.

If a fleet-support effect is detected, display:

`Fleet-support effect detected; recorded but not included in current per-ship optimization.`

## 53. Hullmod Effect Inspector

Selecting a hullmod should display:
- OP cost
- known typed effects
- affected stats
- operation/value
- confidence state
- adapter/override provenance
- unknown scripted effects

When toggling a hullmod, update the DerivedShipState and visible metrics live.

## 54. Legality Display Standard

Use:
- LEGAL
- ILLEGAL
- NOT_DETERMINABLE

Quality warnings are displayed separately.

Do not use "LEGAL WITH WARNINGS" as a legality state.


## 55. Top-Level Workspace Tabs

Use top-level tabs/workspaces to prevent feature overload.

### 55.1 Ships

Purpose:
single-hull inspection, fitting, and candidate work.

Contains:
- Hull Browser
- Ship Fitting Canvas
- Existing Variant Browser
- Build Inspector
- Candidate Comparison

Recommended internal sub-tabs:
- Browse
- Fit
- Inspect
- Compare

### 55.2 Retrofits

Purpose:
modify or repurpose an existing hull/variant.

Contains:
- Refit / Repair Assistant
- Retrofit Templates
- Native vs Retrofit
- Locked Components
- Before / After comparison
- Experimental Retrofits

Recommended internal sub-tabs:
- Suggestions
- Templates
- Before / After
- Locks

Cross-link:
Faction recommendations may open a selected retrofit directly here.

### 55.3 Faction

Purpose:
faction-level doctrine and recommendation context without becoming a whole-fleet
optimizer.

Contains:
- Faction Capability Overview
- Strengths / Weaknesses / Gaps
- "I Recommend These"
- Native / Retrofit / Acquisition sections
- Knowledge Pack
- Doctrine Strictness
- Progression Stage
- Doctrine Evidence
- Why Not?

Recommended internal sub-tabs:
- Overview
- Gaps
- Recommendations
- Knowledge Pack
- Progression
- Evidence

### 55.4 Data / Analysis

Purpose:
advanced inspection of parsed entities and engine reasoning.

Contains:
- Weapons
- Hullmods
- Fighters
- Variants
- Factions
- Adapters
- Overrides
- Unknown Scripted Effects
- Provenance

Recommended internal sub-tabs:
- Weapons
- Hullmods
- Fighters
- Variants
- Provenance

### 55.5 Settings / Export

Purpose:
application configuration and output.

Contains:
- Starsector path
- enabled mods
- scan/cache state
- heuristic set
- output path
- compatibility mod creation
- logging/debug controls

Recommended internal sub-tabs:
- General
- Mods
- Heuristics
- Output
- Logs

## 56. Navigation Rules

Cross-workspace actions should preserve context.

Examples:
- Faction recommendation -> open selected hull in Ships
- Faction retrofit recommendation -> open selected template in Retrofits
- Build Inspector issue -> open Refit Assistant with current variant
- Retrofit result -> preview in Ships
- Any entity source -> open Data / Analysis provenance

Do not duplicate backend state to achieve this.

## 57. Faction Recommendation Presentation

For each gap show:
- Best Native Choice
- Best Retrofit
- Best Acquisition
- up to 3 recommended alternatives

Each item:
- hull
- role
- score
- confidence
- short rationale
- important warning
- source mod

## 58. Recommendation Controls

Lightweight controls:
- Allow foreign hulls
- Allow hidden/secret hulls
- AI / Player / Either
- Experimental retrofits
- Doctrine strictness
- Optional campaign stage

## 59. Why-Not Interaction

Any candidate should support:
**Why wasn't this recommended?**

Show:
- eligibility
- score
- confidence
- strongest positives
- strongest negatives
- exclusion reason
- shortlist cutoff where useful

## 60. Knowledge Pack Status

Display:
- CURRENT
- PARTIALLY_STALE
- STALE
- INCOMPATIBLE

For stale packs show installed vs target version and explain that current
mechanical analysis remains authoritative.

## 61. Fleet Setup Naming Caution

Do not label the Faction workspace "Fleet Planner" in the current version.

Use labels such as:
- Faction
- Faction Guidance
- Faction & Recommendations

because exact whole-fleet composition is outside current scope.


## 62. Equipment Access and Retrofit Mode Controls

Ships and Retrofits expose:

```text
Equipment Access: Strict Faction / Faction+ / Unrestricted
Retrofit Application: Exact / Starsector-Style / Adaptive
```

## 63. Unaligned Equipment

Display factionless content as `Affinity: Unaligned` plus its source mod. Do not hide it merely because the source mod has no faction.

## 64. Equipment Provenance

Advanced details show source mod, faction affinity, availability class, hidden state, confidence, adapter coverage, and override coverage.

## 65. Adaptive Substitution Explanation

Show target item, chosen replacement, why it won, strong alternatives, source mod, affinity, and confidence.

## 66. Gap Recommendation Engine

See `GAP_RECOMMENDATION_ENGINE.md` (project-authored) for the algorithm
behind section 57's "I Recommend These" presentation.

## 67. Scenario / Mission Advisor

The Faction workspace may evaluate the same locked selection against a generic
scenario template or explicit user-declared `CAPABILITY=target` values. Show
mechanical alignment as `GOOD`, `MIXED`, `POOR`, or `UNKNOWN`, followed by
strong, weak, and unknown dimensions and individually ranked additions.

Never label this a combat prediction or promise that a fleet will win a named
mission. The UI must render the backend assessment and its stated limits; it
must not calculate scenario readiness or candidate ranking locally.
