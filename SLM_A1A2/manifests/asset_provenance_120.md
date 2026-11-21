# Asset provenance + runtime — Phase 2 development_120 (preparation)

Status: preparation only; no main benchmark inference or final test access.
The principal verified SHA-256 of all nine downloaded GGUFs and the three
Qwen source shards against their pinned upstream LFS hashes. Qwen conversion
is a separate local build (see conversion records), not an upstream GGUF.
An active partial GGUF snapshot observed during the inventory was explicitly
excluded from verified assets; partial output is never a valid model.

## 1. Runtime (llama.cpp)

- Selected: `tools/llama.cpp/b11457/` — `llama-server.exe --version` →
  `0.6.0-dev (build 11457, commit 5ad1c5da0)`, Clang 20.1.8 Windows x86_64.
  `llama-server/cli/bench/quantize.exe` present (verified 2026-10-06).
- CUDA staged by the principal: extracted `cublas64_13.dll`, `cublasLt64_13.dll`
  and `cudart64_13.dll` from retained CUDA 13.4 archive beside b11457; b11433
  remains untouched. Archive, executables, staged DLLs and pinned source
  archive hashes are in `runtime_asset_hashes_120.json`.
- Exact source commit resolved from tag b11457:
  `5ad1c5da0ad7f6176256b823925aad19134f0263`. Source extracted from its
  commit-pinned GitHub archive; `gguf` installed from that source's `gguf-py`.
- Host: RTX 3070 8 GiB, driver 610.88. Free: C 70.1 GB, D 168.1 GB.
- Do NOT infer GPU fit from file size: measure VRAM/RAM/offload in readiness.

## 2. Pinned sources (local .metadata commit == HF API `sha`, checked 2026-10-06)

| Family | HF repo | rev (commit) | License |
|---|---|---|---|
| Qwen3.5-2B src | `Qwen/Qwen3.5-2B` | `15852e8c16360a2fea060d615a32b45270f8a8fc` | Apache-2.0 |
| Qwen3.5-4B src | `Qwen/Qwen3.5-4B` | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` | Apache-2.0 |
| MiniCPM5-2B GGUF | `openbmb/MiniCPM5-2B-GGUF` | `2079a22f3beaa4e306449978533478fe0522f4b3` | Apache-2.0 |
| LFM2.5-1.2B GGUF | `LiquidAI/LFM2.5-1.2B-Instruct-GGUF` | `8ed288026e23958ad9dfa92d53ed773a8eee7125` | lfm1.0 (`LICENSE`) |
| Gemma QAT Q4_0 | `google/gemma-4-E2B-it-qat-q4_0-gguf` | `675cff42a74c774d6cb76f76d8eacb49b48c9b93` | Apache-2.0 |
| Gemma UD dynamic | `unsloth/gemma-4-E2B-it-qat-GGUF` | `66a399f68ddd113b06dff02fca9523e55465d11d` | Apache-2.0 |

## 3. Local files (junction aliases, not duplicated copies; 12/12 size and SHA OK)

`os.path.samefile` confirms workspace `models/` and `D:/SLM_A1A2_models`
reference the SAME directory. Hash each asset once, not twice. Each downloaded
file matches upstream size and SHA-256:

| File | Bytes |
|---|---|
| `qwen35_2b/source_hf/model.safetensors-00001-of-00001.safetensors` | 4548221488 |
| `qwen35_4b/source_hf/model.safetensors-00001-of-00002.safetensors` | 5329398688 |
| `qwen35_4b/source_hf/model.safetensors-00002-of-00002.safetensors` | 3990429408 |
| `minicpm5_2b/MiniCPM5-2B-F16.gguf` | 5039006688 |
| `minicpm5_2b/MiniCPM5-2B-Q8_0.gguf` | 2679710688 |
| `minicpm5_2b/MiniCPM5-2B-Q4_K_M.gguf` | 1561318368 |
| `lfm25_12b/LFM2.5-1.2B-Instruct-BF16.gguf` | 2343326528 |
| `lfm25_12b/LFM2.5-1.2B-Instruct-Q8_0.gguf` | 1246253888 |
| `lfm25_12b/LFM2.5-1.2B-Instruct-Q4_K_M.gguf` | 730895168 |
| `gemma4_e2b/google_qat_q4_0/gemma-4-E2B_q4_0-it.gguf` | 3349516256 |
| `gemma4_e2b/unsloth_dynamic/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf` | 2620370976 |
| `gemma4_e2b/unsloth_dynamic/gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf` | 2186186784 |

Machine-readable: `manifests/model_inventory_120.json`
(produced by `scripts/write_model_inventory.py --sha --strict`).
Expected per-file `lfs_sha256` values are embedded there from the HF `trees/*.json`
snapshots (e.g. MiniCPM-F16 `0ffba368…cdf25`, LFM-BF16 `3d80914b…43d1b`).

Not downloaded, per plan: any `mmproj`, MTP files, `*_mobile_*`, QAD variants
(QAD-Q4_0 ≠ our PTQ Q4_K_M — do not confuse), `qad/` sources.

## 4. Qwen conversion inputs (for `scripts/build_qwen_gguf_b11457.ps1 -Execute`)

- Both checkpoints parse as `model_type: qwen3_5`, `Qwen3_5ForConditionalGeneration`
  (transformers 5.18.0, config-only read, verified).
- 2B arch notes (`config.json`): hybrid `linear_attention` (18/24 layers) +
  `full_attention` (6/24), Mamba SSM fp32, vocab 248320, `tie_word_embeddings`,
  max 262144, **vision tower present** → convert text weights only, no mmproj.
- Thinking defaults DIFFER by size (chat templates from HF API):
  - 2B: non-thinking default; `enable_thinking=true` opens `<think>`.
  - 4B: thinking default; pass `enable_thinking=false` for the benchmark's
    non-thinking mode (emits empty `<think>\n\n</think>` block).
- Resolved: exact converter source and `gguf-py` are present. The converter
  is modular: Qwen3.5 architecture registration is in `conversion/qwen.py`,
  not the top-level entrypoint. The preflight checks the registration.
- Recipe: F16 text-only conversion with `--no-nextn`, then Q8_0 and Q4_K_M
  from that same F16, without `--mmproj`/MTP. The 4B F16 is retained as an
  untested intermediate, NOT a fifteenth experiment configuration.
- First conversion was interrupted by a 120-second tool timeout; its own
  partial artifact was archived (not deleted or reused). Re-execution uses
  an unlimited background timeout. See `qwen_conversion_interruption_120.json`.

## 5. Official generation parameters (from vendored READMEs — freeze per family)

- Qwen non-thinking general: `temperature=0.7, top_p=0.8, top_k=20, min_p=0.0,
  presence_penalty=1.5, repetition_penalty=1.0` (both READMEs agree).
- MiniCPM: `temperature=1.0, top_p=0.95, min_p=0.0`, repetition baseline 1.0
  (1.05 only if repetitive). NOTE: llama.cpp defaults `min_p=0.05`, which the
  vendor warns causes repetition loops — pass `min_p=0` explicitly.
- Gemma (both READMEs): `temperature=1.0, top_p=0.95, top_k=64`,
  `enable_thinking=False` for non-thinking.
- LFM: vendor llama.cpp example only: `--temp 0.1 --top-k 50 --repeat-penalty 1.05`
  (`LiquidAI/LFM2.5-1.2B-Instruct-GGUF` README). Upstream GGUF meta: arch `lfm2`,
  ctx 128000. MiniCPM GGUF ctx 131072, Gemma QAT/UD ctx 131072.
- Common: `max_tokens=512`, fixed seed where backend supports it, `-c 4096`,
  `-ngl 999` attempted. No grammar/schema, no draft/MTP, text only.

## 6. Remaining verification (main agent, after review)

1. Downloaded/source SHA verification completed; converted outputs still
   require their successful recipe record and byte-level hashes.
2. Qwen `-Execute` conversion → `manifests/qwen_conversion_record_120.json`;
   confirm identical logical chat template across each family's quants.
3. CUDA DLL staging → 14 readiness probes (synthetic input only).
4. No remote re-check needed for the six repos above unless a re-download occurs
   (revisions pinned; any substitution must be annotated, never silent).

## Preparation refresh and scope extension — 2026-10-11

Qwen conversion completed on 2026-10-07; all six outputs are retained and
reverified against qwen_conversion_record_120.json. The 4B F16 remains an
intermediate. No conversion or download of Qwen was repeated.

LFM2.5-2.6B adds official PTQ Q8_0 (2,874,779,648 bytes) and Q4_K_M
(1,674,455,040 bytes), pinned to LiquidAI/LFM2.5-2.6B-GGUF revision
e7caca5d835a3901a8e0d63e94009429bafafdfc. Acquisition hashes match upstream;
see lfm26_acquisition_record_120.json and lfm26_upstream_snapshot_120.json.
License is lfm1.0 (HF generic `other` plus `license_name`), not Apache/MIT.
No QAD, DSpark, F16 or auxiliary assets were acquired for the 2.6B.
The vendor README prescribes temp=0.1/top_k=50/repeat_penalty=1.1; the two
quants share these frozen values and explicit backend defaults for other
sampling knobs. Existing 1.2B parameters remain unchanged.

Matrix now contains 16 configs and 1920 future development calls; an
additional isolated extension contains 80 future calls on the unchanged
40-case benchmark for only LFM2.5-2.6B Q8_0/Q4_K_M. Neither is approved for
execution. See benchmark_120/lfm26_scope_addendum.md.

Gemma native hashes are distinct. Five offline synthetic text-only renders
with enable_thinking=false are equal across official/Unsloth configurations;
this is finite-path evidence, not a proof for tools/thinking or every input.
See native_template_comparison_120.json/.md; no template was replaced.

All 11 recorded runtime files (source/archive, executables, CUDA DLLs and
converter) match runtime_asset_hashes_120.json again. Driver 610.88 and RTX
3070 8192 MiB confirmed. Pre-acquisition free space D: 156,512,002,048 bytes.
The models junction continues to refer to one shared asset directory.

## Readiness logging diagnosis and provenance limits

The first load attempt (Qwen 2B F16) passed health/render/tokenization but
spent zero generations: default log verbosity 3 suppressed library-level
CUDA/offload evidence. Pinned common/log.cpp maps GGML INFO to TRACE=4.
All final server commands/launchers therefore freeze -lv 4. Sampling, weights,
context, offload attempt and template kwargs are unchanged; the initial
manifest/report/logs remain under logs/readiness_initial_attempt. This is a
logging change before any generated response, not output-guided tuning.
The new attempt uses logs/readiness_after_logging_fix and exclusive logs;
request markers anywhere under logs prohibit another synthetic generation
for the same configuration. See readiness_logging_resolution_120.json.

Each readiness launch rehashes the server binary and model with stability
checks. Full render comparison uses independent groups for Qwen2B/Qwen4B,
MiniCPM, LFM1.2/LFM2.6 and Gemma; individual diagnostics spend no generation
and cannot replace the canonical readiness artifacts. Native templates are
never substituted. Revision bindings in the inventory match all eleven
non-Qwen configurations; Qwen sources are pinned by the conversion record.

The retained Qwen record declares the build/recipe/converter and output
hashes. It does not separately record the hash of the quantizer binary at
conversion time. The current quantizer matches the pinned runtime hashes;
that is not retrospective proof of the executable used in October 7's
conversion. The completed handoff record is accepted as declared provenance;
no historical quantizer SHA was invented and no conversion repeated.

## Explicit non-thinking policy applied by user instruction

All 16 commands/launchers now declare --reasoning off and --reasoning-budget0.
The request body fixes reasoning_budget_tokens=0. Eleven Qwen/MiniCPM/Gemma
configurations additionally pass native enable_thinking=false. Native templates
remain byte-identical to the pinned GGUF metadata. The LFM2.6 template opens
<think> unconditionally; common/chat.cpp1167–1176 selects the LFM2.5 parser,
which passes start/end tags to the reasoning-budget sampler. Budget0 forces
immediate closing after prefill (sampling.cpp314–326,reasoning-budget.cpp80–89).
This is source evidence and still needs runtime revalidation. LFM1.2 Instruct
has a plain assistant prefix and no native enable_thinking branch; its tagged
thinking segments remain bounded at zero. --reasoning-format none was not used:
it changes response parsing and does not disable generation.

The previous readiness is retained as historical evidence bound to its
original manifest SHA. No new generations were issued in this update and no
prior response is reattributed to the new manifest. The four previous request
markers remain; their repeat exception still requires explicit approval.

## Authorized runtime follow-up (2026-10-11)

The user explicitly authorized the four technical non-thinking repetitions. The current unchanged manifest passed16/16 readiness, including LFM2.6 Q8_0/Q4_K_M. All16 synthetic responses had empty reasoning_content, nonempty content and finish_reason=stop; the Gemma native renders matched for this probe. Original native template bytes were retained. Sixteen new request markers and persistent generation claims preserve the budget, and the four old markers remain unchanged. See nonthinking_runtime_verification_120.json and preparation_integration_120.json. The earlier offline snapshot remains historical source evidence. Main execution still requires explicit user approval.
