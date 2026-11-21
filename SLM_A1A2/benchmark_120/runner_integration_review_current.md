# Runner/evaluator integration review

Review date: 2026-10-11

## Retry and evaluation contract

- The runner fsyncs every exact HTTP response body to `raw/<config_id>/attempts.jsonl` before it parses the body or writes a parsed row. RAW records carry the resume key, benchmark/model/manifest SHA values, attempt number, disposition, and retry provenance.
- Technical failures are retried only within the configured bounded retry count. A later invocation reopens an eligible technical failure only with `--retry-failed`; the new attempt group names the exact previous final attempt and outcome. Semantic failures are recorded once. HTTP 429 is recorded and stops the whole invocation immediately without retry; a later manual invocation is explicitly marked `rate_limit_resume`.
- Startup reconstructs state from RAW and rejects duplicate attempt numbers, gaps, foreign identities, malformed groups, unauthorized later groups, and checkpoint claims unsupported by RAW. Parsed retries remain separate rows; their attempt traces are not collapsed in the runner.
- Runner-produced rows now require the exact RAW attempt file at evaluation time, including singleton rows. The evaluator verifies each parsed trace, status/outcome, and response content against RAW. A singleton parsed row must match the latest authorized RAW attempt, so an older row cannot conceal a later retry. Duplicate rows must cover distinct authorized groups; the evaluator selects the one with the highest verified final attempt number and never compares response quality. Missing RAW, unauthorized retries, ambiguous groups, or mixed benchmark/model/manifest/config identities fail closed.
- Gold is not part of the request builder: the user message is formatted from `level`, `task`, and `student_text`; the API payload contains messages and manifest generation settings only. Gold remains in the local benchmark file. Synthetic request tests include a gold canary and assert it is absent from payloads.

## Readiness and LFM26 extension

- The 120-case runner expects 16 unique manifest configurations and reports a 1920-row matrix. Readiness must pass all 16 IDs and its top-level `manifest_sha256` must equal the exact current manifest bytes. Per-config hashes, when supplied, must also match; the 40-case extension requires exact model SHA values for all 16 entries.
- Launch policy checks `--parallel N` against `runtime.parallel_sequences` whenever that field is declared. The dedicated extension requires `runtime.parallel_sequences=1` across the manifest and verifies the two exact LFM26 entries, IDs, quantizations, model paths, ports, provenance revision, and extension scope.
- Before each production server spawn, the shared runner rehashes the manifest-selected GGUF and checks its declared byte size plus stable size/mtime/device/inode across hashing. It also requires the single `-m`/`--model` argv path to resolve to that SHA-bound manifest path. This detects asset replacement after readiness; it adds a full sequential disk read of each model immediately before its run.
- `run_benchmark_40_lfm26.py` is fixed to the Phase 1 v2 benchmark SHA, verifies the 24-file Phase 1 baseline inventory, requires the separately scoped 40-case validation record, checks the full 16/16 readiness report, and writes only to `results_40_lfm26`. It cannot select another benchmark, configuration, or output directory. It uses the same RAW/checkpoint/retry/429 implementation as the 120-case runner.

## Verification and limits

Executed with `SLM_A1A2/.venv/Scripts/python.exe`:

```text
python -m unittest scripts.test_run_benchmark_120 scripts.test_evaluate_benchmark_120 scripts.test_evaluation_safety scripts.test_run_benchmark_40_lfm26
Ran 76 tests ... OK
```

The extension execution test used a fake server/client, synthetic cases, temporary output, and 80 synthetic responses; no server process or network request was started. Python compilation and the extension runner `--help` command also succeeded.

The current manifest has 16 entries. Readiness has not passed: its first technical attempt stopped at the initial configuration because the server logger was not visible, and no generation occurred. The runner gates require a complete manifest-bound 16/16 readiness report, so neither the main nor extension preflight is claimed as passed; the parent is documenting and resolving this readiness state. No real runner preflight, benchmark dry-run with authorization, benchmark execution, model inference, final test access, or edits to Phase 1 files/results were performed.
