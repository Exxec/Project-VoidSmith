# VoidSmith
Read-only Starsector variant analysis and generation. Version 0.5 Planning Pack.

## Major Systems

- safe scanner/parsers
- Build Inspector
- hullmod effect engine
- combat + civilian classifiers
- automatic faction capability analyzer
- Faction Doctrine & Retrofit Knowledge Packs
- factionless weapon/fighter/hullmod pack support
- separate equipment provenance and faction affinity
- Exact / Starsector-Style / Adaptive retrofit application
- Refit / Repair Assistant
- Native / Retrofit / Acquisition recommendations
- recommendation confidence and Why-Not explanations
- full variant generator
- PySide6 desktop workspaces

## GUI Workspaces

1. Ships
2. Retrofits
3. Faction
4. Data / Analysis
5. Settings / Export

## Current Scope

Per-ship and faction-capability analysis, plus a locked-selection Fleet Support
Advisor that ranks individual complementary additions. Whole-fleet optimization,
player inventory, market acquisition, and save-state planning remain deferred.

## Development verification

The supported test command mirrors CI and installs the project editable for
the run:

```powershell
uv run --no-project --with-editable . python -m unittest discover -s tests -v
```

It requires Python 3.11+ and `uv`. The local canonical benchmark test skips
when its user-generated Starsector fixtures are unavailable; the portable
suite always runs.

## Windows executable build

From a local checkout, run [`dist/build_voidsmith.bat`](dist/build_voidsmith.bat).
It invokes the reproducible PyInstaller pipeline and writes only local build
artifacts, including a versioned `dist/VoidSmith-<version>.exe`. It also
refreshes `dist/VoidSmith.exe` when that legacy path is not currently locked by
a running copy. It packages neither Starsector nor mod content. The script
fails if packaging fails, so a prior executable is never presented as a newly
successful build.

## Read Order

1. AGENTS.md
2. FORMAL_SPECIFICATION.md
3. DATA_SCHEMA.md
4. HULLMODS_CIVILIAN_AND_REFIT.md
5. FACTION_KNOWLEDGE_PACKS.md
6. EQUIPMENT_ACCESS_AND_AUTOFIT.md
7. TEST_PLAN.md
8. HEURISTICS.md
9. GUI.md
10. ROADMAP.md
