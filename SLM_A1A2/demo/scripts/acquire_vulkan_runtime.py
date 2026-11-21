#!/usr/bin/env python3
"""Acquire the official llama.cpp b11457 Windows x64 Vulkan runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


REPOSITORY = "ggml-org/llama.cpp"
TAG = "b11457"
COMMIT = "5ad1c5da0ad7f6176256b823925aad19134f0263"
ASSET_NAME = "llama-b11457-bin-win-vulkan-x64.zip"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{TAG}"
USER_AGENT = "SLM_A1A2-runtime-acquisition/1.0"
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
PINNED_MANIFEST_SHA256 = "0a88187f51d3d37ce6337372740d0911bca177690073fce48f2e917382e3bec2"
PINNED_ARCHIVE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    "b11457/llama-b11457-bin-win-vulkan-x64.zip"
)
PINNED_ARCHIVE_SHA256 = "d01301582c711a69b9747b5984710d6ca99e57d95f680d3d33753cec570b4cb6"
PINNED_UPSTREAM_DIGEST = f"sha256:{PINNED_ARCHIVE_SHA256}"
PINNED_ARCHIVE_SIZE_BYTES = 33377746
PINNED_RUNTIME_FILE_COUNT = 52
PINNED_PACKAGE_RELATIVE_PATH = "tools/llama.cpp/b11457-vulkan"
PINNED_ARCHIVE_RELATIVE_PATH = f"{PINNED_PACKAGE_RELATIVE_PATH}/{ASSET_NAME}"
PINNED_SERVER_RELATIVE_PATH = f"{PINNED_PACKAGE_RELATIVE_PATH}/llama-server.exe"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_release() -> tuple[dict[str, Any], dict[str, Any]]:
    request = urllib.request.Request(
        RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.load(response)

    if release.get("tag_name") != TAG:
        raise RuntimeError(f"GitHub returned unexpected tag {release.get('tag_name')!r}")
    if release.get("target_commitish") != COMMIT:
        raise RuntimeError(
            "GitHub release does not resolve to the requested commit: "
            f"{release.get('target_commitish')!r}"
        )
    matches = [asset for asset in release.get("assets", []) if asset.get("name") == ASSET_NAME]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one release asset named {ASSET_NAME}")
    asset = matches[0]
    if not asset.get("browser_download_url", "").startswith("https://github.com/"):
        raise RuntimeError("Release asset URL is not an official GitHub URL")
    if asset.get("size", 0) <= 0 or asset["size"] > MAX_DOWNLOAD_BYTES:
        raise RuntimeError(f"Unexpected release asset size: {asset.get('size')!r}")
    return release, asset


def download_asset(url: str, path: Path, expected_size: int) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    received = 0
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response, path.open("xb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if received > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("Download exceeded the configured size limit")
            output.write(chunk)
            digest.update(chunk)
    if received != expected_size:
        raise RuntimeError(f"Downloaded {received} bytes, expected {expected_size}")
    return received, digest.hexdigest()


def safe_member_path(name: str, root: Path) -> Path:
    if not name or "\x00" in name or "\\" in name or ":" in name:
        raise RuntimeError(f"Unsafe ZIP member name: {name!r}")
    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise RuntimeError(f"Absolute ZIP member path rejected: {name!r}")
    if any(part in {"", ".", ".."} for part in name.split("/")):
        raise RuntimeError(f"Non-normal ZIP member path rejected: {name!r}")
    target = root.joinpath(*posix_path.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"ZIP member escapes extraction directory: {name!r}") from exc
    return target


def safe_extract(archive_path: Path, root: Path) -> list[dict[str, Any]]:
    """Extract regular files only, rejecting traversal, links, duplicates and overwrites."""
    root.mkdir(exist_ok=True)
    root_resolved = root.resolve()
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, Path, bool]] = []

    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            target = safe_member_path(info.filename, root)
            key = info.filename.rstrip("/").casefold()
            if key in seen:
                raise RuntimeError(f"Duplicate ZIP member rejected: {info.filename!r}")
            seen.add(key)
            if target == archive_path:
                raise RuntimeError("ZIP member would overwrite the retained release archive")
            if not target.resolve().is_relative_to(root_resolved):
                raise RuntimeError(f"ZIP member escapes extraction directory: {info.filename!r}")

            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            is_directory = info.is_dir()
            if file_type == stat.S_IFLNK:
                raise RuntimeError(f"Symbolic link in release archive rejected: {info.filename!r}")
            if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise RuntimeError(f"Special ZIP member rejected: {info.filename!r}")
            if is_directory and file_type == stat.S_IFREG:
                raise RuntimeError(f"ZIP member has conflicting file type: {info.filename!r}")
            if not is_directory and file_type == stat.S_IFDIR:
                raise RuntimeError(f"ZIP member has conflicting file type: {info.filename!r}")
            members.append((info, target, is_directory))

        for info, target, is_directory in members:
            if is_directory:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)

    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == archive_path:
            continue
        rel_path = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        if suffix == ".exe":
            kind = "executable"
        elif suffix == ".dll":
            kind = "dynamic_library"
        elif "license" in path.name.lower() or "copying" in path.name.lower():
            kind = "license"
        else:
            kind = "other"
        records.append(
            {
                "archive_member": rel_path,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "kind": kind,
            }
        )
    return records


def run_observation(executable: Path, args: list[str], cwd: Path) -> dict[str, Any]:
    command = [str(executable), *args]
    result = subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    return {
        "command": [executable.name, *args],
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def acquire(lab_root: Path) -> Path:
    package_path = Path("tools/llama.cpp/b11457-vulkan")
    manifest_path = Path("manifests/demo_vulkan_runtime_20261109.json")
    destination = lab_root / package_path
    manifest = lab_root / manifest_path
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite runtime directory: {destination}")
    if manifest.exists():
        raise FileExistsError(f"Refusing to overwrite manifest: {manifest}")

    release, asset = read_release()
    upstream_digest = asset.get("digest")
    if upstream_digest is None:
        upstream_digest_record = "NoUpstreamDigest"
        expected_sha256 = None
    elif isinstance(upstream_digest, str) and upstream_digest.startswith("sha256:"):
        expected_sha256 = upstream_digest.removeprefix("sha256:").lower()
        if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
            raise RuntimeError(f"Invalid GitHub asset digest: {upstream_digest!r}")
        upstream_digest_record = upstream_digest
    else:
        raise RuntimeError(f"Unsupported GitHub asset digest: {upstream_digest!r}")

    staging_parent = destination.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(prefix=".b11457-vulkan-staging-", dir=staging_parent))
    try:
        assert staging is not None
        archive_path = staging / ASSET_NAME
        archive_size, archive_sha256 = download_asset(
            asset["browser_download_url"], archive_path, asset["size"]
        )
        if expected_sha256 is not None and archive_sha256 != expected_sha256:
            raise RuntimeError(
                "Downloaded archive SHA-256 does not match GitHub release digest: "
                f"{archive_sha256} != {expected_sha256}"
            )

        files = safe_extract(archive_path, staging)
        server = staging / "llama-server.exe"
        if not server.is_file():
            raise RuntimeError("Release archive does not contain llama-server.exe at its root")
        if not any(item["kind"] == "executable" for item in files):
            raise RuntimeError("Release archive contains no Windows executables")
        if not any(item["kind"] == "dynamic_library" for item in files):
            raise RuntimeError("Release archive contains no DLLs")
        filenames = {Path(item["archive_member"]).name.lower() for item in files}
        if "ggml-vulkan.dll" not in filenames:
            raise RuntimeError("Release archive contains no ggml-vulkan.dll")
        cuda_files = sorted(
            item["archive_member"]
            for item in files
            if Path(item["archive_member"]).name.lower() == "ggml-cuda.dll"
            or Path(item["archive_member"]).name.lower().startswith(("cublas", "cudart"))
        )
        if cuda_files:
            raise RuntimeError(f"CUDA runtime files found in Vulkan archive: {cuda_files}")

        version = run_observation(server, ["--version"], staging)
        devices = run_observation(server, ["--list-devices"], staging)
        help_result = run_observation(server, ["--help"], staging)
        device_none = run_observation(server, ["--device", "none", "--version"], staging)
        help_text = help_result["stdout"] + help_result["stderr"]
        help_lines = help_text.splitlines()
        device_option_index = next(
            (i for i, line in enumerate(help_lines) if "--device <" in line), None
        )
        if device_option_index is None:
            raise RuntimeError("Server help does not document the --device option")
        help_excerpt = "\n".join(help_lines[device_option_index : device_option_index + 3])
        if "none = don't offload" not in " ".join(help_excerpt.split()):
            raise RuntimeError("Server help does not document --device none as no offload")

        relative_files = [
            {
                "path": (package_path / Path(item["archive_member"])).as_posix(),
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
                "kind": item["kind"],
            }
            for item in files
        ]
        extracted_bytes = sum(item["size_bytes"] for item in files)
        cpu_libraries = [
            item
            for item in relative_files
            if Path(item["path"]).name.lower().startswith("ggml-cpu-")
            and Path(item["path"]).suffix.lower() == ".dll"
        ]
        if not cpu_libraries:
            raise RuntimeError("Release archive contains no ggml-cpu backend DLLs")
        retained_archive_path = (package_path / ASSET_NAME).as_posix()
        manifest_data: dict[str, Any] = {
            "schema_version": "writing_demo.runtime_package/1.0",
            "backend": "vulkan",
            "build": TAG,
            "commit": COMMIT,
            "server_path": (package_path / "llama-server.exe").as_posix(),
            "source": {
                "repository": f"https://github.com/{REPOSITORY}",
                "release_url": release["html_url"],
                "release_api_url": RELEASE_API,
                "release_id": release["id"],
                "asset_id": asset["id"],
                "tag": TAG,
                "commit": COMMIT,
            },
            "archive": {
                "url": asset["browser_download_url"],
                "path": retained_archive_path,
                "size_bytes": archive_size,
                "sha256": archive_sha256,
                "upstream_digest": upstream_digest_record,
                "upstream_digest_verified": expected_sha256 is not None,
            },
            "files": relative_files,
            "observations": {
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "runtime_package_size_bytes": extracted_bytes + archive_size,
                "extracted_files_size_bytes": extracted_bytes,
                "extracted_file_count": len(files),
                "executables": [item for item in relative_files if item["kind"] == "executable"],
                "dynamic_libraries": [
                    item for item in relative_files if item["kind"] == "dynamic_library"
                ],
                "licenses": [item for item in relative_files if item["kind"] == "license"],
                "backend_inventory": {
                    "vulkan_dlls": [
                        item
                        for item in relative_files
                        if Path(item["path"]).name.lower() == "ggml-vulkan.dll"
                    ],
                    "cpu_backend_dll_count": len(cpu_libraries),
                    "cpu_backend_dlls": cpu_libraries,
                    "cuda_runtime_files": [],
                },
                "version_check": version,
                "list_devices_check": devices,
                "cpu_fallback": {
                    "cpu_backend_dll_count": len(cpu_libraries),
                    "cpu_backend_dlls": cpu_libraries,
                    "no_offload_option": "--device none",
                    "option_help_excerpt": help_excerpt,
                    "option_check": device_none,
                    "inference_tested": False,
                },
                "model_loaded": False,
                "inference_performed": False,
            },
        }

        if (
            version["return_code"] != 0
            or devices["return_code"] != 0
            or help_result["return_code"] != 0
            or device_none["return_code"] != 0
        ):
            raise RuntimeError(
                "Runtime CLI validation failed; outputs were captured but no package was published. "
                f"--version={version['return_code']}, --list-devices={devices['return_code']}, "
                f"--help={help_result['return_code']}, --device-none={device_none['return_code']}"
            )

        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite runtime directory: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(staging, destination)
        staging = None

        if manifest.exists():
            raise FileExistsError(f"Refusing to overwrite manifest: {manifest}")
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
        return manifest
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)


def restore_pinned(lab_root: Path) -> Path:
    """Restore the exact pinned runtime package without changing its manifest."""
    manifest_relative = Path("manifests/demo_vulkan_runtime_20261109.json")
    package_relative = Path(PINNED_PACKAGE_RELATIVE_PATH)
    manifest = lab_root / manifest_relative
    destination = lab_root / package_relative
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Refusing to overwrite runtime directory: {destination}")
    if manifest.is_symlink() or not manifest.is_file():
        raise FileNotFoundError(f"Pinned runtime manifest is missing or is a link: {manifest}")

    manifest_bytes = manifest.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != PINNED_MANIFEST_SHA256:
        raise RuntimeError(
            "Existing runtime manifest does not match the pinned SHA-256: "
            f"{manifest_sha256} != {PINNED_MANIFEST_SHA256}"
        )
    try:
        data = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Pinned runtime manifest is not valid JSON") from exc

    expected_top_level = {
        "schema_version": "writing_demo.runtime_package/1.0",
        "backend": "vulkan",
        "build": TAG,
        "commit": COMMIT,
        "server_path": PINNED_SERVER_RELATIVE_PATH,
    }
    for key, value in expected_top_level.items():
        if data.get(key) != value:
            raise RuntimeError(f"Pinned runtime manifest has an unexpected {key!r} value")

    archive = data.get("archive")
    if not isinstance(archive, dict):
        raise RuntimeError("Pinned runtime manifest has no archive metadata")
    if (
        archive.get("url") != PINNED_ARCHIVE_URL
        or archive.get("path") != PINNED_ARCHIVE_RELATIVE_PATH
        or archive.get("size_bytes") != PINNED_ARCHIVE_SIZE_BYTES
        or archive.get("sha256") != PINNED_ARCHIVE_SHA256
        or archive.get("upstream_digest") != PINNED_UPSTREAM_DIGEST
        or archive.get("upstream_digest_verified") is not True
    ):
        raise RuntimeError("Pinned runtime manifest archive metadata differs from the pinned asset")

    records = data.get("files")
    if not isinstance(records, list) or len(records) != PINNED_RUNTIME_FILE_COUNT:
        raise RuntimeError(
            f"Pinned runtime manifest must list exactly {PINNED_RUNTIME_FILE_COUNT} files"
        )

    expected_files: dict[str, tuple[int, str]] = {}
    seen_paths: set[str] = set()
    prefix = PINNED_PACKAGE_RELATIVE_PATH + "/"
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("Pinned runtime manifest contains an invalid file record")
        relative = record.get("path")
        if not isinstance(relative, str) or not relative.startswith(prefix):
            raise RuntimeError("Pinned runtime manifest contains a path outside the package")
        member = relative[len(prefix) :]
        safe_member_path(member, destination)
        key = member.casefold()
        if key in seen_paths:
            raise RuntimeError(f"Pinned runtime manifest repeats file {relative!r}")
        seen_paths.add(key)
        size_bytes = record.get("size_bytes")
        sha256 = record.get("sha256")
        if (
            not isinstance(size_bytes, int)
            or size_bytes < 0
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256.lower())
        ):
            raise RuntimeError(f"Pinned runtime manifest has invalid size or hash for {relative!r}")
        expected_files[member] = (size_bytes, sha256.lower())
    if "llama-server.exe" not in expected_files or "ggml-vulkan.dll" not in expected_files:
        raise RuntimeError("Pinned runtime manifest omits required Vulkan server files")

    staging_parent = destination.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(prefix=".b11457-vulkan-restore-", dir=staging_parent))
    try:
        assert staging is not None
        archive_path = staging / ASSET_NAME
        archive_size, archive_sha256 = download_asset(
            PINNED_ARCHIVE_URL, archive_path, PINNED_ARCHIVE_SIZE_BYTES
        )
        if archive_size != PINNED_ARCHIVE_SIZE_BYTES or archive_sha256 != PINNED_ARCHIVE_SHA256:
            raise RuntimeError("Downloaded Vulkan ZIP does not match the pinned asset SHA-256 and size")

        extracted = safe_extract(archive_path, staging)
        actual_files = {item["archive_member"]: item for item in extracted}
        if len(actual_files) != PINNED_RUNTIME_FILE_COUNT or set(actual_files) != set(expected_files):
            missing = sorted(set(expected_files) - set(actual_files))
            extra = sorted(set(actual_files) - set(expected_files))
            raise RuntimeError(
                f"Restored Vulkan ZIP file set differs from manifest; missing={missing}, extra={extra}"
            )
        for member, (expected_size, expected_hash) in expected_files.items():
            actual = actual_files[member]
            if actual["size_bytes"] != expected_size or actual["sha256"] != expected_hash:
                raise RuntimeError(f"Restored Vulkan file does not match the pinned manifest: {member}")

        if hashlib.sha256(manifest.read_bytes()).hexdigest() != PINNED_MANIFEST_SHA256:
            raise RuntimeError("Pinned runtime manifest changed during restoration")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Refusing to overwrite runtime directory: {destination}")
        os.rename(staging, destination)
        staging = None
        return manifest
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--restore-pinned",
        action="store_true",
        help="Restore the existing pinned b11457 Vulkan package without rewriting its manifest.",
    )
    parser.add_argument(
        "--lab-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="SLM_A1A2 project root (defaults to the parent of demo/).",
    )
    args = parser.parse_args()
    lab_root = args.lab_root.resolve()
    try:
        manifest = restore_pinned(lab_root) if args.restore_pinned else acquire(lab_root)
    except Exception as exc:
        print(f"acquisition failed: {exc}", file=sys.stderr)
        return 1
    if args.restore_pinned:
        print(f"pinned runtime restored; manifest unchanged: {manifest}")
    else:
        print(f"runtime ready; manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
