"""Structural preparation tests with tiny invented fixtures, no real cases."""

import copy
import unittest

import jsonschema

from build_benchmark_120 import CASE_SCHEMA, similarity, validate
from normalize_benchmark_drafts import normalize


def synthetic_case():
    text = "She walk beside the quiet red building every morning before her first lesson begins today."
    return {
        "id": "A1-E001", "level": "A1", "condition": "incorrect",
        "task": "Synthetic validation fixture, not a question.", "student_text": text,
        "length_words": 16, "english_variant": "Standard British/American English",
        "gold": {
            "is_correct": False, "corrected_text": text.replace("She walk", "She walks"),
            "acceptable_alternatives": [],
            "errors": [{"original": "She walk", "correction": "She walks", "acceptable_corrections": ["She walks"], "type": "SUBJECT_VERB_AGREEMENT", "subtype": "synthetic", "explanation": "Use walks with she."}],
        },
    }


class PreparationTests(unittest.TestCase):
    def test_case_schema_accepts_synthetic(self):
        jsonschema.validate(synthetic_case(), CASE_SCHEMA)

    def test_schema_rejects_gold_boolean_string(self):
        case = synthetic_case()
        case["gold"]["is_correct"] = "false"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(case, CASE_SCHEMA)

    def test_validator_detects_unlisted_rewrite(self):
        case = synthetic_case()
        case["gold"]["corrected_text"] += " Extra style."
        report = validate([case], {"cases": []})
        self.assertTrue(any("reconstruct" in issue["issue"] for issue in report["issues"]))

    def test_validator_detects_word_mismatch(self):
        case = synthetic_case()
        case["length_words"] = 999
        report = validate([case], {"cases": []})
        self.assertGreater(report["blocker_count"], 0)

    def test_invalid_control_not_silently_repaired(self):
        case = synthetic_case()
        case.update(id="A1-C001", condition="correct")
        normalized = normalize(case)
        self.assertEqual(normalized["gold"], case["gold"])
        self.assertFalse(normalized["gold"]["is_correct"])
        self.assertTrue(normalized["gold"]["errors"])

    def test_normalizer_does_not_mutate_inputs(self):
        case = synthetic_case()
        original = copy.deepcopy(case)
        normalize(case)
        self.assertEqual(case, original)

    def test_normalizer_preserves_explicit_taxonomy(self):
        case = synthetic_case()
        case["gold"]["errors"][0]["type"] = "BE_FORM"
        self.assertEqual(normalize(case)["gold"]["errors"][0]["type"], "BE_FORM")

    def test_similarity_exact_and_nonidentical(self):
        self.assertTrue(similarity("The red lamp.", "THE RED LAMP!")["exact"])
        self.assertFalse(similarity("The red lamp.", "A blue boat sails.")["exact"])


if __name__ == "__main__":
    unittest.main()
