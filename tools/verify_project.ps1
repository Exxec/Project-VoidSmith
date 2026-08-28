param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
& $Python -m unittest discover -s tests -q
if ($LASTEXITCODE -ne 0) { throw "Full regression suite failed with exit code $LASTEXITCODE" }
& powershell -ExecutionPolicy Bypass -File tools\verify_gui.ps1 -Python $Python
if ($LASTEXITCODE -ne 0) { throw "GUI verification batch failed with exit code $LASTEXITCODE" }
Write-Host "VoidSmith project verification passed."
