# Campaign inspection format contract

Qualified profile: `campaign-inspection-v1`, 2026-10-06. This is a read-only
XML integrity and descriptor inspector, not a resource parser or an editor.

## S0 evidence and version boundary

Eighty-one owner-supplied local campaign folders from the selected game and isolated-rig directories were inspected read-only. Each
contained `descriptor.xml` rooted at `SaveGameData` and `campaign.xml` rooted
at `CampaignEngine`. Every descriptor declared game `0.98a-RC8`, save format
`0.6`, and `compressed=false`. Campaign sizes ranged from 9,458,593 to
87,509,452 bytes. No other version is qualified. Descriptor declarations are
source assertions, not proof of the creating executable or runtime compatibility.
No real saves, names, entity lists, or excerpts are distributed as fixtures.

The XML uses aliased objects and `z` object identifiers with `ref` references.
These observations do not establish editable resource semantics. Unknown
elements and attributes are structurally parsed and otherwise ignored. Credits,
cargo, story points, enabled mods, and capacities remain `UNAVAILABLE`.
Capacity-overage consequences remain `UNKNOWN`.

The independently supplied AC8 research handles GVAS/Unreal property tags,
not Starsector XML. Its byte-for-byte round-trip verification practice informs
future verification design; no code, fields, checksums or format rules were imported.

## Input, limits and failures

The caller explicitly selects one save directory. Only the two fixed filenames
above are opened, in binary read-only mode. No recursive discovery or location
guessing occurs. Parent traversal, symlinks and Windows reparse points in any
ancestor or either selected file are refused. Only regular UTF-8 XML files are
supported; UTF-16 is refused. DOCTYPE and entity declarations are refused by
parser callbacks before expansion. Scripts and serialized classes are never executed.

The descriptor cap is 1 MiB; campaign cap is 256 MiB. Streaming Expat reads
64 KiB chunks; maximum depth is 256 and maximum element count is 5,000,000
per file. Recognized descriptor scalars are direct children only, capped at
4,096 characters each. Duplicate or nested recognized scalars are malformed.
Limits are engineering guards, not game rules.

Only the exact version pair above and explicit `compressed=false` are accepted.
Older, newer, missing or otherwise different versions return `UNSUPPORTED_VERSION`.
Compressed input returns `UNSUPPORTED_FORMAT`. Malformed/truncated XML returns
`MALFORMED`; foreign roots or missing/unreadable files return `NOT_A_SAVE`.
Unsafe paths/XML and exceeded limits have distinct refusal statuses.
Partial descriptor hashes may accompany a refusal; no partial facts are returned.

Each completed file read records SHA-256. File identity, size and modification
metadata are checked before opening, during the open, and after closing;
detected changes return `SOURCE_CHANGED`. Users should close the game before
inspection. This is not a hardened defense against a hostile process racing
filesystem operations; no mutation API exists in this slice.

## Normalized schema and consumers

`campaign/models.py` owns frozen `SaveInspection` and `CampaignFact` records.
Facts carry name, optional string value, `PARSED | UNAVAILABLE | UNKNOWN`, and
evidence. Results carry schema version, status, facts, source hashes and notes.
Unavailable values are null, never favorable zeroes. `READABLE` proves accepted
XML structure only, not save health or game-load acceptance.

The API `run_save_inspect(save_dir)` and CLI `voidsmith save inspect SAVE_DIR`
return these records. The CLI writes JSON to stdout only, exits zero on READABLE
and one on refusal. No output, cache, source or log file is written. Redirecting
stdout is the caller's choice. No parser imports generation, scoring, profiles,
validation or recommendations. No campaign fact feeds those engines.

## Gate coverage and outstanding work

The six read-only parser inputs are covered by this format description, the
separate schema, no-write safety plan, neutral fixtures, refusal/non-mutation
tests and the isolated inspection consumer. Existing directory discovery stays
metadata-only. Broader semantics require their own documented evidence and tests.

S0 and S1 are implemented for this single observed profile. S2 is separately implemented and qualified in `CAMPAIGN_SAVE_RESOURCES.md`; basic inspection keeps its original descriptor-only schema. S3 (2026-10-06) adds a verified new-copy writer for changes within the saved capacity, `voidsmith save write`; see `CAMPAIGN_SAVE_RESOURCES.md`. No Save Workshop GUI write control or default-on flag exists.
The existing BridgeForge format survey was reviewed as a structural cross-check; its statistical cargo observations do not prove stored types or runtime effects. No code was imported.

S5 still requires controlled throwaway-campaign observations, which cannot be
substituted with static inspection. Original saves and game folders remain read-only.


## Validation checkpoint — 2026-10-06

- Full existing unittest suite plus the new inspection tests: 795 tests run,
  successful, two skips. The inspector contributes 18 tests; its symlink test
  is skipped because this host cannot create symlinks. A real Windows junction
  refusal test passes, including the Windows reparse-point boundary.
- Final read-only qualification: 81/81 selected campaigns READABLE; every
  descriptor and campaign SHA-256 matches independent before/after hashes.
  This proves source non-mutation and accepted XML, not game-load acceptance.
- `git diff --check` passes. Ruff is unavailable in the local environment;
  no Ruff result is claimed. No heuristic, legality or ranking values changed.
- User-local detailed hashes and qualification checkpoints remain under the
  ignored dist output, outside distributable fixtures and documentation.
- No existing portable artifact was rebuilt, overwritten, or published.
