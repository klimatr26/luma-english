import gc
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch
import transformers
from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText, AutoProcessor, AutoTokenizer

ROOT = Path(__file__).resolve().parent
BENCHMARK_PATH = ROOT / "benchmark_smoke_test_v2.json"
OUTPUT_DIR = ROOT / "benchmark_results_v2_rerun"
HF_HOME = ROOT / "hf_cache"
MAX_NEW_TOKENS = 2048
MAX_CONTEXT_TOKENS = 4096
DTYPE = torch.bfloat16

MODELS = [
    ("LFM2.5-350M", "LiquidAI/LFM2.5-350M", "models--LiquidAI--LFM2.5-350M", "causal"),
    ("LFM2.5-1.2B-Instruct", "LiquidAI/LFM2.5-1.2B-Instruct", "models--LiquidAI--LFM2.5-1.2B-Instruct", "causal"),
    ("LFM2.5-1.2B-Thinking", "LiquidAI/LFM2.5-1.2B-Thinking", "models--LiquidAI--LFM2.5-1.2B-Thinking", "causal"),
    ("Qwen3.5-0.8B", "Qwen/Qwen3.5-0.8B", "models--Qwen--Qwen3.5-0.8B", "multimodal"),
    ("Qwen3.5-2B", "Qwen/Qwen3.5-2B", "models--Qwen--Qwen3.5-2B", "multimodal"),
    ("MiniCPM5-1B", "openbmb/MiniCPM5-1B", "models--openbmb--MiniCPM5-1B", "causal"),
    ("MiniCPM5-2B", "openbmb/MiniCPM5-2B", "models--openbmb--MiniCPM5-2B", "causal"),
    ("Gemma 4 E2B QAT Mobile", "google/gemma-4-E2B-it-qat-mobile-transformers", "models--google--gemma-4-E2B-it-qat-mobile-transformers", "multimodal"),
]


def snapshot_for(cache_name):
    snapshots = sorted((HF_HOME / cache_name / "snapshots").iterdir())
    if len(snapshots) != 1:
        raise RuntimeError(f"Expected one local snapshot for {cache_name}; found {len(snapshots)}")
    return snapshots[0]


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def revision_metadata(snapshot):
    refs = list((snapshot.parent.parent / "refs").glob("*"))
    return {
        "revision": snapshot.name,
        "snapshot_path": str(snapshot),
        "config_sha256": file_sha256(snapshot / "config.json"),
        "weights": [
            {"file": path.name, "bytes": path.stat().st_size}
            for path in sorted(snapshot.glob("*.safetensors"))
        ],
        "refs": {ref.name: ref.read_text(encoding="utf-8").strip() for ref in refs},
    }


def balanced_json_span(text):
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return start, index + 1
        start = text.find("{", start + 1)
    return None


def parse_response(raw):
    span = balanced_json_span(raw)
    if span is None:
        return None, False, False
    start, end = span
    candidate = raw[start:end]
    try:
        parsed = json.loads(candidate)
    except Exception:
        return None, False, bool(raw[:start].strip() or raw[end:].strip())
    valid_whole = raw.strip() == candidate
    return parsed, valid_whole, bool(raw[:start].strip() or raw[end:].strip())


def has_repetition(text):
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if len(normalized) >= 160:
        for width in (24, 40, 60):
            if len(normalized) >= width * 3 and re.search(rf"(.{{{width}}})\1{{2,}}", normalized):
                return True
    tokens = normalized.split()
    if len(tokens) >= 24:
        for width in range(3, min(12, len(tokens) // 3) + 1):
            if tokens[-width:] == tokens[-2 * width:-width] == tokens[-3 * width:-2 * width]:
                return True
    return False


class MemoryMonitor:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.peak_rss = 0
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self):
        while not self.stop_event.is_set():
            try:
                self.peak_rss = max(self.peak_rss, self.process.memory_info().rss)
            except Exception:
                pass
            self.stop_event.wait(0.05)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()


def load_components(snapshot, family):
    config = AutoConfig.from_pretrained(snapshot, local_files_only=True)
    if family == "multimodal":
        processor = AutoProcessor.from_pretrained(snapshot, local_files_only=True)
        tokenizer = processor.tokenizer if hasattr(processor, "tokenizer") else AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
        model = AutoModelForImageTextToText.from_pretrained(
            snapshot,
            local_files_only=True,
            device_map="auto",
            dtype="auto" if config.model_type == "gemma4" else DTYPE,
            low_cpu_mem_usage=True,
        )
        return model, tokenizer, processor
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        device_map="auto",
        dtype=DTYPE,
        low_cpu_mem_usage=True,
    )
    return model, tokenizer, tokenizer


def render_inputs(processor, tokenizer, messages, model_name):
    template_kwargs = {"tokenize": True, "add_generation_prompt": True, "return_tensors": "pt"}
    if model_name.startswith(("Qwen3.5", "MiniCPM5", "Gemma 4")):
        template_kwargs["enable_thinking"] = False
    if processor is tokenizer:
        encoded = tokenizer.apply_chat_template(messages, **template_kwargs)
    else:
        encoded = processor.apply_chat_template(messages, **template_kwargs, return_dict=True)
    if isinstance(encoded, torch.Tensor):
        encoded = {"input_ids": encoded}
    return encoded


def move_inputs(encoded, model):
    device = model.get_input_embeddings().weight.device
    moved = {}
    for key, value in encoded.items():
        moved[key] = value.to(device) if isinstance(value, torch.Tensor) else value
    return moved


def main():
    os.environ["HF_HOME"] = str(HF_HOME)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    OUTPUT_DIR.mkdir(exist_ok=True)
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    if benchmark.get("benchmark_id") != "writing_a1_a2_smoke_v2" or len(benchmark.get("cases", [])) != 40:
        raise RuntimeError("Benchmark identity/count check failed; no model was run.")
    if sum(case["condition"] == "incorrect" for case in benchmark["cases"]) != 30:
        raise RuntimeError("Expected 30 incorrect cases; no model was run.")

    start_utc = datetime.now(timezone.utc).isoformat()
    metadata_path = OUTPUT_DIR / "run_metadata.json"
    raw_path = OUTPUT_DIR / "raw_outputs.jsonl"
    metadata = {
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_sha256": file_sha256(BENCHMARK_PATH),
        "started_utc": start_utc,
        "runtime": {"transformers": transformers.__version__, "torch": torch.__version__, "cuda_runtime": torch.version.cuda, "python": os.sys.version},
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "gpu_total_bytes": torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None,
        "generation": {"do_sample": False, "max_new_tokens": MAX_NEW_TOKENS, "max_context_tokens": MAX_CONTEXT_TOKENS, "constrained_json": False, "seed": None},
        "prompt_policy": "Exact benchmark system_prompt and user_prompt_template; native local chat templates; disable thinking where supported except dedicated LFM2.5-1.2B-Thinking checkpoint.",
        "models": [],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    existing = set()
    if raw_path.exists():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing.add((row["model_name"], row["case_id"]))

    for display_name, checkpoint_id, cache_name, family in MODELS:
        snapshot = snapshot_for(cache_name)
        model_meta = {
            "model_name": display_name,
            "exact_model_checkpoint_id": checkpoint_id,
            "family_loader": family,
            "local_snapshot": revision_metadata(snapshot),
            "requested_dtype": "auto (checkpoint quantization)" if display_name.startswith("Gemma 4") else "bfloat16",
            "quantization": json.loads((snapshot / "config.json").read_text(encoding="utf-8")).get("quantization_config"),
            "status": "pending",
        }
        metadata["models"].append(model_meta)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        keys = [(display_name, case["id"]) for case in benchmark["cases"]]
        if all(key in existing for key in keys):
            model_meta["status"] = "already_complete"
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

        monitor = MemoryMonitor()
        model = tokenizer = processor = None
        load_started = time.perf_counter()
        monitor.start()
        try:
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
            model, tokenizer, processor = load_components(snapshot, family)
            model.eval()
            model_meta["loader_class"] = model.__class__.__name__
            model_meta["tokenizer_class"] = tokenizer.__class__.__name__
            model_meta["processor_class"] = processor.__class__.__name__
            model_meta["resolved_parameter_dtype"] = str(next(model.parameters()).dtype)
            model_meta["load_seconds"] = time.perf_counter() - load_started
            model_meta["status"] = "running"
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            model_meta["status"] = "load_failed"
            model_meta["load_error"] = f"{type(exc).__name__}: {exc}"
            for case in benchmark["cases"]:
                if (display_name, case["id"]) in existing:
                    continue
                row = {
                    "model_name": display_name, "exact_model_checkpoint_id": checkpoint_id,
                    "revision_hash": snapshot.name, "quantization_dtype": model_meta["requested_dtype"],
                    "runtime": metadata["runtime"], "case_id": case["id"], "raw_response": "",
                    "parsed_json": None, "json_valid": False, "completed": False, "truncated": False,
                    "repetition_or_loop": False, "text_outside_json": False,
                    "latency_seconds": None, "tokens_generated": None, "tokens_per_second": None,
                    "peak_RAM_bytes": monitor.peak_rss, "peak_VRAM_bytes": None,
                    "error": model_meta["load_error"],
                }
                with raw_path.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                existing.add((display_name, case["id"]))
            monitor.stop()
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

        for case in benchmark["cases"]:
            if (display_name, case["id"]) in existing:
                continue
            user_message = benchmark["user_prompt_template"].format(level=case["level"], task=case["task"], student_text=case["student_text"])
            messages = [{"role": "system", "content": benchmark["system_prompt"]}, {"role": "user", "content": user_message}]
            row = {
                "model_name": display_name, "exact_model_checkpoint_id": checkpoint_id,
                "revision_hash": snapshot.name, "quantization_dtype": model_meta["requested_dtype"],
                "runtime": metadata["runtime"], "case_id": case["id"], "raw_response": "",
                "parsed_json": None, "json_valid": False, "completed": False, "truncated": False,
                "repetition_or_loop": False, "text_outside_json": False,
                "latency_seconds": None, "tokens_generated": None, "tokens_per_second": None,
                "peak_RAM_bytes": None, "peak_VRAM_bytes": None,
            }
            try:
                encoded = render_inputs(processor, tokenizer, messages, display_name)
                input_tokens = int(encoded["input_ids"].shape[-1])
                if input_tokens > MAX_CONTEXT_TOKENS:
                    raise ValueError(f"Rendered input has {input_tokens} tokens, above common context cap {MAX_CONTEXT_TOKENS}.")
                encoded = move_inputs(encoded, model)
                if torch.cuda.is_available():
                    torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()
                with torch.inference_mode():
                    generated = model.generate(**encoded, do_sample=False, max_new_tokens=MAX_NEW_TOKENS, use_cache=True)
                latency = time.perf_counter() - started
                new_tokens = generated[0, input_tokens:]
                raw = tokenizer.decode(new_tokens, skip_special_tokens=True)
                generated_count = int(new_tokens.shape[-1])
                reached_eos = bool(generated_count and tokenizer.eos_token_id is not None and int(new_tokens[-1]) in ([tokenizer.eos_token_id] if isinstance(tokenizer.eos_token_id, int) else tokenizer.eos_token_id))
                parsed, json_valid, outside = parse_response(raw)
                row.update({
                    "raw_response": raw,
                    "parsed_json": parsed,
                    "json_valid": json_valid,
                    "completed": reached_eos,
                    "truncated": generated_count >= MAX_NEW_TOKENS and not reached_eos,
                    "repetition_or_loop": has_repetition(raw),
                    "text_outside_json": outside,
                    "latency_seconds": latency,
                    "tokens_generated": generated_count,
                    "tokens_per_second": generated_count / latency if latency > 0 else None,
                    "input_tokens": input_tokens,
                    "peak_RAM_bytes": monitor.peak_rss,
                    "peak_VRAM_bytes": torch.cuda.max_memory_reserved() if torch.cuda.is_available() else None,
                    "peak_VRAM_allocated_bytes": torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None,
                })
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                row["peak_RAM_bytes"] = monitor.peak_rss
                row["peak_VRAM_bytes"] = torch.cuda.max_memory_reserved() if torch.cuda.is_available() else None
            with raw_path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing.add((display_name, case["id"]))

        model_meta["status"] = "completed"
        model_meta["peak_RAM_bytes"] = monitor.peak_rss
        model_meta["peak_VRAM_bytes"] = torch.cuda.max_memory_reserved() if torch.cuda.is_available() else None
        monitor.stop()
        del model, tokenizer, processor
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata["completed_utc"] = datetime.now(timezone.utc).isoformat()
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
