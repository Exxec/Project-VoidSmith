from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starsector_variant_generator.analysis.acceptance_baseline import (
    baseline_from_audit,
    compare_with_baseline,
    format_change,
    load_baseline,
    run_acceptance,
)
from starsector_variant_generator.cli import main as cli_main
from starsector_variant_generator.core.models import Hull, ModInfo, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


def scan_with(second_variant_weapon: str = "gun", version: str = "1") -> ScanResult:
    mods = [ModInfo(f"mod_{name}", name.title(), version, Path(f"mods/{name}"), True) for name in ("a", "b", "c")]
    hulls = [Hull(f"hull_{name}", name, f"mod_{name}", SOURCE, hull_size="FRIGATE") for name in ("a", "b", "c")]
    weapons = [Weapon("gun", "Gun", "mod_a", SOURCE)]
    variants = [
        Variant("va", "A", "mod_a", SOURCE, hull_id="hull_a", weapons_by_mount={"WS1": "gun"}),
        Variant("vb", "B", "mod_b", SOURCE, hull_id="hull_b", weapons_by_mount={"WS1": second_variant_weapon}),
        Variant("vc", "C", "mod_c", SOURCE, hull_id="hull_c"),
    ]
    return ScanResult(mods=mods, hulls=hulls, weapons=weapons, variants=variants)


def audit_of(scan: ScanResult, **kwargs: object) -> dict:
    return run_acceptance(scan, Registry.from_scan(scan), **kwargs)  # type: ignore[arg-type]


class AcceptanceBaselineTests(unittest.TestCase):
    def test_chunked_run_matches_the_single_pass_audit_and_reports_each_mod(self) -> None:
        from starsector_variant_generator.analysis.mod_acceptance import audit_mod_acceptance
        scan = scan_with()
        seen: list[tuple[int, int, str]] = []
        audit = audit_of(scan, chunk_size=2, progress=lambda i, n, mod, _c, _s: seen.append((i, n, mod)))
        direct = audit_mod_acceptance(scan, Registry.from_scan(scan))
        self.assertEqual(direct["records"], audit["records"])
        self.assertEqual([(1, 3, "mod_a"), (2, 3, "mod_b"), (3, 3, "mod_c")], seen)

    def test_only_changes_against_a_baseline_are_reported(self) -> None:
        old = baseline_from_audit(audit_of(scan_with()))
        same = compare_with_baseline(old, baseline_from_audit(audit_of(scan_with())))
        self.assertEqual([], same)
        broken = baseline_from_audit(audit_of(scan_with(second_variant_weapon="vanished_gun", version="2")))
        changes = compare_with_baseline(old, broken)
        self.assertEqual(["mod_b"], [c["mod_id"] for c in changes])  # a version bump alone is not a change
        changed_b = next(c for c in changes if c["mod_id"] == "mod_b")
        self.assertTrue(changed_b["regression"])
        self.assertIn("UNRESOLVED_REFERENCES", changed_b["codes_added"])
        self.assertIn("[REGRESSION]", format_change(changed_b))
        self.assertEqual(("1", "2"), (changed_b["version_from"], changed_b["version_to"]))

    def test_added_and_removed_mods_are_changes(self) -> None:
        full = baseline_from_audit(audit_of(scan_with()))
        trimmed = {**full, "mods": {k: v for k, v in full["mods"].items() if k != "mod_c"}}
        kinds = {c["change"] for c in compare_with_baseline(trimmed, full)} | {c["change"] for c in compare_with_baseline(full, trimmed)}
        self.assertEqual({"ADDED", "REMOVED"}, kinds)

    def test_a_checkpoint_resumes_finished_mods_and_is_deleted_at_the_end(self) -> None:
        scan = scan_with()
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "run.partial.jsonl"
            with mock.patch("starsector_variant_generator.analysis.acceptance_baseline.audit_mod_acceptance", wraps=None) as fake:
                from starsector_variant_generator.analysis import mod_acceptance as real
                calls: list[frozenset[str] | None] = []

                def interrupted(*a: object, **k: object) -> dict:
                    calls.append(k.get("only_mod_ids"))  # type: ignore[arg-type]
                    if len(calls) == 2:
                        raise KeyboardInterrupt
                    return real.audit_mod_acceptance(*a, **k)  # type: ignore[arg-type]
                fake.side_effect = interrupted
                with self.assertRaises(KeyboardInterrupt):
                    audit_of(scan, chunk_size=1, checkpoint_path=checkpoint)
            self.assertTrue(checkpoint.exists())
            audit = audit_of(scan, chunk_size=1, checkpoint_path=checkpoint)
            self.assertEqual(["mod_a"], audit["resumed_mods"])
            self.assertEqual(3, len(audit["records"]))
            self.assertFalse(checkpoint.exists())

    def test_a_checkpoint_from_different_inputs_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "run.partial.jsonl"
            checkpoint.write_text(json.dumps({"schema": "other"}) + "\n" + json.dumps({"records": [{"mod_id": "mod_a"}]}) + "\n", encoding="utf-8")
            self.assertEqual([], audit_of(scan_with(), checkpoint_path=checkpoint)["resumed_mods"])

    def test_baseline_file_must_have_the_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self.assertIsNone(load_baseline(path))
            path.write_text('{"schema_version": "nope"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_baseline(path)

    def test_the_command_records_then_compares_and_exits_nonzero_on_regression(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out, baseline = Path(tmp) / "out", Path(tmp) / "base.json"
            argv = ["voidsmith", "acceptance", "--starsector-path", tmp, "--output-dir", str(out), "--baseline", str(baseline), "--quiet"]
            target = "starsector_variant_generator.cli.automation_commands.Scanner"
            with mock.patch("sys.argv", [*argv, "--write-baseline"]), mock.patch(target) as scanner:
                scanner.return_value.scan.return_value = scan_with()
                self.assertEqual(0, cli_main.main())
            self.assertTrue(baseline.is_file())
            with mock.patch("sys.argv", argv), mock.patch(target) as scanner:
                scanner.return_value.scan.return_value = scan_with()
                self.assertEqual(0, cli_main.main())
            with mock.patch("sys.argv", argv), mock.patch(target) as scanner:
                scanner.return_value.scan.return_value = scan_with(second_variant_weapon="vanished_gun")
                self.assertEqual(1, cli_main.main())
            self.assertEqual(3, len(json.loads(baseline.read_text(encoding="utf-8"))["mods"]))


if __name__ == "__main__":
    unittest.main()
