#!/usr/bin/env bash
# Build a self-contained, native Linux x64 VoidSmith archive.  Run this on a
# Linux host/runner only; cross-building a PySide6/PyInstaller bundle from
# Windows would not provide a meaningful runtime smoke test.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

bootstrap_dependencies=false
clean=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --bootstrap-dependencies) bootstrap_dependencies=true ;;
        --clean) clean=true ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

if [[ "$bootstrap_dependencies" == true ]]; then
    uv sync --locked --extra gui --group release
else
    uv sync --locked --offline --extra gui --group release
fi

version="$(uv run --locked --offline --no-sync python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version])')"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-]?[A-Za-z0-9.]+)?$ ]]; then
    echo "Unsafe release version: $version" >&2
    exit 2
fi

release_name="VoidSmith-${version}-linux-x64"
release_root="$project_root/dist/$release_name"
archive_path="$project_root/dist/$release_name.tar.gz"
checksum_path="$archive_path.sha256"
staging_root="$project_root/build/portable-release-linux"
pyinstaller_dist="$staging_root/dist"
pyinstaller_work="$staging_root/pyinstaller"
smoke_root="$staging_root/archive-smoke"

for target in "$release_root" "$archive_path" "$checksum_path"; do
    if [[ -e "$target" ]]; then
        if [[ "$clean" != true ]]; then
            echo "Release target already exists: $target (rerun with --clean after review)" >&2
            exit 1
        fi
        rm -rf -- "$target"
    fi
done
if [[ "$clean" == true ]]; then
    rm -rf -- "$staging_root"
fi
mkdir -p "$project_root/dist" "$staging_root"

uv run --locked --offline --no-sync --extra gui --group release pyinstaller \
    --noconfirm --clean --onedir --windowed --name VoidSmith --paths src \
    --hidden-import starsector_variant_generator.gui.main_window \
    --hidden-import starsector_variant_generator.gui.theme \
    --distpath "$pyinstaller_dist" --workpath "$pyinstaller_work" \
    --specpath "$pyinstaller_work" src/starsector_variant_generator/gui/app.py

if [[ ! -x "$pyinstaller_dist/VoidSmith/VoidSmith" ]]; then
    echo "PyInstaller did not produce the expected Linux executable." >&2
    exit 1
fi
cp -a "$pyinstaller_dist/VoidSmith" "$release_root"
# GPLv3 distributions must carry their license terms. Keep the notices beside
# the executable so an extracted portable archive remains self-contained.
cp "$project_root/LICENSE" "$release_root/LICENSE"
cp "$project_root/NOTICE" "$release_root/NOTICE"

cat > "$release_root/PORTABLE_README.txt" <<EOF
VoidSmith $version - Portable Linux x64

Run ./VoidSmith from this directory. This bundle contains only VoidSmith,
Python, Qt, and required dependencies. It does not contain Starsector, mods,
scans, reports, sprites, knowledge packs, or any third-party game data.

The release-manifest.json inventories this package. The adjacent .sha256 file
verifies the archive. See LICENSE and NOTICE for distribution terms. Delete
this extracted directory to remove VoidSmith.
EOF

QT_QPA_PLATFORM=offscreen "$release_root/VoidSmith" --smoke-test

python - "$release_root" "$version" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name != "release-manifest.json":
        files.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
(root / "release-manifest.json").write_text(json.dumps({
    "schema_version": "voidsmith-portable-release-1",
    "product": "VoidSmith",
    "version": sys.argv[2],
    "platform": "linux-x64",
    "packaging": "portable-tar-gz",
    "installer": False,
    "bundled_content": ["VoidSmith application code", "Python runtime", "Qt runtime", "required Python dependencies", "GPLv3 license", "NOTICE"],
    "excluded_content": ["Starsector core data", "Starsector installation", "third-party mod assets", "scans", "analysis reports", "sprites", "mod-specific knowledge packs", "benchmarks"],
    "hash_algorithm": "SHA-256",
    "manifest_hash_exclusion": "release-manifest.json",
    "files": files,
}, indent=2), encoding="utf-8")
PY

tar -C "$project_root/dist" -czf "$archive_path" "$release_name"
sha256sum "$archive_path" > "$checksum_path"
mkdir -p "$smoke_root"
tar -C "$smoke_root" -xzf "$archive_path"
QT_QPA_PLATFORM=offscreen "$smoke_root/$release_name/VoidSmith" --smoke-test

echo "Portable Linux release built: $archive_path"
cat "$checksum_path"
