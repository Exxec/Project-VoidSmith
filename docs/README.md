# VoidSmith documentation

These tracked guides describe the public application contract. Historical work
notes, real-install reports, screenshots, and source-derived data remain local
and are intentionally not consolidated into release documentation.

| Guide | Use it for |
| --- | --- |
| [Quick Start](QUICK_START.md) | Installing, launching, and first scan/setup. |
| [User Guide](USER_GUIDE.md) | Workspaces, results, safety boundaries, and limitations. |
| [Fleet Support Advisor](FLEET_SUPPORT_ADVISOR.md) | Locked-fleet recommendations and scenario handoff scope. |
| [Portable packaging](WINDOWS_PACKAGING.md) | Reproducible Windows and Linux release artifacts. |
| [Resource inspection and edit planning](CAMPAIGN_SAVE_RESOURCES.md) | S2 static storage evidence, exact locators, pure plans, refusal rules, the within-capacity write gate and the S3 copy writer. |
| [Campaign inspection format](CAMPAIGN_SAVE_FORMAT.md) | Qualified read-only save inspection, schema, failure behavior and remaining gates. |
| [Save Workshop design](SAVE_WORKSHOP_DESIGN.md) | Plan for minor edits to a save copy; S0-S3 implemented in source, over-capacity writes refused, GUI write control built behind the default-off setting. |
| [Save Workshop implementation plan](SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md) | Module layout, GUI design, build slices and lessons ported from BridgeForge. |
| [Developer Guide](DEVELOPER_GUIDE.md) | Architecture, verification, safe I/O, CI gates and contribution rules. |
| [Automation plan](AUTOMATION_PLAN.md) | The checks that run themselves (validate-all, acceptance, check-mod, scan diagnostics, calibration review) and the status of each item. |
| [Observed bugs](BUGS.md) | Open and resolved compatibility gaps. |
| [Calibration import notes](CALIBRATION_IMPORT_NOTES.md) | Sanitized fixture and calibration-import constraints. |
| [Complex hull acceptance matrix](COMPLEX_HULL_ACCEPTANCE_MATRIX.md) | Acceptance evidence for composite-hull modeling. |

For the current implementation plan and completed boundaries, see the root
[roadmap](../ROADMAP.md). The formal contract documents at the repository root
remain required reading before changing engine behavior.
