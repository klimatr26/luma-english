"""Unit tests for SLM_A1A2/run_benchmark_120.py.

Every fixture below is synthetic (SYN- ids, invented micro-sentences) and
lives in temporary directories. No real benchmark case, manifest, model,
server, or network is touched: HTTP and server processes are fakes, and the
runner is NEVER executed for real here (dry-run tests assert zero side
effects; execution tests inject a fake client + fake server factory).
"""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_benchmark_120 as runner
from run_benchmark_120 import (
    CheckpointMismatchError,
    GateError,
    PeakSampler,
    build_parser,
    check_argv_executable,
    check_argv_policy,
    check_port_free,
    check_readiness,
    check_validation,
    classify_http_status,
    count_jsonl_lines,
    derive_parsed_row,
    execute,
    extract_message_content,
    finalize_outcome,
    has_repetition,
    is_healthy_response,
    max_attempt_for_key,
    outcome_manual_retry_eligible,
    parse_nvidia_smi_mib,
    replay_raw_authority,
    resolve_argv,
    resume_key,
    run_single_case,
    sample_gpu,
    select_plan,
    split_resume_key,
    validate_benchmark,
    validate_manifest,
    verify_model_file,
)
from authorization_guard import AuthorizationError

CANARY = "GOLD_CANARY_MUST_NEVER_LEAK"
MODEL_SHA = "ab" * 32


def syn_benchmark(n_incorrect=90, n_correct=30):
    cases = []
    total = n_incorrect + n_correct
    for i in range(total):
        incorrect = i < n_incorrect
        cases.append({
            "id": f"SYN-{'E' if incorrect else 'C'}{i:03d}",
            "level": "A1" if i % 2 == 0 else "A2",
            "condition": "incorrect" if incorrect else "correct",
            "task": "synthetic task",
            "student_text": f"Synthetic sentence {i} about a small green lamp.",
            "gold": {"is_correct": not incorrect,
                     "corrected_text": f"fixed {CANARY} {i}",
                     "errors": ([{"original": "lamp", "correction": "lamps",
                                  "type": "SYN", "explanation": "synthetic"}]
                                if incorrect else []),
                     "acceptable_alternatives": []},
        })
    return {"benchmark_id": "synthetic-120", "version": "0.0-test",
            "system_prompt": "synthetic system prompt",
            "user_prompt_template": "Level: {level}\nTask: {task}\nStudent text: {student_text}",
            "cases": cases}


def syn_argv(i=0):
    return ["llama-server", "--host", "127.0.0.1", "-c", "4096", "-ngl", "999",
            "-m", f"synthetic/model-{i}.gguf", "--port", str(18001 + i), '--reasoning', 'off', '--reasoning-budget', '0']


def syn_manifest(n=16):
    return {"configurations": [
        {"config_id": f"SYN-CFG-{i:02d}", "server_command": syn_argv(i),
         "port": 18001 + i, "model_path": f"synthetic/model-{i}.gguf",
         "model_sha256": MODEL_SHA,
         "generation": {"max_tokens": 512, "temperature": 0.7, 'reasoning_budget_tokens': 0}}
        for i in range(n)]}


def syn_readiness(ids, manifest_sha=None):
    return {"manifest_sha256": manifest_sha,
            "configs": [{"config_id": cid, "status": "pass"} for cid in ids]}


def write_tree(tmpdir):
    root = Path(tmpdir)
    bench = syn_benchmark()
    (root / "bench.json").write_text(json.dumps(bench), encoding="utf-8")
    sha = runner.sha256_file(root / "bench.json")
    man = syn_manifest()
    (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    ids = [c["config_id"] for c in man["configurations"]]
    msha = runner.sha256_file(root / "manifest.json")
    (root / "readiness.json").write_text(json.dumps(syn_readiness(ids, msha)), encoding="utf-8")
    (root / "validation.json").write_text(json.dumps(
        {"status": "VALIDATED_PENDING_USER_APPROVAL", "blocker_count": 0,
         "review_count": 0, "benchmark_sha256": sha}), encoding="utf-8")
    return root, sha


def base_argv(root, sha, extra=()):
    return ["--benchmark", str(root / "bench.json"),
            "--manifest", str(root / "manifest.json"),
            "--readiness-report", str(root / "readiness.json"),
            "--validation-report", str(root / "validation.json"),
            "--out-dir", str(root / "out"),
            "--authorize-execution",
            "--approved-benchmark-sha256", sha, *extra]


OK_BODY = json.dumps({"choices": [{"finish_reason": "stop",
                                   "message": {"content": '{"is_correct": true}'}}],
                      "usage": {"prompt_tokens": 5, "completion_tokens": 7}})


class FakeClient:
    """Scripted HTTP double. script: list of (status, body, error)."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls = []

    def post_json(self, url, payload):
        self.calls.append((url, payload))
        if self.script:
            return self.script.pop(0)
        return 200, OK_BODY, None

    def get(self, url):
        return 200, '{"status": "ok"}'


class FakeServer:
    tracker = {"live": 0, "max_live": 0, "starts": []}

    def __init__(self, argv, port, log_path, healthy=True):
        self.argv = argv
        self.port = port
        self.pid = None  # no real child: sampler degrades to explicit nulls
        self.healthy = healthy
        FakeServer.tracker["starts"].append(argv)

    def __enter__(self):
        FakeServer.tracker["live"] += 1
        FakeServer.tracker["max_live"] = max(FakeServer.tracker["max_live"],
                                             FakeServer.tracker["live"])
        return self

    def __exit__(self, *args):
        FakeServer.tracker["live"] -= 1
        return False

    def wait_healthy(self, client, deadline_seconds, interval_seconds):
        return self.healthy


def reset_tracker():
    FakeServer.tracker = {"live": 0, "max_live": 0, "starts": []}


class ContractTests(unittest.TestCase):
    def test_benchmark_requires_exact_shape(self):
        good = syn_benchmark()
        meta, cases = validate_benchmark(good)
        self.assertEqual(len(cases), 120)
        bad = dict(good)
        del bad["system_prompt"]
        with self.assertRaises(GateError):
            validate_benchmark(bad)
        short = dict(good, cases=good["cases"][:119])
        with self.assertRaises(GateError):
            validate_benchmark(short)
        dup = dict(good, cases=[dict(c) for c in good["cases"]])
        dup["cases"][1] = dict(dup["cases"][0])
        with self.assertRaises(GateError):
            validate_benchmark(dup)
        nogold = json.loads(json.dumps(good))
        del nogold["cases"][0]["gold"]
        with self.assertRaises(GateError):
            validate_benchmark(nogold)

    def test_manifest_requires_sixteen_and_names_gaps(self):
        with self.assertRaises(GateError):
            validate_manifest(syn_manifest(15))
        man = syn_manifest()
        del man["configurations"][3]["server_command"]
        with self.assertRaises(GateError) as ctx:
            validate_manifest(man)
        self.assertIn("server_command", str(ctx.exception))
        man = syn_manifest()
        del man["configurations"][5]["model_sha256"]
        with self.assertRaises(GateError):
            validate_manifest(man)
        man = syn_manifest()
        man["configurations"][7]["generation"]["max_tokens"] = 513
        with self.assertRaises(GateError):
            validate_manifest(man)
        man = syn_manifest()
        man["configurations"][2]["generation"]["grammar"] = "forbidden"
        with self.assertRaises(GateError):
            validate_manifest(man)
        man = syn_manifest()
        man["configurations"][1]["config_id"] = man["configurations"][0]["config_id"]
        with self.assertRaises(GateError):
            validate_manifest(man)
        man = syn_manifest()
        man["configurations"][0]["port"] = True  # bools are not valid ports
        with self.assertRaises(GateError):
            validate_manifest(man)
        man = syn_manifest()
        man["configurations"][0]["server_command"][8] = "synthetic/other-model.gguf"
        with self.assertRaisesRegex(GateError, "model path differs"):
            validate_manifest(man)

    def test_parallel_runtime_is_enforced_only_when_declared(self):
        man = syn_manifest()
        self.assertIsNone(validate_manifest(man)[0]["parallel_sequences"])
        man["configurations"][0]["runtime"] = {"parallel_sequences": 1}
        with self.assertRaisesRegex(GateError, "--parallel 1"):
            validate_manifest(man)
        man["configurations"][0]["server_command"].extend(["--parallel", "1"])
        configs = validate_manifest(man)
        self.assertEqual(configs[0]["parallel_sequences"], 1)

    def test_model_file_sha_and_size_are_verified_without_model_loading(self):
        import hashlib
        import tempfile
        payload = b"synthetic GGUF marker bytes only"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.gguf"
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            verified = verify_model_file(str(path), digest, len(payload))
            self.assertEqual(verified["sha256"], digest)
            self.assertTrue(verified["stable"])
            with self.assertRaisesRegex(GateError, "size.*differs"):
                verify_model_file(str(path), digest, len(payload) + 1)
            with self.assertRaisesRegex(GateError, "SHA-256.*differs"):
                verify_model_file(str(path), "0" * 64, len(payload))
            calls = []

            def spawn(argv, **kwargs):
                calls.append(argv)
                raise AssertionError("bad model hash must stop before spawn")

            server = runner.ManagedServer(
                [sys.executable, "-c", "pass"], 0, "http://127.0.0.1:0/health",
                Path(tmp) / "server.log", popen_factory=spawn,
                model_path=str(path), model_sha256="0" * 64,
                model_size_bytes=len(payload))
            with self.assertRaisesRegex(GateError, "SHA-256.*differs"):
                server.__enter__()
            self.assertEqual(calls, [])

    def test_argv_policy_bind_context_gpu(self):
        check_argv_policy(syn_argv())
        with self.assertRaisesRegex(GateError, "--parallel 1"):
            check_argv_policy(syn_argv(), parallel_sequences=1)
        check_argv_policy(syn_argv() + ["--parallel", "1"], parallel_sequences=1)
        with self.assertRaises(GateError):
            check_argv_policy(syn_argv() + ["--parallel", "2"], parallel_sequences=1)
        reasoning_args = ['--reasoning', 'off', '--reasoning-budget', '0']
        no_bind = ["llama-server", "--host", "0.0.0.0", "-c", "4096", "-ngl", "999"] + reasoning_args
        with self.assertRaises(GateError) as ctx:
            check_argv_policy(no_bind)
        self.assertIn("127.0.0.1", str(ctx.exception))
        no_ctx = ["llama-server", "--host", "127.0.0.1", "-c", "2048", "-ngl", "999"]
        with self.assertRaises(GateError):
            check_argv_policy(no_ctx)
        eq_form = ["llama-server", "--host=127.0.0.1", "--ctx-size=4096",
                   "--n-gpu-layers=999"] + reasoning_args
        check_argv_policy(eq_form)
        no_gpu = ["llama-server", "--host", "127.0.0.1", "-c", "4096", "-ngl", "20"]
        with self.assertRaises(GateError):
            check_argv_policy(no_gpu)

    def test_argv_policy_forbids_grammar_mmproj_draft(self):
        base = syn_argv()
        with self.assertRaises(GateError):
            check_argv_policy(base + ["--grammar", "x.gbnf"])
        with self.assertRaises(GateError):
            check_argv_policy(base + ["--mmproj", "clip.gguf"])
        with self.assertRaises(GateError):
            check_argv_policy(base + ["--model-draft", "d.gguf"])
        with self.assertRaises(GateError):
            check_argv_policy(base + ["--draft-max", "8"])
        # A model filename merely containing those letters outside flags is fine.
        base[base.index('-m') + 1] = 'draft-free-model.gguf'
        check_argv_policy(base)

    def test_nonthinking_launch_and_request_cannot_be_overridden(self):
        base = syn_argv()
        check_argv_policy(base)
        for args in (base + ['--reasoning', 'on'], base + ['--reasoning-budget', '-1'],
                     base + ['-rea', 'on'], base + ['--reasoning=auto'],
                     base + ['--chat-template-kwargs', '{"enable_thinking":true}']):
            with self.subTest(args=args), self.assertRaises(GateError):
                check_argv_policy(args)
        for field, value in (('reasoning_budget_tokens', -1), ('reasoning_budget_tokens', False),
                             ('reasoning_effort', 'high'),
                             ('chat_template_kwargs', {'enable_thinking': True})):
            manifest = syn_manifest()
            manifest['configurations'][0]['generation'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(GateError):
                validate_manifest(manifest)

    def test_resolve_argv_relative_model_path(self):
        argv = ["llama-server", "-m", "models/x.gguf", "--host", "127.0.0.1"]
        out = resolve_argv(argv, Path("/root"))
        self.assertEqual(out[2], str(Path("/root") / "models/x.gguf"))
        self.assertEqual(argv[2], "models/x.gguf")  # input untouched
        abs_val = str(Path.cwd().anchor) + "abs_y.gguf"  # absolute on any OS
        abs_argv = ["llama-server", "-m", abs_val]
        self.assertEqual(resolve_argv(abs_argv, Path("/root"))[2], abs_val)

    def test_failure_taxonomy_and_finalize(self):
        self.assertEqual(classify_http_status(200), "ok")
        self.assertEqual(classify_http_status(429), "rate_limited")
        self.assertEqual(classify_http_status(None), "retryable")
        self.assertEqual(classify_http_status(503), "retryable")
        self.assertEqual(classify_http_status(400), "record_once")
        self.assertEqual(finalize_outcome(200, None, OK_BODY), "ok")
        self.assertEqual(finalize_outcome(200, None, "not json {{{"), "invalid_body")
        self.assertEqual(finalize_outcome(429, "HTTPError:429", ""), "rate_limited")
        self.assertEqual(finalize_outcome(None, "TimeoutError:x", ""), "transport_error")
        self.assertEqual(finalize_outcome(503, "HTTPError:503", ""), "http_503")
        self.assertEqual(finalize_outcome(400, "HTTPError:400", ""), "http_400")
        self.assertTrue(outcome_manual_retry_eligible("transport_error"))
        self.assertTrue(outcome_manual_retry_eligible("http_503"))
        self.assertFalse(outcome_manual_retry_eligible("http_400"))
        self.assertFalse(outcome_manual_retry_eligible("ok"))
        self.assertFalse(outcome_manual_retry_eligible("invalid_body"))

    def test_health_rule_only_200_and_ok(self):
        self.assertTrue(is_healthy_response(200, ""))
        self.assertTrue(is_healthy_response(200, "not json"))
        self.assertTrue(is_healthy_response(200, '{"status": "ok"}'))
        self.assertTrue(is_healthy_response(200, '{"other": 1}'))
        self.assertFalse(is_healthy_response(200, '{"status": "loading"}'))
        self.assertFalse(is_healthy_response(200, '{"status": "error"}'))
        self.assertFalse(is_healthy_response(404, ""))
        self.assertFalse(is_healthy_response(400, ""))
        self.assertFalse(is_healthy_response(503, ""))
        self.assertFalse(is_healthy_response(None, ""))

    def test_message_content_and_repetition(self):
        content, source = extract_message_content(OK_BODY)
        self.assertEqual(content, '{"is_correct": true}')
        self.assertEqual(source, "message_content")
        self.assertEqual(extract_message_content("{{{ bad"), ("", "non_json_body"))
        self.assertEqual(extract_message_content('{"choices": []}'), ("", "no_message_content"))
        c, s = extract_message_content(
            json.dumps({"choices": [{"message": {"content": ""}}]}))
        self.assertEqual((c, s), ("", "empty_content"))
        self.assertTrue(has_repetition("word " * 3 + "x" * 200))
        self.assertTrue(has_repetition("alpha beta gamma " * 6))
        self.assertFalse(has_repetition("A short plain synthetic sentence."))
        self.assertFalse(has_repetition(""))


class GateReportTests(unittest.TestCase):
    def test_readiness_binding(self):
        man = syn_manifest()
        ids = [c["config_id"] for c in man["configurations"]]
        cfgs = validate_manifest(man)
        msha = "cc" * 32
        check_readiness(cfgs, syn_readiness(ids, msha), msha)
        with self.assertRaises(GateError):
            check_readiness(cfgs, syn_readiness(ids[:-1], msha), msha)  # 15/16
        with self.assertRaisesRegex(GateError, "unknown config"):
            check_readiness(cfgs, syn_readiness(ids, msha) | {"configs": syn_readiness(ids, msha)["configs"] + [
                {"config_id": "SYN-UNKNOWN", "status": "pass"}]}, msha)
        duplicate = syn_readiness(ids, msha)
        duplicate["configs"].append(dict(duplicate["configs"][0]))
        with self.assertRaisesRegex(GateError, "duplicates config"):
            check_readiness(cfgs, duplicate, msha)
        failed = syn_readiness(ids, msha)
        failed["configs"][0]["status"] = "fail"
        failed["configs"].append({"config_id": "SYN-CFG-00", "status": "pass"})
        with self.assertRaisesRegex(GateError, "not passing"):
            check_readiness(cfgs, failed, msha)
        with self.assertRaises(GateError):
            check_readiness(cfgs, {"unexpected": "shape"}, msha)
        bound = syn_readiness(ids, msha)
        bound["configs"][0]["model_sha256"] = MODEL_SHA
        bound["configs"][0]["manifest_sha256"] = msha
        check_readiness(cfgs, bound, msha)  # matching bindings pass
        bound["configs"][0]["model_sha256"] = "ff" * 32
        with self.assertRaises(GateError):
            check_readiness(cfgs, bound, msha)
        bound["configs"][0]["model_sha256"] = MODEL_SHA
        bound["configs"][0]["manifest_sha256"] = "ff" * 32
        with self.assertRaises(GateError):
            check_readiness(cfgs, bound, msha)
        unbound = syn_readiness(ids)
        with self.assertRaisesRegex(GateError, "top-level manifest_sha256"):
            check_readiness(cfgs, unbound, msha)

    def test_validation_strict_report(self):
        sha = "ab" * 32
        good = {"status": "VALIDATED_PENDING_USER_APPROVAL", "blocker_count": 0,
                "review_count": 0, "benchmark_sha256": sha}
        check_validation(good, sha)
        with self.assertRaises(GateError):  # pending state rejected
            check_validation(dict(good, status="VALIDATED_PENDING"), sha)
        with self.assertRaises(GateError):  # missing status rejected
            check_validation({"blocker_count": 0, "review_count": 0,
                              "benchmark_sha256": sha}, sha)
        with self.assertRaises(GateError):  # bools are not valid counts
            check_validation(dict(good, blocker_count=False), sha)
        with self.assertRaises(GateError):
            check_validation(dict(good, review_count=True), sha)
        with self.assertRaises(GateError):
            check_validation(dict(good, blocker_count=1), sha)
        with self.assertRaises(GateError):
            check_validation(dict(good, review_count=2), sha)
        with self.assertRaises(GateError):
            check_validation(dict(good, benchmark_sha256="00" * 32), sha)
        alt = dict(good, final_benchmark_sha="AB" * 32)
        del alt["benchmark_sha256"]
        check_validation(alt, sha)  # alias key + case-insensitive hex
        self.assertTrue(str(build_parser().get_default("validation_report"))
                        .endswith("strict_validation_120.json"))

    def test_selection_never_bypasses_counts(self):
        bench = syn_benchmark()
        man = syn_manifest()
        _, cases = validate_benchmark(bench)
        cfgs = validate_manifest(man)
        plan = select_plan(cases, cfgs, ["SYN-CFG-00", "SYN-CFG-01"],
                           ["SYN-E000", "SYN-E001", "SYN-C100"])
        self.assertEqual(len(plan), 2 * 3)
        with self.assertRaises(GateError):
            select_plan(cases, cfgs, ["NOPE"], None)
        with self.assertRaises(GateError):
            select_plan(cases, cfgs, None, ["NOPE"])

    def test_argv_executable_and_port_checks(self):
        with self.assertRaises(GateError):
            check_argv_executable(["definitely-not-an-executable-xyz-123", "x"])
        check_argv_executable([sys.executable, "-c", "pass"])
        import socket
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        busy = probe.getsockname()[1]
        try:
            with self.assertRaises(GateError):
                check_port_free(busy)  # occupied: refuse, kill nothing
        finally:
            probe.close()
        check_port_free(busy)  # free again: passes


class AuthorizationTests(unittest.TestCase):
    def test_dry_run_still_requires_flag_and_sha(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = write_tree(tmp)
            args = build_parser().parse_args(base_argv(root, sha, ("--dry-run",)))
            args.authorize_execution = False
            with self.assertRaises(AuthorizationError):
                execute(args)
            args = build_parser().parse_args(base_argv(root, "00" * 32, ("--dry-run",)))
            with self.assertRaises(AuthorizationError):
                execute(args)

    def test_dry_run_passes_gates_with_zero_side_effects(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = write_tree(tmp)
            args = build_parser().parse_args(base_argv(root, sha, ("--dry-run",)))

            def no_network():
                raise AssertionError("dry-run must not touch the network")

            def no_server(*a, **k):
                raise AssertionError("dry-run must not start servers")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = execute(args, client_factory=no_network, server_factory=no_server)
            self.assertEqual(code, runner.EXIT_OK)
            plan = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(plan["planned_rows"], 16 * 120)
            self.assertFalse((root / "out").exists())  # nothing written


class RawBeforeParseTests(unittest.TestCase):
    """Defect 1: no body parsing may precede the raw fsync; attempts are nested."""

    def test_attempts_persisted_before_any_derivation(self):
        persisted = []
        body2 = json.dumps({"choices": [{"finish_reason": "stop",
                                         "message": {"content": "hello"}}]})
        client = FakeClient([(None, "", "TimeoutError:boom"), (200, body2, None)])
        cfg = validate_manifest(syn_manifest())[3]
        case = {"id": "SYN-E001", "level": "A1", "task": "t", "student_text": "s"}
        final = run_single_case(
            client=client, api_url="http://127.0.0.1:1/x", config=cfg, case=case,
            system_prompt="sys", user_template="L:{level} T:{task} S:{student_text}",
            benchmark_sha="bb" * 32, manifest_sha="cc" * 32, max_retries=2,
            persist_attempt=persisted.append, sampler=PeakSampler(None))
        self.assertEqual([r["attempt"] for r in persisted], [1, 2])
        self.assertEqual([r["disposition"] for r in persisted], ["retry", "final"])
        self.assertEqual(persisted[0]["resume_key"], persisted[1]["resume_key"])
        for row in persisted:  # raw rows: exact records only
            self.assertLessEqual(set(row), runner.RAW_ATTEMPT_KEYS)
            self.assertNotIn("transport", row)
            self.assertNotIn("raw_response", row)
            self.assertNotIn("finish_reason", row)
        self.assertEqual(final["outcome"], "ok")
        # Derivation happens afterwards, from persisted rows only.
        parsed = derive_parsed_row(final_info=final, config=cfg,
                                   benchmark_sha="bb" * 32, manifest_sha="cc" * 32,
                                   server_pid=None, derived_seq=1)
        self.assertEqual(parsed["raw_response"], "hello")
        self.assertEqual(parsed["transport"]["attempts"], 2)
        self.assertEqual(parsed["transport"]["finish_reason"], "stop")
        self.assertEqual(parsed["derived_seq"], 1)

    def test_continued_numbering_avoids_duplicate_keys(self):
        self.assertEqual(max_attempt_for_key(Path("missing.jsonl"), "k"), 0)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jsonl"
            runner.append_jsonl_fsync(path, {"resume_key": "k", "attempt": 1})
            runner.append_jsonl_fsync(path, {"resume_key": "k", "attempt": 2})
            self.assertEqual(max_attempt_for_key(path, "k"), 2)
            self.assertEqual(max_attempt_for_key(path, "other"), 0)
            self.assertEqual(count_jsonl_lines(path), 2)


class MemorySamplerTests(unittest.TestCase):
    """Defect 3: server peak RSS during the request; runner/GPU separated."""

    def test_no_pid_gives_explicit_nulls(self):
        sampler = PeakSampler(None)
        sampler.start()
        out = sampler.stop()
        self.assertFalse(out["server_rss_sampled"])
        self.assertIsNone(out["server_peak_rss_bytes"])
        self.assertEqual(out["server_rss_note"], "no-server-pid")

    def test_peak_tracking_with_stub_psutil(self):
        import itertools
        import time
        rss_values = itertools.cycle([1000, 3000, 2000])

        class FakeMem:
            def __init__(self, rss):
                self.rss = rss

        class FakeProc:
            def memory_info(self):
                return FakeMem(next(rss_values))

            def children(self, recursive=True):
                return []

        stub = type(sys)("psutil-stub")
        stub.Process = lambda pid: FakeProc()
        old = sys.modules.get("psutil")
        sys.modules["psutil"] = stub
        try:
            sampler = PeakSampler(pid=12345, interval_seconds=0.001)
            sampler.start()
            time.sleep(0.05)
            out = sampler.stop()
        finally:
            if old is None:
                del sys.modules["psutil"]
            else:
                sys.modules["psutil"] = old
        self.assertTrue(out["server_rss_sampled"])
        self.assertEqual(out["server_peak_rss_bytes"], 3000)
        self.assertGreaterEqual(out["server_rss_samples"], 1)

    def test_gpu_report_has_explicit_unit_and_scope(self):
        self.assertEqual(parse_nvidia_smi_mib("1234\n 5678\n"), 1234 + 5678)
        report = sample_gpu()
        self.assertEqual(report["gpu_unit"], "bytes")
        self.assertIn("NOT attributable", report["gpu_scope"])
        if report["gpu_sampled"]:
            self.assertIsInstance(report["gpu_used_bytes"], int)
        else:
            self.assertIsNone(report["gpu_used_bytes"])


class ExecutionTests(unittest.TestCase):
    def run_filtered(self, tmp, extra, client, healthy=True):
        root, sha = write_tree(tmp)
        reset_tracker()
        args = build_parser().parse_args(base_argv(root, sha, extra))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = execute(args, client_factory=lambda: client,
                           server_factory=lambda argv, port, log: FakeServer(
                               argv, port, log, healthy))
        return code, root, buf.getvalue()

    def read_raw(self, root, cfg="SYN-CFG-00"):
        path = root / "out" / "raw" / cfg / "attempts.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def read_parsed(self, root, cfg="SYN-CFG-00"):
        path = root / "out" / "parsed" / cfg / "responses.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def test_run_resume_has_no_duplicates_and_hides_gold(self):
        import tempfile
        filt = ("--config", "SYN-CFG-00", "--case", "SYN-E000", "--case", "SYN-E001")
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient()
            code, root, _ = self.run_filtered(tmp, filt, client)
            self.assertEqual(code, runner.EXIT_OK)
            rows = self.read_raw(root)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len({r["resume_key"] for r in rows}), 2)
            parsed = self.read_parsed(root)
            self.assertEqual(len(parsed), 2)
            # Evaluator-shaped: one row per case with raw_response + telemetry.
            by_case = {p["case_id"]: p for p in parsed}
            self.assertEqual(set(by_case), {"SYN-E000", "SYN-E001"})
            self.assertEqual(by_case["SYN-E000"]["raw_response"], '{"is_correct": true}')
            self.assertEqual(by_case["SYN-E000"]["transport"]["outcome"], "ok")
            self.assertEqual(by_case["SYN-E000"]["model_sha256"], MODEL_SHA)
            sent = json.dumps(client.calls[0][1], ensure_ascii=False)
            self.assertIn("Synthetic sentence 0", sent)
            self.assertNotIn(CANARY, sent)
            self.assertNotIn('"gold"', sent)
            for path in list((root / "out").rglob("*.jsonl")) + [
                    root / "out" / "checkpoint.json",
                    root / "out" / "reports" / "run_summary.json"]:
                blob = path.read_text(encoding="utf-8")
                self.assertNotIn(CANARY, blob)
                self.assertNotIn("student_text", blob)
            # Second run: everything skipped, zero new HTTP calls, zero new lines.
            client2 = FakeClient()
            code2, _, _ = self.run_filtered(tmp, filt, client2)
            self.assertEqual(code2, runner.EXIT_OK)
            self.assertEqual(client2.calls, [])
            self.assertEqual(len(self.read_raw(root)), 2)
            self.assertEqual(len(self.read_parsed(root)), 2)

    def test_crash_between_raw_fsync_and_checkpoint_recovers(self):
        import tempfile
        filt = ("--config", "SYN-CFG-00", "--case", "SYN-E000")
        with tempfile.TemporaryDirectory() as tmp:
            code, root, _ = self.run_filtered(tmp, filt, FakeClient())
            self.assertEqual(code, runner.EXIT_OK)
            # Simulate the crash: drop the key from the checkpoint cache.
            cp = root / "out" / "checkpoint.json"
            data = json.loads(cp.read_text(encoding="utf-8"))
            self.assertEqual(len(data["states"]), 1)
            data["states"] = {}
            cp.write_text(json.dumps(data), encoding="utf-8")
            client2 = FakeClient()
            code2, _, _ = self.run_filtered(tmp, filt, client2)
            self.assertEqual(code2, runner.EXIT_OK)
            self.assertEqual(client2.calls, [])  # rebuilt from RAW, not re-run
            self.assertEqual(len(self.read_raw(root)), 1)

    def test_checkpoint_claim_without_raw_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = write_tree(tmp)
            cp = root / "out" / "checkpoint.json"
            cp.parent.mkdir(parents=True, exist_ok=True)
            key = resume_key(sha, MODEL_SHA, runner.sha256_file(root / "manifest.json"),
                             "SYN-CFG-00", "SYN-E000")
            cp.write_text(json.dumps({"benchmark_sha256": sha,
                                      "manifest_sha256": runner.sha256_file(
                                          root / "manifest.json"),
                                      "states": {key: {"state": "done", "outcome": "ok",
                                                       "attempts": 1}}}),
                          encoding="utf-8")
            args = build_parser().parse_args(
                base_argv(root, sha, ("--config", "SYN-CFG-00", "--case", "SYN-E000")))
            with self.assertRaises(CheckpointMismatchError):
                execute(args, client_factory=FakeClient,
                        server_factory=lambda argv, port, log: FakeServer(argv, port, log))

    def test_raw_replay_rejects_foreign_dup_and_mismatch(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = write_tree(tmp)
            msha = runner.sha256_file(root / "manifest.json")
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            cfgs = {c["config_id"]: c for c in validate_manifest(man)}
            case_ids = {f"SYN-E{i:03d}" for i in range(90)} | {f"SYN-C{i:03d}" for i in range(90, 120)}
            key = resume_key(sha, MODEL_SHA, msha, "SYN-CFG-00", "SYN-E000")
            good = {"resume_key": key, "attempt": 1, "disposition": "final",
                    "benchmark_sha256": sha, "manifest_sha256": msha,
                    "model_sha256": MODEL_SHA, "config_id": "SYN-CFG-00",
                    "case_id": "SYN-E000", "http_status": 200,
                    "response_body_exact": OK_BODY, "error": None,
                    "latency_seconds": 0.1, "recorded_utc": "t"}
            foreign = dict(good, resume_key=resume_key("ff" * 32, MODEL_SHA, msha,
                                                       "SYN-CFG-00", "SYN-E000"))
            from run_benchmark_120 import replay_raw_authority as replay
            p1 = root / "r1.jsonl"
            runner.append_jsonl_fsync(p1, foreign)
            with self.assertRaises(CheckpointMismatchError):
                replay([p1], sha, msha, cfgs, case_ids)
            p2 = root / "r2.jsonl"
            runner.append_jsonl_fsync(p2, good)
            runner.append_jsonl_fsync(p2, dict(good, attempt=1))  # dup (key, attempt)
            with self.assertRaises(CheckpointMismatchError):
                replay([p2], sha, msha, cfgs, case_ids)
            p3 = root / "r3.jsonl"
            runner.append_jsonl_fsync(p3, good)
            runner.append_jsonl_fsync(p3, dict(good, attempt=2))  # dup final
            with self.assertRaises(CheckpointMismatchError):
                replay([p3], sha, msha, cfgs, case_ids)
            drift = dict(good, model_sha256="ff" * 32)
            p4 = root / "r4.jsonl"
            runner.append_jsonl_fsync(p4, drift)
            with self.assertRaises(CheckpointMismatchError):
                replay([p4], sha, msha, cfgs, case_ids)
            extra_key = dict(good, extra_derived_field=1)
            p5 = root / "r5.jsonl"
            runner.append_jsonl_fsync(p5, extra_key)
            with self.assertRaises(CheckpointMismatchError):
                replay([p5], sha, msha, cfgs, case_ids)
            p6 = root / "r6.jsonl"
            runner.append_jsonl_fsync(p6, good)
            states = replay([p6], sha, msha, cfgs, case_ids)
            self.assertEqual(states[key]["outcome"], "ok")
            self.assertEqual(split_resume_key(key, sha, msha, cfgs, case_ids),
                             (MODEL_SHA, "SYN-CFG-00", "SYN-E000"))

    def test_one_config_at_a_time(self):
        import tempfile
        filt = ("--config", "SYN-CFG-00", "--config", "SYN-CFG-01", "--case", "SYN-E000")
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = self.run_filtered(tmp, filt, FakeClient())
            self.assertEqual(code, runner.EXIT_OK)
            self.assertEqual(FakeServer.tracker["max_live"], 1)
            self.assertEqual(len(FakeServer.tracker["starts"]), 2)

    def test_technical_retry_is_bounded(self):
        import tempfile
        filt = ("--config", "SYN-CFG-03", "--case", "SYN-E005", "--max-retries", "2")
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([(None, "", "TimeoutError:boom"),
                                 (None, "", "TimeoutError:boom"), (200, OK_BODY, None)])
            code, root, _ = self.run_filtered(tmp, filt, client)
            self.assertEqual(code, runner.EXIT_OK)
            rows = self.read_raw(root, "SYN-CFG-03")
            self.assertEqual([r["attempt"] for r in rows], [1, 2, 3])
            self.assertEqual([r["disposition"] for r in rows], ["retry", "retry", "final"])
            self.assertEqual(len(client.calls), 3)
            parsed = self.read_parsed(root, "SYN-CFG-03")
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0]["transport"]["attempts"], 3)
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([(None, "", "TimeoutError:x")] * 9)
            code, root, _ = self.run_filtered(tmp, filt, client)
            self.assertEqual(code, runner.EXIT_OK)
            rows = self.read_raw(root, "SYN-CFG-03")
            self.assertEqual(len(rows), 3)  # 1 + max_retries(2), then kept once
            self.assertEqual(len(client.calls), 3)

    def test_failed_transport_kept_once_rerun_only_with_flag(self):
        import tempfile
        filt = ("--config", "SYN-CFG-07", "--case", "SYN-E010", "--max-retries", "0")
        with tempfile.TemporaryDirectory() as tmp:
            code, root, _ = self.run_filtered(
                tmp, filt, FakeClient([(None, "", "TimeoutError:x")]))
            self.assertEqual(code, runner.EXIT_OK)
            self.assertEqual(len(self.read_raw(root, "SYN-CFG-07")), 1)
            plain = FakeClient([(200, OK_BODY, None)])
            code2, _, _ = self.run_filtered(tmp, filt, plain)
            self.assertEqual(code2, runner.EXIT_OK)
            self.assertEqual(plain.calls, [])  # kept once: no silent retry
            flagged = FakeClient([(200, OK_BODY, None)])
            code3, _, _ = self.run_filtered(tmp, filt + ("--retry-failed",), flagged)
            self.assertEqual(code3, runner.EXIT_OK)
            self.assertEqual(len(flagged.calls), 1)  # explicit manual rerun
            rows = self.read_raw(root, "SYN-CFG-07")
            self.assertEqual([r["attempt"] for r in rows], [1, 2])  # numbering continues
            parsed = self.read_parsed(root, "SYN-CFG-07")
            self.assertEqual(len(parsed), 2)  # evaluator traces both groups against RAW
            self.assertTrue(parsed[-1]["rerun"])
            self.assertEqual(parsed[0]["retry_mode"], "initial")
            self.assertEqual(parsed[-1]["retry_mode"], "retry_failed")
            self.assertEqual(parsed[-1]["retry_of_attempt"], 1)
            self.assertEqual(parsed[-1]["retry_of_outcome"], "transport_error")
            self.assertEqual(parsed[-1]["attempt_trace"], [2])
            self.assertEqual(parsed[-1]["transport"]["outcome"], "ok")
            self.assertEqual([row["retry_mode"] for row in rows],
                             ["initial", "retry_failed"])
            # Replay on a later invocation accepts the explicitly authorized
            # second final group and does not issue another request.
            again = FakeClient()
            code4, _, _ = self.run_filtered(tmp, filt, again)
            self.assertEqual(code4, runner.EXIT_OK)
            self.assertEqual(again.calls, [])

    def test_semantic_outcomes_never_retry(self):
        import tempfile
        filt = ("--config", "SYN-CFG-04", "--case", "SYN-E006")
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([(200, "this is not json {{{", None)])
            code, root, _ = self.run_filtered(tmp, filt, client)
            self.assertEqual(code, runner.EXIT_OK)
            parsed = self.read_parsed(root, "SYN-CFG-04")
            self.assertEqual(parsed[0]["transport"]["outcome"], "invalid_body")
            self.assertEqual(parsed[0]["raw_response"], "")
            self.assertEqual(len(client.calls), 1)
        with tempfile.TemporaryDirectory() as tmp:
            body = json.dumps({"choices": [{"finish_reason": "length",
                                            "message": {"content": "cut"}}]})
            client = FakeClient([(200, body, None)])
            code, root, _ = self.run_filtered(tmp, filt, client)
            self.assertEqual(code, runner.EXIT_OK)
            parsed = self.read_parsed(root, "SYN-CFG-04")
            self.assertTrue(parsed[0]["transport"]["truncated"])
            self.assertEqual(parsed[0]["raw_response"], "cut")
            self.assertEqual(len(client.calls), 1)

    def test_rate_limit_stops_immediately_without_retry(self):
        import tempfile
        filt = ("--config", "SYN-CFG-05", "--case", "SYN-E007", "--case", "SYN-E008")
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([(429, "too many requests", "HTTPError:429")])
            code, root, out = self.run_filtered(tmp, filt, client)
            self.assertEqual(code, runner.EXIT_RATE_LIMITED)
            self.assertEqual(len(client.calls), 1)  # no retry, no next case
            rows = self.read_raw(root, "SYN-CFG-05")
            self.assertEqual(len(rows), 1)
            parsed = self.read_parsed(root, "SYN-CFG-05")
            self.assertEqual(parsed[0]["transport"]["outcome"], "rate_limited")
            summary = json.loads((root / "out" / "reports" / "run_summary.json")
                                 .read_text(encoding="utf-8"))
            self.assertTrue(summary["rate_limited_stop"])
            # A new invocation resumes after the previous invocation stopped
            # at 429. The 429 itself was never retried in that run.
            client2 = FakeClient()
            code2, _, _ = self.run_filtered(tmp, filt, client2)
            self.assertEqual(code2, runner.EXIT_OK)
            self.assertEqual(len(client2.calls), 2)
            reruns = self.read_raw(root, "SYN-CFG-05")
            self.assertEqual([row["retry_mode"] for row in reruns[:2]],
                             ["initial", "rate_limit_resume"])

    def test_unhealthy_server_refuses_cases(self):
        import tempfile
        filt = ("--config", "SYN-CFG-06", "--case", "SYN-E009")
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = write_tree(tmp)
            reset_tracker()
            args = build_parser().parse_args(base_argv(root, sha, filt))
            with self.assertRaises(GateError):
                execute(args, client_factory=FakeClient,
                        server_factory=lambda argv, port, log: FakeServer(
                            argv, port, log, False))

    def test_failed_enter_cleans_up_without_foreign_kill(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "srv.log"
            calls = []

            def boom(argv, **kwargs):
                calls.append(argv)
                raise OSError("spawn failed")

            server = runner.ManagedServer(["python", "-c", "pass"], 19991,
                                          "http://127.0.0.1:19991/health", log,
                                          popen_factory=boom)
            with self.assertRaises(OSError):
                server.__enter__()
            self.assertIsNone(server.process)  # nothing leaked
            with log.open("ab"):
                pass  # log handle was closed, file reusable
            self.assertEqual(len(calls), 1)
            missing = runner.ManagedServer(["definitely-not-an-executable-xyz-123"],
                                           19992, "http://x/health", log,
                                           popen_factory=boom)
            with self.assertRaises(GateError):
                missing.__enter__()
            self.assertEqual(len(calls), 1)  # spawn never attempted


if __name__ == "__main__":
    unittest.main()
