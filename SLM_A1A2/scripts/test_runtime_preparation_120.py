"""Synthetic-only tests for runtime preparation (no models, no network, no inference).

Covers: stdlib streaming GGOF reader (arrays skipped, full template SHA),
GGUFReader path on a tiny synthetic file, template-assert logic,
server-lifecycle helpers with a dummy sleeping child, port check,
benchmark-path guard, and 429-abort propagation (mocked HTTP).
"""
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
from contextlib import ExitStack

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "scripts"))
import check_readiness_120 as chk
import prepare_experiment_120 as prep


def _wstr(buf, s):
    b = s.encode("utf-8")
    buf += struct.pack("<Q", len(b)) + b


def build_synthetic_gguf(path, template):
    """Minimal GGUF: header + KV block where chat_template comes AFTER a
    string array (merges), proving the reader parses past arrays."""
    buf = bytearray(b"GGUF") + struct.pack("<IQQ", 3, 0, 4)
    _wstr(buf, "general.architecture")
    buf += struct.pack("<I", 8)
    _wstr(buf, "llama")
    _wstr(buf, "llama.context_length")
    buf += struct.pack("<I", 4) + struct.pack("<I", 4096)
    _wstr(buf, "tokenizer.ggml.merges")
    buf += struct.pack("<I", 9) + struct.pack("<IQ", 8, 3)
    for tok in ("a b", "c d", "e f"):
        _wstr(buf, tok)
    _wstr(buf, "tokenizer.chat_template")
    buf += struct.pack("<I", 8)
    _wstr(buf, template)
    with open(path, "wb") as fh:
        fh.write(bytes(buf))
    return path


TEMPLATE_A = "{%- for m in messages -%}X{{ m.content }}{%- endfor -%}"
TEMPLATE_B = "{%- for m in messages -%}Y{{ m.content }}{%- endfor -%}"


class ReaderTests(unittest.TestCase):
    def test_inventory_requires_upstream_hash_match_and_stability(self):
        row = {'file': 'synthetic.gguf', 'path': 'synthetic.gguf', 'size': 10,
               'sha256': 'a' * 64, 'size_match': True, 'sha256_match': True,
               'stable_during_hash': True}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'inventory.json')
            for key in ('size_match', 'sha256_match', 'stable_during_hash'):
                bad = {**row, key: False}
                with open(path, 'w') as stream:
                    json.dump({'roots': [{'entries': [bad]}]}, stream)
                with patch.object(prep, 'INVENTORY', path):
                    self.assertEqual(prep.load_verified_shas(), {})

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f1 = build_synthetic_gguf(os.path.join(self.tmp, "a.gguf"), TEMPLATE_A)
        self.f2 = build_synthetic_gguf(os.path.join(self.tmp, "b.gguf"), TEMPLATE_A)
        self.f3 = build_synthetic_gguf(os.path.join(self.tmp, "c.gguf"), TEMPLATE_B)

    def test_streaming_reads_template_past_array(self):
        meta = prep.gguf_meta_streaming(self.f1)
        self.assertEqual(meta["tokenizer.chat_template"], TEMPLATE_A)
        self.assertEqual(meta["llama.context_length"], 4096)

    def test_full_template_sha_matches(self):
        import hashlib
        for path in (self.f1, self.f2):
            meta = prep.gguf_meta_streaming(path)
            s = prep.summarize_metadata(meta)
            self.assertEqual(s["chat_template_sha256"],
                             hashlib.sha256(TEMPLATE_A.encode()).hexdigest())

    def test_identical_vs_different_templates(self):
        shas = [prep.summarize_metadata(prep.gguf_meta_streaming(p))["chat_template_sha256"]
                for p in (self.f1, self.f2, self.f3)]
        self.assertEqual(shas[0], shas[1])
        self.assertNotEqual(shas[0], shas[2])

    def test_ggufreader_path_tiny_file(self):
        meta, used = prep.gguf_metadata(self.f1)
        self.assertIn("gguf", used)
        self.assertEqual(meta.get("tokenizer.chat_template"), TEMPLATE_A)


class LifecycleTests(unittest.TestCase):
    def synthetic_config(self):
        return {'id': 'synthetic', 'config_id': 'synthetic-id', 'port': 48123,
                'quant': 'Q8_0', 'model_sha256': 'a' * 64,
                'gguf': {'status': 'verified'}, 'model_path': 'synthetic.gguf',
                'runtime': {'server': 'synthetic.exe'},
                'server_command': ['synthetic.exe', '-m', 'synthetic.gguf'],
                'generation': {'max_tokens': 512, 'seed': 42, 'reasoning_budget_tokens': 0, **prep.GENERATION['lfm26']}}

    def run_probe_mocked(self, tokens, layers='12/12', reasoning=''):
        with ExitStack() as stack:
            stack.enter_context(patch.object(chk.os.path, 'isfile', return_value=True))
            stack.enter_context(patch.object(chk, 'port_free', return_value=True))
            stack.enter_context(patch.object(chk, 'ram_snapshot', return_value={}))
            stack.enter_context(patch.object(chk, 'vram_snapshot', return_value=None))
            stack.enter_context(patch.object(chk, 'verify_model_file', return_value=(True, {})))
            stack.enter_context(patch.object(chk, 'start_server', return_value=(SimpleNamespace(pid=1), None)))
            stack.enter_context(patch.object(chk, 'stop_server', return_value={'exit_code': 0}))
            stack.enter_context(patch.object(chk, 'PeakMonitor', return_value=MagicMock(stop=lambda: {})))
            stack.enter_context(patch.object(chk, 'check_health_strict', return_value=('ok', 0, {})))
            stack.enter_context(patch.object(chk, 'render_native', return_value=(200, 'Rendered synthetic', None)))
            stack.enter_context(patch.object(chk, 'tokenize_rendered', return_value=tokens))
            stack.enter_context(patch.object(chk, 'read_log_tail', return_value=''))
            stack.enter_context(patch.object(chk, 'scan_offload_evidence', return_value={'cuda_lines': ['CUDA'], 'offload_lines': ['offload'], 'n_gpu_layers_reported': layers}))
            call = stack.enter_context(patch.object(chk, 'http_call', return_value=(200, {
                'choices': [{'message': {'content': 'Synthetic output', 'reasoning_content': reasoning}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 2, 'completion_tokens': 2}}, None)))
            result = chk.run_config_check(self.synthetic_config(), SimpleNamespace(load_timeout=1, request_timeout=1), tempfile.mkdtemp())
            return result, call

    def test_probe_uses_own_base_url_and_one_generation(self):
        result, call = self.run_probe_mocked(([1, 2], None))
        self.assertEqual(result['status'], chk.ST_READY)
        call.assert_called_once()
        self.assertEqual(call.call_args.args[1], 'http://127.0.0.1:48123/v1/chat/completions')
        self.assertEqual(call.call_args.args[2]['reasoning_budget_tokens'], 0)

    def test_residual_thinking_fails_readiness_without_another_request(self):
        result, call = self.run_probe_mocked(([1, 2], None), reasoning='synthetic tagged thought')
        self.assertEqual(result['status'], chk.ST_REQUEST_FAILED)
        self.assertIn('non-thinking contract', result['measured']['request_error'])
        call.assert_called_once()

    def test_failed_render_tokenization_spends_no_generation(self):
        result, call = self.run_probe_mocked((None, 'technical failure'))
        self.assertEqual(result['status'], chk.ST_TEMPLATE_FAILED)
        call.assert_not_called()

    def test_zero_gpu_layers_spends_no_generation(self):
        result, call = self.run_probe_mocked(([1, 2], None), layers='0/12')
        self.assertEqual(result['status'], chk.ST_OFFLOAD_FAILED)
        call.assert_not_called()

    def test_model_file_verification_rejects_same_size_modified_bytes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'model.gguf')
            with open(path, 'wb') as stream:
                stream.write(b'original')
            expected = hashlib.sha256(b'original').hexdigest()
            self.assertTrue(chk.verify_model_file(path, expected)[0])
            with open(path, 'wb') as stream:
                stream.write(b'modified')
            self.assertFalse(chk.verify_model_file(path, expected)[0])

    def test_server_logs_refuse_stale_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'server.log')
            with open(path, 'w') as stream:
                stream.write('CUDA offloaded 12/12 layers')
            with self.assertRaises(FileExistsError):
                chk.start_server([sys.executable, '-c', 'pass'], LAB, path)

    def test_health_429_aborts_without_retry(self):
        with patch.object(chk, 'http_call', return_value=(429, None, 'limited')) as call:
            with self.assertRaises(chk.AbortRun):
                chk.check_health_strict('http://127.0.0.1:48123', 1, SimpleNamespace(poll=lambda: None))
        call.assert_called_once()

    def test_stop_own_sleeping_child(self):
        log = os.path.join(tempfile.mkdtemp(), "x.log")
        proc, fh = chk.start_server(
            [sys.executable, "-c", "import time; time.sleep(60)"], LAB, log)
        self.assertIsNone(proc.poll())
        info = chk.stop_server(proc, fh, grace_s=10)
        self.assertIsNotNone(info["exit_code"])
        self.assertFalse(info["already_exited"])

    def test_stop_already_exited_child(self):
        log = os.path.join(tempfile.mkdtemp(), "y.log")
        proc, fh = chk.start_server(
            [sys.executable, "-c", "pass"], LAB, log)
        proc.wait(timeout=30)
        info = chk.stop_server(proc, fh)
        self.assertTrue(info["already_exited"])

    def test_port_free_high_port(self):
        self.assertTrue(chk.port_free(48123))

    def test_forbid_benchmark(self):
        with self.assertRaises(ValueError):
            chk.forbid_benchmark("benchmark_development_120_v1.json")

    def test_429_aborts_without_retry(self):
        calls = []

        def fake_http(method, url, payload=None, timeout=30):
            calls.append(url)
            return 429, None, "HTTP 429: limited"
        old = chk.http_call
        chk.http_call = fake_http
        try:
            with self.assertRaises(chk.AbortRun):
                chk.render_native("http://127.0.0.1:48123", 5)
        finally:
            chk.http_call = old
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
