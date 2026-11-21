"""Summarize phone model phases, including incomplete/failed GPU trials, without selecting outputs by quality.

Input is the retained verify_android_phone.py directory, with one model phase per subdirectory.
Memory figures are sampled app+worker sums; they do not include all unified GPU allocations.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import statistics


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def timestamp(value: str) -> float:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def memory(folder: Path, mode: str):
    source = folder / f"{mode}-memory.jsonl"
    states = []
    backend = None
    for line in (folder / "status.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["mode"] != mode:
            continue
        message = row["message"]
        previous = backend
        if message.startswith("Calibrando "):
            backend = "CPU" if message.startswith("Calibrando CPU:") else "Vulkan"
        elif message.startswith("Cargando CPU"):
            backend = "CPU"
        elif message.startswith("Cargando Vulkan/"):
            backend = "Vulkan"
        elif message.startswith("Consultando GPU"):
            backend = None
        if backend != previous:
            states.append((timestamp(row["utc"]), backend))
    result = {key: {"samples_with_worker": 0, "peak_pss_mib": None, "peak_rss_mib": None, "peak_swap_pss_mib": None} for key in ("CPU", "Vulkan")}
    for line in source.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if not row.get("utc"):
            continue  # New controller rows have UTC; never infer a time from copied file metadata.
        when = timestamp(row["utc"])
        eligible = [x for x in states if x[0] <= when]
        if not eligible or eligible[-1][1] is None or when - eligible[-1][0] < 2:
            continue
        processes = row["processes"]
        if not any(p.get("Name", "").startswith("libwriting") for p in processes):
            continue
        group = result[eligible[-1][1]]
        group["samples_with_worker"] += 1
        for field, label in (("Pss", "peak_pss_mib"), ("VmRSS", "peak_rss_mib"), ("SwapPss", "peak_swap_pss_mib")):
            values = [int(p[field].split()[0]) for p in processes if field in p]
            if values:
                value = sum(values) / 1024
                group[label] = max(group[label] or 0, value)
    return result


def summarize(folder: Path, document: dict):
    profile = document.get("profile") or {}
    trials = []
    for trial in profile.get("Trials", []):
        samples = trial["Samples"]
        complete = trial.get("Failure") is None and len(samples) == 3 and all(
            s.get("Failure") is None and s["FinishReason"] == "stop" and s["Tokens"] > 0 and s["Seconds"] > 0 for s in samples)
        trials.append({"placement": trial["Placement"], "failure": trial.get("Failure"), "samples": samples,
                       "complete": complete, "three_usable_outputs": complete and all(s["ParserStatus"] in ("STRICT", "RECOVERED") for s in samples),
                       "median_seconds": statistics.median(s["Seconds"] for s in samples) if complete else None})
    sessions = []
    for expected, session in zip((True, False), document.get("sessions", [])):
        attempt = session["Attempts"][0]
        output, parsed = attempt["Output"], attempt["Parsed"]
        value = parsed.get("Value") or {}
        sessions.append({"example_expected_is_correct": expected, "usable": session["Usable"], "parser": parsed["Status"],
                         "model_is_correct": value.get("IsCorrect"), "verdict_matches_example": value.get("IsCorrect") == expected,
                         "seconds": output["Seconds"], "finish_reason": output["FinishReason"], "metrics": output.get("Metrics")})
    return {"model_id": document["model_id"], "model_sha256": document["model_sha256"], "success": document.get("success"),
            "engine": document.get("engine"), "reason": profile.get("Reason"), "profile_key": profile.get("Key"),
            "profile_date_utc": profile.get("DateUtc"), "trials": trials,
            "prepare_including_calibration_seconds": document.get("prepare_including_verification_and_calibration_seconds"),
            "cached_prepare_seconds": document.get("cached_prepare_seconds"),
            "same_profile_reused": next((c["passed"] for c in document["checks"] if c["id"] == "calibration-cache-reused"), None),
            "course_examples": sessions, "sampled_memory": memory(folder, document["mode"])}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    models = []
    for folder in sorted(args.directory.iterdir()):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            doc = read(path)
            if doc.get("purpose") != "PHONE_INTEGRATION_NOT_BENCHMARK" or "model_id" not in doc or "checks" not in doc:
                continue
            complete = path.name == doc["mode"] + ".json"
            interruption = folder / "harness-interruption.json"
            retained_checkpoint = path.name == doc["mode"] + "-checkpoint.json" and not (folder / (doc["mode"] + ".json")).exists() and interruption.exists()
            if complete or retained_checkpoint:
                row = summarize(folder, doc)
                row["completed_phase_report"] = complete
                row["source_artifact"] = str(path.relative_to(args.directory))
                row["harness_interruption"] = read(interruption) if retained_checkpoint else None
                models.append(row)
    inventory = read(args.directory / "inventory/inventory.json")
    ui = read(args.directory / "ui/ui.json")
    summary = {"purpose": "PHONE_INTEGRATION_NOT_BENCHMARK", "firmware": inventory["firmware"], "api": inventory["api"],
               "device_at_inventory": inventory["device"], "ui_checks_passed": sum(c["passed"] for c in ui["checks"]),
               "ui_checks_total": len(ui["checks"]), "ui_success": ui["success"], "keyboard_opened": ui.get("keyboard_opened"),
               "models": models, "memory_notes": ["Sampled simultaneous PSS/RSS sums of app and native worker; not total unified CPU+GPU memory.",
                   "Samples in the first two seconds after a backend change are excluded; short-lived peaks can be missed.",
                   "No reliable attributable GPU allocation peak is claimed."]}
    path = args.directory / "summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "models": len(models), "ui_checks_passed": summary["ui_checks_passed"]}))


if __name__ == "__main__":
    main()
