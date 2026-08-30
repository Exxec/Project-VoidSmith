# Ship-by-Ship Calibration Expansion

Generated **171 unique faction-context + ship profiles** from the provisional calibration seed.

This layer adds:

- exact source-mentioned weapons and hullmods per ship;
- source roles/loadouts retained verbatim;
- multiple scenario profiles where the guides support more than one use case;
- scenario-specific preferred weapons/hullmods selected only from items explicitly mentioned for that ship;
- mixed-fleet/acquisition provenance preserved;
- mechanical validation required before activation.

No weapon or hullmod absent from the supplied guides is promoted into `SOURCE_EXPLICIT`.
Scenario assignment is an inference from the guide's role/loadout text, so it remains provisional.

## Profiles by faction/context
- Arma Armatura: 12
- Dassault-Mikoyan Engineering: 10
- Diable Avionics: 14
- HMI: 22
- Hegemony: 25
- Luddic Path: 17
- Pirates: 17
- ScalarTech Solutions: 12
- Sephira Conclave: 12
- Tri-Tachyon Corporation: 16
- United Aurora Federation: 14

## Suggested next pass

For ships where local scan data confirms additional legal equipment, Codex may add `INFERRED_SCENARIO_OPTION` entries based on normalized weapon/hullmod mechanics. Those must remain distinct from source-authored expectations and should carry provenance to the local game/mod files.
