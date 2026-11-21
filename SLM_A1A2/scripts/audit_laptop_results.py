"""Audit imported laptop evidence without loading a model or importing runners."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import statistics


LAB = Path(__file__).resolve().parents[1]
RUNNERS = {
    "results_laptop_resources_v1": "run_laptop_resources.py",
    "results_laptop_resources_v1/qwen_vulkan_retry": "run_laptop_resources.py",
    "results_laptop_hybrid_gpu_v1": "run_laptop_hybrid_gpu.py",
    "results_laptop_battery_v1": "run_laptop_battery.py",
    "results_laptop_vram2g_v1": "run_laptop_vram2g.py",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def decode(text):
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


def read(path):
    return decode(path.read_text(encoding="utf-8-sig"))


def rows(path):
    return [decode(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()] if path.exists() else []


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def bound(path, expected):
    require(path.is_file() and sha(path) == expected, f"Missing or changed binding: {path}")


def equal(actual, expected, context):
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        require(actual not in (None, "") and math.isclose(float(actual), expected,
                rel_tol=1e-10, abs_tol=1e-9), f"Metric mismatch: {context}")
    else:
        require(actual == expected, f"Value mismatch: {context}")


def timestamp(value):
    return datetime.fromisoformat(value)


def audit():
    imported = read(LAB / "manifests/laptop_integration_import_20261118.json")
    for item in imported["imported_files"]:
        path = LAB.parent / item["path"]
        bound(path, item["sha256"])
        require(path.stat().st_size == item["bytes"], f"Changed length: {path}")

    frozen_path = LAB / "manifests/finalists_200_20261117.json"
    frozen = read(frozen_path)
    frozen_profiles = {c["model_id"]: c for c in frozen["configurations"]}
    for item in frozen["source_bindings"]:
        # Original absolute paths remain unchanged; resolve their project suffix.
        parts = PureWindowsPath(item["path"]).parts
        bound(LAB.joinpath(*parts[parts.index("SLM_A1A2") + 1:]), item["sha256"])
    benchmark = LAB / PureWindowsPath(frozen["benchmark"]).name
    bound(benchmark, frozen["benchmark_sha256"])

    development = read(LAB / "benchmark_development_120_v1.json")["cases"]
    selection = []
    for (level, condition), quota in {("A1", "incorrect"): 5, ("A1", "correct"): 2,
                                     ("A2", "incorrect"): 6, ("A2", "correct"): 2}.items():
        group = sorted((c for c in development if (c["level"], c["condition"]) == (level, condition)),
                       key=lambda c: (c["length_words"], c["id"]))
        selection.extend(group[(2 * j + 1) * len(group) // (2 * quota)] for j in range(quota))
    selection.sort(key=lambda c: digest("20261118:" + c["id"]))
    subset = [{k: c[k] for k in ("id", "level", "task", "student_text")} for c in selection]
    cases = {c["id"]: c for c in subset}
    expected_ids = list(cases)
    blocks, gaps, battery_energy = [], [], []
    successful = 0

    for directory, runner in RUNNERS.items():
        out = LAB / directory
        manifest_path = out / "manifest.json"
        manifest, completed = read(manifest_path), read(out / "completion.json")
        bound(out / "cases.json", manifest["subset_sha256"])
        bound(frozen_path, manifest["frozen_manifest_sha256"])
        bound(LAB / manifest["source"], manifest["source_sha256"])
        require(read(out / "cases.json") == subset, f"Different subset: {directory}")
        require([c["id"] for c in manifest["selection"]] == expected_ids, "Different case order")
        require(completed["manifest_sha256"] == sha(manifest_path), "Completion binding mismatch")
        for key in ("context", "seed", "thinking", "guided_json", "retries", "llama_cpp_commit"):
            equal(manifest[key], frozen[key], f"{directory}/{key}")
        runner_path = LAB / runner
        if sha(runner_path) != manifest["runner_sha256"]:
            runner_path = out / "runner_used.py"
        bound(runner_path, manifest["runner_sha256"])
        protocol = (LAB / "documentation/laptop_resources_protocol_v1.md"
                    if directory.startswith("results_laptop_resources_v1") else out / "protocol.md")
        bound(protocol, manifest["protocol_sha256"])
        for key in ("worker_sha256", "worker_source_sha256"):
            if key in manifest:
                bound(LAB / "run_laptop_resources.py", manifest[key])
        for item in manifest.get("source_bindings", []):
            bound(LAB / item["path"], item["sha256"])
        if "bridge_build_sha256" in manifest:
            bound(out / "bridge_build.json", manifest["bridge_build_sha256"])
            build = read(out / "bridge_build.json")
            source = LAB / "cross_demo/native/src/writing_llama_bridge.cpp"
            bound(source, build["original_bridge_source_sha256"])
            original = source.read_bytes().decode("utf-8")
            marker = "    model_params.n_gpu_layers = use_gpu ? -1 : 0;"
            require(original.count(marker) == 1, "Ambiguous experimental bridge selector")
            variant = original.replace(marker, build["selector_replacement"])
            equal(digest(variant), build["experimental_bridge_source_sha256"], "Experimental bridge recipe")
        runtimes = manifest.get("runtimes", {"single": {
            "directory": manifest.get("native_directory"), "dll_sha256": manifest.get("dll_sha256", {})}})
        for runtime in runtimes.values():
            for name, expected in runtime["dll_sha256"].items():
                bound(LAB / runtime["directory"] / name, expected)

        configurations = {c["id"]: c for c in manifest["configurations"]}
        for cfg in configurations.values():
            reference = frozen_profiles[cfg["model_id"]]
            for key in ("model_sha256", "model_bytes", "system_prompt_sha256", "system_prompt", "sampling"):
                equal(cfg[key], reference[key], f"{directory}/{cfg['id']}/{key}")
            equal(digest(cfg["system_prompt"]), cfg["system_prompt_sha256"], "Prompt content")

        summary_rows = csv_rows(out / "summary.csv")
        csv_summary = {b["config_id"]: b for b in summary_rows}
        require(len(csv_summary) == len(summary_rows), "Duplicate summary CSV configuration")
        individual_rows = csv_rows(out / "cases.csv") if (out / "cases.csv").exists() else []
        individual = {(r["config_id"], r["case_id"]): r for r in individual_rows}
        require(len(individual) == len(individual_rows), "Duplicate individual CSV case")
        seen_individual = set()
        for summary in completed["blocks"]:
            cid = summary["config_id"]
            require(cid in configurations, f"Unknown configuration: {cid}")
            raw, attempts, telemetry = [rows(out / kind / f"{cid}.jsonl")
                                       for kind in ("raw", "attempts", "telemetry")]
            ids = [r["case_id"] for r in raw]
            require(ids == expected_ids[:len(ids)] and len(set(ids)) == len(ids), f"RAW order: {cid}")
            require([r["case_id"] for r in attempts] == ids, f"Attempt coverage: {cid}")
            require([r["case_id"] for r in telemetry] == ids, f"Telemetry coverage: {cid}")
            equal(len(raw), summary["successful"], f"{cid}/coverage")
            ready = read(out / "readiness" / f"{cid}.json")
            memories = [ready.get(key, {}) for key in ("load_memory", "warmup_memory")]
            for r, a, t in zip(raw, attempts, telemetry):
                require(all(r[k] == v for k, v in a.items()), f"Attempt identity: {cid}")
                require(all(t[k] == v for k, v in a.items()), f"Telemetry identity: {cid}")
                equal(r["manifest_sha256"], sha(manifest_path), "RAW manifest")
                equal(r["model_sha256"], configurations[cid]["model_sha256"], "RAW model")
                case = cases[r["case_id"]]
                prompt = f"Level: {case['level']}\nTask: {case['task']}\nStudent text: {case['student_text']}"
                equal(r["user_prompt_sha256"], digest(prompt), "User prompt")
                equal(t["response_sha256"], digest(r["raw_response"]), "Response hash")
                require(r["status"] == 0 and r["finish_reason"] == "stop" and r["attempt"] == 1,
                        f"Unsuccessful or repeated generation: {cid}")
                key = (cid, r["case_id"])
                require(key in individual and key not in seen_individual, "Individual CSV coverage")
                seen_individual.add(key)
                for metric in ("native_seconds", "prompt_seconds", "decode_seconds", "prompt_tokens", "output_tokens"):
                    equal(individual[key][metric], r[metric], f"Individual CSV/{metric}")
                memories.append(t["memory"])
            for field in ("native_seconds", "prompt_seconds", "decode_seconds", "output_tokens", "prompt_tokens",
                          "decode_tokens_per_second", "output_tokens_per_second"):
                values = [(r["decoded_tokens"] / r["decode_seconds"] if field == "decode_tokens_per_second" else
                           r["output_tokens"] / r["native_seconds"] if field == "output_tokens_per_second" else
                           r[field]) for r in raw]
                for name, stat in (("median", statistics.median), ("mean", statistics.fmean), ("min", min), ("max", max)):
                    expected = stat(values) if values else None
                    equal(summary[f"{field}_{name}"], expected, f"{cid}/{field}/{name}")
                    equal(csv_summary[cid][f"{field}_{name}"], expected if expected is not None else "",
                          f"Summary CSV/{cid}/{field}/{name}")
            for field, stat in (("worker_rss_peak_bytes", max), ("worker_private_peak_bytes", max),
                                ("system_available_min_bytes", min), ("device_vram_peak_mib", max)):
                values = [m[field] for m in memories if m.get(field) is not None]
                equal(summary[field], stat(values) if values else None, f"{cid}/{field}")
            blocks.append({"scope": directory, "config_id": cid, "successful": len(raw),
                           "native_seconds_median": summary["native_seconds_median"],
                           "rss_peak_gib": summary["worker_rss_peak_bytes"] / 2**30
                           if summary["worker_rss_peak_bytes"] is not None else None,
                           "vram_peak_mib": summary["device_vram_peak_mib"]})
            successful += len(raw)
        require(seen_individual == set(individual), "Extra individual CSV records")

    consolidated = csv_rows(LAB / "results_laptop_integration_v1/comparison.csv")
    expected_consolidated = {(directory, r["config_id"]): r for directory in RUNNERS
                             for r in csv_rows(LAB / directory / "summary.csv")}
    require(len(consolidated) == len(expected_consolidated), "Consolidated CSV coverage")
    seen = set()
    for row in consolidated:
        key = row["source_scope"], row["config_id"]
        require(key in expected_consolidated and key not in seen, "Consolidated CSV identity")
        seen.add(key)
        require(all(row.get(k) == v for k, v in expected_consolidated[key].items()),
                "Consolidated CSV differs from original summary")

    diagnostic = LAB / "results_laptop_qwen_vulkan_diagnostic_v1"
    for folder in sorted(p for p in diagnostic.iterdir() if p.is_dir()):
        a, r = read(folder / "attempt.json"), read(folder / "result.json")
        require(all(r[k] == v for k, v in a.items()), f"Diagnostic identity: {folder.name}")
        source = diagnostic / ("probe.cpp" if folder.name == "full-mmap-block1-cpu" else "probe_initial.cpp")
        bound(source, a["probe_source_sha256"])
        for name, expected in a["dll_sha256"].items():
            bound(LAB / "cross_demo/native/artifacts/b12359/win-x64" / name, expected)
    gaps.extend([
        "Diagnostic executable hashes are recorded, but those executables were absent from the supplied copy.",
        "The original failed Qwen full-load attempt lacks peak telemetry; its technical retry is preserved.",
        "No Windows residency/page-fault trace proves that the Intel timings were caused by memory spillover.",
        "These are resource measurements on 15 reused development cases, not new accuracy measurements.",
    ])

    battery = LAB / "results_laptop_battery_v1"
    bounds = read(battery / "power_bounds.json")
    samples = rows(battery / "battery_wmi.jsonl")
    inside = [s for s in samples if timestamp(bounds["start"]["utc"]) <= timestamp(s["utc"])
              <= timestamp(bounds["end"]["utc"])]
    require(inside and all(s["ac_power"] is False for s in inside), "Battery power observations")
    for path in sorted((battery / "readiness").glob("*.json")):
        ready = read(path)
        window = [s for s in inside if timestamp(ready["started_utc"]) <= timestamp(s["utc"])
                  <= timestamp(ready["power_after"]["utc"])]
        battery_energy.append({"config_id": path.stem, "wmi_samples": len(window),
                               "observed_wh": (window[0]["remaining_mwh"] - window[-1]["remaining_mwh"]) / 1000})
    paired = []
    def times(directory, cid):
        return {r["case_id"]: r["native_seconds"] for r in rows(LAB / directory / "raw" / f"{cid}.jsonl")}
    for family, cpu_id, gpu_dir, gpu_id in (
        ("gemma", "13-gemma4-e2b-ud-q4-k-xl--cpu", "results_laptop_resources_v1", "13-gemma4-e2b-ud-q4-k-xl--vulkan"),
        ("qwen", "portable-unsloth-qwen35-4b-q4-k-m--cpu", "results_laptop_hybrid_gpu_v1", "qwen--quadro-p1000--32"),
        ("gemma_partial", "13-gemma4-e2b-ud-q4-k-xl--cpu", "results_laptop_vram2g_v1", "gemma--quadro--18"),
        ("qwen_partial", "portable-unsloth-qwen35-4b-q4-k-m--cpu", "results_laptop_vram2g_v1", "qwen--quadro--14"),
    ):
        cpu, gpu = times("results_laptop_resources_v1", cpu_id), times(gpu_dir, gpu_id)
        paired.append({"comparison": family, "cpu_over_gpu_median": statistics.median(cpu[k] / gpu[k] for k in expected_ids),
                       "gpu_faster_cases": sum(gpu[k] < cpu[k] for k in expected_ids), "cases": len(expected_ids)})
    return {"audit_version": 1, "audit_script_sha256": sha(Path(__file__)),
            "audited_utc": datetime.now(timezone.utc).isoformat(),
            "status": "passed_with_documented_limits", "new_inferences": 0,
            "imported_files_verified": len(imported["imported_files"]),
            "frozen_source_bindings_verified": len(frozen["source_bindings"]),
            "subsets_reconstructed": len(RUNNERS), "unique_development_cases": len(subset),
            "successful_resource_responses": successful, "blocks": blocks, "paired_speedups": paired,
            "battery_inside_run_wh": (inside[0]["remaining_mwh"] - inside[-1]["remaining_mwh"]) / 1000,
            "battery_block_energy_whole_system": battery_energy, "limits": gaps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Create a new audit JSON; never overwrite evidence.")
    args = parser.parse_args()
    result = audit()
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as file:
            file.write(rendered)
        print(f"Audit passed: {result['successful_resource_responses']} resource responses; {args.output}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
