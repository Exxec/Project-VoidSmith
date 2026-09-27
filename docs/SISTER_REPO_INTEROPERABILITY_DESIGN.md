# Sister repository interoperability design (2026-09-27)

Status: proposed. VoidSmith remains offline and deterministic. It reads only explicitly selected local evidence and never changes source game/mod files. Distributable fixtures must be neutral and synthetic.

## Release evidence contract (BridgeForge lesson)

VoidSmith already verifies supplied portable archives in `analysis/release_verification.py`. Extend its existing verification model, rather than importing BridgeForge code, to show a source-to-asset chain: commit/tag, clean build input state, toolchain and lock fingerprints, archive filename/size/SHA-256, embedded app version, package inventory, test/native acceptance result, and separately observed downloaded asset hash. Each gate has `PASS`, `FAIL`, `NOT_RUN`, or `UNKNOWN`, evidence path/date, and a limitation. CI or tag existence does not prove publication; a local archive hash does not prove native GUI behavior.

First inventory fields already emitted by `tools/build_portable_release.ps1`, `tools/verify_portable_release.py`, `tools/gui_release_acceptance.py`, and the current verifier. Implement only missing fields, with synthetic manifest fixtures and tampered-asset tests. Exit when one candidate can be traced from exact source to local package and separately downloaded release asset without inferred gate success.

## Optional SPW identity inventory

Accept a versioned SPW inventory file only when explicitly selected. Join its mod records with VoidSmith's native scan using declared ID plus matching root/metadata hash; paths alone never override native identity. Keep duplicate IDs, disabled metadata rename, stale enabled lists, missing metadata, and changed-install fingerprints as `UNKNOWN` or conflicts. The inventory may add provenance and context; it may not establish fit legality, scripted effects, or recommendation quality. When absent or incompatible, existing scans work unchanged.

Use neutral synthetic fixture pairs for exact match, duplicate ID, stale/disabled entry, missing metadata, and hash mismatch. Exit when matching inventory augments evidence and every ambiguous case leaves the recommendation unchanged with an explicit reason.
