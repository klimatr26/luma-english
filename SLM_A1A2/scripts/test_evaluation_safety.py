"""Regression tests for strict parsing and false-positive matching (synthetic)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_benchmark_120 import (
    detect_format, match_errors, validate_schema, evaluate_case, case_view,
    select_authorized_latest_rows,
)


class EvaluationSafetyTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        self.assertEqual(detect_format('{"is_correct":true,"is_correct":false}')["parse_status"], "invalid")

    def test_nan_is_not_json(self):
        self.assertEqual(detect_format('{"x":NaN}')["parse_status"], "invalid")

    def test_extra_schema_keys_rejected(self):
        response = {"is_correct": True, "corrected_text": "Hello.", "errors": [], "feedback": "OK", "secret": 1}
        self.assertFalse(validate_schema(response)[0])

    def test_wrong_original_never_gets_tp_from_same_correction(self):
        gold = [{"original": "She walk", "correction": "She walks", "acceptable_corrections": ["She walks"]}]
        pred = [{"original": "He runs", "correction": "She walks"}]
        scores = match_errors(gold, pred, "She walks.")
        self.assertEqual((scores["tp"], scores["fp"], scores["fn"]), (0, 1, 1))

    def test_control_fully_preserved_requires_literal_identity(self):
        case = {"id": "SYNTH-C", "level": "A1", "condition": "correct", "student_text": "Hello there.", "gold": {"is_correct": True, "corrected_text": "Hello there.", "errors": []}}
        response = {"is_correct": True, "corrected_text": "Hello  there.", "errors": [], "feedback": "OK"}
        result = evaluate_case(case_view(case), {"raw_response": json.dumps(response)}, None)
        self.assertFalse(result["control_fully_preserved"])
        self.assertFalse(result["corrected_text_changed"])
        self.assertEqual(result["verdict_provisional"], "INCORRECT")

    def test_mixed_benchmark_sha_is_rejected(self):
        rows = [
            {"case_id": "SYN-A", "config_id": "SYN-CFG", "model_sha256": "a" * 64,
             "manifest_sha256": "b" * 64, "benchmark_sha256": "c" * 64,
             "raw_response": "{}"},
            {"case_id": "SYN-B", "config_id": "SYN-CFG", "model_sha256": "a" * 64,
             "manifest_sha256": "b" * 64, "benchmark_sha256": "d" * 64,
             "raw_response": "{}"},
        ]
        with self.assertRaisesRegex(ValueError, "multiple benchmark_sha256"):
            select_authorized_latest_rows(rows, "c" * 64)


if __name__ == "__main__":
    unittest.main()
