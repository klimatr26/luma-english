"""Prepare the isolated 40-case Phase 1 extension for LFM2.5-2.6B.

This runner is deliberately fixed to the frozen Phase 1 v2 benchmark, the two
LFM26 configurations, the 16-config manifest/readiness matrix, and a separate
``results_40_lfm26`` directory. It reuses the transport, RAW, checkpoint,
retry, and 429 behavior from ``run_benchmark_120.py`` without changing any
existing Phase 1 files or results. No inference is run during preparation.
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
EXTENSION_VALIDATION = RUNNER_DIR / "benchmark_40_archive" / "lfm26_extension_validation.json"
MANIFEST = RUNNER_DIR / "manifests" / "experiment_manifest_120.json"
READINESS = RUNNER_DIR / "llama_cpp_readiness_report.json"
OUT_DIR = RUNNER_DIR / "results_40_lfm26"

PHASE1_BENCHMARK_SHA256 = "a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9"
PHASE1_BASELINE_SHA256 = "f2d2d4b081d7afac723178aabc805f618b48ed1289b9f131ce7f5bc08b93989f"
EXPECTED_CASES = 40
EXPECTED_CONFIG_IDS = ("15-lfm25-26b-q8-0", "16-lfm25-26b-q4-k-m")
EXPECTED_PORTS = {EXPECTED_CONFIG_IDS[0]: 8115, EXPECTED_CONFIG_IDS[1]: 8116}
EXPECTED_MODELS = {
    EXPECTED_CONFIG_IDS[0]: "models/lfm25_26b/LFM2.5-2.6B-Q8_0.gguf",
    EXPECTED_CONFIG_IDS[1]: "models/lfm25_26b/LFM2.5-2.6B-Q4_K_M.gguf",
}
EXPECTED_QUANTS = {EXPECTED_CONFIG_IDS[0]: "Q8_0", EXPECTED_CONFIG_IDS[1]: "Q4_K_M"}
EXPECTED_REPO = "LiquidAI/LFM2.5-2.6B-GGUF"
EXPECTED_REVISION = "e7caca5d835a3901a8e0d63e94009429bafafdfc"
EXTENSION_SCOPE = "lfm26_phase1_40"
EXPECTED_MATRIX_ROWS = EXPECTED_CASES * len(EXPECTED_CONFIG_IDS)


class ExtensionGateError(shared.GateError):
    """An extension-specific preflight check failed."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_phase1_baseline(root: Path = RUNNER_DIR, *,
                           baseline_path: Path = PHASE1_BASELINE,
                           expected_baseline_sha256: str = PHASE1_BASELINE_SHA256,
                           expected_benchmark_sha256: str = PHASE1_BENCHMARK_SHA256) -> dict:
    """Verify the exact read-only Phase 1 inventory and return its binding.

    The expected digests are parameters only to support isolated synthetic
    unit fixtures; production defaults are pinned constants above.
    """
    baseline_path = Path(baseline_path)
    try:
        baseline_bytes = baseline_path.read_bytes()
        baseline = json.loads(baseline_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExtensionGateError(f"Cannot read Phase 1 integrity baseline: {exc}.") from exc
    baseline_sha = _sha256_bytes(baseline_bytes)
    if baseline_sha != expected_baseline_sha256:
        raise ExtensionGateError("Phase 1 baseline record SHA differs from the pinned value.")
    records = baseline.get("files") if isinstance(baseline, dict) else None
    if not isinstance(records, list) or len(records) != 24:
        raise ExtensionGateError("Phase 1 baseline must contain exactly 24 file records.")

    root = Path(root).resolve()
    seen: set[str] = set()
    benchmark_record = None
    for record in records:
        if not isinstance(record, dict):
            raise ExtensionGateError("Phase 1 baseline has a non-object file record.")
        rel = record.get("path")
        size = record.get("size_bytes")
        digest_expected = record.get("sha256")
        if (not isinstance(rel, str) or not rel.strip() or rel in seen
                or not isinstance(size, int) or isinstance(size, bool) or size < 0
                or not isinstance(digest_expected, str)
                or len(digest_expected) != 64
                or any(ch not in "0123456789abcdef" for ch in digest_expected)):
            raise ExtensionGateError("Phase 1 baseline has an invalid or duplicate record.")
        seen.add(rel)
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            raise ExtensionGateError(f"Phase 1 baseline path escapes its root: {rel!r}.")
        try:
            before = path.stat()
            if not path.is_file() or before.st_size != size:
                raise ExtensionGateError(f"Phase 1 artifact size mismatch or missing file: {rel}.")
            digest = shared.sha256_file(path)
            after = path.stat()
        except OSError as exc:
            raise ExtensionGateError(f"Cannot verify Phase 1 artifact {rel!r}: {exc}.") from exc
        if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                or digest != digest_expected):
            raise ExtensionGateError(f"Phase 1 artifact changed or hash mismatch: {rel}.")
        if rel == "benchmark_smoke_test_v2.json":
            benchmark_record = record

    if (benchmark_record is None
            or benchmark_record["sha256"] != expected_benchmark_sha256):
        raise ExtensionGateError("Phase 1 v2 benchmark is not pinned by the baseline inventory.")
    return {"baseline_sha256": baseline_sha,
            "verified_files": len(records),
            "benchmark_sha256": benchmark_record["sha256"]}


def validate_extension_report(report, *, benchmark_sha256: str,
                              baseline_sha256: str = PHASE1_BASELINE_SHA256) -> dict:
    """Require the separately reviewed 40-case extension validation record."""
    if not isinstance(report, dict):
        raise ExtensionGateError("LFM26 extension validation must be a JSON object.")
    if benchmark_sha256 != PHASE1_BENCHMARK_SHA256:
        raise ExtensionGateError("Extension benchmark SHA is not the pinned Phase 1 v2 SHA.")
    shared.check_validation(report, benchmark_sha256)
    if report.get("case_count") != EXPECTED_CASES:
        raise ExtensionGateError("Extension validation must bind exactly 40 cases.")
    if report.get("scope_id") != EXTENSION_SCOPE:
        raise ExtensionGateError("Extension validation has the wrong scope_id.")
    if report.get("config_ids") != list(EXPECTED_CONFIG_IDS):
        raise ExtensionGateError("Extension validation must name exactly the two LFM26 config IDs in order.")
    if report.get("phase1_baseline_record_sha256") != baseline_sha256:
        raise ExtensionGateError("Extension validation does not bind the pinned Phase 1 baseline record.")
    if report.get("execution_approved") is not False:
        raise ExtensionGateError("Extension validation must remain a validation record, not an execution authorization.")
    return {"status": report["status"], "case_count": EXPECTED_CASES,
            "scope_id": EXTENSION_SCOPE, "config_ids": list(EXPECTED_CONFIG_IDS),
            "benchmark_sha256": benchmark_sha256,
            "phase1_baseline_record_sha256": baseline_sha256}


def validate_extension_manifest(manifest) -> tuple[list[dict], dict[str, dict]]:
    """Validate the complete 16-entry manifest and the exact two-config scope."""
    normalized = shared.validate_manifest(manifest)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("configurations"), list):
        raise ExtensionGateError("Manifest configurations must be a list.")
    raw_by_id: dict[str, dict] = {}
    for row in manifest["configurations"]:
        cid = row.get("config_id", row.get("id", row.get("name"))) if isinstance(row, dict) else None
        if not isinstance(cid, str) or cid in raw_by_id:
            raise ExtensionGateError("Manifest has a missing or duplicate raw config identity.")
        raw_by_id[cid] = row

    by_id = {entry["config_id"]: entry for entry in normalized}
    if not set(EXPECTED_CONFIG_IDS).issubset(by_id):
        raise ExtensionGateError("Manifest is missing one or both authorized LFM26 configurations.")
    for entry in normalized:
        if entry["parallel_sequences"] != 1:
            raise ExtensionGateError(
                f"{entry['config_id']}: manifest must declare runtime.parallel_sequences=1.")
    for cid in EXPECTED_CONFIG_IDS:
        raw = raw_by_id[cid]
        cfg = by_id[cid]
        expected_quant = EXPECTED_QUANTS[cid]
        if raw.get("family") != "lfm26" or raw.get("quant") != expected_quant:
            raise ExtensionGateError(f"{cid}: manifest family/quantization does not match the fixed scope.")
        if raw.get("supported_benchmarks") != ["development_120", "phase1_40_lfm26_extension"]:
            raise ExtensionGateError(f"{cid}: manifest does not explicitly authorize the separate extension scope.")
        source = raw.get("source")
        if (not isinstance(source, dict) or source.get("repo") != EXPECTED_REPO
                or source.get("revision") != EXPECTED_REVISION):
            raise ExtensionGateError(f"{cid}: model provenance differs from the pinned LFM26 source.")
        gguf = raw.get("gguf")
        if (not isinstance(gguf, dict) or gguf.get("path") != EXPECTED_MODELS[cid]
                or gguf.get("status") != "verified"):
            raise ExtensionGateError(f"{cid}: GGUF path/status differs from the fixed verified asset.")
        if cfg["model_ref"] != EXPECTED_MODELS[cid] or cfg["port"] != EXPECTED_PORTS[cid]:
            raise ExtensionGateError(f"{cid}: model path or port differs from the fixed extension scope.")
    return normalized, by_id


def validate_extension_readiness(configs: list[dict], report, manifest_sha256: str) -> dict:
    """Require a manifest-bound passing readiness row, including SHA, for all 16."""
    if not isinstance(report, dict) or report.get("manifest_sha256") != manifest_sha256:
        raise ExtensionGateError("Readiness report is not bound to the exact current manifest SHA.")
    rows = report.get("configs")
    if not isinstance(rows, list) or len(rows) != len(configs):
        raise ExtensionGateError("Readiness report must contain exactly 16 config rows.")
    shared.check_readiness(configs, report, manifest_sha256)
    rows_by_id = {row["config_id"]: row for row in rows}
    for cfg in configs:
        row = rows_by_id[cfg["config_id"]]
        if row.get("model_sha256") != cfg["model_sha256"]:
            raise ExtensionGateError(
                f"Readiness for {cfg['config_id']!r} lacks an exact matching model SHA.")
    return {"passed": len(configs), "required": len(configs),
            "manifest_sha256": manifest_sha256}


def preflight(*, benchmark_path: Path = PHASE1_BENCHMARK,
              baseline_path: Path = PHASE1_BASELINE,
              validation_path: Path = EXTENSION_VALIDATION,
              manifest_path: Path = MANIFEST,
              readiness_path: Path = READINESS,
              authorize_execution: bool,
              approved_phase1_sha256: str) -> dict:
    """Run all fixed extension gates without starting a server or network call."""
    if approved_phase1_sha256 != PHASE1_BENCHMARK_SHA256:
        raise shared.AuthorizationError("Only the pinned Phase 1 v2 benchmark SHA is accepted.")
    integrity = verify_phase1_baseline(Path(benchmark_path).parent,
                                       baseline_path=baseline_path)
    benchmark_sha = shared.require_authorization(
        benchmark_path, approved_phase1_sha256, authorize_execution)
    benchmark_data, loaded_benchmark_sha = shared.load_json_snapshot(Path(benchmark_path))
    if loaded_benchmark_sha != benchmark_sha:
        raise shared.AuthorizationError(
            "Phase 1 benchmark changed after authorization check; refusing execution.")
    meta, cases = shared.validate_benchmark(benchmark_data, expected_cases=EXPECTED_CASES)
    if benchmark_sha != integrity["benchmark_sha256"]:
        raise ExtensionGateError("Benchmark authorization SHA differs from the Phase 1 inventory.")
    manifest_data, manifest_sha = shared.load_json_snapshot(Path(manifest_path))
    configs, configs_by_id = validate_extension_manifest(manifest_data)
    readiness = validate_extension_readiness(
        configs, shared.load_json(Path(readiness_path)), manifest_sha)
    validation = validate_extension_report(
        shared.load_json(Path(validation_path)), benchmark_sha256=benchmark_sha,
        baseline_sha256=integrity["baseline_sha256"])
    scoped = [configs_by_id[cid] for cid in EXPECTED_CONFIG_IDS]
    return {"benchmark_sha256": benchmark_sha, "manifest_sha256": manifest_sha,
            "benchmark_id": meta.get("benchmark_id"), "cases": cases,
            "system_prompt": benchmark_data["system_prompt"],
            "user_prompt_template": benchmark_data["user_prompt_template"],
            "configs": scoped, "configs_by_id": configs_by_id,
            "readiness": readiness, "validation": validation,
            "phase1_integrity": integrity}


def execute(args, *, client_factory=None, server_factory=None) -> int:
    """Run the fixed 2 x 40 extension, using only the isolated result tree."""
    gates = preflight(authorize_execution=args.authorize_execution,
                      approved_phase1_sha256=args.approved_phase1_sha256)
    cases = gates["cases"]
    configs = gates["configs"]
    benchmark_sha = gates["benchmark_sha256"]
    manifest_sha = gates["manifest_sha256"]
    print(json.dumps({"mode": "dry-run" if args.dry_run else "run",
                      "scope_id": EXTENSION_SCOPE,
                      "benchmark_sha256": benchmark_sha,
                      "manifest_sha256": manifest_sha,
                      "configs": list(EXPECTED_CONFIG_IDS),
                      "cases": len(cases), "planned_rows": EXPECTED_MATRIX_ROWS,
                      "readiness": gates["readiness"],
                      "output_dir": str(OUT_DIR)}))
    if args.dry_run:
        return shared.EXIT_OK

    out_dir = OUT_DIR
    checkpoint_path = out_dir / "checkpoint.json"
    summary_path = out_dir / "reports" / "run_summary.json"
    selected_by_id = {cfg["config_id"]: cfg for cfg in configs}
    case_ids = {case["id"] for case in cases}
    raw_paths = [shared.raw_path_for(out_dir, cid) for cid in EXPECTED_CONFIG_IDS]
    replayed = shared.replay_raw_authority(raw_paths, benchmark_sha, manifest_sha,
                                           selected_by_id, case_ids)
    cached = shared.load_checkpoint(checkpoint_path, benchmark_sha, manifest_sha)
    cached_states = cached.get("states", {})
    for key, entry in cached_states.items():
        if not isinstance(entry, dict) or entry.get("state") not in {"done", "pending"}:
            raise shared.CheckpointMismatchError("Extension checkpoint has an invalid state entry.")
        if key not in replayed or replayed[key].get("state") != entry.get("state"):
            raise shared.CheckpointMismatchError(
                f"Extension checkpoint claim {key!r} has no matching RAW authority.")
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
    try:
        for config in configs:
            stats = shared.run_config(
                config=config, cases=cases, system_prompt=gates["system_prompt"],
                user_template=gates["user_prompt_template"],
                benchmark_sha=benchmark_sha, manifest_sha=manifest_sha,
                out_dir=out_dir, checkpoint_path=checkpoint_path,
                summary_log_path=None, client=client, args=runtime_args,
                states=states, reopen_failed=args.retry_failed,
                server_factory=server_factory)
            per_config.append(stats)
            print(json.dumps({"config": config["config_id"], **stats}))
    except shared.RateLimitedError as exc:
        rate_limited = True
        print(json.dumps({"fatal": "rate_limited", "detail": str(exc)}))

    summary = {"scope_id": EXTENSION_SCOPE, "benchmark_id": gates["benchmark_id"],
               "benchmark_sha256": benchmark_sha, "manifest_sha256": manifest_sha,
               "phase1_baseline_sha256": gates["phase1_integrity"]["baseline_sha256"],
               "started_utc": started_utc, "completed_utc": shared.utcnow(),
               "planned_rows": EXPECTED_MATRIX_ROWS,
               "rate_limited_stop": rate_limited,
               "retry_failed_flag": bool(args.retry_failed),
               "per_config": per_config,
               "completed_rows": sum(item["completed"] for item in per_config),
               "note": ("Transport records only under results_40_lfm26. The Phase 1 input "
                        "and prior result trees are read-only. Exact RAW attempts are the "
                        "authority; HTTP 429 stops the extension immediately.")}
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return shared.EXIT_RATE_LIMITED if rate_limited else shared.EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-execution", action="store_true",
                        help="Explicit opt-in; required for any run, including --dry-run.")
    parser.add_argument("--approved-phase1-sha256", required=True,
                        help="Must equal the frozen Phase 1 v2 SHA-256.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate all fixed gates and print the plan; starts no server.")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Manually reopen only previously recorded technical failures.")
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
