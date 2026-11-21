"""Reject oversized or binary model assets before staging/committing."""

import argparse
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-mib", type=int, default=10)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, check=True, capture_output=True,
    )
    forbidden = {".gguf", ".safetensors", ".bin", ".pt", ".pth", ".exe", ".dll"}
    problems = []
    paths = set(result.stdout.decode("utf-8").split("\0")) - {""}
    for name in sorted(paths):
        path = root / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > args.max_mib * 1024 * 1024 or path.suffix.lower() in forbidden:
            problems.append(f"{name}: {size} bytes")
    if problems:
        print("Refusing oversized/model assets:\n" + "\n".join(problems))
        return 1
    print(f"OK: {len(paths)} eligible files; maximum {args.max_mib} MiB per file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
