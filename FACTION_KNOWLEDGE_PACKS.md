# FACTION_KNOWLEDGE_PACKS.md
# Faction Doctrine, Capability Analysis, Retrofit Packs, and Recommendations
Version 0.5

## 1. Purpose

This subsystem lets the application automatically analyze a faction from
installed mod data, then optionally enrich that analysis with curated faction
knowledge.

It should answer:
- What is this faction good at?
- Where is it weak?
- What roles are genuinely missing?
- Which native hulls solve those roles?
- Which hulls can be retrofitted?
- Which installed foreign hulls are worth acquiring?
- Which 3-5 options are actually recommended?
- Why was another ship not recommended?

Knowledge packs improve thematic intelligence but are optional.

### Equipment approvals

A pack may list `approved_equipment` entries (`id`, `kind`, `confidence`,
optional provenance).  They classify an otherwise non-native resolved item as
`APPROVED` for the pack's target faction.  Strict Faction generation may then
consider it; Faction+ treats it as preferred.  This is advisory access policy,
never a legality exception.  Stale packs still provide advisory approvals, but
their stated confidence is reduced (CURRENT 1.0, PARTIALLY_STALE 0.75, STALE
0.5) wherever recommendation/substitution confidence is reported.

## 2. Automatic Analysis First

With no pack installed, scan:
- faction hull lists
- faction weapon lists
- fighter lists
- existing variants
- hull stats
- mount layouts
- armor/shield/flux/mobility
- fighter bays
- built-ins
- known hullmod effects
- known ship-system behavior
- role classifications

Never execute mod scripts.

Unknown scripted behavior reduces confidence.

## 3. Capability Profile

Initial dimensions:
- armor
- shields
- ballistic
- energy
- missile
- carrier
- phase
- mobility
- long range
- brawling
- skirmishing
- PD
- logistics
- salvage
- survey

Classify as:
- STRONG
- ADEQUATE
- WEAK
- GAP

Do not use one scalar alone to declare a gap. Consider quality and role coverage.

## 4. Recommendation Classes

### NATIVE
Faction-owned hull in a natural role.

### RETROFIT
Existing hull moved toward a secondary but mechanically sensible role.

### ACQUISITION
Installed foreign hull recommended to fill a real capability gap.

## 5. "I Recommend These"

For each gap, return a concise shortlist.

Default:
- 3 recommendations
- expandable to 5 or more

Example:

```text
Gap: Long-range energy support

Native:
No strong native solution.

Retrofit:
Junk Long-Range Support
Score 68
Confidence Medium

Acquisition:
Paragon
Score 94
Confidence High

Champion
Score 87
Confidence High
```

## 6. Score vs Confidence

Recommendation score = how good it appears.

Confidence = how much reliable evidence exists.

Confidence sources:
- direct mechanics
- existing variants
- adapter coverage
- current knowledge pack
- overrides
- unknown scripted mechanics

Do not merge these into one opaque number.

## 7. Diversity

A top-N list should not be five copies of the same solution family.

Prefer meaningful alternatives when competitive:
- maximum capability
- lower-cost/practical
- mobility-oriented
- durability-oriented
- thematic
- native retrofit
- foreign acquisition

Do not promote bad candidates just for variety.

## 8. Why Not?

Any eligible candidate should support:

**Why wasn't this recommended?**

Return:
- score
- confidence
- largest strengths
- largest penalties
- exclusion reason if any
- shortlist cutoff context

## 9. Doctrine Strictness

### LOOSE
Mechanics dominate.

### BALANCED
Mechanics and faction identity both matter.

### STRICT
Strongly prefer faction-authentic solutions. Foreign acquisitions normally need
a clear capability advantage.

## 10. Lightweight User Constraints

Use a few simple controls:
- Allow foreign hulls
- Allow hidden/secret hulls
- AI / Player / Either
- Experimental retrofits
- Doctrine strictness
- Optional campaign stage

No full fleet questionnaire.

## 11. Knowledge Pack Structure

Suggested:

```text
knowledge_packs/
    schema/
        faction_pack.schema.json
    bundled/
        vanilla/
    user/
        hmi/
            manifest.json
            faction.json
            hulls.json
            retrofit_rules.json
            progression.json
            officers.json
            notes.md
```

## 12. Pack Freshness

Record:
- schema version
- target faction
- target mod
- target mod version
- source hashes
- authored date
- authorship method

Status:
- CURRENT
- PARTIALLY_STALE
- STALE
- INCOMPATIBLE

Stale guidance remains advisory only and lowers confidence.

## 13. Review-to-Pack Workflow

A human or AI-assisted review can be converted into a pack:

```text
scan current mod
  -> automatic faction profile
  -> review mod/guide/documentation
  -> produce structured pack
  -> validate schema
  -> validate recommendations against current mechanics
  -> reject illegal advice
```

AI-written guide content is CURATED_GUIDANCE, not game truth.

## 14. Retrofit Before Acquisition

Before recommending foreign hulls:
1. search native solutions
2. search native retrofit solutions
3. evaluate whether those meet the gap adequately
4. only then elevate acquisitions

## 15. Progression Guidance

A pack may define user-selected stages such as:
- EARLY
- MID
- LATE
- ENDGAME

Do not infer save-state or wealth in current scope.

## 16. GUI Workspace

Faction-related features belong primarily in the **Faction** top-level tab.

Sub-tabs/panels:
- Overview
- Capability Gaps
- Recommendations
- Knowledge Pack
- Progression
- Doctrine Evidence

Retrofit templates themselves belong in the **Retrofits** top-level tab, with
cross-links from Faction recommendations.

## 17. Out of Scope

Do not optimize:
- exact fleet composition
- quantity of each hull
- current inventory
- market procurement
- save-state availability
- fleet-wide logistics totals
