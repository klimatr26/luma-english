"""Collect small audit receipts; never execute or rescore a benchmark."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
LAB = APP.parent
REPO = LAB.parent
OUT = APP / "docs/verification"
VERIFY = APP / "artifacts/verification"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for source, target in [
        (VERIFY / "core-tests.json", "core-tests.json"),
        (VERIFY / "ui-tests.json", "ui-tests.json"),
        (VERIFY / "course-examples-final-20261119/report.json", "course-examples.json"),
        (VERIFY / "qwen2-final-20261119/report.json", "qwen2-readiness.json"),
    ]:
        data = json.loads(source.read_text(encoding="utf-8"))
        if "checks" in data and data["passed"] != data["total"]:
            raise RuntimeError("Unresolved automated test failure: " + str(source))
        if target == "course-examples.json" and len(data["Cases"]) != 24:
            raise RuntimeError("Incomplete course integration matrix.")
        shutil.copyfile(source, OUT / target)
    for name, expected in [("reused-core-tests.txt", "39/39 checks passed."), ("reused-ui-tests.txt", "4/4 UI state checks passed.")]:
        source = VERIFY / name
        if expected not in source.read_text(encoding="utf-8-sig"):
            raise RuntimeError("Incomplete reused-component test run.")
        shutil.copyfile(source, OUT / name)

    frozen = json.loads((LAB / "manifests/finalists_200_20261117.json").read_text(encoding="utf-8"))["source_bindings"]
    frozen_results = [{"path": str(Path(r["path"]).relative_to(LAB)).replace("\\", "/"), "sha256": r["sha256"],
                       "unchanged": digest(r["path"]) == r["sha256"]} for r in frozen]
    baseline = json.loads((LAB / "benchmark_40_archive/phase1_baseline_hashes.json").read_text(encoding="utf-8"))["files"]
    phase1 = [{"path": r["path"], "sha256": r["sha256"], "unchanged": digest(LAB / r["path"]) == r["sha256"]} for r in baseline]
    git_blobs = []
    for record in baseline:
        result = subprocess.run(["git", "show", "f2eb39e:SLM_A1A2/" + record["path"].replace("\\", "/")], cwd=REPO, capture_output=True)
        if result.returncode == 0:
            git_blobs.append({"path": record["path"], "unchanged": hashlib.sha256(result.stdout).hexdigest() == record["sha256"]})
    integrity = {"date_utc": datetime.now(timezone.utc).isoformat(), "phase1": phase1, "initial_git_blobs": git_blobs, "frozen_200_bindings": frozen_results}
    if not all(r["unchanged"] for records in (phase1, git_blobs, frozen_results) for r in records):
        raise RuntimeError("Protected source or result changed.")
    save("protected-integrity.json", integrity)

    pins = json.loads((APP / "Course.Core/Assets/extra-models.json").read_text(encoding="utf-8"))
    revision = "f6d5376be1edb4d416d56da11e5397a961aca8ae"
    api = f"https://huggingface.co/api/models/unsloth/Qwen3.5-2B-GGUF/revision/{revision}?blobs=true"
    with urllib.request.urlopen(api, timeout=60) as response:
        upstream = json.load(response)
    receipts = []
    for pin in pins:
        name = pin["RelativePath"].split("/")[-1]
        remote = next(f for f in upstream["siblings"] if f["rfilename"] == name)
        if remote["size"] != pin["SizeBytes"] or remote["lfs"]["sha256"] != pin["Sha256"]:
            raise RuntimeError("Upstream pin mismatch: " + name)
        cache = Path.home() / "AppData/Local/WritingApp/Models" / pin["RelativePath"]
        verified = cache.is_file() and cache.stat().st_size == pin["SizeBytes"] and digest(cache) == pin["Sha256"]
        receipts.append({"id": pin["Id"], "filename": name, "bytes": pin["SizeBytes"], "sha256": pin["Sha256"], "metadata_verified": True, "local_bytes_verified": verified})
    save("qwen2-provenance.json", {"date_utc": datetime.now(timezone.utc).isoformat(), "primary_api_url": api,
         "revision": upstream["sha"], "license": upstream["cardData"]["license"], "benchmark_equivalence_claimed": False, "models": receipts})

    publish = APP / "artifacts/windows-1.0.0"
    archive = APP / "artifacts/WritingLocal-Windows-x64-1.0.0.zip"
    source_files = list(APP.glob("Course.*/*.cs")) + list(APP.glob("Course.*/*.axaml")) + list(APP.glob("Course.*/Assets/*.json"))
    gui_db = APP / "artifacts/ui-validation/course.db"
    gui = None
    if gui_db.exists():
        with sqlite3.connect(f"file:{gui_db.as_posix()}?mode=ro", uri=True) as connection:
            gui = [{"activity_id": r[0], "status": r[1], "session": json.loads(r[2]) if r[2] else None}
                   for r in connection.execute("SELECT activity_id,status,session_json FROM writing_sessions ORDER BY started")]
    gui_export = APP / "artifacts/ui-validation/export-session-20261119.json"
    exported_session = json.loads(gui_export.read_text(encoding="utf-8")) if gui_export.exists() else None
    if exported_session is not None:
        if exported_session["Purpose"] != "COURSE_PRACTICE_NOT_BENCHMARK" or not exported_session["Usable"]:
            raise RuntimeError("Unexpected GUI export.")
        save("published-gui-session.json", exported_session)
        profiles = []
        profile_root = Path.home() / "AppData/Local/WritingApp/adaptive-profiles"
        for path in profile_root.glob("*.json"):
            if path.name.startswith("trace-"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("ModelId") == exported_session["Model"]["Id"] and data.get("Context") == 2048 and "Trials" in data:
                profiles.append(data)
        if profiles:
            profile = max(profiles, key=lambda p: p["DateUtc"])
            save("published-gui-calibration.json", profile)
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    save("delivery.json", {"date_utc": datetime.now(timezone.utc).isoformat(), "source_commit_at_collection": source_commit,
        "sdk": "11.0.100", "avalonia": "12.1.5", "target": "Windows x64 self-contained, JIT, no trimming",
        "zip": {"path": str(archive.relative_to(APP)), "bytes": archive.stat().st_size, "sha256": digest(archive)},
        "package_files": json.loads((publish / "files.sha256.json").read_text(encoding="utf-8-sig")),
        "sources_sha256": {str(p.relative_to(APP)).replace("\\", "/"): digest(p) for p in sorted(source_files)},
        "gui_sessions": gui,
        "gui_export": {"path": str(gui_export.relative_to(APP)), "sha256": digest(gui_export)} if gui_export.exists() else None,
        "retained_local_runs": [str(p.relative_to(APP)).replace("\\", "/") for p in VERIFY.glob("*/report.json")],
        "note": "Integration reports bind their own actual assemblies. Later changes to recommendation policy and restore graphs do not alter writing prompts, sampling, parser, GGUF or native generation. Separate published-GUI evidence is recorded when present."})
    print(f"Collected receipts: {len(phase1)} protected artifacts, {len(git_blobs)} original blobs, {len(frozen_results)} frozen bindings; output {OUT}.")


if __name__ == "__main__":
    main()
