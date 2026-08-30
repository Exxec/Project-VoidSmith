# Enabled-mod availability review

This note records evidence for entries that the scanner cannot locate. It is not an instruction to change the game installation or launcher configuration.

## 2026-08-21 read-only review

Fresh current-code scan: `generated/starsector_scan_current/reports/scan_summary.json`.

- The scan completed with zero parser errors and three unavailable enabled IDs: `THI`, `QualityCaptains`, and `Red_stripe`.
- Read-only local directory inspection found no directory name matching `THI`, `Tiandong`, `Quality`, `Captains`, `Red`, or `Stripe` under the supplied `mods` directory.
- The IDs are still present in the local `mods/enabled_mods.json` list.

| Enabled ID | Evidence-backed identification | Classification | Safe conclusion |
|---|---|---|---|
| `THI` | Community discussion identifies THI as Tiandong Heavy Industries and describes campaign-layer behavior. [Source](https://www.reddit.com/r/starsector/comments/vf6x6y/searching_for_9_5a_compatible_tiandong_heavy_industries/) | Gameplay/content mod | Missing from this installation; no source data is available to scan. |
| `QualityCaptains` | Community mod lists identify it as “Quality Captains: A Skill Rework.” [Source](https://www.reddit.com/r/starsector/comments/rofpig/budget_list_of_mods_to_use/) | Gameplay/skill-overhaul mod | Missing from this installation; it is not treated as a utility or silently ignored. |
| `Red_stripe` | A Starsector launcher log reports discovery under the `red_stripe` mod ID; a current release page identifies Red Stripe as a faction mod. [Discovery evidence](https://www.fossic.org/thread-7032-1.html), [release evidence](https://www.fossic.org/forum.php?aid=80029&from=album&mod=viewthread&page=1&tid=19982) | Gameplay/faction mod | Missing from this installation; no faction, hull, or equipment data is available to scan. |

## Follow-up boundary

Do not change `enabled_mods.json` automatically. A human may either restore compatible copies of these mods or remove their stale IDs through the game’s normal mod-management workflow. Re-scan after that external change.
