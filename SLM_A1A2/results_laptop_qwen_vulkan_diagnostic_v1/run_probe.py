"""Run a single isolated Qwen/Vulkan diagnostic against the exact tested DLLs."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
LAB = OUT.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(LAB))
from run_finalists_200 import Monitor, atomic, gpu, now, read_json, sha

NATIVE = LAB / "cross_demo/native/artifacts/b12359/win-x64"
MODEL = LAB / "models/Qwen3.5-4B-Q4_K_M.gguf"
MANIFEST = LAB / "manifests/finalists_200_20261117.json"
SCENARIOS = {
    "16-layers-mmap": (16, "mmap", {}),
    "32-layers-mmap": (32, "mmap", {}),
    "full-buffered": (-1, "none", {}),
    "full-mmap-smaller-blocks": (-1, "mmap", {"GGML_VK_SUBALLOCATION_BLOCK_SIZE": str(512 * 1024**2)}),
    "full-mmap-block1-cpu": (-1, "mmap", {}),
}
TIMEOUT = 85
GPU_UUID = "GPU-5cdc728c-e00e-b190-607b-b7947dc93773"


def run(executable, scenario):
    layers, mode, settings = SCENARIOS[scenario]
    cpu_pattern = r"^blk\.1\." if scenario == "full-mmap-block1-cpu" else None
    source = OUT / ("probe.cpp" if cpu_pattern else "probe_initial.cpp")
    manifest = read_json(MANIFEST)
    qwen = next(c for c in manifest["configurations"] if c["model_id"] == "portable-unsloth-qwen35-4b-q4-k-m")
    observed = {}
    for item in manifest["source_bindings"]:
        name = item["path"].rsplit("\\", 1)[1]
        if item["path"].endswith(f"win-x64\\{name}") and name.endswith(".dll"):
            actual = sha(NATIVE / name)
            if actual != item["sha256"]:
                raise ValueError(f"Mismatched DLL {name}: {actual}")
            observed[name] = actual
    if len(observed) != 7 or MODEL.stat().st_size != qwen["model_bytes"] or sha(MODEL) != qwen["model_sha256"]:
        raise ValueError("The exact seven DLLs and Qwen GGUF are required.")
    baseline = gpu()
    if baseline.get("uuid") != GPU_UUID or baseline["total_mib"] != 4096:
        raise ValueError(f"Unexpected NVIDIA adapter: {baseline}")
    if layers < 0 and baseline["total_mib"] - baseline["used_mib"] < 3500:
        raise ValueError(f"Less than 3500 MiB of free VRAM for full-load diagnostic: {baseline}")

    folder = OUT / scenario
    folder.mkdir()
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GGML_VK_")}
    environment["PATH"] = str(NATIVE) + os.pathsep + environment.get("PATH", "")
    variables = {"GGML_VK_VISIBLE_DEVICES": "1", **settings}
    record = {
        "started_utc": now(), "context": 2048, "gpu_layers": layers, "load_mode": mode,
        "cpu_tensor_override": cpu_pattern,
        "environment": variables, "baseline_gpu": baseline, "timeout_seconds": TIMEOUT,
        "gguf_sha256": qwen["model_sha256"], "dll_sha256": observed,
        "probe_source_sha256": sha(source), "probe_executable_sha256": sha(executable),
    }
    atomic(folder / "attempt.json", record)
    command = [str(executable), str(NATIVE), str(MODEL), str(layers), mode]
    if cpu_pattern is not None:
        command.append(cpu_pattern)
    with (folder / "progress.log").open("xb") as output, (folder / "native.log").open("xb") as error:
        start = time.perf_counter()
        with subprocess.Popen(command,
                              cwd=OUT, stdout=output, stderr=error, env={**environment, **variables},
                              creationflags=subprocess.CREATE_NO_WINDOW) as process:
            monitor = Monitor(process.pid)
            timed_out = False
            try:
                process.wait(max(0.1, TIMEOUT - (time.perf_counter() - start)))
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait(10)
            finally:
                measurements = monitor.finish()
                monitor.close()
            result = {**record, "ended_utc": now(), "elapsed_seconds": time.perf_counter() - start,
                      "exit_code": process.returncode, "timed_out": timed_out, "measurements": measurements}
    atomic(folder / "result.json", result)
    print((folder / "progress.log").read_text(encoding="utf-8", errors="replace"))
    print(f"exit_code={result['exit_code']} timeout={timed_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("scenario", choices=SCENARIOS)
    args = parser.parse_args()
    run(args.executable.resolve(strict=True), args.scenario)
