"""Offline unit tests for the pinned Qwen preparation helpers."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).with_name("prepare_qwen_demo.py")
SPEC = importlib.util.spec_from_file_location("prepare_qwen_demo", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}


class FakeOpener:
    def __init__(self, body: bytes):
        self.body = body
        self.requests: list[urllib.request.Request] = []

    def open(self, request, timeout=60):
        self.requests.append(request)
        return FakeResponse(self.body)


class FailingOpener:
    def __init__(self, status: int):
        self.status = status
        self.request_count = 0

    def open(self, request, timeout=60):
        self.request_count += 1
        raise urllib.error.HTTPError(request.full_url, self.status, "fixture", {}, None)


class PrepareQwenDemoTests(unittest.TestCase):
    def test_script_parses_and_uses_only_pinned_text_snapshot_files(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        compile(source, str(SCRIPT_PATH), "exec")
        self.assertEqual(
            set(prepare.SOURCE_FILES),
            {
                "LICENSE",
                "chat_template.jinja",
                "config.json",
                "merges.txt",
                "model.safetensors.index.json",
                "model.safetensors-00001-of-00002.safetensors",
                "model.safetensors-00002-of-00002.safetensors",
                "preprocessor_config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "vocab.json",
            },
        )
        self.assertNotIn("README.md", prepare.SOURCE_FILES)
        self.assertEqual(prepare.MODEL_REVISION, "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a")
        self.assertEqual(set(prepare.SOURCE_WEIGHT_FILES), {
            "model.safetensors-00001-of-00002.safetensors",
            "model.safetensors-00002-of-00002.safetensors",
        })

    def test_source_weight_hashes_are_read_from_inventory(self):
        inventory = {
            "roots": [{"entries": [
                {
                    "file": filename,
                    "hf_commit": prepare.MODEL_REVISION,
                    "lfs_sha256_expected": expected,
                }
                for filename, expected in zip(prepare.SOURCE_WEIGHT_FILES, ("a" * 64, "b" * 64), strict=True)
            ]}]
        }
        self.assertEqual(
            prepare.source_hashes_from_inventory(inventory),
            dict(zip(prepare.SOURCE_WEIGHT_FILES, ("a" * 64, "b" * 64), strict=True)),
        )

    def test_existing_source_verification_uses_revision_and_hash_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_dir = Path(temporary)
            source_file = source_dir / "config.json"
            body = b'{"model_type":"fixture"}'
            source_file.write_bytes(body)
            marker = source_dir / ".cache" / "huggingface" / "download" / "config.json.metadata"
            marker.parent.mkdir(parents=True)
            marker.write_text(
                prepare.MODEL_REVISION + "\nlocal-sha256:" + hashlib.sha256(body).hexdigest() + "\n",
                encoding="utf-8",
            )

            prepare.validate_source_file(source_file, "config.json", None)
            source_file.write_bytes(b"changed")
            with self.assertRaises(prepare.PreparationError):
                prepare.validate_source_file(source_file, "config.json", None)

    def test_fake_http_download_is_pinned_and_validates_source_marker(self):
        body = b"small fixture file"
        opener = FakeOpener(body)
        with tempfile.TemporaryDirectory() as temporary, patch.object(prepare, "SAFE_OPENER", opener), patch.dict(
            "os.environ", {"HF_TOKEN": "fixture-secret"}
        ):
            source_dir = Path(temporary)
            expected_hash = hashlib.sha256(body).hexdigest()
            prepare.download_source_file(source_dir, "fixture.json", expected_hash)
            destination = source_dir / "fixture.json"
            self.assertEqual(destination.read_bytes(), body)
            self.assertEqual(len(opener.requests), 1)
            request = opener.requests[0]
            self.assertIn(prepare.MODEL_REVISION, request.full_url)
            self.assertEqual(request.get_header("Authorization"), "Bearer fixture-secret")
            prepare.validate_source_file(destination, "fixture.json", expected_hash)

    def test_rate_limit_stops_without_retry(self):
        opener = FailingOpener(429)
        with tempfile.TemporaryDirectory() as temporary, patch.object(prepare, "SAFE_OPENER", opener):
            with self.assertRaisesRegex(prepare.PreparationError, "HTTP 429.*sin reintentos"):
                prepare.download_source_file(Path(temporary), "fixture.json", None)
        self.assertEqual(opener.request_count, 1)

    def test_publish_no_replace_preserves_existing_destination_and_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "target.gguf"
            partial = root / "target.partial.gguf"
            destination.write_bytes(b"existing")
            partial.write_bytes(b"new")
            with self.assertRaises(prepare.PreparationError):
                prepare.publish_no_replace(partial, destination)
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertTrue(partial.exists())

    def test_redirect_strips_authorization_at_new_authority_and_rejects_downgrade(self):
        handler = prepare.SafeRedirectHandler()
        request = urllib.request.Request(
            "https://huggingface.co/repo/file", headers={"Authorization": "Bearer fixture-secret"}
        )
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://cdn.example/file"
        )
        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))

        with self.assertRaisesRegex(prepare.PreparationError, "HTTPS a HTTP"):
            handler.redirect_request(request, None, 302, "Found", {}, "http://cdn.example/file")

    def test_manifest_json_parser(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(json.dumps({"format_version": 1}), encoding="utf-8")
            self.assertEqual(prepare.read_json(manifest)["format_version"], 1)


if __name__ == "__main__":
    unittest.main()
