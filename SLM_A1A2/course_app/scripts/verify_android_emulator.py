"""Verify the real Android host; refuses physical-device serials and preserves installed data.

Build first: ./scripts/android_publish.ps1 -Runtime android-x64 -Automation
The supplied emulator must be disposable or use -read-only: the course is exercised in its own data.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import base64
import time

APP = Path(__file__).resolve().parents[1]
PACKAGE = "org.kevinlima.writinglab"


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--mode", choices=("full", "resume"), default="full")
    parser.add_argument("--output", type=Path, default=APP / "artifacts/android-1.1.0/emulator")
    args = parser.parse_args()
    if not args.serial.startswith("emulator-") or not args.serial[9:].isdigit():
        parser.error("Only an explicit local emulator-NNNN serial is accepted.")
    adb = Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/platform-tools/adb.exe"
    args.output.mkdir(parents=True, exist_ok=True)
    prefix = [str(adb), "-s", args.serial]

    def run(*command: str) -> str:
        result = subprocess.run([*prefix, *command], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if result.returncode:
            raise RuntimeError(result.stdout + "\n" + result.stderr)
        return result.stdout.strip()

    if run("get-state") != "device" or run("shell", "getprop", "ro.kernel.qemu") != "1":
        raise RuntimeError("The target did not identify as an Android emulator.")
    apk = APP / "artifacts/LumaEnglish-Android-android-x64-automation-1.1.0.apk"
    print(run("install", "-r", str(apk)), flush=True)
    run("shell", "am", "start", "-n", PACKAGE + "/.MainActivity")
    catalog = json.loads((APP.parent / "cross_demo/WritingApp.Shared/Assets/catalog.json").read_text(encoding="utf-8-sig"))
    model = next(m for m in catalog if m["Id"] == "09-lfm25-12b-q4-k-m")
    cached = subprocess.run([*prefix, "shell", "run-as", PACKAGE, "stat", "-c", "%s", "files/models/" + model["RelativePath"]], capture_output=True, text=True)
    if args.mode == "full" and cached.stdout.strip() != str(model["SizeBytes"]):
        source = APP.parent / "models" / model["RelativePath"]
        if source.stat().st_size != model["SizeBytes"]:
            raise RuntimeError("Local GGUF size differs from the pinned catalogue.")
        staging = "files/diagnostic-models"
        run("shell", "run-as", PACKAGE, "mkdir", "-p", staging)
        # Windows adb shell stdin treats Ctrl-Z as EOF. ASCII transport avoids truncation;
        # decoding is inside the private app UID and the real store still verifies SHA-256.
        process = subprocess.Popen([*prefix, "shell", "-T", "run-as", PACKAGE, "sh", "-c",
            "'base64 -d > " + staging + "/" + Path(model["RelativePath"]).name + "'"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            with source.open("rb") as input_file:
                while chunk := input_file.read(3 * 256 * 1024):
                    process.stdin.write(base64.b64encode(chunk))
            process.stdin.close()
            error = process.stderr.read()
            if process.wait(timeout=300):
                raise RuntimeError(error.decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
        staged_size = run("shell", "run-as", PACKAGE, "stat", "-c", "%s", staging + "/" + Path(model["RelativePath"]).name)
        if staged_size != str(model["SizeBytes"]):
            raise RuntimeError("The GGUF transfer was incomplete.")
        print("Pinned local GGUF staged; the application will import and verify SHA-256.", flush=True)
    run("shell", "am", "force-stop", PACKAGE)
    remote = "files/course-verification"
    # Remove only this harness's protocol/report files, never models or progress.
    run("shell", "run-as", PACKAGE, "rm", "-f", remote + "/" + args.mode + ".json", remote + "/screenshot-request.json", remote + "/screenshot-ack.txt")
    run("shell", "am", "start", "-n", PACKAGE + "/.CourseVerificationActivity", "--es", "mode", args.mode)
    deadline, last_request = time.monotonic() + 1200, 0
    while time.monotonic() < deadline:
        state = subprocess.run([*prefix, "shell", "run-as", PACKAGE, "cat", remote + "/" + args.mode + ".json"], capture_output=True, text=True)
        if state.returncode == 0:
            break
        request = subprocess.run([*prefix, "shell", "run-as", PACKAGE, "cat", remote + "/screenshot-request.json"], capture_output=True, text=True)
        if request.returncode == 0:
            message = json.loads(request.stdout)
            if message["id"] != last_request:
                name = message["name"]
                if not name.replace("-", "").isalnum():
                    raise RuntimeError("Invalid screenshot name from harness.")
                action = message.get("action", "screenshot")
                if action == "tap":
                    run("shell", "input", "tap", str(int(message["x"])), str(int(message["y"])))
                    time.sleep(0.5)
                elif action == "type-roundtrip":
                    run("shell", "input", "text", "X")
                    run("shell", "input", "keyevent", "67")
                elif action == "hide-keyboard":
                    run("shell", "input", "keyevent", "4")
                    time.sleep(0.5)
                elif action != "screenshot":
                    raise RuntimeError("Unknown harness input request.")
                capture = subprocess.run([*prefix, "exec-out", "screencap", "-p"], check=True, capture_output=True)
                if not capture.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("ADB did not return a PNG screenshot.")
                (args.output / (name + ".png")).write_bytes(capture.stdout)
                run("shell", "run-as", PACKAGE, "sh", "-c", "'printf " + str(message["id"]) + " > " + remote + "/screenshot-ack.txt'")
                last_request = message["id"]
                print("Screenshot: " + name, flush=True)
        time.sleep(0.5)
    else:
        raise TimeoutError("Android harness did not finish within 20 minutes.")
    for name in (args.mode + ".json", "history.json", "history.csv", "progress.log"):
        payload = subprocess.run([*prefix, "exec-out", "run-as", PACKAGE, "cat", remote + "/" + name], capture_output=True)
        if payload.returncode == 0:
            (args.output / name).write_bytes(payload.stdout)
    report = json.loads((args.output / (args.mode + ".json")).read_text(encoding="utf-8"))
    print(json.dumps({"mode": args.mode, "success": report.get("success"), "checks": len(report.get("checks", [])), "exception": report.get("exception")}, ensure_ascii=False), flush=True)
    if report.get("success") is not True:
        raise RuntimeError("Android verification did not pass.")


if __name__ == "__main__":
    main()
