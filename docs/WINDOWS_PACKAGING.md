# Windows Portable Packaging

Build a self-contained, versioned Windows x64 portable ZIP from the repository
root:

```powershell
.\tools\build_portable_release.ps1
```

Normal release builds are lockfile-only and offline. If the pinned release
dependencies have not yet been materialized on the machine, the command fails
without changing versions or contacting a package index. After reviewing a
lockfile change, materialize that exact graph once with:

```powershell
.\tools\build_portable_release.ps1 -BootstrapDependencies -Clean
```

Ordinary builds reuse PyInstaller's validated dependency-analysis cache when
the existing staging directory is available. `-Clean` removes that staging
directory for a fully fresh build; `-FreshAnalysis` keeps the output target but
forces a fresh PyInstaller analysis. VoidSmith is Python/Qt rather than a C or
C++ project, so native compiler parallelism and `ccache` are not applicable.
The build intentionally collects only the Qt modules imported by the app, not
the full PySide6 distribution.

The result is a directory, ZIP, checksum, and manifest named after the
release version, for example:

```text
dist\VoidSmith-0.1.0-win-x64\
dist\VoidSmith-0.1.0-win-x64.zip
dist\VoidSmith-0.1.0-win-x64.zip.sha256
```

Extract the ZIP and run `VoidSmith.exe` in place. It bundles the generator,
Python runtime, Qt runtime, and required dependencies only. It intentionally
does **not** bundle Starsector, mods, scans, variants, sprites, reports, or
other game/mod data. It requires neither an installer, admin privileges, nor
registry changes; deleting the extracted directory removes it. At first
launch, use **Settings / Export** to select a local Starsector installation;
the application reads that source data without modifying it.

The executable includes a non-interactive, self-closing startup check:

```powershell
.\dist\VoidSmith-0.1.0-win-x64\VoidSmith.exe --smoke-test
```

Or run the release-verification helper, which also prints a SHA-256 digest:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\verify_gui_exe.ps1
```

The portable release build already runs an in-place smoke test and a second
smoke test after extracting the ZIP. It creates `release-manifest.json` inside
the portable directory and a SHA-256 file beside the ZIP. Code signing,
installers, and hosted update channels remain deliberately out of scope.

The repository test remains the deterministic source-level check:

```powershell
uv run python tools/gui_smoke_test.py
```
