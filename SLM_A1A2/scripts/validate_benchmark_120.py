import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "benchmark_120" / "drafts"
SMOKE = ROOT / "benchmark_smoke_test_v2.json"
TAXONOMY = {
    "SUBJECT_VERB_AGREEMENT", "BE_FORM", "PRESENT_SIMPLE", "PRESENT_CONTINUOUS",
    "PAST_SIMPLE", "BASIC_FUTURE", "ARTICLE", "SINGULAR_PLURAL", "SUBJECT_PRONOUN",
    "OBJECT_PRONOUN", "POSSESSIVE", "PREPOSITION_TIME", "PREPOSITION_PLACE",
    "VERB_PREPOSITION", "WORD_ORDER", "QUESTION_FORM", "NEGATION", "COMPARATIVE",
    "SUPERLATIVE", "SOME_ANY", "MUCH_MANY", "COUNTABLE_UNCOUNTABLE",
    "BASIC_LEXICAL_CHOICE", "SPELLING", "CAPITALIZATION", "PUNCTUATION",
    "BASIC_CONNECTOR", "BASIC_MODAL", "PRESENT_PERFECT", "VERB_PATTERN", "CONTRACTION",
}
FILES = [
    "A1_errors_001_015.json", "A1_errors_016_030.json", "A1_errors_031_045.json",
    "A1_controls_001_015.json",
    "A2_errors_001_015.json", "A2_errors_016_030.json", "A2_errors_031_045.json",
    "A2_controls_001_015.json",
]
# Phase 1 is the canonical exact prompt source. No editorial reformulation.
SYSTEM_PROMPT = json.loads(SMOKE.read_text(encoding="utf-8"))["system_prompt"]
USER_PROMPT = "Level: {level}\nTask: {task}\nStudent text: {student_text}"


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return " ".join(text.split())


def count_words(text):
    return len(re.findall(r"\b[\w]+(?:['’][\w]+)*\b", text, re.UNICODE))


def normalized_type(error):
    source = f"{error.get('type', '')} {error.get('type_label', '')}".casefold().replace("-", " ").replace("_", " ")
    rules = [
        (r"subject verb|agreement", "SUBJECT_VERB_AGREEMENT"),
        (r"\bbe\b|form of be", "BE_FORM"),
        (r"present continuous", "PRESENT_CONTINUOUS"),
        (r"present simple", "PRESENT_SIMPLE"),
        (r"present perfect", "PRESENT_PERFECT"),
        (r"past simple|past tense", "PAST_SIMPLE"),
        (r"future", "BASIC_FUTURE"),
        (r"contraction|its/it's", "CONTRACTION"),
        (r"verb pattern|gerund|bare infinitive|infinitive", "VERB_PATTERN"),
        (r"article", "ARTICLE"),
        (r"plural|singular", "SINGULAR_PLURAL"),
        (r"subject pronoun", "SUBJECT_PRONOUN"),
        (r"object pronoun", "OBJECT_PRONOUN"),
        (r"possessive", "POSSESSIVE"),
        (r"preposition.*time|time.*preposition", "PREPOSITION_TIME"),
        (r"preposition.*place|place.*preposition", "PREPOSITION_PLACE"),
        (r"preposition after verb|verb preposition|preposition after", "VERB_PREPOSITION"),
        (r"word order", "WORD_ORDER"),
        (r"question", "QUESTION_FORM"),
        (r"negation|negative", "NEGATION"),
        (r"comparative", "COMPARATIVE"),
        (r"superlative", "SUPERLATIVE"),
        (r"some any|some/any", "SOME_ANY"),
        (r"much many|much/many", "MUCH_MANY"),
        (r"countable|uncountable", "COUNTABLE_UNCOUNTABLE"),
        (r"spelling", "SPELLING"),
        (r"capital", "CAPITALIZATION"),
        (r"punctuation", "PUNCTUATION"),
        (r"connector", "BASIC_CONNECTOR"),
        (r"modal|can |must |should |could ", "BASIC_MODAL"),
        (r"lexical|collocation|word choice", "BASIC_LEXICAL_CHOICE"),
    ]
    for pattern, label in rules:
        if re.search(pattern, source):
            return label
    return None


def flatten(case):
    case_id = case.get("id", "")
    condition = case.get("condition") or ("incorrect" if "-E" in case_id else "correct" if "-C" in case_id else None)
    if "gold" in case:
        gold = case["gold"]
    else:
        gold = {
            "is_correct": case.get("is_correct"),
            "corrected_text": case.get("corrected_text"),
            "errors": case.get("errors"),
            "acceptable_alternatives": case.get("acceptable_alternatives", []),
        }
    if "gold" not in case:
        for key in ("is_correct", "corrected_text", "errors", "acceptable_alternatives"):
            case.pop(key, None)
        case["gold"] = gold
    gold.setdefault("is_correct", condition == "correct")
    gold.setdefault("errors", [])
    gold.setdefault("acceptable_alternatives", [])
    for error in gold.get("errors", []) or []:
        if not error.get("type") or error["type"] not in TAXONOMY:
            inferred = normalized_type(error)
            if inferred:
                error["type"] = inferred
        if not error.get("subtype"):
            error["subtype"] = (error.get("type_label") or error.get("type") or "").casefold().replace(" / ", "_").replace(" ", "_")
        if not error.get("acceptable_corrections") and error.get("correction"):
            error["acceptable_corrections"] = [error["correction"]]
    case.setdefault("condition", condition)
    return {
        "id": case_id,
        "level": case.get("level"),
        "condition": condition,
        "task": case.get("task"),
        "student_text": case.get("student_text"),
        "gold": gold,
        "length_words": case.get("length_words", case.get("longitud_words")),
    }


def run():
    issues = []
    cases = []
    for filename in FILES:
        path = DRAFTS / filename
        if not path.exists():
            issues.append({"severity": "BLOCKER", "file": filename, "issue": "missing draft file"})
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            issues.append({"severity": "BLOCKER", "file": filename, "issue": "top-level value is not a list"})
            continue
        cases.extend(flatten(case) for case in data)

    seen = defaultdict(list)
    smoke = json.loads(SMOKE.read_text(encoding="utf-8"))
    old_cases = [(case["id"], case["student_text"], normalize_text(case["student_text"])) for case in smoke["cases"]]
    type_counts = Counter()
    type_by_level = defaultdict(Counter)
    errors_per_text = Counter()
    lengths = defaultdict(list)
    levels = Counter(case["level"] for case in cases)
    conditions = Counter(case["condition"] for case in cases)
    normalized = []

    for index, case in enumerate(cases):
        cid = case.get("id") or f"MISSING-{index}"
        level = case.get("level")
        expected_prefix = level
        if not cid.startswith(expected_prefix or "!"):
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "ID prefix does not match level"})
        if case.get("condition") not in {"correct", "incorrect"}:
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "unknown condition"})
        if not all(isinstance(case.get(key), str) and case[key].strip() for key in ("task", "student_text")):
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "missing task or student_text"})
            continue

        text = case["student_text"]
        words = count_words(text)
        lengths[level].append(words)
        low, high = (15, 60) if level == "A1" else (25, 100)
        if words < low or words > high:
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "word count outside level range", "words": words, "range": [low, high]})
        if case.get("length_words") != words:
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "length_words mismatch", "declared": case.get("length_words"), "actual": words})
        else:
            case["length_words"] = words
        key = normalize_text(text)
        seen[key].append(cid)
        for old_id, old_text, old_norm in old_cases:
            ratio = SequenceMatcher(None, key, old_norm).ratio()
            if key == old_norm:
                issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "exact smoke text reuse", "smoke_case_id": old_id})
            elif ratio >= 0.78:
                issues.append({"severity": "REVIEW", "case_id": cid, "issue": "near-duplicate candidate against smoke text", "smoke_case_id": old_id, "similarity": round(ratio, 3)})

        gold = case.get("gold")
        if not isinstance(gold, dict):
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "gold must be an object"})
            continue
        errors = gold.get("errors")
        corrected = gold.get("corrected_text")
        expected_correct = case["condition"] == "correct"
        if gold.get("is_correct") is not expected_correct:
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "gold.is_correct disagrees with condition"})
        if not isinstance(errors, list) or not isinstance(corrected, str):
            issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "gold errors/corrected_text malformed"})
            continue
        if expected_correct:
            if errors:
                issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "control has non-empty gold errors"})
            if corrected != text:
                issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "control corrected_text differs from student_text"})
            if gold.get("acceptable_alternatives", []) not in ([], None):
                issues.append({"severity": "REVIEW", "case_id": cid, "issue": "correct control should not need corrected alternatives"})
        else:
            if not errors:
                issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "incorrect text has no gold errors"})
            errors_per_text[len(errors)] += 1
            for err_index, error in enumerate(errors):
                required = ("original", "correction", "acceptable_corrections", "type", "subtype", "explanation")
                if not all(key in error for key in required):
                    issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "gold error missing required field", "error_index": err_index})
                    continue
                if error["type"] not in TAXONOMY:
                    issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "type outside normalized taxonomy", "type": error["type"]})
                type_counts[error["type"]] += 1
                type_by_level[level][error["type"]] += 1
                if not isinstance(error["acceptable_corrections"], list) or not error["acceptable_corrections"]:
                    issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "acceptable_corrections must be a non-empty list"})
                if not error["original"] or error["original"] not in text:
                    issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "gold error fragment not found literally", "error_index": err_index})
                if not all(isinstance(v, str) and v for v in (error["correction"], error["explanation"], error["subtype"])):
                    issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "gold correction/explanation/subtype empty", "error_index": err_index})
                if error["correction"] not in corrected:
                    issues.append({"severity": "BLOCKER", "case_id": cid, "issue": "primary correction absent from corrected_text", "error_index": err_index, "correction": error["correction"]})

        normalized.append(case)

    for text, ids in seen.items():
        if len(ids) > 1:
            issues.append({"severity": "BLOCKER", "issue": "duplicate normalized student text in new set", "case_ids": ids})

    expected_ids = {f"A1-E{i:03d}" for i in range(1, 46)} | {f"A1-C{i:03d}" for i in range(1, 16)} | {f"A2-E{i:03d}" for i in range(1, 46)} | {f"A2-C{i:03d}" for i in range(1, 16)}
    actual_ids = [case["id"] for case in cases if case.get("id")]
    for missing in sorted(expected_ids - set(actual_ids)):
        issues.append({"severity": "BLOCKER", "case_id": missing, "issue": "missing expected case ID"})
    for extra in sorted(set(actual_ids) - expected_ids):
        issues.append({"severity": "BLOCKER", "case_id": extra, "issue": "unexpected case ID"})
    if len(actual_ids) != len(set(actual_ids)):
        issues.append({"severity": "BLOCKER", "issue": "duplicate IDs"})
    if len(cases) != 120:
        issues.append({"severity": "BLOCKER", "issue": "expected 120 cases", "actual": len(cases)})
    if levels != Counter({"A1": 60, "A2": 60}):
        issues.append({"severity": "BLOCKER", "issue": "level counts differ", "counts": dict(levels)})
    expected_conditions = Counter({"incorrect": 90, "correct": 30})
    if conditions != expected_conditions:
        issues.append({"severity": "BLOCKER", "issue": "condition counts differ", "counts": dict(conditions)})

    audit = {
        "draft_case_count": len(cases),
        "level_counts": dict(levels),
        "condition_counts": dict(conditions),
        "error_instance_count": sum(type_counts.values()),
        "error_types": dict(type_counts),
        "error_types_by_level": {level: dict(counter) for level, counter in type_by_level.items()},
        "incorrect_texts_by_error_count": dict(errors_per_text),
        "word_counts": {level: {"mean": round(statistics.mean(vals), 2), "median": statistics.median(vals), "min": min(vals), "max": max(vals)} for level, vals in lengths.items() if vals},
        "issues": issues,
        "blocker_count": sum(issue["severity"] == "BLOCKER" for issue in issues),
        "review_count": sum(issue["severity"] == "REVIEW" for issue in issues),
    }
    # Keep inherited raw draft reports intact. This report is not approval.
    report = ROOT / "benchmark_120" / "draft_validation_current.json"
    report.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("draft_case_count", "level_counts", "condition_counts", "error_instance_count", "incorrect_texts_by_error_count", "word_counts", "blocker_count", "review_count")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
