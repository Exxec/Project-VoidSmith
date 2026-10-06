# Save Workshop design (decision-gated)

Status: **design approved 2026-10-06; S0–S3 implemented by owner request: read-only inspection, edit planning and a verified new-copy writer for changes within the saved capacity.** Over-capacity writing, the GUI write controls and release readiness remain unbuilt.
The source implementation now includes S0/S1 read-only inspection under `CAMPAIGN_SAVE_FORMAT.md`. Qualified resource locators, pure planning and the S3 writer are documented in `CAMPAIGN_SAVE_RESOURCES.md`. S4 provides a default-off read-only GUI preview; existing distributed binaries are unchanged.

## Purpose

Let a player make small, validated changes to their own campaign state without Console Commands or an in-game
mod, for example topping up supplies, fuel or crew after a bad fight. The first release is deliberately minor.

This is a separate, clearly labelled mode. It does not change legality, recommendation, scoring or fleet-planning
behavior, and parsed save facts never feed those engines (see the parser gate, item 6).

## Boundary with the rest of VoidSmith

VoidSmith's source-safety rule (`AGENTS.md`) stays intact: game and mod files, and the player's original save, are
never modified. The Save Workshop writes only a **new copy** of a save the user selects, below the configured
output directory, and the user moves that copy into the game's saves folder themselves. The Workshop never
writes to the game's saves folder, and never guesses where saves live.

A companion tool, Salvor (separate repository, local only), diagnoses and repairs broken saves. The Workshop does
not repair; it edits a healthy save. They share no runtime code dependency.

## Scope, in tiers

| Tier | Edits | Validation before the copy is written |
| --- | --- | --- |
| 1 (first release) | credits; player-fleet cargo commodities (supplies, fuel, crew, marines, heavy machinery); story points | whole, non-negative quantities; the commodity id exists in the installed core or enabled mods; capacity handling below |
| 2 | fleet-member repair state (combat readiness, hull, armour, crew on a member); officer level and skills | registered skill ids only; ranges taken from installed data |
| 3 | known blueprints; adding or removing fleet members; faction relations; market conditions and industries | hull, variant and weapon ids and real slots; conditions checked against industries |
| Later | offline presets | all of the above through the same gate |

Anything the tool does not recognise is refused, not guessed.

## Capacity overages are UNKNOWN

The project owner reports that carrying more than a fleet's capacity slows the fleet (if the limit is weight
based) and raises the supplies consumed per day. The calculation is not known, and nothing here may invent it
(`AGENTS.md`, "Do Not Invent Game Behavior").

Rules:

1. The Workshop never predicts or displays a speed or upkeep consequence. The effect is `UNKNOWN`.
2. It refuses to write a quantity above the capacity it can read from the save. The design allowed an explicit user
   opt-in with a visible warning; S3 (owner decision 2026-10-06) does not implement that path, so over-capacity edits
   are never written. Changes at or below the saved capacity are written.
3. Capacity itself is read from installed data only if documented and parseable; otherwise the check returns
   `NOT_DETERMINABLE` and the user must opt in to proceed.
4. Evidence to resolve this, in order: a controlled before/after run in a throwaway campaign, recorded with the
   quantities, the observed fleet speed and the observed daily consumption; then a documented rule here, with the
   evidence cited. Until then the rules above stay.

## How this meets the parser gate

`docs/CAMPAIGN_SAVE_PARSER_GATE.md` lists six inputs before any content parsing. For the Workshop:

1. **Format description:** to be written from the saves the user supplies, with version boundaries and the
   failure behavior for malformed or newer saves. S0 is documented in `CAMPAIGN_SAVE_FORMAT.md` for one observed version; S2 resource locators and stored types are qualified in `CAMPAIGN_SAVE_RESOURCES.md`; capacity effects remain UNKNOWN.
2. **Normalized campaign schema:** separate from the hull schema; separates parsed facts from runtime-only state.
3. **Source-safety plan:** parser output, errors and every edited copy are written only below the configured
   output directory; the original save is opened read-only.
4. **Fixtures:** neutral synthetic saves, or user-local ignored saves. No real save enters the repository.
5. **Tests:** path traversal, links, malformed data, unknown fields, version mismatch, non-mutation of the
   original (hash before and after), and the refuse-when-unrecognised rule for every edit path.
6. **Consumer scope:** the only consumer is the Workshop's own editor. Parsed facts do not reach legality,
   scoring, recommendations or whole-fleet planning.

## Write pipeline (every edit)

1. Read the chosen save read-only and hash it.
2. Build an edit plan; show every change as old value, new value and evidence.
3. Validate each change; refuse or `NOT_DETERMINABLE` as above.
4. Write a new copy below the output directory (never overwrite; refuse if the target exists).
5. Re-read the copy and confirm that only the planned values differ.
6. Tell the user the copy has not been loaded in the game and should be tried on a throwaway first. Parsing is not
   proof that the game accepts the save.

## Not goals

Real-time memory access, an in-game helper, network features, and editing anything outside a user-selected save
copy. Combat simulation and campaign planning stay out of scope.
