import copy
import json
import re
from pathlib import Path

from validate_benchmark_120 import TAXONOMY

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "benchmark_120" / "drafts"
OUTPUT = ROOT / "benchmark_120" / "normalized"
FILES = [
    "A1_errors_001_015.json", "A1_errors_016_030.json", "A1_errors_031_045.json",
    "A1_controls_001_015.json",
    "A2_errors_001_015.json", "A2_errors_016_030.json", "A2_errors_031_045.json",
    "A2_controls_001_015.json",
]


def infer_type(error):
    if error.get("type") in TAXONOMY:
        return error["type"]
    source = f"{error.get('type', '')} {error.get('type_label', '')}".casefold().replace("-", " ").replace("_", " ")
    rules = [
        ("present perfect", "PRESENT_PERFECT"),
        ("past simple", "PAST_SIMPLE"), ("past tense", "PAST_SIMPLE"),
        ("subject-verb", "SUBJECT_VERB_AGREEMENT"), ("subject verb", "SUBJECT_VERB_AGREEMENT"),
        ("singular/plural", "SINGULAR_PLURAL"), ("plural noun", "SINGULAR_PLURAL"),
        ("number agreement", "SINGULAR_PLURAL"), ("regular plural", "SINGULAR_PLURAL"),
        ("agreement", "SUBJECT_VERB_AGREEMENT"), ("form of be", "BE_FORM"), (" be ", "BE_FORM"),
        ("present continuous", "PRESENT_CONTINUOUS"), ("present simple", "PRESENT_SIMPLE"),
        ("future", "BASIC_FUTURE"), ("article", "ARTICLE"),
        ("subject pronoun", "SUBJECT_PRONOUN"), ("object pronoun", "OBJECT_PRONOUN"),
        ("possessive", "POSSESSIVE"), ("preposition of time", "PREPOSITION_TIME"),
        ("preposition of place", "PREPOSITION_PLACE"), ("preposition after", "VERB_PREPOSITION"),
        ("verb preposition", "VERB_PREPOSITION"), ("word order", "WORD_ORDER"),
        ("question", "QUESTION_FORM"), ("negation", "NEGATION"), ("negative", "NEGATION"),
        ("comparative", "COMPARATIVE"), ("superlative", "SUPERLATIVE"),
        ("some/any", "SOME_ANY"), ("some any", "SOME_ANY"),
        ("much/many", "MUCH_MANY"), ("countable", "COUNTABLE_UNCOUNTABLE"),
        ("uncountable", "COUNTABLE_UNCOUNTABLE"), ("spelling", "SPELLING"),
        ("capital", "CAPITALIZATION"), ("punctuation", "PUNCTUATION"),
        ("connector", "BASIC_CONNECTOR"), ("modal", "BASIC_MODAL"),
        ("verb pattern", "VERB_PATTERN"), ("gerund", "VERB_PATTERN"),
        ("infinitive", "VERB_PATTERN"), ("contraction", "CONTRACTION"),
        ("lexical", "BASIC_LEXICAL_CHOICE"), ("collocation", "BASIC_LEXICAL_CHOICE"),
    ]
    for fragment, label in rules:
        if fragment in source:
            return label
    return error.get("type")


def normalize(case):
    cid = case["id"]
    level = case["level"]
    condition = case.get("condition") or ("incorrect" if "-E" in cid else "correct")
    text = case["student_text"]
    count = len(re.findall(r"\b[\w]+(?:['’][\w]+)*\b", text, re.UNICODE))
    if "gold" in case:
        gold = copy.deepcopy(case["gold"])
    else:
        gold = copy.deepcopy({key: case.get(key) for key in ("is_correct", "corrected_text", "errors", "acceptable_alternatives") if key in case})
    gold.setdefault("is_correct", condition == "correct")
    gold.setdefault("errors", [])
    gold.setdefault("acceptable_alternatives", [])
    if condition == "incorrect" and not gold.get("errors"):
        raise ValueError(f"No gold errors: {cid}")
    # Never erase unexpected control errors or rewrite gold silently.
    # Editorial review and strict validation must resolve discrepancies.
    for error in gold["errors"]:
        error["type"] = infer_type(error)
        if not error.get("subtype"):
            error["subtype"] = (error.get("type_label") or error["type"] or "").casefold().replace(" / ", "_").replace(" ", "_")
        if not error.get("acceptable_corrections") and error.get("correction"):
            error["acceptable_corrections"] = [error["correction"]]
    return {
        "id": cid,
        "level": level,
        "condition": condition,
        "task": case["task"],
        "student_text": text,
        "gold": gold,
        "length_words": count,
        "english_variant": case.get("english_variant", "unspecified; British and American variants accepted"),
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = []
    for filename in FILES:
        source = json.loads((DRAFTS / filename).read_text(encoding="utf-8"))
        output = [normalize(case) for case in source]
        (OUTPUT / filename).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cases.extend(output)
    (OUTPUT / "cases_normalized_preview.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"normalized_files": len(FILES), "case_count": len(cases), "preview": str(OUTPUT / 'cases_normalized_preview.json')}, ensure_ascii=False))


if __name__ == "__main__":
    main()
