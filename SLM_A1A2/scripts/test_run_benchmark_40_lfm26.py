"""Synthetic gate tests for the isolated LFM26 Phase 1 extension runner.

These fixtures do not read or modify the real Phase 1 benchmark/results, do not
use a model, and do not start a server or send a request.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_benchmark_40_lfm26 as extension
import run_benchmark_120 as shared


SYN_SHA = "ab" * 32


def fixture_manifest():
    rows = []
    target_specs = {
        extension.EXPECTED_CONFIG_IDS[0]: ("Q8_0", 8115,
                                           extension.EXPECTED_MODELS[extension.EXPECTED_CONFIG_IDS[0]]),
        extension.EXPECTED_CONFIG_IDS[1]: ("Q4_K_M", 8116,
                                           extension.EXPECTED_MODELS[extension.EXPECTED_CONFIG_IDS[1]]),
    }
    ids = [f"SYN-CFG-{i:02d}" for i in range(14)] + list(extension.EXPECTED_CONFIG_IDS)
    for index, cid in enumerate(ids):
        if cid in target_specs:
            quant, port, model = target_specs[cid]
            family = "lfm26"
            supported = ["development_120", "phase1_40_lfm26_extension"]
            source = {"repo": extension.EXPECTED_REPO,
                      "revision": extension.EXPECTED_REVISION}
            gguf = {"path": model, "status": "verified"}
        else:
            quant, port, model = "SYNTHETIC", 18000 + index, f"synthetic/model-{index}.gguf"
            family, supported = "synthetic", ["development_120"]
            source = {"repo": "synthetic/repo", "revision": "synthetic-revision"}
            gguf = {"path": model, "status": "verified"}
        rows.append({
            "config_id": cid, "id": cid, "family": family, "quant": quant,
            "supported_benchmarks": supported,
            "model_path": model, "model_sha256": SYN_SHA,
            "server_command": ["llama-server", "-m", model, "--host", "127.0.0.1",
                               "--port", str(port), "-c", "4096", "--parallel", "1",
                               "-ngl", "999", '--reasoning', 'off', '--reasoning-budget', '0'],
            "port": port,
            "generation": {"max_tokens": 512, "temperature": 0.1, 'reasoning_budget_tokens': 0},
            "runtime": {"parallel_sequences": 1},
            "source": source, "gguf": gguf,
        })
    return {"configurations": rows}


def fixture_readiness(manifest, manifest_sha):
    return {"manifest_sha256": manifest_sha,
            "configs": [{"config_id": row["config_id"], "status": "pass",
                         "model_sha256": row["model_sha256"]}
                        for row in manifest["configurations"]]}


def fixture_validation(baseline_sha=extension.PHASE1_BASELINE_SHA256):
    return {"status": "VALIDATED_PENDING_USER_APPROVAL",
            "benchmark_sha256": extension.PHASE1_BENCHMARK_SHA256,
            "case_count": 40, "scope_id": extension.EXTENSION_SCOPE,
            "config_ids": list(extension.EXPECTED_CONFIG_IDS),
            "blocker_count": 0, "review_count": 0,
            "execution_approved": False,
            "phase1_baseline_record_sha256": baseline_sha}


class Phase1BaselineTests(unittest.TestCase):
    def test_verifies_synthetic_inventory_and_benchmark_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = []
            for index in range(24):
                rel = ("benchmark_smoke_test_v2.json" if index == 0
                       else f"synthetic/phase1-{index:02d}.bin")
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = f"synthetic artifact {index}".encode()
                path.write_bytes(payload)
                records.append({"path": rel, "size_bytes": len(payload),
                                "sha256": hashlib.sha256(payload).hexdigest()})
            baseline_bytes = json.dumps({"files": records}, separators=(",", ":")).encode()
            baseline_path = root / "baseline.json"
            baseline_path.write_bytes(baseline_bytes)
            got = extension.verify_phase1_baseline(
                root, baseline_path=baseline_path,
                expected_baseline_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
                expected_benchmark_sha256=records[0]["sha256"])
            self.assertEqual(got["verified_files"], 24)
            self.assertEqual(got["benchmark_sha256"], records[0]["sha256"])

    def test_rejects_changed_phase1_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = []
            for index in range(24):
                rel = ("benchmark_smoke_test_v2.json" if index == 0
                       else f"artifact-{index:02d}.bin")
                payload = f"fixture {index}".encode()
                (root / rel).write_bytes(payload)
                records.append({"path": rel, "size_bytes": len(payload),
                                "sha256": hashlib.sha256(payload).hexdigest()})
            baseline_bytes = json.dumps({"files": records}, separators=(",", ":")).encode()
            baseline_path = root / "baseline.json"
            baseline_path.write_bytes(baseline_bytes)
            (root / records[1]["path"]).write_bytes(b"changed")
            with self.assertRaisesRegex(extension.ExtensionGateError, "size mismatch|hash mismatch"):
                extension.verify_phase1_baseline(
                    root, baseline_path=baseline_path,
                    expected_baseline_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
                    expected_benchmark_sha256=records[0]["sha256"])


class ExtensionGateTests(unittest.TestCase):
    def test_manifest_is_full_16_and_scope_is_exact_two_configs(self):
        manifest = fixture_manifest()
        normalized, by_id = extension.validate_extension_manifest(manifest)
        self.assertEqual(len(normalized), 16)
        self.assertEqual(tuple(cfg["config_id"] for cfg in normalized[-2:]),
                         extension.EXPECTED_CONFIG_IDS)
        self.assertEqual([by_id[cid]["port"] for cid in extension.EXPECTED_CONFIG_IDS],
                         [8115, 8116])

    def test_manifest_rejects_wrong_quant_and_missing_parallel_declaration(self):
        manifest = fixture_manifest()
        manifest["configurations"][-1]["quant"] = "Q4_0"
        with self.assertRaisesRegex(extension.ExtensionGateError, "family/quantization"):
            extension.validate_extension_manifest(manifest)
        manifest = fixture_manifest()
        manifest["configurations"][0]["runtime"].pop("parallel_sequences")
        with self.assertRaisesRegex(extension.ExtensionGateError, "parallel_sequences=1"):
            extension.validate_extension_manifest(manifest)

    def test_readiness_must_be_complete_and_manifest_sha_bound(self):
        manifest = fixture_manifest()
        configs = shared.validate_manifest(manifest)
        readiness = fixture_readiness(manifest, SYN_SHA)
        good = extension.validate_extension_readiness(configs, readiness, SYN_SHA)
        self.assertEqual(good["passed"], 16)
        readiness["manifest_sha256"] = "cd" * 32
        with self.assertRaisesRegex(extension.ExtensionGateError, "exact current manifest SHA"):
            extension.validate_extension_readiness(configs, readiness, SYN_SHA)
        readiness = fixture_readiness(manifest, SYN_SHA)
        readiness["configs"].pop()
        with self.assertRaisesRegex(extension.ExtensionGateError, "exactly 16"):
            extension.validate_extension_readiness(configs, readiness, SYN_SHA)

    def test_validation_binds_scope_case_count_config_ids_and_baseline(self):
        report = fixture_validation()
        accepted = extension.validate_extension_report(
            report, benchmark_sha256=extension.PHASE1_BENCHMARK_SHA256)
        self.assertEqual(accepted["case_count"], 40)
        report["config_ids"] = [extension.EXPECTED_CONFIG_IDS[0]]
        with self.assertRaisesRegex(extension.ExtensionGateError, "exactly the two"):
            extension.validate_extension_report(
                report, benchmark_sha256=extension.PHASE1_BENCHMARK_SHA256)

    def test_validation_never_substitutes_another_dataset_sha(self):
        report = fixture_validation()
        with self.assertRaisesRegex(extension.ExtensionGateError, "pinned Phase 1 v2 SHA"):
            extension.validate_extension_report(report, benchmark_sha256="0" * 64)
        with self.assertRaisesRegex(shared.AuthorizationError, "Only the pinned"):
            extension.preflight(authorize_execution=True,
                                approved_phase1_sha256="0" * 64)

    def test_shared_benchmark_contract_accepts_exact_40_case_fixture(self):
        cases = [{"id": f"SYN-{i:02d}", "level": "A1", "task": "synthetic",
                  "student_text": f"A synthetic sentence {i}.", "gold": {}}
                 for i in range(40)]
        data = {"benchmark_id": "synthetic-phase1-extension", "version": "synthetic",
                "system_prompt": "synthetic system",
                "user_prompt_template": "{student_text}", "cases": cases}
        _, validated = shared.validate_benchmark(data, expected_cases=40)
        self.assertEqual(len(validated), 40)


class SyntheticExecutionTests(unittest.TestCase):
    def test_runs_only_two_configs_into_the_separate_output_tree(self):
        manifest = fixture_manifest()
        normalized, by_id = extension.validate_extension_manifest(manifest)
        cases = [{"id": f"SYN-{i:02d}", "level": "A1", "task": "synthetic",
                  "student_text": f"A synthetic sentence {i}.",
                  "gold": {"corrected_text": "SYNTHETIC_GOLD_CANARY"}}
                 for i in range(40)]
        benchmark = {"benchmark_id": "synthetic-extension", "version": "synthetic",
                     "system_prompt": "synthetic system",
                     "user_prompt_template": "Level {level}; {student_text}",
                     "cases": cases}
        gates = {"benchmark_sha256": "a" * 64, "manifest_sha256": "b" * 64,
                 "benchmark_id": benchmark["benchmark_id"], "cases": cases,
                 "system_prompt": benchmark["system_prompt"],
                 "user_prompt_template": benchmark["user_prompt_template"],
                 "configs": [by_id[cid] for cid in extension.EXPECTED_CONFIG_IDS],
                 "configs_by_id": by_id,
                 "readiness": {"passed": 16, "required": 16},
                 "phase1_integrity": {"baseline_sha256": "c" * 64}}

        class FakeClient:
            def __init__(self):
                self.calls = []

            def post_json(self, url, payload):
                self.calls.append((url, payload))
                body = json.dumps({"choices": [{"finish_reason": "stop",
                                                  "message": {"content": "synthetic response"}}],
                                   "usage": {"prompt_tokens": 2, "completion_tokens": 2}})
                return 200, body, None

            def get(self, url):
                return 200, '{"status":"ok"}'

        class FakeServer:
            live = 0
            max_live = 0
            starts = []

            def __init__(self, argv, port, log_path):
                self.argv, self.port, self.log_path, self.pid = argv, port, log_path, None
                type(self).starts.append(port)

            def __enter__(self):
                type(self).live += 1
                type(self).max_live = max(type(self).max_live, type(self).live)
                return self

            def __exit__(self, *args):
                type(self).live -= 1
                return False

            def wait_healthy(self, client, deadline, interval):
                return True

        fake_client = FakeClient()
        args = SimpleNamespace(
            authorize_execution=True, approved_phase1_sha256=extension.PHASE1_BENCHMARK_SHA256,
            dry_run=False, retry_failed=False, api_path="/v1/chat/completions",
            health_path="/health", request_timeout=1.0, health_timeout=1.0,
            health_interval=0.0, max_retries=0)
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "results_40_lfm26"
            with mock.patch.object(extension, "OUT_DIR", out_dir), \
                    mock.patch.object(extension, "preflight", return_value=gates), \
                    mock.patch.object(shared, "load_json", return_value=benchmark):
                code = extension.execute(args, client_factory=lambda: fake_client,
                                         server_factory=lambda argv, port, log:
                                         FakeServer(argv, port, log))
            self.assertEqual(code, shared.EXIT_OK)
            self.assertEqual(FakeServer.starts, [8115, 8116])
            self.assertEqual(FakeServer.max_live, 1)
            self.assertEqual(len(fake_client.calls), 80)
            self.assertTrue(all("gold" not in payload
                                for _, payload in fake_client.calls))
            for cid in extension.EXPECTED_CONFIG_IDS:
                parsed = out_dir / "parsed" / cid / "responses.jsonl"
                raw = out_dir / "raw" / cid / "attempts.jsonl"
                self.assertEqual(len(parsed.read_text(encoding="utf-8").splitlines()), 40)
                self.assertEqual(len(raw.read_text(encoding="utf-8").splitlines()), 40)
            summary = json.loads((out_dir / "reports" / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["planned_rows"], 80)
            self.assertEqual(summary["scope_id"], extension.EXTENSION_SCOPE)


if __name__ == "__main__":
    unittest.main()
