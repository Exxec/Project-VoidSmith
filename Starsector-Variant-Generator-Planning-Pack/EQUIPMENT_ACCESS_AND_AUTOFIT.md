# EQUIPMENT_ACCESS_AND_AUTOFIT.md
# Equipment Provenance, Faction Affinity, and Adaptive Retrofit Rules
Version 0.5

## 1. Core Principle

The mod that supplies an item is not necessarily the faction that owns or prefers it.

Keep these separate:

```text
source_mod_id
source_mod_name
faction_affinity[]
availability_class
```

This allows weapons, fighters, and hullmods from non-faction mods to participate normally.

## 2. Equipment Affinity

```text
NATIVE
APPROVED
COMMON
UNALIGNED
FOREIGN
RESTRICTED
UNKNOWN
```

`UNALIGNED` is the normal state for useful equipment from weapon packs, hullmod packs, fighter packs, and utility/content mods that have no faction ownership.

## 3. Availability Class

```text
STANDARD
COMMON
RARE
SECRET
DEV_ONLY
UNOBTAINABLE
UNKNOWN
```

Affinity and availability are different. `UNALIGNED + STANDARD` is not the same as `UNALIGNED + SECRET`.

## 4. Equipment Access Modes

### STRICT_FACTION
Normally allow `NATIVE`, `APPROVED`, and `COMMON`. Do not silently widen access. Unaligned equipment requires explicit approval/common treatment.

### FACTION_PLUS
Recommended default. Allow `NATIVE`, `APPROVED`, `COMMON`, and `UNALIGNED`. Foreign equipment remains policy-dependent. Prefer faction-flavored gear when mechanically competitive, but do not treat factionless content as foreign by default.

### UNRESTRICTED
Allow any installed legal equipment except content excluded by hidden/restricted settings.

## 5. Non-Faction Weapons

Classify normally by slot legality, size/type, OP, range, damage behavior, flux, projectile behavior, ammo/endurance, PD role, AI friendliness, and hidden state.

If no faction ownership exists, set:

```text
faction_affinity = UNALIGNED
```

## 6. Non-Faction Fighters

Use the same principle. Evaluate legality, OP, replacement time, role, speed, damage behavior, endurance, carrier synergy, and hidden/restricted state.

## 7. Non-Faction Hullmods

Hullmods may be used when legal and sufficiently understood. Apply known typed `HullmodEffect` entries. Scripted behavior remains `UNKNOWN_SCRIPTED_EFFECT` until an adapter or explicit override models it.

## 8. Faction Affinity Inference

Evidence order for non-legality metadata:

```text
explicit user override
knowledge pack
faction data references
existing faction variants
explicit tags/metadata
broad usage across factions
source-mod relationship
unknown
```

Never infer strong faction ownership from source mod identity alone.

## 9. Retrofit Application Modes

### EXACT
Reproduce specified IDs exactly. No substitution. Missing items are reported.

### STARSECTOR_STYLE
Preserve the target template and choose close available substitutes. Keep slot/category/group intent rather than redesigning the build.

### ADAPTIVE
Recommended project default. Preserve intended role and doctrine while selecting the best legal permitted substitutes. Consider role, range, flux, damage behavior, ammo/endurance, AI friendliness, faction affinity, hullmod synergy, OP efficiency, and confidence.

## 10. Adaptive Substitution

Example target intent:

```text
medium ballistic
sustained kinetic pressure
~700 range
moderate flux
AI-friendly
```

Adaptive mode may choose a weapon with a slightly different nominal tag if it better preserves the actual role, range, flux, and AI behavior.

## 11. Substitution Scoring

```text
slot_legality                hard gate
role_match
range_match
flux_match
damage_behavior_match
ammo_endurance_match
AI_friendliness
faction_affinity
doctrine_fit
OP_efficiency
confidence
```

Legality is resolved before scoring.

## 12. Hullmod Substitution

Do not substitute hullmods by name alone. Compare known effects. An unknown scripted hullmod must not silently replace a known armor/flux/logistics effect.

## 13. Optional Available Equipment Pool

```text
AvailableEquipmentPool
    weapons[]
    fighters[]
    hullmods[]
```

If no explicit pool exists, use installed legal equipment under the selected access mode. Do not claim to know the player's inventory.

## 14. Explanation Requirements

For every substitute record:

```text
target_item
replacement_item
replacement_reason
affinity
source_mod
score_components
confidence
```

## 15. Knowledge Pack Interaction

Knowledge packs may mark unaligned equipment as preferred, approve foreign equipment, discourage generic equipment, or define retrofit-specific allowances. They may not bypass legality or invent scripted effects without adapter/override provenance.

## 16. Recommendation Interaction

Faction gap recommendations should consider unaligned equipment before concluding that a foreign hull is required. A native hull plus strong unaligned weapons/hullmods may solve the gap more naturally.

## 17. Preferred FACTION_PLUS Search Order

```text
1. Native
2. Approved
3. Common
4. Unaligned
5. Foreign when current policy allows
```

Within each class, mechanical suitability still matters.

## 18. GUI Placement

Ships and Retrofits should expose:

```text
Equipment Access: Strict Faction / Faction+ / Unrestricted
Retrofit Mode: Exact / Starsector-Style / Adaptive
```

Data / Analysis should show Source Mod, Faction Affinity, Availability, Hidden State, Adapter Coverage, Override Coverage, and Confidence.

## 19. Tests

- factionless weapon is UNALIGNED
- source mod does not imply faction ownership
- Strict Faction can reject unapproved unaligned gear
- Faction+ admits legal unaligned gear
- Unrestricted admits legal non-restricted gear
- Exact never substitutes
- Starsector-style remains template-oriented
- Adaptive can choose the better semantic substitute
- unknown scripted hullmod is not treated as a known equivalent
- provenance appears in explanations
