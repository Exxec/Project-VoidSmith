from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.analysis.video_review import (
    load_video_review_transcript,
    resolve_control_suitability_evidence,
)
from starsector_variant_generator.core.evidence import (
    EvidenceClass,
    evidence_precedence,
)
from starsector_variant_generator.core.models import Hull, ScanResult, Variant
from starsector_variant_generator.core.registry import Registry


class VideoReviewTranscriptTests(unittest.TestCase):
    def test_ingests_explicit_player_and_ai_claims_as_advisory_evidence(self) -> None:
        payload = {
            "schema_name": "video_reviewer_calibration",
            "source": {"source_type": "VIDEO_REVIEW_TRANSCRIPT", "creator": "reviewer", "transcript_sha256": "abc"},
            "records": [
                {"ship_display": "Synthetic Hull", "timestamp_range": "0:01-0:05", "player_suitability_claim": "PLAYER_GOOD", "ai_suitability_claim": "AI_LIMITED"},
                {"ship_display": "No Claim", "timestamp_range": "0:06-0:07", "player_suitability_claim": "UNKNOWN", "ai_suitability_claim": "UNKNOWN"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            evidence = load_video_review_transcript(path)
        self.assertEqual(1, len(evidence))
        self.assertEqual("PLAYER_GOOD", evidence[0].player_suitability_claim)
        self.assertEqual("AI_LIMITED", evidence[0].ai_suitability_claim)
        self.assertIsNone(evidence[0].hull_id)
        self.assertEqual(EvidenceClass.VIDEO_REVIEW_TRANSCRIPT, evidence[0].source.evidence_class)

    def test_precedence_keeps_local_mechanics_above_video_and_video_above_unsourced_guidance(self) -> None:
        self.assertGreater(evidence_precedence(EvidenceClass.DIRECT_DATA), evidence_precedence(EvidenceClass.VIDEO_REVIEW_TRANSCRIPT))
        self.assertGreater(evidence_precedence(EvidenceClass.LOCAL_SOURCE_CODE), evidence_precedence(EvidenceClass.VIDEO_REVIEW_TRANSCRIPT))
        self.assertGreater(evidence_precedence(EvidenceClass.VIDEO_REVIEW_TRANSCRIPT), evidence_precedence(EvidenceClass.GENERIC_UNSOURCED_GUIDANCE))

    def test_rejects_non_video_source_type(self) -> None:
        payload = {"schema_name": "video_reviewer_calibration", "source": {"source_type": "CURATED_GUIDANCE", "transcript_sha256": "abc"}, "records": []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_video_review_transcript(path)

    def test_exact_local_name_resolution_rejects_ambiguous_and_missing_names(self) -> None:
        payload = {
            "schema_name": "video_reviewer_calibration",
            "source": {"source_type": "VIDEO_REVIEW_TRANSCRIPT", "transcript_sha256": "abc"},
            "records": [
                {"ship_display": "Exact", "timestamp_range": "0:01", "player_suitability_claim": "PLAYER_GOOD", "ai_suitability_claim": "UNKNOWN"},
                {"ship_display": "Duplicate", "timestamp_range": "0:02", "player_suitability_claim": "PLAYER_GOOD", "ai_suitability_claim": "UNKNOWN"},
                {"ship_display": "Absent", "timestamp_range": "0:03", "player_suitability_claim": "PLAYER_GOOD", "ai_suitability_claim": "UNKNOWN"},
            ],
        }
        registry = Registry.from_scan(ScanResult(hulls=[Hull("exact", "Exact", "core", Path("x")), Hull("d1", "Duplicate", "core", Path("x")), Hull("d2", "Duplicate", "mod", Path("x"))]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"; path.write_text(json.dumps(payload), encoding="utf-8")
            resolved = resolve_control_suitability_evidence(load_video_review_transcript(path), registry)
        self.assertEqual(("exact", None, None), tuple(item.hull_id for item in resolved))
        self.assertEqual(("RESOLVED_EXACT_LOCAL_NAME", "UNRESOLVED_AMBIGUOUS_LOCAL_NAME", "UNRESOLVED_NO_LOCAL_MATCH"), tuple(item.resolution_status for item in resolved))

    def test_api_returns_only_claims_bound_to_the_selected_variant_hull(self) -> None:
        payload = {"schema_name": "video_reviewer_calibration", "source": {"source_type": "VIDEO_REVIEW_TRANSCRIPT", "transcript_sha256": "abc"}, "records": [{"ship_display": "Exact", "timestamp_range": "0:01", "player_suitability_claim": "PLAYER_GOOD", "ai_suitability_claim": "AI_LIMITED"}]}
        hull = Hull("exact", "Exact", "core", Path("x")); variant = Variant("v", "V", "core", Path("v"), hull_id="exact")
        registry = Registry.from_scan(ScanResult(hulls=[hull], variants=[variant]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"; path.write_text(json.dumps(payload), encoding="utf-8")
            result = api.run_variant_control_evidence(registry, "v", path)
        self.assertEqual("RESOLVED_CLAIMS", result["status"])
        self.assertTrue(result["advisory_only"])
        self.assertEqual("PLAYER_GOOD", result["claims"][0]["player_suitability_claim"])
