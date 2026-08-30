<#
.SYNOPSIS
Build a self-contained, ZIP-packaged VoidSmith Windows x64 portable release.

.DESCRIPTION
Creates a PyInstaller --onedir application bundle, validates it in place and
after ZIP extraction, writes an inventory manifest plus archive SHA-256, and
never creates an installer, touches the registry, requests elevation, or
collects Starsector/mod data.  All temporary and final files stay below the
repository build/ and dist/ directories.
#>
[CmdletBinding()]
param(
    [string]$Version,
    [string]$OutputDirectory,
    [switch]$Clean,
    [switch]$FreshAnalysis,
    [switch]$SkipArchiveSmoke,
    [switch]$BootstrapDependencies
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:UV_CACHE_DIR = Join-Path $ProjectRoot 'build/uv-cache'

# Normal release builds are deliberately lockfile-only and offline.  This
# prevents a release from silently selecting a newer PySide6/PyInstaller build
# when a cache is incomplete.  The one explicit bootstrap path is reserved for
# a reviewed, permitted materialization of exactly the already-locked graph.
if ($BootstrapDependencies) {
    & uv sync --locked --extra gui --group release
    if ($LASTEXITCODE -ne 0) {
        throw 'Release dependency bootstrap failed. The lockfile was not changed; resolve the materialization failure before building.'
    }
} else {
    & uv sync --locked --offline --extra gui --group release
    if ($LASTEXITCODE -ne 0) {
        throw 'Locked release dependencies are not fully materialized in the local cache/environment. Run this script once with -BootstrapDependencies on an approved network connection; normal releases never resolve online.'
    }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $projectToml = Get-Content -LiteralPath (Join-Path $ProjectRoot 'pyproject.toml') -Raw
    if ($projectToml -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
        throw 'Unable to read the VoidSmith version from pyproject.toml.'
    }
    $Version = $Matches[1]
}
# PEP 440 pre-releases use forms such as ``0.1.25rc1`` (without a separator
# before ``rc``). Keep accepting the existing ``-preview`` naming convention
# as well, while rejecting whitespace/path characters before they reach an
# output path.
if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+([-.]?[A-Za-z0-9.]+)?$') {
    throw "Unsafe release version: $Version"
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $ProjectRoot 'dist'
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$ReleaseName = "VoidSmith-$Version-win-x64"
$ReleaseRoot = Join-Path $OutputDirectory $ReleaseName
$ArchivePath = Join-Path $OutputDirectory "$ReleaseName.zip"
$ChecksumPath = "$ArchivePath.sha256"
$StagingRoot = Join-Path $ProjectRoot 'build/portable-release'
$PyInstallerWork = Join-Path $StagingRoot 'pyinstaller'
$PyInstallerDist = Join-Path $StagingRoot 'dist'
$SmokeRoot = Join-Path $StagingRoot 'archive-smoke'

function Invoke-PortableSmokeTest {
    param([Parameter(Mandatory = $true)][string]$Executable)
    # A windowed PyInstaller executable does not reliably propagate its child
    # process lifecycle through PowerShell's direct invocation. Own the smoke
    # process explicitly so a stuck Qt process cannot retain release DLLs.
    $process = Start-Process -FilePath $Executable -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(30000)) {
        Stop-Process -Id $process.Id -Force
        throw "Portable smoke test timed out after 30 seconds: $Executable"
    }
    if ($process.ExitCode -ne 0) {
        throw "Portable smoke test failed with exit code $($process.ExitCode): $Executable"
    }
}

function New-PortableArchive {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    # Windows may retain a just-loaded Python/Qt DLL or zip briefly after the
    # self-closing smoke process exits. Retry only this local archive operation;
    # source and release contents are never changed to work around a lock.
    $lastError = $null
    foreach ($attempt in 1..8) {
        try {
            if (Test-Path -LiteralPath $Destination) {
                Remove-Item -LiteralPath $Destination -Force
            }
            Compress-Archive -LiteralPath $Source -DestinationPath $Destination -CompressionLevel Optimal
            return
        } catch {
            $lastError = $_
            if ($attempt -eq 8) { break }
            Start-Sleep -Milliseconds (250 * $attempt)
        }
    }
    throw "Unable to archive portable release after 8 attempts: $($lastError.Exception.Message)"
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'Portable Windows x64 releases must be built on a 64-bit Windows system.'
}
& uv run --locked --offline --no-sync --extra gui --group release python -c "import struct, sys; raise SystemExit(0 if struct.calcsize('P') == 8 else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The active Python runtime is not 64-bit; refusing to label the release win-x64.' }

foreach ($target in @($ReleaseRoot, $ArchivePath, $ChecksumPath)) {
    if (Test-Path -LiteralPath $target) {
        if (-not $Clean) { throw "Release target already exists: $target. Re-run with -Clean after reviewing it." }
        $resolved = [IO.Path]::GetFullPath($target)
        $allowed = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'build'))
        $allowedDist = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'dist'))
        if (-not ($resolved.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase) -or $resolved.StartsWith($allowedDist, [StringComparison]::OrdinalIgnoreCase))) {
            throw "Refusing to remove a target outside build/dist: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
if ($Clean -and (Test-Path -LiteralPath $StagingRoot)) {
    $resolvedStaging = [IO.Path]::GetFullPath($StagingRoot)
    $allowedStaging = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'build'))
    if (-not $resolvedStaging.StartsWith($allowedStaging, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove build staging outside build/: $resolvedStaging"
    }
    Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDirectory, $StagingRoot | Out-Null

# PyInstaller's PySide6 hooks collect the imported Qt modules and their runtime
# plugins. Do not use --collect-all: it needlessly pulls in unrelated bindings
# (3D, Bluetooth, ActiveX, etc.), slowing release builds and inflating the ZIP.
$pyInstallerArguments = @(
    '--noconfirm',
    '--onedir',
    '--windowed',
    '--name', 'VoidSmith',
    '--paths', 'src',
    '--hidden-import', 'starsector_variant_generator.gui.main_window',
    '--hidden-import', 'starsector_variant_generator.gui.theme',
    '--distpath', $PyInstallerDist,
    '--workpath', $PyInstallerWork,
    '--specpath', $PyInstallerWork,
    'src/starsector_variant_generator/gui/app.py'
)
# Ordinary locked builds reuse PyInstaller's on-disk analysis cache. The
# cache key includes source/dependency changes; -Clean already removes its
# staging directory, while -FreshAnalysis is available for a deliberate fresh
# analysis without deleting a previously validated release output.
if ($FreshAnalysis) { $pyInstallerArguments = @('--clean') + $pyInstallerArguments }
uv run --locked --offline --no-sync --extra gui --group release pyinstaller @pyInstallerArguments
if ($LASTEXITCODE -ne 0) { throw "PyInstaller portable build failed with exit code $LASTEXITCODE." }

$BuiltApplication = Join-Path $PyInstallerDist 'VoidSmith'
if (-not (Test-Path -LiteralPath (Join-Path $BuiltApplication 'VoidSmith.exe') -PathType Leaf)) {
    throw 'PyInstaller did not produce the expected portable VoidSmith.exe.'
}
Copy-Item -LiteralPath $BuiltApplication -Destination $ReleaseRoot -Recurse
# GPLv3 distributions must carry their license terms. Keep the root notices
# beside the executable so an extracted portable archive remains self-contained.
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'LICENSE') -Destination (Join-Path $ReleaseRoot 'LICENSE')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'NOTICE') -Destination (Join-Path $ReleaseRoot 'NOTICE')

# The GUI only imports PySide6.QtCore/QtGui/QtWidgets and never sets an
# explicit widget style, so the native Windows11 style plugin
# (plugins/styles/qmodernwindowsstyle.dll) is kept. PySide6's QtGui hook
# unconditionally also bundles the platforminputcontexts touch/on-screen
# virtual keyboard input method plugin, whose own binary dependency chain
# (not anything this app calls) is the sole reason Qt6Quick/Qt6Qml/
# Qt6VirtualKeyboard are pulled into the release at all -- confirmed via
# PyInstaller.utils.hooks.qt.add_qt6_dependencies, which returns no
# Quick/Qml/VirtualKeyboard binaries for QtWidgets or QtGui directly.
# Removing the plugin (and its now-orphaned exclusive dependencies) removes
# only the ability to summon an on-screen touch keyboard that this desktop
# mouse/keyboard app never invokes; Qt falls back to normal OS keyboard
# input with no other behavior change. Verified with a real build: the
# portable in-place and post-extraction smoke tests both still pass after
# this prune. Qt's shipped translations (its own dialog/widget strings,
# e.g. qtbase_*.qm) are separately only ever read if application code
# constructs a QTranslator, loads a .qm file, and calls
# QApplication.installTranslator; none of that exists in this app either.
#
# Both prunes are re-checked against the actual source tree on every build
# (rather than assumed to hold forever) because gui/ evolves independently
# of this release script: if a future change adds QtQuick/QML,
# QApplication.installTranslator, or an explicit on-screen-keyboard input
# method, that would silently invalidate this prune, so skip it instead of
# shipping a release with files a newer app build actually needs.
$SourceRoot = Join-Path $ProjectRoot 'src'
$SourcePyFilePaths = (Get-ChildItem -LiteralPath $SourceRoot -Filter '*.py' -Recurse -File).FullName
# Pass the path array directly to -Path (not piped FileInfo objects): with
# multiple piped inputs, -Quiet returns one bool per item instead of a
# single aggregate, and a non-empty *array* of all-$false is itself truthy
# in PowerShell, which would silently make this guard never fire.
$QuickQmlStillUnused = -not (Select-String -Path $SourcePyFilePaths -Pattern 'QtQuick|QtQml|QVirtualKeyboard|setInputMethodHints' -Quiet)
$TranslatorStillUnused = -not (Select-String -Path $SourcePyFilePaths -Pattern 'QTranslator|installTranslator' -Quiet)

if ($QuickQmlStillUnused) {
    $UnusedRuntimeFiles = @(
        'plugins\platforminputcontexts\qtvirtualkeyboardplugin.dll',
        'Qt6VirtualKeyboard.dll',
        'Qt6Quick.dll',
        'Qt6Qml.dll',
        'Qt6QmlMeta.dll',
        'Qt6QmlModels.dll',
        'Qt6QmlWorkerScript.dll'
    ) | ForEach-Object { Join-Path $ReleaseRoot "_internal\PySide6\$_" }
    foreach ($unusedFile in $UnusedRuntimeFiles) {
        if (Test-Path -LiteralPath $unusedFile -PathType Leaf) {
            Remove-Item -LiteralPath $unusedFile -Force
        }
    }
} else {
    Write-Warning 'Source now references QtQuick/QtQml/virtual-keyboard input; skipping the Quick/Qml/VirtualKeyboard size prune so the release keeps what the app actually needs.'
}

if ($TranslatorStillUnused) {
    $UnusedTranslationsDir = Join-Path $ReleaseRoot '_internal\PySide6\translations'
    if (Test-Path -LiteralPath $UnusedTranslationsDir -PathType Container) {
        Remove-Item -LiteralPath $UnusedTranslationsDir -Recurse -Force
    }
} else {
    Write-Warning 'Source now references QTranslator/installTranslator; skipping the Qt translations size prune so the release keeps what the app actually needs.'
}

$PortableReadme = @"
VoidSmith $Version — Portable Windows x64

Run VoidSmith.exe from this directory. No installer, registry changes, admin
rights, Starsector files, mod files, scans, reports, sprites, or third-party
game/mod assets are included. Select your locally installed Starsector path in
Settings when the application starts; source files are read-only.

The release-manifest.json inventories this package. The adjacent ZIP .sha256
file verifies the archive. See LICENSE and NOTICE for distribution terms.
Delete this extracted directory to remove VoidSmith.
"@
Set-Content -LiteralPath (Join-Path $ReleaseRoot 'PORTABLE_README.txt') -Value $PortableReadme -Encoding UTF8

# Verify the directory before archiving.  The offscreen platform is only a
# release-test environment variable; end users launch normally.
$env:QT_QPA_PLATFORM = 'offscreen'
Invoke-PortableSmokeTest (Join-Path $ReleaseRoot 'VoidSmith.exe')

$Inventory = Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -File |
    Where-Object { $_.Name -ne 'release-manifest.json' } |
    Sort-Object FullName |
    ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($ReleaseRoot.Length + 1).Replace('\', '/')
            bytes = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
$Manifest = [ordered]@{
    schema_version = 'voidsmith-portable-release-1'
    product = 'VoidSmith'
    version = $Version
    platform = 'windows-x64'
    packaging = 'portable-zip'
    installer = $false
    admin_required = $false
    registry_changes = $false
    bundled_content = @('VoidSmith application code', 'Python runtime', 'Qt runtime', 'required Python dependencies', 'GPLv3 license', 'NOTICE')
    excluded_content = @('Starsector core data', 'Starsector installation', 'third-party mod assets', 'scans', 'analysis reports', 'sprites', 'mod-specific knowledge packs', 'benchmarks')
    hash_algorithm = 'SHA-256'
    manifest_hash_exclusion = 'release-manifest.json'
    files = @($Inventory)
}
$ManifestPath = Join-Path $ReleaseRoot 'release-manifest.json'
$Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

New-PortableArchive -Source $ReleaseRoot -Destination $ArchivePath
$ArchiveHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $ChecksumPath -Value "$ArchiveHash *$([IO.Path]::GetFileName($ArchivePath))" -Encoding ascii

if (-not $SkipArchiveSmoke) {
    # Archive smoke extraction is disposable staging, unlike PyInstaller's
    # reusable analysis cache. Clear it for every archive verification so a
    # previous extraction cannot cause Expand-Archive to reject valid files.
    if (Test-Path -LiteralPath $SmokeRoot) {
        Remove-Item -LiteralPath $SmokeRoot -Recurse -Force
    }
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $SmokeRoot
    $ExtractedExe = Join-Path $SmokeRoot "$ReleaseName\VoidSmith.exe"
    if (-not (Test-Path -LiteralPath $ExtractedExe -PathType Leaf)) { throw 'Portable ZIP did not retain the expected application layout.' }
    Invoke-PortableSmokeTest $ExtractedExe
}

Write-Host "Portable release built: $ArchivePath"
Write-Host "SHA-256: $ArchiveHash"
