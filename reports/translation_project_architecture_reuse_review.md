# Translation Project Architecture Reuse Review

Reviewed read-only: `C:\Users\exxec\Documents\Starsector project go`.
No file in that repository was modified. This review deliberately excludes
translation, AI, text reinjection, OCR, and GUI-specific behavior.

## Executive decision

The highest-value reusable design is a deterministic, read-only **Change
Impact Analyzer**. The Variant Generator already records entity source hashes,
normalizes entity IDs, keeps provenance, and emits audit reports. It lacks the
missing middle layer: classify a new scan against a prior manifest, identify
entity-level changes, traverse known dependencies, and report exactly which
derived results must be recomputed. This should be added before a persistent
analysis cache; the analyzer is independently useful and establishes the cache
invalidation contract without prematurely committing to SQLite.

## Pattern assessment

| Translation-project pattern | Classification | Generator assessment |
|---|---|---|
| Deterministic source/output fingerprints and no-op publication | ADAPT | Source hashes already exist. Add a scan-to-scan entity manifest and impact report, not translation artifact publication. |
| Stable composite extraction keys independent of row order | REUSE_DIRECTLY | Use `(entity_kind, source_mod, entity_id)` as the canonical entity key. Current `Registry` IDs are useful indexes but are not sufficient when mods reuse IDs. |
| Explicit duplicate identity rejection | ADAPT | Emit a conflict finding for duplicate canonical entity keys/source ambiguity; do not reject the whole scan because mod ecosystems can legitimately expose ambiguity. |
| Dependency graph and deterministic cycle reporting | ADAPT | Model scan-derived dependencies only: variant -> hull/weapons/hullmods/fighters; faction -> known entities; hull -> built-ins; knowledge pack -> target faction/mod/hashes. Unknown/scripted references become unresolved edges. |
| Refresh preview with `UNCHANGED/CHANGED/ADDED/REMOVED/CONFLICTED` | REUSE_DIRECTLY | A read-only scan comparison is directly applicable and should precede any cache/write operation. |
| Transactional staged write / dry run | REUSE_DIRECTLY | Existing export already fails closed. New impact analysis remains read-only and reports a proposed recomputation plan; any future cache update must be staged/atomic. |
| Typed provenance and trust preference | ADAPT | Preserve existing source path/hash/mod version, adapter IDs, override/knowledge-pack provenance, and heuristic-set ID. Translation provenance ordering is not applicable. |
| Confidence-aware imported results | ADAPT | Continue current score-vs-confidence separation. An impact report should label invalidation certainty as `EXACT`, `CONSERVATIVE`, or `UNKNOWN_DEPENDENCY`, never turn uncertainty into a cache hit. |
| SQLite translation memory | DEFER | A durable analysis cache is valuable only after impact semantics, schema versioning, and cache lifecycle rules are stable. |
| Text-level fuzzy matching/move suggestions | NOT_APPLICABLE | Entity matching must be exact canonical identity plus source hash. Fuzzy hull/weapon matching would be unsafe. |
| Translation conflict/glossary audits | NOT_APPLICABLE | Domain-specific text consistency is unrelated. The reusable piece is structured, read-only findings only. |
| Out-of-process plugin activation | NOT_APPLICABLE | Generator adapters are pure data/code integrations, not third-party process plugins. Existing adapter isolation is the correct boundary. |

## Proposed Change Impact Analyzer

### Source pattern

`ssmt-project` refreshes into an in-memory candidate, compares stable identities
and fingerprints, produces ordered reconciliation findings, and does not
persist on dry run. Its statuses are `UNCHANGED`, `CHANGED`, `ADDED`,
`REMOVED`, and `CONFLICTED`.

### Starsector problem solved

Today a scan can identify hashes, but it cannot answer: “A weapon changed;
which profiles, variants, hull inference records, factions, reports, and
recommendations are stale?” Full rescans/reanalysis are correct but needlessly
broad for large mod sets and make auditability difficult.

### Architectural fit

Add `analysis/change_impact.py`, operating only on normalized `ScanResult`
snapshots/manifests. It belongs after parsing/registry/provenance and before
analysis-report generation or a future cache. It must not be called from
legality, scoring, or GUI code.

```text
previous entity manifest + current ScanResult
              ↓
  entity reconciliation findings
              ↓
  normalized dependency graph
              ↓
  impacted analysis targets + certainty
              ↓
  read-only JSON/Markdown audit report
```

### Canonical model/interfaces

```text
EntityKey(kind, source_mod_id, entity_id)
ChangeStatus = UNCHANGED | CHANGED | ADDED | REMOVED | CONFLICTED
EntityChange(key, status, previous_hash, current_hash, evidence)
ImpactTarget(kind, key_or_id, certainty, because[])
ChangeImpactReport(schema_version, previous_manifest_hash,
                   current_manifest_hash, changes[], impacts[], warnings[])
```

Known exact edges:

- weapon/hullmod/fighter -> variants that reference it;
- variant -> its hull;
- hull -> variants and factions that know it;
- faction -> faction capability profile, doctrine profile, gap recommendations;
- changed mod source hash -> relevant knowledge-pack freshness and all entities
  from that mod.

Conservative downstream targets:

- affected variants/hulls -> mechanical profile and build-archetype profile;
- affected faction profile -> retrofit candidates and gap recommendations;
- heuristic/adapters/overrides/knowledge-pack changes -> impacted derived
  outputs with explicit non-source provenance causes.

Unknown references never become exact edges; they produce an
`UNKNOWN_DEPENDENCY` warning and conservatively invalidate the nearest owning
analysis target.

### Schema impact

Phase 1 should introduce an additive, versioned manifest/report schema only.
It does **not** change `Hull`, `Weapon`, `Variant`, legality, or recommendation
schemas. A future persistent cache may reference the same manifest hash and
report schema after its own versioned cache contract exists.

### Tests required

- deterministic entity-key ordering and duplicate-key conflict finding;
- every change classification, including removals;
- weapon/hull/hullmod/faction/mod impacts;
- unknown reference produces conservative warning rather than false precision;
- byte-identical report for unchanged inputs;
- no filesystem writes from preview/analyze;
- report schema/version and provenance/heuristic identifiers;
- knowledge-pack source-hash freshness impact.

### Feature-creep assessment

Low for phase 1: it is read-only, uses current scan data, and has no cache,
watcher, GUI, database, or game-source write behavior. Persistent caching,
file watching, incremental parsing, and automatic recomputation are separate
future phases.

## Other targeted adaptations

### Provenance envelope for derived artifacts — ADAPT

Translation reports preserve source identity/provenance. Generator reports
already carry source mod and heuristic set, but a uniform envelope should also
record entity canonical key, entity source hash, adapter IDs, override hash,
knowledge-pack freshness/hash, and analysis schema version. Fit:
`output/analysis_reports.py` and future impact reports. This is additive and
low-risk; test stable serialization and stale-source detection.

### Preview-before-write export consistency — REUSE_DIRECTLY

Translation refresh separates preview from persistence. Generator export is
already legal-only and collision-safe. A future `export --dry-run` can reuse
the existing export plan/manifest generation without writing variants. This is
useful but lower priority than impact analysis because export is already
fail-closed. No schema change; test no output directory mutation.

### Persistent result cache — DEFER

The translation project uses SQLite for durable translation memory. For
generator analysis, a cache should be keyed by the proposed manifest hash,
heuristic-set ID, adapter/override/pack hashes, and analysis schema version.
Implementing it now would risk stale or unexplainable analysis results. Build
it only after the impact analyzer has regression coverage.

## Recommendation

Implement the read-only `ChangeImpactAnalyzer` first, beginning with exact
entity reconciliation and direct scan-reference edges. Emit an audit report
and leave actual selective recomputation/cache reuse deferred. This supplies
the requested flow without falsely claiming incremental computation already
exists:

```text
source file/entity hash change
  -> canonical entity change
  -> dependency graph traversal
  -> selective invalidation plan
  -> auditable report
```
