import hashlib
import importlib.util
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("acquire_vulkan_runtime.py")
SPEC = importlib.util.spec_from_file_location("acquire_vulkan_runtime", SCRIPT)
runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime)


class SafeExtractTests(unittest.TestCase):
    def test_extracts_regular_release_fixture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            archive_path = temp / "fixture.zip"
            extract_path = temp / "runtime"
            payloads = {
                "llama-server.exe": b"server-fixture",
                "ggml-vulkan.dll": b"vulkan-fixture",
                "LICENSE.txt": b"license-fixture",
                "nested/readme.txt": b"readme-fixture",
            }
            with zipfile.ZipFile(archive_path, "w") as archive:
                for name, content in payloads.items():
                    archive.writestr(name, content)

            records = runtime.safe_extract(archive_path, extract_path)

            self.assertEqual(
                {record["archive_member"] for record in records}, set(payloads)
            )
            self.assertEqual(
                (extract_path / "llama-server.exe").read_bytes(), payloads["llama-server.exe"]
            )
            self.assertEqual(
                next(record for record in records if record["archive_member"] == "LICENSE.txt")[
                    "kind"
                ],
                "license",
            )
            for record in records:
                content = payloads[record["archive_member"]]
                self.assertEqual(record["size_bytes"], len(content))
                self.assertEqual(record["sha256"], hashlib.sha256(content).hexdigest())

    def test_rejects_traversal_and_windows_paths(self):
        unsafe_names = ["../outside.dll", "C:/outside.dll", "..\\outside.dll"]
        for name in unsafe_names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                archive_path = temp / "fixture.zip"
                extract_path = temp / "runtime"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(name, b"unsafe")

                with self.assertRaises(RuntimeError):
                    runtime.safe_extract(archive_path, extract_path)

                self.assertTrue(extract_path.is_dir())
                self.assertEqual(list(extract_path.iterdir()), [])
                self.assertFalse((temp / "outside.dll").exists())

    def test_rejects_symlink_member(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            archive_path = temp / "fixture.zip"
            extract_path = temp / "runtime"
            link = zipfile.ZipInfo("link.dll")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(link, "target.dll")

            with self.assertRaisesRegex(RuntimeError, "Symbolic link"):
                runtime.safe_extract(archive_path, extract_path)

            self.assertFalse(any(extract_path.iterdir()))

    def test_refuses_to_overwrite_existing_extracted_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            archive_path = temp / "fixture.zip"
            extract_path = temp / "runtime"
            extract_path.mkdir()
            existing = extract_path / "llama-server.exe"
            existing.write_bytes(b"keep-existing")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("llama-server.exe", b"replacement")

            with self.assertRaises(FileExistsError):
                runtime.safe_extract(archive_path, extract_path)

            self.assertEqual(existing.read_bytes(), b"keep-existing")


class AcquisitionGuardTests(unittest.TestCase):
    def test_digest_mismatch_aborts_without_network_or_publishing(self):
        payload = b"not-the-upstream-digest"
        release = {
            "id": 1,
            "html_url": "https://github.com/ggml-org/llama.cpp/releases/tag/b11457",
        }
        asset = {
            "id": 2,
            "size": len(payload),
            "digest": "sha256:" + ("0" * 64),
            "browser_download_url": "https://github.com/ggml-org/llama.cpp/releases/download/b11457/fixture.zip",
        }

        def fake_download(_url, path, _expected_size):
            path.write_bytes(payload)
            return len(payload), hashlib.sha256(payload).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                mock.patch.object(runtime, "read_release", return_value=(release, asset)) as read,
                mock.patch.object(runtime, "download_asset", side_effect=fake_download) as download,
            ):
                with self.assertRaisesRegex(RuntimeError, "does not match GitHub release digest"):
                    runtime.acquire(root)

            read.assert_called_once_with()
            download.assert_called_once()
            self.assertFalse((root / "tools/llama.cpp/b11457-vulkan").exists())
            self.assertFalse((root / "manifests/demo_vulkan_runtime_20261109.json").exists())
            self.assertEqual(list((root / "tools/llama.cpp").iterdir()), [])

    def test_existing_destination_and_manifest_are_never_overwritten(self):
        for existing_kind in ("destination", "manifest"):
            with self.subTest(existing_kind=existing_kind), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                if existing_kind == "destination":
                    target = root / "tools/llama.cpp/b11457-vulkan"
                    target.mkdir(parents=True)
                    sentinel = target / "keep.txt"
                    sentinel.write_text("keep", encoding="utf-8")
                else:
                    target = root / "manifests/demo_vulkan_runtime_20261109.json"
                    target.parent.mkdir(parents=True)
                    target.write_text('{"keep": true}\n', encoding="utf-8")
                    sentinel = target
                original = sentinel.read_bytes()

                with mock.patch.object(runtime, "read_release") as read:
                    with self.assertRaises(FileExistsError):
                        runtime.acquire(root)

                read.assert_not_called()
                self.assertEqual(sentinel.read_bytes(), original)


class PinnedRestoreTests(unittest.TestCase):
    def create_fixture(self, root: Path, corrupt_manifest_hash: bool = False):
        package = runtime.PINNED_PACKAGE_RELATIVE_PATH
        payloads = {
            "llama-server.exe": b"server fixture",
            "ggml-vulkan.dll": b"vulkan fixture",
            "ggml-cpu-x64.dll": b"cpu fixture",
            "LICENSE-LLVM-OpenMP": b"license fixture",
        }
        for index in range(runtime.PINNED_RUNTIME_FILE_COUNT - len(payloads)):
            payloads[f"extra-{index:02d}.dat"] = f"fixture-{index}".encode("ascii")

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive_file:
            for name, content in payloads.items():
                archive_file.writestr(name, content)
        archive_bytes = archive_buffer.getvalue()
        archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        records = []
        for name, content in payloads.items():
            file_hash = hashlib.sha256(content).hexdigest()
            if corrupt_manifest_hash and name == "ggml-vulkan.dll":
                file_hash = "0" * 64
            records.append(
                {
                    "path": f"{package}/{name}",
                    "size_bytes": len(content),
                    "sha256": file_hash,
                    "kind": "other",
                }
            )

        manifest_data = {
            "schema_version": "writing_demo.runtime_package/1.0",
            "backend": "vulkan",
            "build": runtime.TAG,
            "commit": runtime.COMMIT,
            "server_path": runtime.PINNED_SERVER_RELATIVE_PATH,
            "source": {
                "repository": "https://github.com/ggml-org/llama.cpp",
                "release_url": "https://github.com/ggml-org/llama.cpp/releases/tag/b11457",
                "release_api_url": runtime.RELEASE_API,
                "release_id": 1,
                "asset_id": 2,
                "tag": runtime.TAG,
                "commit": runtime.COMMIT,
            },
            "archive": {
                "url": runtime.PINNED_ARCHIVE_URL,
                "path": runtime.PINNED_ARCHIVE_RELATIVE_PATH,
                "size_bytes": len(archive_bytes),
                "sha256": archive_sha256,
                "upstream_digest": f"sha256:{archive_sha256}",
                "upstream_digest_verified": True,
            },
            "files": records,
        }
        manifest_bytes = (json.dumps(manifest_data, indent=2) + "\n").encode("utf-8")
        manifest_path = root / "manifests/demo_vulkan_runtime_20261109.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_bytes(manifest_bytes)
        return manifest_path, manifest_bytes, archive_bytes, archive_sha256

    def patched_pins(self, manifest_bytes: bytes, archive_bytes: bytes, archive_sha256: str):
        return mock.patch.multiple(
            runtime,
            PINNED_MANIFEST_SHA256=hashlib.sha256(manifest_bytes).hexdigest(),
            PINNED_ARCHIVE_SHA256=archive_sha256,
            PINNED_UPSTREAM_DIGEST=f"sha256:{archive_sha256}",
            PINNED_ARCHIVE_SIZE_BYTES=len(archive_bytes),
        )

    def test_restores_all_pinned_fixture_files_without_rewriting_manifest(self):
        payloads = {
            "llama-server.exe": b"server fixture",
            "ggml-vulkan.dll": b"vulkan fixture",
            "ggml-cpu-x64.dll": b"cpu fixture",
            "LICENSE-LLVM-OpenMP": b"license fixture",
        }
        for index in range(runtime.PINNED_RUNTIME_FILE_COUNT - len(payloads)):
            payloads[f"extra-{index:02d}.dat"] = f"fixture-{index}".encode("ascii")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path, manifest_bytes, archive_bytes, archive_sha256 = self.create_fixture(root)

            def fake_download(url, path, expected_size):
                self.assertEqual(url, runtime.PINNED_ARCHIVE_URL)
                self.assertEqual(expected_size, len(archive_bytes))
                path.write_bytes(archive_bytes)
                return len(archive_bytes), archive_sha256

            with (
                self.patched_pins(manifest_bytes, archive_bytes, archive_sha256),
                mock.patch.object(runtime, "download_asset", side_effect=fake_download) as download,
                mock.patch.object(runtime, "read_release") as read_release,
            ):
                returned_manifest = runtime.restore_pinned(root)

            package = root / runtime.PINNED_PACKAGE_RELATIVE_PATH
            download.assert_called_once()
            read_release.assert_not_called()
            self.assertEqual(returned_manifest, manifest_path)
            self.assertEqual(manifest_path.read_bytes(), manifest_bytes)
            self.assertEqual((package / runtime.ASSET_NAME).read_bytes(), archive_bytes)
            for name, content in payloads.items():
                self.assertEqual((package / name).read_bytes(), content)
            self.assertEqual(len([path for path in package.iterdir() if path.is_file()]), 53)

    def test_rejects_file_hash_mismatch_before_publishing_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _manifest_path, manifest_bytes, archive_bytes, archive_sha256 = self.create_fixture(
                root, corrupt_manifest_hash=True
            )

            def fake_download(_url, path, _expected_size):
                path.write_bytes(archive_bytes)
                return len(archive_bytes), archive_sha256

            with (
                self.patched_pins(manifest_bytes, archive_bytes, archive_sha256),
                mock.patch.object(runtime, "download_asset", side_effect=fake_download),
            ):
                with self.assertRaisesRegex(RuntimeError, "does not match the pinned manifest"):
                    runtime.restore_pinned(root)

            self.assertFalse((root / runtime.PINNED_PACKAGE_RELATIVE_PATH).exists())
            self.assertTrue((root / "manifests/demo_vulkan_runtime_20261109.json").is_file())

    def test_manifest_pin_mismatch_refuses_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _manifest_path, manifest_bytes, archive_bytes, archive_sha256 = self.create_fixture(root)
            with (
                self.patched_pins(manifest_bytes, archive_bytes, archive_sha256),
                mock.patch.object(runtime, "PINNED_MANIFEST_SHA256", "0" * 64),
                mock.patch.object(runtime, "download_asset") as download,
            ):
                with self.assertRaisesRegex(RuntimeError, "does not match the pinned SHA-256"):
                    runtime.restore_pinned(root)

            download.assert_not_called()

    def test_existing_runtime_folder_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _manifest_path, manifest_bytes, archive_bytes, archive_sha256 = self.create_fixture(root)
            package = root / runtime.PINNED_PACKAGE_RELATIVE_PATH
            package.mkdir(parents=True)
            sentinel = package / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with (
                self.patched_pins(manifest_bytes, archive_bytes, archive_sha256),
                mock.patch.object(runtime, "download_asset") as download,
            ):
                with self.assertRaises(FileExistsError):
                    runtime.restore_pinned(root)

            download.assert_not_called()
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
