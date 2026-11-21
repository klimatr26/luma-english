"""Model asset inventory for Phase 2 (development_120), metadata-only by default.

Walks the workspace model roots (SLM_A1A2/models and D:/SLM_A1A2_models),
records file sizes, and cross-checks them against the pinned Hugging Face
provenance captured at download time:
  - <asset>/.cache/huggingface/download/*.metadata  (commit, etag, timestamp)
  - <asset>/.cache/huggingface/trees/<commit>.json (per-file lfs_size/lfs_sha256)

Full SHA-256 hashing is opt-in (--sha) and is LEFT FOR THE MAIN AGENT to run
after review. Size matches against lfs_size are already a strong signal but
are NOT a substitute for the SHA-256 check.

Usage (from SLM_A1A2/):
  .venv/Scripts/python.exe scripts/write_model_inventory.py [--sha] [--strict]
                            [--out manifests/model_inventory_120.json]

Read-only: never modifies model files. Does not download, convert or infer.
Stdlib only.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_ROOTS = [
    os.path.join(WORKSPACE_ROOT, "models"),
    r"D:\SLM_A1A2_models",
]
TRACKED_EXT = (".gguf", ".safetensors")


def read_metadata_blob(path):
    """HF download *.metadata blob: line1=commit, line2=etag/lfs-sha, line3=ts."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [ln.strip() for ln in fh.read().splitlines()]
    except OSError:
        return {}
    out = {}
    if len(lines) > 0 and lines[0]:
        out["commit"] = lines[0]
    if len(lines) > 1 and lines[1]:
        out["etag"] = lines[1]
    if len(lines) > 2 and lines[2]:
        out["timestamp"] = lines[2]
    return out


def load_trees(cache_dir):
    """Return {commit: {filename: {size, lfs_sha256}}} from trees/*.json."""
    trees_dir = os.path.join(cache_dir, "trees")
    result = {}
    if not os.path.isdir(trees_dir):
        return result
    for name in os.listdir(trees_dir):
        if not name.endswith(".json"):
            continue
        commit = name[:-5]
        try:
            with open(os.path.join(trees_dir, name), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        files = {}
        for fname, meta in (data.get("files") or {}).items():
            if not isinstance(meta, dict):
                continue
            files[fname] = {
                "expected_size": meta.get("lfs_size", meta.get("size")),
                "lfs_sha256": meta.get("lfs_sha256"),
            }
        result[commit] = files
    return result


def sha256_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def inventory_root(root, do_sha):
    entries = []
    unverified = []
    conversion_record = os.path.join(WORKSPACE_ROOT, "manifests", "qwen_conversion_record_120.json")
    completed_conversions = {}
    if os.path.isfile(conversion_record):
        with open(conversion_record, encoding="utf-8-sig") as stream:
            record = json.load(stream)
        completed_conversions = {os.path.basename(e["file"]): e for e in record.get("outputs", [])}
    if not os.path.isdir(root):
        return {"root": root, "present": False, "entries": entries}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".venv"]
        cache = os.path.join(dirpath, ".cache", "huggingface")
        blobs = {}
        trees = {}
        if os.path.isdir(os.path.join(cache, "download")):
            for name in os.listdir(os.path.join(cache, "download")):
                if name.endswith(".metadata"):
                    blobs[name[: -len(".metadata")]] = read_metadata_blob(
                        os.path.join(cache, "download", name)
                    )
            trees = load_trees(cache)
        for name in sorted(filenames):
            if not name.endswith(TRACKED_EXT):
                continue
            full = os.path.join(dirpath, name)
            if os.path.basename(dirpath).lower() == "qwen_converted":
                completed = completed_conversions.get(name)
                if not completed or os.path.getsize(full) != completed.get("bytes"):
                    unverified.append({"path": full, "status": "conversion_record_missing_or_size_disagrees; not a verified model"})
                    continue
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            blob = blobs.get(name, {})
            commit = blob.get("commit")
            expected = {}
            if commit and commit in trees:
                expected = trees[commit].get(name, {})
            exp_size = expected.get("expected_size")
            before = os.stat(full)
            actual_sha = sha256_of(full) if do_sha else None
            after = os.stat(full)
            stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
            expected_sha = expected.get("lfs_sha256") or (
                blob.get("etag") if len(blob.get("etag", "")) == 64 else None
            )
            if os.path.basename(dirpath).lower() == "qwen_converted":
                expected_sha = completed_conversions[name].get("sha256")
                exp_size = completed_conversions[name].get("bytes")
            entry = {
                "path": full,
                "file": name,
                "size": size,
                "expected_size": exp_size,
                "size_match": (exp_size == size) if exp_size is not None else None,
                "hf_commit": commit,
                "hf_etag": blob.get("etag"),
                "lfs_sha256_expected": expected_sha,
                "sha256": actual_sha,
                "sha256_match": (actual_sha == expected_sha) if actual_sha and expected_sha else None,
                "stable_during_hash": stable if do_sha else None,
                "mtime_ns": after.st_mtime_ns,
            }
            entries.append(entry)
    return {"root": root, "present": True, "entries": entries, "unverified_conversions": unverified}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", action="store_true",
                    help="Compute full SHA-256 of every tracked file (slow, ~30 GB).")
    ap.add_argument("--strict", action="store_true",
                    help="Fail on mismatches or missing reference/verification evidence; --sha also requires matching stable hashes.")
    ap.add_argument("--out", default=os.path.join(WORKSPACE_ROOT, "manifests",
                                                  "model_inventory_120.json"))
    args = ap.parse_args()

    unique_roots = []
    aliases = []
    for root in MODEL_ROOTS:
        match = next((r for r in unique_roots if os.path.exists(root) and os.path.exists(r) and os.path.samefile(root, r)), None)
        if match:
            aliases.append({"path": root, "same_asset_root_as": match})
        else:
            unique_roots.append(root)
    report = {"roots": [inventory_root(r, args.sha) for r in unique_roots], "aliases": aliases, "generated_utc": datetime.now(timezone.utc).isoformat()}
    mismatches = [e for r in report["roots"] for e in r["entries"]
                  if e["size_match"] is False or e["sha256_match"] is False or e.get("stable_during_hash") is False]
    report["mismatches"] = [e["path"] for e in mismatches]
    unverified = [e['path'] for r in report['roots'] for e in r['entries']
                  if e.get('size_match') is not True
                  or (args.sha and (e.get('sha256_match') is not True or e.get('stable_during_hash') is not True))]
    unverified.extend(e['path'] for r in report['roots'] for e in r.get('unverified_conversions', []))
    report['unverified_assets'] = sorted(set(unverified))

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    for r in report["roots"]:
        print(f'== {r["root"]} present={r["present"]} files={len(r["entries"])}')
        for e in r["entries"]:
            flag = ("OK" if e["size_match"] else
                    ("SIZE-MISMATCH" if e["size_match"] is False else "NO-REF"))
            print(f'  [{flag}] {e["size"]} B  {e["path"]}')
            if e["sha256"]:
                print(f'           sha256={e["sha256"]}')
    print(f"wrote {args.out}")
    if mismatches or unverified:
        print(f'MISMATCHES: {len(mismatches)}; UNVERIFIED: {len(unverified)}', file=sys.stderr)
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
