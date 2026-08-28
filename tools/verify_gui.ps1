param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

& $Python -m py_compile src\starsector_variant_generator\gui\app.py src\starsector_variant_generator\gui\main_window.py src\starsector_variant_generator\gui\workers\scan_worker.py
if ($LASTEXITCODE -ne 0) { throw "GUI syntax verification failed with exit code $LASTEXITCODE" }

& $Python -m unittest tests.test_gui_backend_bridge tests.test_gui_canvas tests.test_gui_presentation tests.test_gui_session -v
if ($LASTEXITCODE -ne 0) { throw "GUI unit tests failed with exit code $LASTEXITCODE" }

$env:QT_QPA_PLATFORM = "offscreen"
& $Python tools\gui_smoke_test.py
if ($LASTEXITCODE -ne 0) { throw "GUI offscreen smoke test failed with exit code $LASTEXITCODE" }

Write-Host "GUI verification passed."
