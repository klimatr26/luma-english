"""Build/strictly validate development cases; never run model inference.

Reviewed sources are not auto-repaired. Phase 1 texts are only used for exclusion.
Passing structural checks does not constitute linguistic or execution approval.
"""

import argparse
import hashlib
import itertools
import json
import re
import statistics
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from validate_benchmark_120 import ROOT, TAXONOMY, count_words, normalize_text


def nonempty_string():
    return {"type": "string", "minLength": 1}


ERROR_SCHEMA = {
    "type": "object",
    "required": ["original", "correction", "acceptable_corrections", "type", "subtype", "explanation"],
    "properties": {
        **{key: nonempty_string() for key in ["original", "correction", "subtype", "explanation"]},
        "type": {"enum": sorted(TAXONOMY)},
        "acceptable_corrections": {"type": "array", "minItems": 1, "uniqueItems": True, "items": nonempty_string()},
    },
    "additionalProperties": False,
}
CASE_SCHEMA = {
    "type": "object",
    "required": ["id", "level", "condition", "task", "student_text", "gold", "length_words", "english_variant"],
    "properties": {
        "id": {"type": "string", "pattern": "^A[12]-[EC][0-9]{3}$"},
        "level": {"enum": ["A1", "A2"]},
        "condition": {"enum": ["correct", "incorrect"]},
        **{key: nonempty_string() for key in ["task", "student_text", "english_variant"]},
        "length_words": {"type": "integer", "minimum": 15, "maximum": 100},
        "gold": {
            "type": "object",
            "required": ["is_correct", "corrected_text", "errors", "acceptable_alternatives"],
            "properties": {
                "is_correct": {"type": "boolean"},
                "corrected_text": nonempty_string(),
                "errors": {"type": "array", "maxItems": 4, "items": ERROR_SCHEMA},
                "acceptable_alternatives": {"type": "array", "uniqueItems": True, "items": nonempty_string()},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}
BENCHMARK_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["benchmark_id", "version", "system_prompt", "user_prompt_template", "cases", "metadata"],
    "properties": {
        "benchmark_id": {"const": "writing_a1_a2_development_120_v1"},
        "version": {"const": 1},
        "system_prompt": nonempty_string(),
        "user_prompt_template": nonempty_string(),
        "cases": {"type": "array", "minItems": 120, "maxItems": 120, "items": CASE_SCHEMA},
        "metadata": {"type": "object"},
    },
    "additionalProperties": False,
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ngrams(text, n=3):
    words = normalize_text(text).split()
    return {tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def similarity(a, b):
    left, right = normalize_text(a), normalize_text(b)
    na, nb = ngrams(a), ngrams(b)
    return {
        "exact": left == right,
        "sequence_ratio": round(SequenceMatcher(None, left, right, autojunk=False).ratio(), 4),
        "trigram_jaccard": round(len(na & nb) / len(na | nb), 4) if na | nb else 0,
        "trigram_containment": round(len(na & nb) / min(len(na), len(nb)), 4) if na and nb else 0,
    }


def validate(cases, smoke):
    import jsonschema

    issues = []
    type_counts = Counter()
    errors_by_level = defaultdict(Counter)
    lengths = defaultdict(list)
    counts = Counter()
    validator = jsonschema.Draft202012Validator(CASE_SCHEMA)

    def issue(cid, message, severity="BLOCKER"):
        issues.append({"case_id": cid, "severity": severity, "issue": message})

    expected = {f"{level}-{kind}{i:03d}" for level in ["A1", "A2"] for kind, maximum in [("E", 45), ("C", 15)] for i in range(1, maximum + 1)}
    ids = [c.get("id") for c in cases]
    if len(cases) != 120 or set(ids) != expected or len(set(ids)) != len(ids):
        issue(None, "Expected exactly 120 unique quota IDs: A1/A2 45E + 15C each")

    for case in cases:
        cid = case.get("id")
        schema_errors = sorted(validator.iter_errors(case), key=lambda e: str(list(e.path)))
        for error in schema_errors:
            issue(cid, f"Schema {list(error.path)}: {error.message}")
        if schema_errors:
            continue
        text, gold, level = case["student_text"], case["gold"], case["level"]
        control = case["condition"] == "correct"
        counts[(level, case["condition"])] += 1
        words = count_words(text)
        lengths[level].append(words)
        low, high = (15, 60) if level == "A1" else (25, 100)
        if not low <= words <= high or words != case["length_words"]:
            issue(cid, f"Length mismatch/range: declared {case['length_words']}, actual {words}, allowed {low}-{high}")
        if not cid.startswith(level + ("-C" if control else "-E")) or gold["is_correct"] is not control:
            issue(cid, "ID/condition/level/gold.is_correct mismatch")
        if control:
            if gold["errors"] or gold["corrected_text"] != text or gold["acceptable_alternatives"]:
                issue(cid, "Control must have literal preserved text, no errors or correction alternatives")
            continue
        errors = gold["errors"]
        errors_by_level[level][len(errors)] += 1
        if not 1 <= len(errors) <= 4:
            issue(cid, "Incorrect case requires 1-4 distinct errors")
        edits = []
        for error in errors:
            type_counts[error["type"]] += 1
            original = error["original"]
            occurrences = [m.start() for m in re.finditer(re.escape(original), text)]
            if len(occurrences) != 1:
                issue(cid, f"Gold fragment must occur exactly once (unambiguous span): {original!r}")
                continue
            if error["correction"] not in error["acceptable_corrections"]:
                issue(cid, "Primary correction missing from acceptable_corrections")
            if original == error["correction"]:
                issue(cid, "No-op error correction")
            start = occurrences[0]
            edits.append((start, start + len(original), error["correction"]))
        ordered = sorted(edits)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            issue(cid, "Overlapping gold fragments")
        else:
            reconstructed = text
            for start, end, correction in reversed(ordered):
                reconstructed = reconstructed[:start] + correction + reconstructed[end:]
            if reconstructed != gold["corrected_text"]:
                issue(cid, "Gold errors do not reconstruct corrected_text exactly (unlisted edits or missing corrections)")
        if count_words(gold["corrected_text"]) < words * 0.75:
            issue(cid, "Potential meaning loss: correction removes over 25% of words", "REVIEW")
        for alternative in gold["acceptable_alternatives"]:
            if count_words(alternative) < words * 0.75:
                issue(cid, "Potential meaning loss in full-text alternative", "REVIEW")

    if counts != Counter({("A1", "correct"): 15, ("A1", "incorrect"): 45, ("A2", "correct"): 15, ("A2", "incorrect"): 45}):
        issue(None, "Level/condition strata do not meet 45/15 quotas")
    for level in ["A1", "A2"]:
        if errors_by_level[level] != Counter({1: 25, 2: 12, 3: 6, 4: 2}):
            issue(None, f"{level} design distribution must be 25x1,12x2,6x3,2x4")
    if set(type_counts) != TAXONOMY:
        issue(None, "Missing normalized taxonomy categories: " + ", ".join(sorted(TAXONOMY - set(type_counts))))

    pairs = []
    comparisons = [(a, b, "within_120") for a, b in itertools.combinations(cases, 2)]
    comparisons.extend((a, b, "against_40") for a in cases for b in smoke["cases"])
    top = []
    for a, b, source in comparisons:
        metrics = similarity(a["student_text"], b["student_text"])
        row = {"case_id": a["id"], "other_case_id": b["id"], "source": source, **metrics}
        top.append(row)
        if metrics["exact"]:
            issue(a["id"], f"Exact normalized reuse: {b['id']} ({source})")
        if metrics["exact"] or metrics["sequence_ratio"] >= 0.60 or metrics["trigram_jaccard"] >= 0.30 or metrics["trigram_containment"] >= 0.55:
            pairs.append(row)
    report = {
        "case_count": len(cases),
        "level_counts": dict(Counter(c["level"] for c in cases)),
        "condition_counts": dict(Counter(c["condition"] for c in cases)),
        "error_instance_count": sum(type_counts.values()),
        "error_types": dict(sorted(type_counts.items())),
        "incorrect_texts_by_error_count": dict(sorted(sum(errors_by_level.values(), Counter()).items())),
        "errors_by_level": {level: dict(counter) for level, counter in errors_by_level.items()},
        "word_counts": {level: {"mean": round(statistics.mean(vals), 2), "median": statistics.median(vals), "min": min(vals), "max": max(vals)} for level, vals in lengths.items()},
        "issues": issues,
        "blocker_count": sum(i["severity"] == "BLOCKER" for i in issues),
        "review_count": sum(i["severity"] == "REVIEW" for i in issues),
        "similarity": {"comparison_count": len(comparisons), "candidate_pairs": pairs, "top_pairs": sorted(top, key=lambda row: row["sequence_ratio"], reverse=True)[:20], "limitations": "Lexical screens cannot prove absence of semantic paraphrases; independent editorial audit and recorded resolutions required."},
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-resolutions", type=Path)
    parser.add_argument("--freeze", action="store_true", help="Write final v1 only after independent reviews/resolutions")
    args = parser.parse_args()
    reviewed = ROOT / "benchmark_120" / "reviewed"
    paths = [reviewed / f"{level}_cases.json" for level in ["A1", "A2"]]
    cases = sorted(sum([json.loads(p.read_text(encoding="utf-8")) for p in paths], []), key=lambda c: c["id"])
    smoke_path = ROOT / "benchmark_smoke_test_v2.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    report = validate(cases, smoke)
    report["source_sha256"] = {p.name: sha256(p) for p in paths}
    report["phase1_benchmark_sha256"] = sha256(smoke_path)
    report["status"] = "STRUCTURAL_CHECKS_ONLY_PENDING_EDITORIAL_REVIEW"
    data_dir = ROOT / "benchmark_120"
    (ROOT / "scripts" / "benchmark_120_schema.json").write_text(json.dumps(BENCHMARK_SCHEMA, indent=2) + "\n", encoding="utf-8")
    output = ROOT / "benchmark_development_120_v1.json"
    if args.freeze:
        resolutions = json.loads(args.review_resolutions.read_text(encoding="utf-8")) if args.review_resolutions else {}
        expected_sources = report["source_sha256"]
        confirmed = (
            resolutions.get("reviewer") and resolutions.get("source_sha256") == expected_sources
            and resolutions.get("independent_review_complete") is True
            and resolutions.get("unresolved_blockers") == []
            and resolutions.get("unresolved_reviews") == []
            and resolutions.get("similarity_pairs_reviewed") == report["similarity"]["candidate_pairs"]
        )
        if report["blocker_count"] or report["review_count"] or not confirmed:
            report["freeze_refused"] = "Structural or editorial blockers/reviews remain, or resolutions do not bind current source bytes/pairs."
        elif output.exists():
            report["freeze_refused"] = "Final v1 already exists; refusing overwrite."
        else:
            benchmark = {
                "benchmark_id": "writing_a1_a2_development_120_v1", "version": 1,
                "system_prompt": smoke["system_prompt"], "user_prompt_template": smoke["user_prompt_template"],
                "cases": cases,
                "metadata": {
                    "stage": "development_120", "execution_approved": False,
                    "dialect_policy": "Accept grammatical British and American English, including consistent spelling, vocabulary, and established regional variants. Do not normalize dialect, register or style. Control gold remains literally identical. Meaning-preserving minimal corrections and listed alternatives are acceptable; unlisted valid alternatives require traced human review, never post-output rewriting of gold.",
                    "word_count_policy": "Unicode word tokens with internal straight/curly apostrophes; hyphenated components counted separately.",
                    "phase1_exclusion_sha256": report["phase1_benchmark_sha256"],
                    "editorial_resolution_sha256": sha256(args.review_resolutions),
                    "source_sha256": expected_sources,
                    "error_count_design": {"1": 50, "2": 24, "3": 12, "4": 4},
                    "invalidation_policy": "After outputs, mark defective case invalid for all configurations; do not rewrite gold.",
                },
            }
            import jsonschema
            jsonschema.validate(benchmark, BENCHMARK_SCHEMA)
            output.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["benchmark_sha256"] = sha256(output)
            report["status"] = "VALIDATED_PENDING_USER_APPROVAL"
    (data_dir / "strict_validation_120.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ["status", "case_count", "error_instance_count", "blocker_count", "review_count", "freeze_refused", "benchmark_sha256"]}, indent=2))
    print(f"Similarity candidates: {len(report['similarity']['candidate_pairs'])}; report {data_dir / 'strict_validation_120.json'}")
    return 1 if report["blocker_count"] or report.get("freeze_refused") else 0


if __name__ == "__main__":
    raise SystemExit(main())
