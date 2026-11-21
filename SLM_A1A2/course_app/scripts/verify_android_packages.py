"""Verify delivery APK identity, signature, ABIs, native runtime and 16 KiB alignment."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parents[1]
SDK = Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/build-tools/37.0.0"
NATIVE = APP.parent / "cross_demo/native/artifacts/b12359-adaptive-v1"
ENV = dict(os.environ, JAVA_HOME=r"C:\Program Files\Android\Android Studio\jbr")


def call(*command: str | Path) -> str:
    result = subprocess.run([str(x) for x in command], env=ENV, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout


def main() -> None:
    project = ET.parse(APP / 'Course.Android/Course.Android.csproj').getroot()
    version = project.findtext('.//ApplicationDisplayVersion')
    version_code = int(project.findtext('.//ApplicationVersion'))
    original = APP.parent / "cross_demo/artifacts/android-0.1.6/org.kevinlima.writinglab-Signed.apk"
    certificate = re.search(r"certificate SHA-256 digest: (\w+)", call(SDK / "apksigner.bat", "verify", "--print-certs", original))[1]
    packages = []
    for rid, abi, source in (("android-arm64", "arm64-v8a", "android-arm64-v8a"), ("android-x64", "x86_64", "android-x86_64")):
        apk = APP / f"artifacts/LumaEnglish-Android-{rid}-{version}.apk"
        signature = call(SDK / "apksigner.bat", "verify", "--verbose", "--print-certs", apk)
        assert re.search(r"certificate SHA-256 digest: (\w+)", signature)[1] == certificate, "Update signing identity changed."
        badging = call(SDK / "aapt2.exe", "dump", "badging", apk)
        assert "name='org.kevinlima.writinglab'" in badging and f"versionCode='{version_code}'" in badging and f"versionName='{version}'" in badging
        assert "application-label:'Luma English'" in badging and "minSdkVersion:'26'" in badging
        manifest = call(SDK / "aapt2.exe", "dump", "xmltree", apk, "--file", "AndroidManifest.xml")
        assert "CourseVerificationActivity" not in manifest and "CourseInstrumentation" not in manifest and "RuntimeDiagnosticsActivity" not in manifest
        assert "PhoneVerificationActivity" not in manifest
        assert not any("android:debuggable" in line and "0xffffffff" in line for line in manifest.splitlines())
        alignment = call(SDK / "zipalign.exe", "-c", "-P", "16", "4", apk)
        with zipfile.ZipFile(apk) as archive:
            names = archive.namelist()
            assert {n.split('/')[1] for n in names if n.startswith("lib/")} == {abi}
            elf_count = 0
            for name in names:
                if not name.startswith("lib/") or not name.endswith(".so"):
                    continue
                elf = archive.read(name)
                assert elf[:5] == b"\x7fELF\x02", name
                phoff = struct.unpack_from("<Q", elf, 32)[0]
                stride, count = struct.unpack_from("<HH", elf, 54)
                for index in range(count):
                    offset = phoff + index * stride
                    if struct.unpack_from("<I", elf, offset)[0] == 1:
                        assert struct.unpack_from("<Q", elf, offset + 48)[0] >= 16384, name + " has a non-16-KiB PT_LOAD segment"
                elf_count += 1
            runtime = []
            for path in sorted((NATIVE / source).glob("*.so")):
                embedded = archive.read(f"lib/{abi}/{path.name}")
                digest = hashlib.sha256(embedded).hexdigest()
                assert digest == hashlib.sha256(path.read_bytes()).hexdigest(), "Native binary changed while packaging: " + path.name
                runtime.append({"name": path.name, "sha256": digest})
            assert "assets/third-party/course-notices.md" in names
            if abi == "arm64-v8a":
                assert "assets/turnip-runtime.zip" in names and any(n.startswith("assets/third-party/") and n != "assets/third-party/course-notices.md" for n in names)
            else:
                assert "assets/turnip-runtime.zip" not in names
        packages.append({"file": apk.name, "bytes": apk.stat().st_size, "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
            "abi": abi, "version": version, "version_code": version_code, "min_sdk": 26, "target_sdk": 37,
            "certificate_sha256": certificate, "same_certificate_as_0_1_6": True, "diagnostics_excluded": True,
            "debuggable": False, "zipalign_16k": True, "elf_16k_libraries": elf_count, "native_runtime": runtime})
    output = APP / f"artifacts/android-{version}/packages.json"
    output.write_text(json.dumps({"packages": packages}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": len(packages), "report": str(output)}))


if __name__ == "__main__":
    main()
