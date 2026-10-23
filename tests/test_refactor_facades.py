"""Pin V1's pre-refactor entry points and callback signatures."""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import unittest

from starsector_variant_generator import api
from starsector_variant_generator.analysis import gap_recommendation

BASELINE = json.loads(Path(__file__).with_name("refactor_facades_baseline.json").read_text(encoding="utf-8"))


class RefactorFacadeTests(unittest.TestCase):
    def test_recommendation_entry_points_preserve_signatures_and_models(self) -> None:
        for name, signature in BASELINE["gap"].items():
            self.assertEqual(str(inspect.signature(getattr(gap_recommendation, name))), signature, name)
        for name in BASELINE["gap_classes"]:
            self.assertIsInstance(getattr(gap_recommendation, name), type)

    def test_api_entry_points_preserve_signatures(self) -> None:
        for name, signature in BASELINE["api"].items():
            self.assertEqual(str(inspect.signature(getattr(api, name))), signature, name)

    def test_window_callbacks_preserve_signatures_without_requiring_qt(self) -> None:
        path = Path(__file__).resolve().parent.parent / "src/starsector_variant_generator/gui/main_window.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        window = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
        signatures = {node.name: [ast.dump(node.args), ast.dump(node.returns) if node.returns else None,
                                 [ast.dump(decorator) for decorator in node.decorator_list]]
                      for node in window.body if isinstance(node, ast.FunctionDef)}
        self.assertEqual(signatures, BASELINE["window_source_signatures"])


if __name__ == "__main__":
    unittest.main()
