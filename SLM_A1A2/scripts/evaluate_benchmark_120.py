"""Independent evaluator for the Fase 2 writing A1/A2 development benchmark (120 cases).

Scope and limits (read before use):

- This script performs NO inference, downloads NO models, and never touches the
  final ~200-case test set. It only scores already-collected raw model outputs
  against an already-frozen benchmark gold file.
- Verdicts produced WITHOUT an explicit human evaluation are PROVISIONAL
  (string-based, deterministic). Meaning preservation and explanation quality
  always require explicit human judgment with traceability (reviewer +
  rationale); the script never certifies them automatically from string
  similarity.
- Extra text around the JSON object NEVER counts as strict-JSON compliance.
- A benchmark case later judged defective is marked INVALID for every model;
  its gold is never rewritten after seeing outputs.

Inputs
------
- Benchmark JSON: ``{"cases": [...]}`` (also accepts a top-level list). Each
  case uses the Fase 1 schema (``benchmark_smoke_test_v2.json`` shape only):
  ``id``, ``level``, ``condition`` (``correct``/``incorrect``), ``task``,
  ``student_text``, ``gold`` with ``is_correct``, ``corrected_text``,
  ``errors`` (``original``/``correction``/``type``/``explanation`` plus
  optional ``acceptable_corrections``), and optional
  ``acceptable_alternatives`` / ``evaluation_note``.
- Parsed outputs JSONL: normally one row per attempt group, with ``case_id``
  and ``raw_response`` (str). After an explicitly authorized retry there can
  be multiple rows for a case. Runner output always requires its companion
  exact-attempt JSONL (``--attempts``), even for singleton rows, so a stale or
  truncated parsed file cannot hide a newer RAW attempt. Selection is
  chronological by highest authorized final attempt number, never by output
  quality. Unverified or ambiguous duplicates are rejected.
- Exact attempts JSONL: one exact runner record per HTTP attempt. Retry
  provenance, hashes, response body and final attempt must match.
- Human evaluations JSONL (optional): one object per case with
  ``case_id``, ``verdict``, ``reviewer``, ``rationale`` and optional
  ``meaning_preserved`` / ``explanations_ok`` booleans.

Outputs
-------
- Per-case evaluations JSONL (``--out-evals``).
- Aggregate summary JSON (``--out-summary``), with provisional vs confirmed
  scores kept separate and a comparison table broken down by subgroup
  (never reduced to a single score).

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

VERDICTS = ("CORRECT", "PARTIAL", "INCORRECT", "INVALID_CASE")
PARSE_STATUSES = ("direct", "recoverable", "invalid")
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
BETA = 0.5
RAW_ATTEMPT_FIELDS = {
    "resume_key", "attempt", "disposition", "benchmark_sha256",
    "manifest_sha256", "model_sha256", "config_id", "case_id",
    "http_status", "response_body_exact", "error", "latency_seconds",
    "recorded_utc", "retry_mode", "retry_of_attempt", "retry_of_outcome",
}
RAW_ATTEMPT_REQUIRED_FIELDS = {
    "resume_key", "attempt", "disposition", "benchmark_sha256",
    "manifest_sha256", "model_sha256", "config_id", "case_id",
    "http_status", "response_body_exact", "error",
}


def strict_json_loads(text):
    """Reject non-JSON constants and duplicate keys instead of accepting them."""
    def reject_constant(value):
        raise ValueError(f"Non-JSON constant: {value}")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def strip_key(text: str) -> str:
    """Strict, case-sensitive key: NFKC + strip surrounding whitespace."""
    return _nfkc(text).strip()


def collapse_ws(text: str) -> str:
    """Whitespace-collapsed form (case-sensitive). Used for change checks."""
    return re.sub(r"\s+", " ", _nfkc(text)).strip()


def fuzzy_key(text: str) -> str:
    """Lowercased, punctuation-light form used ONLY to flag human review.

    Never used to award an automatic true positive.
    """
    text = _nfkc(text).casefold()
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return " ".join(text.split())


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w]+(?:['\u2019][\w]+)*\b", text, re.UNICODE))


# ---------------------------------------------------------------------------
# Format / JSON handling
# ---------------------------------------------------------------------------

def balanced_json_span(text: str):
    """Return (start, end) of the first balanced {...} span, or None."""
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return start, index + 1
        start = text.find("{", start + 1)
    return None


def detect_format(raw) -> dict:
    """Classify a raw model response without ever treating extra text as strict.

    Returns a dict with: parse_status (direct|recoverable|invalid), parsed,
    has_fence, text_outside_json, json_direct, json_recoverable, method.
    """
    info: dict = {
        "parse_status": "invalid",
        "parsed": None,
        "has_fence": False,
        "text_outside_json": False,
        "json_direct": False,
        "json_recoverable": False,
        "method": "none",
    }
    if not isinstance(raw, str):
        info["method"] = "non_string_raw"
        return info
    stripped = raw.strip()
    if not stripped:
        info["method"] = "empty_raw"
        return info
    # 1. Strict path: the whole (trimmed) response must be the JSON object.
    try:
        parsed = strict_json_loads(stripped)
        if isinstance(parsed, dict):
            info.update(
                parse_status="direct", parsed=parsed, json_direct=True,
                method="direct",
            )
            return info
        info["method"] = "direct_non_object"
    except Exception:
        pass
    # 2. Recoverable path: fenced block first, then balanced-span extraction.
    fence_match = FENCE_RE.search(raw)
    if fence_match:
        info["has_fence"] = True
        candidate = fence_match.group(1).strip()
        try:
            parsed = strict_json_loads(candidate)
            if isinstance(parsed, dict):
                before = raw[: fence_match.start()].strip()
                after = raw[fence_match.end():].strip()
                info.update(
                    parse_status="recoverable", parsed=parsed,
                    json_recoverable=True,
                    text_outside_json=bool(before or after),
                    method="fence_block",
                )
                return info
        except Exception:
            pass
    span = balanced_json_span(raw)
    if span is not None:
        start, end = span
        candidate = raw[start:end]
        try:
            parsed = strict_json_loads(candidate)
            if isinstance(parsed, dict):
                info.update(
                    parse_status="recoverable", parsed=parsed,
                    json_recoverable=True,
                    text_outside_json=bool(raw[:start].strip() or raw[end:].strip()),
                    method="balanced_span",
                )
                return info
        except Exception:
            pass
    info["method"] = "unparseable"
    info["text_outside_json"] = True
    return info


REQUIRED_TOP = {"is_correct": bool, "corrected_text": str, "errors": list, "feedback": str}
REQUIRED_ERROR = {"original": str, "correction": str, "type": str, "explanation": str}


def validate_schema(parsed) -> tuple[bool, list[str]]:
    """Check the strict response schema. Returns (valid, error_list)."""
    problems: list[str] = []
    if not isinstance(parsed, dict):
        return False, ["top_level_not_object"]
    if set(parsed) - set(REQUIRED_TOP):
        problems.append("unexpected_top_level_keys")
    for key, kind in REQUIRED_TOP.items():
        if key not in parsed:
            problems.append(f"missing:{key}")
        elif kind is bool:
            if not isinstance(parsed[key], bool):
                problems.append(f"type:{key}:expected_boolean")
        elif not isinstance(parsed[key], kind):
            problems.append(f"type:{key}:expected_{kind.__name__}")
    errors = parsed.get("errors")
    if isinstance(errors, list):
        for i, item in enumerate(errors):
            if not isinstance(item, dict):
                problems.append(f"errors[{i}]:not_object")
                continue
            if set(item) - set(REQUIRED_ERROR):
                problems.append(f"errors[{i}]:unexpected_keys")
            for key, kind in REQUIRED_ERROR.items():
                if key not in item:
                    problems.append(f"errors[{i}].missing:{key}")
                elif not isinstance(item[key], kind) or (
                    kind is str and not item[key].strip()
                ):
                    problems.append(f"errors[{i}].bad:{key}")
    return (len(problems) == 0), problems


# ---------------------------------------------------------------------------
# Error-coverage matching (strict; alternatives never auto-certify meaning)
# ---------------------------------------------------------------------------

def licensed_corrections(gold_error: dict) -> tuple[list[str], str]:
    """Return (ordered licensed strings, primary). Exact, case-sensitive."""
    primary = gold_error.get("correction", "")
    primary = strip_key(primary) if isinstance(primary, str) else ""
    licensed = [primary] if primary else []
    extra = gold_error.get("acceptable_corrections") or []
    if isinstance(extra, list):
        for item in extra:
            if isinstance(item, str):
                key = strip_key(item)
                if key and key not in licensed:
                    licensed.append(key)
    return licensed, primary


def match_errors(gold_errors: list[dict], pred_errors: list[dict],
                 pred_corrected: str) -> dict:
    """Strict bipartite match between gold and predicted error lists.

    A true positive requires BOTH:
      (a) the predicted ``correction`` string exactly equals a gold-licensed
          correction (primary or ``acceptable_corrections``), and
      (b) that same string occurs verbatim (case-sensitive, NFKC) inside the
          predicted ``corrected_text``.
    Anything looser (case/punctuation-insensitive resemblance, text fixed but
    not declared, declared but not realized) is a miss plus a review flag,
    never an automatic TP.
    """
    gold_errors = gold_errors if isinstance(gold_errors, list) else []
    pred_errors = pred_errors if isinstance(pred_errors, list) else []
    corrected = _nfkc(pred_corrected) if isinstance(pred_corrected, str) else ""

    pred_keys: list[str | None] = []
    for item in pred_errors:
        corr = item.get("correction") if isinstance(item, dict) else None
        pred_keys.append(strip_key(corr) if isinstance(corr, str) and corr.strip() else None)

    used_pred = [False] * len(pred_errors)
    tp = 0
    fn = 0
    details: list[dict] = []
    alternative_only = False
    review_reasons: list[str] = []

    for gi, gold in enumerate(gold_errors):
        licensed, primary = licensed_corrections(gold if isinstance(gold, dict) else {})
        hit = None
        hit_via_alternative = False
        if licensed:
            for pj, key in enumerate(pred_keys):
                if key is None or used_pred[pj]:
                    continue
                pred_original = pred_errors[pj].get("original") if isinstance(pred_errors[pj], dict) else None
                gold_original = gold.get("original") if isinstance(gold, dict) else None
                same_span = (
                    isinstance(pred_original, str) and isinstance(gold_original, str)
                    and strip_key(pred_original) == strip_key(gold_original)
                )
                if key in licensed and same_span:
                    hit = pj
                    hit_via_alternative = (key != primary)
                    break
        in_text = (
            [lic for lic in licensed if lic and lic in corrected]
            if licensed else []
        )
        if hit is not None and in_text:
            matched_key = pred_keys[hit]
            if matched_key not in in_text:
                # Declared string differs from the realized string variant.
                used_pred[hit] = True
                tp += 0
                fn += 1
                details.append({"gold_index": gi, "status": "FN",
                                "reason": "declared_correction_not_realized_in_text"})
                review_reasons.append("declared_but_not_realized")
            else:
                used_pred[hit] = True
                tp += 1
                if hit_via_alternative:
                    alternative_only = True
                    review_reasons.append("alternative_match_pending_review")
                details.append({"gold_index": gi, "status": "TP",
                                "pred_index": hit,
                                "via_alternative": hit_via_alternative})
        elif hit is not None:
            used_pred[hit] = True
            fn += 1
            details.append({"gold_index": gi, "status": "FN",
                            "reason": "declared_but_not_realized_in_text",
                            "pred_index": hit})
            review_reasons.append("declared_but_not_realized")
        elif in_text:
            fn += 1
            details.append({"gold_index": gi, "status": "FN",
                            "reason": "fixed_in_text_but_not_declared"})
            review_reasons.append("undeclared_fix")
            if any(key in licensed for key in pred_keys if key):
                review_reasons.append("original_span_mismatch_pending_review")
        else:
            # Fuzzy resemblance (ignoring case/punctuation) is reported only
            # as a review hint, never as a TP.
            fuzzy_hit = False
            if isinstance(gold, dict):
                for lic in licensed:
                    if not lic:
                        continue
                    if fuzzy_key(lic) and fuzzy_key(lic) in fuzzy_key(corrected):
                        fuzzy_hit = True
                        break
            fn += 1
            details.append({"gold_index": gi, "status": "FN",
                            "reason": "missed",
                            "fuzzy_resemblance": fuzzy_hit})
            if fuzzy_hit:
                review_reasons.append("fuzzy_resemblance_only")

    fp = 0
    for pj, key in enumerate(pred_keys):
        if not used_pred[pj]:
            # Unmatched prediction, including empty/non-string corrections.
            fp += 1
    # Shared licensed strings matched by a single prediction are ambiguous.
    seen_licensed: Counter = Counter()
    for gold in gold_errors:
        licensed, _ = licensed_corrections(gold if isinstance(gold, dict) else {})
        for lic in licensed:
            seen_licensed[lic] += 1
    if any(n > 1 for n in seen_licensed.values()) and tp > 0:
        review_reasons.append("shared_correction_ambiguous")

    return {
        "tp": tp, "fp": fp, "fn": fn,
        "details": details,
        "alternative_only": alternative_only,
        "review_reasons": sorted(set(review_reasons)),
    }


def corrected_text_match(student_text, gold_corrected, alternatives, pred_corrected) -> str:
    """Classify corrected_text: exact_primary | alternative | fuzzy_only | none."""
    pred = strip_key(pred_corrected) if isinstance(pred_corrected, str) else None
    gold = strip_key(gold_corrected) if isinstance(gold_corrected, str) else None
    if pred is None:
        return "none"
    if gold is not None and pred == gold:
        return "exact_primary"
    for alt in alternatives or []:
        if isinstance(alt, str) and pred == strip_key(alt):
            return "alternative"
    if gold is not None and fuzzy_key(pred) == fuzzy_key(gold):
        return "fuzzy_only"
    for alt in alternatives or []:
        if isinstance(alt, str) and fuzzy_key(pred) == fuzzy_key(alt):
            return "fuzzy_only"
    return "none"


def is_substantially_changed(student_text, pred_corrected) -> bool | None:
    """True when stripped corrected text differs. None if not comparable."""
    if not isinstance(student_text, str) or not isinstance(pred_corrected, str):
        return None
    return collapse_ws(student_text) != collapse_ws(pred_corrected)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def pr_f05(tp: int, fp: int, fn: int) -> dict:
    if tp + fp == 0:
        precision = 1.0 if fn == 0 else 0.0
    else:
        precision = tp / (tp + fp)
    if tp + fn == 0:
        recall = 1.0
    else:
        recall = tp / (tp + fn)
    denom = (BETA ** 2) * precision + recall
    f05 = ((1 + BETA ** 2) * precision * recall / denom) if denom > 0 else 0.0
    return {"precision": precision, "recall": recall, "f0_5": f05}


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

def load_benchmark(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        meta = {k: v for k, v in data.items() if k != "cases"}
        cases = data["cases"]
    elif isinstance(data, list):
        meta = {}
        cases = data
    else:
        raise ValueError("Benchmark file must be {cases:[...]} or a list.")
    return meta, cases


def case_view(case: dict) -> dict:
    cid = case.get("id", case.get("case_id", ""))
    gold = case.get("gold") if isinstance(case.get("gold"), dict) else {}
    condition = case.get("condition")
    invalid = (
        case.get("invalid") is True or gold.get("invalid") is True
        or condition == "invalid"
    )
    return {
        "case_id": cid,
        "level": case.get("level"),
        "condition": condition,
        "student_text": case.get("student_text"),
        "task": case.get("task"),
        "gold": gold,
        "invalid": invalid,
        "evaluation_note": gold.get("evaluation_note"),
    }


def load_jsonl(path: Path | None) -> list[dict]:
    if path is None:
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _retry_eligible(outcome: str | None) -> bool:
    if outcome == "transport_error":
        return True
    if isinstance(outcome, str) and outcome.startswith("http_"):
        try:
            return int(outcome.split("_", 1)[1]) >= 500
        except ValueError:
            return False
    return False


def _attempt_outcome(row: dict) -> str:
    status = row.get("http_status")
    if status is None:
        return "transport_error"
    if isinstance(status, bool) or not isinstance(status, int):
        raise ValueError("Attempt HTTP status must be an integer or null")
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return f"http_{status}"
    if not 200 <= status < 300:
        return f"http_{status}"
    body = row.get("response_body_exact")
    try:
        payload = json.loads(body) if isinstance(body, str) else None
    except Exception:
        payload = None
    return "ok" if isinstance(payload, dict) else "invalid_body"


def _message_content_from_attempt(row: dict) -> str:
    body = row.get("response_body_exact")
    try:
        payload = json.loads(body) if isinstance(body, str) else None
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
    return ""


def _single_value(rows: list[dict], key: str, *, required: bool = False):
    values = [row.get(key) for row in rows]
    if any(value is not None and not isinstance(value, str) for value in values):
        raise ValueError(f"Output identity field {key} must contain strings")
    present = [value for value in values if value is not None]
    if present and len(present) != len(values):
        raise ValueError(f"Mixed output identity: some rows omit {key}")
    unique = {value.lower() if isinstance(value, str) else value for value in present}
    if len(unique) > 1:
        raise ValueError(f"Mixed output identity: rows contain multiple {key} values")
    if required and not present:
        raise ValueError(f"Output rows lack required identity field {key}")
    return present[0] if present else None


def _validate_attempt_groups(attempt_rows: list[dict], resume_key: str,
                             expected_identity: dict | None = None) -> list[dict]:
    rows = [row for row in attempt_rows if row.get("resume_key") == resume_key]
    if not rows:
        raise ValueError(f"No exact RAW attempts found for resume_key {resume_key!r}")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Exact RAW attempt file contains a non-object row")
    for row in rows:
        missing = RAW_ATTEMPT_REQUIRED_FIELDS - set(row)
        unexpected = set(row) - RAW_ATTEMPT_FIELDS
        if missing or unexpected:
            raise ValueError(f"RAW attempt schema mismatch for {resume_key!r}: "
                             f"missing={sorted(missing)}, unexpected={sorted(unexpected)}")
        status = row.get("http_status")
        if (status is not None and (not isinstance(status, int)
                                    or isinstance(status, bool)
                                    or not 100 <= status <= 599)):
            raise ValueError(f"Invalid HTTP status in RAW attempts for {resume_key!r}")
        if not isinstance(row.get("response_body_exact"), str):
            raise ValueError(f"RAW response body for {resume_key!r} is not exact text")
        if row.get("error") is not None and not isinstance(row.get("error"), str):
            raise ValueError(f"RAW error for {resume_key!r} must be a string or null")
        if "retry_of_attempt" in row and row["retry_of_attempt"] is not None and (
                not isinstance(row["retry_of_attempt"], int)
                or isinstance(row["retry_of_attempt"], bool)):
            raise ValueError(f"Invalid retry_of_attempt in RAW attempts for {resume_key!r}")
        if "retry_of_outcome" in row and row["retry_of_outcome"] is not None and not isinstance(
                row["retry_of_outcome"], str):
            raise ValueError(f"Invalid retry_of_outcome in RAW attempts for {resume_key!r}")
    if expected_identity:
        for row in rows:
            for key in ("benchmark_sha256", "manifest_sha256", "model_sha256",
                        "config_id", "case_id"):
                expected = expected_identity.get(key)
                actual = row.get(key)
                if isinstance(expected, str) and isinstance(actual, str):
                    same = expected.lower() == actual.lower() if key.endswith("sha256") else expected == actual
                else:
                    same = expected == actual
                if not same:
                    raise ValueError(f"Parsed and exact RAW {key} differ for {resume_key!r}")
    seen: set[int] = set()
    for row in rows:
        attempt = row.get("attempt")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError(f"Invalid attempt number for {resume_key!r}")
        if attempt in seen:
            raise ValueError(f"Duplicate RAW attempt number {attempt} for {resume_key!r}")
        seen.add(attempt)
    rows.sort(key=lambda row: row["attempt"])
    if [r["attempt"] for r in rows] != list(range(1, rows[-1]["attempt"] + 1)):
        raise ValueError(f"RAW attempts for {resume_key!r} are not contiguous")

    groups: list[list[dict]] = []
    current: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Exact RAW attempt file contains a non-object row")
        current.append(row)
        disposition = row.get("disposition")
        if disposition not in {"retry", "final"}:
            raise ValueError(f"Unknown RAW attempt disposition for {resume_key!r}")
        if disposition == "final":
            groups.append(current)
            current = []
    if current:
        raise ValueError(f"RAW attempts for {resume_key!r} end in an unfinished group")

    validated: list[dict] = []
    previous_outcome = None
    previous_attempt = None
    for index, group in enumerate(groups):
        first = group[0]
        mode = first.get("retry_mode", "legacy")
        ref_attempt = first.get("retry_of_attempt")
        ref_outcome = first.get("retry_of_outcome")
        if any(row.get("retry_mode", "legacy") != mode
               or row.get("retry_of_attempt") != ref_attempt
               or row.get("retry_of_outcome") != ref_outcome for row in group):
            raise ValueError(f"RAW retry provenance changes within {resume_key!r}")
        if index == 0:
            if mode not in {"initial", "legacy"} or ref_attempt is not None or ref_outcome is not None:
                raise ValueError(f"First RAW attempt group for {resume_key!r} is not initial")
        else:
            if ref_attempt != previous_attempt or ref_outcome != previous_outcome:
                raise ValueError(f"Retry for {resume_key!r} does not reference prior final")
            if _retry_eligible(previous_outcome):
                if mode != "retry_failed":
                    raise ValueError(f"Retry for {resume_key!r} lacks --retry-failed authority")
            elif previous_outcome == "rate_limited":
                if mode != "rate_limit_resume":
                    raise ValueError(f"Resume for {resume_key!r} after 429 lacks stop provenance")
            else:
                raise ValueError(f"Non-retryable output for {resume_key!r} was retried")
        for prior in group[:-1]:
            status = prior.get("http_status")
            retryable = status is None or (isinstance(status, int)
                                           and not isinstance(status, bool)
                                           and status >= 500 and status != 429)
            if prior.get("disposition") != "retry" or not retryable:
                raise ValueError(f"RAW attempt {prior['attempt']} for {resume_key!r} "
                                 "is marked retry without a technical failure")
        final = group[-1]
        if final.get("disposition") != "final":
            raise ValueError(f"RAW attempt group for {resume_key!r} lacks a final row")
        outcome = _attempt_outcome(final)
        validated.append({
            "attempt_trace": [row["attempt"] for row in group],
            "final_attempt": final["attempt"],
            "outcome": outcome,
            "http_status": final.get("http_status"),
            "raw_response": _message_content_from_attempt(final),
            "retry_mode": mode,
            "retry_of_attempt": ref_attempt,
            "retry_of_outcome": ref_outcome,
            "attempts": len(group),
        })
        previous_outcome = outcome
        previous_attempt = final["attempt"]
    return validated


def select_authorized_latest_rows(rows: list[dict], benchmark_sha: str,
                                 attempt_rows: list[dict] | None = None,
                                 config_filter: str | None = None,
                                 manifest_sha: str | None = None,
                                 manifest_data: dict | None = None) -> tuple[list[dict], dict]:
    """Resolve parsed duplicates by the last RAW-verified authorized attempt.

    Runner output always requires exact RAW attempts. This proves that a
    singleton parsed row is the latest recorded attempt too, so a truncated or
    stale parsed file cannot silently restore an earlier response. Output
    identity is validated before applying the optional config assertion so a
    mixed input cannot be hidden by filtering.
    """
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Parsed output contains a non-object row")
    if not rows:
        if config_filter:
            raise ValueError("No parsed rows match the requested config_id")
        return [], {"rows_in": 0, "rows_selected": 0,
                    "duplicate_cases_resolved": [],
                    "selection_policy": "highest verified final attempt number"}

    config_id = _single_value(rows, "config_id")
    model_sha = _single_value(rows, "model_sha256")
    out_benchmark_sha = _single_value(rows, "benchmark_sha256")
    out_manifest_sha = _single_value(rows, "manifest_sha256")
    identities = {row.get("config_id") or row.get("model_name") for row in rows}
    identities.discard(None)
    if len(identities) > 1:
        raise ValueError("Mixed model/configuration outputs: evaluate each configuration separately")
    if out_benchmark_sha is not None and out_benchmark_sha.lower() != benchmark_sha.lower():
        raise ValueError("Parsed outputs bind a different benchmark SHA")
    for field, value in (("model_sha256", model_sha),
                         ("manifest_sha256", out_manifest_sha),
                         ("benchmark_sha256", out_benchmark_sha)):
        if value is not None and (len(value) != 64 or not re.fullmatch(r"[0-9a-fA-F]{64}", value)):
            raise ValueError(f"Parsed output {field} is not a 64-character SHA-256")
    if manifest_sha is not None and out_manifest_sha is not None:
        if out_manifest_sha.lower() != manifest_sha.lower():
            raise ValueError("Parsed outputs bind a different manifest SHA")
    if config_filter and config_id and config_filter != config_id:
        raise ValueError(f"Parsed outputs contain {config_id!r}, not requested {config_filter!r}")
    if config_filter and config_id is None:
        raise ValueError("--config requires parsed rows with config_id")
    if config_id is not None and (not config_id.strip() or model_sha is None
                                  or out_benchmark_sha is None or out_manifest_sha is None):
        raise ValueError("Runner output identity must include config_id and all three SHA-256 values")

    is_runner_output = (config_id is not None or any(
        row.get("resume_key") is not None or row.get("attempt_trace") is not None
        for row in rows))
    if is_runner_output and attempt_rows is None:
        raise ValueError("Runner parsed outputs require exact RAW attempts to verify the latest attempt")

    if attempt_rows is not None:
        if any(not isinstance(row, dict) for row in attempt_rows):
            raise ValueError("Exact RAW attempt file contains a non-object row")
        raw_config = _single_value(attempt_rows, "config_id", required=bool(attempt_rows))
        raw_model_sha = _single_value(attempt_rows, "model_sha256", required=bool(attempt_rows))
        raw_benchmark_sha = _single_value(attempt_rows, "benchmark_sha256", required=bool(attempt_rows))
        raw_manifest_sha = _single_value(attempt_rows, "manifest_sha256", required=bool(attempt_rows))
        if config_id is not None and raw_config != config_id:
            raise ValueError("Parsed outputs and exact RAW attempts use different configs")
        if model_sha is not None and raw_model_sha is not None and model_sha.lower() != raw_model_sha.lower():
            raise ValueError("Parsed outputs and exact RAW attempts use different model SHAs")
        if out_benchmark_sha is not None and raw_benchmark_sha.lower() != out_benchmark_sha.lower():
            raise ValueError("Parsed outputs and exact RAW attempts use different benchmark SHAs")
        if out_manifest_sha is not None and raw_manifest_sha.lower() != out_manifest_sha.lower():
            raise ValueError("Parsed outputs and exact RAW attempts use different manifest SHAs")
        if raw_benchmark_sha is not None and raw_benchmark_sha.lower() != benchmark_sha.lower():
            raise ValueError("Exact RAW attempts bind a different benchmark SHA")
        if manifest_sha is not None and raw_manifest_sha is not None:
            if raw_manifest_sha.lower() != manifest_sha.lower():
                raise ValueError("Exact RAW attempts bind a different manifest SHA")

    if manifest_data is not None:
        configs = manifest_data.get("configurations")
        if not isinstance(configs, list) or not config_id:
            raise ValueError("Manifest must contain configurations and output config_id")
        manifest_config = [entry for entry in configs
                           if isinstance(entry, dict)
                           and entry.get("config_id", entry.get("id")) == config_id]
        if len(manifest_config) != 1:
            raise ValueError(f"Manifest does not uniquely identify config {config_id!r}")
        expected_model_sha = manifest_config[0].get("model_sha256")
        if not isinstance(expected_model_sha, str):
            raise ValueError(f"Manifest config {config_id!r} lacks model_sha256")
        if model_sha is None or model_sha.lower() != expected_model_sha.lower():
            raise ValueError("Parsed outputs model SHA differs from the manifest")
        if out_manifest_sha is None or manifest_sha is None:
            raise ValueError("Manifest-bound evaluation requires a parsed manifest SHA")

    by_case: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        case_id = row.get("case_id", row.get("id"))
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("Parsed output row lacks a non-empty case_id")
        by_case[case_id].append(row)

    selected: list[dict] = []
    resolved: list[dict] = []
    for case_id, candidates in by_case.items():
        for candidate in candidates:
            resume = candidate.get("resume_key")
            if resume is not None and config_id is not None and model_sha is not None:
                expected_resume = ":".join([out_benchmark_sha, model_sha.lower(),
                                            out_manifest_sha.lower(), config_id, case_id])
                if resume != expected_resume:
                    raise ValueError(f"Resume key does not bind parsed identities for {case_id!r}")
        if len(candidates) == 1:
            only = candidates[0]
            retry_mode = only.get("retry_mode", "initial")
            if retry_mode not in {"initial", "legacy"} and attempt_rows is None:
                raise ValueError(
                    f"Retry row for {case_id!r} requires exact RAW attempts for authorization")
            if attempt_rows is not None and only.get("resume_key"):
                trace = only.get("attempt_trace")
                if not isinstance(trace, list) or not trace:
                    if retry_mode not in {"initial", "legacy"}:
                        raise ValueError(f"Retry row for {case_id!r} lacks an attempt trace")
                else:
                    groups = _validate_attempt_groups(
                        attempt_rows, only.get("resume_key"), expected_identity=only)
                    matches = [g for g in groups if g["attempt_trace"] == trace]
                    if len(matches) != 1:
                        raise ValueError(f"Parsed row for {case_id!r} has ambiguous RAW provenance")
                    if matches[0]["final_attempt"] != groups[-1]["final_attempt"]:
                        raise ValueError(
                            f"Single parsed row for {case_id!r} is not the latest RAW-verified attempt")
                    _verify_parsed_against_group(only, matches[0])
            elif retry_mode not in {"initial", "legacy"}:
                if attempt_rows is None:
                    raise ValueError(
                        f"Retry row for {case_id!r} requires exact RAW attempts for authorization")
            selected.append(only)
            continue
        if attempt_rows is None:
            raise ValueError(
                f"Duplicate parsed rows for case {case_id!r}; exact RAW attempts are required")
        resume_keys = {row.get("resume_key") for row in candidates}
        if len(resume_keys) != 1 or not isinstance(next(iter(resume_keys)), str):
            raise ValueError(f"Duplicate parsed rows for {case_id!r} do not share a resume_key")
        groups = _validate_attempt_groups(
            attempt_rows, next(iter(resume_keys)), expected_identity=candidates[0])
        candidate_groups: list[tuple[dict, dict]] = []
        for candidate in candidates:
            trace = candidate.get("attempt_trace")
            if not isinstance(trace, list) or not trace:
                raise ValueError(f"Duplicate parsed row for {case_id!r} lacks an attempt trace")
            if candidate.get("resume_key") != next(iter(resume_keys)):
                raise ValueError(f"Duplicate parsed rows for {case_id!r} disagree on resume_key")
            matches = [group for group in groups if group["attempt_trace"] == trace]
            if len(matches) != 1:
                raise ValueError(f"Duplicate parsed row for {case_id!r} has ambiguous RAW provenance")
            _verify_parsed_against_group(candidate, matches[0])
            candidate_groups.append((candidate, matches[0]))
        group_traces = [group["attempt_trace"] for _, group in candidate_groups]
        if len(set(tuple(trace) for trace in group_traces)) != len(group_traces):
            raise ValueError(f"Duplicate parsed rows for {case_id!r} point to the same attempt group")
        if len(candidate_groups) != len(groups):
            raise ValueError(f"Parsed rows for {case_id!r} do not cover every RAW attempt group")
        candidate_groups.sort(key=lambda pair: pair[1]["final_attempt"])
        chosen, latest_group = candidate_groups[-1]
        selected.append(chosen)
        resolved.append({"case_id": case_id,
                         "selected_attempt": latest_group["final_attempt"],
                         "selected_attempt_trace": latest_group["attempt_trace"],
                         "retry_mode": latest_group["retry_mode"],
                         "discarded_rows": len(candidates) - 1})
    selected.sort(key=lambda row: row.get("derived_seq", 0)
                  if isinstance(row.get("derived_seq", 0), int) else 0)
    return selected, {"rows_in": len(rows), "rows_selected": len(selected),
                      "duplicate_cases_resolved": resolved,
                      "selection_policy": "highest verified final attempt number"}


def _verify_parsed_against_group(parsed: dict, group: dict) -> None:
    if parsed.get("attempt_trace") != group["attempt_trace"]:
        raise ValueError("Parsed attempt trace differs from exact RAW attempts")
    for key in ("retry_mode", "retry_of_attempt", "retry_of_outcome"):
        if parsed.get(key, "initial" if key == "retry_mode" else None) != group.get(key):
            raise ValueError(f"Parsed {key} differs from exact RAW attempts")
    transport = parsed.get("transport")
    if not isinstance(transport, dict):
        raise ValueError("Runner parsed row lacks transport metadata")
    if (transport.get("outcome") != group["outcome"]
            or transport.get("http_status") != group["http_status"]
            or transport.get("attempts") != group["attempts"]):
        raise ValueError("Parsed transport outcome differs from exact RAW attempts")
    if parsed.get("raw_response") != group["raw_response"]:
        raise ValueError("Parsed response content differs from exact RAW body")


# ---------------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------------

def evaluate_case(view: dict, raw_row: dict | None, human: dict | None) -> dict:
    result: dict = {
        "case_id": view["case_id"],
        "level": view["level"],
        "condition": view["condition"],
        "provisional": True,
        "needs_human_review": False,
        "review_reasons": [],
        "format": {},
        "schema_valid": None,
        "schema_errors": [],
        "verdict_provisional": None,
        "verdict_final": None,
        "human_evaluation": human,
    }
    if isinstance(raw_row, dict):
        trace = raw_row.get("attempt_trace")
        if isinstance(trace, list) and trace:
            result["response_provenance"] = {
                "resume_key": raw_row.get("resume_key"),
                "benchmark_sha256": raw_row.get("benchmark_sha256"),
                "manifest_sha256": raw_row.get("manifest_sha256"),
                "model_sha256": raw_row.get("model_sha256"),
                "config_id": raw_row.get("config_id"),
                "attempt_trace": trace,
                "selected_attempt": trace[-1],
                "retry_mode": raw_row.get("retry_mode", "initial"),
                "retry_of_attempt": raw_row.get("retry_of_attempt"),
                "retry_of_outcome": raw_row.get("retry_of_outcome"),
                "derived_seq": raw_row.get("derived_seq"),
            }
    reasons: list[str] = []

    if view["invalid"]:
        result.update(verdict_provisional="INVALID_CASE", verdict_final="INVALID_CASE",
                      provisional=False if human else True)
        result["format"] = {"parse_status": "skipped_invalid_case"}
        if human and isinstance(human, dict) and human.get("verdict") == "INVALID_CASE":
            result["provisional"] = False
        return result
    if human and isinstance(human, dict) and human.get("verdict") == "INVALID_CASE":
        if human.get("reviewer") and human.get("rationale"):
            result.update(verdict_provisional="INVALID_CASE", verdict_final="INVALID_CASE",
                          provisional=False, needs_human_review=False)
            result["format"] = {"parse_status": "invalidated_by_human"}
            return result
        reasons.append("human_invalid_missing_traceability")

    if raw_row is None:
        result["format"] = {"parse_status": "missing_output", "json_direct": False,
                            "json_recoverable": False, "has_fence": False,
                            "text_outside_json": False}
        result.update(tp=0, fp=0, fn=len((view["gold"].get("errors") or [])),
                      verdict_provisional="INCORRECT")
        result["needs_human_review"] = False
        result["review_reasons"] = ["missing_output"]
        result["verdict_final"] = apply_human_override(result["verdict_provisional"], human, result)
        return result

    raw = raw_row.get("raw_response")
    fmt = detect_format(raw)
    result["format"] = {k: fmt[k] for k in
                        ("parse_status", "has_fence", "text_outside_json",
                         "json_direct", "json_recoverable", "method")}
    parsed = fmt["parsed"]

    schema_valid, schema_errors = validate_schema(parsed) if fmt["parsed"] is not None else (False, ["no_parsed_json"])
    result["schema_valid"] = schema_valid
    result["schema_errors"] = schema_errors
    strict_json = bool(fmt["json_direct"] and not fmt["has_fence"]
                       and not fmt["text_outside_json"] and schema_valid)
    result["format"]["strict_json_compliant"] = strict_json

    gold = view["gold"] or {}
    gold_errors = gold.get("errors") if isinstance(gold.get("errors"), list) else []
    alternatives = gold.get("acceptable_alternatives") if isinstance(gold.get("acceptable_alternatives"), list) else []

    pred_is_correct = parsed.get("is_correct") if isinstance(parsed, dict) else None
    pred_corrected = parsed.get("corrected_text") if isinstance(parsed, dict) else None
    pred_errors = parsed.get("errors") if isinstance(parsed, dict) and isinstance(parsed.get("errors"), list) else []

    coverage = match_errors(gold_errors, pred_errors, pred_corrected if isinstance(pred_corrected, str) else "")
    result.update(tp=coverage["tp"], fp=coverage["fp"], fn=coverage["fn"],
                  error_match_details=coverage["details"])
    result["metrics_provisional"] = pr_f05(coverage["tp"], coverage["fp"], coverage["fn"])
    reasons.extend(coverage["review_reasons"])

    text_match = corrected_text_match(view["student_text"], gold.get("corrected_text"),
                                      alternatives, pred_corrected)
    result["corrected_text_match"] = text_match
    if text_match == "alternative":
        reasons.append("alternative_match_pending_review")
    elif text_match == "fuzzy_only":
        reasons.append("fuzzy_resemblance_only")

    changed = is_substantially_changed(view["student_text"], pred_corrected)
    result["corrected_text_changed"] = changed
    if view["condition"] == "correct":
        result["control_false_alarm"] = bool(pred_is_correct is False or (isinstance(pred_errors, list) and len(pred_errors) > 0))
        result["control_fully_preserved"] = bool(
            isinstance(pred_corrected, str) and isinstance(view["student_text"], str)
            and pred_corrected == view["student_text"]
            and pred_is_correct is True and len(pred_errors) == 0
            and schema_valid
        )
    if view.get("evaluation_note"):
        reasons.append("gold_evaluation_note_ambiguous")

    # ---- Provisional verdict ----
    if fmt["parse_status"] == "invalid":
        verdict = "INCORRECT"
        reasons.append("unparseable_json")
    elif view["condition"] == "correct":
        if (pred_is_correct is True and isinstance(pred_errors, list) and len(pred_errors) == 0
                and isinstance(pred_corrected, str) and isinstance(view["student_text"], str)
                and pred_corrected == view["student_text"]
                and schema_valid):
            verdict = "CORRECT"
        else:
            verdict = "INCORRECT"
            if not schema_valid:
                reasons.append("schema_invalid")
            if changed:
                reasons.append("control_text_modified")
            if pred_is_correct is False or (isinstance(pred_errors, list) and len(pred_errors) > 0):
                reasons.append("control_false_alarm")
            if text_match in ("alternative", "fuzzy_only"):
                reasons.append("control_variant_pending_review")
            elif changed and text_match == "none":
                # Any non-trivial control rewrite stays reviewable so a
                # dialect-only variant can be rescued by a human with rationale.
                reasons.append("control_change_pending_review")
    else:  # incorrect condition
        n_gold = len(gold_errors)
        tp, fp, fn = coverage["tp"], coverage["fp"], coverage["fn"]
        flag_wrong = pred_is_correct is True
        if not schema_valid:
            verdict = "INCORRECT"
            reasons.append("schema_invalid")
        elif tp == n_gold and fp == 0 and text_match == "exact_primary" and not flag_wrong:
            if coverage["alternative_only"]:
                verdict = "PARTIAL"
                reasons.append("alternative_match_pending_review")
            else:
                verdict = "CORRECT"
                reasons.append("meaning_explanation_unconfirmed")
        elif tp == n_gold and fp == 0 and text_match == "alternative" and not flag_wrong:
            verdict = "PARTIAL"
            reasons.append("alternative_match_pending_review")
        elif tp > 0 or (text_match in ("exact_primary", "alternative") and fn < n_gold):
            verdict = "PARTIAL"
            if flag_wrong:
                reasons.append("flag_claims_correct")
            if fp > 0:
                reasons.append("false_errors_invented")
            if fn > 0:
                reasons.append("errors_missed")
        else:
            verdict = "INCORRECT"
            if flag_wrong:
                reasons.append("flag_claims_correct")
            if fn > 0 and tp == 0:
                reasons.append("no_gold_error_covered")

    result["verdict_provisional"] = verdict
    # CORRECT on incorrect cases always needs meaning/explanation confirmation.
    # Clean controls and clear INCORRECTs do not auto-require review unless a
    # specific ambiguity reason was recorded.
    if view["condition"] != "correct" and verdict == "CORRECT":
        if "meaning_explanation_unconfirmed" not in reasons:
            reasons.append("meaning_explanation_unconfirmed")
        result["needs_human_review"] = True
    else:
        result["needs_human_review"] = any(
            r for r in reasons if r not in ("false_errors_invented", "errors_missed",
                                            "no_gold_error_covered", "schema_invalid",
                                            "unparseable_json", "flag_claims_correct")
        ) or (len(reasons) > 0 and verdict in ("PARTIAL",))
        # Clear INCORRECT with only miss-type reasons stays non-review to keep
        # the queue focused; ambiguous/fuzzy/alternative cases stay reviewable.
        if verdict == "INCORRECT" and not any(
                r in reasons for r in ("alternative_match_pending_review",
                                       "fuzzy_resemblance_only", "undeclared_fix",
                                       "declared_but_not_realized",
                                       "gold_evaluation_note_ambiguous",
                                       "control_variant_pending_review",
                                       "control_change_pending_review",
                                       "shared_correction_ambiguous")):
            # Keep flag-claims-correct / plain misses as non-review INCORRECT.
            if view["condition"] == "correct" and "control_change_pending_review" in reasons:
                result["needs_human_review"] = True
            elif view["condition"] != "correct":
                result["needs_human_review"] = any(
                    r in reasons for r in ("alternative_match_pending_review",
                                           "fuzzy_resemblance_only", "undeclared_fix",
                                           "declared_but_not_realized",
                                           "gold_evaluation_note_ambiguous",
                                           "shared_correction_ambiguous"))
    result["review_reasons"] = sorted(set(reasons))
    result["verdict_final"] = apply_human_override(verdict, human, result)
    result["provisional"] = result["verdict_final"] == verdict and (
        human is None or not valid_human(human))
    if not result["provisional"]:
        result["needs_human_review"] = False
    return result


def valid_human(human: dict | None) -> bool:
    return (isinstance(human, dict) and human.get("verdict") in VERDICTS
            and isinstance(human.get("reviewer"), str) and human["reviewer"].strip() != ""
            and isinstance(human.get("rationale"), str) and human["rationale"].strip() != "")


def apply_human_override(provisional: str, human: dict | None, result: dict) -> str:
    if valid_human(human):
        return human["verdict"]
    if human is not None:
        result.setdefault("review_reasons", []).append("human_evaluation_missing_traceability")
        result["needs_human_review"] = True
    return provisional


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def length_bucket(words: int | None) -> str:
    if words is None:
        return "unknown"
    if words <= 30:
        return "short_<=30"
    if words <= 60:
        return "medium_31-60"
    return "long_>60"


def error_count_bucket(n: int) -> str:
    if n <= 1:
        return "1_error"
    if n == 2:
        return "2_errors"
    if n == 3:
        return "3_errors"
    return "4+_errors"


def summarize(evals: list[dict], views: dict[str, dict], benchmark_meta: dict,
              model_name: str | None) -> dict:
    scored = [e for e in evals if e["verdict_final"] != "INVALID_CASE"]
    invalid_n = len(evals) - len(scored)
    verdict_counts = Counter(e["verdict_final"] for e in scored)
    prov_counts = Counter(e["verdict_provisional"] for e in scored)

    fmt_counts = Counter(e["format"].get("parse_status", "unknown") for e in scored)
    schema_ok = sum(1 for e in scored if e["schema_valid"] is True)
    strict_n = sum(1 for e in scored if e["format"].get("strict_json_compliant") is True)
    fence_n = sum(1 for e in scored if e["format"].get("has_fence") is True)
    outside_n = sum(1 for e in scored if e["format"].get("text_outside_json") is True)

    incorrect = [e for e in scored if e["condition"] == "incorrect"]
    tp = sum(e.get("tp", 0) for e in incorrect)
    fp = sum(e.get("fp", 0) for e in incorrect)
    fn = sum(e.get("fn", 0) for e in incorrect)
    detection = {"tp": tp, "fp": fp, "fn": fn, **pr_f05(tp, fp, fn)}

    controls = [e for e in scored if e["condition"] == "correct"]
    n_controls = len(controls)
    ctmr_n = sum(1 for e in controls if e.get("corrected_text_changed") is True)
    cfar_n = sum(1 for e in controls if e.get("control_false_alarm") is True)
    preserved_n = sum(1 for e in controls if e.get("control_fully_preserved") is True)
    control_unknown_n = sum(1 for e in controls if e.get("corrected_text_changed") is None)
    cfar_unknown_n = sum(1 for e in controls if e.get("schema_valid") is not True)

    review_n = sum(1 for e in scored if e["needs_human_review"])
    confirmed_n = sum(1 for e in scored if not e["provisional"])

    by_level: dict = {}
    for level in ("A1", "A2"):
        subset = [e for e in incorrect if e["level"] == level]
        s_tp = sum(e.get("tp", 0) for e in subset)
        s_fp = sum(e.get("fp", 0) for e in subset)
        s_fn = sum(e.get("fn", 0) for e in subset)
        vc = Counter(e["verdict_final"] for e in scored if e["level"] == level)
        by_level[level] = {"cases": len([e for e in scored if e["level"] == level]),
                           "verdicts": dict(vc),
                           "error_detection": {"tp": s_tp, "fp": s_fp, "fn": s_fn,
                                               **pr_f05(s_tp, s_fp, s_fn)}}
    by_taxonomy: dict = {}
    tax_tp: Counter = Counter()
    tax_fn: Counter = Counter()
    for e in incorrect:
        for d in e.get("error_match_details", []):
            view = views.get(e["case_id"], {})
            gold_errors = (view.get("gold", {}) or {}).get("errors", []) or []
            gi = d.get("gold_index")
            etype = gold_errors[gi].get("type", "UNKNOWN") if isinstance(gi, int) and gi < len(gold_errors) else "UNKNOWN"
            if d.get("status") == "TP":
                tax_tp[etype] += 1
            else:
                tax_fn[etype] += 1
    for etype in sorted(set(tax_tp) | set(tax_fn)):
        t_tp, t_fn = tax_tp[etype], tax_fn[etype]
        rec = t_tp / (t_tp + t_fn) if (t_tp + t_fn) else 0.0
        by_taxonomy[etype] = {"tp": t_tp, "fn": t_fn, "recall": rec}

    by_error_count: dict = {}
    for e in incorrect:
        view = views.get(e["case_id"], {})
        n = len((view.get("gold", {}) or {}).get("errors", []) or [])
        bucket = error_count_bucket(n)
        by_error_count.setdefault(bucket, {"cases": 0, "tp": 0, "fp": 0, "fn": 0,
                                           "verdicts": Counter()})
        by_error_count[bucket]["cases"] += 1
        by_error_count[bucket]["tp"] += e.get("tp", 0)
        by_error_count[bucket]["fp"] += e.get("fp", 0)
        by_error_count[bucket]["fn"] += e.get("fn", 0)
        by_error_count[bucket]["verdicts"][e["verdict_final"]] += 1
    for bucket, block in by_error_count.items():
        block.update(pr_f05(block["tp"], block["fp"], block["fn"]))
        block["verdicts"] = dict(block["verdicts"])

    by_length: dict = {}
    for e in scored:
        view = views.get(e["case_id"], {})
        student = view.get("student_text")
        words = count_words(student) if isinstance(student, str) else None
        bucket = length_bucket(words)
        by_length.setdefault(bucket, {"cases": 0, "verdicts": Counter()})
        by_length[bucket]["cases"] += 1
        by_length[bucket]["verdicts"][e["verdict_final"]] += 1
    for block in by_length.values():
        block["verdicts"] = dict(block["verdicts"])

    return {
        "metadata": {
            "benchmark_id": benchmark_meta.get("benchmark_id"),
            "model_name": model_name,
            "cases_total": len(evals),
            "cases_scored": len(scored),
            "cases_invalid_excluded": invalid_n,
            "provisional_note": ("All verdicts/scores without a traced human "
                                  "evaluation are PROVISIONAL. Meaning and "
                                  "explanation quality require explicit human "
                                  "judgment."),
            "human_confirmed_cases": confirmed_n,
        },
        "verdicts_final": {v: verdict_counts.get(v, 0) for v in VERDICTS},
        "verdicts_provisional": {v: prov_counts.get(v, 0) for v in VERDICTS},
        "format": {"parse_status_counts": dict(fmt_counts),
                   "schema_valid": schema_ok,
                   "strict_json_compliant": strict_n,
                   "with_fences": fence_n,
                   "with_text_outside_json": outside_n},
        "error_detection_incorrect_only": detection,
        "error_detection_status": "PROVISIONAL_STRICT_MATCH_PROXY; traced verdict overrides do not automatically adjudicate TP/FP/FN counts",
        "detection_metric_policy": "Provisional strict licensed-realized matches with exact original spans; not semantic detection ground truth. Broader valid spans and unlisted valid corrections require traced human adjudication.",
        "controls": {"n_controls": n_controls,
                     "ctmr_modified": ctmr_n,
                     "ctmr_rate": (ctmr_n / n_controls) if n_controls else 0.0,
                     "cfar_false_alarm": cfar_n,
                     "cfar_rate": (cfar_n / n_controls) if n_controls else 0.0,
                      "fully_preserved": preserved_n,
                      "fully_preserved_rate": (preserved_n / n_controls) if n_controls else 0.0,
                      "ctmr_unobservable": control_unknown_n,
                      "cfar_schema_unobservable": cfar_unknown_n,
                      "denominator_policy": "All non-invalid controls, including missing/unparseable outputs; unknown outcomes are explicitly reported, not certified as correct negatives.",
                      "ctmr_rate_upper_bound": ((ctmr_n + control_unknown_n) / n_controls) if n_controls else 0.0},
        "needs_human_review": review_n,
        "by_level": by_level,
        "by_taxonomy_recall": by_taxonomy,
        "by_error_count": by_error_count,
        "by_length_words": by_length,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, help="Benchmark gold JSON file.")
    parser.add_argument("--raw", required=True,
                        help="Runner parsed responses JSONL (raw_response plus telemetry).")
    parser.add_argument("--attempts", default=None,
                        help="Exact runner raw attempts JSONL; required for all runner output, "
                             "to verify that each parsed row is the latest attempt.")
    parser.add_argument("--manifest", default=None,
                        help="Optional manifest JSON used to bind config/model/manifest SHA.")
    parser.add_argument("--human-evals", default=None,
                        help="Optional human evaluations JSONL.")
    parser.add_argument("--out-evals", required=True, help="Output evaluations JSONL.")
    parser.add_argument("--out-summary", required=True, help="Output summary JSON.")
    parser.add_argument("--model", default=None, help="Model label for the summary.")
    parser.add_argument("--config", default=None,
                        help="Assert one exact config_id; mixed configurations are rejected.")
    parser.add_argument("--invalid-cases", default=None, help="Shared, benchmark-SHA-bound invalidation registry for every configuration.")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    benchmark_meta, cases = load_benchmark(Path(args.benchmark))
    views = {c.get("id", c.get("case_id", "")): case_view(c) for c in cases}
    if len(views) != len(cases):
        raise ValueError("Duplicate benchmark case IDs")
    benchmark_sha = file_sha256(Path(args.benchmark))
    if args.invalid_cases:
        registry = strict_json_loads(Path(args.invalid_cases).read_text(encoding="utf-8"))
        if registry.get("benchmark_sha256") != benchmark_sha or not isinstance(registry.get("invalid_cases"), list):
            raise ValueError("Shared invalidation registry must bind the current benchmark SHA and list invalid_cases")
        for entry in registry["invalid_cases"]:
            cid = entry.get("case_id")
            if cid not in views or not all(isinstance(entry.get(key), str) and entry[key].strip() for key in ["reviewer", "rationale"]):
                raise ValueError("Invalidation requires known case_id plus reviewer/rationale")
            views[cid]["invalid"] = True
            views[cid]["invalidation_record"] = entry
    raw_rows = load_jsonl(Path(args.raw))
    attempt_rows = load_jsonl(Path(args.attempts)) if args.attempts else None
    manifest_data = None
    manifest_sha = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        manifest_data = strict_json_loads(manifest_path.read_text(encoding="utf-8"))
        manifest_sha = file_sha256(manifest_path)
    raw_rows, selection_report = select_authorized_latest_rows(
        raw_rows, benchmark_sha, attempt_rows=attempt_rows,
        config_filter=args.config, manifest_sha=manifest_sha,
        manifest_data=manifest_data)
    humans = {row.get("case_id", row.get("id", "")): row
              for row in load_jsonl(args.human_evals)}

    by_case: dict[str, dict] = {}
    for row in raw_rows:
        cid = row.get("case_id", row.get("id", ""))
        if cid in by_case:
            raise ValueError(f"Duplicate raw rows remain for case {cid!r}; refusing to guess.")
        by_case[cid] = row
    model_label = args.model or (raw_rows[0].get("model_name") if raw_rows else None)

    evals: list[dict] = []
    for case in cases:
        cid = case.get("id", case.get("case_id", ""))
        row = by_case.get(cid)
        evals.append(evaluate_case(views[cid], row,
                                   humans.get(cid)))
    extra_ids = sorted(set(by_case) - set(views))
    if extra_ids:
        raise ValueError(f"Raw rows reference unknown case IDs: {extra_ids}")

    summary = summarize(evals, views, benchmark_meta, model_label)
    summary["telemetry"] = telemetry_summary(raw_rows)
    summary["benchmark_sha256"] = benchmark_sha
    summary["manifest_sha256"] = manifest_sha
    summary["response_selection"] = selection_report
    summary["shared_invalidation_registry_sha256"] = file_sha256(Path(args.invalid_cases)) if args.invalid_cases else None

    out_evals = Path(args.out_evals)
    out_evals.parent.mkdir(parents=True, exist_ok=True)
    out_evals.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in evals) + "\n",
                         encoding="utf-8")
    out_summary = Path(args.out_summary)
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(json.dumps({"cases": len(evals), "scored": summary["metadata"]["cases_scored"],
                      "invalid_excluded": summary["metadata"]["cases_invalid_excluded"],
                      "needs_review": summary["needs_human_review"],
                      "human_confirmed": summary["metadata"]["human_confirmed_cases"]},
                     ensure_ascii=False))
    return 0


def telemetry_summary(raw_rows: list[dict]) -> dict:
    summary: dict = {}
    for key in ("latency_seconds", "tokens_generated", "tokens_per_second"):
        values = [r[key] for r in raw_rows
                  if isinstance(r.get(key), (int, float))]
        if values:
            summary[key] = {"n": len(values), "mean": statistics.mean(values),
                            "median": statistics.median(values),
                            "min": min(values), "max": max(values)}
    summary["rows"] = len(raw_rows)
    summary["note"] = "Telemetry is passthrough only; it never affects verdicts."
    return summary


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
