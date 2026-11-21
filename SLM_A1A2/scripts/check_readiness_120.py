"""Single-synthetic-probe readiness check for the 16 dev-120 configs.

ONE server at a time, exact ONE generation per config, sequential, single
launch attempt: failures are recorded, never retried, never fallen back
(-ngl stays 999). A 429 response aborts the ENTIRE run immediately.
Single-config runs are load/render diagnostics only. Full runs require an
unspent synthetic generation budget; the four explicit non-thinking repetitions
are bounded by an exact pinned human authorization and permanent claims.

Gate order per config (generation is the last step, never wasted):
  1. manifest status must be "verified" (else not_ready_unverified, no spawn)
  2. own port must be free (else port_busy, no spawn, nothing killed)
  3. spawn; prompt child-exit detect during load (else load_failed)
  4. /health must answer HTTP 200 with body status "ok" (else health_failed)
  5. /apply-template native render of the synthetic probe must succeed
     (else not_ready_template); rendered prompt is then really tokenized
     via /tokenize (tokenization OF the render, not a template fingerprint)
  6. CUDA + offload evidence must appear in loading stdout
     (else not_ready_offload)
  7. exact ONE /v1/chat/completions (manifest generation, max_tokens=512)
     with reasoning_budget_tokens=0; nonempty reasoning_content fails readiness.

Reads:  manifests/experiment_manifest_120.json (never any benchmark file).
Writes: logs/readiness/<config>.{server.log,request.json,response.json,render.json}
        logs/readiness_120.json (detailed, no benchmark content)
        llama_cpp_readiness_report.json {manifest_sha256, configs:[...]}
        llama_cpp_readiness_report.md (measured table)

Shared helpers are import-safe for the future benchmark runner: importing
this module performs no I/O and no inference.

Usage (authorized synthetic readiness only; never the main benchmark):
  .venv/Scripts/python.exe scripts/check_readiness_120.py [--config ID]
      [--load-timeout 600] [--request-timeout 300]
      [--repeat-authorization EXACT_APPROVED_RECORD]
"""
import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from readiness_generation_guard import load_authorization, check_budget, claim_generation

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(LAB, "manifests", "experiment_manifest_120.json")

# The ONLY text this script ever sends. Synthetic, technical, unrelated to
# any benchmark case. This module never opens benchmark_*.json / drafts.
SYNTHETIC_PROBE_TEXT = "He go to school every day."

ST_READY = "ready"
ST_UNVERIFIED = "not_ready_unverified"
ST_SKIPPED_MISSING = "skipped_missing"
ST_PORT_BUSY = "port_busy"
ST_LOAD_FAILED = "load_failed"
ST_HEALTH_FAILED = "health_failed"
ST_TEMPLATE_FAILED = "not_ready_template"
ST_OFFLOAD_FAILED = "not_ready_offload"
ST_REQUEST_FAILED = "request_failed"
ST_ABORTED = "skipped_aborted_429"


class AbortRun(Exception):
    """HTTP 429 observed: stop everything, no retry."""


def forbid_benchmark(path):
    if "benchmark" in os.path.basename(path).lower():
        raise ValueError(f"refusing benchmark-adjacent path: {path}")
    return path


def load_manifest(path=MANIFEST):
    with open(forbid_benchmark(path), "rb") as fh:
        raw = fh.read()
    data = json.loads(raw)
    data['_loaded_sha256'] = hashlib.sha256(raw).hexdigest()
    cfgs = data.get("configurations", [])
    if len(cfgs) != 16 or len({c["id"] for c in cfgs}) != 16:
        raise ValueError("manifest must hold exactly 16 unique configs")
    # Reuse the import-safe runner contract, including mandatory non-thinking
    # launch flags and a zero request budget, before any server can start.
    if LAB not in sys.path:
        sys.path.insert(0, LAB)
    from run_benchmark_120 import validate_manifest
    validate_manifest(data)
    return data


def manifest_sha256(path=MANIFEST):
    digest = __import__("hashlib").sha256()
    with open(forbid_benchmark(path), "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def http_call(method, url, payload=None, timeout=30):
    """Returns (http_code|None, body|None, error|None). Exact codes preserved."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            code = resp.status
    except urllib.request.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:1000]
        except Exception:
            detail = ""
        return exc.code, None, f"HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa - recorded truthfully by callers
        return None, None, f"{type(exc).__name__}: {exc}"
    try:
        return code, json.loads(raw), None
    except ValueError:
        return code, {"_raw": raw[:4000]}, None


def port_free(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def start_server(command, cwd, log_path):
    """Launch our child with an exclusive new log; preserve earlier attempt evidence."""
    log_fh = open(log_path, "x", encoding="utf-8")
    proc = subprocess.Popen(command, cwd=cwd, stdout=log_fh, stderr=subprocess.STDOUT)
    return proc, log_fh


def stop_server(proc, log_fh, grace_s=20):
    """Terminate ONLY our own child. If already exited, just reap. Returns info."""
    info = {"pid": proc.pid, "exit_code": proc.poll(), "forced_kill": False,
            "already_exited": proc.poll() is not None}
    if proc.poll() is None:
        proc.terminate()
        try:
            info["exit_code"] = proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            info["exit_code"] = proc.wait(timeout=30)
            info["forced_kill"] = True
    log_fh.close()
    return info


def ram_snapshot():
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {"total_gb": round(vm.total / 1e9, 2),
                "available_gb": round(vm.available / 1e9, 2)}
    except ImportError:
        return {"total_gb": None, "available_gb": None, "note": "psutil missing"}


def vram_snapshot():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    if out.returncode != 0:
        return {"error": out.stderr.strip()[:300]}
    try:
        used, total = [p.strip() for p in out.stdout.strip().split(",")]
        return {"used_mib": int(used), "total_mib": int(total)}
    except ValueError:
        return {"error": out.stdout.strip()[:300]}


class PeakMonitor(threading.Thread):
    """Sample own-child RSS + device VRAM; peaks only. Device VRAM is
    device-wide (all processes), labelled as such, never attributed per-proc."""

    def __init__(self, pid, interval_s=0.5):
        super().__init__(daemon=True)
        self.pid = pid
        self.interval_s = interval_s
        self.stop_flag = threading.Event()
        self.rss_peak_mib = None
        self.vram_peak_mib = None

    def run(self):
        try:
            import psutil
            handle = psutil.Process(self.pid)
        except ImportError:
            handle = None
        while not self.stop_flag.is_set():
            if handle is not None:
                try:
                    rss = handle.memory_info().rss / (1024 * 1024)
                    if self.rss_peak_mib is None or rss > self.rss_peak_mib:
                        self.rss_peak_mib = round(rss, 1)
                except Exception:
                    pass
            vm = vram_snapshot()
            if isinstance(vm.get("used_mib"), int):
                if self.vram_peak_mib is None or vm["used_mib"] > self.vram_peak_mib:
                    self.vram_peak_mib = vm["used_mib"]
            self.stop_flag.wait(self.interval_s)

    def stop(self):
        self.stop_flag.set()
        self.join(timeout=10)
        return {"server_rss_peak_mib": self.rss_peak_mib,
                "device_vram_peak_mib": self.vram_peak_mib,
                "vram_note": "device-wide across all processes, not per-model"}


def read_log_tail(path, max_chars=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_chars) if max_chars is not None else 0)
            return fh.read()
    except OSError as exc:
        return f"<unreadable log: {exc}>"


def scan_offload_evidence(log_text):
    """Array of loading-stdout evidence lines. Empty arrays gate generation off."""
    layers, cuda = [], []
    for line in log_text.splitlines():
        low = line.lower()
        if "offload" in low and "layer" in low:
            layers.append(line.strip()[:300])
        if ("cuda" in low or "cublas" in low or "ggml-cuda" in low
                or "n_gpu_layers" in low or "gpu layers" in low):
            cuda.append(line.strip()[:300])
    m = re.search(r"offloaded\s+(\d+)\s*/\s*(\d+)\s*layers", log_text, re.IGNORECASE)
    return {"offload_lines": layers[:10],
            "cuda_lines": cuda[:10],
            "n_gpu_layers_reported": f"{m.group(1)}/{m.group(2)}" if m else None}


def check_health_strict(base_url, timeout_s, proc, interval_s=2.0):
    """HTTP 200 AND body status 'ok'. Child exit during wait -> load failure."""
    start = time.monotonic()
    last = {"code": None, "body": None}
    while time.monotonic() - start < timeout_s:
        if proc.poll() is not None:
            return ("exited", time.monotonic() - start, last)
        code, body, _ = http_call("GET", base_url + "/health", timeout=10)
        if code == 429:
            raise AbortRun("429 from /health")
        last = {"code": code, "body": body}
        if code == 200 and isinstance(body, dict) and str(body.get("status", "")).lower() == "ok":
            return ("ok", time.monotonic() - start, last)
        time.sleep(interval_s)
    return ("timeout", time.monotonic() - start, last)


def render_native(base_url, timeout_s):
    """POST /apply-template with the synthetic messages only (server applies
    its native GGUF template + configured kwargs). Returns (code, prompt|None, err)."""
    code, body, err = http_call("POST", base_url + "/apply-template",
                                {"messages": [{"role": "user",
                                               "content": SYNTHETIC_PROBE_TEXT}]},
                                timeout=timeout_s)
    if err is not None:
        if code == 429:
            raise AbortRun("429 from /apply-template")
        return code, None, err
    prompt = body.get("prompt") if isinstance(body, dict) else None
    if not prompt:
        return code, None, f"empty prompt (code {code})"
    return code, prompt, None


def tokenize_rendered(base_url, prompt, timeout_s):
    """Tokenize the RENDERED prompt: real tokenization of renderer output."""
    code, body, err = http_call("POST", base_url + "/tokenize",
                                {"content": prompt}, timeout=timeout_s)
    if err is not None:
        if code == 429:
            raise AbortRun("429 from /tokenize")
        return None, err
    toks = body.get("tokens") if isinstance(body, dict) else None
    return toks, None


def verify_model_file(path, expected_sha256):
    """Rehash the actual model immediately before launch and require stable bytes."""
    before = os.stat(path)
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(chunk)
    after = os.stat(path)
    stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return stable and digest.hexdigest() == expected_sha256, {
        'sha256': digest.hexdigest(), 'bytes': after.st_size, 'stable_during_hash': stable}


def run_config_check(cfg, args, out_dir, expected_render_sha256=None, allow_generation=True):
    """One config, one launch attempt, exact ONE generation. No retry/fallback."""
    cid, port = cfg["id"], cfg["port"]
    res = {"config_id": cfg["config_id"], "id": cid, "quant": cfg["quant"],
           "port": port, "model_sha256": cfg.get("model_sha256"),
           "status": None, "measured": {}}
    me = res["measured"]
    if cfg["gguf"]["status"] == "missing":
        res["status"] = ST_SKIPPED_MISSING
        return res
    if cfg["gguf"]["status"] != "verified" or not cfg.get("model_sha256"):
        res["status"] = ST_UNVERIFIED
        me["reason"] = (f"gguf status={cfg['gguf']['status']}; "
                        "present-without-record is never ready")
        return res
    if not port_free(port):
        res["status"] = ST_PORT_BUSY
        me["reason"] = f"port {port} already bound; refusing to spawn or kill"
        return res

    server_exe = os.path.join(LAB, *cfg["runtime"]["server"].split("/"))
    if not os.path.isfile(server_exe):
        res["status"] = ST_LOAD_FAILED
        me["reason"] = f"missing binary: {server_exe}"
        return res
    valid_runtime, runtime_evidence = verify_model_file(server_exe, cfg['runtime'].get('server_sha256'))
    me['prelaunch_server_verification'] = runtime_evidence
    if not valid_runtime:
        res['status'] = ST_UNVERIFIED
        me['reason'] = 'server binary differs from pinned runtime hash'
        return res
    command = [(server_exe if t == cfg["runtime"]["server"] else t)
               for t in cfg["server_command"]]
    gguf_abs = (cfg["model_path"] if len(cfg["model_path"]) > 1 and cfg["model_path"][1] == ":"
                else os.path.join(LAB, *cfg["model_path"].split("/")))
    try:
        valid, evidence = verify_model_file(gguf_abs, cfg['model_sha256'])
        me['prelaunch_model_verification'] = evidence
    except OSError as exc:
        valid = False
        me['reason'] = f'prelaunch asset verification failed: {exc}'
    if not valid:
        res['status'] = ST_UNVERIFIED
        me.setdefault('reason', 'actual model hash differs from manifest or file changed during hashing')
        return res
    command = [(gguf_abs if t == cfg["model_path"] else t) for t in command]
    server_log = os.path.join(out_dir, f"{cid}.server.log")

    me["ram_before"] = ram_snapshot()
    me["vram_before_mib"] = vram_snapshot()
    proc, log_fh = start_server(command, LAB, server_log)
    me["server_pid"] = proc.pid
    monitor = PeakMonitor(proc.pid)
    monitor.start()
    base = f"http://127.0.0.1:{port}"
    try:
        outcome, elapsed, last = check_health_strict(base, args.load_timeout, proc)
        me["load_wait_s"] = round(elapsed, 1)
        if outcome == "exited":
            res["status"] = ST_LOAD_FAILED
            me["exit_code"] = proc.poll()
            me["health_last"] = last
            me["offload"] = scan_offload_evidence(read_log_tail(server_log))
            return res
        if outcome != "ok":
            res["status"] = ST_HEALTH_FAILED
            me["health_last"] = last
            me["offload"] = scan_offload_evidence(read_log_tail(server_log))
            return res
        me["health"] = last

        try:
            code, prompt, err = render_native(base, args.request_timeout)
        except AbortRun:
            raise
        me["render_http_code"] = code
        if err is not None or not prompt:
            res["status"] = ST_TEMPLATE_FAILED
            me["render_error"] = err
            return res
        me["rendered_prompt_chars"] = len(prompt)
        me["rendered_prompt_sha256"] = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        if expected_render_sha256 and me['rendered_prompt_sha256'] != expected_render_sha256:
            res['status'] = ST_TEMPLATE_FAILED
            me['render_error'] = 'native synthetic render differs within declared quantization comparison group; no generation spent'
            return res
        with open(os.path.join(out_dir, f"{cid}.render.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"prompt": prompt}, fh, indent=2)
        toks, tok_err = tokenize_rendered(base, prompt, args.request_timeout)
        me["rendered_tokens"] = toks
        me["rendered_tokenize_error"] = tok_err
        if tok_err is not None or not isinstance(toks, list) or not toks:
            res["status"] = ST_TEMPLATE_FAILED
            me["render_error"] = "rendered prompt tokenization failed or returned no tokens"
            return res

        me["offload"] = scan_offload_evidence(read_log_tail(server_log))
        layer_counts = me['offload'].get('n_gpu_layers_reported')
        nonzero_layers = bool(layer_counts and int(layer_counts.split('/')[0]) > 0)
        if not me["offload"]["cuda_lines"] or not nonzero_layers:
            res["status"] = ST_OFFLOAD_FAILED
            me["reason"] = "missing CUDA or positive measured GPU-layer offload; no probe spent"
            return res
        if not allow_generation:
            res['status'] = 'diagnostic_load_render_only'
            me['diagnostic_only'] = True
            me['reason'] = 'single-config diagnostics spend no generation and cannot approve the full matrix'
            return res

        payload = {"messages": [{"role": "user", "content": SYNTHETIC_PROBE_TEXT}],
                   "max_tokens": cfg["generation"]["max_tokens"],
                   "seed": cfg["generation"]["seed"], "stream": False,
                   "temperature": cfg["generation"]["temperature"],
                   "top_p": cfg["generation"]["top_p"],
                   "top_k": cfg["generation"]["top_k"],
                   "min_p": cfg["generation"]["min_p"],
                   "repeat_penalty": cfg["generation"]["repeat_penalty"],
                   "presence_penalty": cfg["generation"]["presence_penalty"],
                   "frequency_penalty": cfg["generation"]["frequency_penalty"]}
        payload['reasoning_budget_tokens'] = cfg['generation']['reasoning_budget_tokens']
        if hasattr(args, '_generation_guard'):
            if manifest_sha256() != args._manifest_sha256:
                raise ValueError('manifest changed before generation; refusing request')
            me['generation_claim'] = claim_generation(
                LAB, cid, args._generation_guard, args._manifest_sha256, out_dir)
        with open(os.path.join(out_dir, f"{cid}.request.json"), "x",
                  encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        t0 = time.monotonic()
        code, data, err = http_call("POST", base + "/v1/chat/completions",
                                   payload, timeout=args.request_timeout)
        me["infer_elapsed_s"] = round(time.monotonic() - t0, 2)
        me["completion_http_code"] = code
        with open(os.path.join(out_dir, f"{cid}.response.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"http_code": code, "data": data, "error": err}, fh, indent=2)
        if code == 429:
            raise AbortRun("429 from /v1/chat/completions")
        if err is not None or not isinstance(data, dict):
            res["status"] = ST_REQUEST_FAILED
            me["request_error"] = err or f"unexpected shape (code {code})"
            return res
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", {})
        except (KeyError, IndexError, TypeError):
            res["status"] = ST_REQUEST_FAILED
            me["request_error"] = f"unexpected response shape (code {code})"
            return res
        me["completion_chars"] = len(content or "")
        reasoning = choice['message'].get('reasoning_content') or ''
        me['reasoning_content_chars'] = len(reasoning) if isinstance(reasoning, str) else None
        me["prompt_tokens"] = usage.get("prompt_tokens")
        me["completion_tokens"] = usage.get("completion_tokens")
        me["finish_reason"] = choice.get("finish_reason")
        if not isinstance(reasoning, str) or reasoning.strip():
            res['status'] = ST_REQUEST_FAILED
            me['request_error'] = 'non-thinking contract violated: reasoning_content is nonempty or malformed'
        elif (content or "").strip():
            res["status"] = ST_READY
        else:
            res["status"] = ST_REQUEST_FAILED
            me["request_error"] = "empty completion"
        return res
    finally:
        me["peaks"] = monitor.stop()
        me["ram_after"] = ram_snapshot()
        me["vram_after_mib"] = vram_snapshot()
        me["server"] = stop_server(proc, log_fh)


def write_markdown(results, path):
    lines = ["# llama.cpp readiness report — development_120",
             "",
             "One synthetic technical probe per config "
             f"(`{SYNTHETIC_PROBE_TEXT}`); no benchmark content involved. "
             "Single launch attempt each; exact one generation per ready-gated "
             "config; failures recorded, never retried; -ngl never lowered.",
             "",
             "| config | status | load_s | infer_s | toks_in/out | finish | "
             "gpu_layers | rss_peak_MiB | vram_peak_MiB(device) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        d = r.get("measured", {})
        pk = d.get("peaks") or {}
        toks = f"{d.get('prompt_tokens')}/{d.get('completion_tokens')}"
        lines.append(f"| {r['id']} | {r['status']} | {d.get('load_wait_s')} | "
                     f"{d.get('infer_elapsed_s')} | {toks} | "
                     f"{d.get('finish_reason')} | "
                     f"{(d.get('offload') or {}).get('n_gpu_layers_reported')} | "
                     f"{pk.get('server_rss_peak_mib')} | "
                     f"{pk.get('device_vram_peak_mib')} |")
    lines += ["", "## Per-config evidence (gates, errors, render)", ""]
    for r in results:
        d = r.get("measured", {})
        lines.append(f"### {r['config_id']} — {r['status']}")
        for key in ("reason", "request_error", "render_error",
                    "rendered_tokenize_error", "exit_code"):
            if d.get(key) is not None:
                lines.append(f"- {key}: `{json.dumps(d[key])[:400]}`")
        for key in ("health_last",):
            if d.get(key) is not None:
                lines.append(f"- {key}: `{json.dumps(d[key])[:400]}`")
        off = d.get("offload") or {}
        for ln in (off.get("offload_lines") or [])[:3]:
            lines.append(f"- log: `{ln}`")
        for ln in (off.get("cuda_lines") or [])[:2]:
            lines.append(f"- log: `{ln}`")
        if d.get("rendered_prompt_chars") is not None:
            lines.append(f"- native render chars: {d['rendered_prompt_chars']}; "
                         f"rendered tokens: `{json.dumps(d.get('rendered_tokens'))[:300]}`")
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None,
                    help="single config id; reruns are diagnostic only, never main inference")
    ap.add_argument("--load-timeout", type=float, default=600)
    ap.add_argument("--request-timeout", type=float, default=300)
    ap.add_argument('--repeat-authorization', help='pinned human authorization for exactly four non-thinking repetitions')
    ap.add_argument("--out-dir", default=os.path.join(LAB, 'logs', 'readiness'),
                    help='new technical attempt directory; preserve logs and enforce pinned generation budgets')
    args = ap.parse_args()

    manifest = load_manifest()
    configs = manifest["configurations"]
    try:
        args._generation_guard = load_authorization(args.repeat_authorization, manifest['_loaded_sha256'], configs)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'readiness authorization rejected: {exc}', file=sys.stderr)
        return 2
    args._manifest_sha256 = manifest['_loaded_sha256']
    if args.config:
        configs = [c for c in configs if c["id"] == args.config]
        if not configs:
            print(f"unknown config: {args.config}", file=sys.stderr)
            return 2

    out_dir = os.path.abspath(args.out_dir)
    if not out_dir.startswith(os.path.join(LAB, 'logs') + os.sep):
        print('readiness output directory must remain under lab/logs', file=sys.stderr)
        return 2
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(LAB, "logs", "servers"), exist_ok=True)
    for cfg in configs:
        if not args.config:
            try:
                check_budget(LAB, cfg['id'], args._generation_guard)
            except (ValueError, OSError) as exc:
                print(f'readiness budget rejected: {exc}', file=sys.stderr)
                return 2
        if os.path.exists(os.path.join(out_dir, cfg['id'] + '.server.log')):
            print(f"refusing stale attempt log for {cfg['id']}; choose a fresh technical attempt directory", file=sys.stderr)
            return 2
    results, aborted = [], False
    group_renders = {}
    stopped_on_failure = False
    for cfg in configs:  # strictly sequential; one server at a time
        if manifest_sha256() != manifest['_loaded_sha256']:
            results.append({'config_id': cfg['config_id'], 'id': cfg['id'],
                            'quant': cfg['quant'], 'port': cfg['port'],
                            'model_sha256': cfg['model_sha256'], 'status': ST_UNVERIFIED,
                            'measured': {'reason': 'manifest changed during readiness'}})
            stopped_on_failure = True
            break
        print(f"[{cfg['id']}] probing ...", flush=True)
        try:
            group = cfg['template_comparison_group']
            res = run_config_check(cfg, args, out_dir, group_renders.get(group), allow_generation=not args.config)
        except AbortRun as exc:
            print(f"[{cfg['id']}] 429 -> aborting entire run ({exc})")
            aborted = True
            break
        except (ValueError, OSError) as exc:
            res = {'config_id': cfg['config_id'], 'id': cfg['id'],
                   'quant': cfg['quant'], 'port': cfg['port'],
                   'model_sha256': cfg['model_sha256'], 'status': ST_REQUEST_FAILED,
                   'measured': {'reason': f'fail-closed technical guard: {exc}'}}
        print(f"[{cfg['id']}] -> {res['status']}")
        results.append(res)
        if res['status'] == ST_READY:
            group_renders[group] = res['measured']['rendered_prompt_sha256']
        if res["status"] != ST_READY:
            stopped_on_failure = True
            break
    if aborted or stopped_on_failure:
        done = {r["id"] for r in results}
        for cfg in configs:
            if cfg["id"] not in done:
                results.append({"config_id": cfg["config_id"], "id": cfg["id"],
                                "quant": cfg["quant"], "port": cfg["port"],
                                "model_sha256": cfg.get("model_sha256"),
                                "status": ST_ABORTED if aborted else "skipped_after_readiness_failure", "measured": {}})

    import datetime as _dt
    manifest_unchanged = manifest_sha256() == manifest['_loaded_sha256']
    if not manifest_unchanged:
        for result in results:
            if result['status'] == ST_READY:
                result['status'] = ST_UNVERIFIED
                result['measured']['reason'] = 'manifest changed during readiness; original snapshot retained'
    report = {"manifest_sha256": manifest['_loaded_sha256'],
              "manifest_unchanged_during_readiness": manifest_unchanged,
              "generated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
              "probe": SYNTHETIC_PROBE_TEXT,
              "probe_max_tokens": 512,
              "aborted_on_429": aborted,
              "stopped_on_failure": stopped_on_failure,
              "native_template_group_render_sha256": group_renders,
              "repeat_authorization": ({'path': args._generation_guard['path'], 'sha256': args._generation_guard['sha256']} if args._generation_guard else None),
              "configs": results}
    detailed_path = os.path.join(out_dir, 'diagnostic_readiness.json') if args.config else os.path.join(LAB, 'logs', 'readiness_120.json')
    with open(detailed_path, "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    slim = {"manifest_sha256": report["manifest_sha256"],
            "repeat_authorization": report['repeat_authorization'],
            "complete_matrix": len(results) == 16 and not args.config and manifest_unchanged and all(r['status'] == ST_READY for r in results),
            "generated_utc": report["generated_utc"],
            "configs": [{"config_id": r["config_id"], "id": r["id"],
                         "status": r["status"],
                         "model_sha256": r.get("model_sha256"),
                         "port": r.get("port"),
                         "quant": r.get("quant"),
                         "finish_reason": (r.get("measured") or {}).get("finish_reason"),
                         "completion_tokens": (r.get("measured") or {}).get("completion_tokens"),
                         "device_vram_peak_mib": ((r.get("measured") or {}).get("peaks") or {}).get("device_vram_peak_mib")}
                        for r in results]}
    if args.config:
        for entry in slim['configs']:
            if entry['status'] == ST_READY:
                entry['status'] = 'diagnostic_only_not_full_matrix'
    slim_path = os.path.join(out_dir, 'diagnostic_readiness_slim.json') if args.config else os.path.join(LAB, 'llama_cpp_readiness_report.json')
    with open(slim_path, "w",
              encoding="utf-8") as fh:
        json.dump(slim, fh, indent=2)
    markdown_path = os.path.join(out_dir, 'diagnostic_readiness.md') if args.config else os.path.join(LAB, 'llama_cpp_readiness_report.md')
    write_markdown(results, markdown_path)
    bad = [r["id"] for r in results if r["status"] != ST_READY]
    print(f"ready={len(results) - len(bad)}/{len(results)}" +
          (f" not-ready: {bad}" if bad else ""))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
