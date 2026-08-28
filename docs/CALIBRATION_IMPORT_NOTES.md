# Calibration Import Notes

This package describes how a locally supplied build guide can become a
**provisional calibration seed**.

## Important contract

- All fleet contexts are `MIXED_FLEET_ALLOWED`.
- A ship appearing in a faction guide is **not automatically faction-native**.
- Explicit captured/salvaged foreign hulls are marked `CAPTURED_OR_SALVAGED_FOREIGN` and point toward the `ACQUISITION` recommendation leg.
- Explicit vanilla auxiliaries are marked `VANILLA_AUXILIARY`.
- Explicit faction variants/native declarations are kept where the source text states them.
- Everything else remains `UNSPECIFIED_WITHIN_GUIDE`; local scanned faction/equipment metadata must resolve actual affinity.
- All converted judgments begin as `SOFT_EXPECTATION` and `PROVISIONAL_REVIEW_REQUIRED`.
- These records must never override legality or local mechanical evidence.
- Source SHA-256 hashes are embedded in the JSON so the calibration seed can be bound to the exact guide inputs.

## Contents

Generated seed/review files and raw source guides can carry third-party game or
mod content. They must remain under the gitignored `generated/` tree, not in
this repository. This file records only the generic import contract.

- `generated/calibration/starsector_calibration_seed.provisional.json`: machine-readable calibration seed.
- `generated/calibration/starsector_calibration_review.csv`: flat review sheet for quick human approval/editing.
- `generated/calibration/sources/`: the raw source guide `.txt` files the seed was built from.
- This file: generic import rules only.

## Suggested activation workflow

1. Resolve `ship_display` to scanned internal hull IDs.
2. Validate weapons/hullmods/fighters against the installed mod set.
3. Resolve `UNSPECIFIED_WITHIN_GUIDE` affinity from local faction/equipment metadata.
4. Review the CSV and change approved rows to `APPROVED`.
5. Promote only truly strong reviewer judgments to `HARD_EXPECTATION`.
6. Keep mixed/captured rows eligible for recommendation calibration, but never use them as evidence of native faction ownership.
