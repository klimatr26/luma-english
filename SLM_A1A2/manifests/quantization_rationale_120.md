# Quantization rationale — Phase 2 development_120

Hypotheses to test, not results. No perplexity or quality number is transferred
from any other model, vendor chart, or paper as if it were our measurement.

## 1. Roles in the 16-config matrix

- **Q8_0 (Qwen-2B, Qwen-4B, MiniCPM5, LFM2.5) — high-fidelity reference.**
  Q8_0 stores blocks of 32 signed 8-bit weights with a shared block scale,
  not one scale per tensor. Greater weight precision motivates its role as a
  high-fidelity PTQ anchor; that does not guarantee better task accuracy.
  The local Qwen recipe uses no importance matrix. It is not ground truth.
- **Q4_K_M (same families, including the new LFM2.5-2.6B) — balanced operating point.**
  Q4_K uses superblocks of 256 weights with finer subblock scales/minima.
  The `_M` recipe mixes tensor formats: selected tensors may use higher
  precision (often Q6_K); allocation depends on architecture and the exact
  quantizer code, not a universal rule that all attention keys are higher
  precision or all feed-forward tensors lower. Q4_K_S uses a smaller mixture.
  Q4_0 is a simpler symmetric 32-weight block format; it is not literally
  uniform precision across every tensor of a model. Q4_K_M balances size and
  expected reconstruction fidelity; actual quality remains to be measured.
  Standard Q4_K_S/IQ2 alternatives are outside this matrix; Gemma QAT Q4_0
  and dynamic UD-Q2_K_XL are deliberate exceptions, not interchangeable tiers.
- **F16 / BF16 references (Qwen-2B converted, MiniCPM5-F16 official,
  LFM2.5-BF16 official).** Conversion fidelity ceiling for the PTQ ladder.
  Qwen-4B has no F16 config in the matrix (Q8_0 + Q4_K_M only,
  `inclusion_stage: development_120`).

## 2. QAT vs PTQ — do not mix

- **Google `gemma-4-E2B_q4_0-it.gguf` (config 12) is quantization-aware trained:**
  the Q4_0 format here is the *output of QAT*, not post-training rounding to
   4 bits. Unsloth variants also originate from a QAT-labelled Gemma checkpoint;
   their dynamic GGUF encoding is a separate transformation. Within Gemma,
   provenance and encoding differences prevent a clean format-only causal
   attribution unless the source checkpoints are demonstrated identical.
   Comparing different model families additionally confounds architecture,
   training and parameter count; it never isolates QAT versus PTQ.
- **LFM QAD-Q4_0 is a different artifact** (`LFM2.5-1.2B-Instruct-QAD-Q4_0.gguf`,
  not downloaded): quantization-aware *distilled*, with its own FP32 source in
  `qad/`. Our LFM Q4_K_M is PTQ from the BF16 release. Same warning applies.

## 3. Unsloth Dynamic (configs 13–14) — non-uniform by construction

`gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf` and `…-Q2_K_XL.gguf` are Unsloth Dynamic 2.0
variants: non-uniform tensor/weight-group bit allocation, with vendor-selected
groups kept at greater precision. They are NOT standard `Q4_K_M` / uniform Q2 quantization, and the
`XL` suffix denotes the dynamic sizing scheme. Label them `unsloth_dynamic`,
keep them out of any "Q4 tier" grouping, and treat vendor quantization-benchmark
claims as hypotheses under test (vendor: Unsloth Dynamic 2.0 GGUF docs).

## 4. Limits and attributions

- K-quant behavior described above follows the llama.cpp quantization design
  (super-block / importance-matrix documentation); per-tensor outcomes depend on
  each GGUF's actual `tensor_type` metadata — dump and record it per file in
  readiness rather than assuming uniformity.
- Vendor sampling defaults used as frozen parameters: Qwen README (non-thinking
  0.7/0.8/20/0.0/1.5/1.0), MiniCPM README (1.0/0.95/0.0 + min_p warning),
  Gemma READMEs (1.0/0.95/64, non-thinking), LFM README llama.cpp example
  (0.1/50/1.05). See `asset_provenance_120.md` §5.
- Local Qwen quantization omits `--imatrix`; this is a recorded recipe, not a
  statement about the downloaded vendors' pipelines. For downloaded GGUFs,
  calibration/imatrix use is unknown unless the pinned vendor metadata or
  documentation establishes it. Readiness cannot reconstruct training or
  calibration provenance from successful loading.

## 5. Sources (definitions, not our task results)

- Pinned llama.cpp quantizer: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/src/llama-quant.cpp
- Block definitions: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-common.h
- Quantization implementations: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-quants.c
- Google QAT artifact: https://huggingface.co/google/gemma-4-E2B-it-qat-q4_0-gguf/tree/675cff42a74c774d6cb76f76d8eacb49b48c9b93
- Unsloth artifact and vendor descriptions: https://huggingface.co/unsloth/gemma-4-E2B-it-qat-GGUF/tree/66a399f68ddd113b06dff02fca9523e55465d11d
- Unsloth Dynamic documentation (vendor claims): https://docs.unsloth.ai/basics/unsloth-dynamic-2.0-ggufs
