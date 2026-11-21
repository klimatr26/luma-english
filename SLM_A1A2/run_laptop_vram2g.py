"""Run the existing writing profile under a simulated 2 GiB VRAM budget."""
import argparse
import ctypes
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import sys
from time import perf_counter

import psutil

sys.dont_write_bytecode = True
import run_laptop_resources as base

LAB = Path(__file__).resolve().parent
OUT = LAB / "results_laptop_vram2g_v1"
HYBRID = LAB / "results_laptop_hybrid_gpu_v1"
PRIOR = LAB / "results_laptop_resources_v1"
ADMISSION = 1920
LIMIT = 2048


def prepare():
    path = OUT / "manifest.json"
    base.require(not path.exists(), "An experiment manifest already exists.")
    base.require(base.ac_connected(), "AC power required.")
    prior, hybrid = [base.read_json(p / "manifest.json") for p in (PRIOR, HYBRID)]
    base.require(base.sha(base.FROZEN) == base.EXPECTED_FROZEN_SHA == prior["frozen_manifest_sha256"]
                 == hybrid["frozen_manifest_sha256"], "Frozen manifest mismatch.")
    base.require(base.sha(PRIOR / "cases.json") == prior["subset_sha256"] == hybrid["subset_sha256"],
                 "Common subset SHA mismatch.")
    frozen = base.read_json(base.FROZEN)
    profiles = {c["family"]: c for c in frozen["configurations"] if c["backend"] == "Vulkan"}
    configs = []
    for family, layers, full, fallback in (("qwen", 14, 33, False), ("qwen", 12, 33, True),
                                           ("gemma", 18, 36, False), ("gemma", 16, 36, True)):
        cfg = dict(profiles[family])
        cfg.update(id=f"{family}--quadro--{layers}", gpu_layers=layers, full_layers=full, conditional=fallback,
                   minimum_free_vram_mib=LIMIT, model_path="models/" + PureWindowsPath(cfg["model_path"]).name)
        configs.append(cfg)
    shutil.copyfile(PRIOR / "cases.json", OUT / "cases.json")
    base.atomic(OUT / "host.json", base.host_inventory())
    manifest = {k: prior[k] for k in ("context", "seed", "thinking", "guided_json", "retries", "llama_cpp_commit",
                                    "case_count", "source", "source_sha256", "frozen_manifest_sha256",
                                    "subset", "subset_sha256", "selection")}
    manifest.update(scope="laptop_vram2g_v1", prepared_utc=base.now(), configurations=configs,
                    native_directory=hybrid["native_directory"], native_abi=2, dll_sha256=hybrid["dll_sha256"],
                    native_timeout_seconds=base.TIMEOUT, admission_mib=ADMISSION, limit_mib=LIMIT,
                    worker_sha256=base.sha(LAB / "run_laptop_resources.py"), runner_sha256=base.sha(__file__),
                    protocol_sha256=base.sha(OUT / "protocol.md"))
    base.atomic(path, manifest)


class VRAMExceeded(RuntimeError):
    pass


def check_vram(sample, limit):
    peak = sample.get("device_vram_peak_mib")
    base.require(peak is not None, "NVIDIA VRAM telemetry unavailable.")
    if peak > limit:
        raise VRAMExceeded(f"Observed {peak} MiB global VRAM, above limit {limit} MiB.")


def verify_placement(state, log, cfg):
    device = next((line for line in log.splitlines() if "using device Vulkan" in line), "")
    placed = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", log)
    expected = (cfg["gpu_layers"], cfg["full_layers"])
    base.require(state["backend"] == "Vulkan" and "Quadro P1000" in device and "0000:01:00.0" in device,
                 "Quadro Vulkan adapter not established.")
    base.require(placed and tuple(map(int, placed[-1])) == expected, "Unexpected layer placement.")
    state.update(device="Quadro P1000", physical_gpu_log=device, offload_evidence_log=list(expected))


def run_block(cfg, cases, manifest_sha, host):
    cid = cfg["id"]
    path = OUT / "readiness" / f"{cid}.json"
    baseline = base.gpu()
    ready = {"config_id": cid, "baseline_gpu": baseline, "started_utc": base.now(),
             "system_cpu_before_percent": psutil.cpu_percent(interval=1), "status": "preflight"}
    worker = monitor = case_id = None
    try:
        base.require(base.ac_connected(), "AC power required.")
        options, _ = base.vulkan_options(host, baseline, cfg)
        options.update(PYTHONIOENCODING="utf-8", WG_HYBRID_GPU_LAYERS=str(cfg["gpu_layers"]))
        ready["worker_env"] = options
        ready["status"] = "load"
        base.atomic(path, ready)
        worker = base.Worker(OUT, cfg, options)
        monitor = base.LaptopMonitor(worker.process.pid)
        base.require(worker.request("echo", text="café") == "café", "UTF-8 probe failed.")
        state = worker.request("load")
        ready["load_memory"] = monitor.finish()
        base.require("load_error" not in state, state.get("load_error"))
        ready["state"] = state
        verify_placement(state, worker.log_path.read_text(encoding="utf-8", errors="replace"), cfg)
        check_vram(ready["load_memory"], ADMISSION)
        ready["status"] = "warmup"
        base.atomic(path, ready)
        monitor.reset()
        warmup = worker.request("generate", user=base.user_prompt(base.SYNTHETIC))
        ready["warmup"] = warmup
        base.atomic(path, ready)
        ready["warmup_memory"] = monitor.finish()
        base.require(warmup["status"] == 0 and warmup["output_tokens"] > 0, "Technical warmup failure.")
        check_vram(ready["warmup_memory"], ADMISSION)
        ready["status"] = "ready"
        base.atomic(path, ready)
        print(f"{cid} ready {state}, warmup={warmup['native_seconds']:.2f}s", flush=True)
        for index, case in enumerate(cases, 1):
            case_id = case["id"]
            base.require(base.ac_connected(), "AC power lost.")
            prompt = base.user_prompt(case)
            identity = {"case_id": case_id, "config_id": cid, "index": index, "attempt": 1,
                        "manifest_sha256": manifest_sha, "model_sha256": cfg["model_sha256"],
                        "user_prompt_sha256": base.digest(prompt), "started_utc": base.now()}
            base.append(OUT / "attempts" / f"{cid}.jsonl", identity)
            monitor.reset()
            start = perf_counter()
            failure = None
            try:
                answer = worker.request("generate", user=prompt)
            except Exception as error:
                failure = error
                answer = {"status": -999, "error": repr(error), "finish_reason": "technical_error", "raw_response": ""}
            elapsed = perf_counter() - start
            base.append(OUT / "raw" / f"{cid}.jsonl", {**identity, **answer, "request_seconds": elapsed})
            memory = monitor.finish()
            base.append(OUT / "telemetry" / f"{cid}.jsonl",
                        {**identity, "response_sha256": base.digest(answer["raw_response"]), "memory": memory})
            if failure is not None:
                raise failure
            base.require(answer["status"] == 0, f"Native generation failed: {answer['error']}")
            check_vram(memory, LIMIT)
            peak = memory["device_vram_peak_mib"]
            print(f"{cid} {index}/{len(cases)} {case_id} {answer['native_seconds']:.2f}s VRAM={peak} MiB", flush=True)
        return False
    except Exception as error:
        failure = {"config_id": cid, "case_id": case_id, "stage": ready["status"], "error": repr(error), "utc": base.now()}
        base.append(OUT / "failures.jsonl", failure)
        ready["failure"] = failure
        if monitor is not None and ready["status"] == "load" and "load_memory" not in ready:
            ready["load_memory"] = monitor.finish()
        base.atomic(path, ready)
        print(f"{cid}: {failure}", flush=True)
        log = worker.log_path.read_text(encoding="utf-8", errors="replace") if worker else ""
        memory_issue = isinstance(error, VRAMExceeded) or bool(
            re.search(r"ErrorOutOf(Device|Host)Memory|failed to allocate|out of (device )?memory", log, re.I)
            and "ErrorDeviceLost" not in log)
        return memory_issue and ready["status"] in ("load", "warmup")
    finally:
        if monitor is not None:
            monitor.close()
        if worker is not None:
            worker.close()


def run():
    path = OUT / "manifest.json"
    m = base.read_json(path)
    for file, key in ((Path(__file__), "runner_sha256"), (LAB / "run_laptop_resources.py", "worker_sha256"),
                      (OUT / "protocol.md", "protocol_sha256"), (OUT / "cases.json", "subset_sha256"),
                      (base.FROZEN, "frozen_manifest_sha256"), (base.SOURCE, "source_sha256")):
        base.require(base.sha(file) == m[key], f"SHA mismatch: {file.name}")
    for name, sha in m["dll_sha256"].items():
        base.require(base.sha(LAB / m["native_directory"] / name) == sha, f"SHA mismatch: {name}")
    for model, cfg in {c["model_path"]: c for c in m["configurations"]}.items():
        p = LAB / model
        base.require(p.stat().st_size == cfg["model_bytes"] and base.sha(p) == cfg["model_sha256"],
                     f"Model mismatch: {model}")
        base.require(base.digest(cfg["system_prompt"]) == cfg["system_prompt_sha256"], "Prompt mismatch.")
    cases = base.read_json(OUT / "cases.json")
    base.require(len(cases) == 15 and [c["id"] for c in cases] == [c["id"] for c in m["selection"]]
                 and all(c.keys() == {"id", "level", "task", "student_text"} for c in cases), "Invalid case subset.")
    base.require(base.ac_connected(), "AC power required.")
    with (OUT / "run.started").open("x", encoding="utf-8") as f:
        f.write(base.now() + "\n")
        f.flush()
        os.fsync(f.fileno())
    sha, host = base.sha(path), base.read_json(OUT / "host.json")
    kernel = ctypes.windll.kernel32
    kernel.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
    kernel.SetThreadExecutionState.restype = ctypes.c_uint32
    base.require(kernel.SetThreadExecutionState(0x80000001), "Could not inhibit sleep.")
    performed = []
    try:
        retry_smaller = False
        for cfg in m["configurations"]:
            if cfg["conditional"] and not retry_smaller:
                continue
            performed.append(cfg)
            retry_smaller = run_block(cfg, cases, sha, host)
    finally:
        kernel.SetThreadExecutionState(0x80000000)
        base.report(OUT, {**m, "configurations": performed})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    if parser.parse_args().command == "prepare":
        prepare()
    else:
        run()
