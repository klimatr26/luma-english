"""Repeat the common Windows laptop resource test on battery power."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path, PureWindowsPath
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
OUT = LAB / "results_laptop_battery_v1"
PRIOR = LAB / "results_laptop_resources_v1"
HYBRID = LAB / "results_laptop_hybrid_gpu_v1"
MIN_CHARGE = 12
TIMEOUT = 600
KERNEL = C.WinDLL("kernel32", use_last_error=True)


class PowerStatus(C.Structure):
    _fields_ = [("ac", C.c_ubyte), ("battery_flag", C.c_ubyte), ("percent", C.c_ubyte),
                ("saver", C.c_ubyte), ("lifetime", C.c_uint32), ("full_lifetime", C.c_uint32)]


KERNEL.GetSystemPowerStatus.argtypes = [C.POINTER(PowerStatus)]
KERNEL.GetSystemPowerStatus.restype = C.c_int
KERNEL.SetThreadExecutionState.argtypes = [C.c_uint32]
KERNEL.SetThreadExecutionState.restype = C.c_uint32


def power_status():
    result = PowerStatus()
    ok = KERNEL.GetSystemPowerStatus(C.byref(result))
    return {"utc": base.now(), "ac_power": bool(result.ac) if ok and result.ac in (0, 1) else None,
            "percent": int(result.percent) if ok and result.percent <= 100 else None,
            "saver": bool(result.saver) if ok and result.saver in (0, 1) else None,
            "estimated_seconds": result.lifetime if ok and result.lifetime != 0xffffffff else None}


class PowerBoundary(RuntimeError):
    pass


def require_battery():
    state = power_status()
    if state["ac_power"] is not False or state["percent"] is None:
        raise PowerBoundary(f"Battery-only power state required: {state}")
    if state["percent"] <= MIN_CHARGE:
        raise PowerBoundary(f"Battery reached the {MIN_CHARGE}% reserve: {state}")
    return state


def prepare():
    path = OUT / "manifest.json"
    base.require(not path.exists(), "This run already has a frozen manifest.")
    require_battery()
    prior, hybrid = [base.read_json(directory / "manifest.json") for directory in (PRIOR, HYBRID)]
    frozen_sha = base.sha(base.FROZEN)
    base.require(frozen_sha == base.EXPECTED_FROZEN_SHA == prior["frozen_manifest_sha256"]
                 == hybrid["frozen_manifest_sha256"], "Frozen manifest mismatch.")
    base.require(base.sha(base.SOURCE) == prior["source_sha256"] == base.EXPECTED_SOURCE_SHA,
                 "Development source mismatch.")
    base.require(base.sha(PRIOR / "cases.json") == prior["subset_sha256"]
                 == hybrid["subset_sha256"], "Common subset mismatch.")
    frozen = base.read_json(base.FROZEN)
    original_dlls = {PureWindowsPath(i["path"]).name: i["sha256"] for i in frozen["source_bindings"]
                      if PureWindowsPath(i["path"]).parent.name == "win-x64" and i["path"].endswith(".dll")}
    hybrid_dlls = hybrid["dll_sha256"]
    base.require(len(original_dlls) == 7 and original_dlls.keys() == hybrid_dlls.keys()
                 and all(a == hybrid_dlls[k] for k, a in original_dlls.items() if k != "writing_llama_bridge.dll"),
                 "Runtime bindings mismatch.")
    runtime = {"original": {"directory": base.NATIVE.as_posix(), "dll_sha256": original_dlls},
               "hybrid": {"directory": hybrid["native_directory"], "dll_sha256": hybrid_dlls}}
    profiles = {(c["family"], c["backend"]): c for c in frozen["configurations"]}
    configs = []
    for family, backend, layers, runtime_id, ref, cid in (
        ("qwen", "Vulkan", 32, "hybrid", "hybrid", "qwen--quadro-p1000--32"),
        ("gemma", "Vulkan", 36, "original", "prior", "13-gemma4-e2b-ud-q4-k-xl--vulkan"),
        ("gemma", "CPU", 0, "original", "prior", "13-gemma4-e2b-ud-q4-k-xl--cpu"),
        ("qwen", "CPU", 0, "original", "prior", "portable-unsloth-qwen35-4b-q4-k-m--cpu"),
    ):
        cfg = dict(profiles[(family, backend)])
        cfg.update(id=cid, gpu_layers=layers, runtime=runtime_id, ac_reference=ref,
                   minimum_free_vram_mib=3450 if family == "qwen" else 2200,
                   model_path="models/" + PureWindowsPath(cfg["model_path"]).name)
        configs.append(cfg)
    shutil.copyfile(PRIOR / "cases.json", OUT / "cases.json")
    host = base.host_inventory()
    for label, args in (
        ("battery_plan", ("SUB_BATTERY",)), ("processor_min", ("SUB_PROCESSOR", "PROCTHROTTLEMIN")),
        ("processor_max", ("SUB_PROCESSOR", "PROCTHROTTLEMAX")),
    ):
        result = subprocess.run(["powercfg", "/query", "SCHEME_CURRENT", *args], capture_output=True,
                                encoding="oem", errors="replace", check=True, timeout=15)
        host[label] = result.stdout
    host["initial_battery"] = require_battery()
    base.atomic(OUT / "host.json", host)
    manifest = {k: prior[k] for k in ("context", "seed", "thinking", "guided_json", "retries", "llama_cpp_commit",
                                    "case_count", "source", "source_sha256", "frozen_manifest_sha256",
                                    "subset", "subset_sha256", "selection")}
    manifest.update(scope="laptop_battery_v1", prepared_utc=base.now(), timeouts_seconds=TIMEOUT,
                    minimum_charge_percent=MIN_CHARGE, runtimes=runtime, configurations=configs,
                    ac_reference_sha256={"prior": base.sha(PRIOR / "manifest.json"), "hybrid": base.sha(HYBRID / "manifest.json")},
                    protocol_sha256=base.sha(OUT / "protocol.md"), runner_sha256=base.sha(__file__),
                    worker_sha256=base.sha(LAB / "run_laptop_resources.py"))
    for name, binding in runtime.items():
        base.atomic(OUT / ("worker_" + name) / "manifest.json",
                    {**manifest, "native_directory": binding["directory"]})
    base.atomic(path, manifest)


class BatteryWorker(base.Worker):
    def request(self, op, **payload):
        require_battery()
        self.process.stdin.write(json.dumps({"op": op, **payload}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        deadline = perf_counter() + TIMEOUT
        while (remaining := deadline - perf_counter()) > 0:
            require_battery()
            try:
                reply = self.replies.get(timeout=min(1.0, remaining))
            except queue.Empty:
                continue
            if reply is None:
                raise RuntimeError(f"Worker closed stdout on {op} (exit {self.process.poll()}).")
            return json.loads(reply)
        raise TimeoutError(f"{op} exceeded {TIMEOUT} s.")


class BatteryMonitor(base.LaptopMonitor):
    def sample_gpu(self, value):
        base.Monitor.sample_gpu(self, value)
        state = {**power_status(), "cpu_percent": psutil.cpu_percent()}
        with self.lock:
            self.system_samples.append(state)


def verify_placement(state, log, cfg):
    if cfg["backend"] == "CPU":
        base.verify_placement(state, log, cfg, None)
        return
    device = next((line for line in log.splitlines() if "using device Vulkan" in line), "")
    layers = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", log)
    base.require(state["backend"] == "Vulkan" and "Quadro P1000" in device and "0000:01:00.0" in device,
                 "Quadro Vulkan device was not established.")
    expected = (cfg["gpu_layers"], 33 if cfg["family"] == "qwen" else 36)
    base.require(layers and tuple(map(int, layers[-1])) == expected, "Unexpected offload count.")
    state.update(device="Quadro P1000", physical_gpu_log=device, offload_evidence_log=list(expected))


def run_block(cfg, cases, manifest_sha, host):
    cid = cfg["id"]
    path = OUT / "readiness" / f"{cid}.json"
    baseline = base.gpu()
    ready = {"config_id": cid, "baseline_gpu": baseline, "started_utc": base.now(), "power_before": power_status(),
             "system_cpu_before_percent": psutil.cpu_percent(interval=1), "status": "preflight"}
    worker = monitor = case_id = None
    try:
        require_battery()
        options = {"PYTHONIOENCODING": "utf-8"}
        if cfg["backend"] == "Vulkan":
            vulkan, _ = base.vulkan_options(host, baseline, cfg)
            options.update(vulkan)
        if cfg["runtime"] == "hybrid":
            options["WG_HYBRID_GPU_LAYERS"] = str(cfg["gpu_layers"])
        ready["worker_env"] = options
        ready["status"] = "load"
        base.atomic(path, ready)
        worker = BatteryWorker(OUT / ("worker_" + cfg["runtime"]), cfg, options)
        monitor = BatteryMonitor(worker.process.pid)
        base.require(worker.request("echo", text="café") == "café", "UTF-8 probe failed.")
        state = worker.request("load")
        ready["load_memory"] = monitor.finish()
        require_battery()
        base.require("load_error" not in state, state.get("load_error"))
        ready["state"] = state
        verify_placement(state, worker.log_path.read_text(encoding="utf-8", errors="replace"), cfg)
        ready["status"] = "warmup"
        base.atomic(path, ready)
        monitor.reset()
        warmup = worker.request("generate", user=base.user_prompt(base.SYNTHETIC))
        ready["warmup"] = warmup
        base.atomic(path, ready)
        ready["warmup_memory"] = monitor.finish()
        require_battery()
        base.require(warmup["status"] == 0 and warmup["output_tokens"] > 0, "Technical warmup failure.")
        ready["status"] = "ready"
        base.atomic(path, ready)
        print(f"{cid} ready {state}, warmup={warmup['native_seconds']:.2f}s battery={power_status()['percent']}%", flush=True)
        for index, case in enumerate(cases, 1):
            case_id = case["id"]
            before = require_battery()
            prompt = base.user_prompt(case)
            identity = {"case_id": case_id, "config_id": cid, "index": index, "attempt": 1,
                        "manifest_sha256": manifest_sha, "model_sha256": cfg["model_sha256"],
                        "user_prompt_sha256": base.digest(prompt), "started_utc": base.now(),
                        "battery_before_percent": before["percent"], "saver_before": before["saver"]}
            base.append(OUT / "attempts" / f"{cid}.jsonl", identity)
            monitor.reset()
            start = perf_counter()
            failure = None
            answer = {}
            try:
                answer = worker.request("generate", user=prompt)
                require_battery()
            except Exception as error:
                failure = error
                answer = {**answer, "returned_status": answer.get("status"), "status": -999, "error": repr(error),
                          "raw_response": answer.get("raw_response", ""), "finish_reason": "technical_error"}
            elapsed = perf_counter() - start
            after = power_status()
            row = {**identity, **answer, "request_seconds": elapsed, "battery_after_percent": after["percent"],
                   "saver_after": after["saver"]}
            base.append(OUT / "raw" / f"{cid}.jsonl", row)
            base.append(OUT / "telemetry" / f"{cid}.jsonl",
                        {**identity, "response_sha256": base.digest(answer["raw_response"]), "memory": monitor.finish()})
            if failure is not None:
                raise failure
            base.require(answer["status"] == 0, f"Native generation failed: {answer['error']}")
            print(f"{cid} {index}/{len(cases)} {case_id} {answer['native_seconds']:.2f}s, battery={after['percent']}%", flush=True)
        return False
    except Exception as error:
        failure = {"config_id": cid, "case_id": case_id, "stage": ready["status"], "error": repr(error), "utc": base.now()}
        base.append(OUT / "failures.jsonl", failure)
        ready["failure"] = failure
        print(f"{cid}: {failure}", flush=True)
        return isinstance(error, PowerBoundary)
    finally:
        if monitor is not None:
            monitor.close()
        if worker is not None:
            worker.close()
        ready["power_after"] = power_status()
        base.atomic(path, ready)


def run():
    path = OUT / "manifest.json"
    manifest = base.read_json(path)
    for p, key in ((Path(__file__), "runner_sha256"), (LAB / "run_laptop_resources.py", "worker_sha256"),
                   (OUT / "cases.json", "subset_sha256"), (OUT / "protocol.md", "protocol_sha256"),
                   (base.FROZEN, "frozen_manifest_sha256"), (base.SOURCE, "source_sha256")):
        base.require(base.sha(p) == manifest[key], f"SHA mismatch: {p.name}")
    for name, binding in manifest["runtimes"].items():
        for file, sha in binding["dll_sha256"].items():
            base.require(base.sha(LAB / binding["directory"] / file) == sha, f"Runtime SHA mismatch: {file}")
        worker = base.read_json(OUT / ("worker_" + name) / "manifest.json")
        base.require(worker == {**manifest, "native_directory": binding["directory"]}, "Worker binding mismatch.")
    for cfg in manifest["configurations"]:
        base.require(base.digest(cfg["system_prompt"]) == cfg["system_prompt_sha256"], "Prompt mismatch.")
    for file, cfg in {c["model_path"]: c for c in manifest["configurations"]}.items():
        p = LAB / file
        base.require(p.stat().st_size == cfg["model_bytes"] and base.sha(p) == cfg["model_sha256"], "Model mismatch.")
    cases = base.read_json(OUT / "cases.json")
    base.require(len(cases) == 15 and [c["id"] for c in cases] == [c["id"] for c in manifest["selection"]]
                 and all(c.keys() == {"id", "level", "task", "student_text"} for c in cases), "Invalid case subset.")
    start = require_battery()
    with (OUT / "run.started").open("x", encoding="utf-8") as f:
        f.write(start["utc"] + "\n")
        f.flush()
        os.fsync(f.fileno())
    base.require(KERNEL.SetThreadExecutionState(0x80000001), "Could not inhibit sleep.")
    host = base.read_json(OUT / "host.json")
    stopped = False
    try:
        for cfg in manifest["configurations"]:
            if run_block(cfg, cases, base.sha(path), host):
                stopped = True
                break
    finally:
        KERNEL.SetThreadExecutionState(0x80000000)
        base.atomic(OUT / "power_bounds.json", {"start": start, "end": power_status(), "stopped_on_power_boundary": stopped})
        base.report(OUT, manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    if parser.parse_args().command == "prepare":
        prepare()
    else:
        run()
