"""Capture the normal APK's home summary on a local emulator, without model inference.

Keeps installed data and restores rotation settings. Geometry assertions are in UI16/UI17;
these screenshots also require visual review. Refuses physical devices.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parents[1]
PACKAGE = "org.kevinlima.writinglab"


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, default=APP / "artifacts/summary-fix/emulator")
    args = parser.parse_args()
    if not args.serial.startswith("emulator-") or not args.serial[9:].isdigit():
        parser.error("Only an explicit emulator-NNNN is accepted.")
    prefix = [str(Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/platform-tools/adb.exe"), "-s", args.serial]

    def run(*command: str) -> str:
        return subprocess.run([*prefix, *command], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120).stdout.strip()

    if run("shell", "getprop", "ro.kernel.qemu") != "1":
        raise RuntimeError("Target is not an Android emulator.")
    args.output.mkdir(parents=True, exist_ok=True)
    project = ET.parse(APP / "Course.Android/Course.Android.csproj").getroot()
    version = project.findtext(".//ApplicationDisplayVersion")
    apk = APP / f"artifacts/LumaEnglish-Android-android-x64-{version}.apk"
    settings = {key: run("shell", "settings", "get", "system", key) for key in ("accelerometer_rotation", "user_rotation")}
    captures = []
    try:
        print(run("install", "-r", str(apk)), flush=True)
        run("shell", "settings", "put", "system", "accelerometer_rotation", "0")
        run("shell", "am", "force-stop", PACKAGE)
        run("shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity")
        time.sleep(2)
        for rotation, label in ((0, "portrait"), (1, "landscape")):
            run("shell", "settings", "put", "system", "user_rotation", str(rotation))
            time.sleep(1)
            # Scroll the home page to the summary; the course database is not changed.
            if rotation == 0:
                run("shell", "input", "swipe", "540", "1450", "540", "1120", "1200")
            else:
                run("shell", "input", "swipe", "1600", "650", "1600", "350", "1200")
            time.sleep(1)
            pid = run("shell", "pidof", PACKAGE)
            resumed = run("shell", "dumpsys", "activity", "activities")
            if not pid or not any(PACKAGE in line and "ResumedActivity" in line for line in resumed.splitlines()):
                raise RuntimeError("App is not running in the foreground.")
            path = args.output / f"home-summary-{label}.png"
            with path.open("wb") as image:
                subprocess.run([*prefix, "exec-out", "screencap", "-p"], stdout=image, check=True, timeout=30)
            captures.append({"orientation": label, "file": path.name, "pid": pid, "foreground": True})
    finally:
        for key, value in settings.items():
            if value == "null":
                run("shell", "settings", "delete", "system", key)
            else:
                run("shell", "settings", "put", "system", key, value)
    report = {"kind": "NORMAL_APK_UI_CAPTURE_REQUIRES_VISUAL_REVIEW", "dateUtc": datetime.now(timezone.utc).isoformat(),
              "version": version, "serial": args.serial, "android": run("shell", "getprop", "ro.build.version.release"),
              "api": run("shell", "getprop", "ro.build.version.sdk"), "model_inferences": 0, "rotation_settings_restored": settings,
              "data_cleared": False, "captures": captures}
    (args.output / "capture-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
