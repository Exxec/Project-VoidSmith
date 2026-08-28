"""Resolve local calibration scenarios without rewriting source expectations.

Both the earlier record list and the richer ship/scenario profile document are
accepted. Source-mentioned equipment remains separately represented from legal
``INFERRED_SCENARIO_OPTION`` candidates generated from local scanned mechanics.
"""
from __future__ import annotations

import argparse, json, re
from pathlib import Path
from typing import Any, Iterable

from starsector_variant_generator import api
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.scanner import Scanner

PROFILE_BY_HINT = (
    ("LINE_ARTILLERY", "LINE_ARTILLERY"), ("MISSILE_SUPPORT", "MISSILE_SUPPORT"),
    ("PD_ESCORT", "PD_ESCORT"), ("CARRIER", "CARRIER_SUPPORT"),
    ("ARMOR_TANKING", "TANK"), ("TANK", "TANK"),
    ("AGGRESSIVE_SHORT_RANGE", "FAST_STRIKE"),
)
PROFILE_BY_SCENARIO = {
    "PD_SCREEN": "PD_ESCORT", "LONG_RANGE_SUPPORT": "LINE_ARTILLERY",
    "LINE_HOLDING": "LINE_BRAWLER", "CLOSE_ASSAULT": "FAST_STRIKE",
    "MISSILE_STRIKE": "MISSILE_SUPPORT", "CARRIER_OPERATIONS": "CARRIER_SUPPORT",
    "CARRIER_SUPPORT": "CARRIER_SUPPORT",
}

def _name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", value)).replace("*", "").strip().casefold()

def _unique_by_name(entities: Iterable[Any]) -> dict[str, Any]:
    groups: dict[str, list[Any]] = {}
    for entity in entities: groups.setdefault(_name(entity.name), []).append(entity)
    return {key: values[0] for key, values in groups.items() if len(values) == 1}

def _explicit_matches(text: str, entities: Iterable[Any]) -> list[dict[str, str]]:
    haystack=text.casefold(); matches=[]
    for entity in sorted(entities, key=lambda item: len(item.name), reverse=True):
        name=entity.name.casefold()
        # Text-only provenance is deliberately conservative. A one- or two-
        # character entity display name (for example ``p``) is not meaningful
        # evidence when it happens to occur in prose such as "max armor".
        if len(name) >= 3 and re.search(r"(?<!\\w)" + re.escape(name) + r"(?!\\w)", haystack):
            matches.append({"id":entity.id,"name":entity.name,"source_mod":entity.source_mod})
    return matches

def _named_matches(names: Iterable[Any], entities: Iterable[Any]) -> tuple[list[dict[str, str]], list[str]]:
    by_name = _unique_by_name(entities); found=[]; unresolved=[]
    for raw_name in names:
        name=str(raw_name); entity=by_name.get(_name(name))
        if entity is None: unresolved.append(name)
        else: found.append({"id":entity.id,"name":entity.name,"source_mod":entity.source_mod})
    return found, unresolved

def _scenario_records(seed: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten either supported guide format while retaining original objects."""
    old_records=seed.get("calibration_records")
    if isinstance(old_records,list): return [record for record in old_records if isinstance(record,dict)]
    records=[]
    for ship in seed.get("ship_profiles",[]):
        if not isinstance(ship,dict): continue
        for scenario in ship.get("scenario_profiles",[]):
            if not isinstance(scenario,dict): continue
            records.append({
                "ship_display":ship.get("ship_display",""), "normalized_archetype_hints":ship.get("archetype_hints",[]),
                "weapons_source_explicit":ship.get("weapons_source_explicit",[]), "hullmods_source_explicit":ship.get("hullmods_source_explicit",[]),
                "loadouts_source_raw":ship.get("loadouts_source_raw",[]), "faction_context":ship.get("faction_context"),
                "fleet_scope":ship.get("fleet_scope"), "scenario_profile":scenario, "source_profile":ship,
            })
    return records

def _profile_for(record: dict[str, Any]) -> str:
    scenario=record.get("scenario_profile")
    if isinstance(scenario,dict):
        mapped=PROFILE_BY_SCENARIO.get(str(scenario.get("scenario","")))
        if mapped: return mapped
    hints=record.get("normalized_archetype_hints",[])
    return next((profile for hint,profile in PROFILE_BY_HINT if hint in hints),"LINE_BRAWLER")

def _source_explicit(record: dict[str, Any], weapons: Iterable[Any], hullmods: Iterable[Any]) -> dict[str, Any]:
    scenario=record.get("scenario_profile") if isinstance(record.get("scenario_profile"),dict) else {}
    raw_loadouts=record.get("loadouts_source_raw",[])
    if not isinstance(raw_loadouts,list): raw_loadouts=[str(raw_loadouts)]
    legacy_text=str(record.get("loadout_text","")); raw_loadouts=[str(item) for item in raw_loadouts]
    weapon_names=[*record.get("weapons_source_explicit",[]),*scenario.get("preferred_weapons_source_explicit",[])]
    hullmod_names=[*record.get("hullmods_source_explicit",[]),*scenario.get("preferred_hullmods_source_explicit",[])]
    named_weapons,unresolved_weapons=_named_matches(weapon_names,weapons)
    named_hullmods,unresolved_hullmods=_named_matches(hullmod_names,hullmods)
    text="\n".join([*raw_loadouts,legacy_text])
    return {"resolution":"SOURCE_EXPLICIT", "loadout_text":legacy_text, "loadouts_source_raw":raw_loadouts,
            "weapons":named_weapons or _explicit_matches(text,weapons), "hullmods":named_hullmods or _explicit_matches(text,hullmods),
            "unresolved_weapon_mentions":unresolved_weapons, "unresolved_hullmod_mentions":unresolved_hullmods,
            "scenario_basis":scenario.get("basis"), "source_review_status":scenario.get("review_status",record.get("review_status"))}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("seed",type=Path); parser.add_argument("--starsector-path",type=Path,required=True); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args()
    seed=json.loads(args.seed.read_text(encoding="utf-8")); records=_scenario_records(seed)
    scan=Scanner(args.starsector_path).scan(); registry=Registry.from_scan(scan); hulls=_unique_by_name(scan.hulls)
    resolved=[]; skipped=[]
    for index, record in enumerate(records):
        hull=hulls.get(_name(str(record.get("ship_display",""))))
        if hull is None: skipped.append({"record_index":index,"ship_display":record.get("ship_display"),"reason":"UNRESOLVED_OR_AMBIGUOUS_LOCAL_HULL"}); continue
        profile=_profile_for(record); source_explicit=_source_explicit(record,scan.weapons,scan.hullmods)
        outcome=api.run_generate(registry,"baseline_0.2",hull.id,"guided",profile=profile,faction_mode="UNRESTRICTED",max_candidates=3)
        inferred=[]
        for candidate in outcome.assessed_candidates:
            variant=candidate["variant"]
            inferred.append({"resolution":"INFERRED_SCENARIO_OPTION","profile":profile,"equipment_access_policy":"UNRESTRICTED_NO_FACTION_ASSERTION","weapons_by_mount":variant["weapons_by_mount"],"hullmods":variant["hullmods"],"legality":candidate["legality"],"score":candidate["quality"]["final_score"]})
        inferred_ids={item for option in inferred for item in (*option["weapons_by_mount"].values(),*option["hullmods"])}
        explicit_ids={item["id"] for item in [*source_explicit["weapons"],*source_explicit["hullmods"]]}
        resolved.append({"record_index":index,"hull":{"id":hull.id,"source_mod":hull.source_mod,"source_hash":hull.source_hash},"faction_context":record.get("faction_context"),"fleet_scope":record.get("fleet_scope"),"source_profile":record.get("source_profile",record),"scenario_profile":record.get("scenario_profile"),"source_explicit":source_explicit,"inferred_scenario_options":inferred,"comparison":{"recognized_source_equipment":sorted(explicit_ids),"inferred_overlap":sorted(explicit_ids & inferred_ids),"source_equipment_not_selected":sorted(explicit_ids-inferred_ids)}})
    output={"schema_version":"scenario-calibration-resolution-0.2","seed_status":seed.get("status"),"source_contract":seed.get("contract"),"policy":"SOURCE_EXPLICIT is preserved; inferred options are separate, generated from local scanned mechanics, and never alter source expectations or assert faction ownership.","resolved":resolved,"skipped":skipped}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(output,indent=2,sort_keys=True),encoding="utf-8")
    print(f"Resolved {len(resolved)} scenarios; skipped {len(skipped)} unambiguous-hull failures.")
    return 0
if __name__=="__main__": raise SystemExit(main())
