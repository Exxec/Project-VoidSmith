# VoidSmith Quick Start

VoidSmith is a read-only Starsector ship, variant, and faction-analysis tool.
It reads your local installation and mods; it never overwrites game or mod
files. Generated reports, caches, logs, and exports go below the output folder
you choose.

## Install and launch

If you have a packaged Windows release, extract the VoidSmith folder somewhere
writable and launch the included GUI executable. It is portable: no installer,
administrator rights, or registry setup is required.

For a source checkout, use Python 3.15+ and `uv`:

```powershell
uv sync --extra gui
uv run voidsmith-gui
```

The primary console command is `voidsmith`; the GUI entry point is
`voidsmith-gui`. Legacy `svg` / `svg-gui` aliases remain for local workflow
compatibility. A Windows build can be made from a checkout with
`tools/build_gui_exe.ps1` (output goes to the gitignored `dist/`). If a previous `dist/VoidSmith.exe` is still open,
use the newly created versioned `dist/VoidSmith-<version>.exe`; the build does
not need to close the running copy.

## GUI: first build

1. Open **Settings / Export**.
2. Choose the Starsector installation and an output folder.
3. Click **Scan Installed Data**. This reads core data and enabled mods.
4. Open **Ships**, select a hull, and use the **Generate** tab.
5. Choose a mode, optional faction/access mode, and profile; click generate.
6. Read the legality, score, confidence, warnings, and omitted-structure notes.
7. Export only a candidate marked `LEGAL` with **Export Current Hull
   (conservative)**.

The GUI can also accept a dropped mod folder or archive as an extra scan source.
It is not copied into the game installation. Archives are read with size and
compression-ratio limits, and links are refused.

After a scan, **Data / Analysis > Diagnostics** lists mod files that failed to
parse (with file and line) and enabled mods that are not installed.

## Console: first build

Replace `C:\Starsector` with your installation path.

```powershell
voidsmith scan --starsector-path C:\Starsector --output-dir generated
voidsmith list-profiles
voidsmith generate your_hull_id --profile LINE_BRAWLER `
  --starsector-path C:\Starsector --output-dir generated
voidsmith export your_hull_id --profile LINE_BRAWLER `
  --starsector-path C:\Starsector --output-dir generated
```

`scan` writes reports and a cache under the output folder. `generate` prints
the report path for deterministic, bounded alternatives. `export` writes a
generated compatibility mod only when it has a legal candidate. `scan` also
prints parse-failure and missing-enabled-mod lines.

Read-only checks (source builds; see the User Guide for details):

```powershell
voidsmith validate-all --starsector-path C:\Starsector --output-dir generated
voidsmith acceptance --baseline generated/reports/acceptance_baseline.json `
  --starsector-path C:\Starsector --output-dir generated
voidsmith check-mod C:\Mods\MyModFolder --starsector-path C:\Starsector
```

## Reading a result

VoidSmith separates **legality**, **quality**, and **confidence**. A build can be
legal without being the best choice, and a high-scoring build can still carry
limited confidence when a mod uses mechanics that cannot be proven statically.

- `LEGAL` means the documented validation checks passed. It does not mean the
  build is optimal.
- `ILLEGAL` means a hard parsed constraint failed, such as mount compatibility,
  OP, bays, vents/capacitors, or a missing reference.
- `NOT_DETERMINABLE` means available static evidence cannot safely decide a
  required rule.
- Score and confidence are separate. A high score can still have limited
  confidence when data or scripted mechanics are incomplete.
- `UNKNOWN_SCRIPTED_EFFECT` means VoidSmith did not execute or guess a script.

## Current support boundary

**Supported:** scanning, normal hull fitting, conservative generation,
validation, variant analysis, minimal-change refit, faction capability/gap
recommendations, Why-Not, locked-fleet support recommendations, static scenario
alignment, and generated compatibility-mod export.

**Partial:** mod scripts/static Java effects, complex/module ships, fighter-like
entities, doctrine, and AI/player suitability.

**Experimental:** six-axis warfare posture, combat-entity/deployment labels,
manual overrides, knowledge-pack guidance, and calibration evidence. These are
advisory and do not silently override legality.

**Read-only inspection (source builds):** `voidsmith save inspect "PATH_TO_SELECTED_SAVE_FOLDER"` reports qualified descriptor facts and XML integrity only. Add `--resources` for qualified values or use `save plan SAVE_DIR --set credits=200000` for a read-only change plan. `save write SAVE_DIR --set credits=200000 --output-dir DIR` (or **Write edited copy** in the Save Workshop, which Settings / Export keeps off by default) writes a verified new copy below `DIR/save_workshop/` for changes within the saved capacity (the original is never modified; over-capacity changes are refused; the copy is not loaded in the game, so try it on a throwaway first, and back up the original: the game saves a loaded copy back to the original's folder). See [the format contract](CAMPAIGN_SAVE_FORMAT.md).

**Not supported:** combat simulation, save-game/inventory planning, market
availability, whole-fleet optimization, executing/decompiling mod code, and
runtime load-order-effective script behavior.
