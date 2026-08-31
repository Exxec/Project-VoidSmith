# Campaign-Save Parser Evidence Gate

Current support is limited to direct, metadata-only enumeration of a directory
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

Until then, `discover_campaign_directory()` remains the complete supported
boundary and returns `CAMPAIGN_SAVE_UNINSPECTED` metadata only.
