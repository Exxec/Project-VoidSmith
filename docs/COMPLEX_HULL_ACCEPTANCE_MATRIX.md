# Complex Hull Acceptance Matrix

This matrix defines the current acceptance boundary for multipart ships,
stations, and module-heavy content. It prevents a locally parseable module from
being misrepresented as a fully modeled composite hull. Unknown behavior is
preserved rather than simulated.

| Feature | Current acceptance | Current behavior | Generation / recommendation policy |
|---|---|---|---|
| `MULTIPART_PARENT_CHILD` | `STRUCTURAL_PROFILE` | Declared parent-slot to child-variant records are normalized. | Never claim composite validation. |
| `REPEATED_MODULES` | `STRUCTURAL_PROFILE` | Repeated child mappings remain distinct parent-slot records. | No aggregate score/recommendation. |
| `ASYMMETRIC_MODULES` | `STRUCTURAL_PROFILE` | Distinct child mappings are recorded as structural asymmetry only. | No aggregate score/recommendation. |
| `INDEPENDENT_SHIELDS` | `NOT_DETERMINABLE` | Only the inspected hull's parsed shield fields are known. | No composite tank conclusion. |
| `MODULE_LOCAL_WEAPONS` | `PARSED_SEPARATELY` | A module hull's documented mounts may be parsed/validated for that module only. | Local fitting only; never merge with parent. |
| `MODULE_LOCAL_SYSTEMS` | `PROVENANCE_ONLY` | System IDs may be retained as raw evidence. | No system-effect scoring without an adapter. |
| `DESTROYABLE_SECTIONS` | `NOT_DETERMINABLE` | Health/destruction semantics are not modeled. | No survivability aggregation. |
| `STATION_STYLE_MODULES` | `STRUCTURAL_PROFILE` | `STATION` hints remain on the structural profile. | No station composite generation. |
| `DETACHABLE_COMPONENTS` | `NOT_DETERMINABLE` | Detachment/post-detachment state is not modeled. | No mobility/survivability conclusion. |
| `SCRIPTED_MODULE_BEHAVIOR` | `UNKNOWN_SCRIPTED_EFFECT` | Scripts are never executed; unrecognized behavior remains explicit. | `NOT_DETERMINABLE` whenever it affects legality/score. |

## Acceptance requirements for a future composite implementation

The scanner now normalizes an auditable structural parent-slot/child-variant
profile, source references, multiplicity, and basic asymmetry. Before a
complex parent can receive a composite recommendation, it must additionally
model local mounts/systems/shields and destruction/detachment semantics where
those facts are parseable. Every aggregate output must retain per-module
provenance and return `NOT_DETERMINABLE` when an unknown scripted portion is
material.

## Batch audit

`tools/audit_complex_hulls.py` performs two read-only checks against a selected
installation: its enabled loadout and all installed mods (including disabled
ones). It writes only compact local diagnostics below the configured output
directory:

```text
reports/complex_hull_acceptance_enabled.json
reports/complex_hull_acceptance_all_installed.json
```

The audit checks structural hints, non-empty variant module mappings,
ambiguous parents, unresolved child variants/hulls, repeated mappings, and the
normalized structural profile. It does not execute scripts, choose between
duplicate IDs, or merge module weapons/systems/shields into a parent.

An audit warning is an explicit source-data/provenance limitation, not a
legality failure. It means the relevant composite behavior remains outside the
current acceptance boundary.
