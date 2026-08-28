# Role profile catalog

Profiles are deterministic quality intents. They do not establish any game legality and are never consulted by validation.

| ID | Intent | Current scope |
|---|---|---|
| `LINE_BRAWLER` | Favor low-OP weapon packages and short-range role fit. | Weapons + up to 2 evidence-bound hullmods + vents/capacitors. |
| `LINE_ARTILLERY` | Favor longer-range weapon packages. | Weapons + up to 2 evidence-bound hullmods + vents/capacitors. |
| `FAST_STRIKE` | Favor compact, low-OP weapon packages. | Weapons + up to 2 evidence-bound hullmods + vents/capacitors. |
| `TANK` | Same conservative low-OP weapon policy as Line Brawler, but hullmod selection prefers the hull's own "Defenses"-tagged options first. | Weapons + hullmods (category-prioritized) + vents/capacitors. |
| `PD_ESCORT` | Prefers weapons `classify_weapon` already tags "PD" for each mount, falling back to the conservative low-OP policy otherwise. | Weapons (PD-prioritized) + hullmods + vents/capacitors. |
| `MISSILE_SUPPORT` | Low-OP weapon policy; missile mounts fill through the same generic mount-type matching every other weapon type uses. | Weapons + hullmods + vents/capacitors. Ammo/reload-aware missile curation is not implemented. |
| `CARRIER_SUPPORT` | Low-OP weapon policy; hullmod selection prefers the hull's own "Fighters"-tagged options first. | Weapons + hullmods (category-prioritized) + **fighter wings** (fills documented bay capacity, faction-evidence-preferred) + vents/capacitors. |

All seven profiles were stress-tested together against all 158 real core combat hulls (1,106 candidates): 157/158 (99.4%) LEGAL for every profile, 0 exceptions -- the one exception is a pre-existing, unrelated Universal-mount-semantics gap, not profile-specific.

Hullmod selection (`generation/hullmods.py`) never fabricates "hullmod X suits role Y": `preferred_hullmod_ids` is a faction's real parsed `known_hullmods`, and `hullmod_priority_tag` (TANK's "Defenses", CARRIER_SUPPORT's "Fighters") is a documented category the game's own `uiTags` column assigns, not an opinion about a specific item. `max_hullmods` defaults to 2 -- not "everything OP allows" -- because that's the real median/mean across 324 live core variants that carry any hullmods at all; an uncapped first attempt produced an unrealistic 20-hullmod frigate on live data. Fighter-wing selection (`generation/fighters.py`) has no such artificial cap: `hull.fighter_bays` is a real, directly parsed physical capacity, so filling it (subject to OP) is the natural conservative behavior, not an invented maximum.

The baseline quality thresholds `artillery_min_range` and `brawler_max_range` are versioned in `baseline_0.1`/`baseline_0.2`; they are scoring heuristics, not legality rules.

As of `baseline_0.2`, scoring also includes a `flux_sustainability` component (its target set by `--flux-mode SAFE|BALANCED|AGGRESSIVE`, defaulted per user mode) and a `faction_doctrine_match` component (only when `--faction-id` resolves to an indexed faction). Both are omitted from the final score -- not zeroed -- when the underlying data is unavailable; see `docs/ROADMAP.md` Tier 2/3.1.
