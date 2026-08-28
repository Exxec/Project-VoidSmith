from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.heuristics import BASELINE_0_1, BASELINE_0_2, BASELINE_0_7, BASELINE_0_8, get_heuristic_set
from starsector_variant_generator.core.logging import configure_logging


class ConfigAndHeuristicTests(unittest.TestCase):
    def test_baseline_registry_matches_the_formal_specification(self) -> None:
        self.assertIs(BASELINE_0_1, get_heuristic_set("baseline_0.1"))
        self.assertEqual(250.0, BASELINE_0_1.values["range_mismatch_moderate"])
        self.assertEqual(400.0, BASELINE_0_1.values["range_mismatch_severe"])
        self.assertEqual(0.90, BASELINE_0_1.values["beginner_flux_target"])
        self.assertEqual(0.75, BASELINE_0_1.values["balanced_flux_target"])
        self.assertEqual(1.50, BASELINE_0_1.values["artillery_range_weight"])
        self.assertEqual(set(BASELINE_0_1.values), set(BASELINE_0_1.metadata))
        artillery_range = BASELINE_0_1.metadata["artillery_min_range"]
        self.assertEqual("threshold", artillery_range.kind)
        self.assertEqual("game range units", artillery_range.units)
        # baseline_0.1 is immutable: it must never gain the scoring-weight
        # keys baseline_0.2 introduces, or old reports tagged baseline_0.1
        # would stop being reproducible from the identifier alone.
        self.assertNotIn("weight_flux_sustainability", BASELINE_0_1.values)

    def test_baseline_0_2_adds_flux_and_doctrine_weights_without_changing_targets(self) -> None:
        self.assertIs(BASELINE_0_2, get_heuristic_set("baseline_0.2"))
        self.assertEqual(set(BASELINE_0_2.values), set(BASELINE_0_2.metadata))
        # Flux targets are unchanged from baseline_0.1 -- only their role
        # changes (documented-only there, actively consumed here).
        for key in ("beginner_flux_target", "balanced_flux_target", "aggressive_flux_target"):
            self.assertEqual(BASELINE_0_1.values[key], BASELINE_0_2.values[key])
        self.assertAlmostEqual(1.0, sum(BASELINE_0_2.values[key] for key in (
            "weight_range_coherence", "weight_op_efficiency", "weight_role_match",
            "weight_flux_sustainability", "weight_faction_doctrine",
        )))

    def test_baseline_0_8_is_byte_identical_to_baseline_0_7_except_the_flux_gate(self) -> None:
        # baseline_0.8 must only add the new opt-in FLUX-hullmod-adjustment
        # gate flag; every value baseline_0.7 already defines must be
        # untouched, so any report tagged baseline_0.7 (or earlier) stays
        # byte-for-byte reproducible after this change.
        self.assertIs(BASELINE_0_8, get_heuristic_set("baseline_0.8"))
        self.assertEqual(set(BASELINE_0_8.values), set(BASELINE_0_8.metadata))
        extra_keys = set(BASELINE_0_8.values) - set(BASELINE_0_7.values)
        self.assertEqual({"flux_hullmod_adjustment_enabled"}, extra_keys)
        for key in BASELINE_0_7.values:
            self.assertEqual(BASELINE_0_7.values[key], BASELINE_0_8.values[key])
        self.assertEqual(1.0, BASELINE_0_8.values["flux_hullmod_adjustment_enabled"])
        self.assertEqual("flag", BASELINE_0_8.metadata["flux_hullmod_adjustment_enabled"].kind)

    def test_shipped_default_heuristic_set_stays_baseline_0_7_not_the_new_baseline_0_8(self) -> None:
        # baseline_0.8's FLUX-hullmod-adjusted scoring is available but
        # opt-in only (a caller must pass heuristic_set="baseline_0.8"
        # explicitly) -- adding the registry entry must not silently
        # change what an unconfigured run scores against.
        config = AppConfig(Path("starsector"), Path("out"), Path("logs"))
        self.assertEqual("baseline_0.7", config.heuristic_set)

    def test_configuration_and_logging_write_only_to_configured_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.toml"
            config_path.write_text('starsector_path = "C:/Games/Starsector"\noutput_dir = "out"\nlog_dir = "logs"\n', encoding="utf-8")
            config = AppConfig.from_toml(config_path)
            self.assertEqual("baseline_0.7", config.heuristic_set)
            logger = configure_logging(config.log_dir)
            logger.info("fixture logging")
            for handler in logger.handlers:
                handler.close()
            logger.handlers.clear()
            self.assertIn("fixture logging", (root / "logs/svg.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
