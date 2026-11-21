"""Compare the LFM3 Phase 1 extension with matched historical Q8 and Q4 runs."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys

import evaluate_benchmark_120 as frozen
import evaluate_responses_v2 as v2
import gec_alignment_v2 as gec
import report_execution_results as reporting

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import run_benchmark_40_lfm3 as lfm3  # noqa: E402
import run_benchmark_120 as shared  # noqa: E402

HISTORICAL = "results_40_current_16"
COMPARATORS = (
    "05-minicpm5-2b-q8-0", "06-minicpm5-2b-q4-k-m",
    "08-lfm25-12b-q8-0", "09-lfm25-12b-q4-k-m",
    "15-lfm25-26b-q8-0", "16-lfm25-26b-q4-k-m",
)


def load_verified_rows(result_dir, config, benchmark_sha, manifest_sha, manifest, source_pins):
    cid = config["config_id"]
    raw_path = shared.raw_path_for(result_dir, cid)
    parsed_path = shared.parsed_path_for(result_dir, cid)
    evidence = {}
    for path in (raw_path, parsed_path):
        digest = shared.sha256_file(path)
        relative_path = path.relative_to(LAB.parent).as_posix()
        if source_pins and source_pins.get(relative_path) != digest:
            raise ValueError(f"Historical source differs from evaluation v2 snapshot: {relative_path}")
        evidence[relative_path] = digest
    raw = reporting.load_jsonl(raw_path)
    selected, _ = frozen.select_authorized_latest_rows(
        reporting.load_jsonl(parsed_path), benchmark_sha, attempt_rows=raw,
        config_filter=cid, manifest_sha=manifest_sha, manifest_data=manifest)
    return selected, raw, evidence


def assess(config, selected, raw, data, benchmark_sha, manifest_sha):
    cases = {case["id"]: case for case in data["cases"]}
    if len(selected) != len(cases) or {row["case_id"] for row in selected} != cases.keys():
        raise ValueError(f"Incomplete or duplicate case matrix: {config['config_id']}")
    attempts = {(row["resume_key"], row["attempt"]): row for row in raw}
    analyses, timings, parser_input = [], [], []
    for row in selected:
        case = cases[row["case_id"]]
        _, prompt_sha = shared.build_messages(data["system_prompt"], data["user_prompt_template"], case)
        if row["prompt_sha256"] != prompt_sha:
            raise ValueError(f"Response does not bind the frozen prompt: {row['resume_key']}")
        group = [attempts[(row["resume_key"], number)] for number in row["attempt_trace"]]
        transport = reporting._assert_parsed_telemetry_matches_raw(row, group[-1], group)
        if transport["outcome"] != "ok":
            raise ValueError(f"Missing successful transport: {row['resume_key']}")
        body = json.loads(group[-1]["response_body_exact"])
        message = body["choices"][0]["message"]
        timing = body.get("timings", {})
        timings.append({
            "case_id": case["id"], "finish": transport["finish_reason"],
            "latency": transport["latency_seconds_total"],
            "completion_tokens": transport["usage"]["completion_tokens"],
            "prompt_tokens": transport["usage"]["prompt_tokens"],
            "decode_tokens_per_second": timing.get("predicted_per_second"),
            "prefill_tokens_per_second": timing.get("prompt_per_second"),
            "cache_n": timing.get("cache_n"),
            "reasoning_nonempty": bool((message.get("reasoning_content") or "").strip()),
            "vram_device_bytes": row.get("memory", {}).get("gpu_used_bytes"),
            "server_rss_peak_bytes": row.get("memory", {}).get("server_peak_rss_bytes"),
        })
        analyses.append(v2.evaluate_text(
            case, row, scope=lfm3.SCOPE, benchmark_sha=benchmark_sha,
            manifest_sha=manifest_sha, scorer=gec.score_text))
        parser_input.append({
            "config_id": config["config_id"], "case_id": case["id"],
            "raw_response": row["raw_response"], "student_text": case["student_text"],
        })
    median_keys = ("latency", "completion_tokens", "prompt_tokens",
                   "decode_tokens_per_second", "prefill_tokens_per_second", "cache_n")
    return {
        "config_id": config["config_id"],
        "quant": config["quant"],
        "model_bytes": config["gguf"]["bytes"],
        "manifest_sha256": manifest_sha,
        "evaluation": v2.aggregate(analyses),
        "finish_reason": dict(Counter(row["finish"] for row in timings)),
        "reasoning_nonempty": sum(row["reasoning_nonempty"] for row in timings),
        "medians": {
            key: median(row[key] for row in timings if row[key] is not None)
            if any(row[key] is not None for row in timings) else None for key in median_keys
        },
        "sample_counts": {key: sum(row[key] is not None for row in timings) for key in median_keys},
        "max_sampled_device_vram_bytes": max(
            (row["vram_device_bytes"] for row in timings if row["vram_device_bytes"] is not None), default=None),
        "max_sampled_server_rss_bytes": max(
            (row["server_rss_peak_bytes"] for row in timings if row["server_rss_peak_bytes"] is not None), default=None),
    }, analyses, timings, parser_input


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def main():
    data, benchmark_sha = shared.load_json_snapshot(lfm3.phase1.PHASE1_BENCHMARK)
    if benchmark_sha != lfm3.phase1.PHASE1_BENCHMARK_SHA256:
        raise ValueError("The Phase 1 benchmark has changed.")
    shared.validate_benchmark(data, expected_cases=40)
    new_manifest, new_sha = shared.load_json_snapshot(lfm3.MANIFEST)
    lfm3.load_configs(new_manifest)
    run = shared.load_json(lfm3.OUT / "reports" / "run_summary.json")
    if (run["manifest_sha256"], run["benchmark_sha256"], run["transport_ok"]) != (new_sha, benchmark_sha, 80):
        raise ValueError("The new extension did not complete its bound 80 responses.")
    old_manifest, old_sha = shared.load_json_snapshot(reporting.MANIFEST)
    old_results = LAB / "analysis_v2" / HISTORICAL
    old_comparison = shared.load_json(old_results / "scope_summary.json")
    if (old_comparison["benchmark_sha256"], old_comparison["manifest_sha256"]) != (benchmark_sha, old_sha):
        raise ValueError("Historical results do not bind the same benchmark and frozen manifest.")
    pins = {row["path"]: row["sha256"] for row in
            shared.load_json(old_results / "completion_record.json")["source_inputs"]}
    old_metrics = {row["config_id"]: row["summary"] for row in old_comparison["configurations"]}
    groups = (
        (lfm3.OUT, lfm3.CONFIG_IDS, new_manifest, new_sha, {}),
        (LAB / HISTORICAL, COMPARATORS, old_manifest, old_sha, pins),
    )
    work = lfm3.OUT / "logs" / "evaluation"
    work.mkdir(parents=True, exist_ok=True)
    scores, parser_inputs, sources = [], [], {}
    for result_dir, ids, manifest, manifest_sha, source_pins in groups:
        entries = {config["config_id"]: config for config in manifest["configurations"]}
        for cid in ids:
            config = entries[cid]
            selected, raw, evidence = load_verified_rows(
                result_dir, config, benchmark_sha, manifest_sha, manifest, source_pins)
            summary, analyses, timings, parser_input = assess(
                config, selected, raw, data, benchmark_sha, manifest_sha)
            if source_pins and summary["evaluation"] != old_metrics[cid]:
                raise ValueError(f"Could not reproduce the historical ERRANT summary for {cid}")
            summary["runtime"] = "b11457 CUDA 13.4" if source_pins else "b12359 CUDA 12.4"
            scores.append(summary)
            parser_inputs.extend(parser_input)
            sources.update(evidence)
            write_jsonl(work / f"{cid}.evaluation.jsonl", analyses)
            write_jsonl(work / f"{cid}.timings.jsonl", timings)
            print(f"{cid}: {len(analyses)} cases", flush=True)
    v2.assert_sources_unchanged(
        [{"path": path, "sha256": sha} for path, sha in sources.items()])
    write_jsonl(work / "app-parser-input.jsonl", parser_inputs)
    v2.write_json(lfm3.OUT / "reports" / "comparison.json", {
        "scope": lfm3.SCOPE, "benchmark_sha256": benchmark_sha,
        "new_manifest_sha256": new_sha, "historical_manifest_sha256": old_sha,
        "scorer": gec.get_engine().metadata(), "sources": sources, "configurations": scores,
    })


if __name__ == "__main__":
    main()
