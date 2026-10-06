# Save Workshop implementation plan (design only)

Companion to [SAVE_WORKSHOP_DESIGN.md](SAVE_WORKSHOP_DESIGN.md). Nothing here is authorized to ship until the
parser gate in [CAMPAIGN_SAVE_PARSER_GATE.md](CAMPAIGN_SAVE_PARSER_GATE.md) is met; the slices below are ordered so
that each one is useful, testable and reversible on its own, and the write path is the last thing built.

## Principles carried over from the repository contract

- The backend owns every rule; the GUI only presents (`GUI.md`).
- The original save is never modified; the only write is a new copy below the configured output directory.
- Unknown stays unknown. Edit checks return `ACCEPTED`, `REFUSED` or `NOT_DETERMINABLE`. These are a separate
  enum from fit legality: `validation/` remains the only owner of `LEGAL`/`ILLEGAL`/`NOT_DETERMINABLE` for fits, and
  nothing in the Workshop feeds it.
- Offline, deterministic, explainable, testable without AI; no game or mod data in the repository.

## Code layout

A new subpackage `campaign/` beside `analysis/`, `validation/` and `output/`. It imports nothing from
`generation/`, `scoring/`, `profiles/` or the recommendation code, and none of them import it.

| Module | Responsibility |
| --- | --- |
| `campaign/format.py` | The documented format layer: bounded, streaming read of a save's XML. Refuses a DOCTYPE or entity declaration, a file over a size cap, and an unrecognised root. Records the game and save versions it can see and refuses a newer major version it has no row for. |
| `campaign/models.py` | Frozen dataclasses for parsed facts. Every field carries a `FactStatus` (`PARSED`, `UNAVAILABLE`, `UNKNOWN`), so a missing value is never a favourable zero. Separate from the hull schema. |
| `campaign/locators.py` | One locator per editable thing (credits, a cargo commodity stack, a capacity figure, story points). A locator returns the exact byte span of the value and the evidence for it, or refuses. No locator means no edit. |
| `campaign/edit_plan.py` | `EditRequest`, `PlannedChange` (old value, new value, locator, evidence) and `EditPlan`. Pure data; no I/O. |
| `campaign/edit_checks.py` | The only place edit rules live: whole non-negative quantities, a known commodity id (from the scanned core and enabled mods), capacity handling, and tier gating. Returns an outcome and a reason per change. |
| `campaign/writer.py` | Copies the save folder to a new directory below `output_dir`, patches only the planned byte spans in the copy (no re-serialisation, so the diff is exactly the edit), and refuses if the target exists. |
| `campaign/verify.py` | Hashes the original before and after, re-reads the copy, and proves that only the planned spans differ. Returns a `VerificationReport`; any surprise fails the write and removes the copy. |
| `campaign/fixtures.py` (tests only) | Builds neutral synthetic saves. No real save enters the repository. |

Surgical byte patching is the central choice: re-serialising a whole save would risk changing things the tool does
not understand. The cost is that every locator must be exact, which is why unrecognised paths are refused.

## Service boundary

- `api.py`: `run_save_inspect(save_dir)`, `run_save_edit_plan(save_dir, requests, registry)`,
  `run_save_edit_write(plan, output_dir)`. Dataclass results with explicit payload helpers, as elsewhere.
- CLI (`cli/main.py`, thin): `voidsmith save inspect`, `voidsmith save plan`, `voidsmith save write`. `write` prints
  the verification report and the not-loaded-in-game notice.
- Config: one opt-in flag, `save_workshop_enabled`, default off. While the gate is open the flag exists only in
  development builds. The output location is the existing `output_dir`, under `save_workshop/`.
- `run_campaign_save_discovery` stays as it is: the user picks a directory, the discovery lists entries, and the user
  picks one save from it. The tool never guesses a saves location.

## Data flow

```text
user-selected save folder (read-only)
  -> campaign/format.py bounded parse -> campaign/models.py facts (+ FactStatus)
  -> campaign/locators.py edit targets (byte spans + evidence)
  -> EditRequest list -> campaign/edit_checks.py -> EditPlan (outcomes, reasons)
  -> user reviews plan -> campaign/writer.py -> new copy under output_dir/save_workshop/
  -> campaign/verify.py -> VerificationReport
```

## Tier 1 edit rules

| Edit | Rule |
| --- | --- |
| Credits, story points | non-negative whole number within the format's stored type; nothing else |
| Cargo commodity (supplies, fuel, crew, marines, heavy machinery) | non-negative whole number; the commodity id must exist in the scanned data; a missing stack is created only if the locator can prove the stack's exact shape, otherwise `REFUSED` |
| Capacity | read from the save when the figure is present; the figure's meaning (stored at save time or derived later) is unproven, so a quantity above it returns `NOT_DETERMINABLE`, and writing it needs the explicit opt-in described in the design |

Effects of an overage on fleet speed or upkeep are never computed or displayed (they are `UNKNOWN`).

## GUI design

Follows `GUI.md`: PySide6, dense desktop utility, backend-owned rules, long work on a worker thread.

**Entry.** A new top-level workspace, **Save Workshop**, hidden until enabled in Settings. Enabling it shows a
one-time notice: edits are written to a copy; close the game first; try the copy on a throwaway campaign.

**Layout** (a `QSplitter`):

- Left pane, **Save**: a "Choose saves folder..." button (a `QFileDialog`, never a guessed path), a table of the
  entries the discovery found, and the selected save's status badge (`READABLE`, `UNSUPPORTED_VERSION`,
  `MALFORMED`, `NOT_A_SAVE`).
- Right pane, a `QTabWidget`:
  - **Overview**: read-only facts the parser could establish (save name, game version, enabled mods as listed,
    fleet totals), each with its `FactStatus`; unavailable items are shown as such, not hidden.
  - **Resources** (tier 1): a table with columns Item, Current, Capacity, New value, Check. "New value" is a spin
    box per row; the Check column shows `ACCEPTED`, `REFUSED` or `NOT_DETERMINABLE` with the reason as a tooltip.
    An over-capacity row is highlighted with a persistent "effects unknown" label and stays blocked until the
    opt-in checkbox ("Allow over capacity; consequences are unknown") is ticked. Row buttons: reset, and "set to
    capacity" where a capacity was read.
  - **Plan and verify**: the full diff (old value, new value, evidence), the plan's overall state, and, after a
    write, the verification report. A plan with any `REFUSED` row cannot be written.
- Footer: a permanent safety banner ("Edits a copy; your save is not changed"), the planned output path, and
  **Write edited copy**. After the write, a result dialog shows the verification outcome, the new folder, and the
  not-loaded-in-game notice, with an "Open output folder" action.

**Presentation split.** Display strings, badge text, colours and tooltips live in `gui/presentation.py` as pure
functions, tested headless like the existing presentation tests. The widget code holds no rules.

**Threading.** `gui/workers/save_worker.py` follows the scan and analysis workers: inspect, plan and write run off
the UI thread with progress and a safe "Stop Waiting" that discards a pending result without claiming to interrupt
the backend.

**Models.** An `EditTableModel` (model/view, like `EntityTableModel`) backs the Resources table; the Plan table is a
read-only model over `EditPlan`.

**Keyboard and clarity.** Tab order follows reading order; every disabled button carries a tooltip naming what is
missing; no silent modifications; nothing is written until the button is pressed.

## Slices, in order

| Slice | Delivers | Done when |
| --- | --- | --- |
| S0 | Format description for the supported save versions, written from user-supplied saves; synthetic fixture builder | the format doc exists with version boundaries and failure behavior; fixtures parse |
| S1 | `campaign/format.py`, models, `run_save_inspect`, CLI `save inspect` (read-only) | malformed, DOCTYPE, oversized, linked and newer-version inputs are refused with tests |
| S2 | Locators, edit requests, edit checks, plan (no write), CLI `save plan` | every tier-1 rule has a test that names it; overage returns `NOT_DETERMINABLE` |
| S3 | Writer and verifier, CLI `save write` | hash-before/after non-mutation test; only-planned-spans test; target-exists refusal; failed verification removes the copy |
| S4 | GUI workspace, presentation functions, worker | presentation tests pass; GUI smoke on a synthetic save; the refuse and opt-in paths are exercised |
| S5 | Evidence for capacity overages (see below) | a documented rule, or the `UNKNOWN` rules re-confirmed, with the evidence cited |
| S6 | Release readiness: docs, user-facing limits, feature flag decision | the owner decides whether the flag ships on; `README`, quick-start and user-guide "not supported" lines are updated in the same change |

S0 and S5 need real saves and the game, so they are user-local work. They cannot be completed by agent sessions
that lack the game or saves.

## Evidence plan for capacity overages

The tool is built without the answer; the answer decides only whether over-capacity edits can ever be described.
Run in a throwaway campaign, outside this repository (BridgeForge's test rig is one way): set cargo, fuel and crew
below, at and above capacity; record the quantities, the fleet's observed speed and the observed daily supplies
use for each case; repeat once with a fleet of a different size. Write the observations, the game version and the
procedure into the evidence record, then add a documented rule here. No formula is inferred from fewer than three
distinct fleets.

## Tests that must exist before the gate can close

Path traversal and link refusal; malformed and truncated input; DOCTYPE and entity refusal; unknown fields and
roots; newer-version refusal; hash-identical original after every operation; only-planned-spans diff; target-exists
refusal; each tier-1 rule by name; the over-capacity refuse and opt-in paths; and a check that no real save or game
data is in the repository or the package.

## Out of scope for this plan

An in-game helper, memory access, repairing broken saves (Salvor's job), tiers 2 and 3 (they reuse this structure
and need their own locators, checks and evidence), and any use of parsed save facts by the recommendation or
fit-legality engines.

## Appendix: lessons ported from BridgeForge (2026-10-06)

BridgeForge (the sister project, local) already reads saves read-only (`save-inspect`, `save-compat`, `save-doctor`,
`save-removal-plan`, `save-snapshot` and others) and runs live tests in an isolated rig. These are the parts of that
experience the Workshop should reuse. They are practices and observed format facts only; no game or mod data is
copied here.

### Save format facts observed (one 0.98a-RC8 save; S0 must confirm them across versions)

- A save folder holds a large XStream XML campaign file (about 10-15 MB) beside small descriptor files. Objects carry
  an id attribute and are referenced elsewhere by a matching reference attribute, so a value can sit far from the
  object that uses it. A locator must resolve references, not assume nesting.
- Class names are short aliases or obfuscated, and they change between game versions. Never key a locator on an
  obfuscated name alone; key it on structure plus a version row, and refuse when the version is unknown.
- Survey of 74 saves from one game version (0.98a-RC8): the player fleet's cargo container carried the same set of
  attributes in every one, and a credits value object was present in every one. Older or newer versions are not
  covered, so S0 still needs saves from other versions.
- A cargo container stores its stacks as elements holding a quantity and a commodity id, and the container also
  carries attributes that look like capacity and space-used figures (cargo, fuel, personnel). Whether those are
  stored at save time or derived later is **unproven**, so S1 must record it and S5 must test it.
- Credits are a separate value object, not a cargo stack.
- Mods leave their own classes and scripts in the file. An editor must preserve unknown content byte for byte, which
  is why the plan patches spans instead of re-serialising.

### Safety and process lessons

- **Parsing is not proof.** A save that re-reads cleanly may still be refused or may misbehave in the game. The only
  acceptance test is loading the copy in a throwaway rig. Say so in the result dialog.
- **Rig isolation.** Test runs use a separate game folder whose core is a junction or symlink to the real install,
  with its own saves and mods folders, and refuse to run if the core is a real copy. The real install and the
  player's saves are read-only. Use this pattern for the load test in S3 and S5.
- **A fatal error dialog never reaches the redirected log.** Record window text separately when load-testing, or a
  failed load will look like a pass.
- **Take a snapshot before and after.** Copy the save into the rig before loading, and compare hashes afterwards so a
  test cannot silently change the file under test.
- **Check that the right build made the save.** A save stores the mod list and versions it was made with; warn when
  the save was made with different versions than the ones scanned, as stale state wastes test time.
- **Registries to validate against** (all backend, none in the GUI): skills must be registered or the game errors
  fatally; market conditions and industries are distinct sets; a hull's weapon slots come from its own data. These
  matter for tiers 2 and 3, and the same "refuse what you cannot prove" rule applies.
- **Long operations** print one progress line per item and checkpoint so an interrupted run resumes; the Workshop's
  inspect of a large save and any batch plan should follow the same rule and the existing worker progress pattern.
- **Write code with the editor tools, not shell heredocs.** Escape sequences inside heredoc-generated source were
  unescaped twice and broke several edits in one session.

### Tools and test assets to reuse

| From BridgeForge | Use in the Workshop |
| --- | --- |
| `save-inspect`, `save-compat`, `save-doctor` | cross-check VoidSmith's reader on the same saves (differences are bugs in one of them); never import it |
| `save-snapshot` | model for the before/after copy and hash discipline |
| probe setup lines (credits, reputation, cargo-style setups applied through the public API) | build the S5 overage cases inside a throwaway campaign |
| rig launch helper with window and log capture | the S3/S5 load test procedure |
| `docs/RC8_BEHAVIOUR.md` (one row per proven fact) | the template for the Workshop's own evidence record; cite a row id in code |
| the unattended-run rule (progress, checkpoint, resume) | any batch edit or multi-save inspect |

Anything the Workshop proves about the game, such as overage effects, goes in a dated evidence row with its method,
as BridgeForge does, and BridgeForge's table may cite it by id.
