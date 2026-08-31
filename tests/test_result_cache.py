from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.analysis.change_impact import (
 ChangeImpactReport,
 ImpactTarget,
)
from starsector_variant_generator.core.result_cache import (
 AnalysisContextFingerprint,
 AnalysisResultCache,
 CacheReadiness,
)


class AnalysisResultCacheTests(unittest.TestCase):
 def test_fingerprint_changes_for_each_declared_analysis_input(self):
  first=AnalysisContextFingerprint("build",("h1","w1"),"baseline_0.7",("api-0.1",),knowledge_pack_freshness="CURRENT")
  changed=AnalysisContextFingerprint("build",("h1","w2"),"baseline_0.7",("api-0.1",),knowledge_pack_freshness="CURRENT")
  self.assertNotEqual(AnalysisResultCache.fingerprint_key(first),AnalysisResultCache.fingerprint_key(changed))
 def test_exact_context_and_impact_invalidation(self):
  with tempfile.TemporaryDirectory() as temp:
   cache=AnalysisResultCache(Path(temp)/"cache.sqlite")
   context={"manifest_hash":"a","heuristic_set":"baseline_0.6"}; cache.put("mechanical_profile","h",context,{"score":1})
   self.assertEqual({"score":1},cache.get("mechanical_profile","h",context)); self.assertIsNone(cache.get("mechanical_profile","h",{**context,"manifest_hash":"b"}))
   self.assertEqual(1,cache.invalidate(ChangeImpactReport("x",(),(ImpactTarget("mechanical_profile","h","EXACT",("changed",)),),())))
   self.assertIsNone(cache.get("mechanical_profile","h",context))
 def test_incomplete_fingerprint_fails_closed_to_recomputation(self):
  with tempfile.TemporaryDirectory() as temp:
   cache=AnalysisResultCache(Path(temp)/"cache.sqlite"); unsafe=AnalysisContextFingerprint("report",("h",),"baseline_0.7")
   cache.put_fingerprint("report","h",unsafe,{"value":1})
   self.assertIsNone(cache.get_fingerprint("report","h",unsafe))
   safe=AnalysisContextFingerprint("report",("h",),"baseline_0.7",readiness=CacheReadiness.CACHE_SAFE)
   cache.put_fingerprint("report","h",safe,{"value":1})
   self.assertEqual({"value":1},cache.get_fingerprint("report","h",safe))
if __name__=="__main__": unittest.main()
