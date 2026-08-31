from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.analysis.recommendation_feedback import (
    FEEDBACK_SCHEMA_VERSION,
    FeedbackKind,
    RecommendationFeedback,
    append_feedback,
)


class RecommendationFeedbackTests(unittest.TestCase):
    def test_appends_only_to_the_configured_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            path = append_feedback(output, RecommendationFeedback(FeedbackKind.TOO_FLUX_HUNGRY, "fleet-support:synthetic", "synthetic", "fixture", "Needs review", "2026-01-01T00:00:00+00:00"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(FEEDBACK_SCHEMA_VERSION, payload["schema_version"])
            self.assertEqual("TOO_FLUX_HUNGRY", payload["entries"][0]["feedback"])
            self.assertIn("never auto-applied", payload["policy"])

    def test_rejects_incomplete_or_oversized_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with self.assertRaises(ValueError):
                append_feedback(output, RecommendationFeedback(FeedbackKind.KEEP, "", "synthetic"))
            with self.assertRaises(ValueError):
                append_feedback(output, RecommendationFeedback(FeedbackKind.KEEP, "id", "synthetic", note="x" * 2001))

    def test_rejects_an_unrecognized_existing_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "recommendation-feedback.json").write_text('{"schema_version":"wrong","entries":[]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                append_feedback(output, RecommendationFeedback(FeedbackKind.KEEP, "id", "synthetic"))
