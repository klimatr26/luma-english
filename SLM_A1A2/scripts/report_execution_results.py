"""Create auditable, read-only evaluation reports for authorized scopes.

This script never starts a server, makes a network request, retries an attempt,
or reads the final test set. It binds every run to the pinned benchmark and
manifest bytes, invokes ``evaluate_benchmark_120.py`` separately for each
configuration with exact full parsed and RAW case coverage, and keeps the
120-case and 40-case result trees separate.

Reports are written only under the selected result tree's ``evaluations`` and
``reports`` directories. Incomplete collection is represented explicitly in
the full expected case/configuration matrix; ``--require-complete`` can be
used to refuse a consolidated report until each expected case has a parsed row
bound to a final exact RAW attempt. A recorded technical failure counts as a
collected row and remains visible as such.

All scores are provisional strict-match proxies. This script supplies no
human evaluations; semantic correctness, meaning preservation, and
explanation quality remain unconfirmed until independently judged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNNER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = RUNNER_DIR.parent
EVALUATOR = RUNNER_DIR / "scripts" / "evaluate_benchmark_120.py"
MANIFEST = RUNNER_DIR / "manifests" / "experiment_manifest_120.json"
AUTHORIZATION = RUNNER_DIR / "manifests" / "main_execution_authorization_20261011.json"
EXPANSION_AUTHORIZATION = RUNNER_DIR / "manifests" / "main_execution_expansion_20261011.json"
CURRENT16_VALIDATION = RUNNER_DIR / "benchmark_40_archive" / "current16_extension_validation.json"
PHASE1_BASELINE = RUNNER_DIR / "benchmark_40_archive" / "phase1_baseline_hashes.json"
PINNED_MANIFEST_SHA256 = "8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255"
PINNED_PHASE1_BASELINE_SHA256 = "f2d2d4b081d7afac723178aabc805f618b48ed1289b9f131ce7f5bc08b93989f"
EXPECTED_BENCHMARK_SHA256 = {
    "results_120": "07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9",
    "results_40_lfm26": "a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9",
    "results_40_current_16": "a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9",
}
AUTHORIZATION_PATHS = {
    "results_120": AUTHORIZATION,
    "results_40_lfm26": AUTHORIZATION,
    "results_40_current_16": EXPANSION_AUTHORIZATION,
}
VALIDATION_PATHS = {"results_40_current_16": CURRENT16_VALIDATION}
SCOPE_AUTH_KEYS = {
    "results_120": "development",
    "results_40_lfm26": "phase1_extension",
    "results_40_current_16": "phase1_extension",
}
SCOPE_MANIFEST_LABELS = {
    "results_120": "development_120",
    "results_40_lfm26": "phase1_40_lfm26_extension",
    # The frozen manifest was intentionally not edited for this new authorized
    # run; all 16 current configurations carry development_120 support.
    "results_40_current_16": "development_120",
}
SCOPE_IDS = {"results_40_current_16": "phase1_40_current_16"}
SCOPE_CASE_COUNTS = {
    "results_120": 120,
    "results_40_lfm26": 40,
    "results_40_current_16": 40,
}
SCOPE_PLANNED_ROWS = {
    "results_120": 1920,
    "results_40_lfm26": 80,
    "results_40_current_16": 640,
}
SCOPE_CONFIG_COUNTS = {
    "results_120": 16,
    "results_40_lfm26": 2,
    "results_40_current_16": 16,
}
BENCHMARKS = {
    "results_120": RUNNER_DIR / "benchmark_development_120_v1.json",
    "results_40_lfm26": RUNNER_DIR / "benchmark_smoke_test_v2.json",
    "results_40_current_16": RUNNER_DIR / "benchmark_smoke_test_v2.json",
}
RESULT_DIRS = {
    "results_120": RUNNER_DIR / "results_120",
    "results_40_lfm26": RUNNER_DIR / "results_40_lfm26",
    "results_40_current_16": RUNNER_DIR / "results_40_current_16",
}


class ReportError(RuntimeError):
    """Input identity or report-integrity check failed."""


@dataclass(frozen=True)
class ScopeInventory:
    scope: str
    benchmark_path: Path
    result_dir: Path
    benchmark_sha256: str
    manifest_sha256: str
    cases: list[dict[str, Any]]
    configurations: list[dict[str, Any]]

    @property
    def case_ids(self) -> list[str]:
        return [str(case.get("id", case.get("case_id", ""))) for case in self.cases]

    @property
    def config_ids(self) -> list[str]:
        return [str(config.get("config_id", config.get("id", "")))
                for config in self.configurations]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportError(f"Cannot read JSON input {path}: {exc}") from exc


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ReportError(f"Cannot read JSONL input {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReportError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ReportError(f"Expected a JSON object at {path}:{line_no}")
        rows.append(row)
    return rows


def _case_list(data: Any, source: Path) -> list[dict[str, Any]]:
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or any(not isinstance(c, dict) for c in cases):
        raise ReportError(f"Benchmark {source} must contain a list of case objects")
    ids = [c.get("id", c.get("case_id")) for c in cases]
    if any(not isinstance(cid, str) or not cid for cid in ids):
        raise ReportError(f"Benchmark {source} contains a missing or invalid case ID")
    if len(ids) != len(set(ids)):
        raise ReportError(f"Benchmark {source} contains duplicate case IDs")
    return cases


def validate_scope_binding(*, scope: str, benchmark_sha256: str,
                           manifest_sha256: str,
                           expected_config_ids: list[str],
                           manifest_config_ids: list[str]) -> None:
    """Fail closed when scope identities or the full config matrix drift."""
    if scope not in EXPECTED_BENCHMARK_SHA256:
        raise ReportError(f"Unknown result scope {scope!r}")
    if benchmark_sha256.lower() != EXPECTED_BENCHMARK_SHA256[scope]:
        raise ReportError(f"{scope} benchmark SHA differs from its pinned value")
    if manifest_sha256.lower() != PINNED_MANIFEST_SHA256:
        raise ReportError("Manifest SHA differs from the pinned execution manifest")
    if len(expected_config_ids) != len(set(expected_config_ids)):
        raise ReportError("Authorization contains duplicate configuration IDs")
    if len(manifest_config_ids) != len(set(manifest_config_ids)):
        raise ReportError("Manifest contains duplicate configuration IDs")
    if expected_config_ids != manifest_config_ids:
        raise ReportError("Expected configuration matrix differs from the pinned manifest scope")


def validate_current16_validation_record(record: Any, *,
                                         benchmark_sha256: str,
                                         manifest_sha256: str,
                                         config_ids: list[str],
                                         phase1_baseline_sha256: str,
                                         authorization_sha256: str) -> None:
    """Bind the new 40x16 scope to its independent validation record."""
    if not isinstance(record, dict):
        raise ReportError("Current-16 validation record must be a JSON object")
    expected_fields = {
        "status": "VALIDATED_PENDING_USER_APPROVAL",
        "scope_id": SCOPE_IDS["results_40_current_16"],
        "benchmark_sha256": benchmark_sha256,
        "manifest_sha256": manifest_sha256,
        "case_count": 40,
        "planned_rows": 640,
        "config_ids": config_ids,
        "expansion_authorization_sha256": authorization_sha256,
    }
    for key, expected in expected_fields.items():
        if record.get(key) != expected:
            raise ReportError(f"Current-16 validation record has conflicting {key}")
    recorded_baseline_sha = record.get(
        "phase1_baseline_record_sha256", record.get("phase1_baseline_sha256"))
    if recorded_baseline_sha != phase1_baseline_sha256:
        raise ReportError("Current-16 validation record does not bind the pinned Phase 1 baseline")


def load_scope_inventory(scope: str) -> ScopeInventory:
    if scope not in BENCHMARKS:
        raise ReportError(f"Unknown result scope {scope!r}")
    benchmark_path = BENCHMARKS[scope]
    benchmark_sha = sha256_file(benchmark_path)
    manifest_sha = sha256_file(MANIFEST)
    authorization_path = AUTHORIZATION_PATHS[scope]
    authorization = load_json(authorization_path)
    manifest = load_json(MANIFEST)
    benchmark = load_json(benchmark_path)
    auth_key = SCOPE_AUTH_KEYS[scope]
    auth_scope = authorization.get(auth_key) if isinstance(authorization, dict) else None
    expected_ids = auth_scope.get("config_ids") if isinstance(auth_scope, dict) else None
    if (not isinstance(expected_ids, list)
            or any(not isinstance(cid, str) for cid in expected_ids)):
        raise ReportError(f"Authorization is missing the {auth_key} configuration list")
    if len(expected_ids) != SCOPE_CONFIG_COUNTS[scope]:
        raise ReportError(f"Authorization configuration count differs from the {scope} matrix")
    if authorization.get("manifest_sha256") != PINNED_MANIFEST_SHA256:
        raise ReportError("Authorization record does not bind the pinned manifest SHA")
    if not isinstance(auth_scope, dict) or auth_scope.get("benchmark_sha256") != benchmark_sha:
        raise ReportError("Authorization record does not bind the current scope benchmark SHA")
    configurations = manifest.get("configurations") if isinstance(manifest, dict) else None
    if not isinstance(configurations, list) or any(not isinstance(c, dict) for c in configurations):
        raise ReportError("Pinned manifest must contain configuration objects")
    all_manifest_ids = [c.get("config_id", c.get("id")) for c in configurations]
    if any(not isinstance(cid, str) or not cid for cid in all_manifest_ids):
        raise ReportError("Manifest contains a missing or invalid configuration ID")
    config_by_id = {c.get("config_id", c.get("id")): c for c in configurations}
    if len(config_by_id) != len(configurations):
        raise ReportError("Manifest contains duplicate configuration IDs")
    unknown = [cid for cid in expected_ids if cid not in config_by_id]
    if unknown:
        raise ReportError(f"Authorized scope names unknown manifest configurations: {unknown}")
    label = SCOPE_MANIFEST_LABELS[scope]
    scoped_configs = [c for c in configurations
                      if label in (c.get("supported_benchmarks") or [])]
    scoped_ids = [c.get("config_id", c.get("id")) for c in scoped_configs]
    validate_scope_binding(
        scope=scope, benchmark_sha256=benchmark_sha,
        manifest_sha256=manifest_sha, expected_config_ids=expected_ids,
        manifest_config_ids=scoped_ids)
    cases = _case_list(benchmark, benchmark_path)
    expected_n = SCOPE_CASE_COUNTS[scope]
    if len(cases) != expected_n:
        raise ReportError(f"{scope} benchmark has {len(cases)} cases; expected {expected_n}")
    if auth_scope.get("case_count") != expected_n:
        raise ReportError(f"Authorization case count differs from the {scope} benchmark")
    expected_matrix_rows = SCOPE_PLANNED_ROWS[scope]
    if auth_scope.get("planned_rows") != expected_matrix_rows:
        raise ReportError(f"Authorization planned row count differs from the {scope} matrix")
    if scope == "results_40_current_16":
        if authorization.get("scope") != SCOPE_IDS[scope]:
            raise ReportError("Current-16 authorization record has a conflicting scope ID")
        if auth_scope.get("scope_id") != SCOPE_IDS[scope]:
            raise ReportError("Current-16 authorization section has a conflicting scope ID")
        if auth_scope.get("output_dir") != RESULT_DIRS[scope].name:
            raise ReportError("Current-16 authorization output directory differs from its result tree")
        baseline_sha = authorization.get("phase1_baseline_sha256")
        if baseline_sha != PINNED_PHASE1_BASELINE_SHA256:
            raise ReportError("Current-16 authorization does not bind the pinned Phase 1 baseline")
        if sha256_file(PHASE1_BASELINE) != PINNED_PHASE1_BASELINE_SHA256:
            raise ReportError("Pinned Phase 1 baseline record SHA differs from its expected value")
        validation = load_json(VALIDATION_PATHS[scope])
        validate_current16_validation_record(
            validation, benchmark_sha256=benchmark_sha,
            manifest_sha256=manifest_sha, config_ids=expected_ids,
            phase1_baseline_sha256=baseline_sha,
            authorization_sha256=sha256_file(authorization_path))
    if (not isinstance(benchmark, dict)
            or benchmark.get("benchmark_sha256") not in (None, benchmark_sha)):
        raise ReportError("Benchmark metadata contains a conflicting benchmark SHA")
    return ScopeInventory(scope, benchmark_path, RESULT_DIRS[scope], benchmark_sha,
                          manifest_sha, cases, scoped_configs)


def _config_id(config: dict[str, Any]) -> str:
    return str(config.get("config_id", config.get("id", "")))


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_DIR.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _read_existing_jsonl(path: Path) -> list[dict[str, Any]]:
    return load_jsonl(path) if path.is_file() else []


def _run_evaluator(inventory: ScopeInventory, config: dict[str, Any],
                   parsed_path: Path, attempts_path: Path,
                   evals_path: Path, summary_path: Path,
                   invalid_cases_path: Path | None) -> None:
    command = [
        sys.executable, str(EVALUATOR),
        "--benchmark", str(inventory.benchmark_path),
        "--raw", str(parsed_path),
        "--attempts", str(attempts_path),
        "--manifest", str(MANIFEST),
        "--model", str(config.get("id", _config_id(config))),
        "--config", _config_id(config),
        "--out-evals", str(evals_path),
        "--out-summary", str(summary_path),
    ]
    if invalid_cases_path is not None:
        command.extend(["--invalid-cases", str(invalid_cases_path)])
    completed = subprocess.run(command, cwd=RUNNER_DIR, capture_output=True,
                               text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "no evaluator diagnostic").strip()
        raise ReportError(f"Evaluation failed for {_config_id(config)}: {detail}")


def _row_identity(row: dict[str, Any]) -> tuple[str, tuple[int, ...]] | None:
    provenance = row.get("response_provenance")
    if not isinstance(provenance, dict):
        return None
    resume_key = provenance.get("resume_key")
    trace = provenance.get("attempt_trace")
    if not isinstance(resume_key, str) or not isinstance(trace, list):
        return None
    if any(isinstance(item, bool) or not isinstance(item, int) for item in trace):
        return None
    return resume_key, tuple(trace)


def _attempt_group(attempt_rows: list[dict[str, Any]], resume_key: str,
                   trace: tuple[int, ...]) -> list[dict[str, Any]] | None:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in sorted((r for r in attempt_rows if r.get("resume_key") == resume_key),
                      key=lambda r: r.get("attempt", 0)):
        current.append(row)
        if row.get("disposition") == "final":
            groups.append(current)
            current = []
    for group in groups:
        if tuple(row.get("attempt") for row in group) == trace:
            return group
    return None


def _raw_transport(body: Any) -> dict[str, Any]:
    if not isinstance(body, str):
        payload = None
    else:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            payload = None
    if not isinstance(payload, dict):
        return {"body_json_valid": False, "finish_reason": None, "usage": None,
                "truncated": False, "completed": False}
    choices = payload.get("choices") or []
    finish = choices[0].get("finish_reason") if choices and isinstance(choices[0], dict) else None
    return {"body_json_valid": True, "finish_reason": finish,
            "usage": payload.get("usage"), "truncated": finish == "length",
            "completed": finish in ("stop", "eos", "end_of_turn")}


def _raw_outcome(row: dict[str, Any]) -> str:
    status = row.get("http_status")
    if status is None:
        return "transport_error"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return f"http_{status}"
    if not 200 <= status < 300:
        return f"http_{status}"
    try:
        body = json.loads(row.get("response_body_exact", ""))
    except (TypeError, json.JSONDecodeError):
        body = None
    return "ok" if isinstance(body, dict) else "invalid_body"


def _assert_parsed_telemetry_matches_raw(parsed: dict[str, Any],
                                         raw: dict[str, Any],
                                         group: list[dict[str, Any]]) -> dict[str, Any]:
    raw_fields = _raw_transport(raw.get("response_body_exact"))
    transport = parsed.get("transport")
    if not isinstance(transport, dict):
        raise ReportError("Selected runner row lacks nested transport telemetry")
    for key in ("body_json_valid", "finish_reason", "usage", "truncated", "completed"):
        if transport.get(key) != raw_fields[key]:
            raise ReportError(f"Parsed transport {key} differs from exact RAW body")
    raw_outcome = _raw_outcome(raw)
    if transport.get("outcome") != raw_outcome:
        raise ReportError("Parsed transport outcome differs from exact RAW status/body")
    latency_values = [r.get("latency_seconds") for r in group
                      if _number(r.get("latency_seconds"))]
    parsed_latency = transport.get("latency_seconds_total")
    if _number(parsed_latency) and latency_values:
        if not math.isclose(float(parsed_latency), sum(latency_values), rel_tol=1e-8, abs_tol=1e-8):
            raise ReportError("Parsed latency total differs from exact RAW attempt latencies")
    raw_fields["outcome"] = raw_outcome
    raw_fields["latency_seconds_total"] = (sum(latency_values)
                                             if len(latency_values) == len(group) else None)
    return raw_fields


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _count_values(values: list[Any], *, expected: int | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        label = "missing" if value is None else str(value)
        counts[label] += 1
    if expected is not None and expected > len(values):
        counts["missing"] += expected - len(values)
    return dict(sorted(counts.items()))


def _numeric_summary(values: list[Any], *, expected: int, unit: str) -> dict[str, Any]:
    clean = [float(v) for v in values if _number(v)]
    return {
        "unit": unit,
        "expected": expected,
        "observed": len(clean),
        "missing": max(0, expected - len(clean)),
        "min": min(clean) if clean else None,
        "median": statistics.median(clean) if clean else None,
        "mean": statistics.mean(clean) if clean else None,
        "max": max(clean) if clean else None,
    }


def _telemetry_summary(parsed_selected: list[dict[str, Any]],
                       raw_transport_selected: list[dict[str, Any]],
                       raw_attempt_rows: list[dict[str, Any]],
                       expected_cases: int) -> dict[str, Any]:
    transports = raw_transport_selected
    memories = [r.get("memory") if isinstance(r.get("memory"), dict) else {}
                for r in parsed_selected]

    usage_values: dict[str, list[Any]] = {
        "prompt_tokens": [], "completion_tokens": [], "total_tokens": [],
    }
    for transport in transports:
        usage = transport.get("usage")
        for key in usage_values:
            usage_values[key].append(usage.get(key) if isinstance(usage, dict) else None)

    numeric_fields = {
        "case_latency_seconds_total": [t.get("latency_seconds_total") for t in transports],
        "prompt_tokens": usage_values["prompt_tokens"],
        "completion_tokens": usage_values["completion_tokens"],
        "total_tokens": usage_values["total_tokens"],
        "server_peak_rss_bytes": [m.get("server_peak_rss_bytes") for m in memories],
        "runner_rss_bytes": [m.get("runner_rss_bytes") for m in memories],
        "gpu_used_bytes": [m.get("gpu_used_bytes") for m in memories],
    }
    units = {
        "case_latency_seconds_total": "seconds",
        "prompt_tokens": "tokens", "completion_tokens": "tokens", "total_tokens": "tokens",
        "server_peak_rss_bytes": "bytes", "runner_rss_bytes": "bytes", "gpu_used_bytes": "bytes",
    }
    summaries = {key: _numeric_summary(values, expected=expected_cases, unit=units[key])
                 for key, values in numeric_fields.items()}
    summaries["raw_attempt_latency_seconds"] = _numeric_summary(
        [r.get("latency_seconds") for r in raw_attempt_rows],
        expected=len(raw_attempt_rows), unit="seconds_per_http_attempt")
    raw_final_rows = [r for r in raw_attempt_rows if r.get("disposition") == "final"]
    return {
        "expected_cases": expected_cases,
        "parsed_selected_cases": len(parsed_selected),
        "numeric": summaries,
        "finish_reason_counts": _count_values([t.get("finish_reason") for t in transports], expected=expected_cases),
        "completed_counts": _count_values([t.get("completed") for t in transports], expected=expected_cases),
        "truncated_counts": _count_values([t.get("truncated") for t in transports], expected=expected_cases),
        "body_json_valid_counts": _count_values([t.get("body_json_valid") for t in transports], expected=expected_cases),
        "transport_outcome_counts": _count_values([t.get("outcome") for t in transports], expected=expected_cases),
        "raw_final_http_status_counts": _count_values([r.get("http_status") for r in raw_final_rows],
                                                       expected=len(raw_final_rows)),
        "raw_attempt_rows": len(raw_attempt_rows),
        "raw_retry_rows": sum(1 for r in raw_attempt_rows if r.get("disposition") == "retry"),
        "raw_selected_transport_by_case": [
            {"case_id": transport.get("case_id"),
             **{key: transport.get(key) for key in (
                 "outcome", "finish_reason", "usage", "truncated", "completed",
                 "body_json_valid", "latency_seconds_total")}}
            for transport in transports],
        "memory_sampling": {
            "server_rss_sampled_counts": _count_values([m.get("server_rss_sampled") for m in memories], expected=expected_cases),
            "server_rss_note_counts": _count_values([m.get("server_rss_note") for m in memories], expected=expected_cases),
            "runner_rss_sampled_counts": _count_values([m.get("runner_rss_sampled") for m in memories], expected=expected_cases),
            "runner_rss_note_counts": _count_values([m.get("runner_rss_note") for m in memories], expected=expected_cases),
            "gpu_sampled_counts": _count_values([m.get("gpu_sampled") for m in memories], expected=expected_cases),
            "gpu_note_counts": _count_values([m.get("gpu_note") for m in memories], expected=expected_cases),
            "gpu_scope_counts": _count_values([m.get("gpu_scope") for m in memories], expected=expected_cases),
            "gpu_unit_counts": _count_values([m.get("gpu_unit") for m in memories], expected=expected_cases),
            "memory_by_case": [
                {"case_id": row.get("case_id"), **_memory_projection(row)}
                for row in parsed_selected],
        },
        "provenance_note": (
            "HTTP status, response body, and per-attempt latency come from exact RAW attempts. "
            "Usage, finish_reason, truncation, completion, and body validity are re-derived "
            "from each selected exact RAW response body and checked against its parsed row. "
            "RSS and GPU fields are runner-sampled metadata from the selected parsed row; "
            "their source JSONL SHA-256 is indexed. GPU memory is device-wide and is not "
            "attributable to this process. Null or absent readings remain missing, not zero."
        ),
    }


def _memory_projection(parsed: dict[str, Any] | None) -> dict[str, Any]:
    memory = parsed.get("memory") if isinstance(parsed, dict) else None
    memory = memory if isinstance(memory, dict) else {}
    return {
        "server_peak_rss_bytes": memory.get("server_peak_rss_bytes"),
        "server_rss_sampled": memory.get("server_rss_sampled"),
        "server_rss_note": memory.get("server_rss_note"),
        "runner_rss_bytes": memory.get("runner_rss_bytes"),
        "runner_rss_sampled": memory.get("runner_rss_sampled"),
        "runner_rss_note": memory.get("runner_rss_note"),
        "gpu_used_bytes": memory.get("gpu_used_bytes"),
        "gpu_sampled": memory.get("gpu_sampled"),
        "gpu_unit": memory.get("gpu_unit"),
        "gpu_scope": memory.get("gpu_scope"),
        "gpu_note": memory.get("gpu_note"),
    }


def assert_complete_coverage(config_summaries: list[dict[str, Any]], expected_cases: int,
                            expected_config_ids: set[str] | list[str] | tuple[str, ...]) -> None:
    """Refuse finalization unless every expected config/case is represented."""
    ids = [row.get("config_id") for row in config_summaries]
    if len(ids) != len(set(ids)):
        raise ReportError("Complete coverage check received duplicate configuration summaries")
    expected_ids = set(expected_config_ids)
    if set(ids) != expected_ids:
        missing = sorted(expected_ids - set(ids))
        unexpected = sorted(set(ids) - expected_ids)
        raise ReportError("Complete coverage required; configuration identities differ from "
                          f"the full expected matrix (missing={missing}, unexpected={unexpected})")
    incomplete = [row["config_id"] for row in config_summaries
                  if row.get("selected_parsed_cases") != expected_cases
                  or row.get("verified_raw_final_cases", row.get("raw_final_cases")) != expected_cases]
    if incomplete:
        raise ReportError("Complete coverage required; these configurations lack a parsed row "
                          f"bound to a final RAW attempt for every case: {incomplete}")


def build_case_matrix(inventory: ScopeInventory,
                      evals_by_config: dict[str, dict[str, dict[str, Any]]],
                      selected_by_config: dict[str, dict[str, dict[str, Any]]],
                      raw_final_by_config: dict[str, dict[str, dict[str, Any]]],
                      attempts_by_config: dict[str, list[dict[str, Any]]],
                      config_statuses: dict[str, str],
                      parsed_candidates_by_config: dict[str, dict[str, list[dict[str, Any]]]]
                      | None = None,
                      raw_candidates_by_config: dict[str, dict[str, dict[str, Any]]]
                      | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected_case_ids = set(inventory.case_ids)
    for config in inventory.configurations:
        config_id = _config_id(config)
        evals = evals_by_config.get(config_id, {})
        selected = selected_by_config.get(config_id, {})
        finals = raw_final_by_config.get(config_id, {})
        attempts = attempts_by_config.get(config_id, [])
        candidates = (parsed_candidates_by_config or {}).get(config_id, {})
        raw_candidates = (raw_candidates_by_config or {}).get(config_id, {})
        if set(evals) - expected_case_ids or set(selected) - expected_case_ids:
            raise ReportError(f"Evaluation for {config_id} contains unknown case IDs")
        for case in inventory.cases:
            case_id = str(case.get("id", case.get("case_id", "")))
            evaluation = evals.get(case_id)
            parsed = selected.get(case_id)
            candidate_rows = candidates.get(case_id, [])
            final_raw = finals.get(case_id)
            raw_candidate = raw_candidates.get(case_id)
            status = config_statuses.get(config_id, "not_collected")
            if evaluation is None:
                if raw_candidate and len(candidate_rows) > 1:
                    case_status = "ambiguous_parsed_rows_pending_evaluation"
                elif raw_candidate and candidate_rows:
                    case_status = ("pending_full_coverage" if _raw_outcome(raw_candidate) == "ok"
                                   else "technical_failure_pending_full_coverage")
                elif raw_candidate:
                    case_status = ("raw_only_technical_failure_unverified"
                                   if _raw_outcome(raw_candidate) != "ok"
                                   else "raw_only_unverified")
                elif candidate_rows:
                    case_status = ("parsed_with_incomplete_RAW" if any(
                        row.get("case_id") == case_id for row in attempts)
                                   else "unbound_parsed_row")
                elif any(row.get("case_id") == case_id for row in attempts):
                    case_status = "attempt_incomplete"
                elif status == "not_collected":
                    case_status = "not_collected"
                else:
                    case_status = "not_recorded"
            elif evaluation.get("format", {}).get("parse_status") == "missing_output":
                case_status = "missing_output"
            else:
                outcome = ((parsed or {}).get("transport") or {}).get("outcome")
                case_status = "recorded" if outcome == "ok" else "technical_failure"

            raw_fields: dict[str, Any] = {}
            row_raw = final_raw if isinstance(final_raw, dict) else raw_candidate
            if parsed is None and isinstance(row_raw, dict):
                raw_fields = _raw_transport(row_raw.get("response_body_exact"))
                transport = {"outcome": _raw_outcome(row_raw)}
            if parsed is not None and evaluation is not None:
                identity = _row_identity(evaluation)
                if identity is None:
                    raise ReportError(f"Selected evaluation for {config_id}/{case_id} lacks RAW provenance")
                resume_key, trace = identity
                group = _attempt_group(attempts, resume_key, trace)
                if not group:
                    raise ReportError(f"Cannot bind selected row to RAW attempts for {config_id}/{case_id}")
                final_raw = group[-1]
                raw_fields = _assert_parsed_telemetry_matches_raw(parsed, final_raw, group)
            transport = parsed.get("transport") if isinstance(parsed, dict) else None
            transport = transport if isinstance(transport, dict) else {}
            if parsed is not None:
                transport = parsed.get("transport") if isinstance(parsed.get("transport"), dict) else {}
            elif isinstance(row_raw, dict):
                transport = {"outcome": _raw_outcome(row_raw)}
            usage = raw_fields.get("usage") if isinstance(raw_fields.get("usage"), dict) else {}
            metrics = evaluation.get("metrics_provisional") if isinstance(evaluation, dict) else {}
            metrics = metrics if isinstance(metrics, dict) else {}
            memory = _memory_projection(parsed)
            trace = parsed.get("attempt_trace") if isinstance(parsed, dict) else None
            http_status = row_raw.get("http_status") if isinstance(row_raw, dict) else None
            rows.append({
                "scope": inventory.scope,
                "benchmark_sha256": inventory.benchmark_sha256,
                "manifest_sha256": inventory.manifest_sha256,
                "config_id": config_id,
                "model_id": config.get("id", config_id),
                "family": config.get("family"),
                "quant": config.get("quant"),
                "case_id": case_id,
                "level": case.get("level"),
                "condition": case.get("condition"),
                "case_status": case_status,
                "raw_final_recorded": bool(row_raw),
                "raw_final_verified": bool(final_raw),
                "parsed_row_selected": parsed is not None,
                "parsed_row_candidates_n": len(candidate_rows),
                "raw_attempts_n": len(trace) if isinstance(trace, list) else None,
                "http_status": http_status,
                "transport_outcome": transport.get("outcome"),
                "transport_error_present": bool(final_raw and final_raw.get("error")),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "finish_reason": raw_fields.get("finish_reason"),
                "truncated": raw_fields.get("truncated"),
                "completed": raw_fields.get("completed"),
                "body_json_valid": raw_fields.get("body_json_valid"),
                "latency_seconds_total": (raw_fields.get("latency_seconds_total")
                                           if raw_fields else transport.get("latency_seconds_total")),
                **memory,
                "parse_status": (evaluation.get("format") or {}).get("parse_status") if evaluation else None,
                "schema_valid": evaluation.get("schema_valid") if evaluation else None,
                "verdict_provisional": evaluation.get("verdict_provisional") if evaluation else None,
                "verdict_final": evaluation.get("verdict_final") if evaluation else None,
                "provisional": evaluation.get("provisional") if evaluation else None,
                "needs_human_review": evaluation.get("needs_human_review") if evaluation else None,
                "tp": evaluation.get("tp") if evaluation else None,
                "fp": evaluation.get("fp") if evaluation else None,
                "fn": evaluation.get("fn") if evaluation else None,
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f0_5": metrics.get("f0_5"),
                "control_text_changed": evaluation.get("corrected_text_changed") if evaluation else None,
                "control_false_alarm": evaluation.get("control_false_alarm") if evaluation else None,
                "source_parsed_jsonl": (inventory.result_dir / "parsed" / config_id / "responses.jsonl").relative_to(inventory.result_dir).as_posix(),
                "source_attempts_jsonl": (inventory.result_dir / "raw" / config_id / "attempts.jsonl").relative_to(inventory.result_dir).as_posix(),
            })
    expected_rows = len(inventory.cases) * len(inventory.configurations)
    matrix_keys = [(row["config_id"], row["case_id"]) for row in rows]
    if len(rows) != expected_rows or len(set(matrix_keys)) != expected_rows:
        raise ReportError("Case/configuration matrix is not the exact unique expected cross-product")
    return rows


def _eval_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    return summary if isinstance(summary, dict) else {}


def _build_config_summary(config: dict[str, Any], summary: dict[str, Any] | None,
                          eval_rows: dict[str, dict[str, Any]],
                          raw_attempts: list[dict[str, Any]],
                          selected_rows: dict[str, dict[str, Any]],
                          raw_final_by_case: dict[str, dict[str, Any]],
                          expected_cases: int, config_status: str,
                          parsed_candidate_case_ids: set[str] | None = None,
                          parsed_candidate_rows: int = 0,
                          raw_candidate_by_case: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    config_id = _config_id(config)
    summary = _eval_summary(summary)
    selection = summary.get("response_selection", {})
    selected_case_count = sum(1 for row in eval_rows.values()
                              if isinstance(row.get("response_provenance"), dict))
    final_case_count = len(raw_final_by_case)
    raw_candidate_by_case = raw_candidate_by_case or raw_final_by_case
    parsed_candidate_case_ids = parsed_candidate_case_ids or {
        row.get("case_id") for row in eval_rows.values()
        if isinstance(row.get("response_provenance"), dict)}
    paired_case_count = len(parsed_candidate_case_ids & set(raw_candidate_by_case))
    missing_cases = max(0, expected_cases - paired_case_count)
    technical_count = sum(1 for row in raw_final_by_case.values()
                          if _raw_outcome(row) != "ok")
    technical_candidate_count = sum(1 for row in raw_candidate_by_case.values()
                                    if _raw_outcome(row) != "ok")
    raw_transport_selected = []
    for evaluation in eval_rows.values():
        identity = _row_identity(evaluation)
        if identity is None:
            continue
        case_id = evaluation.get("case_id")
        parsed = selected_rows.get(case_id)
        if parsed is None:
            raise ReportError(f"Selected evaluation for {config_id}/{case_id} has no parsed row")
        group = _attempt_group(raw_attempts, identity[0], identity[1])
        if not group:
            raise ReportError(f"Selected evaluation for {config_id}/{case_id} has no exact RAW group")
        raw_fields = _assert_parsed_telemetry_matches_raw(parsed, group[-1], group)
        raw_fields["case_id"] = case_id
        raw_transport_selected.append(raw_fields)
    telemetry = _telemetry_summary(list(selected_rows.values()), raw_transport_selected,
                                   raw_attempts, expected_cases)
    execution_complete = selected_case_count == expected_cases and final_case_count == expected_cases
    return {
        "config_id": config_id,
        "model_id": config.get("id", config_id),
        "family": config.get("family"),
        "quant": config.get("quant"),
        "status": ("complete" if execution_complete else "partial") if summary else config_status,
        "expected_cases": expected_cases,
        "parsed_case_candidates": len(parsed_candidate_case_ids),
        "parsed_rows_candidates": parsed_candidate_rows,
        "candidate_paired_cases": paired_case_count,
        "raw_final_candidates": len(raw_candidate_by_case),
        "raw_final_candidates_unverified": max(0, len(raw_candidate_by_case) - final_case_count),
        "verified_raw_final_cases": final_case_count,
        "selected_parsed_cases": selected_case_count,
        "raw_final_cases": final_case_count,
        "missing_cases": missing_cases,
        "technical_failure_cases": technical_count,
        "technical_failure_candidates": technical_candidate_count,
        "execution_complete": execution_complete,
        "provisional": True,
        "human_confirmed_cases": (summary.get("metadata") or {}).get("human_confirmed_cases", 0),
        "evaluation": summary,
        "response_selection": selection,
        "telemetry": telemetry,
    }


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _subgroup_rows(config_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    verdict_names = ("CORRECT", "PARTIAL", "INCORRECT", "INVALID_CASE")
    for config in config_summaries:
        summary = config.get("evaluation") or {}
        config_id = config["config_id"]
        by_level = summary.get("by_level") or {}
        for subgroup, block in by_level.items():
            detection = block.get("error_detection") or {}
            verdicts = block.get("verdicts") or {}
            rows.append({"config_id": config_id, "dimension": "level", "subgroup": subgroup,
                         "cases": block.get("cases"), **{v.lower(): verdicts.get(v, 0) for v in verdict_names},
                         "tp": detection.get("tp"), "fp": detection.get("fp"), "fn": detection.get("fn"),
                         "precision": detection.get("precision"), "recall": detection.get("recall"),
                         "f0_5": detection.get("f0_5")})
        for subgroup, block in (summary.get("by_taxonomy_recall") or {}).items():
            rows.append({"config_id": config_id, "dimension": "taxonomy", "subgroup": subgroup,
                         "tp": block.get("tp"), "fn": block.get("fn"), "recall": block.get("recall")})
        for subgroup, block in (summary.get("by_error_count") or {}).items():
            verdicts = block.get("verdicts") or {}
            rows.append({"config_id": config_id, "dimension": "gold_error_count", "subgroup": subgroup,
                         "cases": block.get("cases"), **{v.lower(): verdicts.get(v, 0) for v in verdict_names},
                         **{key: block.get(key) for key in ("tp", "fp", "fn", "precision", "recall", "f0_5")}})
        for subgroup, block in (summary.get("by_length_words") or {}).items():
            verdicts = block.get("verdicts") or {}
            rows.append({"config_id": config_id, "dimension": "student_text_length_words", "subgroup": subgroup,
                         "cases": block.get("cases"), **{v.lower(): verdicts.get(v, 0) for v in verdict_names}})
    return rows


def _configuration_csv_rows(config_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for config in config_summaries:
        summary = config.get("evaluation") or {}
        detection = summary.get("error_detection_incorrect_only") or {}
        controls = summary.get("controls") or {}
        fmt = summary.get("format") or {}
        verdicts = summary.get("verdicts_final") or {}
        telemetry = config["telemetry"].get("numeric", {})
        values = {
            "config_id": config["config_id"], "model_id": config["model_id"],
            "family": config.get("family"), "quant": config.get("quant"),
            "status": config.get("status"), "execution_complete": config["execution_complete"],
            "cases_expected": config["expected_cases"],
            "parsed_candidate_cases": config.get("parsed_case_candidates"),
            "parsed_candidate_rows": config.get("parsed_rows_candidates"),
            "candidate_paired_cases": config.get("candidate_paired_cases"),
            "raw_final_candidates_unverified": config.get("raw_final_candidates_unverified"),
            "verified_raw_final_cases": config.get("verified_raw_final_cases"),
            "selected_parsed_cases": config["selected_parsed_cases"],
            "raw_final_cases": config["raw_final_cases"],
            "missing_cases": config["missing_cases"],
            "technical_failure_cases": config["technical_failure_cases"],
            "technical_failure_candidates": config.get("technical_failure_candidates"),
            "correct": verdicts.get("CORRECT"), "partial": verdicts.get("PARTIAL"),
            "incorrect": verdicts.get("INCORRECT"), "invalid_case": verdicts.get("INVALID_CASE"),
            "tp": detection.get("tp"), "fp": detection.get("fp"), "fn": detection.get("fn"),
            "precision": detection.get("precision"), "recall": detection.get("recall"),
            "f0_5": detection.get("f0_5"),
            "ctmr_modified": controls.get("ctmr_modified"), "ctmr_rate": controls.get("ctmr_rate"),
            "ctmr_unobservable": controls.get("ctmr_unobservable"),
            "cfar_false_alarm": controls.get("cfar_false_alarm"), "cfar_rate": controls.get("cfar_rate"),
            "cfar_schema_unobservable": controls.get("cfar_schema_unobservable"),
            "fully_preserved": controls.get("fully_preserved"),
            "fully_preserved_rate": controls.get("fully_preserved_rate"),
            "parse_direct": (fmt.get("parse_status_counts") or {}).get("direct", 0 if summary else None),
            "parse_recoverable": (fmt.get("parse_status_counts") or {}).get("recoverable", 0 if summary else None),
            "parse_invalid": (fmt.get("parse_status_counts") or {}).get("invalid", 0 if summary else None),
            "schema_valid": fmt.get("schema_valid"),
            "strict_json_compliant": fmt.get("strict_json_compliant"),
            "needs_human_review": summary.get("needs_human_review"),
            "human_confirmed_cases": (summary.get("metadata") or {}).get("human_confirmed_cases"),
            "latency_median_seconds": (telemetry.get("case_latency_seconds_total") or {}).get("median"),
            "latency_observed_n": (telemetry.get("case_latency_seconds_total") or {}).get("observed"),
            "prompt_tokens_median": (telemetry.get("prompt_tokens") or {}).get("median"),
            "prompt_tokens_observed_n": (telemetry.get("prompt_tokens") or {}).get("observed"),
            "completion_tokens_median": (telemetry.get("completion_tokens") or {}).get("median"),
            "completion_tokens_observed_n": (telemetry.get("completion_tokens") or {}).get("observed"),
            "server_peak_rss_max_bytes": (telemetry.get("server_peak_rss_bytes") or {}).get("max"),
            "server_peak_rss_observed_n": (telemetry.get("server_peak_rss_bytes") or {}).get("observed"),
            "runner_rss_median_bytes": (telemetry.get("runner_rss_bytes") or {}).get("median"),
            "gpu_used_median_bytes": (telemetry.get("gpu_used_bytes") or {}).get("median"),
            "gpu_observed_n": (telemetry.get("gpu_used_bytes") or {}).get("observed"),
        }
        rows.append(values)
    return rows


def _md(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(_md(value) for value in row) + " |" for row in rows)
    return "\n".join(out)


def render_scope_report(inventory: ScopeInventory,
                        config_summaries: list[dict[str, Any]],
                        case_rows: list[dict[str, Any]], generated_utc: str) -> str:
    config_rows = _configuration_csv_rows(config_summaries)
    complete = sum(bool(row.get("execution_complete")) for row in config_summaries)
    total_cases = len(inventory.cases) * len(inventory.configurations)
    selected = sum(row.get("selected_parsed_cases", 0) for row in config_summaries)
    raw_final = sum(row.get("verified_raw_final_cases", 0) for row in config_summaries)
    raw_candidates = sum(row.get("raw_final_candidates_unverified", 0) for row in config_summaries)
    technical = sum(row.get("technical_failure_cases", 0) for row in config_summaries)
    technical_candidates = sum(row.get("technical_failure_candidates", 0) for row in config_summaries)
    missing = sum(row.get("missing_cases", 0) for row in config_summaries)
    status = "COMPLETE" if complete == len(config_summaries) else "INCOMPLETE"
    if inventory.scope == "results_40_current_16":
        scope_description = (
            "This is the newly authorized 40-case extension across all 16 current "
            "manifest configurations (640 expected cells). It includes the two LFM "
            "configurations once and supersedes the unstarted 80-cell LFM-only extension."
        )
    elif inventory.scope == "results_40_lfm26":
        scope_description = (
            "This legacy 80-cell LFM-only extension was superseded before execution by "
            "the 640-cell current-16 extension and is retained only as a separate result-tree path."
        )
    else:
        scope_description = "This is the 120-case development evaluation."
    table = [[r["config_id"], r["status"],
              f"{r['parsed_candidate_cases']}/{r['cases_expected']}",
              f"{r['selected_parsed_cases']}/{r['cases_expected']}",
              f"{r['verified_raw_final_cases']}/{r['cases_expected']}",
              r["raw_final_candidates_unverified"], r["missing_cases"],
              r["technical_failure_cases"], r["technical_failure_candidates"],
              r["correct"], r["partial"], r["incorrect"],
              r["precision"], r["recall"], r["f0_5"], r["ctmr_rate"], r["cfar_rate"],
              r["parse_direct"], r["parse_recoverable"], r["schema_valid"]]
             for r in config_rows]
    level_rows: list[list[Any]] = []
    for config in config_summaries:
        for subgroup, block in ((config.get("evaluation") or {}).get("by_level") or {}).items():
            detection = block.get("error_detection") or {}
            level_rows.append([config["config_id"], subgroup, block.get("cases"),
                               detection.get("precision"), detection.get("recall"),
                               detection.get("f0_5")])
    telemetry_rows = []
    for config in config_summaries:
        numeric = (config.get("telemetry") or {}).get("numeric", {})
        def med(key: str) -> Any:
            return (numeric.get(key) or {}).get("median")
        def observed(key: str) -> Any:
            return (numeric.get(key) or {}).get("observed", 0)
        telemetry_rows.append([
            config["config_id"], med("case_latency_seconds_total"),
            f"{observed('prompt_tokens')}/{config['expected_cases']}",
            f"{observed('completion_tokens')}/{config['expected_cases']}",
            (config.get("telemetry") or {}).get("finish_reason_counts"),
            med("server_peak_rss_bytes"), med("runner_rss_bytes"),
            med("gpu_used_bytes"), observed("gpu_used_bytes")])
    return f"""# {inventory.scope} evaluation report

Generated: {generated_utc} UTC

Collection status: **{status}**

Benchmark SHA-256: `{inventory.benchmark_sha256}`

Manifest SHA-256: `{inventory.manifest_sha256}`

## Scope and method

{scope_description} It binds to the frozen {len(inventory.cases)}-case benchmark and the authorized {len(inventory.configurations)}-configuration scope ({total_cases} expected case/configuration cells). The 120-case development run and separate 40-case result trees remain distinct. No inference, server, retry, or final-test access is performed here.

For each configuration whose parsed case IDs and syntactic final RAW candidates cover the entire benchmark, this report invokes `scripts/evaluate_benchmark_120.py` with that configuration ID, the frozen benchmark and manifest, the parsed JSONL, and its exact RAW attempts JSONL. That evaluator verifies SHA identity and the full retry authorization chain, then selects only the latest RAW-verified attempt group. In incomplete configurations, apparent RAW finals remain explicitly unverified candidates and are not counted as verified final rows or used to score cases. This report derives token usage and completion fields from each selected exact RAW response body and checks them against the parsed transport fields. RSS and GPU readings come from runner-sampled metadata on the selected parsed row; the source JSONL SHA is listed in `source_index.json`. GPU memory is a device-wide point sample, not attributable to this process.

All verdicts and automatic error-detection metrics below are **provisional string-based proxies**. No human-evaluation file is supplied. Semantic correctness, meaning preservation, and explanation quality remain unconfirmed. Technical-failure candidates in incomplete configurations are shown separately from evaluator-verified technical failures; missing or unpaired case/configuration cells remain explicit in the matrix. An incomplete run must not be interpreted as a complete comparison.

## Collection and configuration results

Parsed candidates: {sum(row.get('parsed_rows_candidates', 0) for row in config_summaries)} rows across {sum(row.get('parsed_case_candidates', 0) for row in config_summaries)}/{total_cases} distinct case/config cells. Evaluator-selected parsed rows: {selected}/{total_cases}. Verified final RAW records: {raw_final}/{total_cases}; unverified final RAW candidates: {raw_candidates}. Unpaired or missing case/config cells: {missing}. Verified technical failures: {technical}; technical-failure candidates including unverified partial RAW: {technical_candidates}. Configurations with full case coverage: {complete}/{len(config_summaries)}.

{_md_table(['Configuration', 'Status', 'Parsed candidates', 'Selected', 'Verified RAW final', 'Unverified RAW candidates', 'Unpaired/missing', 'Verified tech failures', 'Tech failure candidates', 'Correct', 'Partial', 'Incorrect', 'P', 'R', 'F0.5', 'CTMR', 'CFAR', 'Direct', 'Recoverable', 'Schema valid'], table)}

Precision, recall, and F0.5 are the evaluator's provisional strict-match error-detection measures over incorrect cases. CTMR is the control-text modification rate; CFAR is the control false-alarm rate. Unknown control outcomes are retained in the per-configuration evaluator summaries. Format counts distinguish direct JSON, recoverable JSON, and invalid parsing; schema-valid counts are separate.

## A1/A2 breakdown

{_md_table(['Configuration', 'Level', 'Cases', 'Precision', 'Recall', 'F0.5'], level_rows)}

Taxonomy recall, gold error-count buckets, and student-text-length buckets are recorded per configuration in `reports/subgroup_summary.csv` and the detailed `evaluations/<config_id>/summary.json` files. Verdict counts and metric denominators are retained in each summary.

## Runtime telemetry

{_md_table(['Configuration', 'Median case latency (s)', 'Prompt tokens observed', 'Completion tokens observed', 'Finish reasons', 'Max server RSS (bytes)', 'Median runner RSS (bytes)', 'Median GPU used (bytes)', 'GPU samples'], telemetry_rows)}

Telemetry sample counts and missing counts are explicit in `reports/telemetry_summary.json`. Server RSS is the sampled peak across server process and children during a request; runner RSS is a point sample at row derivation. GPU memory is device-wide. Missing values are null or absent with their recorded sampling note; they are never treated as zero. Exact per-case records and sampling notes are in `reports/case_matrix.csv`.

## Audit artifacts

`reports/case_matrix.csv` has exactly {total_cases} unique rows, one for every expected configuration/case pair, including not-collected and missing rows. `reports/configuration_summary.csv` contains one row per expected configuration. `reports/subgroup_summary.csv` contains the level, taxonomy, error-count, and length breakdowns. `reports/source_index.json` hashes the frozen inputs, runner JSONL sources, evaluator, report code, and generated artifacts. Per-case evaluations and per-configuration evaluator JSON summaries are under `evaluations/`.
"""


def _raw_final_index(attempts: list[dict[str, Any]], expected_case_ids: set[str],
                     config: dict[str, Any], benchmark_sha: str,
                     manifest_sha: str) -> dict[str, dict[str, Any]]:
    config_id = _config_id(config)
    model_sha = config.get("model_sha256")
    by_resume: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for row in attempts:
        required = {"resume_key", "attempt", "disposition", "benchmark_sha256",
                    "manifest_sha256", "model_sha256", "config_id", "case_id",
                    "http_status", "response_body_exact", "error"}
        allowed = required | {"latency_seconds", "recorded_utc", "retry_mode",
                              "retry_of_attempt", "retry_of_outcome"}
        missing = required - set(row)
        unexpected = set(row) - allowed
        if missing or unexpected:
            raise ReportError(f"RAW attempt schema mismatch for {config_id}: "
                              f"missing={sorted(missing)}, unexpected={sorted(unexpected)}")
        if row.get("config_id") != config_id:
            raise ReportError(f"RAW attempt file contains a different config than {config_id}")
        for field, expected in (("benchmark_sha256", benchmark_sha),
                                ("manifest_sha256", manifest_sha),
                                ("model_sha256", model_sha)):
            actual = row.get(field)
            if not isinstance(actual, str) or actual.lower() != str(expected).lower():
                raise ReportError(f"RAW {field} differs from the pinned identity for {config_id}")
        case_id = row.get("case_id")
        attempt_no = row.get("attempt")
        if case_id not in expected_case_ids:
            raise ReportError(f"RAW attempts contain unknown case ID {case_id!r}")
        if not isinstance(row.get("resume_key"), str) or not row["resume_key"]:
            raise ReportError(f"RAW resume key is invalid for {config_id}/{case_id}")
        expected_resume_key = ":".join([benchmark_sha, str(model_sha).lower(),
                                         manifest_sha.lower(), config_id, case_id])
        if row["resume_key"] != expected_resume_key:
            raise ReportError(f"RAW resume key does not bind identity for {config_id}/{case_id}")
        if isinstance(attempt_no, bool) or not isinstance(attempt_no, int) or attempt_no < 1:
            raise ReportError(f"RAW attempt number is invalid for {config_id}/{case_id}")
        status = row.get("http_status")
        if status is not None and (isinstance(status, bool) or not isinstance(status, int)
                                   or not 100 <= status <= 599):
            raise ReportError(f"RAW HTTP status is invalid for {config_id}/{case_id}")
        if not isinstance(row.get("response_body_exact"), str):
            raise ReportError(f"RAW response body is not exact text for {config_id}/{case_id}")
        if row.get("error") is not None and not isinstance(row.get("error"), str):
            raise ReportError(f"RAW error value is invalid for {config_id}/{case_id}")
        if row.get("latency_seconds") is not None and not _number(row.get("latency_seconds")):
            raise ReportError(f"RAW latency is invalid for {config_id}/{case_id}")
        key = (str(row.get("resume_key")), attempt_no)
        if key in seen:
            raise ReportError(f"Duplicate RAW attempt number for {config_id}/{case_id}")
        seen.add(key)
        if row.get("disposition") not in {"retry", "final"}:
            raise ReportError(f"RAW attempt disposition is invalid for {config_id}/{case_id}")
        by_resume[row["resume_key"]].append(row)
    finals: dict[str, dict[str, Any]] = {}
    for resume_key, resume_rows in by_resume.items():
        resume_rows.sort(key=lambda row: row["attempt"])
        attempts_seen = [row["attempt"] for row in resume_rows]
        if attempts_seen != list(range(1, attempts_seen[-1] + 1)):
            case_id = resume_rows[0]["case_id"]
            raise ReportError(f"RAW attempt numbers are not contiguous for {config_id}/{case_id}")
        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for row in resume_rows:
            current.append(row)
            if row["disposition"] == "final":
                groups.append(current)
                current = []
        # An unfinished trailing retry group means an older final response is
        # no longer the latest completed result for this resume key.
        if not current and groups:
            final = groups[-1][-1]
            finals[final["case_id"]] = final
    return finals


def _select_parsed_by_evals(parsed_rows: list[dict[str, Any]],
                            eval_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    parsed_by_identity: dict[tuple[str, tuple[int, ...]], list[dict[str, Any]]] = defaultdict(list)
    for parsed in parsed_rows:
        trace = parsed.get("attempt_trace")
        resume = parsed.get("resume_key")
        if isinstance(resume, str) and isinstance(trace, list):
            if any(isinstance(x, bool) or not isinstance(x, int) for x in trace):
                raise ReportError("Parsed row has an invalid attempt trace")
            parsed_by_identity[(resume, tuple(trace))].append(parsed)
    selected: dict[str, dict[str, Any]] = {}
    for evaluation in eval_rows:
        identity = _row_identity(evaluation)
        if identity is None:
            continue
        case_id = evaluation.get("case_id")
        matches = parsed_by_identity.get(identity, [])
        if len(matches) != 1:
            raise ReportError(f"Evaluation RAW provenance maps to {len(matches)} parsed rows for {case_id}")
        if case_id in selected:
            raise ReportError(f"Duplicate selected evaluation for case {case_id}")
        selected[case_id] = matches[0]
    return selected


def _parsed_candidate_index(parsed_rows: list[dict[str, Any]],
                            expected_case_ids: set[str],
                            config_id: str) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in parsed_rows:
        case_id = row.get("case_id", row.get("id"))
        if not isinstance(case_id, str) or not case_id:
            raise ReportError(f"Parsed runner row lacks a case ID for {config_id}")
        if case_id not in expected_case_ids:
            raise ReportError(f"Parsed runner rows contain unknown case ID {case_id!r} for {config_id}")
        candidates[case_id].append(row)
    return dict(candidates)


def _source_record(path: Path, role: str) -> dict[str, Any]:
    if not path.is_file():
        return {"path": _relative(path), "role": role, "exists": False,
                "size_bytes": None, "sha256": None}
    return {"path": _relative(path), "role": role, "exists": True,
            "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def execute(scope: str, *, invalid_cases_path: Path | None = None,
            require_complete: bool = False) -> dict[str, Any]:
    inventory = load_scope_inventory(scope)
    result_dir = inventory.result_dir
    evaluations_dir = result_dir / "evaluations"
    reports_dir = result_dir / "reports"
    evals_by_config: dict[str, dict[str, dict[str, Any]]] = {}
    selected_by_config: dict[str, dict[str, dict[str, Any]]] = {}
    raw_final_by_config: dict[str, dict[str, dict[str, Any]]] = {}
    raw_candidates_by_config: dict[str, dict[str, dict[str, Any]]] = {}
    attempts_by_config: dict[str, list[dict[str, Any]]] = {}
    parsed_by_config: dict[str, list[dict[str, Any]]] = {}
    parsed_candidates_by_config: dict[str, dict[str, list[dict[str, Any]]]] = {}
    summaries_by_config: dict[str, dict[str, Any]] = {}
    config_statuses: dict[str, str] = {}
    config_summaries: list[dict[str, Any]] = []
    input_records = [
        _source_record(inventory.benchmark_path, "frozen_benchmark"),
        _source_record(MANIFEST, "frozen_manifest"),
        _source_record(AUTHORIZATION_PATHS[scope], "execution_authorization"),
        _source_record(EVALUATOR, "evaluator_code"),
        _source_record(Path(__file__).resolve(), "report_orchestrator_code"),
    ]
    if scope in VALIDATION_PATHS:
        input_records.append(_source_record(VALIDATION_PATHS[scope], "scope_validation_record"))
        input_records.append(_source_record(PHASE1_BASELINE, "phase1_baseline_record"))
    if invalid_cases_path is not None:
        input_records.append(_source_record(invalid_cases_path, "shared_invalid_case_registry"))
    expected_case_ids = set(inventory.case_ids)

    for config in inventory.configurations:
        config_id = _config_id(config)
        parsed_path = result_dir / "parsed" / config_id / "responses.jsonl"
        attempts_path = result_dir / "raw" / config_id / "attempts.jsonl"
        parsed_rows = _read_existing_jsonl(parsed_path)
        attempt_rows = _read_existing_jsonl(attempts_path)
        parsed_by_config[config_id] = parsed_rows
        attempts_by_config[config_id] = attempt_rows
        parsed_candidates = _parsed_candidate_index(parsed_rows, expected_case_ids, config_id)
        parsed_candidates_by_config[config_id] = parsed_candidates
        input_records.extend([_source_record(parsed_path, f"parsed_runner_rows:{config_id}"),
                              _source_record(attempts_path, f"exact_raw_attempts:{config_id}")])
        raw_candidates = (_raw_final_index(attempt_rows, expected_case_ids, config,
                                           inventory.benchmark_sha256,
                                           inventory.manifest_sha256)
                          if attempt_rows else {})
        raw_candidates_by_config[config_id] = raw_candidates
        parsed_case_ids = set(parsed_candidates)
        raw_candidate_case_ids = set(raw_candidates)
        complete_inputs = (parsed_case_ids == expected_case_ids
                           and raw_candidate_case_ids == expected_case_ids)

        # A config is scored only when both independent inputs cover the exact
        # benchmark inventory. The evaluator then validates the full RAW retry
        # authorization chain and parsed-to-RAW provenance. For incomplete
        # configs, apparent RAW finals remain unverified candidates.
        if complete_inputs:
            config_statuses[config_id] = "evaluated"
            output_dir = evaluations_dir / config_id
            evals_path = output_dir / "case_evaluations.jsonl"
            summary_path = output_dir / "summary.json"
            _run_evaluator(inventory, config, parsed_path, attempts_path,
                           evals_path, summary_path, invalid_cases_path)
            eval_rows = load_jsonl(evals_path)
            eval_map = {row.get("case_id"): row for row in eval_rows}
            if len(eval_map) != len(eval_rows):
                raise ReportError(f"Evaluator emitted duplicate case IDs for {config_id}")
            if set(eval_map) != expected_case_ids:
                raise ReportError(f"Evaluator did not emit the exact case inventory for {config_id}")
            summary = load_json(summary_path)
            selected = _select_parsed_by_evals(parsed_rows, eval_rows)
            if set(selected) != expected_case_ids:
                raise ReportError(f"Evaluator did not select parsed RAW provenance for every case in {config_id}")
            evals_by_config[config_id] = eval_map
            selected_by_config[config_id] = selected
            summaries_by_config[config_id] = summary
            # At this point the existing evaluator has accepted all retry
            # histories and parsed-row bindings, so the syntactic candidates
            # are verified final RAW records for this configuration.
            raw_final_by_config[config_id] = raw_candidates
            config_summary = _build_config_summary(
                config, summary, eval_map, attempt_rows, selected, raw_candidates,
                len(inventory.cases), config_statuses[config_id],
                parsed_candidate_case_ids=parsed_case_ids,
                parsed_candidate_rows=len(parsed_rows),
                raw_candidate_by_case=raw_candidates)
            config_summaries.append(config_summary)
        else:
            raw_final_by_config[config_id] = {}
            if parsed_rows and attempt_rows:
                config_status = "partial"
            elif parsed_rows:
                config_status = "parsed_without_raw"
            elif attempt_rows:
                config_status = "raw_only_unverified"
            else:
                config_status = "not_collected"
            config_statuses[config_id] = config_status
            config_summaries.append(_build_config_summary(
                config, None, {}, attempt_rows, {}, raw_final_by_config[config_id],
                len(inventory.cases), config_statuses[config_id],
                parsed_candidate_case_ids=parsed_case_ids,
                parsed_candidate_rows=len(parsed_rows),
                raw_candidate_by_case=raw_candidates))

    case_rows = build_case_matrix(inventory, evals_by_config, selected_by_config,
                                  raw_final_by_config, attempts_by_config, config_statuses,
                                  parsed_candidates_by_config,
                                  raw_candidates_by_config)
    if require_complete:
        assert_complete_coverage(config_summaries, len(inventory.cases),
                                 set(inventory.config_ids))

    generated_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    all_matrix_rows = len(inventory.cases) * len(inventory.configurations)
    config_csv = _configuration_csv_rows(config_summaries)
    subgroup_csv = _subgroup_rows(config_summaries)
    telemetry = {row["config_id"]: row["telemetry"] for row in config_summaries}
    scope_summary = {
        "scope": scope,
        "generated_utc": generated_utc,
        "benchmark": {"path": _relative(inventory.benchmark_path),
                      "sha256": inventory.benchmark_sha256, "cases": len(inventory.cases)},
        "manifest": {"path": _relative(MANIFEST), "sha256": inventory.manifest_sha256},
        "planned": {"configurations": len(inventory.configurations),
                    "case_config_cells": all_matrix_rows},
        "coverage": {
            "parsed_candidate_case_cells": sum(r["parsed_case_candidates"] for r in config_summaries),
            "parsed_candidate_rows": sum(r["parsed_rows_candidates"] for r in config_summaries),
            "selected_parsed_cases": sum(r["selected_parsed_cases"] for r in config_summaries),
            "raw_final_candidate_cases_unverified": sum(r["raw_final_candidates_unverified"] for r in config_summaries),
            "verified_final_raw_cases": sum(r["verified_raw_final_cases"] for r in config_summaries),
            "candidate_paired_cases": sum(r["candidate_paired_cases"] for r in config_summaries),
            "unpaired_or_missing_case_cells": sum(r["missing_cases"] for r in config_summaries),
            "technical_failure_cases": sum(r["technical_failure_cases"] for r in config_summaries),
            "technical_failure_candidates": sum(r["technical_failure_candidates"] for r in config_summaries),
            "complete_configurations": sum(bool(r["execution_complete"]) for r in config_summaries),
            "status": ("COMPLETE" if all(r["execution_complete"] for r in config_summaries)
                      else "INCOMPLETE"),
        },
        "provisional_only": True,
        "human_evaluations_supplied": False,
        "case_matrix_rows": len(case_rows),
        "configuration_summaries": config_summaries,
    }
    case_fields = list(case_rows[0]) if case_rows else []
    config_fields = list(config_csv[0]) if config_csv else []
    subgroup_fields = ["config_id", "dimension", "subgroup", "cases",
                       "correct", "partial", "incorrect", "invalid_case",
                       "tp", "fp", "fn", "precision", "recall", "f0_5"]
    write_csv(reports_dir / "case_matrix.csv", case_rows, case_fields)
    write_csv(reports_dir / "configuration_summary.csv", config_csv, config_fields)
    write_csv(reports_dir / "subgroup_summary.csv", subgroup_csv, subgroup_fields)
    _atomic_json(reports_dir / "telemetry_summary.json", telemetry)
    _atomic_json(reports_dir / "scope_summary.json", scope_summary)
    report_text = render_scope_report(inventory, config_summaries, case_rows, generated_utc)
    report_path = reports_dir / "scope_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")

    generated_files = [path for base in (evaluations_dir, reports_dir)
                       for path in base.rglob("*") if path.is_file()
                       and path.name != "source_index.json"]
    source_index = {
        "scope": scope,
        "generated_utc": generated_utc,
        "source_inputs": input_records,
        "generated_artifacts": [_source_record(path, "generated_report_or_evaluation")
                                for path in sorted(generated_files)],
        "index_scope_note": "This index lists every generated evaluation/report artifact except itself to avoid a self-referential hash.",
    }
    _atomic_json(reports_dir / "source_index.json", source_index)
    return scope_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=tuple(BENCHMARKS), required=True,
                        help="Evaluate exactly one authorized result tree.")
    parser.add_argument("--invalid-cases", default=None,
                        help="Optional benchmark-SHA-bound shared invalidation registry.")
    parser.add_argument("--require-complete", action="store_true",
        help="Refuse consolidated reports unless every expected case has evaluator-verified parsed and final RAW coverage in every expected configuration.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = execute(args.scope,
                         invalid_cases_path=Path(args.invalid_cases).resolve()
                         if args.invalid_cases else None,
                         require_complete=args.require_complete)
    except ReportError as exc:
        print(f"report_execution_results: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"scope": result["scope"], "coverage": result["coverage"],
                      "case_matrix_rows": result["case_matrix_rows"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
