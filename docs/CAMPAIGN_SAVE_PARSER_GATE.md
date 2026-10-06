# Campaign-Save Parser Evidence Gate

The six inputs below are now met for the bounded read-only inspection scope documented in `CAMPAIGN_SAVE_FORMAT.md` (2026-10-06). S2 resource interpretation and pure planning now meet those inputs under `CAMPAIGN_SAVE_RESOURCES.md`. Writing is implemented separately (S3, within saved capacity only; see `CAMPAIGN_SAVE_RESOURCES.md`).

Directory discovery remains direct, metadata-only enumeration of a directory
explicitly selected by the user. The application does not open save contents,
guess save locations, follow links, alter saves, infer inventory, or make
campaign availability claims.

Content parsing may begin only after all of these inputs exist:

1. A documented, read-only format description with version boundaries and
   failure behavior for malformed or newer saves.
2. A separate normalized campaign schema that distinguishes parsed facts from
   unavailable/runtime-only information.
3. A source-safety plan proving parser output and errors write only below a
   configured user output/cache directory.
4. Neutral synthetic fixtures or user-local ignored fixtures; no copied save,
   game, or mod content may enter the distributable repository.
5. Tests for path traversal, links, malformed data, unknown fields, version
   mismatch, and explicit non-mutation.
6. A scope decision for every proposed consumer. Parsed campaign facts may not
   silently change legality, recommendation score, or whole-fleet planning.

Writing is a further gate. The Save Workshop (`SAVE_WORKSHOP_DESIGN.md`) may write only a new copy of a
user-selected save below the configured output directory, after the original has been hashed, and must re-read the
copy to confirm that only planned values changed. The original is never modified and the game's saves folder is
never written. Capacity-overage effects are `UNKNOWN` until evidence is recorded there. S3 (owner decision 2026-10-06) implements that write path for changes within the saved capacity only; over-capacity changes are refused and never written.

`discover_campaign_directory()` still returns `CAMPAIGN_SAVE_UNINSPECTED` metadata only. The separate opt-in-by-command `run_save_inspect()` boundary accepts one selected folder under `CAMPAIGN_SAVE_FORMAT.md`; basic inspection returns no editable facts. Explicit `run_save_resources()` and `run_save_edit_plan()` add separately qualified read-only resources and plans under `CAMPAIGN_SAVE_RESOURCES.md`; neither writes files.
