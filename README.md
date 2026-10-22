# VoidSmith

VoidSmith is an offline, deterministic desktop tool for read-only Starsector
ship fitting, variant inspection, and faction-capability analysis.

**Current release:** [latest release](https://github.com/Exxec/Project-VoidSmith/releases/latest) · [All releases](https://github.com/Exxec/Project-VoidSmith/releases)

## What it does

- safely scans locally installed core and enabled-mod data without changing it;
- validates variants independently from recommendation quality;
- generates bounded legal fits and minimal-change refit suggestions;
- analyzes faction capabilities and explains Native, Retrofit, and Acquisition
  recommendations, including confidence and Why-Not paths;
- provides locked-selection Fleet Support and static Scenario / Mission
  advisory workflows; and
- exports only to a user-selected local output directory.

## Quick start

For a portable release, download the available archive for your platform from
[Releases](https://github.com/Exxec/Project-VoidSmith/releases), extract it to
a writable directory, and launch the included executable. Windows and Linux
release artifacts are built natively for their respective platforms when
published.

For a source checkout, install Python 3.15+ and [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --extra gui
uv run voidsmith-gui
```

See the [Quick Start](docs/QUICK_START.md) for setup and the
[packaging guide](docs/WINDOWS_PACKAGING.md) for local portable builds.

## Safety and scope

Optional sister-tool checks are available from source: `tools/review_spw_inventory.py INVENTORY INSTALLATION` reviews an explicit SPW inventory against current local metadata/JAR hashes without changing scans or fits. `tools/verify_portable_release.py ARCHIVE --release-evidence FILE [--downloaded-asset FILE]` reports separate source, build, native, live, rights, and publication evidence states. Matching local asset bytes alone leave publication authenticity unknown.

VoidSmith reads game and mod sources as untrusted, read-only input. It does not
overwrite source variants, alter Starsector files, execute mod scripts, or
bundle Starsector/mod data in this repository or its packages. Unknown or
scripted mechanics remain explicit rather than guessed.

It is not a combat simulator, whole-fleet optimizer, save-state planner, or
market/inventory availability tool. Legality, quality, confidence, and warnings
are deliberately separate.

Source builds also offer `voidsmith save inspect "PATH_TO_SELECTED_SAVE_FOLDER"` for bounded, read-only descriptor/XML inspection of game 0.98a-RC8 / save 0.6. It prints JSON and source hashes without modifying files. Add `--resources` for qualified values or use `save plan SAVE_DIR --set credits=200000` to review numeric changes without writing. `save plan` also shows the recorded cost and speed consequences of an over-capacity edit (cited by BridgeForge row id; the write stays refused). Settings / Export can enable a default-off Save Workshop in the GUI: inspect, plan, and a "Write edited copy" button. `save write SAVE_DIR --set ... --output-dir DIR` (and that button) writes a verified new copy of a save for changes within the saved capacity (over-capacity changes are refused, the original is never modified, the copy is untested in the game); existing portable binaries have not been rebuilt. See [the format contract](docs/CAMPAIGN_SAVE_FORMAT.md).

Source builds also offer checks that need no hand work, all read-only: `validate-all` validates every shipped variant, `acceptance` compares per-mod verdicts with a baseline, `check-mod MOD_FOLDER` writes a PASS / REVIEW / FAIL JSON verdict on one mod folder, `scan` lists parse failures with file locations and enabled mods missing from the install (also under Data / Analysis > Diagnostics in the GUI), and `calibration resolve | approve | propose` helps a person finish a calibration review. See the [User Guide](docs/USER_GUIDE.md#automated-checks-source-builds).

## Documentation

- [Documentation index](docs/README.md)
- [User guide](docs/USER_GUIDE.md)
- [Developer guide](docs/DEVELOPER_GUIDE.md)
- [Automation plan](docs/AUTOMATION_PLAN.md)
- [Fleet Support Advisor](docs/FLEET_SUPPORT_ADVISOR.md)
- [Roadmap](ROADMAP.md)

## Contributing and issues

Please read [AGENTS.md](AGENTS.md) and the [developer guide](docs/DEVELOPER_GUIDE.md)
before contributing. Use the issue forms for bugs, mod compatibility, and
recommendation quality. Do not attach game/mod source files, extracted entity
lists, or other third-party content; provide redacted diagnostics instead.

## License and disclaimer

VoidSmith is licensed under the [GNU General Public License v3.0](LICENSE). It is an
unofficial tool and is not affiliated with, endorsed by, or distributed with
Starsector or any mod author.
