from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class HullmodIncompatibility:
    a: str
    b: str
    citation: str


@dataclass(frozen=True)
class FluxUnitCost:
    op_cost_per_unit: int
    max_vents_by_hull_size: Mapping[str, int]
    max_capacitors_by_hull_size: Mapping[str, int]
    dissipation_per_vent: float
    capacity_per_capacitor: float
    citation: str


# Vanilla flux vent/capacitor OP cost, per-hull-size maximum count, and
# per-unit effect. installed-game data/config/settings.json directly
# declares dissipation_per_vent/capacity_per_capacitor
# ("fluxPerCapacitor":200, "dissipationPerVent":10) -- those two values are
# parsed data, not a citation. OP cost and the hull-size maximum are not in
# any parseable file (engine-hardcoded); verified 2026-08-22 against a live
# installation at "C:\Program Files (x86)\Fractal Softworks\Starsector" plus
# https://starsector.wiki.gg/wiki/Flux ("Adding a vent or capacitor costs 1
# Ordnance Point"; max table: Frigate 10, Destroyer 20, Cruiser 30, Capital 50),
# cross-checked against the installed settings.json's dissipation/capacity
# values matching the same wiki page exactly.
FLUX_UNIT_COST = FluxUnitCost(
    op_cost_per_unit=1,
    max_vents_by_hull_size=MappingProxyType({"FRIGATE": 10, "DESTROYER": 20, "CRUISER": 30, "CAPITAL_SHIP": 50}),
    max_capacitors_by_hull_size=MappingProxyType({"FRIGATE": 10, "DESTROYER": 20, "CRUISER": 30, "CAPITAL_SHIP": 50}),
    dissipation_per_vent=10.0,
    capacity_per_capacitor=200.0,
    citation="https://starsector.wiki.gg/wiki/Flux, cross-checked against installed data/config/settings.json (2026-08-22)",
)


# Vanilla-Starsector hullmod pairs that are mutually exclusive. This table is
# the only place such rules may live (see Agent.md's adapter-layer
# requirement); validation/legality.py must never infer incompatibility from
# names, tags, or descriptions.
#
# Deliberately empty, and likely to stay that way: two independent sources
# (https://starsector.wiki.gg/wiki/Hullmod and a targeted follow-up query
# against it, 2026-08-22) turned up no documented *pairwise* hullmod
# exclusivity mechanic in vanilla at all. What the wiki documents instead is
# a *categorical* limit -- see MAX_LOGISTICS_HULLMODS below, which is the
# real mechanic and is now implemented. Do not populate this table on the
# strength of a mod's own exclusivity feature (e.g. a compatibility patch
# toggling "mutual exclusivity" between two specific hullmods) -- that is
# evidence about the mod, not about vanilla, unless independently confirmed
# against vanilla's own data or documentation.
INCOMPATIBLE_HULLMOD_PAIRS: tuple[HullmodIncompatibility, ...] = ()


# Vanilla caps a ship at this many hullmods whose CSV `uiTags` column
# contains "Logistics" (verified installed-game hull_mods.csv column;
# e.g. "Logistics, Requires Dock"), regardless of remaining OP. This is a
# different mechanic from vent/capacitor OP cost or pairwise incompatibility
# -- a categorical count limit. Verified 2026-08-22 against a live
# installation's data/config/settings.json ("maxLogisticsHullmods":2) and
# https://starsector.wiki.gg/wiki/Hullmod ("limited to a maximum of 2
# logistics hullmods").
#
# validation/legality.py only ever uses this to ADD an ILLEGAL finding when
# it has positive tag evidence of exceeding the count; a hullmod whose
# uiTags don't parse or don't mention "Logistics" is never assumed
# non-logistics with confidence -- it simply isn't counted, so this check
# can under-enforce for inconsistently-tagged modded hullmods but never
# wrongly fail a legal variant on missing data.
MAX_LOGISTICS_HULLMODS = 2


@dataclass(frozen=True)
class HullmodLogisticsEffect:
    """First real slice of DATA_SCHEMA.md v0.3's HullmodEffect model.

    Deliberately narrower than that model's full generality (which covers
    12 effect categories and 10 operation kinds): only the specific
    "flat bonus by hull size, or a percent of the base stat, whichever is
    higher" pattern that 3 of 3 researched vanilla LOGISTICS hullmods
    actually use. Generalizing to DATA_SCHEMA.md's full operation
    vocabulary (MULTIPLY/SET/CONDITIONAL/...) before more categories are
    actually researched would mean guessing at shapes no verified data
    supports yet -- see docs/ROADMAP.md's Hullmod Effect Engine section.
    """

    hullmod_id: str
    stat: str
    flat_bonus_by_hull_size: Mapping[str, float]
    percent_bonus: float | None
    civilian_maintenance_penalty_percent: float | None
    citation: str


# Verified 2026-08-22: the real `.wpn`-equivalent hullmod CSV's `desc` field
# for these hullmods contains only unfilled "%s" template placeholders (the
# actual numbers are engine-hardcoded, not in any parseable data file --
# confirmed absent from data/config/settings.json too), so these values are
# from https://starsector.wiki.gg/wiki (one fetch per hullmod, quoted
# directly), cross-checked against this installation's own real, already-
# parsed OP-cost table before being trusted: the wiki's claimed OP costs
# (Frigate 5 / Destroyer 10 / Cruiser 15 / Capital 25) match this
# installation's `Hullmod.op_cost_by_hull_size` for all three exactly.
LOGISTICS_HULLMOD_EFFECTS: tuple[HullmodLogisticsEffect, ...] = (
    HullmodLogisticsEffect(
        hullmod_id="expanded_cargo_holds", stat="cargo_capacity",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 30.0, "DESTROYER": 60.0, "CRUISER": 100.0, "CAPITAL_SHIP": 200.0}),
        percent_bonus=0.30, civilian_maintenance_penalty_percent=0.50,
        citation="https://starsector.wiki.gg/wiki/Expanded_Cargo_Holds (2026-08-22), OP-cost cross-checked against live install",
    ),
    HullmodLogisticsEffect(
        hullmod_id="auxiliary_fuel_tanks", stat="fuel_capacity",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 30.0, "DESTROYER": 60.0, "CRUISER": 100.0, "CAPITAL_SHIP": 200.0}),
        percent_bonus=0.30, civilian_maintenance_penalty_percent=0.50,
        citation="https://starsector.wiki.gg/wiki/Auxiliary_Fuel_Tanks (2026-08-22), OP-cost cross-checked against live install",
    ),
    HullmodLogisticsEffect(
        hullmod_id="additional_berthing", stat="crew_max",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 30.0, "DESTROYER": 60.0, "CRUISER": 100.0, "CAPITAL_SHIP": 200.0}),
        percent_bonus=0.30, civilian_maintenance_penalty_percent=0.50,
        citation="https://starsector.wiki.gg/wiki/Additional_Berthing (2026-08-22), OP-cost cross-checked against live install",
    ),
    HullmodLogisticsEffect(
        hullmod_id="augmentedengines", stat="max_burn",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 2.0, "DESTROYER": 2.0, "CRUISER": 2.0, "CAPITAL_SHIP": 2.0}),
        percent_bonus=None, civilian_maintenance_penalty_percent=None,
        citation="https://starsector.wiki.gg/wiki/Augmented_Drive_Field (2026-08-22): flat +2 burn, all hull sizes, no percent component",
    ),
    # militarized_subsystems affects two independent stats -- max_burn (flat)
    # and crew_min (percent) -- so it needs two entries sharing one
    # hullmod_id. See adapters/__init__.py's grouped lookup, which returns
    # every matching entry rather than assuming one per hullmod id (a real
    # limitation the first 4 hullmods, each single-stat, never exercised).
    HullmodLogisticsEffect(
        hullmod_id="militarized_subsystems", stat="max_burn",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 1.0, "DESTROYER": 1.0, "CRUISER": 1.0, "CAPITAL_SHIP": 1.0}),
        percent_bonus=None, civilian_maintenance_penalty_percent=None,
        citation="https://starsector.wiki.gg/wiki/Militarized_Subsystems (2026-08-22): flat +1 max burn level, all hull sizes, no percent component. OP cost 4/8/12/20 and base value 6,000 cross-checked exactly against live install.",
    ),
    HullmodLogisticsEffect(
        hullmod_id="militarized_subsystems", stat="crew_min",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 0.0, "DESTROYER": 0.0, "CRUISER": 0.0, "CAPITAL_SHIP": 0.0}),
        percent_bonus=1.0, civilian_maintenance_penalty_percent=None,
        citation="https://starsector.wiki.gg/wiki/Militarized_Subsystems (2026-08-22): doubles (+100%) minimum crew required, no flat component. The real hullmod CSV's own desc text independently confirms two separate effects (\"increases maximum burn level by %s ... Increases minimum crew required by %s\"), corroborating the wiki's two-effect claim even though the numeric %s values are engine-hardcoded, not in the CSV itself.",
    ),
)


@dataclass(frozen=True)
class HullmodPercentReductionEffect:
    """A second, distinct pattern found while researching the LOGISTICS
    group's remaining hullmods (docs/ROADMAP.md's "real scope of LOGISTICS
    confirmed" note): a flat percent *reduction* applied to one or more
    stats, not the flat-by-size-or-percent *increase* `HullmodLogisticsEffect`
    models. Deliberately kept as a separate type rather than force-fit into
    the max(flat, percent) formula, which has no sensible "which is
    stronger" comparison for a reduction (a reduction's whole magnitude
    applies -- there is no flat-vs-percent alternative to pick the larger
    of, unlike the increase case where real vanilla hullmods do offer both
    and only the higher one applies).
    """

    hullmod_id: str
    stats: tuple[str, ...]
    percent_reduction: float
    citation: str


# Verified 2026-08-22: `efficiency_overhaul`'s CSV `desc` field is also an
# unfilled "%s" template (same pattern as LOGISTICS_HULLMOD_EFFECTS above).
# Values from https://starsector.wiki.gg/wiki/Efficiency_Overhaul: 20% (base,
# non-S-mod) reduction to supply use for maintenance, fuel use, and minimum
# crew required, plus separate combat-readiness-recovery and repair-rate
# bonuses this project doesn't model (no CR/repair-rate Hull stat exists) and
# an additional 10% S-mod-only reduction this project doesn't model (no S-mod
# concept exists on Variant yet). OP cost (3/6/9/15) and base value (4,000
# credits) cross-checked exactly against this installation's own parsed
# `Hullmod.op_cost_by_hull_size` and CSV base value before trusting the
# percentage. "Fuel use" here means fuel consumed per day
# of travel, not `Hull.fuel_capacity` (a different, currently-unmodeled stat)
# -- only the two stats this project already tracks (`supplies_per_month`,
# `crew_min`) are represented below.
EFFICIENCY_HULLMOD_EFFECTS: tuple[HullmodPercentReductionEffect, ...] = (
    HullmodPercentReductionEffect(
        hullmod_id="efficiency_overhaul",
        stats=("supplies_per_month", "crew_min"),
        percent_reduction=0.20,
        citation="https://starsector.wiki.gg/wiki/Efficiency_Overhaul (2026-08-22): 20% base reduction to supply use for maintenance and minimum crew required (fuel-use-per-day and the S-mod-only extra 10% are not modeled -- see module docstring). OP cost 3/6/9/15 and base value 4,000 cross-checked exactly against live install.",
    ),
)


@dataclass(frozen=True)
class HullmodDefenseEffect:
    """DEFENSE-category hullmod effects on a hull's base armor rating or hull
    hitpoints ("hull integrity" in the game's own hullmod description text).

    Unlike HullmodLogisticsEffect, no researched DEFENSE hullmod combines a
    flat-by-hull-size component with a percent component on the SAME
    hullmod -- each of the 4 hullmods below is either flat-only
    (heavyarmor) or percent-only (the other three) -- so this type only
    ever has one of flat_bonus_by_hull_size/percent_bonus populated, the
    other left None. It deliberately does not reuse
    HullmodLogisticsEffect's max(flat, percent) "whichever is higher"
    formula: that formula describes a documented single-hullmod mechanic
    (3 of 3 researched LOGISTICS hullmods genuinely have both components
    and the higher one applies) that no researched DEFENSE hullmod
    exhibits, so implementing "take the max" here would mean guessing at a
    combining rule no evidence supports.
    """

    hullmod_id: str
    stat: str  # "armor_rating" or "hull_hp"
    flat_bonus_by_hull_size: Mapping[str, float] | None
    percent_bonus: float | None
    citation: str


# armor_rating and hull_hp ("hull integrity" in the hullmod desc text) are
# not typed Hull dataclass fields (core/models.py) -- they come only from
# the raw hull CSV row's "armor rating"/"hitpoints" columns, which
# parsers/entities.py's hull_from_row preserves verbatim in Hull.raw (never
# parsed into a typed field, since nothing in this project consumed them
# before now). analysis/combat_stats.py reads them from there, falling back
# to the base hull's raw for a skin-derived Hull (whose own raw holds only
# skin_data + base_hull_id/base_hull_source_mod -- see hull_from_skin in
# parsers/entities.py, which does not carry the CSV row forward for skins).
#
# Verified 2026-08-23: same "%s" unfilled-template pattern as
# LOGISTICS_HULLMOD_EFFECTS above -- hull_mods.csv's desc column for all 4
# of these hullmods has the actual numbers as engine-hardcoded "%s"
# placeholders, not parseable data. Values are from
# https://starsector.wiki.gg/wiki (one fetch per hullmod, 2026-08-23),
# cross-checked against this installation's own already-parsed data before
# being trusted: every one of these 4 hullmods' claimed OP cost by hull
# size matches `Hullmod.op_cost_by_hull_size` from a live scan exactly
# (heavyarmor 8/15/20/40, reinforcedhull 5/10/15/30, blast_doors 4/8/12/20,
# armoredweapons 3/6/9/15), and each hullmod's CSV "base value" column
# (2,500 credits for all 4) is consistent with them being same-tier
# defensive hullmods.
#
# When more than one of these hullmods targets the SAME stat in one
# variant (e.g. reinforcedhull + blast_doors both target hull_hp), this
# project does not fabricate a cross-hullmod stacking rule (additive vs
# multiplicative percent stacking is undocumented) -- see
# analysis/combat_stats.py's `stacking_notes`, which applies the same
# discipline `compute_derived_civilian_stats` already uses for combined
# civilian maintenance penalties: report each contribution separately
# rather than guess at how they combine.
DEFENSE_HULLMOD_EFFECTS: tuple[HullmodDefenseEffect, ...] = (
    HullmodDefenseEffect(
        hullmod_id="heavyarmor", stat="armor_rating",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 150.0, "DESTROYER": 300.0, "CRUISER": 400.0, "CAPITAL_SHIP": 500.0}),
        percent_bonus=None,
        citation="https://starsector.wiki.gg/wiki/Heavy_Armor (2026-08-23): +150/300/400/500 armor by hull size (frigate/destroyer/cruiser/capital), no percent component. OP cost 8/15/20/40 cross-checked exactly against live install.",
    ),
    HullmodDefenseEffect(
        hullmod_id="armoredweapons", stat="armor_rating",
        flat_bonus_by_hull_size=None,
        percent_bonus=0.10,
        citation="https://starsector.wiki.gg/wiki/Armored_Weapon_Mounts (2026-08-23): +10% ship armor (the hullmod's other 3 effects -- weapon durability +100%, recoil -25%, weapon turn rate -25% -- are per-weapon stats this project doesn't track, not a ship-level stat, so are not modeled here). OP cost 3/6/9/15 cross-checked exactly against live install.",
    ),
    HullmodDefenseEffect(
        hullmod_id="reinforcedhull", stat="hull_hp",
        flat_bonus_by_hull_size=None,
        percent_bonus=0.40,
        citation="https://starsector.wiki.gg/wiki/Reinforced_Bulkheads (2026-08-23): +40% hull integrity (the ship-almost-always-recoverable-if-disabled effect is not a ship stat this project tracks). OP cost 5/10/15/30 cross-checked exactly against live install.",
    ),
    HullmodDefenseEffect(
        hullmod_id="blast_doors", stat="hull_hp",
        flat_bonus_by_hull_size=None,
        percent_bonus=0.20,
        citation="https://starsector.wiki.gg/wiki/Blast_Doors (2026-08-23): +20% hull integrity (the crew-casualty-reduction-from-hull-damage effect is not a Hull stat this project tracks). OP cost 4/8/12/20 cross-checked exactly against live install.",
    ),
    HullmodDefenseEffect(
        hullmod_id="insulatedengine", stat="hull_hp",
        flat_bonus_by_hull_size=None,
        percent_bonus=0.10,
        citation="https://starsector.wiki.gg/wiki/Insulated_Engine_Assembly (research recorded 2026-08-23): +10% hull integrity. Engine durability and sensor-profile effects have no normalized static stat here. OP cost 3/6/9/15 previously cross-checked against live install.",
    ),
)


@dataclass(frozen=True)
class HullmodMobilityEffect:
    """MOBILITY-category hullmod effects on a hull's base engine-performance
    stats: top speed, acceleration, deceleration, max turn rate, and turn
    acceleration (the five real hull CSV columns "max speed"/"acceleration"/
    "deceleration"/"max turn rate"/"turn acceleration" -- see
    analysis/mobility_stats.py's `_MOBILITY_STAT_CSV_COLUMNS`).

    Structurally identical to HullmodDefenseEffect (one of
    flat_bonus_by_hull_size/percent_bonus populated, the other None), but
    kept as its own type rather than reused: MOBILITY is a distinct
    DATA_SCHEMA.md v0.3 category from DEFENSE, and the two happening to
    share a shape today (as LOGISTICS and DEFENSE also do not exactly
    share one) is not evidence they should be coupled -- see
    HullmodDefenseEffect's own docstring for the same reasoning applied to
    LOGISTICS vs. DEFENSE.
    """

    hullmod_id: str
    stat: str  # "max_speed", "acceleration", "deceleration", "max_turn_rate", or "turn_acceleration"
    flat_bonus_by_hull_size: Mapping[str, float] | None
    percent_bonus: float | None
    citation: str


# Researched 2026-08-23 from the real hull_mods.csv's uiTags column: of the
# vanilla hullmods tagged "Engines" (auxiliarythrusters, escort_package,
# nav_relay, safetyoverrides, unstable_injector, insulatedengine), three
# have a genuinely per-ship, unconditional, documented numeric effect on one
# of the five MOBILITY stats above -- the same "%s"-unfilled-template CSV
# desc pattern as every other category above, so values are from
# https://starsector.wiki.gg/wiki (two independent fetches per hullmod,
# 2026-08-23, cross-checked against each other), and each hullmod's real OP
# cost by hull size was cross-checked exactly against this installation's
# own parsed `Hullmod.op_cost_by_hull_size` before being trusted
# (auxiliarythrusters 4/8/12/20, unstable_injector 5/10/15/25,
# safetyoverrides 15/30/45/70).
#
# The other three "Engines"-tagged hullmods were researched and ruled out,
# same discipline as LOGISTICS_HULLMOD_EFFECTS' excluded list below:
# - nav_relay (OP 10/15/20/25): "increases nav rating of your fleet ...
#   increases the top speed of your deployed ships" -- a FLEET-wide
#   campaign mechanic (own fleet's nav rating pool), same class of
#   out-of-scope effect as hiressensors (see LOGISTICS' excluded list).
# - escort_package (OP 0/7/15/0): maneuverability/speed/weapon-range bonus
#   is conditional on "within approximately %s su of a larger friendly
#   vessel" -- a real-time positional condition this project's static,
#   offline per-variant analysis cannot evaluate (no battlefield state
#   exists), not an unconditional hull stat.
# - insulatedengine (OP 3/6/9/15): already researched under LOGISTICS'
#   excluded list -- its only stat-shaped effect (hull integrity +10%) is
#   a DEFENSE-category stat, not MOBILITY; its engine-durability and
#   sensor-profile effects have no corresponding Hull stat at all.
#
# auxiliarythrusters' own desc text advertises "50% better maneuverability"
# as a single number, but the wiki's Notes section documents that this is
# flavor text for four *separate* underlying stat bonuses -- modeled here
# as four independent entries rather than one fabricated "maneuverability"
# stat, since no such single CSV column or Hull field exists.
#
# safetyoverrides' top-speed bonus is documented for only 3 of 4 hull
# sizes (frigate/destroyer/cruiser) -- its own desc text states "Can not
# be installed on civilian or capital ships", so CAPITAL_SHIP is
# deliberately absent from its flat_bonus_by_hull_size mapping rather than
# populated with a guessed value; a capital-ship hull encountered with this
# hullmod anyway (e.g. modded data that ignores the restriction) is left
# unverified for that stat rather than assigned a fabricated bonus. Its
# desc also documents a same-direction, unquantified "corresponding
# increase in acceleration" and unrelated flux-dissipation-rate/peak-CR-
# time/weapon-range penalties; none of those are modeled since no exact
# number is given for the first and the others are not MOBILITY stats.
#
# When unstable_injector and safetyoverrides are both present on one
# variant, they target the same stat (max_speed) -- see
# analysis/mobility_stats.py's stacking_notes, which applies the identical
# "report each contribution separately, never fabricate a combined value"
# discipline DEFENSE already established for reinforcedhull + blast_doors.
MOBILITY_HULLMOD_EFFECTS: tuple[HullmodMobilityEffect, ...] = (
    HullmodMobilityEffect(
        hullmod_id="auxiliarythrusters", stat="acceleration",
        flat_bonus_by_hull_size=None, percent_bonus=1.00,
        citation="https://starsector.wiki.gg/wiki/Auxiliary_Thrusters (2026-08-23), Notes section: \"the actual bonuses are as follows: Acceleration: +100%\" (desc's advertised \"50% better maneuverability\" is flavor text, not the real per-stat magnitude). OP cost 4/8/12/20 cross-checked exactly against live install.",
    ),
    HullmodMobilityEffect(
        hullmod_id="auxiliarythrusters", stat="deceleration",
        flat_bonus_by_hull_size=None, percent_bonus=0.50,
        citation="https://starsector.wiki.gg/wiki/Auxiliary_Thrusters (2026-08-23), Notes section: \"Deceleration: +50%\". OP cost 4/8/12/20 cross-checked exactly against live install.",
    ),
    HullmodMobilityEffect(
        hullmod_id="auxiliarythrusters", stat="turn_acceleration",
        flat_bonus_by_hull_size=None, percent_bonus=1.00,
        citation="https://starsector.wiki.gg/wiki/Auxiliary_Thrusters (2026-08-23), Notes section: \"Turn acceleration: +100%\". OP cost 4/8/12/20 cross-checked exactly against live install.",
    ),
    HullmodMobilityEffect(
        hullmod_id="auxiliarythrusters", stat="max_turn_rate",
        flat_bonus_by_hull_size=None, percent_bonus=0.50,
        citation="https://starsector.wiki.gg/wiki/Auxiliary_Thrusters (2026-08-23), Notes section: \"Max turn rate: +50%\". OP cost 4/8/12/20 cross-checked exactly against live install.",
    ),
    HullmodMobilityEffect(
        hullmod_id="unstable_injector", stat="max_speed",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 25.0, "DESTROYER": 20.0, "CRUISER": 15.0, "CAPITAL_SHIP": 15.0}),
        percent_bonus=None,
        citation="https://starsector.wiki.gg/wiki/Unstable_Injector (2026-08-23): \"Increases the ship's top speed in combat by 25/20/15/15 su/second, depending on hull size\" (frigate/destroyer/cruiser/capital). The weapon-range and fighter-replacement-time penalties are not MOBILITY stats and are not modeled. OP cost 5/10/15/25 cross-checked exactly against live install.",
    ),
    HullmodMobilityEffect(
        hullmod_id="safetyoverrides", stat="max_speed",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 50.0, "DESTROYER": 30.0, "CRUISER": 20.0}),
        percent_bonus=None,
        citation="https://starsector.wiki.gg/wiki/Safety_Overrides (2026-08-23): \"increases the ship's top speed in combat by 50/30/20 (depending on ship size...)\" (frigate/destroyer/cruiser only -- desc text states \"Can not be installed on civilian or capital ships\", so no capital value is given or modeled). The unquantified \"corresponding increase in acceleration\", the flux-dissipation-rate x2 and peak-CR-time /3 factors, and the weapon-range penalty are not modeled (no exact acceleration number given; the others are not MOBILITY stats). OP cost 15/30/45/70 cross-checked exactly against live install.",
    ),
)


# Remaining real LOGISTICS-tagged hullmods, researched 2026-08-22 and found
# NOT modelable in this project's current DerivedShipState scope -- not
# "not yet researched," but investigated and deliberately excluded, each for
# a specific, documented reason. Kept here (not silently dropped) so a
# future session doesn't re-research these from scratch or assume the gap
# is an oversight. All OP costs below were cross-checked exactly against
# this installation's own parsed `Hullmod.op_cost_by_hull_size` before
# these conclusions were reached.
#
# - hiressensors (High Resolution Sensors, OP 4/6/9/15): its effect is a
#   FLEET-wide campaign-map sensor range bonus (+50/75/100/150 by hull
#   size) -- a whole-fleet mechanic, which Agent.md and root ROADMAP.md's
#   "Current Scope Boundary" explicitly defer ("whole-fleet optimization
#   is deferred"). Its only per-ship effect is an S-mod-only in-combat
#   vision-range bonus; S-mods aren't modeled on Variant at all.
# - insulatedengine (Insulated Engine Assembly, OP 3/6/9/15): its verified
#   +10% hull-integrity effect is modeled under DEFENSE. Engine durability
#   and sensor-profile effects remain unavailable (no static normalized stat).
# - solar_shielding (Solar Shielding, OP 3/6/9/15): reduces a specific
#   campaign hazard's CR penalty and a flat 10% in-combat energy-damage
#   reduction. The damage-reduction effect specifically would mean
#   modeling live combat damage math, which Forge formal spec.txt section
#   4 explicitly rules out ("combat simulation" is out of scope at any
#   future point).
# - surveying_equipment (Surveying Equipment, OP 5/10/15/25): reduces the
#   supply/machinery cost of the campaign-map "survey a planet" action.
#   Not a ship stat at all -- a campaign-action cost modifier, outside
#   this project's per-variant analysis scope entirely.


@dataclass(frozen=True)
class HullmodFluxEffect:
    """FLUX-category hullmod effects on a hull's base `flux_dissipation` or
    `shield_upkeep` -- the same two typed `Hull` dataclass fields (not raw
    CSV columns; see core/models.py) that scoring/candidate_score.py's
    `_flux_component` already reads for the existing `flux_sustainability`
    score. `flux_capacity` (a third, separate typed Hull field) is
    deliberately out of scope here -- see the researched-but-excluded note
    below for `fluxcoil`.

    Three distinct real operation shapes appear across the verified
    hullmods below, so this type deliberately supports all three rather
    than force-fitting into HullmodDefenseEffect's/HullmodMobilityEffect's
    two-shape (flat-by-size XOR additive percent) vocabulary:
      - `fluxdistributor`: flat bonus by hull size (same shape as
        DEFENSE/MOBILITY's flat_bonus_by_hull_size).
      - `safetyoverrides`: a *multiplicative* factor applied to the whole
        dissipation rate ("increased by a factor of 2"), not an additive
        percent bonus -- reusing an additive-percent field here would
        understate the real, documented effect.
      - `stabilizedshieldemitter`: a percent *reduction* (same shape as
        HullmodPercentReductionEffect), applied to shield_upkeep.
    Exactly one of flat_bonus_by_hull_size / multiplicative_factor /
    percent_reduction is populated per entry; the other two are None.

    `excluded_hull_sizes` names hull sizes the citation itself documents as
    unable to carry this hullmod at all (e.g. `safetyoverrides`' own desc
    text: "Can not be installed on civilian or capital ships"). A
    `flat_bonus_by_hull_size` mapping already expresses this naturally by
    simply omitting the excluded size's key (see MOBILITY_HULLMOD_EFFECTS'
    own `safetyoverrides` entry above, whose mapping has no CAPITAL_SHIP
    key) -- but `multiplicative_factor`/`percent_reduction` are bare scalars
    with no per-size structure, so without this field a consumer would have
    no way to avoid fabricating a x2 flux_dissipation bonus for a
    CAPITAL_SHIP hull the real hullmod could never be installed on. Empty
    for every entry except `safetyoverrides`.
    """

    hullmod_id: str
    stat: str  # "flux_dissipation" or "shield_upkeep"
    flat_bonus_by_hull_size: Mapping[str, float] | None
    multiplicative_factor: float | None
    percent_reduction: float | None
    excluded_hull_sizes: frozenset[str]
    citation: str


# Researched 2026-08-23 starting from the task-supplied candidate list, using
# each hullmod's REAL id from the live installation's own
# data/hullmods/hull_mods.csv (which differs from the task's guessed
# underscore-style names in several cases -- e.g. "Flux Distributor"'s real
# id is `fluxdistributor`, "Hardened Shields"' is `hardenedshieldemitter`,
# "Flux Coil Adjunct"'s is `fluxcoil`, "Stabilized Shields"' is
# `stabilizedshieldemitter`). Same "%s"-unfilled-template CSV desc pattern
# as every other category above (verified 2026-08-23 directly against the
# live CSV), so values are from https://starsector.wiki.gg/wiki (one fetch
# per hullmod, 2026-08-23), cross-checked against this installation's own
# already-parsed `Hullmod.op_cost_by_hull_size` before being trusted:
# fluxdistributor 4/8/12/20, stabilizedshieldemitter 3/6/9/15, and
# safetyoverrides 15/30/45(/70) all match the live CSV's cost_frigate/
# cost_dest/cost_cruiser/cost_capital columns exactly.
#
# `safetyoverrides` was not in the task's candidate list but was found
# while researching the CSV for any other hullmod whose desc text mentions
# "flux dissipation": its "flux dissipation rate ... increased by a factor
# of %s" is a real, unconditional, per-ship effect on the same stat this
# module already tracks, and its OP cost/top-speed numbers were already
# cross-checked and modeled once under MOBILITY_HULLMOD_EFFECTS above
# (whose own docstring already flagged this x2 factor as "not a MOBILITY
# stat" -- it is a FLUX stat, modeled here instead). Like its MOBILITY
# entry, CAPITAL_SHIP is deliberately absent: the hullmod's own desc text
# states "Can not be installed on civilian or capital ships", and the
# wiki's own OP-cost table only lists Frigate/Destroyer/Cruiser for the
# same reason (the live CSV does carry a cost_capital=70 value, but that is
# an unused engine default, not evidence the hullmod can target capitals).
#
# When `fluxdistributor` and `safetyoverrides` are both present on one
# variant, they target the same stat (flux_dissipation) via two different
# operations (flat-add vs. multiply) -- see analysis/flux_stats.py's
# `stacking_notes`, which applies the identical "report each contribution
# separately, never fabricate a combined value" discipline DEFENSE and
# MOBILITY already established.
FLUX_HULLMOD_EFFECTS: tuple[HullmodFluxEffect, ...] = (
    HullmodFluxEffect(
        hullmod_id="fluxdistributor", stat="flux_dissipation",
        flat_bonus_by_hull_size=MappingProxyType({"FRIGATE": 30.0, "DESTROYER": 60.0, "CRUISER": 90.0, "CAPITAL_SHIP": 150.0}),
        multiplicative_factor=None, percent_reduction=None, excluded_hull_sizes=frozenset(),
        citation="https://starsector.wiki.gg/wiki/Flux_Distributor (2026-08-23): \"Increases the ship's flux dissipation by 30/60/90/150, depending on hull size\" (frigate/destroyer/cruiser/capital). The S-mod-only extra bonus is not modeled (no S-mod concept exists on Variant). OP cost 4/8/12/20 cross-checked exactly against live install.",
    ),
    HullmodFluxEffect(
        hullmod_id="safetyoverrides", stat="flux_dissipation",
        flat_bonus_by_hull_size=None, multiplicative_factor=2.0, percent_reduction=None,
        excluded_hull_sizes=frozenset({"CAPITAL_SHIP"}),
        citation="https://starsector.wiki.gg/wiki/Safety_Overrides (2026-08-23): \"The flux dissipation rate, including that of additional vents, is increased by a factor of 2.\" Not modeled on CAPITAL_SHIP -- desc text states \"Can not be installed on civilian or capital ships\" (matches this hullmod's own MOBILITY_HULLMOD_EFFECTS entry above, which also omits CAPITAL_SHIP; `excluded_hull_sizes` is this entry's equivalent gate, since `multiplicative_factor` is a bare scalar with no per-size map to omit a key from). OP cost 15/30/45 (frigate/destroyer/cruiser) cross-checked exactly against live install.",
    ),
    HullmodFluxEffect(
        hullmod_id="stabilizedshieldemitter", stat="shield_upkeep",
        flat_bonus_by_hull_size=None, multiplicative_factor=None, percent_reduction=0.50, excluded_hull_sizes=frozenset(),
        citation="https://starsector.wiki.gg/wiki/Stabilized_Shields (2026-08-23): \"Reduces the amount of soft flux raised shields generate per second by 50%. Does not affect the hard flux generated as a result of shields taking damage.\" (the CSV's own desc text confirms the same two-part structure with unfilled %s placeholders). The S-mod-only hard-flux-to-soft-flux conversion is not modeled. OP cost 3/6/9/15 cross-checked exactly against live install. No hull-size restriction is documented for this hullmod.",
    ),
)


# Remaining real candidates researched 2026-08-23 (the task's original list
# plus every other hullmod turned up while grep-ing the live CSV's desc
# column for "flux dissipation"/"soft flux"/"shield"+"flux") and found NOT
# modelable here -- not "not yet researched," but investigated and
# deliberately excluded, each for a specific, documented reason. All OP
# costs below were cross-checked exactly against this installation's own
# parsed `Hullmod.op_cost_by_hull_size` before these conclusions were
# reached.
#
# - fluxcoil (Flux Coil Adjunct, OP 4/8/12/20): "Increases the flux
#   capacity by 600/1200/1800/3000, depending on hull size" (wiki,
#   2026-08-23) -- a real, unconditional, per-hull-size effect, but on
#   `flux_capacity`, a third typed Hull field this task's scope explicitly
#   excludes (only flux_dissipation and shield_upkeep, matching what
#   _flux_component actually consumes). Named here rather than silently
#   dropped in case a future FLUX-scope extension wants it.
# - hardenedshieldemitter (Hardened Shields, OP 5/10/15/25): "Reduces the
#   amount of damage taken by shields by 20%" (wiki, 2026-08-23) plus an
#   EMP-arc-piercing-chance reduction -- neither is a change to
#   flux_dissipation or shield_upkeep (shield damage reduction is a
#   combat-damage-math effect, which Forge formal spec.txt section 4 rules
#   out modeling), and no Hull field exists for either effect.
# - fluxbreakers (Resistant Flux Conduits, OP 3/6/9/15): "increases the
#   ship's flux dissipation rate while venting by 25%" (wiki, 2026-08-23)
#   -- a real number, but CONDITIONAL on the ship actively venting flux,
#   not a permanent modification of the always-on flux_dissipation stat
#   this project's static, offline per-variant analysis represents (the
#   same class of exclusion as MOBILITY's escort_package: a real-time
#   battlefield-state condition this project cannot evaluate). Its
#   unconditional 50% EMP-damage-reduction effect has no corresponding
#   Hull field.
# - phase_anchor (Phase Anchor, OP 10/20/30/50): "Increases the soft flux
#   dissipation and weapon recharge rate by 2x while phased" (wiki,
#   2026-08-23) -- same conditional-effect exclusion as fluxbreakers above
#   (only while the ship is phased, a real-time battlefield state), plus
#   it is restricted to phase hulls.
# - augmentedengines (Augmented Drive Field): re-verified against the live
#   CSV's desc column -- its only effect is "Increases maximum burn level
#   by %s" (already modeled under LOGISTICS_HULLMOD_EFFECTS above). No
#   flux-relevant effect exists for this hullmod in vanilla.
# - unstable_injector: re-verified against the live CSV's desc column --
#   its only effects are the top-speed bonus (already modeled under
#   MOBILITY_HULLMOD_EFFECTS above) and a weapon-range/fighter-replacement-
#   time penalty. No flux-relevant effect exists for this hullmod either.
# - design_compromises, andrada_mods ("Special Modifications"),
#   faulty_grid ("Faulty Power Grid"), heg_militarized, shared_flux_sink,
#   fluxshunt: each has real "%s"-templated flux-dissipation/-capacity
#   text in its desc column, but every one of them has `hidden=TRUE` in the
#   live CSV -- these are narrative d-mods, unique-ship narrative
#   hullmods, or modular-station-only mechanics the engine applies
#   automatically, never player-installable choices a generated variant
#   would carry. Excluded as out of this project's per-variant, player-
#   built-loadout scope, not for lack of a citable number.
FLUX_HULLMOD_EXCLUDED_IDS: tuple[str, ...] = (
    "fluxcoil", "hardenedshieldemitter", "fluxbreakers", "phase_anchor",
    "design_compromises", "andrada_mods", "faulty_grid", "heg_militarized",
    "shared_flux_sink", "fluxshunt",
)


@dataclass(frozen=True)
class HullmodCombatEffect:
    """COMBAT-category hullmod effects on an equipped weapon's base `range`
    (`Weapon.range` -- see core/models.py). This is the first category
    whose verified effects live on `Weapon`, not `Hull`: DEFENSE/MOBILITY/
    FLUX all resolve onto a single per-hull stat, but both hullmods below
    are installed on the hull yet grant a percent bonus to each *equipped*
    weapon's own `range` field individually -- so a consumer needs the
    hull (for `hull_size`, which selects the percent bonus and gates
    which hull sizes may carry the hullmod at all) AND the variant's
    `weapons_by_mount` (to know which real `Weapon` occupies each mount,
    and that weapon's own `mount_type`/`range`), not the hull alone. See
    analysis/weapon_range_stats.py's `compute_derived_combat_stats`, which
    is why (unlike compute_derived_flux_stats/_defense_stats/_mobility_stats)
    it takes the whole `Variant`, not just a bare `hullmod_ids` iterable.

    `applies_to_mount_types` gates by `Weapon.mount_type` -- verified
    directly against every real `.wpn` file's own `"type"` field in this
    installation (`parsers/entities.py::weapon_spec_fields`), which takes
    exactly one of four real values: BALLISTIC, ENERGY, MISSILE,
    DECORATIVE. Both hullmods below document "ballistic and energy
    weapons" explicitly, so `applies_to_mount_types` is always
    `{"BALLISTIC", "ENERGY"}` -- MISSILE and DECORATIVE weapons are never
    matched, and a weapon whose `mount_type` didn't parse (None) is
    likewise never matched (absence of mount_type evidence is not treated
    as a BALLISTIC/ENERGY match).

    Both verified entries use the same single operation shape -- a percent
    bonus to `Weapon.range`, keyed by the *hull's* `hull_size` (not the
    weapon's own `size`) -- so `stat`/`operation` are not separate fields
    the way HullmodFluxEffect needs them (FLUX has three real shapes;
    COMBAT researched here has only one). `percent_bonus_by_hull_size`
    only contains keys for hull sizes the hullmod's own citation
    documents as eligible -- `dedicated_targeting_core`'s mapping omits
    FRIGATE/DESTROYER entirely (its own desc text says "Can not be
    installed on a frigate or a destroyer", matching this installation's
    own cost_frigate=0/cost_dest=0), the same "omit the key, never
    fabricate a value" discipline `safetyoverrides`' FLUX/MOBILITY entries
    already use for CAPITAL_SHIP.
    """

    hullmod_id: str
    stat: str
    applies_to_mount_types: frozenset[str]
    percent_bonus_by_hull_size: Mapping[str, float]
    citation: str


# Researched 2026-08-24, continuing the DATA_SCHEMA.md v0.3 category sweep
# (LOGISTICS/DEFENSE/MOBILITY/FLUX already modeled) into COMBAT: grepped
# the live install's hull_mods.csv desc column for weapon range/damage/
# rate-of-fire language. COMBAT hullmods overwhelmingly target per-weapon
# stats this project does not have a typed field for at all (ammo
# capacity, rate of fire, turn rate, recoil, weapon durability, raw
# damage) -- see the excluded list below. The two exceptions are
# `targetingunit` (Integrated Targeting Unit) and `dedicated_targeting_core`
# (Dedicated Targeting Core), both of which grant a real, unconditional,
# documented percent bonus to `Weapon.range` -- a field that already
# exists (weapon_from_row parses it directly from weapon_data.csv's
# "range" column). Both hullmods' desc columns carry only unfilled "%s"
# templates in the live CSV (same pattern as every other category), so
# values are from https://starsector.wiki.gg/wiki (one fetch per hullmod,
# 2026-08-24), cross-checked against this installation's own already-
# parsed `Hullmod.op_cost_by_hull_size` before being trusted: targetingunit
# 4/8/15/25 and dedicated_targeting_core 0/0/15/25 (frigate/destroyer/
# cruiser/capital) both match the live CSV's cost_frigate/cost_dest/
# cost_cruiser/cost_capital columns exactly.
#
# When both hullmods are present on one variant (illegal in vanilla per
# their own desc text -- "Can not work in conjunction with" -- but
# validation/legality.py, not this adapter or its consumer, is the only
# place that may enforce that), they target the same weapons' `range` via
# the same operation shape (percent_add) with different values -- see
# analysis/weapon_range_stats.py's `stacking_notes`, which applies the
# identical "report each contribution separately, never fabricate a
# combined value" discipline every other category above already
# established.
COMBAT_HULLMOD_EFFECTS: tuple[HullmodCombatEffect, ...] = (
    HullmodCombatEffect(
        hullmod_id="targetingunit", stat="range",
        applies_to_mount_types=frozenset({"BALLISTIC", "ENERGY"}),
        percent_bonus_by_hull_size=MappingProxyType({"FRIGATE": 0.10, "DESTROYER": 0.20, "CRUISER": 0.40, "CAPITAL_SHIP": 0.60}),
        citation="https://starsector.wiki.gg/wiki/Integrated_Targeting_Unit (2026-08-24): \"Extends the range of ballistic and energy weapons by 10%/20%/40%/60%, depending on hull size\" (frigate/destroyer/cruiser/capital). \"Can not work in conjunction with Dedicated Targeting Core\" -- a legality-layer pairwise-incompatibility concern, out of this adapter's/its consumer's scope. OP cost 4/8/15/25 cross-checked exactly against live install.",
    ),
    HullmodCombatEffect(
        hullmod_id="dedicated_targeting_core", stat="range",
        applies_to_mount_types=frozenset({"BALLISTIC", "ENERGY"}),
        percent_bonus_by_hull_size=MappingProxyType({"CRUISER": 0.35, "CAPITAL_SHIP": 0.50}),
        citation="https://starsector.wiki.gg/wiki/Dedicated_Targeting_Core (2026-08-24): \"Increases the range of ballistic and energy weapons by 35%/50% for cruisers/capital ships.\" \"Can not be installed on a frigate or a destroyer\" -- matches this installation's own cost_frigate=0/cost_dest=0 (only cost_cruiser=15/cost_capital=25 populated), so FRIGATE/DESTROYER are deliberately absent from percent_bonus_by_hull_size rather than populated with a guessed value. The S-mod-only 40%/60% bonus is not modeled (no S-mod concept exists on Variant). OP cost 15/25 (cruiser/capital) cross-checked exactly against live install.",
    ),
)


# Remaining real candidates researched 2026-08-24 (grepped the live CSV's
# desc column for "weapon range"/"rate of fire"/"damage"/"turn rate" plus
# every hullmod tagged "Weapons" in uiTags) and found NOT modelable here --
# investigated and deliberately excluded, each for a specific, documented
# reason. All OP costs and hidden flags below were cross-checked exactly
# against this installation's own parsed `Hullmod.op_cost_by_hull_size`
# and raw CSV `hidden` column before these conclusions were reached.
#
# - advancedoptics (Advanced Optics, OP 5/10/15/25): "Extends the range of
#   beam weapons by %s" -- a real per-weapon range effect, but restricted
#   to *beam* weapons specifically, a sub-category of ENERGY with no
#   corresponding typed field anywhere in this project (Weapon.mount_type
#   is only BALLISTIC/ENERGY/MISSILE/DECORATIVE; "beam" is only visible as
#   a free-text tag like "beam10"/"beam12" in the weapon CSV's `tags`
#   column, an untyped/unstructured raw field this project does not treat
#   as a reliable boolean signal). Its turn-rate-reduction effect has no
#   Weapon field either.
# - turretgyros (Advanced Turret Gyros, OP 2/4/6/10): turret turn rate --
#   no corresponding Weapon field.
# - armoredweapons (Armored Weapon Mounts, OP 3/6/9/15): its +10% armor
#   effect is already modeled under DEFENSE_HULLMOD_EFFECTS above; its
#   other three effects (weapon durability, recoil, weapon turn rate) have
#   no corresponding Weapon field.
# - missleracks (Expanded Missile Racks, OP 8/12/20/30): ammo capacity and
#   rate-of-fire -- no corresponding Weapon field for either.
# - hardenedshieldemitter, high_scatter_amp: already researched under
#   FLUX_HULLMOD_EXCLUDED_IDS above (shield damage reduction / beam range
#   reduction plus beam damage increase) -- re-confirmed here that neither
#   has a usable COMBAT-category effect either (high_scatter_amp's beam
#   range reduction has the same beam-detection problem as advancedoptics
#   above, and its damage increase has no Weapon field).
# - pointdefenseai (Integrated Point Defense AI, OP 3/6/9/15): flare
#   detection, target-leading, and a PD damage increase -- none is a
#   static per-weapon numeric stat this project tracks (damage increase
#   has no Weapon field; the rest are AI-behavior/targeting mechanics).
# - eccm (ECCM Package, OP 5/8/15/20): reduces the chance missiles are
#   affected by enemy ECM/flares -- CONDITIONAL on enemy electronic-warfare
#   presence, the same class of real-time-battlefield-state exclusion as
#   FLUX's fluxbreakers/phase_anchor.
# - escort_package (OP 0/7/15/0): its ballistic/energy weapon range bonus
#   is CONDITIONAL ("within approximately %s su of a larger friendly
#   vessel") -- already excluded once under MOBILITY_HULLMOD_EFFECTS'
#   researched-but-excluded notes above for the same reason.
# - advancedcore (Advanced Targeting Core), supercomputer (Targeting
#   Supercomputer), terminator_core (Terminator Core), distributed_fire_control
#   (Distributed Fire Control): each has a real, unconditional, "%s"-
#   templated weapon-range or weapon-durability effect in its desc column,
#   but all four have `hidden=TRUE` in the live CSV with cost_frigate/
#   cost_dest/cost_cruiser/cost_capital all 0 -- these are AI-core-granted
#   or built-in-only hullmods, never a player-installable choice a
#   generated variant would carry (same exclusion class as FLUX's
#   design_compromises/andrada_mods/etc. above).
COMBAT_HULLMOD_EXCLUDED_IDS: tuple[str, ...] = (
    "advancedoptics", "turretgyros", "missleracks", "high_scatter_amp",
    "pointdefenseai", "eccm", "escort_package",
    "advancedcore", "supercomputer", "terminator_core", "distributed_fire_control",
)
