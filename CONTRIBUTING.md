# Contributing

## Layout

- `src/starsector_variant_generator/`: application code.
- `tests/`: deterministic tests and small synthetic fixtures.
- `knowledge_packs/`: optional, data-driven faction guidance.
- `tools/`: local developer utilities.
- `docs/`: work logs and supporting documentation.
- Root specification files are canonical project contracts and remain at the
  repository root because `AGENTS.md` requires that reading order.

## Safety

Never modify Starsector core data or installed mod data. Scans are read-only;
all generated reports, exports, logs, and caches belong below the configured
output directory.

## Distribution boundary

Do not commit or package Starsector/mod assets, extracted scan output, real
entity identifiers/lists, mod-specific packs, or copied descriptions. Tests
use neutral synthetic fixtures only. Any benchmark that selects real locally
installed entities belongs in an ignored local manifest and is generated from
the user's installation at run time.

## Verification

Run the complete suite before submitting a behavior change:

```powershell
uv run --no-project --with-editable . python -m unittest discover -s tests -q
```

Changes to heuristics, scoring, parsers, adapters, or output schemas require
matching tests and documentation updates. Legality must remain independent of
all quality and recommendation behavior.
