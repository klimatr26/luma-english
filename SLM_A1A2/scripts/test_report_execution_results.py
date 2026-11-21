"""Synthetic, offline tests for the execution-result reporting safeguards."""

from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock

import report_execution_results as report


class ReportExecutionResultsTests(unittest.TestCase):
    def _inventory(self, case_count: int, config_count: int) -> report.ScopeInventory:
        cases = [{"id": f"case-{i:03d}", "level": "A1", "condition": "incorrect"}
                 for i in range(case_count)]
        configs = [{"config_id": f"config-{i:02d}", "id": f"model-{i:02d}"}
                   for i in range(config_count)]
        for config in configs:
            config["model_sha256"] = "c" * 64
        return report.ScopeInventory(
            scope="synthetic",
            benchmark_path=report.Path("synthetic-benchmark.json"),
            result_dir=report.Path("synthetic-results"),
            benchmark_sha256="a" * 64,
            manifest_sha256="b" * 64,
            cases=cases,
            configurations=configs,
        )

    def test_development_matrix_has_exact_unique_120_by_16_cells(self) -> None:
        inventory = self._inventory(120, 16)
        rows = report.build_case_matrix(
            inventory, {}, {}, {}, {},
            {f"config-{i:02d}": "not_collected" for i in range(16)},
        )
        keys = {(row["config_id"], row["case_id"]) for row in rows}
        self.assertEqual(len(rows), 1920)
        self.assertEqual(len(keys), 1920)
        self.assertTrue(all(row["case_status"] == "not_collected" for row in rows))
        self.assertTrue(all(row["verdict_provisional"] is None for row in rows))

    def test_extension_matrix_has_exact_unique_40_by_2_cells(self) -> None:
        inventory = self._inventory(40, 2)
        rows = report.build_case_matrix(
            inventory, {}, {}, {}, {},
            {"config-00": "not_collected", "config-01": "not_collected"},
        )
        self.assertEqual(len(rows), 80)
        self.assertEqual(len({(row["config_id"], row["case_id"]) for row in rows}), 80)

    def test_current_model_extension_matrix_has_exact_unique_40_by_16_cells(self) -> None:
        inventory = self._inventory(40, 16)
        rows = report.build_case_matrix(
            inventory, {}, {}, {}, {},
            {f"config-{i:02d}": "not_collected" for i in range(16)},
        )
        keys = {(row["config_id"], row["case_id"]) for row in rows}
        self.assertEqual(len(rows), 640)
        self.assertEqual(len(keys), 640)

    def test_current16_authorization_matches_full_manifest_scope(self) -> None:
        authorization = report.load_json(report.EXPANSION_AUTHORIZATION)
        manifest = report.load_json(report.MANIFEST)
        manifest_ids = [c["config_id"] for c in manifest["configurations"]
                        if "development_120" in c.get("supported_benchmarks", [])]
        report.validate_scope_binding(
            scope="results_40_current_16",
            benchmark_sha256=report.EXPECTED_BENCHMARK_SHA256["results_40_current_16"],
            manifest_sha256=report.PINNED_MANIFEST_SHA256,
            expected_config_ids=authorization["phase1_extension"]["config_ids"],
            manifest_config_ids=manifest_ids,
        )
        self.assertEqual(authorization["phase1_extension"]["planned_rows"], 640)
        self.assertEqual(authorization["phase1_extension"]["scope_id"],
                         report.SCOPE_IDS["results_40_current_16"])

    def test_current16_validation_record_binds_all_scope_identities(self) -> None:
        config_ids = [f"config-{i:02d}" for i in range(16)]
        valid = {
            "status": "VALIDATED_PENDING_USER_APPROVAL",
            "scope_id": "phase1_40_current_16",
            "benchmark_sha256": report.EXPECTED_BENCHMARK_SHA256["results_40_current_16"],
            "manifest_sha256": report.PINNED_MANIFEST_SHA256,
            "case_count": 40,
            "planned_rows": 640,
            "config_ids": config_ids,
            "phase1_baseline_record_sha256": report.PINNED_PHASE1_BASELINE_SHA256,
            "expansion_authorization_sha256": "d" * 64,
        }
        report.validate_current16_validation_record(
            valid,
            benchmark_sha256=report.EXPECTED_BENCHMARK_SHA256["results_40_current_16"],
            manifest_sha256=report.PINNED_MANIFEST_SHA256,
            config_ids=config_ids,
            phase1_baseline_sha256=report.PINNED_PHASE1_BASELINE_SHA256,
            authorization_sha256="d" * 64,
        )
        invalid = dict(valid, config_ids=config_ids[:-1] + ["substituted-config"])
        with self.assertRaisesRegex(report.ReportError, "config_ids"):
            report.validate_current16_validation_record(
                invalid,
                benchmark_sha256=report.EXPECTED_BENCHMARK_SHA256["results_40_current_16"],
                manifest_sha256=report.PINNED_MANIFEST_SHA256,
                config_ids=config_ids,
                phase1_baseline_sha256=report.PINNED_PHASE1_BASELINE_SHA256,
                authorization_sha256="d" * 64,
            )

    def test_complete_coverage_refuses_missing_case_and_missing_config(self) -> None:
        complete = [
            {"config_id": "c1", "selected_parsed_cases": 120, "raw_final_cases": 120},
            {"config_id": "c2", "selected_parsed_cases": 120, "raw_final_cases": 120},
        ]
        self.assertIsNone(report.assert_complete_coverage(complete, 120, {"c1", "c2"}))
        incomplete_case = [dict(complete[0]), dict(complete[1])]
        incomplete_case[0]["selected_parsed_cases"] = 119
        with self.assertRaisesRegex(report.ReportError, "c1"):
            report.assert_complete_coverage(incomplete_case, 120, {"c1", "c2"})
        substituted = [dict(complete[0]), dict(complete[1])]
        substituted[1]["config_id"] = "c3"
        with self.assertRaisesRegex(report.ReportError, "identities differ"):
            report.assert_complete_coverage(substituted, 120, {"c1", "c2"})
        with self.assertRaisesRegex(report.ReportError, "identities differ"):
            report.assert_complete_coverage(complete[:1], 120, {"c1", "c2"})

    def test_scope_binding_rejects_changed_benchmark_or_config_matrix(self) -> None:
        report.validate_scope_binding(
            scope="results_120",
            benchmark_sha256=report.EXPECTED_BENCHMARK_SHA256["results_120"],
            manifest_sha256=report.PINNED_MANIFEST_SHA256,
            expected_config_ids=["c1", "c2"],
            manifest_config_ids=["c1", "c2"],
        )
        with self.assertRaisesRegex(report.ReportError, "benchmark SHA"):
            report.validate_scope_binding(
                scope="results_120", benchmark_sha256="0" * 64,
                manifest_sha256=report.PINNED_MANIFEST_SHA256,
                expected_config_ids=["c1", "c2"], manifest_config_ids=["c1", "c2"],
            )
        with self.assertRaisesRegex(report.ReportError, "Manifest SHA"):
            report.validate_scope_binding(
                scope="results_120",
                benchmark_sha256=report.EXPECTED_BENCHMARK_SHA256["results_120"],
                manifest_sha256="0" * 64,
                expected_config_ids=["c1", "c2"], manifest_config_ids=["c1", "c2"],
            )
        with self.assertRaisesRegex(report.ReportError, "configuration matrix"):
            report.validate_scope_binding(
                scope="results_120",
                benchmark_sha256=report.EXPECTED_BENCHMARK_SHA256["results_120"],
                manifest_sha256=report.PINNED_MANIFEST_SHA256,
                expected_config_ids=["c1", "c2"], manifest_config_ids=["c1"],
            )

    def test_absent_telemetry_is_counted_as_missing_not_zero(self) -> None:
        telemetry = report._telemetry_summary([], [], [], expected_cases=4)
        gpu = telemetry["numeric"]["gpu_used_bytes"]
        self.assertEqual(gpu["expected"], 4)
        self.assertEqual(gpu["observed"], 0)
        self.assertEqual(gpu["missing"], 4)
        self.assertIsNone(gpu["median"])
        self.assertEqual(telemetry["finish_reason_counts"], {"missing": 4})
        self.assertEqual(telemetry["memory_sampling"]["gpu_note_counts"], {"missing": 4})

    def test_terminal_technical_failure_is_kept_as_a_recorded_raw_case(self) -> None:
        config = {"config_id": "c1", "model_sha256": "c" * 64}
        row = {
            "resume_key": ":".join(["a" * 64, "c" * 64, "b" * 64, "c1", "case-001"]),
            "attempt": 1, "disposition": "final",
            "benchmark_sha256": "a" * 64, "manifest_sha256": "b" * 64,
            "model_sha256": "c" * 64, "config_id": "c1", "case_id": "case-001",
            "http_status": None, "response_body_exact": "", "error": "timeout",
            "latency_seconds": 2.0,
        }
        indexed = report._raw_final_index([row], {"case-001"}, config,
                                          "a" * 64, "b" * 64)
        self.assertIn("case-001", indexed)
        self.assertEqual(report._raw_outcome(indexed["case-001"]), "transport_error")

    def test_trailing_unfinished_retry_group_does_not_count_an_older_final(self) -> None:
        config = {"config_id": "c1", "model_sha256": "c" * 64}
        resume = ":".join(["a" * 64, "c" * 64, "b" * 64, "c1", "case-001"])
        base = {
            "resume_key": resume, "benchmark_sha256": "a" * 64,
            "manifest_sha256": "b" * 64, "model_sha256": "c" * 64,
            "config_id": "c1", "case_id": "case-001",
            "http_status": 503, "response_body_exact": "{}", "error": None,
            "latency_seconds": 1.0,
        }
        attempts = [
            {**base, "attempt": 1, "disposition": "final"},
            {**base, "attempt": 2, "disposition": "retry"},
        ]
        indexed = report._raw_final_index(attempts, {"case-001"}, config,
                                          "a" * 64, "b" * 64)
        self.assertEqual(indexed, {})

    def _synthetic_raw_attempt(self, case_id: str, *, attempt: int = 1,
                               disposition: str = "final",
                               retry_mode: str | None = None,
                               retry_of_attempt: int | None = None,
                               retry_of_outcome: str | None = None) -> dict:
        config = {"config_id": "config-00", "model_sha256": "c" * 64}
        resume = ":".join(["a" * 64, "c" * 64, "b" * 64,
                           "config-00", case_id])
        row = {
            "resume_key": resume, "attempt": attempt,
            "disposition": disposition,
            "benchmark_sha256": "a" * 64, "manifest_sha256": "b" * 64,
            "model_sha256": "c" * 64, "config_id": "config-00",
            "case_id": case_id, "http_status": 200,
            "response_body_exact": json.dumps({"choices": [{"finish_reason": "stop"}]}),
            "error": None, "latency_seconds": 1.0,
        }
        if retry_mode is not None:
            row["retry_mode"] = retry_mode
            row["retry_of_attempt"] = retry_of_attempt
            row["retry_of_outcome"] = retry_of_outcome
        return row

    def _run_synthetic_incomplete_scope(self, parsed_rows: list[dict],
                                        attempt_rows: list[dict]) -> tuple[dict, list[dict]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            inventory = report.ScopeInventory(
                scope="results_120", benchmark_path=Path("synthetic-benchmark.json"),
                result_dir=base, benchmark_sha256="a" * 64,
                manifest_sha256="b" * 64,
                cases=[{"id": "case-001"}, {"id": "case-002"}],
                configurations=[{"config_id": "config-00", "id": "model-00",
                                 "model_sha256": "c" * 64}],
            )

            def read_rows(path: Path) -> list[dict]:
                return parsed_rows if path.parent.name == "config-00" and "parsed" in path.parts else attempt_rows

            with (mock.patch.object(report, "load_scope_inventory", return_value=inventory),
                  mock.patch.object(report, "_read_existing_jsonl", side_effect=read_rows),
                  mock.patch.object(report, "_run_evaluator") as run_evaluator):
                summary = report.execute("results_120")
                run_evaluator.assert_not_called()
            with (base / "reports" / "case_matrix.csv").open(encoding="utf-8", newline="") as handle:
                matrix = list(report.csv.DictReader(handle))
            return summary, matrix

    def test_partial_configuration_is_not_scored_and_keeps_full_matrix(self) -> None:
        parsed = [{"case_id": "case-001"}]
        attempts = [self._synthetic_raw_attempt("case-001")]
        summary, matrix = self._run_synthetic_incomplete_scope(parsed, attempts)
        config = summary["configuration_summaries"][0]
        self.assertEqual(summary["case_matrix_rows"], 2)
        self.assertEqual(config["status"], "partial")
        self.assertEqual(config["selected_parsed_cases"], 0)
        self.assertEqual(config["verified_raw_final_cases"], 0)
        self.assertEqual(config["raw_final_candidates"], 1)
        self.assertTrue(all(row["verdict_provisional"] == "" for row in matrix))
        first = next(row for row in matrix if row["case_id"] == "case-001")
        self.assertEqual(first["case_status"], "pending_full_coverage")
        self.assertEqual(first["raw_final_verified"], "False")

    def test_raw_only_invalid_retry_after_ok_is_reported_unverified(self) -> None:
        attempts = [
            self._synthetic_raw_attempt("case-001", attempt=1,
                                        retry_mode="initial"),
            self._synthetic_raw_attempt("case-001", attempt=2,
                                        retry_mode="retry_failed",
                                        retry_of_attempt=1,
                                        retry_of_outcome="ok"),
        ]
        summary, matrix = self._run_synthetic_incomplete_scope([], attempts)
        config = summary["configuration_summaries"][0]
        self.assertEqual(config["status"], "raw_only_unverified")
        self.assertEqual(config["raw_final_candidates"], 1)
        self.assertEqual(config["verified_raw_final_cases"], 0)
        first = next(row for row in matrix if row["case_id"] == "case-001")
        self.assertEqual(first["case_status"], "raw_only_unverified")
        self.assertEqual(first["raw_final_recorded"], "True")
        self.assertEqual(first["raw_final_verified"], "False")

    def test_evaluator_subprocess_receives_scope_and_optional_registry(self) -> None:
        inventory = self._inventory(2, 1)
        config = inventory.configurations[0]
        with mock.patch.object(report.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stderr="", stdout="")) as run:
            report._run_evaluator(
                inventory, config, Path("parsed.jsonl"), Path("attempts.jsonl"),
                Path("evals.jsonl"), Path("summary.json"), Path("invalid.json"))
        command = run.call_args.args[0]
        self.assertIn("--benchmark", command)
        self.assertIn(str(inventory.benchmark_path), command)
        self.assertIn("--config", command)
        self.assertIn(config["config_id"], command)
        self.assertIn("--attempts", command)
        self.assertIn("attempts.jsonl", command)
        self.assertIn("--invalid-cases", command)
        self.assertIn("invalid.json", command)


if __name__ == "__main__":
    unittest.main()
