# Save resource locators and edit planning

S2 source implementation, 2026-10-06. The format boundary remains precisely
game `0.98a-RC8`, save `0.6`, uncompressed UTF-8 XML. All S1 limits, path/link
refusals, declaration refusals and read-only rules remain in force.

## Static evidence

The installed game was inspected with `javap -p` and `javap -p -c`, without
executing the game or mod code. The application imports no game code. No
bytecode disassembly, extracted source or real save fixture is distributed.

The following format facts were established from the game's serialization
registration in `CampaignGameManager`, field declarations, and saved structure:

| Evidence row | Field and serialized representation | Stored type |
| --- | --- | --- |
| RC8-CREDITS | CargoData `credits` aliases to `c`; its MutableValue holds `value` | float32 |
| RC8-STACK | CargoItemStack aliases to `CIStack`; `size` aliases to `s`, data to `d`, type to `t`, maximum to `mS`, cargo space per unit to `cSPU` | float32 quantity |
| RC8-CAPACITY | CargoData maxCapacity/maxFuel/maxPersonnel/spaceUsed alias to mC/mF/mP/sU | float32 saved figures |
| RC8-STORY | CharacterStats storyPoints aliases to `sp` | signed int32 |

These are storage facts, not proof of game-load acceptance or current runtime
capacity. The saved figures may be stale. Capacity-overage speed and upkeep
effects remain UNKNOWN; no consequence is calculated or displayed.

## Exact location and ambiguity

The root's playerFleet pointer is resolved by object identity. The selected
fleet's fD/cargo identifies its cargo; c/value identifies its credit value.
The root's characterData/person pointer identifies player stats, never NPC
stats elsewhere. Inline objects and referenced container/value objects are
supported. Each referenced identifier must resolve once; duplicates, cycles
and excessive reference chains are refused. Class aliases alone never select
an object. Resource stacks must be inline RESOURCES stacks with a plain string
identifier. Missing, referenced or duplicate stacks are not invented.

The reader builds small selected projections, not a full campaign DOM. Projections
reuse already captured inline children, while every reference scan retains
bounded XML validation and hash checking. Additional bounds: 10,000 projected
nodes, 4,096 characters per scalar, 16 KiB opening tags, 128-character numeric
representations and eight reference steps. Numeric attributes are tokenized with
quote-aware matches; text inside an unrelated quoted attribute cannot become an
edit target. Expat supplies UTF-8 byte offsets. Scalars with markup, numeric
entities or unsupported representations are refused.

Locators retain exact original ASCII bytes, start/end byte offsets, stored type
and an evidence row. Only those numeric spans belong to a planned change.
Campaign and descriptor hashes are checked throughout and after projection.
Malformed or changed sources return no edit-ready facts.

## Separate schema and rules

`campaign-resources-v1` records resources, optional saved capacity fields,
source hashes, notes and unmodeled cargo state. `campaign-edit-plan-v1` records
immutable requests/changes, old/new values, numeric replacements, exact locators,
per-change outcomes and reasons, explicit capacity opt-in, catalog provenance,
readiness and the independent write-gate state. These schemas never feed fit
legality, scoring, recommendation or fleet optimization.

Requests must be whole non-negative integers; booleans, fractions and strings
are refused. Story points must fit signed int32. Float32 quantities must round
trip exactly through float32, rather than silently losing units. Stack maximums
are checked where qualified; missing limits are refused. Duplicate requests,
tier-2/3 targets and missing stacks are refused. No-op requests preserve their
original number spelling. Nonempty cargo partials refuse commodity edits because
their contribution is unmodeled.

Tier-1 commodity identifiers must also exist in a hash-recorded CSV catalog from
installed core and explicitly enabled native sources. The source discovery
adapter lives in api.py; no game facts or source lists are hardcoded into the
catalog. Disabled and unknown-enabled-state sources are excluded. Incomplete
discovery, unreadable CSV, unrecognized IDs, changed sources and invalid headers
make membership unavailable. Source roots, CSV size (8 MiB) and count (512) are
bounded; source links and traversal are refused. No CSV is modified or copied.

Changed commodity quantities are judged against the saved capacity per
dimension (owner decision 2026-10-06; before it, every change was
NOT_DETERMINABLE):

- cargo: saved space used plus each edited stack's change times its saved space
  per unit, against saved cargo capacity (all edited cargo stacks together);
- fuel: the fuel stack against saved fuel capacity;
- personnel: crew plus marines against saved personnel capacity.

A result at or below the capacity is ACCEPTED. Above it, or unprovable (a saved
figure or a stack's space per unit missing, or saved space used lower than the
stacks occupy), it is NOT_DETERMINABLE and overage effects stay UNKNOWN. Saved
capacity is a saved figure, not a runtime-verified one. Explicit
`allow_unknown_capacity` still marks a plan ready for review, but the writer
never writes an over-capacity change. It never bypasses a refusal. Credits and
story-point plans need no commodity catalog.

## Source-build API and CLI

`run_save_resources(save_dir)` returns only read-only resource facts.
`run_save_commodity_catalog(starsector_path)` reads native installed membership.
`run_save_edit_plan(save_dir, requests, catalog, allow_unknown_capacity=...)`
returns the immutable reviewable plan and writes nothing.
`run_save_edit_write(plan, output_dir, name=None)` writes one verified new copy
(see S3 below).

```text
voidsmith save inspect "SELECTED_SAVE_DIRECTORY" --resources
voidsmith save plan "SELECTED_SAVE_DIRECTORY" --set credits=200000 --set story_points=10
voidsmith save plan "SELECTED_SAVE_DIRECTORY" --starsector-path "SELECTED_INSTALLATION" --set commodity:supplies=100 --allow-unknown-capacity
voidsmith save write "SELECTED_SAVE_DIRECTORY" --starsector-path "SELECTED_INSTALLATION" --set commodity:supplies=400 --output-dir "OUTPUT_DIRECTORY"
```

Both commands emit JSON on stdout; inspection exits one on a refused format,
and planning exits one if any change is refused or lacks required planning
opt-in. No plan is executed. `ready_for_copy` is distinct from write permission.

## Overage preview (2026-10-18)

When a planned commodity quantity would exceed a saved capacity, `EditPlan.overage_preview` (shown in `save plan` JSON and in the GUI
plan view) lists, from `campaign/overage.py`, the recorded consequences cited by BridgeForge row id for build 0.98a-RC8: RC8-34 (0.1
supplies per day per unit over cargo, fuel or personnel capacity, capped at 50 per resource, costs add) and RC8-35 (the burn level
becomes max(1, round(base burn x (2 - r))) for the worst used/capacity ratio r; the base burn is not read from a save, so only r and
the factor are shown). RC8-36 is cited for the saved figures being written at save time. It is display only: the change stays
NOT_DETERMINABLE and is never written, and every other overage effect is UNKNOWN. Whether a load recomputes an edited
`mC`/`mF`/`mP` is still unmeasured.

## S3: verified copy writer (2026-10-06)

The write gate is `OPEN_WITHIN_CAPACITY` (owner decision 2026-10-06; it was
`CLOSED_CAPACITY_EVIDENCE`). `voidsmith save write` and
`api.run_save_edit_write` write one new copy below
`OUTPUT_DIR/save_workshop/NAME` and nothing else:

- Every change must be ACCEPTED. NOT_DETERMINABLE and REFUSED changes block the
  whole write, including a change carrying the plan's capacity opt-in:
  over-capacity writing is not implemented. The CLI `write` offers no opt-in.
- The save must still match the plan's hashes; the bytes at each planned span
  must equal the located value. Only the planned spans are patched in the bytes
  of `campaign.xml` (no re-serialisation); every other file is copied unchanged.
  The saved space-used figure is not rewritten; whether the game recalculates it
  on load is untested.
- The target is created, never overwritten. The output directory must be
  separate from the save and its parents, with no links or `..`. The save folder
  must be flat; a subfolder, link or unusual entry refuses the write. The copy
  name is 1-120 characters of letters, digits, `_`, `.`, `-` (default: the
  save name plus a digest of the plan).
- `campaign/verify.py` then re-hashes the original, checks the copy's file list,
  walks the copy's bytes against the planned spans with its own offset
  arithmetic, and re-reads the copy through the qualified readers (planned values
  present, every other resource and the saved capacities unchanged). Any problem,
  or any error, removes the copy and returns `FAILED_VERIFICATION` or `FAILED`.
- A written copy carries the notice that it has not been loaded in the game, and that it keeps the original's character and slot identity:
  in a local test the game loaded an edited copy and then saved to the ORIGINAL's folder, so back up the original before playing the copy.
  The edited copy's saved space-used figure was stale (the game accepted it and wrote the stack sum on its next save).
  Game acceptance remains untested; S5 and S6 are separate. S4's GUI write
  controls are built (2026-10-18) behind the default-off Workshop setting.

Existing packaged binaries are unchanged.


## S4 GUI workspace and validation checkpoint

In source builds, Settings / Export exposes **Enable Save Workshop (inspect,
plan, write verified copies)**, off by default and scoped to the current session. This adds a
separate top-level workspace. The user explicitly selects one save folder;
no path is guessed or scanned automatically. Overview shows only backend
resource facts, saved capacity and evidence limits. Resources uses a model/view
table with current value, requested new value, backend check and reason tooltip.
Changing a request or opt-in invalidates the current plan. Plan and verify shows
backend old/new values, reasons, evidence and the independent write gate.
The write button is enabled only for a fully ACCEPTED, current plan with an output directory (otherwise its tooltip names what is missing and the backend gate reason); it writes through `api.run_save_edit_write`, re-verifies the copy and shows VERIFIED or FAILED_VERIFICATION.

All save inspection and planning run in retained SaveWorker threads using the
existing background-operation service. Stop Waiting discards result delivery;
it does not claim to interrupt backend reads. Old results cannot replace a
newer request. Closing the main window waits for retained workers to finish.
The preview does not load campaign facts into any fitting or recommendation
engine. There is no default-on or release decision yet (S6 is the owner's).

Validation: full unittest suite, 822 tests run successfully with two skips.
S2 adds 22 synthetic tests; S4 adds five GUI smoke/workflow tests, including
an actual worker lifecycle without a scan. Read-only qualification locates
credits and story points in 81/81 supplied saves; exact spans, source hashes
and independent before/after non-mutation checks pass in every case. Native
commodity membership was verified read-only outside the restricted sandbox;
unreadable metadata remains unavailable inside it. No ACL or source file was
changed. Detailed local reports remain under ignored dist output. Static
lint is not claimed because Ruff is unavailable. Existing packages are unchanged.


The GUI worker smoke test suppresses inherited auto-scan timers while pumping
the shared test event loop, so earlier GUI tests cannot open an unrelated modal
scan dialog. The final full-suite run passes with that isolation. This changes
test setup only; application auto-scan behavior remains covered by its existing
tests. `git diff --check` passes. S3 remains genuinely blocked on the requested
controlled-capacity evidence record; no approval or empirical result is inferred
from elapsed time or from a successful read/plan.
