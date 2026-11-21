# results_120 evaluation report

Generated: 2026-10-11T19:03:13.190699Z UTC

Collection status: **COMPLETE**

Benchmark SHA-256: `07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9`

Manifest SHA-256: `8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255`

## Scope and method

This is the 120-case development evaluation. It binds to the frozen 120-case benchmark and the authorized 16-configuration scope (1920 expected case/configuration cells). The 120-case development run and separate 40-case result trees remain distinct. No inference, server, retry, or final-test access is performed here.

For each configuration whose parsed case IDs and syntactic final RAW candidates cover the entire benchmark, this report invokes `scripts/evaluate_benchmark_120.py` with that configuration ID, the frozen benchmark and manifest, the parsed JSONL, and its exact RAW attempts JSONL. That evaluator verifies SHA identity and the full retry authorization chain, then selects only the latest RAW-verified attempt group. In incomplete configurations, apparent RAW finals remain explicitly unverified candidates and are not counted as verified final rows or used to score cases. This report derives token usage and completion fields from each selected exact RAW response body and checks them against the parsed transport fields. RSS and GPU readings come from runner-sampled metadata on the selected parsed row; the source JSONL SHA is listed in `source_index.json`. GPU memory is a device-wide point sample, not attributable to this process.

All verdicts and automatic error-detection metrics below are **provisional string-based proxies**. No human-evaluation file is supplied. Semantic correctness, meaning preservation, and explanation quality remain unconfirmed. Technical-failure candidates in incomplete configurations are shown separately from evaluator-verified technical failures; missing or unpaired case/configuration cells remain explicit in the matrix. An incomplete run must not be interpreted as a complete comparison.

## Collection and configuration results

Parsed candidates: 1920 rows across 1920/1920 distinct case/config cells. Evaluator-selected parsed rows: 1920/1920. Verified final RAW records: 1920/1920; unverified final RAW candidates: 0. Unpaired or missing case/config cells: 0. Verified technical failures: 0; technical-failure candidates including unverified partial RAW: 0. Configurations with full case coverage: 16/16.

| Configuration | Status | Parsed candidates | Selected | Verified RAW final | Unverified RAW candidates | Unpaired/missing | Verified tech failures | Tech failure candidates | Correct | Partial | Incorrect | P | R | F0.5 | CTMR | CFAR | Direct | Recoverable | Schema valid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01-qwen35-2b-f16 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 30 | 17 | 73 | 0.1894 | 0.1667 | 0.1844 | 0.1000 | 0.1667 | 117 | 1 | 110 |
| 02-qwen35-2b-q8-0 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 33 | 14 | 73 | 0.1894 | 0.1667 | 0.1844 | 0.1000 | 0.1333 | 117 | 2 | 108 |
| 03-qwen35-2b-q4-k-m | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 33 | 15 | 72 | 0.1970 | 0.1733 | 0.1917 | 0.0333 | 0.1667 | 119 | 1 | 114 |
| 04-minicpm5-2b-f16 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 24 | 6 | 90 | 0.1667 | 0.1067 | 0.1498 | 0.0667 | 0.3333 | 79 | 11 | 86 |
| 05-minicpm5-2b-q8-0 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 26 | 11 | 83 | 0.2737 | 0.1733 | 0.2453 | 0.0000 | 0.3667 | 85 | 8 | 92 |
| 06-minicpm5-2b-q4-k-m | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 36 | 10 | 74 | 0.2017 | 0.1600 | 0.1917 | 0.0667 | 0.1000 | 118 | 0 | 116 |
| 07-lfm25-12b-bf16 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 19 | 6 | 95 | 0.0745 | 0.0467 | 0.0665 | 0.2333 | 0.2333 | 120 | 0 | 118 |
| 08-lfm25-12b-q8-0 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 18 | 8 | 94 | 0.0952 | 0.0667 | 0.0877 | 0.2333 | 0.2667 | 120 | 0 | 118 |
| 09-lfm25-12b-q4-k-m | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 21 | 2 | 97 | 0.0800 | 0.0133 | 0.0400 | 0.2667 | 0.0333 | 120 | 0 | 120 |
| 10-qwen35-4b-q8-0 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 43 | 20 | 57 | 0.3852 | 0.3467 | 0.3768 | 0.0667 | 0.1333 | 118 | 1 | 115 |
| 11-qwen35-4b-q4-k-m | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 44 | 14 | 62 | 0.3538 | 0.3067 | 0.3433 | 0.0667 | 0.1667 | 116 | 1 | 114 |
| 12-gemma4-e2b-qat-q4-0 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 37 | 17 | 66 | 0.3147 | 0.3000 | 0.3116 | 0.0000 | 0.4667 | 93 | 27 | 120 |
| 13-gemma4-e2b-ud-q4-k-xl | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 39 | 20 | 61 | 0.3082 | 0.3000 | 0.3065 | 0.0000 | 0.2333 | 20 | 100 | 116 |
| 14-gemma4-e2b-ud-q2-k-xl | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 0 | 0 | 120 | 0.0000 | 0.0000 | 0.0000 | 0.2000 | 0.1667 | 0 | 45 | 8 |
| 15-lfm25-26b-q8-0 | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 26 | 13 | 81 | 0.1571 | 0.1467 | 0.1549 | 0.0000 | 0.3667 | 0 | 115 | 112 |
| 16-lfm25-26b-q4-k-m | complete | 120/120 | 120/120 | 120/120 | 0 | 0 | 0 | 0 | 7 | 21 | 92 | 0.1406 | 0.1800 | 0.1471 | 0.0000 | 0.8333 | 0 | 117 | 114 |

Precision, recall, and F0.5 are the evaluator's provisional strict-match error-detection measures over incorrect cases. CTMR is the control-text modification rate; CFAR is the control false-alarm rate. Unknown control outcomes are retained in the per-configuration evaluator summaries. Format counts distinguish direct JSON, recoverable JSON, and invalid parsing; schema-valid counts are separate.

## A1/A2 breakdown

| Configuration | Level | Cases | Precision | Recall | F0.5 |
| --- | --- | --- | --- | --- | --- |
| 01-qwen35-2b-f16 | A1 | 60 | 0.1471 | 0.1333 | 0.1441 |
| 01-qwen35-2b-f16 | A2 | 60 | 0.2344 | 0.2000 | 0.2266 |
| 02-qwen35-2b-q8-0 | A1 | 60 | 0.1471 | 0.1333 | 0.1441 |
| 02-qwen35-2b-q8-0 | A2 | 60 | 0.2344 | 0.2000 | 0.2266 |
| 03-qwen35-2b-q4-k-m | A1 | 60 | 0.1549 | 0.1467 | 0.1532 |
| 03-qwen35-2b-q4-k-m | A2 | 60 | 0.2459 | 0.2000 | 0.2351 |
| 04-minicpm5-2b-f16 | A1 | 60 | 0.1765 | 0.1200 | 0.1613 |
| 04-minicpm5-2b-f16 | A2 | 60 | 0.1556 | 0.0933 | 0.1373 |
| 05-minicpm5-2b-q8-0 | A1 | 60 | 0.2353 | 0.1600 | 0.2151 |
| 05-minicpm5-2b-q8-0 | A2 | 60 | 0.3182 | 0.1867 | 0.2789 |
| 06-minicpm5-2b-q4-k-m | A1 | 60 | 0.2097 | 0.1733 | 0.2012 |
| 06-minicpm5-2b-q4-k-m | A2 | 60 | 0.1930 | 0.1467 | 0.1815 |
| 07-lfm25-12b-bf16 | A1 | 60 | 0.0833 | 0.0400 | 0.0685 |
| 07-lfm25-12b-bf16 | A2 | 60 | 0.0690 | 0.0533 | 0.0651 |
| 08-lfm25-12b-q8-0 | A1 | 60 | 0.1064 | 0.0667 | 0.0951 |
| 08-lfm25-12b-q8-0 | A2 | 60 | 0.0862 | 0.0667 | 0.0814 |
| 09-lfm25-12b-q4-k-m | A1 | 60 | 0.0909 | 0.0133 | 0.0420 |
| 09-lfm25-12b-q4-k-m | A2 | 60 | 0.0714 | 0.0133 | 0.0382 |
| 10-qwen35-4b-q8-0 | A1 | 60 | 0.3088 | 0.2800 | 0.3026 |
| 10-qwen35-4b-q8-0 | A2 | 60 | 0.4627 | 0.4133 | 0.4519 |
| 11-qwen35-4b-q4-k-m | A1 | 60 | 0.2576 | 0.2267 | 0.2507 |
| 11-qwen35-4b-q4-k-m | A2 | 60 | 0.4531 | 0.3867 | 0.4381 |
| 12-gemma4-e2b-qat-q4-0 | A1 | 60 | 0.2429 | 0.2267 | 0.2394 |
| 12-gemma4-e2b-qat-q4-0 | A2 | 60 | 0.3836 | 0.3733 | 0.3815 |
| 13-gemma4-e2b-ud-q4-k-xl | A1 | 60 | 0.2857 | 0.2667 | 0.2817 |
| 13-gemma4-e2b-ud-q4-k-xl | A2 | 60 | 0.3289 | 0.3333 | 0.3298 |
| 14-gemma4-e2b-ud-q2-k-xl | A1 | 60 | 0.0000 | 0.0000 | 0.0000 |
| 14-gemma4-e2b-ud-q2-k-xl | A2 | 60 | 0.0000 | 0.0000 | 0.0000 |
| 15-lfm25-26b-q8-0 | A1 | 60 | 0.1268 | 0.1200 | 0.1253 |
| 15-lfm25-26b-q8-0 | A2 | 60 | 0.1884 | 0.1733 | 0.1852 |
| 16-lfm25-26b-q4-k-m | A1 | 60 | 0.1158 | 0.1467 | 0.1209 |
| 16-lfm25-26b-q4-k-m | A2 | 60 | 0.1649 | 0.2133 | 0.1728 |

Taxonomy recall, gold error-count buckets, and student-text-length buckets are recorded per configuration in `reports/subgroup_summary.csv` and the detailed `evaluations/<config_id>/summary.json` files. Verdict counts and metric denominators are retained in each summary.

## Runtime telemetry

| Configuration | Median case latency (s) | Prompt tokens observed | Completion tokens observed | Finish reasons | Max server RSS (bytes) | Median runner RSS (bytes) | Median GPU used (bytes) | GPU samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01-qwen35-2b-f16 | 2.2152 | 120/120 | 120/120 | {'stop': 120} | 5119543296.0000 | 38273024.0000 | 4872732672.0000 | 120 |
| 02-qwen35-2b-q8-0 | 1.4436 | 120/120 | 120/120 | {'length': 1, 'stop': 119} | 3442393088.0000 | 38768640.0000 | 3090153472.0000 | 120 |
| 03-qwen35-2b-q4-k-m | 1.1830 | 120/120 | 120/120 | {'length': 1, 'stop': 119} | 2572144640.0000 | 38465536.0000 | 2348810240.0000 | 120 |
| 04-minicpm5-2b-f16 | 2.1123 | 120/120 | 120/120 | {'stop': 120} | 5263853568.0000 | 38567936.0000 | 5699010560.0000 | 120 |
| 05-minicpm5-2b-q8-0 | 1.2705 | 120/120 | 120/120 | {'stop': 120} | 3033892864.0000 | 37838848.0000 | 3581935616.0000 | 120 |
| 06-minicpm5-2b-q4-k-m | 0.8424 | 120/120 | 120/120 | {'stop': 120} | 2000871424.0000 | 38004736.0000 | 2594177024.0000 | 120 |
| 07-lfm25-12b-bf16 | 0.6669 | 120/120 | 120/120 | {'stop': 120} | 2948237312.0000 | 38322176.0000 | 3429892096.0000 | 120 |
| 08-lfm25-12b-q8-0 | 0.4207 | 120/120 | 120/120 | {'stop': 120} | 1745528832.0000 | 38498304.0000 | 2324692992.0000 | 120 |
| 09-lfm25-12b-q4-k-m | 0.2911 | 120/120 | 120/120 | {'stop': 120} | 1197010944.0000 | 38473728.0000 | 1803550720.0000 | 120 |
| 10-qwen35-4b-q8-0 | 2.5596 | 120/120 | 120/120 | {'length': 1, 'stop': 119} | 6290878464.0000 | 38129664.0000 | 5716836352.0000 | 120 |
| 11-qwen35-4b-q4-k-m | 2.0011 | 120/120 | 120/120 | {'length': 3, 'stop': 117} | 5601398784.0000 | 28905472.0000 | 4014997504.0000 | 120 |
| 12-gemma4-e2b-qat-q4-0 | 1.1420 | 120/120 | 120/120 | {'stop': 120} | 2311522304.0000 | 28971008.0000 | 2622488576.0000 | 120 |
| 13-gemma4-e2b-ud-q4-k-xl | 1.0468 | 120/120 | 120/120 | {'stop': 120} | 2057230336.0000 | 29124608.0000 | 2481979392.0000 | 120 |
| 14-gemma4-e2b-ud-q2-k-xl | 6.1439 | 120/120 | 120/120 | {'length': 6, 'stop': 114} | 1913929728.0000 | 29814784.0000 | 1630535680.0000 | 120 |
| 15-lfm25-26b-q8-0 | 1.9721 | 120/120 | 120/120 | {'length': 4, 'stop': 116} | 3564388352.0000 | 30087168.0000 | 4063232000.0000 | 120 |
| 16-lfm25-26b-q4-k-m | 1.7595 | 120/120 | 120/120 | {'length': 4, 'stop': 116} | 2424852480.0000 | 32256000.0000 | 2863661056.0000 | 120 |

Telemetry sample counts and missing counts are explicit in `reports/telemetry_summary.json`. Server RSS is the sampled peak across server process and children during a request; runner RSS is a point sample at row derivation. GPU memory is device-wide. Missing values are null or absent with their recorded sampling note; they are never treated as zero. Exact per-case records and sampling notes are in `reports/case_matrix.csv`.

## Audit artifacts

`reports/case_matrix.csv` has exactly 1920 unique rows, one for every expected configuration/case pair, including not-collected and missing rows. `reports/configuration_summary.csv` contains one row per expected configuration. `reports/subgroup_summary.csv` contains the level, taxonomy, error-count, and length breakdowns. `reports/source_index.json` hashes the frozen inputs, runner JSONL sources, evaluator, report code, and generated artifacts. Per-case evaluations and per-configuration evaluator JSON summaries are under `evaluations/`.
