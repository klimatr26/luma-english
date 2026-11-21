"""Measure production-profile Qwen hybrid Vulkan and Intel UHD 630 Vulkan."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
from time import perf_counter

import psutil

sys.dont_write_bytecode = True
import run_laptop_resources as base

LAB = Path(__file__).resolve().parent
OUT = LAB / "results_laptop_hybrid_gpu_v1"
PRIOR = LAB / "results_laptop_resources_v1"
INTEL = "Intel(R) UHD Graphics 630"
NVIDIA = "Quadro P1000"
WAIT = {"load": 180, "warmup": 120, "case": 240}


def prepare():
    manifest_path = OUT / "manifest.json"
    base.require(not manifest_path.exists(), "A manifest already exists.")
    prior = base.read_json(PRIOR / "manifest.json")
    base.require(base.sha(PRIOR / "cases.json") == prior["subset_sha256"], "Prior common subset SHA mismatch.")
    base.require(base.sha(base.FROZEN) == prior["frozen_manifest_sha256"] == base.EXPECTED_FROZEN_SHA,
                 "Frozen manifest SHA mismatch.")
    base.require(base.sha(base.SOURCE) == prior["source_sha256"] == base.EXPECTED_SOURCE_SHA,
                 "Frozen development source SHA mismatch.")
    frozen = base.read_json(base.FROZEN)
    profiles = {c["family"]: c for c in frozen["configurations"] if c["backend"] == "Vulkan"}
    configs = []
    for family, adapter, layers, cid in (
        ("qwen", NVIDIA, 32, "qwen--quadro-p1000--32"),
        ("qwen", INTEL, -1, "qwen--intel-uhd630--all"),
        ("qwen", INTEL, 16, "qwen--intel-uhd630--16"),
        ("gemma", INTEL, -1, "gemma--intel-uhd630--all"),
        ("gemma", INTEL, 16, "gemma--intel-uhd630--16"),
    ):
        cfg = dict(profiles[family])
        cfg.update(id=cid, adapter=adapter, gpu_layers=layers, conditional=adapter == INTEL and layers == 16,
                   model_path="models/" + base.PureWindowsPath(cfg["model_path"]).name)
        configs.append(cfg)
    build = base.read_json(OUT / "bridge_build.json")
    base.require(build["frozen_manifest_sha256"] == prior["frozen_manifest_sha256"], "Bridge build mismatch.")
    shutil.copyfile(PRIOR / "cases.json", OUT / "cases.json")
    host = base.host_inventory()
    host["intel_preflight"] = base.read_json(OUT / "intel_preflight.json")
    base.atomic(OUT / "host.json", host)
    manifest = {k: prior[k] for k in ("context", "seed", "thinking", "guided_json", "retries", "llama_cpp_commit",
                                    "case_count", "source", "source_sha256", "frozen_manifest_sha256",
                                    "subset", "subset_sha256", "selection")}
    base.atomic(manifest_path, {**manifest, "scope": "laptop_hybrid_gpu_v1", "prepared_utc": base.now(),
        "reference_manifest_sha256": base.sha(PRIOR / "manifest.json"),
        "native_directory": str((OUT / "native").relative_to(LAB)), "native_abi": 2,
        "timeouts_seconds": WAIT, "configurations": configs, "dll_sha256": build["staged_dll_sha256"],
        "bridge_build_sha256": base.sha(OUT / "bridge_build.json"), "runner_sha256": base.sha(__file__),
        "worker_source_sha256": base.sha(LAB / "run_laptop_resources.py"),
        "protocol_sha256": base.sha(OUT / "protocol.md")})


class TimedWorker(base.Worker):
    def request(self, op, *, timeout, **payload):
        self.process.stdin.write(json.dumps({"op": op, **payload}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        try:
            reply = self.replies.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"{op} exceeded {timeout} s") from None
        if reply is None:
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            raise RuntimeError(f"Worker closed stdout on {op} (exit {self.process.poll()}).")
        return json.loads(reply)


class IntelMonitor(base.LaptopMonitor):
    def sample_gpu(self, value):
        super().sample_gpu({"unavailable_reason": "NVIDIA telemetry does not describe Intel shared memory."})

    def gpu_loop(self):
        while not self.stop_event.wait(1):
            self.sample_gpu(None)


def device_options(host, cfg, baseline):
    summary = host["vulkan"].get("stdout", "")
    devices = re.split(r"(?m)^GPU(\d+):\s*$", summary)
    candidates = [(index, description) for index, description in zip(devices[1::2], devices[2::2])
                  if cfg["adapter"] in description]
    base.require(len(candidates) == 1, f"Could not uniquely select {cfg['adapter']}.")
    index, description = candidates[0]
    if cfg["adapter"] == INTEL:
        base.require(host["intel_preflight"]["initialized"], "Intel backend preflight failed.")
        base.require(psutil.virtual_memory().available >= 6 * 2**30, "Insufficient host RAM for Intel UMA.")
        base.require("PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU" in description, "Intel device is not the enumerated iGPU.")
    else:
        base.require(baseline.get("total_mib", 0) - baseline.get("used_mib", 0) >= 3450,
                     "Insufficient NVIDIA VRAM headroom for the measured 32-layer candidate.")
    return {"PYTHONIOENCODING": "utf-8", "GGML_VK_VISIBLE_DEVICES": index,
            "WG_HYBRID_GPU_LAYERS": str(cfg["gpu_layers"])}


def placement(state, log, cfg):
    prefix = next((line for line in log.splitlines() if "using device Vulkan" in line), None)
    matches = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", log)
    base.require(state["backend"] == "Vulkan" and prefix and cfg["adapter"] in prefix,
                 "Effective Vulkan adapter not established.")
    if cfg["adapter"] == NVIDIA:
        base.require("0000:01:00.0" in prefix, "Unexpected NVIDIA PCI device.")
    base.require(matches, "No layer placement evidence.")
    used, full = map(int, matches[-1])
    expected = full if cfg["gpu_layers"] < 0 else cfg["gpu_layers"]
    base.require(used == expected and (cfg["adapter"] != NVIDIA or full == 33),
                 f"Unexpected offload: {used}/{full}.")
    state.update(device=cfg["adapter"], physical_gpu_log=prefix, offload_evidence_log=[used, full])


def run_block(cfg, cases, manifest_sha, host):
    cid = cfg["id"]
    intel = cfg["adapter"] == INTEL
    baseline = {} if intel else base.gpu()
    path = OUT / "readiness" / f"{cid}.json"
    ready = {"config_id": cid, "adapter": cfg["adapter"], "baseline_gpu": baseline, "started_utc": base.now(),
             "system_cpu_before_percent": psutil.cpu_percent(interval=1), "ac_power": base.ac_connected(),
             "status": "preflight"}
    worker = monitor = case_id = None
    try:
        base.require(ready["ac_power"], "AC power required.")
        options = device_options(host, cfg, baseline)
        ready.update(options)
        ready["status"] = "load"
        base.atomic(path, ready)
        worker = TimedWorker(OUT, cfg, options)
        monitor = (IntelMonitor if intel else base.LaptopMonitor)(worker.process.pid)
        base.require(worker.request("echo", text="café", timeout=15) == "café", "UTF-8 probe failed.")
        state = worker.request("load", timeout=WAIT["load"])
        ready["load_memory"] = monitor.finish()
        base.require("load_error" not in state, state.get("load_error"))
        ready["state"] = state
        placement(state, worker.log_path.read_text(encoding="utf-8", errors="replace"), cfg)
        ready["status"] = "warmup"
        base.atomic(path, ready)
        monitor.reset()
        warmup = worker.request("generate", user=base.user_prompt(base.SYNTHETIC), timeout=WAIT["warmup"])
        ready["warmup"] = warmup
        base.atomic(path, ready)
        ready["warmup_memory"] = monitor.finish()
        base.require(warmup["status"] == 0 and warmup["output_tokens"] > 0, "Technical warmup failure.")
        if intel:
            base.require(warmup["native_seconds"] <= WAIT["warmup"], "Intel warmup exceeded the practical limit.")
        ready["status"] = "ready"
        base.atomic(path, ready)
        print(f"{cid} ready {state}, warmup={warmup['native_seconds']:.2f}s", flush=True)
        for index, case in enumerate(cases, 1):
            case_id = case["id"]
            base.require(base.ac_connected(), "Lost AC power.")
            prompt = base.user_prompt(case)
            identity = {"case_id": case_id, "config_id": cid, "index": index, "attempt": 1,
                        "manifest_sha256": manifest_sha, "model_sha256": cfg["model_sha256"],
                        "user_prompt_sha256": base.digest(prompt), "started_utc": base.now()}
            base.append(OUT / "attempts" / f"{cid}.jsonl", identity)
            monitor.reset()
            start = perf_counter()
            try:
                answer = worker.request("generate", user=prompt, timeout=WAIT["case"])
            except Exception as error:
                answer = {"status": -999, "error": repr(error), "finish_reason": "technical_error", "raw_response": ""}
            base.append(OUT / "raw" / f"{cid}.jsonl",
                        {**identity, **answer, "request_seconds": perf_counter() - start})
            base.append(OUT / "telemetry" / f"{cid}.jsonl",
                        {**identity, "response_sha256": base.digest(answer["raw_response"]), "memory": monitor.finish()})
            base.require(answer["status"] == 0, f"Native generation failed: {answer['error']}")
            print(f"{cid} {index}/{len(cases)} {case_id} {answer['native_seconds']:.2f}s", flush=True)
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
        return intel and cfg["gpu_layers"] < 0 and ready["status"] == "load" and bool(
            re.search(r"ErrorOutOf(Device|Host)Memory|failed to allocate|out of (device )?memory", log, re.I)
            and "ErrorDeviceLost" not in log)
    finally:
        if monitor is not None:
            monitor.close()
        if worker is not None:
            worker.close()


def run():
    manifest_path = OUT / "manifest.json"
    m = base.read_json(manifest_path)
    for file, key in ((Path(__file__), "runner_sha256"), (LAB / "run_laptop_resources.py", "worker_source_sha256"),
                      (OUT / "cases.json", "subset_sha256"), (OUT / "protocol.md", "protocol_sha256"),
                      (OUT / "bridge_build.json", "bridge_build_sha256")):
        base.require(base.sha(file) == m[key], f"SHA mismatch: {file.name}")
    for name, sha256 in m["dll_sha256"].items():
        base.require(base.sha(OUT / "native" / name) == sha256, f"SHA mismatch: {name}")
    models = {cfg["model_path"]: cfg for cfg in m["configurations"]}
    for model, cfg in models.items():
        path = LAB / model
        base.require(path.stat().st_size == cfg["model_bytes"] and base.sha(path) == cfg["model_sha256"],
                     f"Model SHA mismatch: {model}")
        base.require(base.digest(cfg["system_prompt"]) == cfg["system_prompt_sha256"], "Prompt SHA mismatch.")
    cases = base.read_json(OUT / "cases.json")
    base.require([c["id"] for c in cases] == [c["id"] for c in m["selection"]] and len(cases) == 15
                 and all(c.keys() == {"id", "level", "task", "student_text"} for c in cases), "Invalid case coverage.")
    base.require(base.ac_connected(), "Connect to AC power.")
    sha = base.sha(manifest_path)
    host = base.read_json(OUT / "host.json")
    with (OUT / "run.started").open("x", encoding="utf-8") as f:
        f.write(base.now() + "\n")
        f.flush()
        os.fsync(f.fileno())
    kernel = ctypes.windll.kernel32
    kernel.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
    kernel.SetThreadExecutionState.restype = ctypes.c_uint32
    base.require(kernel.SetThreadExecutionState(0x80000001), "Could not inhibit sleep.")
    performed = []
    try:
        partial = False
        for cfg in m["configurations"]:
            if cfg["conditional"] and not partial:
                continue
            performed.append(cfg)
            partial = run_block(cfg, cases, sha, host)
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
