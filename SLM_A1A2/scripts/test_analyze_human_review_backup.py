"""Synthetic rating math and intake checks; no human records are imported."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze_human_review_backup as analysis
import human_review_v2 as human


def review(condition="correct", score=2):
    result = {"schema_version": human.HUMAN_REVIEW_SCHEMA_VERSION,
              "reviewer_id": "SYNTHETIC_ONLY", "review_date": "2026-11-09",
              "response_assessable": True, "rationale": "Synthetic test fixture, never imported.",
              **{key: score for key in human.CRITERIA}, "meaning_preserved": True,
              "explanations_ok": True, "verdict": "CORRECT"}
    if condition == "correct":
        result["detection"] = result["correction"] = "NA"
    else:
        result["clean_text_handling"] = "NA"
    return result


class RatingMathTests(unittest.TestCase):
    def test_na_is_not_zero_and_each_output_has_equal_weight(self):
        first = review()
        second = review("incorrect")
        second.update({key: 0 for key in human.CRITERIA})
        second["clean_text_handling"] = "NA"
        rows = [{"review": first, "condition": "correct", "level": "A1"},
                {"review": second, "condition": "incorrect", "level": "A2"}]
        saved = copy.deepcopy(rows)
        result = analysis.aggregate(rows)
        self.assertEqual(result["mean_per_output_0_2"], 1)
        self.assertEqual(result["normalized_rubric_points_0_100"], 50)
        self.assertEqual(result["criteria"]["detection"]["n"], 1)
        self.assertEqual(result["criteria"]["clean_text_handling"]["mean"], 2)
        self.assertEqual(rows, saved)

    def test_unassessable_is_coverage_gap_not_invented_zero_or_success(self):
        missing = review()
        missing.update({key: "NA" for key in human.CRITERIA})
        missing.update(response_assessable=False, meaning_preserved="NA", explanations_ok="NA", verdict="INCORRECT")
        result = analysis.aggregate([{"review": missing, "condition": "correct", "level": "A1"}])
        self.assertIsNone(result["mean_per_output_0_2"])
        self.assertEqual(result["unscored_outputs"], 1)
        self.assertEqual(result["verdict_counts"], {"INCORRECT": 1})


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet = self.root / "packet.json"
        self.crosswalk_file = self.root / "crosswalk.json"
        self.crosswalk_file.write_text("{}", encoding="utf-8")
        self.backup = self.root / "backup.json"
        entries, visible, identities, rows = [], [], [], []
        for config in analysis.NAMES:
            for case, condition in (("A1-C-fixture", "correct"), ("A1-E-fixture", "incorrect")):
                bid = config + ":" + case
                identity = {"scope": "results_120", "benchmark_sha256": "a"*64, "manifest_sha256": "b"*64,
                            "response_sha256": hashlib.sha256(b"Synthetic response").hexdigest(), "config_id": config, "case_id": case}
                identities.append({"blind_output_id": bid, **identity})
                visible.append({"blind_output_id": bid, "response_text": "Synthetic response"})
                rows.append({**identity, "condition": condition, "level": "A1"})
                entries.append({"blind_output_id": bid, "review": review(condition), "original_has_errors": condition == "incorrect", "completed": True})
        self.packet.write_text(json.dumps({"items": visible}), encoding="utf-8")
        self.data = {"schema_version": "human_review_web.backup/1.0", "packet_sha256": analysis.sha(self.packet),
                     "profile": {"reviewer_id": "SYNTHETIC_ONLY", "review_date": "2026-11-09"}, "entries": entries, "current_id": entries[0]["blind_output_id"]}
        for name, value in (("PACKET", self.packet), ("CROSSWALK", self.crosswalk_file)):
            context = patch.object(analysis, name, value)
            context.start()
            self.addCleanup(context.stop)
        for context in (patch.object(analysis.prep, "load_verified_crosswalk", return_value={"items": identities}),
                        patch.object(analysis.prep, "load_bound_rows", return_value=(None, rows))):
            context.start()
            self.addCleanup(context.stop)

    def run_intake(self):
        self.backup.write_text(json.dumps(self.data), encoding="utf-8")
        return analysis.analyze(self.backup)

    def test_condition_conflict_removes_same_base_case_from_all_comparisons(self):
        self.data["entries"][0]["original_has_errors"] = True
        result = self.run_intake()
        self.assertEqual(result["pending_common_case_ids"], ["A1-C-fixture"])
        self.assertTrue(all(s["paired_pending_cases_omitted"]["outputs"] == 1 for s in result["summaries"].values()))
        self.assertFalse(result["original_ratings_modified"])
        self.assertFalse(result["human_layer_imported"])

    def test_invalid_proposal_is_not_silently_adjudicated(self):
        self.data["entries"][0]["review"]["verdict"] = "INVALID_CASE"
        result = self.run_intake()
        self.assertEqual(len(result["invalid_case_proposals"]), 1)
        self.assertEqual(result["bound_reviews"][0]["review"]["verdict"], "INVALID_CASE")
        self.assertIn("PROVISIONAL", result["status"])

    def test_unknown_duplicate_and_missing_ids_are_rejected(self):
        original = copy.deepcopy(self.data)
        for kind in ("unknown", "duplicate", "missing"):
            self.data = copy.deepcopy(original)
            if kind == "unknown":
                self.data["entries"][0]["blind_output_id"] = "unknown"
            elif kind == "duplicate":
                self.data["entries"][0] = self.data["entries"][1]
            else:
                self.data["entries"].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.run_intake()

    def test_wrong_packet_and_response_hash_are_rejected(self):
        self.data["packet_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "binding"):
            self.run_intake()
        self.data["packet_sha256"] = analysis.sha(self.packet)
        packet = json.loads(self.packet.read_text(encoding="utf-8"))
        packet["items"][0]["response_text"] = "Altered"
        self.packet.write_text(json.dumps(packet), encoding="utf-8")
        self.data["packet_sha256"] = analysis.sha(self.packet)
        with self.assertRaisesRegex(ValueError, "Response hash"):
            self.run_intake()

    def test_boolean_score_cannot_enter_rubric_math(self):
        self.data["entries"][0]["review"]["meaning_preservation"] = True
        with self.assertRaisesRegex(ValueError, "booleans"):
            self.run_intake()


if __name__ == "__main__":
    unittest.main()
