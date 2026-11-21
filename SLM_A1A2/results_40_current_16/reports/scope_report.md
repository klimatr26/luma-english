# results_40_current_16 evaluation report

Generated: 2026-10-11T19:03:15.923629Z UTC

Collection status: **COMPLETE**

Benchmark SHA-256: `a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9`

Manifest SHA-256: `8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255`

## Scope and method

This is the newly authorized 40-case extension across all 16 current manifest configurations (640 expected cells). It includes the two LFM configurations once and supersedes the unstarted 80-cell LFM-only extension. It binds to the frozen 40-case benchmark and the authorized 16-configuration scope (640 expected case/configuration cells). The 120-case development run and separate 40-case result trees remain distinct. No inference, server, retry, or final-test access is performed here.

For each configuration whose parsed case IDs and syntactic final RAW candidates cover the entire benchmark, this report invokes `scripts/evaluate_benchmark_120.py` with that configuration ID, the frozen benchmark and manifest, the parsed JSONL, and its exact RAW attempts JSONL. That evaluator verifies SHA identity and the full retry authorization chain, then selects only the latest RAW-verified attempt group. In incomplete configurations, apparent RAW finals remain explicitly unverified candidates and are not counted as verified final rows or used to score cases. This report derives token usage and completion fields from each selected exact RAW response body and checks them against the parsed transport fields. RSS and GPU readings come from runner-sampled metadata on the selected parsed row; the source JSONL SHA is listed in `source_index.json`. GPU memory is a device-wide point sample, not attributable to this process.

All verdicts and automatic error-detection metrics below are **provisional string-based proxies**. No human-evaluation file is supplied. Semantic correctness, meaning preservation, and explanation quality remain unconfirmed. Technical-failure candidates in incomplete configurations are shown separately from evaluator-verified technical failures; missing or unpaired case/configuration cells remain explicit in the matrix. An incomplete run must not be interpreted as a complete comparison.

## Collection and configuration results

Parsed candidates: 640 rows across 640/640 distinct case/config cells. Evaluator-selected parsed rows: 640/640. Verified final RAW records: 640/640; unverified final RAW candidates: 0. Unpaired or missing case/config cells: 0. Verified technical failures: 0; technical-failure candidates including unverified partial RAW: 0. Configurations with full case coverage: 16/16.

| Configuration | Status | Parsed candidates | Selected | Verified RAW final | Unverified RAW candidates | Unpaired/missing | Verified tech failures | Tech failure candidates | Correct | Partial | Incorrect | P | R | F0.5 | CTMR | CFAR | Direct | Recoverable | Schema valid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01-qwen35-2b-f16 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 8 | 4 | 28 | 0.1633 | 0.1356 | 0.1569 | 0.3000 | 0.1000 | 39 | 1 | 35 |
| 02-qwen35-2b-q8-0 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 8 | 3 | 29 | 0.2195 | 0.1525 | 0.2018 | 0.3000 | 0.1000 | 35 | 2 | 31 |
| 03-qwen35-2b-q4-k-m | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 9 | 7 | 24 | 0.1538 | 0.1356 | 0.1498 | 0.1000 | 0.1000 | 38 | 2 | 37 |
| 04-minicpm5-2b-f16 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 11 | 3 | 26 | 0.1707 | 0.1186 | 0.1570 | 0.0000 | 0.0000 | 29 | 3 | 31 |
| 05-minicpm5-2b-q8-0 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 12 | 3 | 25 | 0.1915 | 0.1525 | 0.1822 | 0.0000 | 0.1000 | 33 | 2 | 34 |
| 06-minicpm5-2b-q4-k-m | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 12 | 3 | 25 | 0.1556 | 0.1186 | 0.1464 | 0.0000 | 0.0000 | 40 | 0 | 39 |
| 07-lfm25-12b-bf16 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 8 | 2 | 30 | 0.0588 | 0.0339 | 0.0513 | 0.2000 | 0.1000 | 40 | 0 | 40 |
| 08-lfm25-12b-q8-0 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 8 | 2 | 30 | 0.0465 | 0.0339 | 0.0433 | 0.2000 | 0.1000 | 40 | 0 | 40 |
| 09-lfm25-12b-q4-k-m | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 9 | 2 | 29 | 0.1667 | 0.0339 | 0.0935 | 0.1000 | 0.0000 | 40 | 0 | 40 |
| 10-qwen35-4b-q8-0 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 16 | 8 | 16 | 0.4310 | 0.4237 | 0.4296 | 0.0000 | 0.0000 | 40 | 0 | 38 |
| 11-qwen35-4b-q4-k-m | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 18 | 6 | 16 | 0.4615 | 0.4068 | 0.4494 | 0.0000 | 0.0000 | 38 | 1 | 36 |
| 12-gemma4-e2b-qat-q4-0 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 8 | 4 | 28 | 0.2407 | 0.2203 | 0.2364 | 0.0000 | 0.5000 | 27 | 12 | 37 |
| 13-gemma4-e2b-ud-q4-k-xl | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 12 | 6 | 22 | 0.3158 | 0.3051 | 0.3136 | 0.0000 | 0.4000 | 7 | 33 | 37 |
| 14-gemma4-e2b-ud-q2-k-xl | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 0 | 0 | 40 | 0.0000 | 0.0000 | 0.0000 | 0.1000 | 0.2000 | 0 | 21 | 4 |
| 15-lfm25-26b-q8-0 | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 6 | 6 | 28 | 0.1607 | 0.1525 | 0.1590 | 0.0000 | 0.5000 | 0 | 38 | 38 |
| 16-lfm25-26b-q4-k-m | complete | 40/40 | 40/40 | 40/40 | 0 | 0 | 0 | 0 | 1 | 4 | 35 | 0.0746 | 0.0847 | 0.0765 | 0.0000 | 0.9000 | 0 | 38 | 38 |

Precision, recall, and F0.5 are the evaluator's provisional strict-match error-detection measures over incorrect cases. CTMR is the control-text modification rate; CFAR is the control false-alarm rate. Unknown control outcomes are retained in the per-configuration evaluator summaries. Format counts distinguish direct JSON, recoverable JSON, and invalid parsing; schema-valid counts are separate.

## A1/A2 breakdown

| Configuration | Level | Cases | Precision | Recall | F0.5 |
| --- | --- | --- | --- | --- | --- |
| 01-qwen35-2b-f16 | A1 | 20 | 0.2143 | 0.1765 | 0.2055 |
| 01-qwen35-2b-f16 | A2 | 20 | 0.0952 | 0.0800 | 0.0917 |
| 02-qwen35-2b-q8-0 | A1 | 20 | 0.2400 | 0.1765 | 0.2239 |
| 02-qwen35-2b-q8-0 | A2 | 20 | 0.1875 | 0.1200 | 0.1685 |
| 03-qwen35-2b-q4-k-m | A1 | 20 | 0.1923 | 0.1471 | 0.1812 |
| 03-qwen35-2b-q4-k-m | A2 | 20 | 0.1154 | 0.1200 | 0.1163 |
| 04-minicpm5-2b-f16 | A1 | 20 | 0.1111 | 0.0882 | 0.1056 |
| 04-minicpm5-2b-f16 | A2 | 20 | 0.2857 | 0.1600 | 0.2469 |
| 05-minicpm5-2b-q8-0 | A1 | 20 | 0.2000 | 0.1765 | 0.1948 |
| 05-minicpm5-2b-q8-0 | A2 | 20 | 0.1765 | 0.1200 | 0.1613 |
| 06-minicpm5-2b-q4-k-m | A1 | 20 | 0.1481 | 0.1176 | 0.1408 |
| 06-minicpm5-2b-q4-k-m | A2 | 20 | 0.1667 | 0.1200 | 0.1546 |
| 07-lfm25-12b-bf16 | A1 | 20 | 0.0769 | 0.0294 | 0.0581 |
| 07-lfm25-12b-bf16 | A2 | 20 | 0.0476 | 0.0400 | 0.0459 |
| 08-lfm25-12b-q8-0 | A1 | 20 | 0.0526 | 0.0294 | 0.0455 |
| 08-lfm25-12b-q8-0 | A2 | 20 | 0.0417 | 0.0400 | 0.0413 |
| 09-lfm25-12b-q4-k-m | A1 | 20 | 0.5000 | 0.0294 | 0.1190 |
| 09-lfm25-12b-q4-k-m | A2 | 20 | 0.1000 | 0.0400 | 0.0769 |
| 10-qwen35-4b-q8-0 | A1 | 20 | 0.4375 | 0.4118 | 0.4321 |
| 10-qwen35-4b-q8-0 | A2 | 20 | 0.4231 | 0.4400 | 0.4264 |
| 11-qwen35-4b-q4-k-m | A1 | 20 | 0.4643 | 0.3824 | 0.4452 |
| 11-qwen35-4b-q4-k-m | A2 | 20 | 0.4583 | 0.4400 | 0.4545 |
| 12-gemma4-e2b-qat-q4-0 | A1 | 20 | 0.3125 | 0.2941 | 0.3086 |
| 12-gemma4-e2b-qat-q4-0 | A2 | 20 | 0.1364 | 0.1200 | 0.1327 |
| 13-gemma4-e2b-ud-q4-k-xl | A1 | 20 | 0.3548 | 0.3235 | 0.3481 |
| 13-gemma4-e2b-ud-q4-k-xl | A2 | 20 | 0.2692 | 0.2800 | 0.2713 |
| 14-gemma4-e2b-ud-q2-k-xl | A1 | 20 | 0.0000 | 0.0000 | 0.0000 |
| 14-gemma4-e2b-ud-q2-k-xl | A2 | 20 | 0.0000 | 0.0000 | 0.0000 |
| 15-lfm25-26b-q8-0 | A1 | 20 | 0.2500 | 0.2647 | 0.2528 |
| 15-lfm25-26b-q8-0 | A2 | 20 | 0.0000 | 0.0000 | 0.0000 |
| 16-lfm25-26b-q4-k-m | A1 | 20 | 0.1282 | 0.1471 | 0.1316 |
| 16-lfm25-26b-q4-k-m | A2 | 20 | 0.0000 | 0.0000 | 0.0000 |

Taxonomy recall, gold error-count buckets, and student-text-length buckets are recorded per configuration in `reports/subgroup_summary.csv` and the detailed `evaluations/<config_id>/summary.json` files. Verdict counts and metric denominators are retained in each summary.

## Runtime telemetry

| Configuration | Median case latency (s) | Prompt tokens observed | Completion tokens observed | Finish reasons | Max server RSS (bytes) | Median runner RSS (bytes) | Median GPU used (bytes) | GPU samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01-qwen35-2b-f16 | 2.3138 | 40/40 | 40/40 | {'length': 1, 'stop': 39} | 4946542592.0000 | 34217984.0000 | 4952424448.0000 | 40 |
| 02-qwen35-2b-q8-0 | 1.6836 | 40/40 | 40/40 | {'length': 3, 'stop': 37} | 3095447552.0000 | 34461696.0000 | 3171942400.0000 | 40 |
| 03-qwen35-2b-q4-k-m | 1.3455 | 40/40 | 40/40 | {'length': 1, 'stop': 39} | 2367600640.0000 | 34805760.0000 | 2435842048.0000 | 40 |
| 04-minicpm5-2b-f16 | 1.9794 | 40/40 | 40/40 | {'stop': 40} | 5221873664.0000 | 35033088.0000 | 5784993792.0000 | 40 |
| 05-minicpm5-2b-q8-0 | 1.1409 | 40/40 | 40/40 | {'stop': 40} | 2977777664.0000 | 35209216.0000 | 3660578816.0000 | 40 |
| 06-minicpm5-2b-q4-k-m | 0.9282 | 40/40 | 40/40 | {'stop': 40} | 2003777536.0000 | 35434496.0000 | 2677014528.0000 | 40 |
| 07-lfm25-12b-bf16 | 0.5558 | 40/40 | 40/40 | {'stop': 40} | 2915442688.0000 | 35373056.0000 | 3509583872.0000 | 40 |
| 08-lfm25-12b-q8-0 | 0.3624 | 40/40 | 40/40 | {'stop': 40} | 1697583104.0000 | 35438592.0000 | 2404384768.0000 | 40 |
| 09-lfm25-12b-q4-k-m | 0.2455 | 40/40 | 40/40 | {'stop': 40} | 1172566016.0000 | 35760128.0000 | 1888485376.0000 | 40 |
| 10-qwen35-4b-q8-0 | 3.0887 | 40/40 | 40/40 | {'stop': 40} | 6335131648.0000 | 35315712.0000 | 5787090944.0000 | 40 |
| 11-qwen35-4b-q4-k-m | 2.4724 | 40/40 | 40/40 | {'length': 2, 'stop': 38} | 4795117568.0000 | 35381248.0000 | 4014997504.0000 | 40 |
| 12-gemma4-e2b-qat-q4-0 | 1.2727 | 40/40 | 40/40 | {'stop': 40} | 2216892416.0000 | 34541568.0000 | 2622488576.0000 | 40 |
| 13-gemma4-e2b-ud-q4-k-xl | 1.2575 | 40/40 | 40/40 | {'stop': 40} | 1943560192.0000 | 35497984.0000 | 2481979392.0000 | 40 |
| 14-gemma4-e2b-ud-q2-k-xl | 5.8016 | 40/40 | 40/40 | {'length': 2, 'stop': 38} | 1795657728.0000 | 34897920.0000 | 1630535680.0000 | 40 |
| 15-lfm25-26b-q8-0 | 2.0711 | 40/40 | 40/40 | {'stop': 40} | 3477051392.0000 | 35753984.0000 | 4063232000.0000 | 40 |
| 16-lfm25-26b-q4-k-m | 1.6937 | 40/40 | 40/40 | {'stop': 40} | 2268837888.0000 | 34684928.0000 | 2863661056.0000 | 40 |

Telemetry sample counts and missing counts are explicit in `reports/telemetry_summary.json`. Server RSS is the sampled peak across server process and children during a request; runner RSS is a point sample at row derivation. GPU memory is device-wide. Missing values are null or absent with their recorded sampling note; they are never treated as zero. Exact per-case records and sampling notes are in `reports/case_matrix.csv`.

## Audit artifacts

`reports/case_matrix.csv` has exactly 640 unique rows, one for every expected configuration/case pair, including not-collected and missing rows. `reports/configuration_summary.csv` contains one row per expected configuration. `reports/subgroup_summary.csv` contains the level, taxonomy, error-count, and length breakdowns. `reports/source_index.json` hashes the frozen inputs, runner JSONL sources, evaluator, report code, and generated artifacts. Per-case evaluations and per-configuration evaluator JSON summaries are under `evaluations/`.
