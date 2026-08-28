<#!
.SYNOPSIS
Verify a locally built GUI executable without opening an interactive window.
#>
[CmdletBinding()]
param([string]$Executable)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Executable)) {
    $ProjectRoot = if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { (Get-Location).Path } else { Split-Path -Parent $PSScriptRoot }
    $Executable = Join-Path $ProjectRoot 'dist\VoidSmith.exe'
}
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Executable not found: $Executable"
}

& $Executable --smoke-test
if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "GUI smoke test failed with exit code $LASTEXITCODE"
}

$artifact = Get-Item -LiteralPath $Executable
$hash = Get-FileHash -LiteralPath $Executable -Algorithm SHA256
Write-Host "Verified: $($artifact.FullName)"
Write-Host "Bytes: $($artifact.Length)"
Write-Host "SHA-256: $($hash.Hash)"
