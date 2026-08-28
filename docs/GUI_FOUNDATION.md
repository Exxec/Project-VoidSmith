# GUI Foundation Completion Note

Status: functional desktop workflow complete; visual polish remains iterative.

The optional PySide6 entry point is `svg-gui` after installing the optional
extra (`pip install -e .[gui]`). The shell deliberately follows the attached
visual reference only at a design level: a dense dark technical workspace,
top-level navigation, split panes, a central fitting canvas area, and a right
build-inspector surface.

Implemented presentation surfaces:

- Ships, Retrofits, Faction, Data / Analysis, and Settings / Export tabs.
- Ships Browse/Fit/Inspect/Compare sub-tabs.
- Hull filter/browser, technical-grid mount canvas, build-path results,
  inspector, comparison view, and status bar.
- Background read-only scan worker bound to `api.run_scan`; normalized scanned
  hulls populate the browser and its search/size/source-mod filters.
- Parsed slot `locations` render as data-driven canvas anchors (without
  hardcoded per-hull coordinates); settings persist installation/output paths
  and window size through `QSettings`.
- A single GUI fitting state backs the editable slot list and canvas labels.
  Built-in mounts are locked; editable mount choices come from the backend
  compatibility service and each changed fit is validated by the backend.
- An optional dependency boundary: importing backend modules does not require
  PySide6.

Deliberate limits:

- No scan, generation, validation, scoring, or legality logic was copied into
  Qt widgets.
- No Starsector/mod assets are embedded or shipped.
- The canvas does not yet render hull/weapon sprites or callout packing.
  Slot selection currently uses a compact dialog rather than inline callouts.
- Scan, candidate generation, refit/repair actions, faction capability/gap
  analysis, and export are connected to the existing backend service layer.
  Every potentially long-running operation is dispatched through a `QThread`.
- Data / Analysis tables show scanned weapons, hullmods, fighters, and
  variants. Retrofit and faction controls operate on the selected normalized
  entity.

Verification:

- `uv run --with ruff ruff check src/starsector_variant_generator/gui tools/gui_smoke_test.py`
- `uv run --with mypy mypy src/starsector_variant_generator/gui tools/gui_smoke_test.py`
- `uv run python tools/gui_smoke_test.py` (offscreen and self-closing)

Sprite rendering, connector callout packing, richer candidate cards, and
interactive comparison controls are presentation polish. They do not block the
data-driven desktop workflows above.
