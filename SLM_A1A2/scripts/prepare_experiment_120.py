"""Build manifests/experiment_manifest_120.json with the 16 Phase-2 configs.

Unified contract: top-level "configurations" list (with "configs" as an
identical alias). Per config: config_id, id, model_path STRING, model_sha256,
server_command LIST, port, generation dict (max_tokens=512, seed=42, only
real llama.cpp server API keys, every knob explicit, identical per family),
plus retained nested source/gguf/runtime metadata.

SHA policy (no silent overwrite): without --sha, model_sha256 is reused ONLY
from inventory with upstream/conversion hash agreement, stable hashing,
matching path, size and mtime. Qwen additionally requires the conversion
record to agree; that record alone never verifies current bytes.
With --sha, recompute ONLY files lacking a verified match. A present GGUF
with no record match is "present_unverified" (never treated as ready).
Partial-write artifacts (*.partial) are ignored, never parsed.

GGUF metadata: installed `gguf` package (GGUFReader) first; stdlib
full-streaming fallback otherwise (seek-based, complete array skip, full
untruncated strings, full template SHA-256, tensor-type histogram).

Qwen conversion recipe/hash pointers come from
manifests/runtime_asset_hashes_120.json (principal) + the vendored
converter tree (qwen3_5 registration verified 2026-10-06).

Read-only apart from writing the manifest. Never converts/infers/downloads.

Usage: .venv/Scripts/python.exe scripts/prepare_experiment_120.py [--sha] [--qwen-dir DIR]
"""
import argparse
import hashlib
import json
import os
import struct
import sys

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "scripts"))
from authorization_guard import sha256_file  # shared, no side effects

MANIFEST_OUT = os.path.join(LAB, "manifests", "experiment_manifest_120.json")
INVENTORY = os.path.join(LAB, "manifests", "model_inventory_120.json")
CONV_RECORD = os.path.join(LAB, "manifests", "qwen_conversion_record_120.json")
RUNTIME_HASHES = os.path.join(LAB, "manifests", "runtime_asset_hashes_120.json")

# Full llama.cpp commit (principal runtime_asset_hashes_120.json).
LLAMA = {"build": "b11457",
         "commit": "5ad1c5da0ad7f6176256b823925aad19134f0263",
         "version": "0.6.0-dev (build 11457, commit 5ad1c5da0)",
         "bin_dir": "tools/llama.cpp/b11457"}
SERVER_EXE = "tools/llama.cpp/b11457/llama-server.exe"

# Verified server API facts (b11457 binary strings, 2026-10-06):
#  - sampling key is `repeat_penalty` (`repetition_penalty` absent);
#  - `presence_penalty`, `frequency_penalty`, `min_p` present;
#  - routes `/apply-template` and `/tokenize` present.
# Generation dicts use ONLY these keys (+temperature/top_p/top_k/seed/
# max_tokens). Every knob explicit; `*_default` source noted per value.
GENERATION = {
    # Vendor non-thinking general: 0.7/0.8/20/0.0 + presence 1.5 + repetition 1.0.
    # repetition->repeat_penalty, presence->presence_penalty, frequency stays 0.0.
    "qwen": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
             "repeat_penalty": 1.0, "presence_penalty": 1.5, "frequency_penalty": 0.0},
    # Vendor: 1.0/0.95/0.0, repetition baseline 1.0. top_k vendor-unspecified ->
    # backend default 40 recorded explicitly (NOT vendor-endorsed).
    "minicpm": {"temperature": 1.0, "top_p": 0.95, "top_k": 40, "min_p": 0.0,
                "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0},
    # Vendor llama.cpp example only: temp 0.1/top-k 50/repeat 1.05.
    # top_p + min_p vendor-unspecified -> backend defaults recorded explicitly.
    "lfm": {"temperature": 0.1, "top_p": 0.95, "top_k": 50, "min_p": 0.05,
            "repeat_penalty": 1.05, "presence_penalty": 0.0, "frequency_penalty": 0.0},
    "lfm26": {"temperature": 0.1, "top_p": 0.95, "top_k": 50, "min_p": 0.05,
              "repeat_penalty": 1.1, "presence_penalty": 0.0, "frequency_penalty": 0.0},
    # Vendor: 1.0/0.95/64, non-thinking. min_p vendor-unspecified -> default.
    "gemma": {"temperature": 1.0, "top_p": 0.95, "top_k": 64, "min_p": 0.05,
              "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0},
}
GENERATION_NOTES = {
    "qwen": "vendor values; repetition_penalty mapped to server repeat_penalty",
    "minicpm": "vendor values; top_k=40 is backend default, vendor-unspecified",
    "lfm": "vendor temp/top_k/repeat only; top_p/min_p are backend defaults",
    "lfm26": "2.6B pinned vendor README: temp=0.1/top_k=50/repeat=1.1; top_p/min_p are explicit backend defaults, not vendor recommendations",
    "gemma": "vendor values; min_p=0.05 is backend default, vendor-unspecified",
}
# Native-template kwargs (NOT a template override; --chat-template* never used).
# Qwen non-thinking requires enable_thinking=false (4B defaults to thinking).
# MiniCPM and Gemma also support the native toggle. Runtime reasoning off and
# zero thinking budget are explicit for all configurations; zero budget closes
# LFM2.6's unconditional native <think> prefix without replacing its template.
TEMPLATE_KWARGS = {
    "qwen": {"enable_thinking": False},
    "gemma": {"enable_thinking": False},
    "minicpm": {"enable_thinking": False},
    "lfm": None,
    "lfm26": None,
}
THINKING_CONTROL = {
    'qwen': 'native_enable_thinking_false_and_zero_budget',
    'minicpm': 'native_enable_thinking_false_and_zero_budget',
    'gemma': 'native_enable_thinking_false_and_zero_budget',
    'lfm': 'plain_instruct_prefix_no_native_toggle; zero_budget_if_parser_exposes_thinking_tags',
    'lfm26': 'unconditional_native_think_prefix; zero_budget_forces_immediate_end_tag',
}

# (config_id, id, family, quant, gguf-spec, repo, rev, license, port,
#  inclusion_stage, quant_note)
CONFIGS = [
    ("01-qwen35-2b-f16", "qwen35_2b_f16", "qwen", "F16", ("Qwen3.5-2B-F16.gguf", True),
     "Qwen/Qwen3.5-2B", "15852e8c16360a2fea060d615a32b45270f8a8fc",
     "Apache-2.0", 8101, "development_120", "converted reference"),
    ("02-qwen35-2b-q8-0", "qwen35_2b_q8_0", "qwen", "Q8_0", ("Qwen3.5-2B-Q8_0.gguf", True),
     "Qwen/Qwen3.5-2B", "15852e8c16360a2fea060d615a32b45270f8a8fc",
     "Apache-2.0", 8102, "development_120", "high-fidelity PTQ anchor"),
    ("03-qwen35-2b-q4-k-m", "qwen35_2b_q4_k_m", "qwen", "Q4_K_M", ("Qwen3.5-2B-Q4_K_M.gguf", True),
     "Qwen/Qwen3.5-2B", "15852e8c16360a2fea060d615a32b45270f8a8fc",
     "Apache-2.0", 8103, "development_120", "balanced K-quant"),
    ("04-minicpm5-2b-f16", "minicpm5_2b_f16", "minicpm", "F16",
     "models/minicpm5_2b/MiniCPM5-2B-F16.gguf",
     "openbmb/MiniCPM5-2B-GGUF", "2079a22f3beaa4e306449978533478fe0522f4b3",
     "Apache-2.0", 8104, "development_120", "official reference"),
    ("05-minicpm5-2b-q8-0", "minicpm5_2b_q8_0", "minicpm", "Q8_0",
     "models/minicpm5_2b/MiniCPM5-2B-Q8_0.gguf",
     "openbmb/MiniCPM5-2B-GGUF", "2079a22f3beaa4e306449978533478fe0522f4b3",
     "Apache-2.0", 8105, "development_120", "high-fidelity PTQ anchor"),
    ("06-minicpm5-2b-q4-k-m", "minicpm5_2b_q4_k_m", "minicpm", "Q4_K_M",
     "models/minicpm5_2b/MiniCPM5-2B-Q4_K_M.gguf",
     "openbmb/MiniCPM5-2B-GGUF", "2079a22f3beaa4e306449978533478fe0522f4b3",
     "Apache-2.0", 8106, "development_120", "balanced K-quant"),
    ("07-lfm25-12b-bf16", "lfm25_12b_bf16", "lfm", "BF16",
     "models/lfm25_12b/LFM2.5-1.2B-Instruct-BF16.gguf",
     "LiquidAI/LFM2.5-1.2B-Instruct-GGUF", "8ed288026e23958ad9dfa92d53ed773a8eee7125",
     "lfm1.0", 8107, "development_120", "official reference"),
    ("08-lfm25-12b-q8-0", "lfm25_12b_q8_0", "lfm", "Q8_0",
     "models/lfm25_12b/LFM2.5-1.2B-Instruct-Q8_0.gguf",
     "LiquidAI/LFM2.5-1.2B-Instruct-GGUF", "8ed288026e23958ad9dfa92d53ed773a8eee7125",
     "lfm1.0", 8108, "development_120", "high-fidelity PTQ anchor"),
    ("09-lfm25-12b-q4-k-m", "lfm25_12b_q4_k_m", "lfm", "Q4_K_M",
     "models/lfm25_12b/LFM2.5-1.2B-Instruct-Q4_K_M.gguf",
     "LiquidAI/LFM2.5-1.2B-Instruct-GGUF", "8ed288026e23958ad9dfa92d53ed773a8eee7125",
     "lfm1.0", 8109, "development_120", "balanced K-quant; distinct from QAD-Q4_0"),
    ("10-qwen35-4b-q8-0", "qwen35_4b_q8_0", "qwen", "Q8_0", ("Qwen3.5-4B-Q8_0.gguf", True),
     "Qwen/Qwen3.5-4B", "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
     "Apache-2.0", 8110, "development_120", "dev-only scale point, not a 40-case candidate"),
    ("11-qwen35-4b-q4-k-m", "qwen35_4b_q4_k_m", "qwen", "Q4_K_M", ("Qwen3.5-4B-Q4_K_M.gguf", True),
     "Qwen/Qwen3.5-4B", "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
     "Apache-2.0", 8111, "development_120", "dev-only scale point, not a 40-case candidate"),
    ("12-gemma4-e2b-qat-q4-0", "gemma4_e2b_qat_q4_0", "gemma", "Q4_0",
     "models/gemma4_e2b/google_qat_q4_0/gemma-4-E2B_q4_0-it.gguf",
     "google/gemma-4-E2B-it-qat-q4_0-gguf", "675cff42a74c774d6cb76f76d8eacb49b48c9b93",
     "Apache-2.0", 8112, "development_120", "official QAT output, not PTQ"),
    ("13-gemma4-e2b-ud-q4-k-xl", "gemma4_e2b_ud_q4_k_xl", "gemma", "UD-Q4_K_XL",
     "models/gemma4_e2b/unsloth_dynamic/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf",
     "unsloth/gemma-4-E2B-it-qat-GGUF", "66a399f68ddd113b06dff02fca9523e55465d11d",
     "Apache-2.0", 8113, "development_120", "Unsloth Dynamic non-uniform, not Q4_K_M"),
    ("14-gemma4-e2b-ud-q2-k-xl", "gemma4_e2b_ud_q2_k_xl", "gemma", "UD-Q2_K_XL",
     "models/gemma4_e2b/unsloth_dynamic/gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf",
     "unsloth/gemma-4-E2B-it-qat-GGUF", "66a399f68ddd113b06dff02fca9523e55465d11d",
     "Apache-2.0", 8114, "development_120", "Unsloth Dynamic non-uniform, aggressive"),
    ("15-lfm25-26b-q8-0", "lfm25_26b_q8_0", "lfm26", "Q8_0",
     "models/lfm25_26b/LFM2.5-2.6B-Q8_0.gguf",
     "LiquidAI/LFM2.5-2.6B-GGUF", "e7caca5d835a3901a8e0d63e94009429bafafdfc",
     "lfm1.0", 8115, "development_120", "official PTQ Q8_0; additional separate 40-case preparation"),
    ("16-lfm25-26b-q4-k-m", "lfm25_26b_q4_k_m", "lfm26", "Q4_K_M",
     "models/lfm25_26b/LFM2.5-2.6B-Q4_K_M.gguf",
     "LiquidAI/LFM2.5-2.6B-GGUF", "e7caca5d835a3901a8e0d63e94009429bafafdfc",
     "lfm1.0", 8116, "development_120", "official PTQ Q4_K_M; not Q4_0 or QAD; additional separate 40-case preparation"),
]


def _field_text(field):
    """Best-effort scalar extraction from a GGUFReader field (any gguf-py shape)."""
    if field is None:
        return None
    for attr in ("contents", "value", "data"):
        obj = getattr(field, attr, None)
        if obj is None:
            continue
        if callable(obj):
            try:
                obj = obj()
            except TypeError:
                continue
        if isinstance(obj, (bytes, bytearray)):
            return bytes(obj).decode("utf-8", "replace")
        if isinstance(obj, str):
            return obj
        try:
            import numpy as np  # noqa
            if isinstance(obj, np.ndarray) and obj.size == 1:
                item = obj.reshape(-1)[0]
                return item.decode("utf-8", "replace") if isinstance(item, bytes) else item
        except ImportError:
            pass
        return obj
    return None


def gguf_meta_ggufreader(path):
    """Full metadata via installed gguf.GGUFReader. Raises on any failure."""
    from gguf import GGUFReader
    reader = GGUFReader(path)
    fields = getattr(reader, "fields", {})
    meta = {}
    for key in fields:
        try:
            field = reader.get_field(key)
        except Exception:
            continue
        val = _field_text(field)
        if isinstance(val, str) and key == "tokenizer.chat_template":
            meta[key] = val  # full, never truncated
        elif isinstance(val, (str, int, float, bool)):
            meta[key] = val if not isinstance(val, str) or len(val) <= 4096 else val[:4096]
        # non-scalars (arrays/tensors) skipped for metadata purposes
    tensor_types = {}
    tensors = getattr(reader, "tensors", [])
    for info in tensors:
        tensor_type = getattr(info, "tensor_type", None)
        tname = getattr(tensor_type, "name", None) or str(tensor_type)
        tensor_types[tname] = tensor_types.get(tname, 0) + 1
    meta["_tensor_type_histogram"] = tensor_types or None
    meta["_n_tensors"] = len(tensors)
    return meta


# ---- stdlib full-streaming fallback (seek-based, no size cap) ----
_FMTS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f",
         7: "<?", 10: "<Q", 11: "<q", 12: "<d"}


def _rs(fh, n):
    buf = fh.read(n)
    if len(buf) != n:
        raise ValueError("truncated GGUF file")
    return buf


def _rstr(fh):
    (n,) = struct.unpack("<Q", _rs(fh, 8))
    return _rs(fh, n).decode("utf-8", "replace")


def _skip_val(fh, typ):
    if typ == 8:
        _rstr(fh)
        return
    if typ == 9:
        (ety, ln) = struct.unpack("<IQ", _rs(fh, 12))
        if ety == 8:
            for _ in range(ln):
                _rstr(fh)
        elif ety == 9:
            raise ValueError("nested array in GGUF metadata")
        else:
            fh.seek(struct.calcsize(_FMTS[ety]) * ln, os.SEEK_CUR)
        return
    fh.seek(struct.calcsize(_FMTS[typ]), os.SEEK_CUR)


def _read_val(fh, typ):
    if typ == 8:
        return _rstr(fh)
    if typ == 9:
        raise ValueError("array passed to scalar reader")
    return struct.unpack(_FMTS[typ], _rs(fh, struct.calcsize(_FMTS[typ])))[0]


def gguf_meta_streaming(path):
    """Seek-based full KV parse. Reads the whole header, never truncates strings."""
    meta = {}
    with open(path, "rb") as fh:
        if _rs(fh, 4) != b"GGUF":
            raise ValueError("bad GGUF magic")
        ver, n_tensors, n_kv = struct.unpack("<IQQ", _rs(fh, 20))
        meta["_gguf_version"] = ver
        meta["_n_tensors"] = n_tensors
        for _ in range(n_kv):
            key = _rstr(fh)
            (typ,) = struct.unpack("<I", _rs(fh, 4))
            if typ == 9 or key == "tokenizer.ggml.merges":
                if key == "tokenizer.chat_template":
                    raise ValueError("unexpected array chat template")
                _skip_val(fh, typ)
                continue
            meta[key] = _read_val(fh, typ)
    return meta


def gguf_metadata(path):
    """GGUFReader first; stdlib streaming fallback. Returns (meta, reader_used)."""
    try:
        return gguf_meta_ggufreader(path), "gguf.GGUFReader"
    except Exception as exc_reader:
        try:
            return gguf_meta_streaming(path), f"stdlib-streaming (GGUFReader: {type(exc_reader).__name__})"
        except Exception as exc_std:
            raise ValueError(f"both readers failed ({type(exc_reader).__name__} / "
                             f"{type(exc_std).__name__}: {exc_std})")


def summarize_metadata(meta):
    arch = meta.get("general.architecture")
    out = {
        "architecture": arch,
        "context_length": meta.get("llama.context_length") if arch == "llama" else
                          meta.get(f"{arch}.context_length") if arch else None,
        "embedding_length": meta.get("llama.embedding_length") if arch == "llama" else
                            meta.get(f"{arch}.embedding_length") if arch else None,
        "block_count": meta.get("llama.block_count") if arch == "llama" else
                       meta.get(f"{arch}.block_count") if arch else None,
        "tensor_type_histogram": meta.get("_tensor_type_histogram"),
        "n_tensors": meta.get("_n_tensors"),
    }
    chat = meta.get("tokenizer.chat_template")
    out["chat_template_present"] = isinstance(chat, str)
    out["chat_template_chars"] = len(chat) if isinstance(chat, str) else None
    out["chat_template_sha256"] = (hashlib.sha256(chat.encode("utf-8")).hexdigest()
                                   if isinstance(chat, str) else None)
    return out


def load_verified_shas():
    """basename -> sha256 from inventory (verified, --strict) — read-only."""
    out = {}
    try:
        with open(INVENTORY, "r", encoding="utf-8") as fh:
            inv = json.load(fh)
        for root in inv.get("roots", []):
            for e in root.get("entries", []):
                if (e.get("sha256") and e.get("size_match") is True
                        and e.get("sha256_match") is True
                        and e.get("stable_during_hash") is True):
                    out.setdefault(e["file"], {"sha256": e["sha256"],
                                               "bytes": e.get("size"),
                                               "mtime_ns": e.get("mtime_ns"),
                                               "hf_commit": e.get('hf_commit'),
                                               "path": e.get("path")})
    except (OSError, ValueError):
        pass
    return out


def load_conversion_outputs():
    """filename -> {sha256, bytes} from qwen_conversion_record_120.json, if present."""
    try:
        with open(CONV_RECORD, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    runtime = load_runtime_hashes() or {}
    expected_sources = {'2B': '15852e8c16360a2fea060d615a32b45270f8a8fc',
                        '4B': '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'}
    converter = rec.get('converter')
    pinned_converter = next((f.get('sha256') for f in runtime.get('files', [])
                             if f['path'].endswith('convert_hf_to_gguf.py')), None)
    if (rec.get('llama_commit') != LLAMA['commit'] or rec.get('llama_build') != LLAMA['build']
            or rec.get('sources') != expected_sources
            or not pinned_converter or rec.get('converter_sha256') != pinned_converter
            or not converter or not os.path.isfile(converter)
            or sha256_file(converter) != pinned_converter):
        raise ValueError('Qwen conversion provenance disagrees with pinned runtime/source/converter')
    recipe = rec.get('recipe', '')
    if not all(fragment in recipe for fragment in ('--outtype f16', '--no-nextn', 'text-only', 'Q8_0/Q4_K_M')):
        raise ValueError('Qwen conversion recipe does not match approved text-only F16/no-nextn PTQ chain')
    registration = os.path.join(os.path.dirname(converter), 'conversion', 'qwen.py')
    with open(registration, encoding='utf-8') as stream:
        if 'Qwen3_5ForConditionalGeneration' not in stream.read():
            raise ValueError('Pinned converter lacks Qwen3.5 registration')
    out = {}
    for o in rec.get("outputs", []):
        name = os.path.basename(o.get("file", ""))
        if name and o.get("sha256") and o.get("bytes"):
            out[name] = {"sha256": o["sha256"], "bytes": o["bytes"]}
    return {"date_utc": rec.get("date_utc"), "llama_commit": rec.get("llama_commit"),
            "converter": rec.get("converter"), "sources": rec.get("sources"),
            "recipe": recipe, "recipe_consistency_verified": True,
            "outputs": out}


def load_runtime_hashes():
    try:
        with open(RUNTIME_HASHES, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def host_snapshot():
    snap = {}
    try:
        import psutil
        vm = psutil.virtual_memory()
        snap["ram_total_gb"] = round(vm.total / 1e9, 2)
        snap["ram_available_gb"] = round(vm.available / 1e9, 2)
    except ImportError:
        snap["ram_total_gb"] = None
        snap["ram_available_gb"] = None
    snap.update(HOST_STATIC)
    return snap


HOST_STATIC = {"gpu": "NVIDIA GeForce RTX 3070 8 GiB", "driver": "610.88",
               "os": "Windows x86_64"}


def main():
    import argparse
    import datetime
    ap = argparse.ArgumentParser()
    ap.add_argument("--qwen-dir", default=r"D:\SLM_A1A2_models\qwen_converted")
    ap.add_argument("--sha", action="store_true",
                    help="Recompute SHA-256 ONLY for files with no verified match.")
    args = ap.parse_args()

    verified = load_verified_shas()
    conv = load_conversion_outputs()
    conv_out = (conv or {}).get("outputs", {}) or {}
    runtime_hashes = load_runtime_hashes()

    entries = []
    for spec in CONFIGS:
        (cid, iid, fam, quant, gspec, repo, rev, lic, port, stage, qnote) = spec
        if isinstance(gspec, tuple):
            fname = gspec[0]
            model_path = os.path.join(args.qwen_dir, fname).replace("\\", "/")
            abspath = os.path.join(args.qwen_dir, fname)
            convertible = True
        else:
            model_path = gspec
            abspath = os.path.join(LAB, *gspec.split("/"))
            convertible = False
        present = os.path.isfile(abspath) and not abspath.endswith(".partial")
        nbytes = os.path.getsize(abspath) if present else None
        base = os.path.basename(abspath)

        # SHA resolution: verified records on exact (basename, bytes) match only.
        model_sha256, sha_source = None, None
        cand = verified.get(base)
        if (present and cand and cand.get("bytes") == nbytes
                and cand.get("mtime_ns") == os.stat(abspath).st_mtime_ns
                and os.path.samefile(cand["path"], abspath)
                and (convertible or cand.get('hf_commit') == rev)):
            model_sha256, sha_source = cand["sha256"], "model_inventory_120.json"
        cand = conv_out.get(base)
        if present and convertible and (not cand or cand.get("bytes") != nbytes):
            model_sha256, sha_source = None, None
        if present and cand and cand.get("bytes") == nbytes and model_sha256:
            if model_sha256 and model_sha256 != cand["sha256"]:
                raise SystemExit(f"SHA conflict for {base}: inventory vs conversion record")
            # The recipe record is expected provenance, never evidence of current bytes.
            sha_source = "verified model_inventory_120.json + qwen_conversion_record_120.json"
        if present and model_sha256 is None and args.sha:
            before = os.stat(abspath)
            model_sha256, sha_source = sha256_file(abspath), "computed-now-unverified"
            after = os.stat(abspath)
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise SystemExit(f"Asset changed while hashing: {base}")
        status = ("missing" if not present
                  else "verified" if model_sha256 and sha_source != "computed-now-unverified"
                  else "present_unverified")

        gen = dict(GENERATION[fam])
        gen_full = {"max_tokens": 512, "seed": 42, 'reasoning_budget_tokens': 0}
        gen_full.update(gen)
        cmd = [SERVER_EXE, "-m", model_path, "--host", "127.0.0.1",
               "--port", str(port), "-c", "4096", "--parallel", "1", "-lv", "4", "-ngl", "999", "-s", "42",
               '--reasoning', 'off', '--reasoning-budget', '0',
               "--log-file", f"logs/servers/{iid}.log"]
        kwargs = TEMPLATE_KWARGS[fam]
        if kwargs is not None:
            cmd += ["--chat-template-kwargs", json.dumps(kwargs, separators=(",", ":"))]
        entry = {
            "config_id": cid, "id": iid, "family": fam, "quant": quant,
            "template_comparison_group": "gemma4_e2b_text_non_thinking" if fam == "gemma" else repo,
            "inclusion_stage": stage,
            "supported_benchmarks": (["development_120", "phase1_40_lfm26_extension"]
                                     if fam == "lfm26" else ["development_120"]),
            "model_path": model_path,
            "model_sha256": model_sha256,
            "model_sha256_source": sha_source,
            "server_command": cmd,
            "port": port,
            "generation": gen_full,
            "generation_note": GENERATION_NOTES[fam],
            "chat_template_kwargs": kwargs,
            'thinking_policy': {'requested_mode': 'disabled_where_supported',
                                'control': THINKING_CONTROL[fam],
                                'evidence': 'pinned native GGUF template and b11457 reasoning-budget implementation; runtime revalidation pending'},
            "source": {"repo": repo, "revision": rev, "license": lic},
            "gguf": {"path": model_path, "status": status,
                     "bytes": nbytes,
                     "inventory_sha256": (verified.get(base) or {}).get("sha256")
                     if not convertible else None},
            "quant_note": qnote,
            "runtime": {
                "llama": LLAMA, "host": host_snapshot(),
                "server": SERVER_EXE, "command": cmd,
                "server_sha256": next(f['sha256'] for f in runtime_hashes['files'] if f['path'].endswith(SERVER_EXE)),
                "log_verbosity": 4,
                "bind": "127.0.0.1", "ctx": 4096, "ngl_attempt": 999,
                "parallel_sequences": 1,
                'reasoning_mode': 'off', 'reasoning_budget_tokens': 0,
                "kv_cache_offload": "backend default (enabled)",
                "kv_cache_types": "backend default (not overridden)",
                "template": "native GGUF metadata (no --chat-template/--chat-template-file)",
                "extras": {"mmproj": False, "mtp": False, "speculative": False,
                           "grammar": False, "jinja": "backend default (enabled)"},
            },
        }
        if present and status == "verified":
            try:
                meta, reader_used = gguf_metadata(abspath)
                entry["gguf"]["metadata_reader"] = reader_used
                entry["gguf"].update(summarize_metadata(meta))
            except ValueError as exc:
                entry["gguf"]["status"] = "present_unverified"
                entry["gguf"]["metadata_error"] = str(exc)[:300]
                status = "present_unverified"
        entries.append(entry)

    # Intra-family native-template assertion (raw SHA; nulls never count as equal).
    templates = {}
    for e in entries:
        if e["gguf"].get("chat_template_sha256"):
            templates.setdefault(e["family"], {})[e["id"]] = e["gguf"]["chat_template_sha256"]
    template_assert = {}
    for fam in sorted({e["family"] for e in entries}):
        shas = set(templates.get(fam, {}).values())
        ids = [e["id"] for e in entries if e["family"] == fam]
        embedded = [e["id"] for e in entries
                    if e["family"] == fam and e["gguf"].get("chat_template_sha256")]
        template_assert[fam] = {
            "identical": len(shas) == 1 and len(embedded) == len(ids),
            "sha256": next(iter(shas)) if len(shas) == 1 else None,
            "embedded_in": embedded,
            "note": ("all configs embed byte-identical template" if len(shas) == 1 and len(embedded) == len(ids)
                     else "different embedded template hashes; synthetic render comparison required"
                     if len(embedded) == len(ids)
                     else "INCOMPLETE: some configs lack embedded template; readiness must verify the effective render per config via /apply-template"),
        }

    import datetime as _dt
    manifest = {
        "name": "experiment_manifest_120",
        "n_configs": len(entries),
        "n_verified": sum(1 for e in entries if e["gguf"]["status"] == "verified"),
        "n_present_unverified": sum(1 for e in entries if e["gguf"]["status"] == "present_unverified"),
        "n_missing": sum(1 for e in entries if e["gguf"]["status"] == "missing"),
        "date_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "qwen_conversion": ({
            "record": CONV_RECORD.replace("\\", "/"),
            "date_utc": (conv or {}).get("date_utc"),
            "converter": (conv or {}).get("converter"),
            "converter_sha256": next(
                (f["sha256"] for f in (runtime_hashes or {}).get("files", [])
                 if f["path"].endswith("convert_hf_to_gguf.py")), None),
            "sources": (conv or {}).get("sources") or
                       {"2B": "15852e8c16360a2fea060d615a32b45270f8a8fc",
                        "4B": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"},
            "qwen3_5_registered_in_converter": True,
            "recipe_consistency_verified": (conv or {}).get('recipe_consistency_verified', False),
        }),
        "template_assert": template_assert,
        "configurations": entries,
        "configs": entries,
    }
    with open(MANIFEST_OUT, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"verified={manifest['n_verified']} unverified={manifest['n_present_unverified']} "
          f"missing={manifest['n_missing']} -> {MANIFEST_OUT}")
    for e in entries:
        if e["gguf"]["status"] != "verified":
            print(f"  {e['gguf']['status'].upper()} {e['id']}: {e['model_path']}")


if __name__ == "__main__":
    main()
