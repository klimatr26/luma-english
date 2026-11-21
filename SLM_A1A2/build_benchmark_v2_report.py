import csv
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "benchmark_results_v2_rerun"
BENCHMARK = json.loads((ROOT / "benchmark_smoke_test_v2.json").read_text(encoding="utf-8"))
METADATA = json.loads((OUT / "run_metadata.json").read_text(encoding="utf-8"))
RAW = {}
for line in (OUT / "raw_outputs.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        RAW[(row["model_name"], row["case_id"])] = row

JUDGMENT_FILES = {
    "LFM2.5-350M": "judgments_lfm2_5_350m.json",
    "LFM2.5-1.2B-Instruct": "judgments_lfm2_5_1_2b_instruct.json",
    "LFM2.5-1.2B-Thinking": "judgments_lfm2-5-1-2b-thinking.json",
    "Qwen3.5-0.8B": "judgments_qwen3-5-0-8b.json",
    "Qwen3.5-2B": "judgments_qwen3.5-2b.json",
    "MiniCPM5-1B": "judgments_minicpm5-1b.json",
    "MiniCPM5-2B": "judgments_minicpm5-2b.json",
    "Gemma 4 E2B QAT Mobile": "judgments_gemma-4-e2b-qat-mobile.json",
}

case_lookup = {case["id"]: case for case in BENCHMARK["cases"]}
meta_lookup = {model["model_name"]: model for model in METADATA["models"]}


def get_rows(path):
    data = json.loads((OUT / path).read_text(encoding="utf-8"))
    return data.get("cases", data.get("judgments", []))


def parsed_content(raw):
    parsed = raw.get("parsed_json")
    if isinstance(parsed, dict):
        return parsed
    response = raw.get("raw_response", "")
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", response, re.IGNORECASE)
    if fenced:
        try:
            candidate = json.loads(fenced.group(1))
            return candidate if isinstance(candidate, dict) else None
        except Exception:
            return None
    start = response.find("{")
    end = response.rfind("}")
    if start >= 0 and end > start:
        try:
            candidate = json.loads(response[start:end + 1])
            return candidate if isinstance(candidate, dict) else None
        except Exception:
            return None
    return None


def median(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(values) if values else None


case_export = []
model_summaries = []
review_cases = []

for model_name, filename in JUDGMENT_FILES.items():
    judgments = get_rows(filename)
    if len(judgments) != 40:
        raise ValueError(f"Expected 40 judgments for {model_name}, got {len(judgments)}")
    by_id = {row["case_id"]: row for row in judgments}
    if len(by_id) != 40:
        raise ValueError(f"Duplicate or missing judgment IDs for {model_name}")

    rows = []
    for case in BENCHMARK["cases"]:
        jid = case["id"]
        judgment = by_id[jid]
        raw = RAW[(model_name, jid)]
        parsed = parsed_content(raw)
        final_text = parsed.get("corrected_text") if isinstance(parsed, dict) else None
        modified = final_text is not None and final_text != case["student_text"]
        execution_completed = not raw.get("truncated", False) and not raw.get("error")
        real_errors_value = judgment.get("real_errors", len(case["gold"]["errors"]))
        real_errors_count = len(real_errors_value) if isinstance(real_errors_value, list) else int(real_errors_value)
        detected_value = judgment.get("detected_errors", 0)
        detected_count = len(detected_value) if isinstance(detected_value, list) else int(detected_value)
        missed_value = judgment.get("missed_errors", 0)
        missed_count = len(missed_value) if isinstance(missed_value, list) else int(missed_value)
        false_positive_value = judgment.get("false_positive_errors", 0)
        false_positive_count = len(false_positive_value) if isinstance(false_positive_value, list) else int(false_positive_value)
        record = {
            "model_name": model_name,
            "case_id": jid,
            "level": case["level"],
            "condition": case["condition"],
            "result": judgment.get("label", "INCORRECT"),
            "real_errors": real_errors_count,
            "detected_errors": detected_count,
            "missed_errors": missed_count,
            "false_positive_errors": false_positive_count,
            "corrections_valid": judgment.get("corrections_valid", False),
            "explanation_valid": judgment.get("explanation_valid", False),
            "meaning_preserved": judgment.get("meaning_preserved", False),
            "control_text_modified": modified if case["condition"] == "correct" else None,
            "json_valid": bool(raw.get("json_valid", False)),
            "completed": execution_completed,
            "truncated": bool(raw.get("truncated", False)),
            "repetition_or_loop": bool(raw.get("repetition_or_loop", False)),
            "text_outside_json": bool(raw.get("text_outside_json", False)),
            "latency_seconds": raw.get("latency_seconds"),
            "tokens_generated": raw.get("tokens_generated"),
            "tokens_per_second": raw.get("tokens_per_second"),
            "peak_RAM_bytes": raw.get("peak_RAM_bytes"),
            "peak_VRAM_bytes": raw.get("peak_VRAM_bytes"),
            "needs_human_review": bool(judgment.get("needs_human_review", False)),
            "review_note": judgment.get("review_note", ""),
            "observation": judgment.get("review_note", "") if judgment.get("needs_human_review") else "",
        }
        rows.append(record)
        case_export.append(record)
        if record["needs_human_review"]:
            review_cases.append({
                "model_name": model_name,
                "case_id": jid,
                "review_note": record["review_note"],
                "raw_response_preserved_in": "raw_outputs.jsonl",
            })

    erroneous = [row for row in rows if row["condition"] == "incorrect"]
    controls = [row for row in rows if row["condition"] == "correct"]
    labels = {label: sum(row["result"] == label for row in rows) for label in ("CORRECT", "PARTIAL", "INCORRECT")}
    a1_correct = sum(row["result"] == "CORRECT" for row in rows if row["level"] == "A1")
    a2_correct = sum(row["result"] == "CORRECT" for row in rows if row["level"] == "A2")
    erroneous_resolved = sum(row["result"] == "CORRECT" for row in erroneous)
    control_fault = lambda row: row["false_positive_errors"] > 0 or row["control_text_modified"] is True or row["result"] != "CORRECT"
    preserved = sum(not control_fault(row) for row in controls)
    modified_controls = sum(row["control_text_modified"] is True for row in controls)
    false_correction_cases = sum(row["false_positive_errors"] > 0 for row in controls)
    latencies = [row["latency_seconds"] for row in rows if row["latency_seconds"] is not None]
    tokens = [row["tokens_generated"] for row in rows if row["tokens_generated"] is not None]
    tps = [row["tokens_per_second"] for row in rows if row["tokens_per_second"] is not None]
    runtime_meta = meta_lookup[model_name]
    invalid_correction_cases = sum(not row["corrections_valid"] for row in rows if row["condition"] == "incorrect") + sum(row["false_positive_errors"] > 0 for row in controls)
    invalid_explanation_cases = sum(not row["explanation_valid"] for row in rows if row["condition"] == "incorrect") + sum(row["false_positive_errors"] > 0 for row in controls)
    summary = {
        "model_name": model_name,
        "cases_evaluated": len(rows),
        "fully_correct": labels["CORRECT"],
        "fully_correct_percent": labels["CORRECT"] / len(rows) * 100,
        "partial": labels["PARTIAL"],
        "incorrect": labels["INCORRECT"],
        "A1_fully_correct": a1_correct,
        "A2_fully_correct": a2_correct,
        "erroneous_texts_fully_resolved": erroneous_resolved,
        "correct_controls_preserved": preserved,
        "correct_controls_modified_unnecessarily": modified_controls,
        "controls_with_false_positive_errors": false_correction_cases,
        "false_correction_rate": modified_controls / len(controls) if controls else None,
        "total_gold_errors": sum(row["real_errors"] for row in rows),
        "correctly_detected_errors": sum(row["detected_errors"] for row in rows),
        "missed_errors": sum(row["missed_errors"] for row in rows),
        "false_positive_errors": sum(row["false_positive_errors"] for row in rows),
        "cases_with_invalid_corrections": invalid_correction_cases,
        "cases_with_meaning_loss": sum(not row["meaning_preserved"] for row in rows),
        "cases_with_incorrect_explanations": invalid_explanation_cases,
        "valid_json": sum(row["json_valid"] for row in rows),
        "responses_truncated": sum(row["truncated"] for row in rows),
        "responses_with_repetition_or_loop": sum(row["repetition_or_loop"] for row in rows),
        "responses_with_text_outside_json": sum(row["text_outside_json"] for row in rows),
        "execution_completed_operational": sum(row["completed"] for row in rows),
        "execution_completed_flag_from_runner": sum(bool(RAW[(model_name, row["case_id"])].get("completed", False)) for row in rows),
        "needs_human_review_cases": sum(row["needs_human_review"] for row in rows),
        "latency_seconds_mean": statistics.mean(latencies) if latencies else None,
        "latency_seconds_median": median(latencies),
        "tokens_generated_mean": statistics.mean(tokens) if tokens else None,
        "tokens_generated_median": median(tokens),
        "tokens_per_second_mean": statistics.mean(tps) if tps else None,
        "peak_RAM_bytes": max((row["peak_RAM_bytes"] or 0) for row in rows) or None,
        "peak_VRAM_bytes": max((row["peak_VRAM_bytes"] or 0) for row in rows) or None,
        "exact_checkpoint_id": runtime_meta["exact_model_checkpoint_id"],
        "revision_hash": runtime_meta["local_snapshot"]["revision"],
        "resolved_dtype": runtime_meta.get("resolved_parameter_dtype"),
        "quantized": bool(runtime_meta.get("quantization")),
        "runtime": METADATA["runtime"],
        "max_new_tokens": METADATA["generation"]["max_new_tokens"],
    }
    model_summaries.append(summary)

model_summaries.sort(key=lambda x: (
    -x["fully_correct"],
    x["false_positive_errors"],
    x["false_correction_rate"],
    x["cases_with_meaning_loss"],
    x["cases_with_incorrect_explanations"],
    -x["valid_json"],
))

comparison_fields = [
    "model_name", "fully_correct", "fully_correct_percent", "partial", "incorrect",
    "A1_fully_correct", "A2_fully_correct", "erroneous_texts_fully_resolved",
    "correct_controls_preserved", "correct_controls_modified_unnecessarily", "controls_with_false_positive_errors", "false_correction_rate", "correctly_detected_errors",
    "false_positive_errors", "cases_with_meaning_loss", "cases_with_incorrect_explanations", "valid_json",
]

(OUT / "model_summaries_v2.json").write_text(json.dumps(model_summaries, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "needs_human_review_v2.json").write_text(json.dumps(review_cases, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "comparison_v2.json").write_text(json.dumps([{field: row[field] for field in comparison_fields} for row in model_summaries], ensure_ascii=False, indent=2), encoding="utf-8")
with (OUT / "case_results_v2.csv").open("w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(case_export[0]))
    writer.writeheader()
    writer.writerows(case_export)
with (OUT / "comparison_v2.csv").open("w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.DictWriter(handle, fieldnames=comparison_fields)
    writer.writeheader()
    writer.writerows([{field: row[field] for field in comparison_fields} for row in model_summaries])

# Compact markdown report for directly viewing the principal comparison.
headers = ["Modelo", "Correctos /40", "%", "Parciales", "Incorrectos", "A1", "A2", "Resueltos /30", "Controles preservados /10", "Controles modificados", "Controles con FP", "FCR", "Errores detectados", "Falsos positivos", "Pérdida significado", "Explicaciones incorrectas", "JSON válido"]
lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
for row in model_summaries:
    values = [row["model_name"], f'{row["fully_correct"]}/40', f'{row["fully_correct_percent"]:.1f}%', str(row["partial"]), str(row["incorrect"]), f'{row["A1_fully_correct"]}/20', f'{row["A2_fully_correct"]}/20', f'{row["erroneous_texts_fully_resolved"]}/30', f'{row["correct_controls_preserved"]}/10', str(row["correct_controls_modified_unnecessarily"]), str(row["controls_with_false_positive_errors"]), f'{row["false_correction_rate"]:.0%}', str(row["correctly_detected_errors"]), str(row["false_positive_errors"]), str(row["cases_with_meaning_loss"]), str(row["cases_with_incorrect_explanations"]), f'{row["valid_json"]}/40']
    lines.append("| " + " | ".join(values) + " |")
(OUT / "comparison_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({"models": len(model_summaries), "cases": len(case_export), "review_items": len(review_cases), "comparison": str(OUT / 'comparison_v2.md')}, ensure_ascii=False))
