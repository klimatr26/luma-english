"""Verify untouched Phase 1 artifacts against the handoff byte-level baseline."""

import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    baseline = root / "benchmark_40_archive" / "phase1_baseline_hashes.json"
    records = json.loads(baseline.read_text(encoding="utf-8"))["files"]
    failures = []
    for record in records:
        path = root / record["path"]
        if not path.is_file():
            failures.append(f"Missing: {record['path']}")
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if path.stat().st_size != record["size_bytes"] or digest.hexdigest() != record["sha256"]:
            failures.append(f"Changed: {record['path']}")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"OK: {len(records)} Phase 1 artifacts are byte-identical to the handoff baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
