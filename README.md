# VoidSmith

VoidSmith is an offline, deterministic desktop tool for read-only Starsector
ship fitting, variant inspection, and faction-capability analysis.

**Current pre-release:** [v0.1.25rc1](https://github.com/Exxec/Project-VoidSmith/releases/tag/v0.1.25rc1) · [All releases](https://github.com/Exxec/Project-VoidSmith/releases)

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

For a source checkout, install Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --extra gui
uv run voidsmith-gui
```

See the [Quick Start](docs/QUICK_START.md) for setup and the
[packaging guide](docs/WINDOWS_PACKAGING.md) for local portable builds.

## Safety and scope

VoidSmith reads game and mod sources as untrusted, read-only input. It does not
overwrite source variants, alter Starsector files, execute mod scripts, or
bundle Starsector/mod data in this repository or its packages. Unknown or
scripted mechanics remain explicit rather than guessed.

It is not a combat simulator, whole-fleet optimizer, save-state planner, or
market/inventory availability tool. Legality, quality, confidence, and warnings
are deliberately separate.

## Documentation

- [Documentation index](docs/README.md)
- [User guide](docs/USER_GUIDE.md)
- [Developer guide](docs/DEVELOPER_GUIDE.md)
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
