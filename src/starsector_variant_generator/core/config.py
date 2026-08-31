from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

# The single source of truth for "what heuristic set applies when nothing
# more specific was configured" -- every front end (CLI config loading, the
# GUI's per-action fallback when self._config is None) should reference this
# constant rather than repeating the literal "baseline_0.7" string. Must
# name a real, registered identifier in core/heuristics.py::REGISTRY.
DEFAULT_HEURISTIC_SET = "baseline_0.7"


@dataclass(frozen=True)
class AppConfig:
    starsector_path: Path
    output_dir: Path
    log_dir: Path
    heuristic_set: str = DEFAULT_HEURISTIC_SET
    # Mod directories scanned in addition to the normal core + enabled-mods
    # set (e.g. a drag-and-dropped mod folder or extracted archive that
    # isn't installed under `starsector_path/mods/` at all). Always treated
    # as enabled; see `core/scanner.py::Scanner.extra_mod_paths`.
    extra_mod_paths: tuple[Path, ...] = ()
    # Scan every mod physically present under `starsector_path/mods/`, not
    # just the ones listed in Starsector's own `enabled_mods.json` -- see
    # `api.py::run_scan`'s `include_disabled_mods` parameter, which this
    # forwards to.
    include_disabled_mods: bool = False

    @classmethod
    def from_toml(cls, path: Path) -> AppConfig:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        root = path.parent
        return cls(
            starsector_path=Path(data["starsector_path"]).expanduser(),
            output_dir=(root / data.get("output_dir", "generated")).resolve(),
            log_dir=(root / data.get("log_dir", "generated/logs")).resolve(),
            heuristic_set=data.get("heuristic_set", DEFAULT_HEURISTIC_SET),
        )
