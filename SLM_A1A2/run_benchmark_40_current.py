"""Run the authorized 40-case Phase 1 extension across all 16 current models.

This runner is fixed to the frozen Phase 1 v2 benchmark, the exact current
16-configuration manifest and readiness snapshot, and the separate
``results_40_current_16`` tree. It uses the shared transport, RAW, checkpoint,
retry, and rate-limit behavior from ``run_benchmark_120.py`` without changing
the manifest, the original Phase 1 artifacts, or the 120-case result tree.
Importing this module or running preflight performs no inference and starts no
server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

RUNNER_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = RUNNER_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import run_benchmark_120 as shared  # noqa: E402

PHASE1_BENCHMARK = RUNNER_DIR / "benchmark_smoke_test_v2.json"
PHASE1_BASELINE = RUNNER_DIR / "benchmark_40_archive" / "phase1_baseline_hashes.json"
EXTENSION_VALIDATION = RUNNER_DIR / "benchmark_40_archive" / "current16_extension_validation.json"
EXPANSION_AUTHORIZATION = RUNNER_DIR / "manifests" / "main_execution_expansion_20261011.json"
MANIFEST = RUNNER_DIR / "manifests" / "experiment_manifest_120.json"
READINESS = RUNNER_DIR / "llama_cpp_readiness_report.json"
OUT_DIR = RUNNER_DIR / "results_40_current_16"

PHASE1_BENCHMARK_SHA256 = "a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9"
PHASE1_BASELINE_SHA256 = "f2d2d4b081d7afac723178aabc805f618b48ed1289b9f131ce7f5bc08b93989f"
PINNED_MANIFEST_SHA256 = "8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255"
PINNED_READINESS_SHA256 = "921ed2df2512edf6ccfb1634657eb07d1ac559bfe11b7732bb9c958a9c76e26a"
PINNED_EXPANSION_AUTHORIZATION_SHA256 = "fbf12e175fc14208f4514af126e5755bb58b514490e271b8dcb080137c4e7bbc"
EXPECTED_CASES = 40
CURRENT_SCOPE = "phase1_40_current_16"
EXPECTED_CONFIG_IDS = (
    "01-qwen35-2b-f16",
    "02-qwen35-2b-q8-0",
    "03-qwen35-2b-q4-k-m",
    "04-minicpm5-2b-f16",
    "05-minicpm5-2b-q8-0",
    "06-minicpm5-2b-q4-k-m",
    "07-lfm25-12b-bf16",
    "08-lfm25-12b-q8-0",
    "09-lfm25-12b-q4-k-m",
    "10-qwen35-4b-q8-0",
    "11-qwen35-4b-q4-k-m",
    "12-gemma4-e2b-qat-q4-0",
    "13-gemma4-e2b-ud-q4-k-xl",
    "14-gemma4-e2b-ud-q2-k-xl",
    "15-lfm25-26b-q8-0",
    "16-lfm25-26b-q4-k-m",
)
EXPECTED_MATRIX_ROWS = EXPECTED_CASES * len(EXPECTED_CONFIG_IDS)


class CurrentExtensionGateError(shared.GateError):
    """A current-model extension preflight check failed."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_phase1_baseline(root: Path = RUNNER_DIR, *,
                           baseline_path: Path = PHASE1_BASELINE,
                           expected_baseline_sha256: str = PHASE1_BASELINE_SHA256,
                           expected_benchmark_sha256: str = PHASE1_BENCHMARK_SHA256) -> dict:
    """Verify the original 24-file Phase 1 inventory without changing it."""
    baseline_path = Path(baseline_path)
    try:
        baseline_bytes = baseline_path.read_bytes()
        baseline = json.loads(baseline_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CurrentExtensionGateError(f"Cannot read Phase 1 integrity baseline: {exc}.") from exc
    baseline_sha = _sha256_bytes(baseline_bytes)
    if baseline_sha != expected_baseline_sha256:
        raise CurrentExtensionGateError("Phase 1 baseline record SHA differs from the pinned value.")
    records = baseline.get("files") if isinstance(baseline, dict) else None
    if not isinstance(records, list) or len(records) != 24:
        raise CurrentExtensionGateError("Phase 1 baseline must contain exactly 24 file records.")

    root = Path(root).resolve()
    seen: set[str] = set()
    benchmark_record = None
    for record in records:
        if not isinstance(record, dict):
            raise CurrentExtensionGateError("Phase 1 baseline has a non-object file record.")
        rel = record.get("path")
        size = record.get("size_bytes")
        digest_expected = record.get("sha256")
        if (not isinstance(rel, str) or not rel.strip() or rel in seen
                or not isinstance(size, int) or isinstance(size, bool) or size < 0
                or not isinstance(digest_expected, str) or len(digest_expected) != 64
                or any(ch not in "0123456789abcdef" for ch in digest_expected)):
            raise CurrentExtensionGateError("Phase 1 baseline has an invalid or duplicate record.")
        seen.add(rel)
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            raise CurrentExtensionGateError(f"Phase 1 baseline path escapes its root: {rel!r}.")
        try:
            before = path.stat()
            if not path.is_file() or before.st_size != size:
                raise CurrentExtensionGateError(f"Phase 1 artifact size mismatch or missing file: {rel}.")
            digest = shared.sha256_file(path)
            after = path.stat()
        except OSError as exc:
            raise CurrentExtensionGateError(f"Cannot verify Phase 1 artifact {rel!r}: {exc}.") from exc
        if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                or digest != digest_expected):
            raise CurrentExtensionGateError(f"Phase 1 artifact changed or hash mismatch: {rel}.")
        if rel == "benchmark_smoke_test_v2.json":
            benchmark_record = record

    if (benchmark_record is None
            or benchmark_record["sha256"] != expected_benchmark_sha256):
        raise CurrentExtensionGateError("Phase 1 v2 benchmark is not pinned by the baseline inventory.")
    return {"baseline_sha256": baseline_sha,
            "verified_files": len(records),
            "benchmark_sha256": benchmark_record["sha256"]}


def validate_expansion_authorization(record, *, authorization_sha256: str,
                                     manifest_sha256: str,
                                     benchmark_sha256: str,
                                     baseline_sha256: str) -> dict:
    """Require the separate user authorization for the expanded 16-config scope."""
    if not isinstance(record, dict):
        raise CurrentExtensionGateError("Expansion authorization must be a JSON object.")
    if authorization_sha256 != PINNED_EXPANSION_AUTHORIZATION_SHA256:
        raise CurrentExtensionGateError("Expansion authorization SHA differs from the pinned record.")
    if record.get("status") != "HUMAN_AUTHORIZED_CURRENT16_EXTENSION_NOT_STARTED":
        raise CurrentExtensionGateError("Expansion authorization is not in the accepted not-started state.")
    if record.get("scope") != CURRENT_SCOPE:
        raise CurrentExtensionGateError("Expansion authorization has the wrong scope.")
    if record.get("manifest_sha256") != manifest_sha256:
        raise CurrentExtensionGateError("Expansion authorization does not bind the exact manifest SHA.")
    if record.get("phase1_baseline_sha256") != baseline_sha256:
        raise CurrentExtensionGateError("Expansion authorization does not bind the Phase 1 baseline.")
    if (record.get("old_files_readonly") is not True
            or record.get("original_40_artifacts_read_only") is not True
            or record.get("frozen_manifest_changed") is not False
            or record.get("generation_changed") is not False
            or record.get("final_test_access_authorized") is not False):
        raise CurrentExtensionGateError("Expansion authorization must preserve the old files, manifest, generation, and final-test boundary.")
    scope = record.get("phase1_extension")
    if not isinstance(scope, dict):
        raise CurrentExtensionGateError("Expansion authorization lacks phase1_extension scope details.")
    expected = {
        "benchmark_sha256": benchmark_sha256,
        "case_count": EXPECTED_CASES,
        "planned_rows": EXPECTED_MATRIX_ROWS,
        "scope_id": CURRENT_SCOPE,
        "output_dir": OUT_DIR.name,
        "config_ids": list(EXPECTED_CONFIG_IDS),
    }
    for key, value in expected.items():
        if scope.get(key) != value:
            raise CurrentExtensionGateError(f"Expansion authorization phase1_extension.{key} differs from the fixed scope.")
    if record.get("planned_total_new_rows") != 2560:
        raise CurrentExtensionGateError("Expansion authorization does not bind the full 2560-row plan.")
    if (not isinstance(record.get("authorization_source"), str)
            or not record["authorization_source"].strip()
            or not isinstance(record.get("user_instruction"), str)
            or not record["user_instruction"].strip()):
        raise CurrentExtensionGateError("Expansion authorization lacks its direct-user source and instruction record.")
    return {"sha256": authorization_sha256, "scope_id": CURRENT_SCOPE,
            "benchmark_sha256": benchmark_sha256,
            "manifest_sha256": manifest_sha256,
            "config_ids": list(EXPECTED_CONFIG_IDS),
            "planned_rows": EXPECTED_MATRIX_ROWS}


def validate_current_extension_report(report, *, benchmark_sha256: str,
                                      manifest_sha256: str,
                                      baseline_sha256: str,
                                      authorization_sha256: str) -> dict:
    """Require a separate validation record tied to this exact new scope."""
    if not isinstance(report, dict):
        raise CurrentExtensionGateError("Current 16-config extension validation must be a JSON object.")
    if report.get("status") != "VALIDATED_PENDING_USER_APPROVAL":
        raise CurrentExtensionGateError("Current extension validation has not reached its accepted state.")
    expected = {
        "scope_id": CURRENT_SCOPE,
        "benchmark_sha256": benchmark_sha256,
        "manifest_sha256": manifest_sha256,
        "phase1_baseline_sha256": baseline_sha256,
        "case_count": EXPECTED_CASES,
        "planned_rows": EXPECTED_MATRIX_ROWS,
        "config_ids": list(EXPECTED_CONFIG_IDS),
        "expansion_authorization_sha256": authorization_sha256,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise CurrentExtensionGateError(f"Current extension validation {key} does not match the authorized scope.")
    for key in ("blocker_count", "review_count"):
        value = report.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value != 0:
            raise CurrentExtensionGateError(f"Current extension validation {key} must be integer zero.")
    if report.get("execution_approved") is not False:
        raise CurrentExtensionGateError("Validation record is not an execution authorization.")
    return {"status": report["status"], **expected}


def validate_current_manifest(manifest) -> tuple[list[dict], dict[str, dict]]:
    """Validate all 16 frozen manifest entries and retain their exact settings."""
    try:
        normalized = shared.validate_manifest(manifest)
    except shared.GateError as exc:
        raise CurrentExtensionGateError(f"Pinned 16-config manifest is invalid: {exc}") from exc
    raw_configs = manifest.get("configurations") if isinstance(manifest, dict) else None
    if not isinstance(raw_configs, list) or len(raw_configs) != len(EXPECTED_CONFIG_IDS):
        raise CurrentExtensionGateError("Manifest must contain exactly the 16 current configurations.")
    raw_ids = [row.get("config_id") if isinstance(row, dict) else None for row in raw_configs]
    normalized_ids = [row["config_id"] for row in normalized]
    if raw_ids != list(EXPECTED_CONFIG_IDS) or normalized_ids != list(EXPECTED_CONFIG_IDS):
        raise CurrentExtensionGateError("Manifest configuration IDs/order differ from the expansion authorization.")
    by_id = {row["config_id"]: row for row in normalized}
    for config in normalized:
        if config.get("parallel_sequences") != 1:
            raise CurrentExtensionGateError(
                f"{config['config_id']}: runtime.parallel_sequences must remain exactly one.")
        generation = config.get("generation")
        if (not isinstance(generation, dict)
                or generation.get("max_tokens") != shared.FIXED_MAX_TOKENS
                or generation.get("reasoning_budget_tokens") != 0):
            raise CurrentExtensionGateError(
                f"{config['config_id']}: frozen 512-token non-thinking generation is required.")
    # supported_benchmarks is preserved verbatim from the frozen manifest.
    # Authorization of this new experiment scope lives only in the sidecar
    # authorization/validation records above.
    return normalized, by_id


def validate_current_readiness(configs: list[dict], report,
                                manifest_sha256: str) -> dict:
    """Require a passing, manifest-bound, per-model-SHA readiness row for all 16."""
    if not isinstance(report, dict) or report.get("manifest_sha256") != manifest_sha256:
        raise CurrentExtensionGateError("Readiness report is not bound to the exact current manifest SHA.")
    rows = report.get("configs")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_CONFIG_IDS):
        raise CurrentExtensionGateError("Readiness report must contain exactly 16 config rows.")
    try:
        shared.check_readiness(configs, report, manifest_sha256)
    except shared.GateError as exc:
        raise CurrentExtensionGateError(f"Readiness gate failed: {exc}") from exc
    rows_by_id = {row["config_id"]: row for row in rows}
    for config in configs:
        row = rows_by_id[config["config_id"]]
        model_sha = row.get("model_sha256")
        if not isinstance(model_sha, str) or model_sha.lower() != config["model_sha256"]:
            raise CurrentExtensionGateError(
                f"Readiness for {config['config_id']!r} lacks the exact manifest model SHA.")
    return {"passed": len(configs), "required": len(configs),
            "manifest_sha256": manifest_sha256}


def preflight(*, benchmark_path: Path = PHASE1_BENCHMARK,
              baseline_path: Path = PHASE1_BASELINE,
              validation_path: Path = EXTENSION_VALIDATION,
              authorization_path: Path = EXPANSION_AUTHORIZATION,
              manifest_path: Path = MANIFEST,
              readiness_path: Path = READINESS,
              authorize_execution: bool,
              approved_phase1_sha256: str) -> dict:
    """Verify every scope, consent, readiness, and integrity gate before launch."""
    if approved_phase1_sha256 != PHASE1_BENCHMARK_SHA256:
        raise shared.AuthorizationError("Only the pinned Phase 1 v2 benchmark SHA is accepted.")

    baseline = verify_phase1_baseline(
        Path(benchmark_path).parent, baseline_path=baseline_path,
        expected_baseline_sha256=PHASE1_BASELINE_SHA256,
        expected_benchmark_sha256=PHASE1_BENCHMARK_SHA256)
    benchmark_sha = shared.require_authorization(
        benchmark_path, approved_phase1_sha256, authorize_execution)
    benchmark_data, loaded_benchmark_sha = shared.load_json_snapshot(Path(benchmark_path))
    if loaded_benchmark_sha != benchmark_sha:
        raise shared.AuthorizationError(
            "Phase 1 benchmark changed after authorization check; refusing execution.")
    metadata, cases = shared.validate_benchmark(benchmark_data, expected_cases=EXPECTED_CASES)
    if benchmark_sha != baseline["benchmark_sha256"]:
        raise CurrentExtensionGateError("Authorized benchmark SHA differs from the Phase 1 integrity inventory.")

    manifest_data, manifest_sha = shared.load_json_snapshot(Path(manifest_path))
    if manifest_sha != PINNED_MANIFEST_SHA256:
        raise CurrentExtensionGateError("Current manifest SHA differs from its frozen Phase 1 pin.")
    configs, configs_by_id = validate_current_manifest(manifest_data)

    authorization, authorization_sha = shared.load_json_snapshot(Path(authorization_path))
    if authorization_sha != PINNED_EXPANSION_AUTHORIZATION_SHA256:
        raise CurrentExtensionGateError("Expansion authorization file SHA differs from its pinned record.")
    authorization_binding = validate_expansion_authorization(
        authorization, authorization_sha256=authorization_sha,
        manifest_sha256=manifest_sha, benchmark_sha256=benchmark_sha,
        baseline_sha256=baseline["baseline_sha256"])
    if authorization_binding["config_ids"] != [cfg["config_id"] for cfg in configs]:
        raise CurrentExtensionGateError("Authorization and current manifest configuration IDs differ.")

    readiness_data, readiness_sha = shared.load_json_snapshot(Path(readiness_path))
    if readiness_sha != PINNED_READINESS_SHA256:
        raise CurrentExtensionGateError("Readiness report SHA differs from the authorized 16-config snapshot.")
    readiness = validate_current_readiness(configs, readiness_data, manifest_sha)

    validation_data = shared.load_json(Path(validation_path))
    validation = validate_current_extension_report(
        validation_data, benchmark_sha256=benchmark_sha,
        manifest_sha256=manifest_sha, baseline_sha256=baseline["baseline_sha256"],
        authorization_sha256=authorization_sha)
    return {"benchmark_sha256": benchmark_sha,
            "manifest_sha256": manifest_sha,
            "benchmark_id": metadata.get("benchmark_id"),
            "cases": cases,
            "system_prompt": benchmark_data["system_prompt"],
            "user_prompt_template": benchmark_data["user_prompt_template"],
            "configs": configs,
            "configs_by_id": configs_by_id,
            "readiness": readiness,
            "authorization": authorization_binding,
            "validation": validation,
            "phase1_integrity": baseline}


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def execute(args, *, client_factory=None, server_factory=None) -> int:
    """Run exactly 16 configurations × 40 cases in the new result tree."""
    gates = preflight(authorize_execution=args.authorize_execution,
                      approved_phase1_sha256=args.approved_phase1_sha256)
    cases = gates["cases"]
    configs = gates["configs"]
    benchmark_sha = gates["benchmark_sha256"]
    manifest_sha = gates["manifest_sha256"]
    print(json.dumps({"mode": "dry-run" if args.dry_run else "run",
                      "scope_id": CURRENT_SCOPE,
                      "benchmark_sha256": benchmark_sha,
                      "manifest_sha256": manifest_sha,
                      "expansion_authorization_sha256": gates["authorization"]["sha256"],
                      "configs": [config["config_id"] for config in configs],
                      "cases": len(cases), "planned_rows": EXPECTED_MATRIX_ROWS,
                      "readiness": gates["readiness"],
                      "output_dir": str(OUT_DIR)}))
    if args.dry_run:
        return shared.EXIT_OK

    checkpoint_path = OUT_DIR / "checkpoint.json"
    summary_path = OUT_DIR / "reports" / "run_summary.json"
    case_ids = {case["id"] for case in cases}
    raw_paths = [shared.raw_path_for(OUT_DIR, cid) for cid in EXPECTED_CONFIG_IDS]
    replayed = shared.replay_raw_authority(
        raw_paths, benchmark_sha, manifest_sha, gates["configs_by_id"], case_ids)
    cached = shared.load_checkpoint(checkpoint_path, benchmark_sha, manifest_sha)
    cached_states = cached.get("states", {})
    for key, entry in cached_states.items():
        if not isinstance(entry, dict) or entry.get("state") not in {"done", "pending"}:
            raise shared.CheckpointMismatchError("Current 16-config checkpoint has an invalid state entry.")
        if key not in replayed or replayed[key].get("state") != entry.get("state"):
            raise shared.CheckpointMismatchError(
                f"Checkpoint claim {key!r} has no matching RAW authority.")
    states: dict = {key: dict(info) for key, info in replayed.items()}
    shared.write_checkpoint_atomic(checkpoint_path, benchmark_sha, manifest_sha, states)

    client = (client_factory or (lambda: shared.HttpClient(args.request_timeout)))()
    runtime_args = SimpleNamespace(
        api_path=args.api_path, health_path=args.health_path,
        health_timeout=args.health_timeout, health_interval=args.health_interval,
        request_timeout=args.request_timeout, max_retries=args.max_retries,
        retry_failed=args.retry_failed)
    per_config: list[dict] = []
    started_utc = shared.utcnow()
    rate_limited = False
    rate_limited_config = None
    rate_limit_detail = None
    try:
        for config in configs:
            rate_limited_config = config["config_id"]
            stats = shared.run_config(
                config=config, cases=cases,
                system_prompt=gates["system_prompt"],
                user_template=gates["user_prompt_template"],
                benchmark_sha=benchmark_sha, manifest_sha=manifest_sha,
                out_dir=OUT_DIR, checkpoint_path=checkpoint_path,
                summary_log_path=None, client=client, args=runtime_args,
                states=states, reopen_failed=args.retry_failed,
                server_factory=server_factory)
            per_config.append(stats)
            print(json.dumps({"config": config["config_id"], **stats}))
            rate_limited_config = None
    except shared.RateLimitedError as exc:
        rate_limited = True
        rate_limit_detail = str(exc)
        print(json.dumps({"fatal": "rate_limited", "detail": rate_limit_detail,
                          "config": rate_limited_config,
                          "policy": "stopped immediately; no 429 retry or fallback"}))

    summary = {
        "scope_id": CURRENT_SCOPE,
        "benchmark_id": gates["benchmark_id"],
        "benchmark_sha256": benchmark_sha,
        "manifest_sha256": manifest_sha,
        "phase1_baseline_sha256": gates["phase1_integrity"]["baseline_sha256"],
        "expansion_authorization_sha256": gates["authorization"]["sha256"],
        "extension_validation": gates["validation"],
        "started_utc": started_utc,
        "completed_utc": shared.utcnow(),
        "planned_rows": EXPECTED_MATRIX_ROWS,
        "rate_limited_stop": rate_limited,
        "rate_limited_config": rate_limited_config if rate_limited else None,
        "rate_limit_detail": rate_limit_detail,
        "retry_failed_flag": bool(args.retry_failed),
        "per_config": per_config,
        "successful_rows": sum(item["completed"] for item in per_config),
        "recorded_rows_in_returned_stats": sum(
            item["completed"] + item["failed"] for item in per_config),
        "note": ("All current 16 manifest configurations are evaluated over the frozen Phase 1 40-case benchmark. "
                 "Sampling settings are read unchanged from the pinned family-specific manifest entries. "
                 "The new scope writes only to results_40_current_16; historical Phase 1 artifacts and the "
                 "120-case development tree are read-only. HTTP 429 stops the entire invocation immediately, "
                 "with no retry or fallback."),
    }
    _write_json_atomic(summary_path, summary)
    return shared.EXIT_RATE_LIMITED if rate_limited else shared.EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-execution", action="store_true",
                        help="Explicit opt-in; required for any run, including --dry-run.")
    parser.add_argument("--approved-phase1-sha256", required=True,
                        help="Must equal the frozen Phase 1 v2 SHA-256.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate the complete 16-config plan without starting a server.")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Manually reopen previously recorded technical failures; HTTP 429 is never retried in-run.")
    parser.add_argument("--api-path", default="/v1/chat/completions")
    parser.add_argument("--health-path", default="/health")
    parser.add_argument("--request-timeout", type=float, default=300.0)
    parser.add_argument("--health-timeout", type=float, default=180.0)
    parser.add_argument("--health-interval", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=2)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_retries < 0:
        print(json.dumps({"fatal": "gate", "detail": "--max-retries must be non-negative."}))
        return shared.EXIT_GATE
    try:
        return execute(args)
    except shared.AuthorizationError as exc:
        print(json.dumps({"fatal": "authorization", "detail": str(exc)}))
        return shared.EXIT_GATE
    except (shared.GateError, shared.CheckpointMismatchError) as exc:
        print(json.dumps({"fatal": "gate", "detail": str(exc)}))
        return shared.EXIT_GATE
    except shared.RateLimitedError as exc:
        print(json.dumps({"fatal": "rate_limited", "detail": str(exc)}))
        return shared.EXIT_RATE_LIMITED


if __name__ == "__main__":
    raise SystemExit(main())
