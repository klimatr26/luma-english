"""Synthetic contract and sampling checks for human_review_v2."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from human_review_v2 import (  # noqa: E402
    CRITERIA,
    HUMAN_REVIEW_SCHEMA_VERSION,
    build_sample_plan,
    packet_for_rows,
    validate_human_record,
)


def identity(case_id: str = "A1-E001", config_id: str = "cfg-1", response: str = "raw output") -> dict[str, str]:
    return {
        "scope": "development_120_evaluation_v2",
        "benchmark_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "config_id": config_id,
        "case_id": case_id,
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
    }


def review_record(condition: str = "incorrect", assessable: bool = True) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
        **identity(),
        "reviewer_id": "reviewer-test",
        "review_date": "2026-10-11",
        "response_assessable": assessable,
        "rationale": "The response and its proposed correction are readable and can be assessed.",
        "detection": 2,
        "correction": 2,
        "meaning_preservation": 2,
        "level_appropriateness": 2,
        "grammatical_explanation": 2,
        "pedagogical_clarity": 2,
        "clean_text_handling": "NA",
        "meaning_preserved": True,
        "explanations_ok": True,
        "verdict": "CORRECT",
    }
    if condition == "correct":
        values.update({
            "detection": "NA",
            "correction": "NA",
            "meaning_preservation": 2,
            "grammatical_explanation": "NA",
            "clean_text_handling": 2,
            "explanations_ok": "NA",
        })
    if not assessable:
        values.update({criterion: "NA" for criterion in CRITERIA})
        values.update({"meaning_preserved": "NA", "explanations_ok": "NA", "verdict": "INCORRECT"})
        values["rationale"] = "The raw response is unreadable, so the semantic criteria cannot be assessed."
    return values


def synthetic_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for level in ("A1", "A2"):
        for index in range(1, 16):
            cases.append({
                "id": f"{level}-C{index:03d}",
                "level": level,
                "condition": "correct",
                "task": f"Write a short text {index}.",
                "student_text": f"This is a correct text {index}.",
                "gold": {"errors": [], "acceptable_alternatives": []},
            })
        error_index = 0
        for error_count, total in ((1, 25), (2, 12), (3, 6), (4, 2)):
            alternative_total = {1: 4, 2: 3, 3: 3, 4: 0}[error_count]
            for item_index in range(total):
                error_index += 1
                has_alternatives = item_index < alternative_total
                cases.append({
                    "id": f"{level}-E{error_index:03d}",
                    "level": level,
                    "condition": "incorrect",
                    "task": f"Write a short text with {error_count} target errors.",
                    "student_text": f"Student text {level} {error_index}.",
                    "gold": {
                        "errors": [{"original": f"e{i}", "correction": f"c{i}"} for i in range(error_count)],
                        "acceptable_alternatives": ["Complete-text reference"] if has_alternatives else [],
                    },
                })
    return cases


def evaluation_rows(cases: list[dict[str, object]], config_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in cases:
        case_id = str(case["id"])
        raw_response = f"Exact raw response for {case_id}."
        row_identity = identity(case_id, config_id, raw_response)
        rows.append({
            **row_identity,
            "level": case["level"],
            "condition": case["condition"],
            "task": case["task"],
            "student_text": case["student_text"],
            "raw_response": raw_response,
            "parsed_response": {"ignored_by_blind_packet": True},
            "model_name": f"hidden-{config_id}",
        })
    return rows


class HumanRecordValidationTests(unittest.TestCase):
    def test_complete_incorrect_review_matches_exact_identity(self) -> None:
        record = review_record("incorrect")
        self.assertEqual(validate_human_record(record, identity(), "incorrect"), [])

    def test_wrong_identity_hash_and_unknown_confirmation_field_are_rejected(self) -> None:
        record = review_record("incorrect")
        record["human_confirmed"] = True
        expected = identity()
        expected["manifest_sha256"] = "c" * 64
        errors = validate_human_record(record, expected, "incorrect")
        self.assertTrue(any("manifest_sha256 does not match" in item for item in errors))
        self.assertTrue(any("unknown keys: human_confirmed" in item for item in errors))

    def test_duplicate_json_key_nonfinite_and_boolean_score_are_rejected(self) -> None:
        record = review_record("incorrect")
        raw = json.dumps(record).replace(
            '"response_assessable": true,',
            '"response_assessable": true, "response_assessable": true,',
        )
        self.assertTrue(any("duplicate JSON key" in item for item in validate_human_record(raw, identity(), "incorrect")))

        nonfinite = json.dumps(record).replace('"detection": 2', '"detection": NaN')
        self.assertTrue(any("Non-finite JSON constant" in item for item in validate_human_record(nonfinite, identity(), "incorrect")))

        record["detection"] = True
        errors = validate_human_record(record, identity(), "incorrect")
        self.assertTrue(any("booleans are not scores" in item for item in errors))

        record = review_record("incorrect")
        record["response_assessable"] = 1
        self.assertTrue(any("response_assessable must be an explicit JSON boolean" in item for item in validate_human_record(record, identity(), "incorrect")))

    def test_unassessable_record_requires_na_and_cannot_be_correct(self) -> None:
        record = review_record("incorrect", assessable=False)
        self.assertEqual(validate_human_record(record, identity(), "incorrect"), [])
        record["verdict"] = "CORRECT"
        errors = validate_human_record(record, identity(), "incorrect")
        self.assertTrue(any("all criteria are NA" in item for item in errors))
        self.assertTrue(any("cannot receive verdict CORRECT" in item for item in errors))

    def test_correct_verdict_conflicts_with_negative_flags_or_zero_scores(self) -> None:
        record = review_record("incorrect")
        record["meaning_preserved"] = False
        record["detection"] = 0
        errors = validate_human_record(record, identity(), "incorrect")
        self.assertTrue(any("meaning_preserved=false" in item for item in errors))
        self.assertTrue(any("zero score" in item for item in errors))

    def test_explanation_boolean_must_agree_with_graded_explanation(self) -> None:
        record = review_record("incorrect")
        record["explanations_ok"] = False
        record["grammatical_explanation"] = 1
        errors = validate_human_record(record, identity(), "incorrect")
        self.assertTrue(any("explanations_ok=false requires grammatical_explanation=0" in item for item in errors))

    def test_control_na_rules_and_blind_human_assessability(self) -> None:
        record = review_record("correct")
        self.assertEqual(validate_human_record(record, identity(), "correct"), [])
        record["detection"] = 0
        self.assertTrue(any("correct-text control" in item for item in validate_human_record(record, identity(), "correct")))

        unreadable = review_record("correct", assessable=False)
        unreadable["verdict"] = "INCORRECT"
        self.assertEqual(validate_human_record(unreadable, identity(), {"condition": "correct", "response_assessable": True}), [])


class SampleAndPacketTests(unittest.TestCase):
    def test_seeded_sample_has_fixed_case_and_error_count_strata(self) -> None:
        cases = synthetic_cases()
        plan = build_sample_plan(cases)
        repeated = build_sample_plan(list(reversed(cases)))
        self.assertEqual(plan["selected_case_ids"], repeated["selected_case_ids"])
        self.assertEqual(plan["selected_counts"]["total"], 60)
        self.assertEqual(plan["selected_counts"]["controls"], 30)
        self.assertEqual(plan["selected_counts"]["incorrect"], 30)
        selected_by_level = {
            level: [case_id for case_id in plan["selected_case_ids"] if case_id.startswith(level + "-")]
            for level in ("A1", "A2")
        }
        self.assertEqual({level: len(ids) for level, ids in selected_by_level.items()}, {"A1": 30, "A2": 30})
        for level in ("A1", "A2"):
            selected_incorrect = [case_id for case_id in selected_by_level[level] if "-E" in case_id]
            counts = {}
            for case_id in selected_incorrect:
                case = next(item for item in cases if item["id"] == case_id)
                counts[len(case["gold"]["errors"])] = counts.get(len(case["gold"]["errors"]), 0) + 1
            self.assertEqual(counts, {1: 8, 2: 4, 3: 2, 4: 1})

    def test_packet_is_blind_has_blank_template_and_keeps_separate_crosswalk(self) -> None:
        cases = synthetic_cases()
        plan = build_sample_plan(cases)
        rows = evaluation_rows(cases, "cfg-a") + evaluation_rows(cases, "cfg-b")
        packet, crosswalk = packet_for_rows(rows, plan)
        self.assertEqual(len(packet["items"]), 120)
        self.assertEqual(len(crosswalk["items"]), 120)
        self.assertEqual(
            {item["case_id"] for item in crosswalk["items"] if item["config_id"] == "cfg-a"},
            set(plan["selected_case_ids"]),
        )
        for item in packet["items"]:
            self.assertIn(item["level"], ("A1", "A2"))
            self.assertEqual(set(item), {"blind_output_id", "level", "task", "student_text", "response_text", "review_template"})
            self.assertNotIn("model_name", item)
            self.assertNotIn("config_id", item)
            self.assertNotIn("case_id", item)
            self.assertNotIn("condition", item)
            template = item["review_template"]
            self.assertNotIn("human_confirmed", template)
            self.assertTrue(all(template[key] is None for key in template if key != "schema_version"))
            self.assertEqual(template["schema_version"], HUMAN_REVIEW_SCHEMA_VERSION)

    def test_packet_rejects_duplicate_rows_bad_response_hash_and_unknown_case(self) -> None:
        cases = synthetic_cases()
        plan = build_sample_plan(cases)
        rows = evaluation_rows(cases, "cfg-a")
        selected_row = next(row for row in rows if row["case_id"] in plan["selected_case_ids"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            packet_for_rows(rows + [selected_row], plan)

        bad_hash_rows = evaluation_rows(cases, "cfg-a")
        bad_hash_row = next(row for row in bad_hash_rows if row["case_id"] in plan["selected_case_ids"])
        bad_hash_row["response_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match raw_response"):
            packet_for_rows(bad_hash_rows, plan)

        unknown_rows = evaluation_rows(cases, "cfg-a")
        unknown_rows[0]["case_id"] = "Z9-UNKNOWN"
        with self.assertRaisesRegex(ValueError, "unknown case_id"):
            packet_for_rows(unknown_rows, plan)


if __name__ == "__main__":
    unittest.main()
