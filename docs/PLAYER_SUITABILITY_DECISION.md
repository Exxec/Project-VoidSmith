# Player-Suitability Decision Gate

`BuildArchetypeProfile.player_suitability` is currently the compatibility
placeholder `GOOD`. It must not be interpreted as a player-skill assessment,
combat prediction, or promise that a build will perform well in a campaign.

Before changing the field, a maintainer must choose and document:

1. The vocabulary and meaning of each value (for example, static control
   complexity rather than effectiveness).
2. The evidence inputs permitted for each value. Static mechanical maturity
   and documented control assumptions are candidates; inferred player skill,
   runtime combat behavior, and unsourced flavor are not.
3. Whether experimental-maturity builds receive a distinct value.
4. Whether an explicit user override or transcript evidence can supplement the
   static value, with provenance, without changing legality or score.
5. Regression fixtures covering each allowed result and the UI wording that
   makes the advisory limit clear.

Until that decision is made, VoidSmith preserves the existing behavior and
keeps `SVG-023` open. No heuristic set is changed by this planning record.
