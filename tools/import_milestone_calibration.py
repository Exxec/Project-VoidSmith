"""Import reviewer milestone-table hull roles as hash-bound soft expectations."""
from __future__ import annotations

import argparse, json, re
from pathlib import Path
from starsector_variant_generator.core.scanner import Scanner

ROLE_MAP = (("carrier", ("CARRIER_SUPPORT", "BATTLECARRIER")), ("pd", ("PD_ESCORT",)), ("escort", ("PD_ESCORT", "LINE_ANCHOR")), ("artillery", ("ARTILLERY",)), ("fire support", ("ARTILLERY",)), ("missile", ("MISSILE_SUPPORT",)), ("anchor", ("LINE_ANCHOR", "TANK")), ("brawler", ("TANK", "FINISHER")), ("assault", ("FINISHER", "TANK")), ("striker", ("FINISHER",)))

def clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", re.sub(r"[*_`\"]", "", value))).strip().casefold()

def main() -> int:
    # Default points at the gitignored generated/ tree, not docs/: these
    # guide files carry real, copied mod/ship/faction content and must
    # never end up in a committed/distributed path (see CLAUDE.md's
    # distribution boundary; docs/*.txt guides and their derived seed/
    # review files were relocated to generated/calibration/sources/ for
    # exactly this reason).
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--starsector-path",type=Path,required=True); parser.add_argument("--docs-dir",type=Path,default=Path("generated/calibration/sources")); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args()
    scan=Scanner(args.starsector_path).scan(); by_name={}
    for hull in scan.hulls: by_name.setdefault(clean(hull.name),[]).append(hull)
    labels=[]; skipped=[]
    for text_path in sorted(args.docs_dir.glob("*.txt")):
      for line_no,line in enumerate(text_path.read_text(encoding="utf-8",errors="replace").splitlines(),1):
       cells=[cell.strip() for cell in line.strip().strip("|").split("|")]
       if len(cells)<3 or not line.lstrip().startswith("|"): continue
       role=cells[2].casefold(); builds=next((builds for keyword,builds in ROLE_MAP if keyword in role),None)
       if not builds: continue
       matches=by_name.get(clean(cells[0]),[])
       if len(matches)!=1: skipped.append({"file":text_path.name,"line":line_no,"hull":cells[0],"reason":"unmatched_or_ambiguous"}); continue
       hull=matches[0]
       if not hull.source_hash: skipped.append({"file":text_path.name,"line":line_no,"hull":cells[0],"reason":"missing_hash"}); continue
       labels.append({"entity_key":f"hull:{hull.source_mod}:{hull.id}","entity_hash":hull.source_hash,"label":f"MILESTONE_ROLE:{role}","expected":builds[0],"expected_any":list(builds),"strength":"SOFT_EXPECTATION","note":f"Reviewer milestone role in {text_path.name}:{line_no}"})
    unique={ (x["entity_key"],tuple(x["expected_any"])):x for x in labels }
    result={"schema_version":"calibration-labels-0.1","fixture_id":"reviewer-milestone-import","labels":list(unique.values()),"skipped":skipped}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(f"Imported {len(unique)} soft expectations; skipped {len(skipped)} unmatched/ambiguous rows."); return 0
if __name__=="__main__": raise SystemExit(main())
