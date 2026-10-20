import tomllib
import unittest
from pathlib import Path

import starsector_variant_generator

ROOT = Path(__file__).resolve().parents[1]


class VersionConsistencyTest(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(starsector_variant_generator.__version__, project["version"])


if __name__ == "__main__":
    unittest.main()
