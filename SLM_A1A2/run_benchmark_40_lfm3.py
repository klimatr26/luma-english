"""Run the 40-case LFM3-1.7B extension with the Phase 1 transport."""

from __future__ import annotations

import argparse
import json
import msvcrt
import sys
from pathlib import Path
from types import SimpleNamespace

import run_benchmark_40_current as phase1
import run_benchmark_120 as shared
import check_readiness_120 as readiness

LAB = Path(__file__).resolve().parent
MANIFEST = LAB / "manifests" / "lfm3_40_20261117.json"
OUT = LAB / "results_40_lfm3_17b"
SCOPE = "phase1_40_lfm3_17b"
CONFIG_IDS = ("17-lfm3-17b-q8-0", "18-lfm3-17b-q4-k-m")


def load_configs(manifest):
    if (manifest["scope"] != SCOPE
            or manifest["benchmark"] != phase1.PHASE1_BENCHMARK.name
            or manifest["benchmark_sha256"] != phase1.PHASE1_BENCHMARK_SHA256
            or manifest["case_count"] != 40
            or manifest["authorization"]["planned_rows"] != 80
            or manifest["authorization"]["development_120_authorized"] is not False
            or tuple(row["config_id"] for row in manifest["configurations"]) != CONFIG_IDS):
        raise shared.GateError("Expected the exact two-configuration Phase 1 scope.")
    runtime = manifest["runtime"]
    return [
        {
            **row, "runtime": runtime, "generation": manifest["generation"],
            "server_command": [
                runtime["server"], "-m", row["model_path"], "--port", str(row["port"]),
                *runtime["arguments"],
            ],
        }
        for row in manifest["configurations"]
    ]


def verify_runtime(runtime):
    server = LAB / runtime["server"]
    for path, digest in (
        (server, runtime["server_sha256"]),
        (server.with_name("llama-server-impl.dll"), runtime["server_impl_sha256"]),
        (server.with_name("ggml-cuda.dll"), runtime["cuda_plugin_sha256"]),
    ):
        if shared.sha256_file(path) != digest:
            raise shared.GateError(f"Runtime differs from the manifest: {path}")


def synthetic_readiness(entries, configs, manifest, manifest_sha):
    report_path = OUT / "reports" / "readiness.json"
    logs = OUT / "logs" / "readiness"
    if report_path.is_file():
        report = shared.load_json(report_path)
    else:
        logs.mkdir(parents=True, exist_ok=True)
        args = SimpleNamespace(load_timeout=120, request_timeout=90)
        report = {"manifest_sha256": manifest_sha, "scope": SCOPE, "configs": []}
        render_sha = None
        for row in entries:
            result = readiness.run_config_check(row, args, logs, expected_render_sha256=render_sha)
            measured = result["measured"]
            if result["status"] == "ready":
                render = shared.load_json(logs / f'{row["id"]}.render.json')["prompt"]
                suffix = manifest["source"]["template_assistant_suffix_with_thinking_off"]
                if not render.rstrip().endswith(suffix):
                    result["status"] = "not_ready_thinking"
                placed, total = measured["offload"]["n_gpu_layers_reported"].split("/")
                if placed != total:
                    result["status"] = "not_ready_partial_offload"
                render_sha = measured["rendered_prompt_sha256"]
            report["configs"].append(result)
            print(json.dumps({"readiness": row["config_id"], "status": result["status"],
                              "offload": measured.get("offload", {}).get("n_gpu_layers_reported")}),
                  flush=True)
            if result["status"] != "ready":
                break
        phase1._write_json_atomic(report_path, report)
    shared.check_readiness(configs, report, manifest_sha)
    return {row["config_id"]: row for row in report["configs"]}


def run_locked(args, data, benchmark_sha, manifest, manifest_sha, cases, entries, configs):
    verify_runtime(manifest["runtime"])
    report = synthetic_readiness(entries, configs, manifest, manifest_sha)
    for config in configs:
        measured = report[config["config_id"]]["measured"]
        config["offload"] = measured["offload"]["n_gpu_layers_reported"]
        config["argv"][0] = str(LAB / config["argv"][0])
    if args.readiness_only:
        return shared.EXIT_OK

    checkpoint = OUT / "checkpoint.json"
    raw_paths = [shared.raw_path_for(OUT, cid) for cid in CONFIG_IDS]
    states = shared.replay_raw_authority(
        raw_paths, benchmark_sha, manifest_sha, dict(zip(CONFIG_IDS, configs, strict=True)),
        {case["id"] for case in cases},
    )
    shared.write_checkpoint_atomic(checkpoint, benchmark_sha, manifest_sha, states)
    runtime_args = SimpleNamespace(api_path="/v1/chat/completions", health_path="/health",
                                   health_timeout=120, health_interval=1, max_retries=1)
    client = shared.HttpClient(90)
    started = shared.utcnow()
    stats = []
    for config in configs:
        print(json.dumps({"started_config": config["config_id"], "case_count": len(cases)}), flush=True)
        result = shared.run_config(
            config=config, cases=cases, system_prompt=data["system_prompt"],
            user_template=data["user_prompt_template"], benchmark_sha=benchmark_sha,
            manifest_sha=manifest_sha, out_dir=OUT, checkpoint_path=checkpoint,
            summary_log_path=None, client=client, args=runtime_args, states=states,
            reopen_failed=False,
        )
        print(json.dumps(result), flush=True)
        stats.append(result)
    phase1.verify_phase1_baseline()
    completed = sum(state["state"] == "done" for state in states.values())
    transport_ok = sum(state["outcome"] == "ok" for state in states.values())
    phase1._write_json_atomic(OUT / "reports" / "run_summary.json", {
        "scope": SCOPE, "benchmark_sha256": benchmark_sha, "manifest_sha256": manifest_sha,
        "started_utc": started, "completed_utc": shared.utcnow(), "planned_rows": 80,
        "recorded_cases": completed, "transport_ok": transport_ok, "per_config": stats,
        "readiness_sha256": shared.sha256_file(OUT / "reports" / "readiness.json"),
    })
    if completed != 80 or transport_ok != 80:
        raise shared.GateError(f"Expected 80 completed transports, got {completed} finals and {transport_ok} OK.")
    return shared.EXIT_OK


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-execution", action="store_true")
    parser.add_argument("--approved-phase1-sha256", required=True)
    parser.add_argument("--readiness-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        phase1.verify_phase1_baseline()
        benchmark_sha = shared.require_authorization(
            phase1.PHASE1_BENCHMARK, args.approved_phase1_sha256, args.authorize_execution)
        data, snapshot_sha = shared.load_json_snapshot(phase1.PHASE1_BENCHMARK)
        if snapshot_sha != benchmark_sha or benchmark_sha != phase1.PHASE1_BENCHMARK_SHA256:
            raise shared.GateError("The Phase 1 snapshot differs from the authorized baseline.")
        _, cases = shared.validate_benchmark(data, expected_cases=40)
        manifest, manifest_sha = shared.load_json_snapshot(MANIFEST)
        entries = load_configs(manifest)
        configs = [shared.normalize_config(row, i) for i, row in enumerate(entries)]
        (OUT / "logs").mkdir(parents=True, exist_ok=True)
        with (OUT / "logs" / "run.lock").open("a+b") as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            return run_locked(args, data, benchmark_sha, manifest, manifest_sha, cases, entries, configs)
    except (shared.GateError, shared.AuthorizationError, shared.RateLimitedError,
            readiness.AbortRun, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
