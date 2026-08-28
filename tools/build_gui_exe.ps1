<#!
.SYNOPSIS
Build the self-contained Windows desktop executable.

.DESCRIPTION
Packages only the generator application and its Python/Qt runtime.  It does
not collect a Starsector installation, enabled mods, scan outputs, or any
other game/mod source data.  Those remain user-selected read-only inputs at
runtime.
#>
[CmdletBinding()]
param(
    [switch]$FreshAnalysis,
    [switch]$BootstrapDependencies,
    [switch]$NoVersionBump
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
# Keep transient resolver artifacts inside the project.  This avoids relying
# on a user-profile cache that may be locked while retaining a fully local,
# reproducible build workflow.
$env:UV_CACHE_DIR = Join-Path $ProjectRoot 'build/uv-cache'

# Bumps pyproject.toml's patch version and keeps uv.lock's own recorded
# version for the local editable `voidsmith` package in exact sync with it
# -- `uv sync --locked` refuses to proceed once they diverge (discovered
# building 0.1.1; see docs/WORK_LOG.md). Writes with .NET's UTF8Encoding
# ($false = no BOM) rather than Set-Content, since Windows PowerShell 5.1's
# -Encoding utf8 always adds a BOM neither file originally has.
function Step-PatchVersion {
    param([string]$ProjectRoot)

    $pyprojectPath = Join-Path $ProjectRoot 'pyproject.toml'
    $lockPath = Join-Path $ProjectRoot 'uv.lock'
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    $pyproject = [System.IO.File]::ReadAllText($pyprojectPath)
    $match = [regex]::Match($pyproject, '(?m)^version = "(\d+)\.(\d+)\.(\d+)"')
    if (-not $match.Success) {
        throw "Could not find a 'version = ""X.Y.Z""' line in pyproject.toml to bump."
    }
    $major = [int]$match.Groups[1].Value; $minor = [int]$match.Groups[2].Value; $patch = [int]$match.Groups[3].Value
    $oldVersion = "$major.$minor.$patch"
    $newVersion = "$major.$minor.$($patch + 1)"
    $newPyproject = $pyproject.Substring(0, $match.Index) + "version = ""$newVersion""" + $pyproject.Substring($match.Index + $match.Length)
    [System.IO.File]::WriteAllText($pyprojectPath, $newPyproject, $utf8NoBom)

    $lock = [System.IO.File]::ReadAllText($lockPath)
    $lockMatch = [regex]::Match($lock, '(?ms)name = "voidsmith"\r?\nversion = "(\d+\.\d+\.\d+)"')
    if (-not $lockMatch.Success) {
        throw 'Could not find voidsmith''s package entry in uv.lock to keep in sync with pyproject.toml.'
    }
    $versionGroup = $lockMatch.Groups[1]
    $newLock = $lock.Substring(0, $versionGroup.Index) + $newVersion + $lock.Substring($versionGroup.Index + $versionGroup.Length)
    [System.IO.File]::WriteAllText($lockPath, $newLock, $utf8NoBom)

    Write-Host "Bumped version: $oldVersion -> $newVersion (pyproject.toml + uv.lock)"
    return $newVersion
}

$BuiltVersion = $null
if (-not $NoVersionBump) {
    $BuiltVersion = Step-PatchVersion -ProjectRoot $ProjectRoot
}

function Get-ProjectVersion {
    param([string]$ProjectRoot)
    $projectToml = [System.IO.File]::ReadAllText((Join-Path $ProjectRoot 'pyproject.toml'))
    $match = [regex]::Match($projectToml, '(?m)^version\s*=\s*"([^"]+)"')
    if (-not $match.Success) { throw 'Could not read the current project version from pyproject.toml.' }
    return $match.Groups[1].Value
}

function Get-AvailableArtifactPath {
    param([string]$Directory, [string]$Version)
    $candidate = Join-Path $Directory "VoidSmith-$Version.exe"
    $suffix = 1
    while (Test-Path -LiteralPath $candidate) {
        $candidate = Join-Path $Directory "VoidSmith-$Version-rebuild$suffix.exe"
        $suffix += 1
    }
    return $candidate
}

$ArtifactVersion = if ($BuiltVersion) { $BuiltVersion } else { Get-ProjectVersion -ProjectRoot $ProjectRoot }
$StagedDist = Join-Path $ProjectRoot 'build/onefile-dist'

# Locked and offline, matching tools/build_portable_release.ps1's own
# discipline: this quick one-file build previously used `uv run --with
# pyinstaller`, which resolves PyInstaller from the network on every run and
# can silently pick a different, unpinned version than the `6.22.2` the real
# release pipeline locks in `uv.lock`. `-BootstrapDependencies` is the one
# explicit, reviewed path that's allowed to touch the network.
if ($BootstrapDependencies) {
    & uv sync --locked --no-build-isolation --extra gui --group release
    if ($LASTEXITCODE -ne 0) {
        throw 'Dependency bootstrap failed. The lockfile was not changed; resolve the materialization failure before building.'
    }
} else {
    & uv sync --locked --offline --no-build-isolation --extra gui --group release
    if ($LASTEXITCODE -ne 0) {
        throw 'Locked build dependencies are not fully materialized in the local cache/environment. Run this script once with -BootstrapDependencies on an approved network connection; normal builds never resolve online.'
    }
}

# The PySide6 hook follows the application's imported Qt modules and deploys
# their required plugins. Collecting all of PySide6 pulls unrelated bindings.
$pyInstallerArguments = @(
    '--noconfirm',
    '--onefile',
    '--windowed',
    # Never make PyInstaller overwrite the executable a user may currently
    # have open. It writes a disposable staging artifact; publication below
    # always creates a fresh versioned file in dist/.
    '--name', 'VoidSmith-build',
    '--paths', 'src',
    '--hidden-import', 'starsector_variant_generator.gui.main_window',
    '--hidden-import', 'starsector_variant_generator.gui.theme',
    '--distpath', $StagedDist,
    '--workpath', 'build/pyinstaller',
    '--specpath', 'build/pyinstaller',
    'src/starsector_variant_generator/gui/app.py'
)
if ($FreshAnalysis) { $pyInstallerArguments = @('--clean') + $pyInstallerArguments }
uv run --locked --offline --no-sync --extra gui --group release pyinstaller @pyInstallerArguments

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

$StagedExecutable = Join-Path $StagedDist 'VoidSmith-build.exe'
if (-not (Test-Path -LiteralPath $StagedExecutable -PathType Leaf)) {
    throw "PyInstaller did not produce the expected staged executable: $StagedExecutable"
}
$DistDirectory = Join-Path $ProjectRoot 'dist'
New-Item -ItemType Directory -Path $DistDirectory -Force | Out-Null
$VersionedArtifact = Get-AvailableArtifactPath -Directory $DistDirectory -Version $ArtifactVersion
Copy-Item -LiteralPath $StagedExecutable -Destination $VersionedArtifact

# Preserve the familiar dist/VoidSmith.exe path when it is not in use. A
# running Windows executable may be locked; that must not make a successful
# rebuild fail or cause the currently-running app to be disturbed.
$LegacyArtifact = Join-Path $DistDirectory 'VoidSmith.exe'
try {
    Copy-Item -LiteralPath $StagedExecutable -Destination $LegacyArtifact -Force
    Write-Host "Updated latest executable: $LegacyArtifact"
} catch {
    Write-Warning "Could not replace locked latest executable '$LegacyArtifact'. New build is available at '$VersionedArtifact'. Close the running app and rebuild later to refresh the legacy path."
}

if ($BuiltVersion) {
    Write-Host "Built: $VersionedArtifact (v$BuiltVersion)"
} else {
    Write-Host "Built: $VersionedArtifact"
}
