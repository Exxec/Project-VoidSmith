from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from starsector_variant_generator.analysis.hullmod_static_analysis import analyze_hullmod_sources
from starsector_variant_generator.core.models import Hullmod
class HullmodStaticAnalysisTests(unittest.TestCase):
 def test_compiled_only_declared_script_is_distinguished(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); (root/"opaque.jar").write_bytes(b"not executed")
   mod=Hullmod("opaque","Opaque","mod",root/"data"/"hullmods"/"hull_mods.csv",raw={"script":"data.hullmods.Opaque"})
   result=analyze_hullmod_sources(mod,root)
   self.assertEqual("COMPILED_ONLY_SCRIPT",result.analysis_state)
   self.assertEqual("UNAVAILABLE",result.static_effect_coverage)
   self.assertEqual("COMPILED_ONLY_SCRIPT",result.source_association)

 def test_recognizes_documented_weapon_flux_modifier(self):
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp); (source/"Flux.java").write_text('class Flux { void apply(MutableShipStatsAPI stats) { stats.getEnergyWeaponFluxCostMod().modifyPercent(id, -10f); } }',encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("flux","Flux","m",Path("h"),raw={"script":"Flux"}),source)
   self.assertEqual("energy_weapon_flux_cost",result.recognized_effects[0].target_stat)
 def test_recognizes_known_literal_api_effect_and_preserves_unknown(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); source=root/"data"/"scripts"; source.mkdir(parents=True)
   (source/"Mod.java").write_text('class Mod { void apply(MutableShipStatsAPI stats) {\n stats.getMaxSpeed().modifyFlat(id, 20f);\n stats.getCustom().modifyFoo(id, x);\n } }',encoding="utf-8")
   mod=Hullmod("mod","Mod","x",root/"data"/"hullmods"/"hull_mods.csv",raw={"script":"Mod"})
   result=analyze_hullmod_sources(mod,root)
   self.assertEqual("DECLARED_SCRIPT_CLASS", result.source_association)
   self.assertEqual("max_speed",result.recognized_effects[0].target_stat); self.assertEqual(20.0,result.recognized_effects[0].numeric_value); self.assertTrue(result.unknown_scripted_portions)
   self.assertEqual("HULLMOD_EFFECT", result.evidence[0].evidence_type)
   self.assertEqual("LOCAL_SOURCE_CODE", result.evidence[0].evidence_class)
   self.assertEqual("Mod", result.evidence[0].source_class)

 def test_declared_script_class_excludes_unrelated_id_references(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); source=root/"src"; source.mkdir(parents=True)
   (source/"Actual.java").write_text('class Actual { void apply(MutableShipStatsAPI stats) { stats.getMaxSpeed().modifyFlat(id, 20f); } }',encoding="utf-8")
   (source/"Unrelated.java").write_text('class Unrelated { String id = "mod"; void apply(MutableShipStatsAPI stats) { stats.getFluxCapacity().modifyFlat(id, 9000f); } }',encoding="utf-8")
   mod=Hullmod("mod","Mod","x",root/"data"/"hullmods"/"hull_mods.csv",raw={"script":"data.hullmods.Actual"})
   result=analyze_hullmod_sources(mod,root)
   self.assertEqual("DECLARED_SCRIPT_CLASS", result.source_association)
   self.assertEqual(1, len(result.source_files))
   self.assertEqual("max_speed", result.recognized_effects[0].target_stat)

 def test_recognized_no_effect_class_retains_unknown_remainder(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); source=root/"src"; source.mkdir(parents=True)
   (source/"Custom.java").write_text('class Custom { void apply() { doSomethingCustom(); } }',encoding="utf-8")
   mod=Hullmod("custom","Custom","x",root/"data"/"hullmods"/"hull_mods.csv",raw={"script":"Custom"})
   result=analyze_hullmod_sources(mod,root)
   self.assertEqual("DECLARED_SCRIPT_CLASS", result.source_association)
   self.assertFalse(result.recognized_effects)
   self.assertTrue(result.unknown_scripted_portions)

 def test_records_simple_hull_size_branch_without_assuming_other_control_flow(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); source=root/"src"; source.mkdir(parents=True)
   (source/"Sized.java").write_text('class Sized { void apply(MutableShipStatsAPI stats) {\n if (ship.getHullSize() == ShipAPI.HullSize.CRUISER) {\n stats.getArmorBonus().modifyFlat(id, 250f);\n }\n } }',encoding="utf-8")
   mod=Hullmod("sized","Sized","x",root/"data"/"hullmods"/"hull_mods.csv",raw={"script":"Sized"})
   effect=analyze_hullmod_sources(mod,root).recognized_effects[0]
   self.assertEqual("CRUISER", effect.hull_size)
   self.assertEqual("ShipAPI.HullSize.CRUISER", effect.condition)

 def test_resolves_constant_expression_built_from_two_local_constants(self):
  # Mirrors a real pattern found across the local installed-mod sweep this
  # phase measured (e.g. "1f - (0.01f * RECOIL_BONUS)"): a multiplicative
  # sub-expression folded against a locally declared constant, not a bare
  # literal or single identifier -- exercises the new sub-tier-2 path.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Recoil.java").write_text(
    'class Recoil { static final float RECOIL_BONUS = 50f; '
    'void apply(MutableShipStatsAPI stats) { '
    'stats.getFluxDissipation().modifyMult(id, 1f - (0.01f * RECOIL_BONUS)); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("recoil","Recoil","m",Path("h"),raw={"script":"Recoil"}),source)
   self.assertEqual(1, len(result.recognized_effects))
   effect=result.recognized_effects[0]
   self.assertAlmostEqual(0.5, effect.numeric_value)
   self.assertEqual("MULTIPLY", effect.operation)
   self.assertAlmostEqual(0.85, effect.confidence)
   self.assertAlmostEqual(0.85, result.evidence[0].confidence)

 def test_resolves_constant_expression_with_addition_and_division(self):
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Vent.java").write_text(
    'class Vent { static final float VENT_RATE_BONUS = 25f; '
    'void apply(MutableShipStatsAPI stats) { '
    'stats.getFluxDissipation().modifyPercent(id, VENT_RATE_BONUS / 100f); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("vent","Vent","m",Path("h"),raw={"script":"Vent"}),source)
   self.assertEqual(1, len(result.recognized_effects))
   self.assertAlmostEqual(0.25, result.recognized_effects[0].numeric_value)

 def test_does_not_guess_expression_referencing_a_runtime_variable(self):
  # A parameter/field/local variable (never declared as a local constant)
  # must never be treated as resolvable, even inside an otherwise-familiar
  # arithmetic shape -- this is the same real pattern the local sweep found
  # (e.g. "MANEUVER_BONUS_ACCEL * effectLevel") that must stay unresolved.
  # Phase 38 round 2: this call site DID match a registered `_CALLS` accessor
  # (getAcceleration), so the unresolved remainder is now UNSUPPORTED, not
  # UNKNOWN -- a pure re-classification of the same unresolved fact.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Scaled.java").write_text(
    'class Scaled { static final float MANEUVER_BONUS = 100f; '
    'void apply(MutableShipStatsAPI stats, float effectLevel) { '
    'stats.getAcceleration().modifyPercent(id, MANEUVER_BONUS * effectLevel); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("scaled","Scaled","m",Path("h"),raw={"script":"Scaled"}),source)
   self.assertFalse(result.recognized_effects)
   self.assertFalse(result.unknown_scripted_portions)
   self.assertTrue(any("not statically resolvable" in item for item in result.unsupported_scripted_portions))
   self.assertTrue(any(item.startswith("UNSUPPORTED_SCRIPTED_EFFECT:") for item in result.unsupported_scripted_portions))

 def test_does_not_guess_expression_referencing_cross_file_constant_without_a_class_qualifier(self):
  # A *bare* (unqualified) name resolved only via a Java `import static`
  # remains a genuinely unimplemented pattern even after Phase 38 round 2's
  # qualified `ClassName.CONSTANT` cross-file resolution (see the
  # `test_resolves_qualified_cross_file_constant*` tests below) -- confirms
  # the new cross-file table is reached only through an explicit qualifier,
  # never a bare name, so this stays unresolved (now UNSUPPORTED, since the
  # call site still matched a registered accessor).
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Shared.java").write_text('class Shared { static final float BONUS = 40f; }',encoding="utf-8")
   (source/"CrossRef.java").write_text(
    'class CrossRef { void apply(MutableShipStatsAPI stats) { '
    'stats.getMaxSpeed().modifyFlat(id, 1f + BONUS); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("crossref","CrossRef","m",Path("h"),raw={"script":"CrossRef"}),source)
   self.assertFalse(result.recognized_effects)
   self.assertFalse(result.unknown_scripted_portions)
   self.assertTrue(any("not statically resolvable" in item for item in result.unsupported_scripted_portions))

 def test_resolves_qualified_cross_file_constant_declared_in_a_different_local_file(self):
  # The real pattern Phase 38 round 2 closes: a shared "Constants"-style
  # class declared in a *different* .java file within the same mod root,
  # referenced via an explicit ClassName.CONSTANT qualifier -- e.g. the
  # task's own cited real-world shape "Constants.HULL_PENALTY". Same source
  # root, different file: must now resolve, at the new, lower CROSS_FILE
  # confidence tier (0.75) rather than the same-file tiers (0.9/0.85).
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Constants.java").write_text('class Constants { public static final float HULL_PENALTY = 25f; }',encoding="utf-8")
   (source/"AF_OpenAmmoDepot.java").write_text(
    'class AF_OpenAmmoDepot { void apply(MutableShipStatsAPI stats) { '
    'stats.getHullBonus().modifyPercent(id, -Constants.HULL_PENALTY); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("af_openammodepot","Depot","m",Path("h"),raw={"script":"AF_OpenAmmoDepot"}),source)
   self.assertEqual(1, len(result.recognized_effects))
   effect=result.recognized_effects[0]
   self.assertEqual("hull_hp", effect.target_stat)
   self.assertAlmostEqual(-25.0, effect.numeric_value)
   self.assertAlmostEqual(0.75, effect.confidence)
   self.assertAlmostEqual(0.75, result.evidence[0].confidence)

 def test_resolves_qualified_cross_file_constant_combined_with_a_same_file_constant(self):
  # A cross-file qualified reference combined with a same-file constant in
  # one expression must still be tagged CROSS_FILE overall (the lower of
  # the two tiers involved), not silently upgraded to the same-file
  # EXPRESSION tier just because part of the expression was local.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Constants.java").write_text('class Constants { static final float BASE_BONUS = 10f; }',encoding="utf-8")
   (source/"Mixed.java").write_text(
    'class Mixed { static final float LOCAL_BONUS = 5f; '
    'void apply(MutableShipStatsAPI stats) { '
    'stats.getMaxSpeed().modifyFlat(id, Constants.BASE_BONUS + LOCAL_BONUS); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("mixed","Mixed","m",Path("h"),raw={"script":"Mixed"}),source)
   self.assertEqual(1, len(result.recognized_effects))
   effect=result.recognized_effects[0]
   self.assertAlmostEqual(15.0, effect.numeric_value)
   self.assertAlmostEqual(0.75, effect.confidence)

 def test_does_not_resolve_a_qualifier_naming_a_class_this_source_root_never_declares(self):
  # A qualifier that looks like ClassName.CONSTANT but names a class no
  # local .java file under this source root declares at all (e.g. a
  # genuinely different mod's class, or a typo) must never be guessed --
  # confirms the cross-file table's lookup fails closed.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Lonely.java").write_text(
    'class Lonely { void apply(MutableShipStatsAPI stats) { '
    'stats.getMaxSpeed().modifyFlat(id, OtherMod.SOME_CONSTANT); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("lonely","Lonely","m",Path("h"),raw={"script":"Lonely"}),source)
   self.assertFalse(result.recognized_effects)
   self.assertTrue(any("not statically resolvable" in item for item in result.unsupported_scripted_portions))

 def test_bare_literal_and_bare_constant_still_report_original_high_confidence(self):
  # Regression guard: sub-tier 1 (bare literal / single declared constant)
  # must keep its original 0.9 confidence unchanged by the new sub-tier 2
  # (expression folding) path added alongside it.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Plain.java").write_text(
    'class Plain { static final float SPEED_BONUS = 30f;\n'
    'void apply(MutableShipStatsAPI stats) {\n'
    'stats.getMaxSpeed().modifyFlat(id, 20f);\n'
    'stats.getAcceleration().modifyPercent(id, SPEED_BONUS);\n'
    '} }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("plain","Plain","m",Path("h"),raw={"script":"Plain"}),source)
   self.assertEqual(2, len(result.recognized_effects))
   for effect in result.recognized_effects:
    self.assertAlmostEqual(0.9, effect.confidence)

 def test_recognizes_newly_registered_weapon_rate_of_fire_and_range_bonus_accessors(self):
  # Phase 38 round 2: real, documented `-0.4` registry additions
  # (getBallisticRoFMult/getEnergyWeaponRangeBonus), the two highest-real-
  # frequency new accessors measured against the local install sweep.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Gunner.java").write_text(
    'class Gunner { void apply(MutableShipStatsAPI stats) {\n'
    'stats.getBallisticRoFMult().modifyPercent(id, 15f);\n'
    'stats.getEnergyWeaponRangeBonus().modifyPercent(id, 10f);\n'
    '} }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("gunner","Gunner","m",Path("h"),raw={"script":"Gunner"}),source)
   stats={effect.target_stat: effect for effect in result.recognized_effects}
   self.assertEqual(2, len(result.recognized_effects))
   self.assertAlmostEqual(15.0, stats["ballistic_weapon_rate_of_fire"].numeric_value)
   self.assertAlmostEqual(10.0, stats["energy_weapon_range"].numeric_value)
   for effect in result.recognized_effects:
    self.assertAlmostEqual(0.9, effect.confidence)
    self.assertEqual("starsector-api-effects-0.4", effect.api_registry_version)

 def test_recognizes_max_combat_readiness_matching_real_vanilla_automated_pattern(self):
  # Mirrors the real vanilla `Automated.java` call this registry addition
  # was directly verified against:
  # `stats.getMaxCombatReadiness().modifyFlat(id, -MAX_CR_PENALTY, "...")`
  # -- including the optional third string-description argument, already
  # supported by the existing `call_args[1]`-only extraction.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Automated.java").write_text(
    'class Automated { public static final float MAX_CR_PENALTY = 100f; '
    'void apply(MutableShipStatsAPI stats) { '
    'stats.getMaxCombatReadiness().modifyFlat(id, -MAX_CR_PENALTY, "Automated ship penalty"); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("automated","Automated","m",Path("h"),raw={"script":"Automated"}),source)
   self.assertEqual(1, len(result.recognized_effects))
   effect=result.recognized_effects[0]
   self.assertEqual("max_combat_readiness", effect.target_stat)
   self.assertAlmostEqual(-100.0, effect.numeric_value)

 def test_unregistered_accessor_stays_unknown_not_unsupported(self):
  # The genuine UNKNOWN/UNSUPPORTED boundary: a `stats.getX().modifyY(...)`
  # call whose accessor the registry has no `_CALLS` entry for at all must
  # stay UNKNOWN (the registry never recognized it), never UNSUPPORTED
  # (reserved for a call the registry DID recognize but couldn't resolve).
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Exotic.java").write_text(
    'class Exotic { void apply(MutableShipStatsAPI stats) { '
    'stats.getSomeNeverRegisteredStat().modifyFlat(id, 5f); } }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("exotic","Exotic","m",Path("h"),raw={"script":"Exotic"}),source)
   self.assertFalse(result.recognized_effects)
   self.assertFalse(result.unsupported_scripted_portions)
   self.assertTrue(any(item.startswith("UNKNOWN_SCRIPTED_EFFECT:") for item in result.unknown_scripted_portions))

 def test_unsupported_portion_does_not_downgrade_confidence_below_effects_only_case(self):
  # A class with one fully-resolved effect and one UNSUPPORTED (registry-
  # recognized-but-unresolved) remainder must land at the same partial
  # (0.6) confidence tier a class with an UNKNOWN remainder already used --
  # unsupported is still "not fully understood", not silently ignored.
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)
   (source/"Partial.java").write_text(
    'class Partial { void apply(MutableShipStatsAPI stats, float runtimeVar) {\n'
    'stats.getMaxSpeed().modifyFlat(id, 20f);\n'
    'stats.getAcceleration().modifyPercent(id, runtimeVar);\n'
    '} }',
    encoding="utf-8")
   result=analyze_hullmod_sources(Hullmod("partial","Partial","m",Path("h"),raw={"script":"Partial"}),source)
   self.assertEqual(1, len(result.recognized_effects))
   self.assertTrue(result.unsupported_scripted_portions)
   self.assertFalse(result.unknown_scripted_portions)
   self.assertAlmostEqual(0.6, result.confidence)

if __name__=="__main__": unittest.main()
