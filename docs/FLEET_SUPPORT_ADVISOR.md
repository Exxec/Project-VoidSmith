# Fleet Support Advisor

The Fleet Support Advisor answers: **given ships the player has deliberately
selected, which single additional hulls could complement them?** It is not a
whole-fleet optimizer.

## Contract

- Input is one or more `FleetSelection` records. Every resolved selection is
  locked; selected hulls are excluded from recommendations and never replaced.
- Output is a `PlayerFleetProfile`, identified `FleetSupportNeed` records,
  and a short ranked list of individual `FleetSupportRecommendation` records.
- It never recommends quantities, a complete composition, deployment-point
  allocation, campaign inventory, procurement, or save-state changes.
- It ranks structural hull candidates only. Every result states
  `NOT_EVALUATED_NO_CONCRETE_FIT`: hard fit legality belongs to validation once
  a concrete variant exists.

## Evidence and limits

The profile aggregates already normalized capability vectors and six-axis
combat doctrine. Capability aggregation reports the best selected-hull
coverage for each dimension; it does not claim that several ships combine into
a combat outcome. Candidate scoring combines declared support-need coverage,
doctrine cohesion, access affinity, and only static speed/position/tempo
friction.

Range matching, sensor profile, strategic burn, fleet deployment cost,
formation conflict, phase behavior, and fleet-wide logistics are explicitly
unknown rather than scored. `FleetCompatibilityProfile` and `FleetFriction`
preserve those unavailable fields and notes for the presentation layer.
When both sides have resolved existing-variant weapons, range cohesion is
reported from their mean mounted range; it is evidence about observed fits,
not a prediction of a future candidate build.
Static base `max_burn` is separately reported as a cohesion/friction signal
when every needed hull exposes it. This is not a claim about hullmod-modified
or campaign-specific fleet burn behavior.
Consequently, the `STEALTH` focus currently returns no fabricated support need
until normalized sensor or phase-signature evidence exists.

## Access and explanations

`STRICT_FACTION`, `FACTION_PLUS`, and `UNRESTRICTED` are supported. Access is
policy, separate from hull recommendation eligibility and fit legality.
Source-mod provenance never creates faction ownership: an unlisted hull remains
`UNALIGNED` and strict access excludes it.

Each recommendation distinguishes `SYNERGY`, `GAP_FILL`, or both, lists the
capabilities it supports, preserves score separately from confidence, and
records static friction. Candidate exclusions retain reasons, including locked
selection, structural ineligibility, and access-policy exclusion. When no
eligible candidate provides material evidence for a detected need, it appears
in `unaddressed_support_needs`; the advisor does not pad its shortlist.
`category_shortlists` exposes the same eligible ranked evidence separately as
combat and logistics support, so a hybrid candidate can be understood in both
contexts without creating a second candidate pool or scoring formula.

`FleetSupportWhyNotExplanation` uses the advisor's same full ranking path, not
a second scoring pass. It distinguishes an unresolved hull, pre-ranking
exclusion, no material match, a shortlisted recommendation, and a candidate
ranked below the shortlist cutoff.

When `baseline_0.13` or later is selected, a shortlist additionally favors a distinct
inferred mechanical family only among materially score-competitive candidates.

## Composition synergy

`baseline_0.14` adds a separately reported composition-synergy component. It
is neither a support need nor doctrine cohesion. Counted locked selections
produce evidence-gated traits such as direct phase prevalence, normalized
static sensor-profile availability, base-burn compatibility, mobility
character, carrier/missile orientation, battlefield posture, and civilian
prevalence. Only available direct or normalized evidence contributes; missing
evidence is ignored rather than treated as mismatch.

This allows a logistics candidate to be preferred for preserving an already
observed phase-oriented composition without claiming phase support is a fleet
gap. The advisor still does not infer runtime phase mechanics, fleet-wide
sensor behavior, hullmod-modified burn, deployment points, quantities, or a
concrete candidate fit.

Each ranked recommendation exposes named score components (`support_need_coverage`,
`doctrine_cohesion`, `composition_synergy`, `static_friction`, and
`access_affinity`) and purpose labels such as `LINE_ANCHOR`, `PD_SCREEN`,
`ARMOR_BREAKER`, `CARGO_SUPPORT`, and `FUEL_SUPPORT`. Why-Not presents these
same backend-produced components; it does not recalculate scores in the GUI.

## Generate Support Fit

After the user selects a currently shortlisted candidate, **Generate Support
Fit** reruns the advisor's exact current ranking path and then invokes the
normal bounded generator with a purpose-to-existing-profile mapping. The
returned variants, rather than the original advisory card, carry ordinary
validation results. The action writes nothing. Logistics-only purposes remain
explicitly unavailable because the generator does not yet model a dedicated
logistics fit profile; VoidSmith will not substitute an unrelated combat role.

## Roadmap relationship

Fleet Support remains a per-addition advisor. Its next dependency is the
Scenario / Mission Advisor's portable scenario request and explicit
scenario-fit handoff; neither permits whole-fleet quantity/replacement
selection. Read the root [`ROADMAP.md`](../ROADMAP.md) for the current ordered
plan and its read-only campaign-save/DP/officer boundaries.

Scenario Advisor requests use a separate portable JSON schema containing only
user-declared locked selections, capability targets, pressures, and access
constraints. It never serializes a scan, registry, game/mod source facts, or a
battle prediction.
The recommendation retains its mechanical-archetype evidence, shortlist order,
and diversity reason; Why-Not uses that same selection result.

## Heuristics

`baseline_0.12` adds the named Fleet Support Advisor thresholds, shortlist cap,
and complement/cohesion/friction weights. Earlier heuristic sets remain
compatible through conservative documented fallback values; the advisor never
uses heuristic values for legality.
`baseline_0.13` adds an explicitly enabled, score-bounded diversity selector.
`baseline_0.14` adds score-bounded composition preservation and access-affinity
weights, retaining all previous components as separately inspectable evidence.
The desktop advisor defaults to baseline 0.14 and exposes all three advisor
baselines separately from global fitting defaults.

## CLI

```text
voidsmith fleet-support <locked-hull-id> [<locked-hull-id> ...]
  --faction-id <id> --access-mode FACTION_PLUS --focus BALANCED
  --starsector-path <path> --output-dir <path>
```

Repeating a hull ID records another selected instance; it still does not turn
the advisor into a quantity optimizer.
For convenience, CLI and desktop entries also accept `hull_id*count` (for
example `afflictor*2`); this records a locked selection count only.
`variant:<variant_id>*count` is also accepted. A resolved variant contributes
its own mounted-weapon range evidence while still retaining hard fit legality
as a separate validation concern.

The Faction workspace formats backend results as compact support cards; it
does not derive scores, support needs, or legality independently.
It also accepts an optional candidate hull ID and displays the backend's exact
Fleet Support Why-Not record.
Returned additions are rendered as selectable cards; selecting one fills the
candidate field for the same backend Why-Not operation.
The Ships inspector can add the currently selected hull directly to the locked
selection field; repeating this action intentionally records another selected
instance without choosing a recommendation quantity.
The desktop app persists these local advisor inputs (locked IDs, optional
candidate ID, focus, access, and availability flags) in its own preferences;
it never reads a campaign save or inventory.
Its Clear action removes the local locked/candidate text fields so a new fleet
concept can be entered safely.

```text
voidsmith fleet-support-why-not <candidate-hull-id> <locked-hull-id> [...]
  --faction-id <id> --access-mode FACTION_PLUS --focus BALANCED
  --starsector-path <path> --output-dir <path>
```
