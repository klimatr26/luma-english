# Independent review: non-thinking controls in Phase 2

## Scope and method

This is a source-only review of the 16 GGUF assets named in `scripts/prepare_experiment_120.py`. I imported that module without calling `main()` and read each asset's `tokenizer.chat_template` via its `gguf_meta_streaming()` implementation (`scripts/prepare_experiment_120.py:258-277`). The report records the full-template SHA-256 values computed from that metadata. No model inference, readiness run, or benchmark was performed.

## Native GGUF templates inspected

| Config ID | GGUF asset | `tokenizer.chat_template` SHA-256 |
|---|---|---|
| `01-qwen35-2b-f16` | `models/qwen_converted/Qwen3.5-2B-F16.gguf` | `273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80` |
| `02-qwen35-2b-q8-0` | `models/qwen_converted/Qwen3.5-2B-Q8_0.gguf` | `273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80` |
| `03-qwen35-2b-q4-k-m` | `models/qwen_converted/Qwen3.5-2B-Q4_K_M.gguf` | `273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80` |
| `04-minicpm5-2b-f16` | `models/minicpm5_2b/MiniCPM5-2B-F16.gguf` | `cc945752db555d60949b16989df4ccfeb52a313d6b4b5c5229dd786e2e9fcf1c` |
| `05-minicpm5-2b-q8-0` | `models/minicpm5_2b/MiniCPM5-2B-Q8_0.gguf` | `cc945752db555d60949b16989df4ccfeb52a313d6b4b5c5229dd786e2e9fcf1c` |
| `06-minicpm5-2b-q4-k-m` | `models/minicpm5_2b/MiniCPM5-2B-Q4_K_M.gguf` | `cc945752db555d60949b16989df4ccfeb52a313d6b4b5c5229dd786e2e9fcf1c` |
| `07-lfm25-12b-bf16` | `models/lfm25_12b/LFM2.5-1.2B-Instruct-BF16.gguf` | `f05bf4b967dc993bdc7a2fe6e43759ee218eb0eb340d68b063e1c4f8ad148176` |
| `08-lfm25-12b-q8-0` | `models/lfm25_12b/LFM2.5-1.2B-Instruct-Q8_0.gguf` | `f05bf4b967dc993bdc7a2fe6e43759ee218eb0eb340d68b063e1c4f8ad148176` |
| `09-lfm25-12b-q4-k-m` | `models/lfm25_12b/LFM2.5-1.2B-Instruct-Q4_K_M.gguf` | `f05bf4b967dc993bdc7a2fe6e43759ee218eb0eb340d68b063e1c4f8ad148176` |
| `10-qwen35-4b-q8-0` | `models/qwen_converted/Qwen3.5-4B-Q8_0.gguf` | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |
| `11-qwen35-4b-q4-k-m` | `models/qwen_converted/Qwen3.5-4B-Q4_K_M.gguf` | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |
| `12-gemma4-e2b-qat-q4-0` | `models/gemma4_e2b/google_qat_q4_0/gemma-4-E2B_q4_0-it.gguf` | `0a2c8073c878ab1da004bee933a998606537bbb62016310352c7285c3f01c5b5` |
| `13-gemma4-e2b-ud-q4-k-xl` | `models/gemma4_e2b/unsloth_dynamic/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf` | `241c50d86bdfe5e43307da87f559cd2416aacd67a8de46c15acc0105ef2200b7` |
| `14-gemma4-e2b-ud-q2-k-xl` | `models/gemma4_e2b/unsloth_dynamic/gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf` | `241c50d86bdfe5e43307da87f559cd2416aacd67a8de46c15acc0105ef2200b7` |
| `15-lfm25-26b-q8-0` | `models/lfm25_26b/LFM2.5-2.6B-Q8_0.gguf` | `ea663864491de7ade391839479860ca95541f892f72665c73251fbd4643b1bef` |
| `16-lfm25-26b-q4-k-m` | `models/lfm25_26b/LFM2.5-2.6B-Q4_K_M.gguf` | `ea663864491de7ade391839479860ca95541f892f72665c73251fbd4643b1bef` |

The native-template hashes are per template string, so identical hashes here mean identical embedded template text across those quantizations. They do not verify identical model behavior.

## What b11457 flags do

The pinned source is `tools/llama.cpp/llama.cpp-5ad1c5da0ad7f6176256b823925aad19134f0263` (the b11457 commit recorded in `manifests/runtime_asset_hashes_120.json`).

- `common/arg.cpp:3700-3708`: `--reasoning off` sets `enable_reasoning = 0` and adds `enable_thinking=false` to the default template kwargs. Server initialization then computes effective thinking as “reasoning not explicitly off” **and** “the template supports thinking” (`tools/server/server-context.cpp:1593-1618`; support probe in `common/chat.cpp:358-370`).
- `common/arg.cpp:3544-3558`: `--chat-template-kwargs` writes directly into the same default kwargs map. For `enable_thinking`, b11457 logs that this setting is deprecated and points to `--reasoning on/off`. For templates that inspect `enable_thinking`, both settings convey false. `tools/server/server-common.cpp:1397-1411` also shows request kwargs are merged over server defaults and parsed into the template input.
- `--reasoning-format none` is a separate response-parser setting. The b11457 description says it leaves thoughts unparsed in `message.content` (`common/arg.cpp:3687-3698`, `tools/server/README.md:232`). It does not stop generation; it can leave the raw thought text visible in content. `deepseek` moves parsed thought text into `reasoning_content`; that changes the response field, not the generation prompt.
- `--reasoning-budget 0` is a generation-time token constraint, not a response parser. The CLI documents zero as “immediate end” (`common/arg.cpp:3729-3736`). For LFM2, its parser supplies `<think>` and `</think>` as the start and end tags (`common/parsers/lfm2.cpp:23-25,46-47`); the server forwards these plus the budget (`tools/server/server-common.cpp:1454-1468`). The sampler replays prompt tokens, switches to forcing as soon as it sees the start tag with zero budget, and forces the configured end tag (`common/sampling.cpp:314-326`, `common/reasoning-budget.cpp:80-89,166-184`; the end tag is configured at `tools/server/server-schema.cpp:398-430`). This is a static source conclusion; it was not exercised against a running server.

## Per-family finding

| Family and included variants | Native-template behavior | Source-based conclusion |
|---|---|---|
| Qwen3.5 2B (3 GGUFs) | Template SHA `273d…2d80`; generation branch opens `<think>` only when `enable_thinking` is true, and otherwise emits an empty `<think>…</think>` block. | **Template-level off switch exists.** `--reasoning off` or `enable_thinking=false` selects the no-thinking prompt branch. |
| Qwen3.5 4B (2 GGUFs) | Template SHA `a4ae…f715`; false emits the empty block; the other branch opens `<think>`. | **Template-level off switch exists.** Explicit false is material because this template's fallback branch opens thinking. |
| MiniCPM5 (3 GGUFs) | Template SHA `cc94…9fcf`; when false, the generation prompt emits `<think>\n\n</think>\n\n`; when true it opens `<think>`. | **Template-level off switch exists.** Explicit false closes the thinking section before generation continues. |
| Gemma 4 official QAT (1 GGUF) | Template SHA `0a2c…c5b5`; it defaults `enable_thinking` to false and emits the `<|think|>` marker only inside the enabled branch. | **Template-level off switch exists.** The native default is already off; explicit false makes the choice clear. |
| Gemma 4 Unsloth Dynamic (2 GGUFs) | Shared template SHA `241c…00b7`; same `enable_thinking` default/conditional marker behavior. | **Template-level off switch exists.** Explicit false selects the no-thinking branch. |
| LFM2.5 1.2B Instruct (3 GGUFs) | Template SHA `f05b…8176`; it defines `keep_past_thinking` (default false) for prior assistant messages, but has no `enable_thinking` branch. Its generation prompt ends with `<|im_start|>assistant\n`. | **No native generation-mode switch found.** `--reasoning off`/`enable_thinking=false` has no corresponding branch to select. `keep_past_thinking=false` strips old tagged thinking from conversation history only. The LFM2 parser can identify tagged `<think>` output, but `reasoning_format` controls whether it extracts that text; that is parsing, not prevention (`common/parsers/lfm2.cpp:51-53,67-80`). |
| LFM2.5 2.6B (2 GGUFs) | Template SHA `ea66…b1bef`; it defines `preserve_thinking` for prior messages and unconditionally ends the generation prompt with `<|im_start|>assistant\n<think>`. No `enable_thinking` branch. | **`--reasoning off` alone does not close this native prefix.** A source-supported generation constraint is `--reasoning-budget 0`: because the prefilling prompt ends with `<think>`, b11457's budget sampler should force `</think>` as the first generated token. This closes the explicit reasoning section without replacing the template or changing response parsing. |

## Limits

These findings classify template switches and the b11457 sampler's documented mechanics. They do not claim that a model cannot reason internally, that a model will never produce untagged reasoning in an answer, or that source-level budget behavior has been empirically validated for these GGUFs. The generation-budget conclusion for LFM2.6 follows from the pinned code path and native prompt suffix only; no runtime or generation test was run.
