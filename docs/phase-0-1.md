# Phase 0/1 completion notes

Implemented: package skeleton, TOML configuration, own-directory logging,
normalized models, core/enabled-mod discovery, standard CSV/JSON parsers, a
read-only scan report, and vanilla-style/modded fixtures with unit tests.

Not implemented: validation, legality decisions, classification, doctrine
inference, scoring, candidate generation, or export. Unknown fields are kept
in `raw`; the ingestion layer does not infer their gameplay behavior.

