"""Synthetic tests for the frozen 40-case, 16-configuration extension.

All filesystem fixtures are temporary. End-to-end cases use a fake HTTP client
and fake server context manager, so these tests start no model/server and send
no network requests. The real historical artifacts are never written.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_benchmark_40_current as extension
import run_benchmark_120 as shared


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, data) -> bytes:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def fixture_manifest():
    rows = []
    for index, config_id in enumerate(extension.EXPECTED_CONFIG_IDS):
        model = f"synthetic/models/model-{index:02d}.gguf"
        port = 18001 + index
        rows.append({
            "config_id": config_id,
            "family": f"synthetic-family-{index // 3}",
            "quant": "SYNTHETIC",
            # The extension is granted by its own sidecar. Preserve the
            # pinned manifest's prior supported_benchmarks declaration.
            "supported_benchmarks": ["development_120"],
            "model_path": model,
            "model_sha256": f"{index + 1:02x}" * 32,
            "server_command": [
                "synthetic-llama-server", "-m", model, "--host", "127.0.0.1",
                "--port", str(port), "-c", "4096", "--parallel", "1",
                "-ngl", "999", "--reasoning", "off", "--reasoning-budget", "0",
            ],
            "port": port,
            "generation": {
                "max_tokens": 512,
                "reasoning_budget_tokens": 0,
                "temperature": 0.1 + index / 100,
                "top_p": 0.8,
            },
            "runtime": {"parallel_sequences": 1},
        })
    return {"configurations": rows}


def fixture_cases(n=40):
    return [{
        "id": f"SYN-{index:02d}", "level": "A1" if index % 2 == 0 else "A2",
        "task": "synthetic task",
        "student_text": f"A synthetic sentence number {index}.",
        "gold": {"corrected_text": f"GOLD_CANARY_{index}"},
    } for index in range(n)]


def fixture_benchmark():
    return {"benchmark_id": "synthetic-phase1-40", "version": "0.test",
            "system_prompt": "Synthetic system prompt.",
            "user_prompt_template": "{level}: {task}: {student_text}",
            "cases": fixture_cases()}


def fixture_readiness(manifest, manifest_sha):
    return {"manifest_sha256": manifest_sha,
            "configs": [{"config_id": row["config_id"], "status": "pass",
                         "model_sha256": row["model_sha256"]}
                        for row in manifest["configurations"]]}


def fixture_authorization(manifest_sha, benchmark_sha, baseline_sha):
    return {
        "status": "HUMAN_AUTHORIZED_CURRENT16_EXTENSION_NOT_STARTED",
        "authorization_source": "synthetic direct-user authorization fixture",
        "user_instruction": "Synthetic test fixture only.",
        "scope": extension.CURRENT_SCOPE,
        "manifest_sha256": manifest_sha,
        "phase1_baseline_sha256": baseline_sha,
        "phase1_extension": {
            "benchmark_sha256": benchmark_sha,
            "case_count": extension.EXPECTED_CASES,
            "planned_rows": extension.EXPECTED_MATRIX_ROWS,
            "scope_id": extension.CURRENT_SCOPE,
            "output_dir": extension.OUT_DIR.name,
            "config_ids": list(extension.EXPECTED_CONFIG_IDS),
        },
        "old_files_readonly": True,
        "original_40_artifacts_read_only": True,
        "frozen_manifest_changed": False,
        "generation_changed": False,
        "final_test_access_authorized": False,
        "planned_total_new_rows": 2560,
    }


def fixture_validation(manifest_sha, benchmark_sha, baseline_sha, authorization_sha):
    return {
        "status": "VALIDATED_PENDING_USER_APPROVAL",
        "scope_id": extension.CURRENT_SCOPE,
        "benchmark_sha256": benchmark_sha,
        "manifest_sha256": manifest_sha,
        "phase1_baseline_sha256": baseline_sha,
        "case_count": extension.EXPECTED_CASES,
        "planned_rows": extension.EXPECTED_MATRIX_ROWS,
        "config_ids": list(extension.EXPECTED_CONFIG_IDS),
        "expansion_authorization_sha256": authorization_sha,
        "blocker_count": 0, "review_count": 0,
        "execution_approved": False,
    }


def fixture_phase1_tree(root: Path):
    """Write an isolated 24-file integrity inventory for preflight tests."""
    benchmark_path = root / "benchmark_smoke_test_v2.json"
    benchmark_raw = dump(benchmark_path, fixture_benchmark())
    benchmark_sha = sha256(benchmark_raw)
    records = [{"path": benchmark_path.name, "size_bytes": len(benchmark_raw),
                "sha256": benchmark_sha}]
    for index in range(23):
        rel = f"synthetic/phase1-artifact-{index:02d}.bin"
        payload = f"synthetic historical artifact {index}".encode()
        artifact = root / rel
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(payload)
        records.append({"path": rel, "size_bytes": len(payload), "sha256": sha256(payload)})
    baseline_raw = dump(root / "baseline.json", {"files": records})
    return benchmark_path, sha256(baseline_raw), benchmark_sha


def fixture_preflight_tree(root: Path):
    benchmark_path, baseline_sha, benchmark_sha = fixture_phase1_tree(root)
    manifest = fixture_manifest()
    manifest_raw = dump(root / "manifest.json", manifest)
    manifest_sha = sha256(manifest_raw)
    readiness = fixture_readiness(manifest, manifest_sha)
    readiness_raw = dump(root / "readiness.json", readiness)
    authorization = fixture_authorization(manifest_sha, benchmark_sha, baseline_sha)
    authorization_raw = dump(root / "authorization.json", authorization)
    validation = fixture_validation(manifest_sha, benchmark_sha, baseline_sha,
                                    sha256(authorization_raw))
    dump(root / "validation.json", validation)
    return {
        "benchmark_path": benchmark_path,
        "baseline_path": root / "baseline.json",
        "manifest_path": root / "manifest.json",
        "readiness_path": root / "readiness.json",
        "authorization_path": root / "authorization.json",
        "validation_path": root / "validation.json",
        "baseline_sha": baseline_sha,
        "benchmark_sha": benchmark_sha,
        "manifest_sha": manifest_sha,
        "readiness_sha": sha256(readiness_raw),
        "authorization_sha": sha256(authorization_raw),
    }


class GateTests(unittest.TestCase):
    def test_manifest_requires_exact_order_and_keeps_frozen_support_labels(self):
        manifest = fixture_manifest()
        configs, by_id = extension.validate_current_manifest(manifest)
        self.assertEqual([config["config_id"] for config in configs],
                         list(extension.EXPECTED_CONFIG_IDS))
        self.assertEqual(by_id[extension.EXPECTED_CONFIG_IDS[0]]["generation"],
                         manifest["configurations"][0]["generation"])
        self.assertEqual(
            by_id[extension.EXPECTED_CONFIG_IDS[0]]["manifest_extra"]["supported_benchmarks"],
            ["development_120"])

        manifest["configurations"][0], manifest["configurations"][1] = (
            manifest["configurations"][1], manifest["configurations"][0])
        with self.assertRaisesRegex(extension.CurrentExtensionGateError, "IDs/order"):
            extension.validate_current_manifest(manifest)

    def test_manifest_requires_512_non_thinking_and_parallel_one(self):
        manifest = fixture_manifest()
        manifest["configurations"][3]["generation"]["max_tokens"] = 513
        with self.assertRaisesRegex(extension.CurrentExtensionGateError, "exactly 512"):
            extension.validate_current_manifest(manifest)
        manifest = fixture_manifest()
        manifest["configurations"][3]["runtime"]["parallel_sequences"] = 2
        with self.assertRaisesRegex(extension.CurrentExtensionGateError, "parallel_sequences"):
            extension.validate_current_manifest(manifest)

    def test_readiness_requires_all_sixteen_exact_model_hashes(self):
        manifest = fixture_manifest()
        configs = shared.validate_manifest(manifest)
        manifest_sha = "de" * 32
        report = fixture_readiness(manifest, manifest_sha)
        self.assertEqual(extension.validate_current_readiness(configs, report, manifest_sha)["passed"], 16)
        report["configs"][4]["model_sha256"] = "ff" * 32
        with self.assertRaisesRegex(extension.CurrentExtensionGateError, "model SHA"):
            extension.validate_current_readiness(configs, report, manifest_sha)

    def test_authorization_and_validation_bind_all_scope_fields(self):
        benchmark_sha, manifest_sha, baseline_sha = "a1" * 32, "b2" * 32, "c3" * 32
        authorization_sha = extension.PINNED_EXPANSION_AUTHORIZATION_SHA256
        auth = fixture_authorization(manifest_sha, benchmark_sha, baseline_sha)
        accepted = extension.validate_expansion_authorization(
            auth, authorization_sha256=authorization_sha,
            manifest_sha256=manifest_sha, benchmark_sha256=benchmark_sha,
            baseline_sha256=baseline_sha)
        self.assertEqual(accepted["planned_rows"], 640)
        report = fixture_validation(manifest_sha, benchmark_sha, baseline_sha,
                                    authorization_sha)
        self.assertEqual(extension.validate_current_extension_report(
            report, benchmark_sha256=benchmark_sha, manifest_sha256=manifest_sha,
            baseline_sha256=baseline_sha,
            authorization_sha256=authorization_sha)["status"],
            "VALIDATED_PENDING_USER_APPROVAL")
        report["planned_rows"] = 80
        with self.assertRaisesRegex(extension.CurrentExtensionGateError, "planned_rows"):
            extension.validate_current_extension_report(
                report, benchmark_sha256=benchmark_sha, manifest_sha256=manifest_sha,
                baseline_sha256=baseline_sha,
                authorization_sha256=authorization_sha)

    def test_verifies_synthetic_24_file_baseline_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path, baseline_sha, benchmark_sha = fixture_phase1_tree(root)
            baseline_path = root / "baseline.json"
            got = extension.verify_phase1_baseline(
                root, baseline_path=baseline_path,
                expected_baseline_sha256=baseline_sha,
                expected_benchmark_sha256=benchmark_sha)
            self.assertEqual(got["verified_files"], 24)
            artifact = root / "synthetic/phase1-artifact-00.bin"
            artifact.write_bytes(b"drift")
            with self.assertRaisesRegex(extension.CurrentExtensionGateError, "mismatch"):
                extension.verify_phase1_baseline(
                    root, baseline_path=baseline_path,
                    expected_baseline_sha256=baseline_sha,
                    expected_benchmark_sha256=benchmark_sha)

    def test_preflight_requires_cli_approval_and_all_pinned_scope_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = fixture_preflight_tree(root)
            with mock.patch.multiple(
                extension,
                PHASE1_BENCHMARK_SHA256=paths["benchmark_sha"],
                PHASE1_BASELINE_SHA256=paths["baseline_sha"],
                PINNED_MANIFEST_SHA256=paths["manifest_sha"],
                PINNED_READINESS_SHA256=paths["readiness_sha"],
                PINNED_EXPANSION_AUTHORIZATION_SHA256=paths["authorization_sha"],
            ):
                kwargs = {key: paths[key] for key in (
                    "benchmark_path", "baseline_path", "validation_path",
                    "authorization_path", "manifest_path", "readiness_path")}
                with self.assertRaises(shared.AuthorizationError):
                    extension.preflight(**kwargs, authorize_execution=False,
                                        approved_phase1_sha256=paths["benchmark_sha"])
                gates = extension.preflight(
                    **kwargs, authorize_execution=True,
                    approved_phase1_sha256=paths["benchmark_sha"])
                self.assertEqual(len(gates["cases"]), 40)
                self.assertEqual(len(gates["configs"]), 16)
                self.assertEqual(gates["authorization"]["planned_rows"], 640)


class SyntheticExecutionTests(unittest.TestCase):
    @staticmethod
    def quick_sampler(_pid):
        return SimpleNamespace(start=lambda: None,
                               stop=lambda: {"server_peak_rss_bytes": None,
                                             "server_rss_samples": 0,
                                             "server_rss_sampled": False,
                                             "server_rss_note": "synthetic-test"})

    def run_execute(self, out_dir, response_script=None):
        cases = fixture_cases()
        configs, by_id = extension.validate_current_manifest(fixture_manifest())
        gates = {
            "benchmark_sha256": "aa" * 32, "manifest_sha256": "bb" * 32,
            "benchmark_id": "synthetic-phase1-40", "cases": cases,
            "system_prompt": "Synthetic system prompt.",
            "user_prompt_template": "{level}: {task}: {student_text}",
            "configs": configs, "configs_by_id": by_id,
            "readiness": {"passed": 16, "required": 16},
            "authorization": {"sha256": "cc" * 32},
            "validation": {"status": "VALIDATED_PENDING_USER_APPROVAL"},
            "phase1_integrity": {"baseline_sha256": "dd" * 32},
        }

        class FakeClient:
            def __init__(self, script):
                self.script = list(script or [])
                self.calls = []

            def get(self, _url):
                return 200, '{"status":"ok"}'

            def post_json(self, url, payload):
                self.calls.append((url, payload))
                if self.script:
                    return self.script.pop(0)
                body = json.dumps({"choices": [{"finish_reason": "stop",
                                                  "message": {"content": "synthetic response"}}],
                                   "usage": {"prompt_tokens": 2, "completion_tokens": 3}})
                return 200, body, None

        client = FakeClient(response_script)

        class FakeServer:
            live = 0
            max_live = 0
            starts = []

            def __init__(self, argv, port, log):
                self.argv, self.port, self.log_path = argv, port, log
                self.pid = None
                type(self).starts.append(port)

            def __enter__(self):
                type(self).live += 1
                type(self).max_live = max(type(self).max_live, type(self).live)
                return self

            def __exit__(self, *_args):
                type(self).live -= 1
                return False

            def wait_healthy(self, _client, _deadline, _interval):
                return True

        args = SimpleNamespace(
            authorize_execution=True,
            approved_phase1_sha256=extension.PHASE1_BENCHMARK_SHA256,
            dry_run=False, retry_failed=False, api_path="/v1/chat/completions",
            health_path="/health", request_timeout=1.0, health_timeout=1.0,
            health_interval=0.0, max_retries=3)
        with mock.patch.object(extension, "OUT_DIR", out_dir), \
                mock.patch.object(extension, "preflight", return_value=gates), \
                mock.patch.object(shared, "PeakSampler", self.quick_sampler), \
                mock.patch.object(shared, "sample_runner_rss", return_value={
                    "runner_rss_bytes": None, "runner_rss_sampled": False,
                    "runner_rss_note": "synthetic-test"}), \
                mock.patch.object(shared, "sample_gpu", return_value={
                    "gpu_used_bytes": None, "gpu_unit": "bytes", "gpu_sampled": False,
                    "gpu_scope": "synthetic-test", "gpu_note": "synthetic-test"}), \
                contextlib.redirect_stdout(io.StringIO()):
            code = extension.execute(
                args, client_factory=lambda: client,
                server_factory=lambda argv, port, log: FakeServer(argv, port, log))
        return code, client, FakeServer

    def test_full_matrix_is_sequential_and_uses_only_prompt_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "results_40_current_16"
            code, client, fake_server = self.run_execute(out_dir)
            self.assertEqual(code, shared.EXIT_OK)
            self.assertEqual(len(fake_server.starts), 16)
            self.assertEqual(fake_server.max_live, 1)
            self.assertEqual(fake_server.live, 0)
            self.assertEqual(len(client.calls), 640)
            self.assertEqual(fake_server.starts,
                             [config["port"] for config in fixture_manifest()["configurations"]])
            for index, (url, payload) in enumerate(client.calls):
                config_index = index // 40
                config = fixture_manifest()["configurations"][config_index]
                self.assertEqual(url, f"http://127.0.0.1:{config['port']}/v1/chat/completions")
                self.assertEqual(payload["max_tokens"], 512)
                self.assertEqual(payload["temperature"], config["generation"]["temperature"])
                self.assertNotIn("gold", json.dumps(payload).lower())
                self.assertNotIn("GOLD_CANARY", json.dumps(payload))
            for config_id in extension.EXPECTED_CONFIG_IDS:
                parsed = shared.parsed_path_for(out_dir, config_id)
                raw = shared.raw_path_for(out_dir, config_id)
                self.assertEqual(shared.count_jsonl_lines(parsed), 40)
                self.assertEqual(shared.count_jsonl_lines(raw), 40)
                self.assertNotIn("GOLD_CANARY", parsed.read_text(encoding="utf-8"))
            summary = json.loads((out_dir / "reports/run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["scope_id"], extension.CURRENT_SCOPE)
            self.assertEqual(summary["planned_rows"], 640)
            self.assertEqual(summary["successful_rows"], 640)

    def test_429_is_fsynced_then_stops_without_retry_or_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "results_40_current_16"
            code, client, fake_server = self.run_execute(
                out_dir, response_script=[(429, '{"error":"rate limited"}', "HTTPError:429")])
            self.assertEqual(code, shared.EXIT_RATE_LIMITED)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(fake_server.starts, [fixture_manifest()["configurations"][0]["port"]])
            raw_path = shared.raw_path_for(out_dir, extension.EXPECTED_CONFIG_IDS[0])
            raw_rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["http_status"], 429)
            self.assertEqual(raw_rows[0]["disposition"], "final")
            summary = json.loads((out_dir / "reports/run_summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["rate_limited_stop"])
            self.assertEqual(summary["rate_limited_config"], extension.EXPECTED_CONFIG_IDS[0])
            self.assertEqual(summary["per_config"], [])


if __name__ == "__main__":
    unittest.main()
