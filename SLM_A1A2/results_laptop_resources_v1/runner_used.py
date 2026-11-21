"""Run the 15-case Windows laptop resource comparison with frozen model profiles."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import queue
import re
import statistics
import subprocess
import sys
import threading
from time import perf_counter

import psutil

sys.dont_write_bytecode = True
from run_finalists_200 import NativeBridge, Monitor, SYNTHETIC, append, atomic, gpu, now, read_json, sha, user_prompt


LAB = Path(__file__).resolve().parent
OUT = LAB / "results_laptop_resources_v1"
FROZEN = LAB / "manifests/finalists_200_20261117.json"
SOURCE = LAB / "benchmark_development_120_v1.json"
NATIVE = Path("cross_demo/native/artifacts/b12359/win-x64")
QUOTAS = {("A1", "incorrect"): 5, ("A1", "correct"): 2, ("A2", "incorrect"): 6, ("A2", "correct"): 2}
TIMEOUT = 600
MIB = 1024**2
EXPECTED_FROZEN_SHA = "9ec595218c105e6a2b48d515dcffd01bbfd762b94646b2958f5f972b987e9878"
EXPECTED_SOURCE_SHA = "07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def host_inventory():
    inventory = r"""
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    $ErrorActionPreference = 'Stop'
    $thermal = @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue |
        Select-Object InstanceName,CurrentTemperature)
    [ordered]@{
        computer = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,TotalPhysicalMemory
        cpu = Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
        os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber
        adapters = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,PNPDeviceID)
        energy_plan = powercfg /getactivescheme
        sleep_config = @(powercfg /query SCHEME_CURRENT SUB_SLEEP)
        thermal_zones_tenths_kelvin = $thermal
    } | ConvertTo-Json -Depth 5 -Compress
    """
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", inventory],
                            capture_output=True, encoding="utf-8", check=True, timeout=35)
    host = json.loads(result.stdout)
    host.update({"timestamp_utc": now(), "python": sys.version, "psutil": psutil.__version__,
                 "battery": psutil.sensors_battery()._asdict(), "memory": psutil.virtual_memory()._asdict(),
                 "cpu_percent_before": psutil.cpu_percent(interval=1)})
    for name, command in (
        ("nvidia", ["nvidia-smi", "--query-gpu=name,uuid,pci.bus_id,memory.total,driver_version,driver_model.current",
                    "--format=csv,noheader,nounits"]),
        ("vulkan", ["vulkaninfo", "--summary"]),
    ):
        try:
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=30)
            host[name] = {"stdout": result.stdout, "stderr": result.stderr, "exit": result.returncode}
        except (OSError, subprocess.TimeoutExpired) as error:
            host[name] = {"error": str(error)}
    return host


def prepare(out):
    require(not (out / "manifest.json").exists(), "An existing manifest already freezes this run.")
    require(sha(FROZEN) == EXPECTED_FROZEN_SHA and sha(SOURCE) == EXPECTED_SOURCE_SHA,
            "Frozen manifest or development source SHA mismatch.")
    frozen = read_json(FROZEN)
    cases = read_json(SOURCE)["cases"]
    selected = []
    for (level, condition), size in QUOTAS.items():
        group = sorted((c for c in cases if (c["level"], c["condition"]) == (level, condition)),
                       key=lambda c: (c["length_words"], c["id"]))
        selected.extend(group[(2*j+1)*len(group)//(2*size)] for j in range(size))
    require(len(cases) == 120 and len({c["id"] for c in selected}) == 15, "Unexpected sample coverage.")
    selected.sort(key=lambda case: digest("20261118:" + case["id"]))
    subset = [{key: case[key] for key in ("id", "level", "task", "student_text")} for case in selected]
    atomic(out / "cases.json", subset)
    atomic(out / "host.json", host_inventory())
    bindings = []
    for item in frozen["source_bindings"]:
        parts = PureWindowsPath(item["path"]).parts
        path = Path(*parts[parts.index("SLM_A1A2") + 1:])
        if path.parent == NATIVE or path.name in {"run_finalists_200.py", "prompts.json", "catalog.json",
                                                  "writing_json_grammar.h"}:
            bindings.append({"path": path.as_posix(), "sha256": item["sha256"]})
    require(sum(Path(item["path"]).parent == NATIVE for item in bindings) == 7, "Expected seven native DLLs.")
    configs = sorted(frozen["configurations"], key=lambda c: (c["backend"], c["family"]))
    for config in configs:
        config["model_path"] = "models/" + PureWindowsPath(config["model_path"]).name
        config["minimum_free_vram_mib"] = {"gemma": 2200, "qwen": 3500}[config["family"]]
    manifest = {key: frozen[key] for key in ("context", "seed", "thinking", "guided_json", "retries", "llama_cpp_commit")}
    atomic(out / "manifest.json", {
        **manifest, "scope": "laptop_resources_v1", "prepared_utc": now(), "case_count": 15,
        "source": SOURCE.name, "source_sha256": sha(SOURCE), "frozen_manifest_sha256": sha(FROZEN),
        "subset": "cases.json", "subset_sha256": sha(out / "cases.json"),
        "selection": [{key: c[key] for key in ("id", "level", "condition", "length_words")} for c in selected],
        "native_directory": NATIVE.as_posix(), "native_abi": 2, "native_timeout_seconds": TIMEOUT,
        "runner_sha256": sha(__file__), "protocol_sha256": sha(LAB / "documentation/laptop_resources_protocol_v1.md"),
        "source_bindings": bindings, "configurations": configs,
    })


class LaptopMonitor(Monitor):
    def reset(self):
        self.system_samples = []
        psutil.cpu_percent()
        super().reset()

    def sample_gpu(self, value):
        super().sample_gpu(value)
        sample = {"utc": now(), "cpu_percent": psutil.cpu_percent(),
                  "ac_power": psutil.sensors_battery().power_plugged}
        with self.lock:
            self.system_samples.append(sample)

    def finish(self):
        stats = super().finish()
        with self.lock:
            return {**stats, "system_samples": list(self.system_samples)}


def worker(manifest_path, config_id):
    manifest = read_json(manifest_path)
    config = next(c for c in manifest["configurations"] if c["id"] == config_id)
    config["model_path"] = str(LAB / config["model_path"])
    bridge = NativeBridge(LAB / manifest["native_directory"])
    try:
        for line in sys.stdin:
            request = json.loads(line)
            match request["op"]:
                case "echo":
                    reply = request["text"]
                case "load":
                    reply = bridge.load(config, manifest["context"])
                case "generate":
                    reply = bridge.generate(config, request)
                case "exit":
                    break
                case operation:
                    raise ValueError(f"Unexpected operation: {operation}")
            print(json.dumps(reply, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        bridge.close()


class Worker:
    def __init__(self, out, config, options):
        self.replies = queue.Queue()
        self.log_path = out / "logs" / (config["id"] + ".log")
        self.log_path.parent.mkdir(exist_ok=True)
        with self.log_path.open("xb") as log:
            self.process = subprocess.Popen(
                [sys.executable, "-B", "-u", __file__, "--out", str(out), "--worker", config["id"]],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                encoding="utf-8", env={**os.environ, **options}, creationflags=NO_WINDOW,
            )
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:
                self.replies.put(line)
        finally:
            self.replies.put(None)

    def request(self, op, **payload):
        self.process.stdin.write(json.dumps({"op": op, **payload}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        try:
            reply = self.replies.get(timeout=TIMEOUT)
        except queue.Empty:
            raise TimeoutError(f"{op} exceeded {TIMEOUT} s") from None
        require(reply is not None, f"Worker closed stdout on {op} (exit {self.process.poll()}).")
        return json.loads(reply)

    def close(self):
        try:
            self.process.stdin.write('{"op":"exit"}\n')
            self.process.stdin.flush()
            self.process.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                for child in psutil.Process(self.process.pid).children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                self.process.kill()
                self.process.wait(10)
        finally:
            self.process.stdin.close()
            self.reader.join(5)
            self.process.stdout.close()


def ac_connected():
    battery = psutil.sensors_battery()
    return battery is not None and battery.power_plugged


def vulkan_options(host, baseline, config):
    nvidia = host["nvidia"].get("stdout", "").strip().splitlines()
    require(len(nvidia) == 1, "Expected one NVIDIA adapter in nvidia-smi.")
    name, uuid, pci, *_ = [field.strip() for field in nvidia[0].split(",")]
    require(name == "Quadro P1000" and baseline.get("uuid") == uuid, "Quadro P1000 or its telemetry is unavailable.")
    require(baseline["total_mib"] - baseline["used_mib"] >= config["minimum_free_vram_mib"],
            "Free NVIDIA VRAM below the declared admission threshold.")
    vulkan = host["vulkan"].get("stdout", "")
    devices = re.split(r"(?m)^GPU(\d+):\s*$", vulkan)
    matches = [index for index, description in zip(devices[1::2], devices[2::2])
               if name in description and uuid.removeprefix("GPU-").lower() in description.lower()]
    require(len(matches) == 1, "Could not match Quadro UUID to a Vulkan device index.")
    return {"GGML_VK_VISIBLE_DEVICES": matches[0]}, ":".join(pci.lower().split(":")[-2:])


def verify_placement(state, log, config, pci):
    if config["backend"] == "CPU":
        require(state["backend"] == "CPU" and state["offloaded_layers"] == 0, "CPU zero-offload not established.")
        return
    placed = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", log)
    match = re.search(r"using device Vulkan[^\r\n]*Quadro P1000[^\r\n]*?(\d+) MiB free", log)
    state["physical_gpu_log"] = match[0] if match else None
    state["offload_evidence_log"] = list(map(int, placed[-1])) if placed else None
    require(match and pci in match[0].lower(), "Native log does not confirm the Quadro PCI device.")
    require(placed and placed[-1][0] == placed[-1][1] and int(placed[-1][0]) > 0, "Full offload not confirmed.")
    require(int(match[1]) >= config["minimum_free_vram_mib"], "Free native Vulkan budget below declared threshold.")


def run_block(out, cfg, manifest_sha, cases, host):
    cid = cfg["id"]
    baseline = gpu()
    ready = {"config_id": cid, "baseline_gpu": baseline, "system_cpu_before_percent": psutil.cpu_percent(interval=1),
             "started_utc": now(), "ac_power": ac_connected(), "status": "preflight"}
    path = out / "readiness" / (cid + ".json")
    process = monitor = case_id = None
    try:
        require(ready["ac_power"], "AC power required.")
        options, pci = vulkan_options(host, baseline, cfg) if cfg["backend"] == "Vulkan" else ({}, None)
        ready.update(options)
        ready["status"] = "load"
        process = Worker(out, cfg, {"PYTHONIOENCODING": "utf-8", **options})
        monitor = LaptopMonitor(process.process.pid)
        require(process.request("echo", text="café") == "café", "UTF-8 transport probe failed.")
        state = process.request("load")
        ready.update(state=state, load_memory=monitor.finish())
        verify_placement(state, process.log_path.read_text(encoding="utf-8", errors="replace"), cfg, pci)
        ready["status"] = "warmup"
        atomic(path, ready)
        monitor.reset()
        warmup = process.request("generate", user=user_prompt(SYNTHETIC))
        ready["warmup"] = warmup
        atomic(path, ready)
        ready["warmup_memory"] = monitor.finish()
        require(warmup["status"] == 0 and warmup["output_tokens"] > 0, "Technical warmup failure.")
        if pci:
            peak = ready["warmup_memory"]["device_vram_peak_mib"]
            require(peak is not None and baseline["total_mib"] - peak >= 256,
                    "Warmup left less than 256 MiB of NVIDIA device headroom or telemetry was unavailable.")
        ready["status"] = "ready"
        atomic(path, ready)
        print(f"{cid} ready {state}", flush=True)
        for index, case in enumerate(cases, 1):
            case_id = case["id"]
            require(ac_connected(), "Lost AC power before sending case.")
            prompt = user_prompt(case)
            identity = {"case_id": case_id, "config_id": cid, "index": index, "attempt": 1,
                        "manifest_sha256": manifest_sha, "model_sha256": cfg["model_sha256"],
                        "user_prompt_sha256": digest(prompt), "started_utc": now()}
            append(out / "attempts" / f"{cid}.jsonl", identity)
            monitor.reset()
            start = perf_counter()
            try:
                answer = process.request("generate", user=prompt)
            except Exception as error:
                answer = {"status": -999, "error": repr(error), "finish_reason": "technical_error", "raw_response": ""}
            append(out / "raw" / f"{cid}.jsonl",
                   {**identity, **answer, "request_seconds": perf_counter() - start})
            append(out / "telemetry" / f"{cid}.jsonl",
                   {**identity, "response_sha256": digest(answer["raw_response"]), "memory": monitor.finish()})
            require(answer["status"] == 0, f"Native generation failed: {answer['error']}")
            print(f"{cid} {index}/{len(cases)} {case_id} {answer['native_seconds']:.2f}s", flush=True)
    except Exception as error:
        failure = {"config_id": cid, "case_id": case_id, "stage": ready["status"], "error": repr(error), "utc": now()}
        append(out / "failures.jsonl", failure)
        ready["failure"] = failure
        atomic(path, ready)
        print(f"{cid}: {failure}", flush=True)
    finally:
        if monitor is not None:
            monitor.close()
        if process is not None:
            process.close()


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def csv_file(path, records):
    require(records, f"No rows for {path.name}.")
    keys = dict.fromkeys(key for record in records for key in record)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        writer.writerows(records)


def report(out, manifest):
    individual = []
    blocks = []
    failures = rows(out / "failures.jsonl")
    for cfg in manifest["configurations"]:
        cid = cfg["id"]
        raw = rows(out / "raw" / f"{cid}.jsonl")
        attempts = rows(out / "attempts" / f"{cid}.jsonl")
        telemetry = {r["case_id"]: r for r in rows(out / "telemetry" / f"{cid}.jsonl")}
        path = out / "readiness" / f"{cid}.json"
        ready = read_json(path) if path.exists() else {}
        state = ready.get("state", {})
        baseline = ready.get("baseline_gpu", {}).get("used_mib")
        memories = [ready.get(k, {}) for k in ("load_memory", "warmup_memory")]
        require([r["case_id"] for r in attempts] == [r["id"] for r in manifest["selection"]][:len(attempts)],
                f"Unexpected case order or duplicate attempts in {cid}.")
        require([r["case_id"] for r in raw] == [r["case_id"] for r in attempts][:len(raw)],
                f"Unexpected RAW coverage in {cid}.")
        ok = []
        for row in raw:
            metrics = {k: v for k, v in row.items() if k != "raw_response"}
            sample = telemetry.get(row["case_id"], {})
            if sample:
                require(sample["response_sha256"] == digest(row["raw_response"]), f"RAW and telemetry mismatch: {cid}.")
            memory = sample.get("memory", {})
            memories.append(memory)
            metrics.update({k: v for k, v in memory.items() if not isinstance(v, list)})
            metrics.update({"baseline_vram_mib": baseline,
                            "decode_tokens_per_second": ratio(row, "decoded_tokens", "decode_seconds"),
                            "output_tokens_per_second": ratio(row, "output_tokens", "native_seconds")})
            individual.append(metrics)
            if metrics["status"] == 0:
                ok.append(metrics)
        summary = {"config_id": cid, "requested_backend": cfg["backend"], "backend": state.get("backend"),
                   "device": state.get("device"), "gpu_layers": state.get("offloaded_layers") if not state.get(
                       "offload_evidence_log") else state["offload_evidence_log"][0],
                   "planned": manifest["case_count"], "attempted": len(attempts), "successful": len(ok),
                   "length_finishes": sum(r["finish_reason"] == "length" for r in ok),
                   "failures": " | ".join(f["error"] for f in failures if f["config_id"] == cid),
                   "load_seconds": state.get("load_seconds"), "warmup_seconds": ready.get("warmup", {}).get("native_seconds"),
                   "baseline_vram_mib": baseline, "cpu_percent_before_block": ready.get("system_cpu_before_percent")}
        for field in ("native_seconds", "prompt_seconds", "decode_seconds", "output_tokens", "prompt_tokens",
                      "decode_tokens_per_second", "output_tokens_per_second"):
            values = [r[field] for r in ok if r.get(field) is not None]
            for name, stat in (("median", statistics.median), ("mean", statistics.fmean), ("min", min), ("max", max)):
                summary[f"{field}_{name}"] = stat(values) if values else None
        for field, stat in (("worker_rss_peak_bytes", max), ("worker_private_peak_bytes", max),
                            ("system_available_min_bytes", min), ("device_vram_peak_mib", max),
                            ("gpu_temperature_max_c", max), ("gpu_utilization_max_percent", max)):
            values = [m[field] for m in memories if m.get(field) is not None]
            summary[field] = stat(values) if values else None
        counts = Counter(bool(s["ac_power"]) for m in memories for s in m.get("system_samples", []))
        summary["ac_samples"], summary["battery_samples"] = counts[True], counts[False]
        samples = [s["cpu_percent"] for m in memories for s in m.get("system_samples", [])]
        summary["maximum_system_cpu_percent"] = max(samples, default=None)
        blocks.append(summary)
    if individual:
        csv_file(out / "cases.csv", individual)
    csv_file(out / "summary.csv", blocks)
    atomic(out / "completion.json", {"completed_utc": now(), "manifest_sha256": sha(out / "manifest.json"),
                                     "blocks": blocks, "failures": len(failures)})


def ratio(row, numerator, denominator):
    return row[numerator] / row[denominator] if row.get(denominator, 0) > 0 else None


def run(out):
    manifest = read_json(out / "manifest.json")
    require(sha(__file__) == manifest["runner_sha256"], "Runner differs from the prepared manifest.")
    require(sha(SOURCE) == manifest["source_sha256"] == EXPECTED_SOURCE_SHA, "Development source SHA mismatch.")
    require(sha(FROZEN) == manifest["frozen_manifest_sha256"] == EXPECTED_FROZEN_SHA, "Frozen manifest SHA mismatch.")
    require(sha(out / manifest["subset"]) == manifest["subset_sha256"], "Subset SHA mismatch.")
    cases = read_json(out / manifest["subset"])
    require(len(cases) == 15 and [c["id"] for c in cases] == [r["id"] for r in manifest["selection"]]
            and all(c.keys() == {"id", "level", "task", "student_text"} for c in cases), "Invalid worker subset.")
    assets = []
    for binding in manifest["source_bindings"]:
        path = LAB / binding["path"]
        require(path.is_file() and sha(path) == binding["sha256"], f"Missing or mismatched asset {binding}.")
        assets.append(binding)
    models = {c["model_path"]: c for c in manifest["configurations"]}
    for model, cfg in models.items():
        path = LAB / model
        require(path.is_file() and path.stat().st_size == cfg["model_bytes"] and sha(path) == cfg["model_sha256"],
                f"Missing or mismatched {model}, expected {cfg['model_sha256']}")
        assets.append({"path": model, "sha256": cfg["model_sha256"], "bytes": cfg["model_bytes"]})
    for cfg in manifest["configurations"]:
        require(digest(cfg["system_prompt"]) == cfg["system_prompt_sha256"], "Prompt SHA mismatch.")
    require(ac_connected(), "Connect AC power before starting inference.")
    with (out / "run.started").open("x", encoding="utf-8") as marker:
        marker.write(now() + "\n")
        marker.flush()
        os.fsync(marker.fileno())
    atomic(out / "verified_assets.json", assets)
    kernel = ctypes.windll.kernel32
    kernel.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
    kernel.SetThreadExecutionState.restype = ctypes.c_uint32
    require(kernel.SetThreadExecutionState(0x80000001), "Could not request sleep inhibition.")
    try:
        host = read_json(out / "host.json")
        for config in manifest["configurations"]:
            run_block(out, config, sha(out / "manifest.json"), cases, host)
    finally:
        kernel.SetThreadExecutionState(0x80000000)
        report(out, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--worker")
    args = parser.parse_args()
    out = args.out.resolve()
    if args.worker:
        worker(out / "manifest.json", args.worker)
    elif args.prepare:
        prepare(out)
    else:
        run(out)


if __name__ == "__main__":
    main()
