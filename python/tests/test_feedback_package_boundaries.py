import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.feedback import _append_jsonl_locked, run
from kbprep_worker.feedback.jsonl_store import _read_jsonl
from kbprep_worker.feedback.patterns import _matches_pattern
from kbprep_worker.feedback.proposals import _validate_proposal_acceptance
from kbprep_worker.feedback.promotion_history import _promotion_history_document_summary
from kbprep_worker.feedback.scope_inference import (
    _source_identity_patterns_from_contexts,
    _source_pattern_from_repeated_names,
)


class FeedbackPackageBoundaryTests(unittest.TestCase):
    def test_public_compatibility_exports_still_work(self):
        self.assertTrue(callable(run))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "rules.jsonl")
            _append_jsonl_locked(path, {"id": "one"})
            self.assertEqual(_read_jsonl(path)[0]["id"], "one")

    def test_proposal_pattern_helpers_remain_importable(self):
        validation = _validate_proposal_acceptance({
            "pattern": "关注公众号",
            "match": "literal",
            "examples": ["关注公众号领取资料"],
            "counterexamples": ["正文案例：关注公众号是渠道字段"],
        })

        self.assertTrue(_matches_pattern("请关注公众号领取资料", "关注公众号", "literal"))
        self.assertFalse(validation["ok"])
        self.assertEqual(validation["counterexample_matches"], ["正文案例：关注公众号是渠道字段"])

    def test_scope_and_promotion_history_helpers_remain_importable(self):
        contexts = [
            {"source_identity": {"source_url": "https://example.com/a", "source_domain": "example.com"}},
            {"source_identity": {"source_url": "https://example.com/b", "source_domain": "example.com"}},
        ]
        history = _promotion_history_document_summary("course", [
            {
                "schema": "kbprep.dictionary_promotion_history.v1",
                "created_at": "2026-06-01T00:00:00Z",
                "document_type": "course",
                "promoted_count": 1,
                "regression_verification": {
                    "status": "passed",
                    "sample_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "samples": [{"ok": True}],
                },
            }
        ])

        self.assertEqual(_source_pattern_from_repeated_names(["site-a-001.md", "site-a-002.md"]), "site-a")
        self.assertEqual(_source_identity_patterns_from_contexts(contexts)[0], "source_domain:example.com")
        self.assertEqual(history["latest_status"], "passed")
        self.assertEqual(history["failed_promotions"], 0)


if __name__ == "__main__":
    unittest.main()
