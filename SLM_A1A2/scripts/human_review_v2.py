"""Strict human-review records and a blinded, fixed-sample review packet.

This module only prepares review materials for already-collected development
outputs. It performs no model inference, does not change the primary evaluator,
and does not access the reserved final test set.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import secrets
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any


HUMAN_REVIEW_SCHEMA_VERSION = "human_review_v2/1.0"
SAMPLE_PLAN_SCHEMA_VERSION = "human_review_v2.sample_plan/1.0"
PACKET_SCHEMA_VERSION = "human_review_v2.review_packet/1.0"
DEFAULT_SAMPLE_SEED = 20261011

IDENTITY_FIELDS = (
    "scope",
    "benchmark_sha256",
    "manifest_sha256",
    "config_id",
    "case_id",
    "response_sha256",
)
CRITERIA = (
    "detection",
    "correction",
    "meaning_preservation",
    "level_appropriateness",
    "grammatical_explanation",
    "pedagogical_clarity",
    "clean_text_handling",
)
REVIEW_FIELDS = (
    "reviewer_id",
    "review_date",
    "response_assessable",
    "rationale",
    *CRITERIA,
    "meaning_preserved",
    "explanations_ok",
    "verdict",
)
RECORD_FIELDS = frozenset(("schema_version", *IDENTITY_FIELDS, *REVIEW_FIELDS))
VERDICTS = frozenset(("CORRECT", "PARTIAL", "INCORRECT", "INVALID_CASE"))
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Per level, approximate the population's 25/12/6/2 distribution while keeping
# one four-error case in the fixed panel.
ERROR_COUNT_QUOTAS = {1: 8, 2: 4, 3: 2, 4: 1}


class _DuplicateJSONKey(ValueError):
    pass


def _strict_json_loads(raw: str) -> Any:
    """Parse JSON while rejecting duplicate keys and NaN/Infinity constants."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON constant: {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJSONKey(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)


def _nonfinite_paths(value: Any, path: str = "record") -> list[str]:
    found: list[str] = []
    if isinstance(value, float) and not math.isfinite(value):
        found.append(path)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            found.extend(_nonfinite_paths(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_nonfinite_paths(item, f"{path}[{index}]"))
    return found


def _is_rating(value: Any) -> bool:
    # `type(...) is int` deliberately rejects JSON/Python booleans as scores.
    return (type(value) is int and value in (0, 1, 2)) or value == "NA"


def _condition_context(condition: str | Mapping[str, Any]) -> str:
    if isinstance(condition, str):
        return condition
    if not isinstance(condition, Mapping):
        return ""
    # Only the case condition comes from the separate crosswalk. Whether a
    # response can be judged is an explicit human field on the review record.
    return condition.get("condition", "")


def validate_human_record(
    record: Mapping[str, Any] | str,
    expected_identity: Mapping[str, str],
    condition: str | Mapping[str, Any],
) -> list[str]:
    """Return all contract violations without raising for malformed records.

    `record` may be an already-parsed mapping or raw JSON text. Passing raw JSON
    also lets this function detect duplicate JSON keys before they are lost by
    dictionary parsing. `condition` is `correct`/`incorrect`, or a context
    mapping containing the crosswalk's condition. Assessability is never
    inferred from parsing or supplied by the crosswalk: the reviewer fills
    `response_assessable`.
    """

    errors: list[str] = []
    if isinstance(record, str):
        try:
            record = _strict_json_loads(record)
        except (json.JSONDecodeError, ValueError) as exc:
            return [f"invalid JSON record: {exc}"]
    if not isinstance(record, Mapping):
        return ["record must be a JSON object"]

    for path in _nonfinite_paths(record):
        errors.append(f"non-finite number at {path}")

    supplied_keys = set(record.keys())
    missing = sorted(RECORD_FIELDS - supplied_keys)
    unknown = sorted(supplied_keys - RECORD_FIELDS, key=str)
    if missing:
        errors.append("missing required keys: " + ", ".join(missing))
    if unknown:
        errors.append("unknown keys: " + ", ".join(str(key) for key in unknown))

    if record.get("schema_version") != HUMAN_REVIEW_SCHEMA_VERSION:
        errors.append(f"schema_version must be {HUMAN_REVIEW_SCHEMA_VERSION!r}")

    for field in IDENTITY_FIELDS:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")
        elif field in ("benchmark_sha256", "manifest_sha256", "response_sha256") and not HEX_SHA256_RE.fullmatch(value):
            errors.append(f"{field} must be 64 lowercase hexadecimal characters")
        expected = expected_identity.get(field) if isinstance(expected_identity, Mapping) else None
        if not isinstance(expected, str) or not expected:
            errors.append(f"expected_identity is missing {field}")
        elif value != expected:
            errors.append(f"{field} does not match expected identity")
        elif field in ("benchmark_sha256", "manifest_sha256", "response_sha256") and not HEX_SHA256_RE.fullmatch(expected):
            errors.append(f"expected_identity.{field} must be 64 lowercase hexadecimal characters")

    reviewer = record.get("reviewer_id")
    if not isinstance(reviewer, str) or not reviewer.strip():
        errors.append("reviewer_id must be a non-empty string")
    review_date = record.get("review_date")
    if not isinstance(review_date, str):
        errors.append("review_date must be an ISO date (YYYY-MM-DD)")
    else:
        try:
            if date.fromisoformat(review_date).isoformat() != review_date:
                raise ValueError("date is not canonical")
        except ValueError:
            errors.append("review_date must be a valid ISO date (YYYY-MM-DD)")
    response_assessable = record.get("response_assessable")
    if type(response_assessable) is not bool:
        errors.append("response_assessable must be an explicit JSON boolean chosen by the reviewer")
    rationale = record.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append("rationale must be a non-empty string")

    for criterion in CRITERIA:
        if criterion in record and not _is_rating(record[criterion]):
            errors.append(f"{criterion} must be integer 0, 1, 2, or 'NA' (booleans are not scores)")

    condition_label = _condition_context(condition)
    if condition_label not in ("correct", "incorrect"):
        errors.append("condition must be 'correct' or 'incorrect'")
    elif type(response_assessable) is bool and not response_assessable:
        for criterion in CRITERIA:
            if criterion in record and record[criterion] != "NA":
                errors.append(f"{criterion} must be 'NA' when the reviewer marks the response unassessable")
        for field in ("meaning_preserved", "explanations_ok"):
            if field in record and record[field] != "NA":
                errors.append(f"{field} must be 'NA' when the reviewer marks the response unassessable")
    elif condition_label == "correct" and response_assessable is True:
        for criterion in ("detection", "correction"):
            if criterion in record and record[criterion] != "NA":
                errors.append(f"{criterion} must be 'NA' for a correct-text control")
        clean_score = record.get("clean_text_handling")
        if "clean_text_handling" in record and not (type(clean_score) is int and clean_score in (0, 1, 2)):
            errors.append("clean_text_handling must be 0, 1, or 2 for an assessable correct-text control")
        for criterion in ("meaning_preservation", "level_appropriateness", "pedagogical_clarity"):
            score = record.get(criterion)
            if criterion in record and not (type(score) is int and score in (0, 1, 2)):
                errors.append(f"{criterion} must be 0, 1, or 2 for an assessable control")
        explanation_score = record.get("grammatical_explanation")
        if "grammatical_explanation" in record:
            explanations_ok = record.get("explanations_ok")
            if explanations_ok == "NA" and explanation_score != "NA":
                errors.append("grammatical_explanation must be 'NA' when explanations_ok is 'NA' on a control")
            if type(explanations_ok) is bool and not (type(explanation_score) is int and explanation_score in (0, 1, 2)):
                errors.append("grammatical_explanation must be 0, 1, or 2 when a control output has an explanation")
    elif condition_label == "incorrect" and response_assessable is True:
        for criterion in ("detection", "correction"):
            score = record.get(criterion)
            if criterion in record and not (type(score) is int and score in (0, 1, 2)):
                errors.append(f"{criterion} must be 0, 1, or 2 for an assessable incorrect-text case")
        if "clean_text_handling" in record and record["clean_text_handling"] != "NA":
            errors.append("clean_text_handling must be 'NA' for an incorrect-text case")
        for criterion in ("meaning_preservation", "level_appropriateness", "grammatical_explanation", "pedagogical_clarity"):
            score = record.get(criterion)
            if criterion in record and not (type(score) is int and score in (0, 1, 2)):
                errors.append(f"{criterion} must be 0, 1, or 2 for an assessable incorrect-text case")

    for field in ("meaning_preserved", "explanations_ok"):
        value = record.get(field)
        if type(value) is not bool and value != "NA":
            errors.append(f"{field} must be a JSON boolean or 'NA'")

    if condition_label == "incorrect" and response_assessable is True:
        for field in ("meaning_preserved", "explanations_ok"):
            if field in record and type(record[field]) is not bool:
                errors.append(f"{field} must be an explicit JSON boolean for an incorrect-text case")
    elif condition_label == "correct" and response_assessable is True:
        if "meaning_preserved" in record and type(record["meaning_preserved"]) is not bool:
            errors.append("meaning_preserved must be an explicit JSON boolean for an assessable control")
        if "explanations_ok" in record:
            if type(record["explanations_ok"]) is not bool and record["explanations_ok"] != "NA":
                errors.append("explanations_ok must be a JSON boolean or 'NA' for an assessable control")

    if response_assessable is True:
        explanations_ok = record.get("explanations_ok")
        grammar_score = record.get("grammatical_explanation")
        if explanations_ok is False and grammar_score != 0:
            errors.append("explanations_ok=false requires grammatical_explanation=0")
        if explanations_ok is True and grammar_score not in (1, 2):
            errors.append("explanations_ok=true requires grammatical_explanation=1 or 2")
        if explanations_ok == "NA" and condition_label == "correct" and grammar_score != "NA":
            errors.append("explanations_ok='NA' on a control requires grammatical_explanation='NA'")

    verdict = record.get("verdict")
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        errors.append("verdict must be CORRECT, PARTIAL, INCORRECT, or INVALID_CASE")

    if verdict == "CORRECT":
        if record.get("meaning_preserved") is False:
            errors.append("verdict CORRECT conflicts with meaning_preserved=false")
        if record.get("explanations_ok") is False:
            errors.append("verdict CORRECT conflicts with explanations_ok=false")
        applicable_scores = [record.get(criterion) for criterion in CRITERIA if record.get(criterion) != "NA"]
        if any(type(score) is int and score == 0 for score in applicable_scores):
            errors.append("verdict CORRECT conflicts with a zero score on an applicable criterion")
        if not applicable_scores:
            errors.append("verdict CORRECT cannot be assigned when all criteria are NA")
    if verdict == "CORRECT" and response_assessable is False:
        errors.append("an unassessable response cannot receive verdict CORRECT")
    if response_assessable is False and verdict not in ("INCORRECT", "INVALID_CASE"):
        errors.append("an unassessable response must receive verdict INCORRECT or INVALID_CASE")

    # Do not derive or emit any human-confirmed flag here. A valid record is an
    # auditable human claim, not a side effect on primary evaluation results.
    return errors


def _case_id(case: Mapping[str, Any]) -> str:
    value = case.get("id", case.get("case_id"))
    if not isinstance(value, str) or not value.strip():
        raise ValueError("every case must have a non-empty id or case_id")
    return value


def _gold(case: Mapping[str, Any]) -> Mapping[str, Any]:
    value = case.get("gold", {})
    if not isinstance(value, Mapping):
        raise ValueError(f"case {_case_id(case)} has malformed gold")
    return value


def build_sample_plan(cases: Sequence[Mapping[str, Any]], seed: int = DEFAULT_SAMPLE_SEED) -> dict[str, Any]:
    """Build a seeded 60-case panel: all controls plus stratified incorrect cases.

    The design matches the frozen 120-case development benchmark: 15 controls
    per level and 45 incorrect cases per level in the population. Within each
    level, the selected 15 incorrect cases target error-count quotas 8/4/2/1
    for 1/2/3/4 gold errors, approximating the population distribution while
    retaining a four-error case. When a count stratum has both alternative-bearing
    and other cases, selection includes both and follows the population mix as
    closely as the quota permits.
    """

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise ValueError("cases must be a sequence of benchmark case objects")
    if len(cases) != 120:
        raise ValueError(f"expected the 120-case development benchmark, received {len(cases)} cases")

    by_id: dict[str, Mapping[str, Any]] = {}
    grouped: dict[tuple[str, str], list[tuple[str, int, bool]]] = {}
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("every case must be an object")
        case_id = _case_id(case)
        if case_id in by_id:
            raise ValueError(f"duplicate case id: {case_id}")
        by_id[case_id] = case
        level = case.get("level")
        condition = case.get("condition")
        if level not in ("A1", "A2") or condition not in ("correct", "incorrect"):
            raise ValueError(f"case {case_id} has an unsupported level or condition")
        gold = _gold(case)
        if condition == "correct":
            error_count = 0
            has_alternatives = False
        else:
            errors = gold.get("errors")
            alternatives = gold.get("acceptable_alternatives", [])
            if not isinstance(errors, list) or not 1 <= len(errors) <= 4:
                raise ValueError(f"incorrect case {case_id} must have 1 to 4 gold errors")
            if not isinstance(alternatives, list):
                raise ValueError(f"case {case_id} acceptable_alternatives must be an array")
            error_count = len(errors)
            has_alternatives = bool(alternatives)
        grouped.setdefault((level, condition), []).append((case_id, error_count, has_alternatives))

    expected_counts = {
        ("A1", "correct"): 15,
        ("A2", "correct"): 15,
        ("A1", "incorrect"): 45,
        ("A2", "incorrect"): 45,
    }
    for group, expected in expected_counts.items():
        actual = len(grouped.get(group, []))
        if actual != expected:
            raise ValueError(f"expected {expected} cases in {group}, found {actual}")

    rng = random.Random(seed)
    selected: list[str] = []
    selected.extend(sorted(item[0] for level in ("A1", "A2") for item in grouped[(level, "correct")]))
    strata: list[dict[str, Any]] = []

    for level in ("A1", "A2"):
        level_selected_count = 0
        for error_count, quota in ERROR_COUNT_QUOTAS.items():
            items = [item for item in grouped[(level, "incorrect")] if item[1] == error_count]
            with_alt = sorted(item[0] for item in items if item[2])
            without_alt = sorted(item[0] for item in items if not item[2])
            if not items:
                raise ValueError(f"no {level} incorrect cases with {error_count} gold errors")

            if with_alt and without_alt and quota >= 2:
                desired_alt = int(quota * len(with_alt) / len(items) + 0.5)
                alt_quota = min(quota - 1, max(1, desired_alt))
            elif with_alt:
                alt_quota = quota
            else:
                alt_quota = 0
            plain_quota = quota - alt_quota
            if len(with_alt) < alt_quota or len(without_alt) < plain_quota:
                raise ValueError(
                    f"stratum {level}, {error_count} errors cannot meet alternative quotas "
                    f"({alt_quota} with, {plain_quota} without)"
                )
            rng.shuffle(with_alt)
            rng.shuffle(without_alt)
            chosen = with_alt[:alt_quota] + without_alt[:plain_quota]
            selected.extend(chosen)
            level_selected_count += len(chosen)
            strata.append({
                "level": level,
                "condition": "incorrect",
                "gold_error_count": error_count,
                "has_acceptable_alternatives": True,
                "population_count": len(with_alt),
                "selected_count": alt_quota,
            })
            strata.append({
                "level": level,
                "condition": "incorrect",
                "gold_error_count": error_count,
                "has_acceptable_alternatives": False,
                "population_count": len(without_alt),
                "selected_count": plain_quota,
            })
        if level_selected_count != 15:
            raise ValueError(f"internal sampling error: expected 15 incorrect cases for {level}")

    rng.shuffle(selected)
    sorted_selected = sorted(selected)
    selection_hash = hashlib.sha256("\n".join(sorted_selected).encode("utf-8")).hexdigest()
    control_counts = {level: len(grouped[(level, "correct")]) for level in ("A1", "A2")}
    return {
        "schema_version": SAMPLE_PLAN_SCHEMA_VERSION,
        "seed": seed,
        "population_case_ids": sorted(by_id),
        "selected_case_ids": selected,
        "selected_case_ids_sha256": selection_hash,
        "selected_counts": {
            "total": len(selected),
            "controls": sum(control_counts.values()),
            "incorrect": 30,
            "by_level_condition": {
                "A1": {"correct": control_counts["A1"], "incorrect": 15},
                "A2": {"correct": control_counts["A2"], "incorrect": 15},
            },
        },
        "incorrect_strata": strata,
        "alternative_definition": "gold.acceptable_alternatives is a non-empty array",
        "design_note": "The same selected case IDs are used for every configuration included in a review packet.",
    }


def _row_identity(row: Mapping[str, Any]) -> dict[str, str]:
    identity: dict[str, str] = {}
    for field in IDENTITY_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"row is missing non-empty identity field {field}")
        identity[field] = value
    for field in ("benchmark_sha256", "manifest_sha256", "response_sha256"):
        if not HEX_SHA256_RE.fullmatch(identity[field]):
            raise ValueError(f"row {field} must be 64 lowercase hexadecimal characters")
    return identity


def _blank_review_template() -> dict[str, Any]:
    template: dict[str, Any] = {
        "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
        "reviewer_id": None,
        "review_date": None,
        "response_assessable": None,
        "rationale": None,
    }
    template.update({criterion: None for criterion in CRITERIA})
    template.update({
        "meaning_preserved": None,
        "explanations_ok": None,
        "verdict": None,
    })
    return template


def packet_for_rows(
    rows: Sequence[Mapping[str, Any]],
    sample_plan: Mapping[str, Any],
    seed: int = DEFAULT_SAMPLE_SEED,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a blind review packet and a separate identity crosswalk.

    Rows may cover the complete benchmark; this function filters to the fixed
    sample. Each included configuration must have exactly one row for every
    selected case. The human-facing packet shows level, task, student text, and
    exact response; it omits case, condition, configuration, and model
    identity. Save the returned crosswalk separately.
    """

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    selected = sample_plan.get("selected_case_ids")
    population = sample_plan.get("population_case_ids")
    if not isinstance(selected, list) or len(selected) != 60 or len(set(selected)) != 60:
        raise ValueError("sample_plan must contain 60 unique selected_case_ids")
    if not isinstance(population, list) or len(set(population)) != 120:
        raise ValueError("sample_plan must contain 120 unique population_case_ids")
    selected_set = set(selected)
    population_set = set(population)
    if not selected_set <= population_set:
        raise ValueError("sample_plan selected_case_ids must belong to population_case_ids")

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("rows must be a sequence of evaluation v2 rows")
    config_rows: dict[str, dict[str, Mapping[str, Any]]] = {}
    row_identities: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("every evaluation row must be an object")
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("every evaluation row must have a non-empty case_id")
        if case_id not in population_set:
            raise ValueError(f"evaluation row has unknown case_id {case_id}")
        if case_id not in selected_set:
            continue
        identity = _row_identity(row)
        if identity["case_id"] != case_id:
            raise ValueError(f"row case_id does not match its identity for {identity['config_id']}/{case_id}")
        config_id = identity["config_id"]
        response = row.get("raw_response")
        if not isinstance(response, str):
            raise ValueError(f"raw_response must be a string for {config_id}/{case_id}")
        actual_response_hash = hashlib.sha256(response.encode("utf-8")).hexdigest()
        if actual_response_hash != identity["response_sha256"]:
            raise ValueError(f"response_sha256 does not match raw_response for {config_id}/{case_id}")
        if not isinstance(row.get("task"), str) or not isinstance(row.get("student_text"), str):
            raise ValueError(f"task and student_text must be strings for {config_id}/{case_id}")
        if row.get("level") not in ("A1", "A2"):
            raise ValueError(f"level must be A1 or A2 for {config_id}/{case_id}")
        key = tuple(identity[field] for field in IDENTITY_FIELDS)
        if key in row_identities:
            raise ValueError(f"duplicate evaluation identity for {config_id}/{case_id}")
        row_identities[key] = identity
        if case_id in config_rows.setdefault(config_id, {}):
            raise ValueError(f"duplicate evaluation row for {config_id}/{case_id}")
        config_rows[config_id][case_id] = row

    if not config_rows:
        raise ValueError("no sampled evaluation rows were supplied")
    for config_id, rows_by_case in config_rows.items():
        missing = sorted(selected_set - set(rows_by_case))
        if missing:
            raise ValueError(f"configuration {config_id} is missing sampled cases: {', '.join(missing)}")

    records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    blind_ids: set[str] = set()
    for config_id in sorted(config_rows):
        for case_id in sorted(selected_set):
            row = config_rows[config_id][case_id]
            identity = _row_identity(row)
            blind_id = "br-" + secrets.token_hex(12)
            while blind_id in blind_ids:
                blind_id = "br-" + secrets.token_hex(12)
            blind_ids.add(blind_id)
            item = {
                "blind_output_id": blind_id,
                "level": row["level"],
                "task": row["task"],
                "student_text": row["student_text"],
                "response_text": row["raw_response"],
                "review_template": _blank_review_template(),
            }
            records.append((item, {"blind_output_id": blind_id, **identity}))

    random.Random(seed).shuffle(records)
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "items": [item for item, _crosswalk in records],
    }
    crosswalk = {
        "schema_version": "human_review_v2.crosswalk/1.0",
        "identity_fields": list(IDENTITY_FIELDS),
        "items": [item for _packet_item, item in records],
    }
    return packet, crosswalk
