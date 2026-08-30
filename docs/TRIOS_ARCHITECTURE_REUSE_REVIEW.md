# TriOS Architecture Reuse Review

Reviewed 2026-08-23 against [TriOS](https://github.com/wispborne/TriOS), a
separate Starsector launcher/mod-manager/toolkit. This review uses its design
ideas only; no TriOS code, assets, data, or UI is copied or shipped.

## Boundary

TriOS is a mod manager and may change installed-mod state. Starsector Variant
Generator is a read-only analyzer/generator: it must never write Starsector or
mod directories. Therefore a TriOS-style profile **can only be an analysis
snapshot** here. It cannot enable, disable, install, rename, download, or
otherwise activate a mod.

## Findings

| TriOS pattern | Classification | Adaptation for this project | Scope / contract |
|---|---|---|---|
| Shallow persisted mod-profile records, separate from full mod objects; profile changes are previewed as add/remove/swap/missing differences. | ADAPT — implemented read-only core | `core/scan_profiles.py` now provides `ScanProfile` snapshots: installation identity, enabled-mod IDs, source-manifest hash, timestamps, persistence, and an explicit current-scan diff. | Store only in configured output/settings. A profile can select an analysis context, never edit `enabled_mods.json`. |
| Platform-specific helpers for game/JRE/log locations plus a validated game-root controller and optional custom paths. | ADAPT | Introduce an explicit `InstallationLayout` service when macOS/Linux fixture evidence is available. Keep `AppConfig` platform-neutral and have the scanner consume the resolved read-only source paths. | Do not infer a macOS Starsector layout from TriOS alone; add fixtures before implementation. |
| Pinned versus reorderable navigation and workspace-specific page state. | ADAPT | Persist selected workspace, table/filter state, splitter sizes, and last selected normalized entity with `QSettings`; keep required Settings/Export navigation pinned. | UI-only state. It must not duplicate analysis/legality state. |
| Long-running work uses isolated task wrappers/channels, while UI exposes loading/error states. | ADAPT | Extend GUI workers with typed phase/progress events and cooperative cancellation at scanner-defined safe checkpoints. | Cancellation must stop future parsing/report work and retain no partial result as a completed scan. It needs a scanner contract change and tests. |
| Log viewer summarizes known errors, records last refresh, and avoids treating every log line as fatal. | ADAPT | Add a read-only Diagnostics panel that groups scanner warnings/errors/skips, provides report/log paths, and allows copying/opening only output directories. | Game/mod logs remain source input; no in-place log mutations. |
| Generic settings managers plus migration/backups when state schema evolves. | ADAPT | Version the application-owned preferences/profile JSON and perform migration by writing a backup before replacement. | `QSettings` window fields can remain; profile/export state needs a portable schema. |
| UI controllers own selection/state; managers own parsing/filesystem work; parse results aggregate file-level errors. | REUSE_DIRECTLY | This project already follows the useful part: Qt widgets call `api`, workers isolate long tasks, `Scanner` and parsers own source access, and `ScanResult` preserves warnings/errors/skips. Retain and tighten this separation. | No GUI rules engine; no direct source access from widgets. |
| Per-file/per-row error collection lets malformed mods be reported while other mods continue. | REUSE_DIRECTLY | Existing scanner behavior already matches this and should be surfaced more clearly in Diagnostics. | Preserve malformed/unusual data as warnings/errors/skips; never silently repair source data. |
| Updater/release channels, installers, and platform-specific launch support. | DEFER | The current reproducible PyInstaller build and hash/smoke verification are sufficient. | Installer, code signing, hosted updates, and release channels require a license, signing identity, distribution policy, and a security review. |
| Mod downloads, installation, version retention, enabled-mod switching, game launching, JRE/RAM mutation. | NOT_APPLICABLE | These are contrary to the generator's source-safety/read-only contract. | Explicitly out of scope. |

## Concrete next steps

1. Bind the implemented portable `ScanProfile` schema/diff to the GUI.
2. Add typed progress/cancellation events at safe scanner checkpoints.
3. Add a GUI Diagnostics panel for `ScanResult` warnings/errors/skips and
   output-report paths.
4. Add cross-platform path fixtures before changing path resolution.
5. Revisit installer/update work only after the release-policy decisions are
   made.

## Evidence consulted

- TriOS’s `mod_profiles` model/manager separates shallow persisted profile
  records from full mod variants and computes profile differences before
  applying them.
- Its `platform_paths` and game-path controller centralize platform path
  selection/validation.
- Its task wrappers and viewer managers isolate long work and collect parse
  errors instead of failing a full scan.
- Its navigation model distinguishes reorderable tools from pinned settings.

These observations are architectural summaries, not copied implementation.

## Interoperability decision

### TriOS mod profiles: yes, import-only

Support is appropriate because the current TriOS profile document has a narrow
membership shape: `modProfiles[]` with named `enabledModVariants[]` records
and `modId`. The generator now supports an explicit caller-selected profile
import preview through `import_trios_profile`. It does not interpret
`smolVariantId` or version data as a Starsector load-order/compatibility
guarantee, and it does not modify TriOS or game files.

### TriOS installation metadata: no automatic interoperability

TriOS application settings include mutable, platform-specific paths and are
not a documented public interchange format. Automatically locating or trusting
them would couple this project to TriOS internals and could select an unwanted
installation. The generator keeps its own user-selected installation path.
An explicit future *suggested-path* import would require a versioned schema,
clear user confirmation, and platform fixtures; it must never overwrite either
application's settings.
