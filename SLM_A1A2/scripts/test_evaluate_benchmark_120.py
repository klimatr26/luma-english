"""Unit tests for evaluate_benchmark_120.py.

All texts below are synthetic micro-sentences invented for these tests. They
are intentionally short (<12 words) and do not come from the 40-case smoke
benchmark, the 120-case development set, or any model output. No benchmark,
model, or final ~200-case test set is executed or accessed here.
"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_benchmark_120 import (
    apply_human_override,
    corrected_text_match,
    detect_format,
    evaluate_case,
    is_substantially_changed,
    match_errors,
    pr_f05,
    select_authorized_latest_rows,
    summarize,
    validate_schema,
)


def gold_error(original, correction, alternates=None):
    return {
        "original": original,
        "correction": correction,
        "type": "SYNTHETIC",
        "explanation": "synthetic explanation",
        "acceptable_corrections": [correction] + list(alternates or []),
    }


def incorrect_view(case_id="SYN-E01", student="They goes to the lake daily.",
                   corrected="They go to the lake daily.",
                   errors=None, alternatives=None, note=None):
    gold = {"is_correct": False, "corrected_text": corrected,
            "errors": errors or [], "acceptable_alternatives": alternatives or []}
    if note:
        gold["evaluation_note"] = note
    return {"case_id": case_id, "level": "A1", "condition": "incorrect",
            "student_text": student, "task": "synthetic", "gold": gold,
            "invalid": False, "evaluation_note": gold.get("evaluation_note")}


def control_view(case_id="SYN-C01", student="The cat naps on the warm rug."):
    return {"case_id": case_id, "level": "A1", "condition": "correct",
            "student_text": student, "task": "synthetic",
            "gold": {"is_correct": True, "corrected_text": student,
                     "errors": [], "acceptable_alternatives": []},
            "invalid": False, "evaluation_note": None}


def raw_of(obj):
    import json
    return {"case_id": "X", "raw_response": json.dumps(obj)}


def retry_fixture():
    benchmark_sha = "a" * 64
    manifest_sha = "c" * 64
    model_sha = "b" * 64
    config_id = "SYN-CFG-01"
    case_id = "SYN-E01"
    resume = ":".join([benchmark_sha, model_sha, manifest_sha, config_id, case_id])
    failed_body = "HTTP 503 synthetic body"
    latest_body = '{"choices":[{"message":{"content":"later output"}}]}'
    identity = {"resume_key": resume, "benchmark_sha256": benchmark_sha,
                "manifest_sha256": manifest_sha, "model_sha256": model_sha,
                "config_id": config_id, "case_id": case_id}
    attempts = [
        {**identity, "attempt": 1, "disposition": "final", "http_status": 503,
         "response_body_exact": failed_body, "error": "HTTPError:503",
         "retry_mode": "initial", "retry_of_attempt": None,
         "retry_of_outcome": None},
        {**identity, "attempt": 2, "disposition": "final", "http_status": 200,
         "response_body_exact": latest_body, "error": None,
         "retry_mode": "retry_failed", "retry_of_attempt": 1,
         "retry_of_outcome": "http_503"},
    ]
    parsed = [
        {**identity, "derived_seq": 1, "attempt_trace": [1],
         "retry_mode": "initial", "retry_of_attempt": None,
         "retry_of_outcome": None, "raw_response": "",
         "transport": {"outcome": "http_503", "http_status": 503, "attempts": 1}},
        {**identity, "derived_seq": 2, "attempt_trace": [2],
         "retry_mode": "retry_failed", "retry_of_attempt": 1,
         "retry_of_outcome": "http_503", "raw_response": "later output",
         "transport": {"outcome": "ok", "http_status": 200, "attempts": 1}},
    ]
    return benchmark_sha, attempts, parsed


class RetrySelectionTests(unittest.TestCase):
    def test_selects_latest_authorized_attempt_by_attempt_number(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        selected, report = select_authorized_latest_rows(parsed, benchmark_sha, attempts)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["raw_response"], "later output")
        self.assertEqual(report["duplicate_cases_resolved"][0]["selected_attempt"], 2)
        self.assertEqual(report["duplicate_cases_resolved"][0]["retry_mode"], "retry_failed")

    def test_duplicate_rows_without_exact_attempts_are_rejected(self):
        benchmark_sha, _, parsed = retry_fixture()
        with self.assertRaisesRegex(ValueError, "exact RAW attempts"):
            select_authorized_latest_rows(parsed, benchmark_sha)

    def test_single_runner_row_also_requires_raw_attempts(self):
        benchmark_sha, _, parsed = retry_fixture()
        with self.assertRaisesRegex(ValueError, "require exact RAW attempts"):
            select_authorized_latest_rows(parsed[:1], benchmark_sha)

    def test_single_stale_parsed_row_cannot_hide_a_later_raw_retry(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        with self.assertRaisesRegex(ValueError, "is not the latest RAW-verified attempt"):
            select_authorized_latest_rows(parsed[:1], benchmark_sha, attempts)
        selected, _ = select_authorized_latest_rows(parsed[1:], benchmark_sha, attempts)
        self.assertEqual(selected[0]["raw_response"], "later output")

    def test_retry_without_explicit_authorization_is_rejected(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        attempts[1]["retry_mode"] = "initial"
        parsed[1]["retry_mode"] = "initial"
        with self.assertRaisesRegex(ValueError, "lacks --retry-failed"):
            select_authorized_latest_rows(parsed, benchmark_sha, attempts)

    def test_parsed_content_must_match_preserved_raw_body(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        parsed[1]["raw_response"] = "a different response"
        with self.assertRaisesRegex(ValueError, "differs from exact RAW body"):
            select_authorized_latest_rows(parsed, benchmark_sha, attempts)

    def test_mixed_model_sha_is_rejected_before_selection(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        parsed[1]["model_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "multiple model_sha256"):
            select_authorized_latest_rows(parsed, benchmark_sha, attempts)

    def test_mixed_manifest_sha_or_config_is_rejected(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        parsed[1]["manifest_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "multiple manifest_sha256"):
            select_authorized_latest_rows(parsed, benchmark_sha, attempts)
        benchmark_sha, attempts, parsed = retry_fixture()
        parsed[1]["config_id"] = "SYN-CFG-OTHER"
        with self.assertRaisesRegex(ValueError, "multiple config_id"):
            select_authorized_latest_rows(parsed, benchmark_sha, attempts)

    def test_latest_attempt_is_selected_even_when_it_failed(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        attempts[1]["http_status"] = 503
        attempts[1]["response_body_exact"] = "another HTTP 503"
        attempts[1]["error"] = "HTTPError:503"
        attempts[1]["retry_of_outcome"] = "http_503"
        parsed[1]["transport"] = {"outcome": "http_503", "http_status": 503,
                                   "attempts": 1}
        parsed[1]["raw_response"] = ""
        selected, report = select_authorized_latest_rows(parsed, benchmark_sha, attempts)
        self.assertEqual(selected[0]["transport"]["outcome"], "http_503")
        self.assertEqual(report["duplicate_cases_resolved"][0]["selected_attempt"], 2)

    def test_later_run_after_429_requires_and_accepts_resume_provenance(self):
        benchmark_sha, attempts, parsed = retry_fixture()
        attempts[0].update(http_status=429, response_body_exact="rate limited",
                           error="HTTPError:429")
        parsed[0].update(raw_response="", transport={"outcome": "rate_limited",
                                                       "http_status": 429,
                                                       "attempts": 1})
        attempts[1].update(retry_mode="rate_limit_resume",
                           retry_of_outcome="rate_limited")
        parsed[1].update(retry_mode="rate_limit_resume",
                         retry_of_outcome="rate_limited")
        selected, report = select_authorized_latest_rows(parsed, benchmark_sha, attempts)
        self.assertEqual(selected[0]["raw_response"], "later output")
        self.assertEqual(report["duplicate_cases_resolved"][0]["retry_mode"],
                         "rate_limit_resume")


class FormatTests(unittest.TestCase):
    def test_direct_json_is_strict(self):
        import json
        payload = {"is_correct": True, "corrected_text": "t",
                   "errors": [], "feedback": "f"}
        fmt = detect_format(json.dumps(payload))
        self.assertEqual(fmt["parse_status"], "direct")
        self.assertTrue(fmt["json_direct"])
        self.assertFalse(fmt["has_fence"])
        self.assertFalse(fmt["text_outside_json"])

    def test_fenced_json_is_recoverable_never_strict(self):
        import json
        payload = {"is_correct": True, "corrected_text": "t",
                   "errors": [], "feedback": "f"}
        raw = "Here is the JSON:\n```json\n" + json.dumps(payload) + "\n```\nThanks!"
        fmt = detect_format(raw)
        self.assertEqual(fmt["parse_status"], "recoverable")
        self.assertTrue(fmt["has_fence"])
        self.assertFalse(fmt["json_direct"])
        valid, _ = validate_schema(fmt["parsed"])
        self.assertTrue(valid)
        strict = bool(fmt["json_direct"] and not fmt["has_fence"]
                      and not fmt["text_outside_json"] and valid)
        self.assertFalse(strict)

    def test_text_outside_json_is_recoverable_never_strict(self):
        import json
        payload = {"is_correct": True, "corrected_text": "t",
                   "errors": [], "feedback": "f"}
        fmt = detect_format("Result: " + json.dumps(payload) + " hope this helps")
        self.assertEqual(fmt["parse_status"], "recoverable")
        self.assertTrue(fmt["text_outside_json"])
        self.assertFalse(fmt["json_direct"])

    def test_garbage_is_invalid(self):
        fmt = detect_format("sorry, no json here")
        self.assertEqual(fmt["parse_status"], "invalid")
        self.assertIsNone(fmt["parsed"])

    def test_schema_separated_from_parse(self):
        import json
        parsed_ok = {"is_correct": False, "corrected_text": "c",
                     "errors": [{"original": "a", "correction": "b",
                                 "type": "T", "explanation": "e"}],
                     "feedback": "f"}
        valid, _ = validate_schema(json.loads(json.dumps(parsed_ok)))
        self.assertTrue(valid)
        invalid, problems = validate_schema({"is_correct": "false"})
        self.assertFalse(invalid)
        self.assertTrue(any("missing" in p for p in problems))


class MatchingTests(unittest.TestCase):
    def test_tp_fp_fn_and_f05(self):
        gold2 = [gold_error("goes", "go"), gold_error("swim", "swims")]
        pred = [{"original": "goes", "correction": "go",
                 "type": "T", "explanation": "e"},
                {"original": "lake", "correction": "pond",
                 "type": "T", "explanation": "e"}]
        out2 = match_errors(gold2, pred, "They go to the lake daily and swim there.")
        self.assertEqual((out2["tp"], out2["fp"], out2["fn"]), (1, 1, 1))
        m = pr_f05(1, 1, 1)
        self.assertAlmostEqual(m["precision"], 0.5)
        self.assertAlmostEqual(m["recall"], 0.5)
        self.assertAlmostEqual(m["f0_5"], 0.5)

    def test_f05_beta_weights_precision(self):
        m = pr_f05(2, 2, 0)  # P=0.5 R=1.0
        expected = 1.25 * 0.5 * 1.0 / (0.25 * 0.5 + 1.0)
        self.assertAlmostEqual(m["f0_5"], expected)

    def test_fuzzy_only_never_tp(self):
        gold = [gold_error("goes", "go")]
        pred = [{"original": "goes", "correction": "Go",  # case differs
                 "type": "T", "explanation": "e"}]
        out = match_errors(gold, pred, "They Go to the lake daily.")
        self.assertEqual(out["tp"], 0)
        self.assertEqual(out["fn"], 1)
        self.assertTrue(out["review_reasons"])

    def test_undeclared_fix_is_fn_with_review(self):
        gold = [gold_error("goes", "go")]
        out = match_errors(gold, [], "They go to the lake daily.")
        self.assertEqual((out["tp"], out["fp"], out["fn"]), (0, 0, 1))
        self.assertIn("undeclared_fix", out["review_reasons"])

    def test_corrected_text_match_levels(self):
        self.assertEqual(corrected_text_match("s", "They go home.", [], "They go home."),
                         "exact_primary")
        self.assertEqual(corrected_text_match("s", "They go home.", ["They walk home."],
                                              "They walk home."), "alternative")
        self.assertEqual(corrected_text_match("s", "They go home.", [], "they go home "),
                         "fuzzy_only")

    def test_substantial_change_ignores_surrounding_ws(self):
        self.assertFalse(is_substantially_changed("abc", "  abc\n"))
        self.assertTrue(is_substantially_changed("abc", "abd"))
        self.assertIsNone(is_substantially_changed(None, "abc"))


class VerdictTests(unittest.TestCase):
    def test_full_match_is_correct_provisional_pending_review(self):
        view = incorrect_view(
            student="She have a green bicycle.",
            corrected="She has a green bicycle.",
            errors=[gold_error("have", "has")])
        row = {"case_id": "SYN-E01", "raw_response": (
            '{"is_correct": false, "corrected_text": "She has a green bicycle.",'
            ' "errors": [{"original": "have", "correction": "has",'
            ' "type": "SYNTHETIC", "explanation": "third person singular"}],'
            ' "feedback": "ok"}')}
        out = evaluate_case(view, row, None)
        self.assertEqual(out["verdict_provisional"], "CORRECT")
        self.assertTrue(out["provisional"])
        self.assertTrue(out["needs_human_review"])
        self.assertIn("meaning_explanation_unconfirmed", out["review_reasons"])

    def test_alternative_match_is_partial_not_correct(self):
        view = incorrect_view(
            student="She have a green bicycle.",
            corrected="She has a green bicycle.",
            errors=[gold_error("have", "has", alternates=["'s got"])])
        row = {"case_id": "SYN-E01", "raw_response": (
            '{"is_correct": false, "corrected_text": "She walks home.",'
            ' "errors": [{"original": "have", "correction": "\'s got",'
            ' "type": "SYNTHETIC", "explanation": "ok"}],'
            ' "feedback": "ok"}')}
        # Pred uses the licensed alternative; text below realizes it.
        row["raw_response"] = (
            '{"is_correct": false, "corrected_text": "She\'s got a green bicycle.",'
            ' "errors": [{"original": "have", "correction": "\'s got",'
            ' "type": "SYNTHETIC", "explanation": "ok"}],'
            ' "feedback": "ok"}')
        out = evaluate_case(view, row, None)
        self.assertEqual(out["verdict_provisional"], "PARTIAL")
        self.assertIn("alternative_match_pending_review", out["review_reasons"])

    def test_partial_and_incorrect(self):
        view = incorrect_view(
            student="They goes to the lake and swim there.",
            corrected="They go to the lake and swim there.",
            errors=[gold_error("goes", "go"), gold_error("swimX", "swim")])
        view["gold"]["errors"] = [gold_error("goes", "go"), gold_error("swim", "swims")]
        view["gold"]["corrected_text"] = "They go to the lake and swims there."
        partial_row = {"case_id": "SYN-E01", "raw_response": (
            '{"is_correct": false, "corrected_text": "They go to the lake and swim there.",'
            ' "errors": [{"original": "goes", "correction": "go",'
            ' "type": "T", "explanation": "e"}], "feedback": "f"}')}
        out = evaluate_case(view, partial_row, None)
        self.assertEqual(out["verdict_provisional"], "PARTIAL")
        bad_row = {"case_id": "SYN-E01", "raw_response": "no json at all {{{"}
        out2 = evaluate_case(view, bad_row, None)
        self.assertEqual(out2["verdict_provisional"], "INCORRECT")

    def test_ambiguous_gold_note_forces_review(self):
        view = incorrect_view(note="either reading is acceptable")
        view["gold"]["errors"] = [gold_error("have", "has")]
        view["gold"]["corrected_text"] = "She has a green bicycle."
        view["student_text"] = "She have a green bicycle."
        row = {"case_id": "SYN-E01", "raw_response": (
            '{"is_correct": false, "corrected_text": "She has a green bicycle.",'
            ' "errors": [{"original": "have", "correction": "has",'
            ' "type": "T", "explanation": "e"}], "feedback": "f"}')}
        out = evaluate_case(view, row, None)
        self.assertIn("gold_evaluation_note_ambiguous", out["review_reasons"])
        self.assertTrue(out["needs_human_review"])

    def test_controls_ctmr_cfar_preserved(self):
        clean = control_view("SYN-C01")
        other = control_view("SYN-C02")
        good_row = {"case_id": "SYN-C01", "raw_response": (
            '{"is_correct": true, "corrected_text": "The cat naps on the warm rug.",'
            ' "errors": [], "feedback": "fine"}')}
        bad_row = {"case_id": "SYN-C02", "raw_response": (
            '{"is_correct": false, "corrected_text": "The cat sleeps on the warm rug.",'
            ' "errors": [{"original": "naps", "correction": "sleeps",'
            ' "type": "T", "explanation": "e"}], "feedback": "f"}')}
        e1 = evaluate_case(clean, good_row, None)
        e2 = evaluate_case(other, bad_row, None)
        self.assertEqual(e1["verdict_provisional"], "CORRECT")
        self.assertEqual(e2["verdict_provisional"], "INCORRECT")
        views = {"SYN-C01": clean, "SYN-C02": other}
        summary = summarize([e1, e2], views, {"benchmark_id": "syn"}, None)
        controls = summary["controls"]
        self.assertEqual(controls["n_controls"], 2)
        self.assertEqual(controls["ctmr_modified"], 1)
        self.assertAlmostEqual(controls["ctmr_rate"], 0.5)
        self.assertEqual(controls["cfar_false_alarm"], 1)
        self.assertAlmostEqual(controls["cfar_rate"], 0.5)
        self.assertEqual(controls["fully_preserved"], 1)

    def test_invalid_case_excluded(self):
        view = control_view("SYN-C09")
        view["invalid"] = True
        out = evaluate_case(view, None, None)
        self.assertEqual(out["verdict_final"], "INVALID_CASE")
        views = {"SYN-C09": view}
        summary = summarize([out], views, {}, None)
        self.assertEqual(summary["metadata"]["cases_scored"], 0)
        self.assertEqual(summary["metadata"]["cases_invalid_excluded"], 1)


class HumanEvalTests(unittest.TestCase):
    def test_traced_human_override_confirms(self):
        view = incorrect_view(
            student="She have a green bicycle.",
            corrected="She has a green bicycle.",
            errors=[gold_error("have", "has")])
        row = {"case_id": "SYN-E01", "raw_response": (
            '{"is_correct": false, "corrected_text": "She has a red bicycle.",'
            ' "errors": [{"original": "have", "correction": "has",'
            ' "type": "T", "explanation": "e"}], "feedback": "f"}')}
        prov = evaluate_case(view, row, None)
        self.assertEqual(prov["verdict_provisional"], "PARTIAL")
        human = {"case_id": "SYN-E01", "verdict": "CORRECT",
                 "reviewer": "r1", "rationale": "meaning kept, explanation right",
                 "meaning_preserved": True, "explanations_ok": True}
        final = evaluate_case(view, row, human)
        self.assertEqual(final["verdict_final"], "CORRECT")
        self.assertFalse(final["provisional"])
        self.assertFalse(final["needs_human_review"])

    def test_untraced_human_ignored_stays_provisional(self):
        view = control_view()
        row = {"case_id": "SYN-C01", "raw_response": "not json"}
        human = {"case_id": "SYN-C01", "verdict": "CORRECT"}  # no reviewer/rationale
        out = evaluate_case(view, row, human)
        self.assertTrue(out["provisional"])
        self.assertTrue(out["needs_human_review"])
        self.assertIn("human_evaluation_missing_traceability", out["review_reasons"])
        self.assertFalse(apply_human_override("INCORRECT", None, out) != "INCORRECT")


if __name__ == "__main__":
    unittest.main()
