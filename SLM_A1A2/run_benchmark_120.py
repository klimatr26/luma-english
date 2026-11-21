"""Root runner for the Fase 2 writing A1/A2 development benchmark (120 cases).

What this script does
---------------------
Runs the frozen 120-case development benchmark against the 16 manifest
configurations (16 x 120 = 1920 model calls) through one locally managed
server process at a time, persisting exact transport records for later
independent evaluation. It performs NO scoring and NEVER sees gold answers:
only ``id``/``level``/``task``/``student_text`` leave the benchmark file.

Persistence layout (under ``--out-dir``)
----------------------------------------
- ``raw/<config_id>/attempts.jsonl``: ONE ROW PER ATTEMPT, exact bytes only
  (``response_body_exact``). Appended and fsynced BEFORE any body parsing.
  Attempts share the logical ``resume_key`` and are nested by ``attempt``.
- ``parsed/<config_id>/responses.jsonl``: one row per case invocation; an
  explicitly authorized ``--retry-failed`` can append another row for the
  same case. Rows are derived ONLY after raw attempts are fsynced and carry
  ``raw_response`` (the exact ``choices[0].message.content`` string, or ``""``)
  plus the trace needed to reconcile against RAW.
- ``checkpoint.json``: convenience cache of per-key states. The RAW files
  are the authority: on startup keys are replayed from raw, checkpoint
  claims without raw evidence are rejected, never trusted.
- ``reports/run_summary.json``: transport counts only. No gold, no student
  text, no scores anywhere in outputs.

What this script never does
---------------------------
- No inference without BOTH ``--authorize-execution`` AND the exact
  ``--approved-benchmark-sha256`` (checked via ``scripts/authorization_guard.py``,
  including for ``--dry-run`` and for filtered ``--config``/``--case`` runs).
- No readiness probing (owned by a separate agent); instead it requires a
  final readiness pass covering every manifest configuration (currently
  16/16) before the main run and refuses otherwise.
- No sampling-parameter flags: ``max_tokens`` (fixed 512), temperatures and
  native-template settings come verbatim from the manifest. Grammar /
  JSON-schema constrained decoding, multimodal projectors and draft/speculative
  decoding are forbidden and rejected explicitly.
- Thinking is disabled through explicit ``--reasoning off`` and a zero
  thinking budget, also sent as ``reasoning_budget_tokens=0``. Launch/request
  overrides that re-enable it are rejected; native templates are retained.
- No output-guided tuning: parameters are recorded, never adjusted.
- No retries for semantic outcomes (invalid JSON, truncation, repetition):
  recorded once. Technical transport failures retry bounded; HTTP 429
  (rate limit) stops the whole run immediately with NO retry.
- Never touches the final ~200-case test set. Never kills foreign processes.

Pre-flight gates (all fail-closed, all apply to dry-run and selections too)
---------------------------------------------------------------------------
1. Authorization guard: flag + exact benchmark bytes.
2. Benchmark contract: dict with ``benchmark_id``, ``version``,
   ``system_prompt``, ``user_prompt_template``, ``cases`` (exactly 120,
   unique IDs, each with ``id``/``level``/``task``/``student_text`` + gold).
3. Manifest contract: dict with ``configurations`` (exactly 16, unique IDs).
   Launch argv must bind ``127.0.0.1``, use context 4096 and ``-ngl 999``;
   anything missing or forbidden aborts with the field named -- never
   silently invented.
4. Readiness: top-level ``manifest_sha256`` must bind the exact current
   manifest, with final passes covering every manifest config; per-entry
   ``model_sha256``/``manifest_sha256``, when present, must bind.
5. Validation: strict final report, status ``VALIDATED_PENDING_USER_APPROVAL``,
   integer (non-bool) ``blocker_count == 0`` and ``review_count == 0``,
   bound to the approved benchmark SHA.

Resume (RAW is the authority)
-----------------------------
- Every attempt is fsynced to raw with a ``disposition`` (``retry``/``final``)
  decided from the status code BEFORE any body parsing.
- A logical key is complete iff raw holds a ``final`` attempt whose outcome
  is not ``rate_limited``. Failed transport/HTTP outcomes are kept once and
  skipped on resume, unless the explicit manual flag ``--retry-failed`` is
  given (re-running the command at all is already a manual act; nothing is
  ever retried silently). ``rate_limited`` keys are never marked done.
- Startup replays raw: foreign hashes, unresolvable key parts, duplicate
  ``(key, attempt)`` rows, duplicate finals, or checkpoint claims without
  raw evidence are all rejected fail-closed. Checkpoint entries missing
  from raw cannot exist (rejected); raw completions missing from the
  checkpoint are rebuilt, never lost (crash between raw fsync and
  checkpoint write recovers).

Only the Python standard library is used, plus OPTIONAL ``psutil`` /
``nvidia-smi`` for best-effort memory sampling (nulls with explicit reasons
when unavailable; measurements are never fabricated).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUNNER_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = RUNNER_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from authorization_guard import AuthorizationError, require_authorization  # noqa: E402

EXPECTED_CASES = 120
EXPECTED_CONFIGS = 16
EXPECTED_TOTAL_ROWS = EXPECTED_CASES * EXPECTED_CONFIGS
FIXED_MAX_TOKENS = 512
REQUIRED_BENCHMARK_KEYS = (
    "benchmark_id", "version", "system_prompt", "user_prompt_template", "cases",
)
FORBIDDEN_GENERATION_KEYS = (
    "grammar", "json_schema", "response_format", "grammars", "schema",
)
READINESS_PASS_STATUSES = {"pass", "ready", "ok"}
VALIDATION_OK_STATUS = "VALIDATED_PENDING_USER_APPROVAL"
VALIDATION_SHA_KEYS = ("benchmark_sha256", "benchmark_sha", "sha256",
                       "final_benchmark_sha256", "final_benchmark_sha")
READINESS_MODEL_SHA_KEYS = ("model_sha256", "model_sha", "sha256")
READINESS_MANIFEST_SHA_KEYS = ("manifest_sha256", "manifest_sha")
# Raw attempt rows carry ONLY exact records; these derived keys must never
# appear in raw. The unit tests enforce this allowlist gap.
RAW_ATTEMPT_KEYS = {"resume_key", "attempt", "disposition", "benchmark_sha256",
                    "manifest_sha256", "model_sha256", "config_id", "case_id",
                    "http_status", "response_body_exact", "error",
                    "latency_seconds", "recorded_utc", "retry_mode",
                    "retry_of_attempt", "retry_of_outcome"}

EXIT_OK = 0
EXIT_GATE = 2
EXIT_RATE_LIMITED = 3


class GateError(ValueError):
    """A fail-closed pre-flight or consistency gate refused the run."""


class CheckpointMismatchError(GateError):
    """Existing checkpoint/outputs are inconsistent with this run; refusing."""


class RateLimitedError(RuntimeError):
    """HTTP 429 observed: stop the whole run immediately, no retry."""


# ---------------------------------------------------------------------------
# Hashing / loading helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_file(model_path: str, expected_sha256: str,
                      expected_size_bytes: int | None = None,
                      root: Path = RUNNER_DIR) -> dict:
    """Rehash one GGUF immediately before launch and reject changing files."""
    if (not isinstance(model_path, str) or not model_path.strip()
            or not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256)):
        raise GateError("Cannot verify model bytes without a path and 64-digit manifest SHA.")
    if (expected_size_bytes is not None
            and (not isinstance(expected_size_bytes, int)
                 or isinstance(expected_size_bytes, bool)
                 or expected_size_bytes < 1)):
        raise GateError("Manifest GGUF byte size must be a positive integer when declared.")
    candidate = Path(model_path)
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    try:
        resolved_before = candidate.resolve(strict=True)
        before = resolved_before.stat()
        if not resolved_before.is_file():
            raise GateError(f"Manifest model path is not a file: {model_path!r}.")
        if expected_size_bytes is not None and before.st_size != expected_size_bytes:
            raise GateError(f"Model size for {model_path!r} differs from manifest; refusing launch.")
        digest = sha256_file(resolved_before)
        after = resolved_before.stat()
        resolved_after = candidate.resolve(strict=True)
    except OSError as exc:
        raise GateError(f"Cannot verify model file {model_path!r}: {exc}.") from exc
    stable_before = (before.st_size, before.st_mtime_ns, before.st_dev, before.st_ino)
    stable_after = (after.st_size, after.st_mtime_ns, after.st_dev, after.st_ino)
    try:
        same_file = resolved_before.samefile(resolved_after)
    except OSError:
        same_file = False
    if stable_before != stable_after or not same_file:
        raise GateError(f"Model file {model_path!r} changed while hashing; refusing launch.")
    if digest.lower() != expected_sha256.lower():
        raise GateError(f"Model SHA-256 for {model_path!r} differs from manifest; refusing launch.")
    return {"path": str(resolved_before), "size_bytes": after.st_size,
            "sha256": digest.lower(), "stable": True}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_json_snapshot(path: Path) -> tuple[object, str]:
    """Parse one byte snapshot and return its SHA, avoiding hash/parse drift."""
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    return data, hashlib.sha256(raw).hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl_fsync(path: Path, row: dict) -> None:
    """Append one JSON line and fsync. Used for BOTH raw and parsed files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def count_jsonl_lines(path: Path) -> int:
    """Count non-blank lines. Pure observation; never raises on missing file."""
    if not path.exists():
        return 0
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total


def max_attempt_for_key(raw_path: Path, key: str) -> int:
    """Highest attempt number already persisted for a resume key (0 if none).

    Manual ``--retry-failed`` reruns continue numbering from here, so raw
    ``(key, attempt)`` pairs stay unique and the replay never sees duplicates.
    """
    best = 0
    if not raw_path.exists():
        return best
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue  # malformed lines are rejected by the replay pass
            if row.get("resume_key") == key and isinstance(row.get("attempt"), int):
                best = max(best, row["attempt"])
    return best


# ---------------------------------------------------------------------------
# Benchmark contract
# ---------------------------------------------------------------------------

def validate_benchmark(data, expected_cases: int = EXPECTED_CASES) -> tuple[dict, list[dict]]:
    """Check the final benchmark dict contract; return (meta, cases)."""
    if not isinstance(data, dict):
        raise GateError("Benchmark must be a JSON object (dict), "
                        f"got {type(data).__name__}.")
    missing = [k for k in REQUIRED_BENCHMARK_KEYS if k not in data]
    if missing:
        raise GateError(f"Benchmark missing required keys: {missing}.")
    for key in ("system_prompt", "user_prompt_template"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise GateError(f"Benchmark {key!r} must be a non-empty string.")
    cases = data["cases"]
    if not isinstance(cases, list) or len(cases) != expected_cases:
        n = len(cases) if isinstance(cases, list) else type(cases).__name__
        raise GateError(f"Benchmark must hold exactly {expected_cases} cases; found {n}.")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise GateError(f"Case #{index} is not an object.")
        for key in ("id", "level", "task", "student_text"):
            value = case.get(key)
            if not isinstance(value, str) or not value.strip():
                raise GateError(f"Case #{index} has missing/empty {key!r}.")
        if case["id"] in seen:
            raise GateError(f"Duplicate benchmark case id {case['id']!r}.")
        seen.add(case["id"])
        # Gold answers exist in the file but must never be transmitted or logged.
        if "gold" not in case:
            raise GateError(f"Case {case['id']!r} lacks its gold entry (contract).")
    meta = {k: v for k, v in data.items() if k != "cases"}
    return meta, cases


# ---------------------------------------------------------------------------
# Manifest contract
#
# CONFIG FIELDS (per entry of ``configurations``; aliases accepted, extra
# keys preserved verbatim under ``manifest_extra`` and never interpreted):
#   identity : config_id | id | name            (required)
#   launch   : server_command | command         (required, str or list[str])
#   port     : port                              (required int; no silent pick)
#   model ref: model_path | model_id | gguf      (required string)
#   model sha: model_sha256 | sha256 | lfs_sha256 (required 64 hex chars)
#   gen      : generation (required dict, max_tokens must be 512, no
#              grammar/response_format/json_schema keys)
#   template : chat_template | template          (optional, recorded verbatim)
#   offload  : offload | gpu_offload             (optional, recorded verbatim)
#
# Launch argv policy (checked here, fail-closed):
#   bind 127.0.0.1, context 4096 (-c/--ctx-size), -ngl 999
#   (-ngl/--n-gpu-layers); no mmproj / grammar / draft flags anywhere.
# ---------------------------------------------------------------------------

_ID_KEYS = ("config_id", "id", "name")
_LAUNCH_KEYS = ("server_command", "command")
_MODEL_REF_KEYS = ("model_path", "model_id", "gguf")
_MODEL_SHA_KEYS = ("model_sha256", "sha256", "lfs_sha256")
_TEMPLATE_KEYS = ("chat_template", "template")
_OFFLOAD_KEYS = ("offload", "gpu_offload")


def _first_present(entry: dict, keys: tuple[str, ...]):
    for key in keys:
        if entry.get(key) not in (None, ""):
            return key, entry[key]
    return None, None


def check_argv_policy(argv: list[str], parallel_sequences: int | None = None) -> None:
    """Enforce the frozen launch policy on manifest argv. Fail-closed."""
    if not argv:
        raise GateError("Manifest launch argv is empty.")
    for flag, expected in (('--reasoning', 'off'), ('--reasoning-budget', '0')):
        matches = [argv[i+1] if i+1 < len(argv) else None
                   for i, token in enumerate(argv) if token == flag]
        if matches != [expected]:
            raise GateError(f'Launch argv must declare exactly one {flag} {expected}; thinking must be disabled.')
    if any(t.startswith('--reasoning=') or t.startswith('--reasoning-budget=') or t == '-rea' for t in argv):
        raise GateError('Reasoning aliases/duplicate overrides are not allowed in the frozen launch argv.')
    for i, token in enumerate(argv):
        if token == '--chat-template-kwargs':
            try:
                kwargs = json.loads(argv[i+1])
            except (ValueError, IndexError):
                raise GateError('Invalid native chat-template kwargs.')
            if not isinstance(kwargs, dict) or kwargs.get('enable_thinking', False) is not False:
                raise GateError('Native chat-template kwargs must not enable thinking.')
    joined = " ".join(argv)
    if "127.0.0.1" not in joined:
        raise GateError("Launch argv must bind 127.0.0.1 explicitly; "
                        f"got: {joined!r}.")
    if not _flag_value_is(argv, ("-c", "--ctx-size"), "4096"):
        raise GateError("Launch argv must set context 4096 (-c/--ctx-size 4096); "
                        f"got: {joined!r}.")
    if not _flag_value_is(argv, ("-ngl", "--n-gpu-layers"), "999"):
        raise GateError("Launch argv must attempt full GPU offload (-ngl/--n-gpu-layers 999); "
                        f"got: {joined!r}.")
    if parallel_sequences is not None and not _flag_value_is(
            argv, ("--parallel",), str(parallel_sequences)):
        raise GateError(f"Launch argv must set --parallel {parallel_sequences} "
                        "to match the manifest runtime.parallel_sequences; "
                        f"got: {joined!r}.")
    for token in argv:
        low = token.lower()
        if "mmproj" in low or "grammar" in low:
            raise GateError(f"Launch argv forbids multimodal projectors and constrained "
                            f"decoding; offending token: {token!r}.")
        if token.startswith("-") and "draft" in low:
            raise GateError(f"Launch argv forbids draft/speculative decoding; offending "
                            f"token: {token!r}.")


def _flag_value_is(argv: list[str], flags: tuple[str, ...], want: str) -> bool:
    for index, token in enumerate(argv):
        if token in flags and index + 1 < len(argv) and argv[index + 1] == want:
            return True
        for flag in flags:
            if token == f"{flag}={want}":
                return True
    return False


def validate_argv_model_path(argv: list[str], model_ref: str,
                             root: Path = RUNNER_DIR) -> Path:
    """Require the launched ``-m`` file to be the same as the SHA-bound ref."""
    values: list[str] = []
    for index, token in enumerate(argv):
        if token in ("-m", "--model"):
            if index + 1 >= len(argv) or not argv[index + 1] or argv[index + 1].startswith("-"):
                raise GateError("Launch argv has a missing model path after -m/--model.")
            values.append(argv[index + 1])
        elif token.startswith("-m=") or token.startswith("--model="):
            values.append(token.split("=", 1)[1])
    if len(values) != 1:
        raise GateError("Launch argv must contain exactly one -m/--model path bound to the manifest model SHA.")

    expected = Path(model_ref)
    actual = Path(values[0])
    root = Path(root)
    if not expected.is_absolute():
        expected = root / expected
    if not actual.is_absolute():
        actual = root / actual
    expected_path = expected.resolve(strict=False)
    actual_path = actual.resolve(strict=False)
    if os.path.normcase(str(expected_path)) != os.path.normcase(str(actual_path)):
        raise GateError("Launch argv model path differs from the manifest SHA-bound model reference.")
    return expected_path


def resolve_argv(argv: list[str], root: Path) -> list[str]:
    """Resolve a relative ``-m``/``--model`` path against the runner root.

    Pure function (unit-tested). Existence is NOT checked here: the server
    itself reports a bad path via its health check, and this runner never
    invents files.
    """
    out = list(argv)
    for index, token in enumerate(out):
        if token in ("-m", "--model") and index + 1 < len(out):
            value = out[index + 1]
            if value and not Path(value).is_absolute():
                out[index + 1] = str(Path(root) / value)
    return out


def normalize_config(entry: dict, index: int) -> dict:
    if not isinstance(entry, dict):
        raise GateError(f"Manifest configuration #{index} is not an object.")
    _, config_id = _first_present(entry, _ID_KEYS)
    if not isinstance(config_id, str) or not config_id.strip():
        raise GateError(f"Manifest configuration #{index} is missing its identity "
                        f"(expected one of {_ID_KEYS}); refusing to invent one.")
    tag = f"config {config_id!r}"

    launch_key, launch = _first_present(entry, _LAUNCH_KEYS)
    if isinstance(launch, str):
        if not launch.strip():
            raise GateError(f"{tag}: empty launch command; refusing to invent one.")
        argv = shlex.split(launch, posix=(os.name != "nt"))
    elif isinstance(launch, list) and launch and all(isinstance(p, str) for p in launch):
        argv = list(launch)
    else:
        raise GateError(f"{tag}: missing launch field (expected one of "
                        f"{_LAUNCH_KEYS} as a command string or argv list); "
                        "refusing to invent one.")
    runtime = entry.get("runtime")
    if runtime is not None and not isinstance(runtime, dict):
        raise GateError(f"{tag}: 'runtime' must be an object when declared.")
    parallel_sequences = (runtime.get("parallel_sequences")
                          if isinstance(runtime, dict)
                          else entry.get("parallel_sequences"))
    if parallel_sequences is not None:
        if (not isinstance(parallel_sequences, int)
                or isinstance(parallel_sequences, bool)
                or parallel_sequences < 1):
            raise GateError(f"{tag}: runtime.parallel_sequences must be a positive integer.")
    check_argv_policy(argv, parallel_sequences)

    port = entry.get("port")
    if isinstance(port, str) and port.isdigit():
        port = int(port)
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        raise GateError(f"{tag}: missing/invalid 'port' (required int 1-65535); "
                        "refusing to pick one silently.")

    _, model_ref = _first_present(entry, _MODEL_REF_KEYS)
    if not isinstance(model_ref, str) or not model_ref.strip():
        raise GateError(f"{tag}: missing model reference (expected one of "
                        f"{_MODEL_REF_KEYS}); refusing to invent one.")
    validate_argv_model_path(argv, model_ref)

    _, model_sha = _first_present(entry, _MODEL_SHA_KEYS)
    if (not isinstance(model_sha, str) or len(model_sha) != 64
            or any(c not in "0123456789abcdef" for c in model_sha.lower())):
        raise GateError(f"{tag}: missing/invalid model SHA (expected one of "
                        f"{_MODEL_SHA_KEYS} as 64 hex chars); refusing to invent one.")

    generation = entry.get("generation")
    if not isinstance(generation, dict):
        raise GateError(f"{tag}: missing 'generation' dict (max_tokens and sampling "
                        "parameters must come from the manifest).")
    if generation.get("max_tokens") != FIXED_MAX_TOKENS:
        raise GateError(f"{tag}: generation.max_tokens must be exactly "
                        f"{FIXED_MAX_TOKENS} per the frozen manifest; "
                        f"found {generation.get('max_tokens')!r}.")
    forbidden = [k for k in FORBIDDEN_GENERATION_KEYS if k in generation]
    if type(generation.get('reasoning_budget_tokens')) is not int or generation['reasoning_budget_tokens'] != 0:
        raise GateError(f'{tag}: generation.reasoning_budget_tokens must be the integer 0.')
    if generation.get('reasoning_effort', 'none') != 'none':
        raise GateError(f'{tag}: reasoning_effort must not enable thinking.')
    request_kwargs = generation.get('chat_template_kwargs', {})
    if not isinstance(request_kwargs, dict) or request_kwargs.get('enable_thinking', False) is not False:
        raise GateError(f'{tag}: generation chat_template_kwargs must not enable thinking.')
    if forbidden:
        raise GateError(f"{tag}: constrained decoding is forbidden in free-format "
                        f"mode; generation must not contain {forbidden}.")

    _, template = _first_present(entry, _TEMPLATE_KEYS)
    _, offload = _first_present(entry, _OFFLOAD_KEYS)
    gguf = entry.get("gguf")
    model_size_bytes = gguf.get("bytes") if isinstance(gguf, dict) else None
    if (model_size_bytes is not None
            and (not isinstance(model_size_bytes, int)
                 or isinstance(model_size_bytes, bool)
                 or model_size_bytes < 1)):
        raise GateError(f"{tag}: gguf.bytes must be a positive integer when declared.")
    known = set(_ID_KEYS) | set(_LAUNCH_KEYS) | set(_MODEL_REF_KEYS) | set(
        _MODEL_SHA_KEYS) | {"port", "generation", "runtime", "parallel_sequences"} | set(_TEMPLATE_KEYS) | set(_OFFLOAD_KEYS)
    extra = {k: v for k, v in entry.items() if k not in known}
    return {
        "config_id": config_id,
        "launch_key": launch_key,
        "argv": argv,
        "port": port,
        "model_ref": model_ref,
        "model_sha256": model_sha.lower(),
        "model_size_bytes": model_size_bytes,
        "generation": dict(generation),
        "chat_template": template,  # native server-side template; recorded only
        "offload": offload,          # readiness snapshot; recorded only
        "parallel_sequences": parallel_sequences,
        "manifest_extra": extra,     # preserved, never interpreted
    }


def validate_manifest(data) -> list[dict]:
    if not isinstance(data, dict):
        raise GateError("Manifest must be a JSON object (dict).")
    configs = data.get("configurations")
    if not isinstance(configs, list) or len(configs) != EXPECTED_CONFIGS:
        n = len(configs) if isinstance(configs, list) else type(configs).__name__
        raise GateError(f"Manifest must hold exactly {EXPECTED_CONFIGS} configurations "
                        f"under 'configurations'; found {n}.")
    normalized = [normalize_config(e, i) for i, e in enumerate(configs)]
    ids = [c["config_id"] for c in normalized]
    if len(set(ids)) != len(ids):
        raise GateError(f"Manifest has duplicate config ids: {ids}.")
    return normalized


# ---------------------------------------------------------------------------
# Readiness + validation gates (externally owned report schemas; explicit)
# ---------------------------------------------------------------------------

def check_readiness(configs: list[dict], report, manifest_sha: str | None = None) -> dict:
    """Require a final pass covering every manifest config id.

    Per-entry ``model_sha256``/``manifest_sha256``, when present, must bind to
    the manifest values; absence is accepted (never invented), mismatch aborts.
    When the caller supplies a manifest SHA, the readiness report's top-level
    ``manifest_sha256`` is required and must bind the entire readiness snapshot.
    """
    if not isinstance(report, dict) or not isinstance(report.get("configs"), list):
        raise GateError("Readiness report must be a JSON object with a 'configs' list "
                        "of {'config_id', 'status'} entries (schema owned by the "
                        "readiness agent); refusing to guess another shape.")
    if manifest_sha is not None:
        report_manifest_sha = report.get("manifest_sha256")
        if (not isinstance(report_manifest_sha, str)
                or report_manifest_sha.lower() != manifest_sha.lower()):
            raise GateError("Readiness report top-level manifest_sha256 is missing or "
                            "does not bind this exact manifest; main run refused.")
    by_id = {c["config_id"]: c for c in configs}
    passed: set[str] = set()
    seen: set[str] = set()
    for entry in report["configs"]:
        if not isinstance(entry, dict):
            raise GateError("Readiness report holds a non-object entry; refusing.")
        cid = entry.get("config_id")
        if not isinstance(cid, str) or cid not in by_id:
            raise GateError(f"Readiness report names an unknown config {cid!r}; refusing.")
        if cid in seen:
            raise GateError(f"Readiness report duplicates config {cid!r}; refusing to guess.")
        seen.add(cid)
        if entry.get("status") not in READINESS_PASS_STATUSES:
            raise GateError(f"Readiness for {cid!r} is not passing "
                            f"(status={entry.get('status')!r}); main run refused.")
        _, entry_model_sha = _first_present(entry, READINESS_MODEL_SHA_KEYS)
        if entry_model_sha is not None:
            if (not isinstance(entry_model_sha, str)
                    or entry_model_sha.lower() != by_id[cid]["model_sha256"]):
                raise GateError(f"Readiness entry for {cid!r} binds a different "
                                "model SHA than the manifest; main run refused.")
        _, entry_manifest_sha = _first_present(entry, READINESS_MANIFEST_SHA_KEYS)
        if entry_manifest_sha is not None and manifest_sha is not None:
            if (not isinstance(entry_manifest_sha, str)
                    or entry_manifest_sha.lower() != manifest_sha.lower()):
                raise GateError(f"Readiness entry for {cid!r} binds a different "
                                "manifest SHA than this run; main run refused.")
        passed.add(cid)
    missing = sorted(set(by_id) - passed)
    if missing:
        raise GateError(f"Final readiness {len(passed)}/{len(by_id)} not met; "
                        "missing passing entries for: "
                        f"{missing}. Main run refused.")
    return {"passed": len(passed), "required": len(by_id)}


def _require_zero_int(report: dict, key: str) -> None:
    value = report.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GateError(f"Validation report {key!r} must be an integer "
                        f"(booleans rejected); found {value!r}.")
    if value != 0:
        raise GateError(f"Validation report {key}={value}; main run refused until "
                        "the benchmark validates clean.")


def check_validation(report, approved_sha: str) -> dict:
    """Align to the strict final validation report.

    Accepted if and only if: ``status`` is exactly
    ``VALIDATED_PENDING_USER_APPROVAL`` (no pending/unresolved state),
    integer (non-bool) ``blocker_count == 0`` and ``review_count == 0``,
    and a declared final benchmark SHA equals the approved SHA.
    """
    if not isinstance(report, dict):
        raise GateError("Validation report must be a JSON object.")
    status = report.get("status")
    if status != VALIDATION_OK_STATUS:
        raise GateError(f"Validation status {status!r} is not the accepted final "
                        f"state {VALIDATION_OK_STATUS!r}; pending/unresolved "
                        "validations never authorize a main run.")
    _require_zero_int(report, "blocker_count")
    _require_zero_int(report, "review_count")
    declared = None
    for key in VALIDATION_SHA_KEYS:
        if isinstance(report.get(key), str):
            declared = report[key]
            break
    if declared is None:
        raise GateError("Validation report declares no final benchmark SHA (expected one of "
                        f"{list(VALIDATION_SHA_KEYS)}); refusing an untied validation.")
    if declared.lower() != approved_sha.lower():
        raise GateError("Validation report SHA differs from the approved benchmark SHA; "
                        "main run refused.")
    return {"status": status, "blocker_count": 0, "review_count": 0,
            "benchmark_sha256": declared.lower()}


# ---------------------------------------------------------------------------
# Resume bookkeeping: RAW is the authority, checkpoint is a cache
# ---------------------------------------------------------------------------

def resume_key(benchmark_sha: str, model_sha: str, manifest_sha: str,
               config_id: str, case_id: str) -> str:
    return ":".join([benchmark_sha, model_sha, manifest_sha, config_id, case_id])


def split_resume_key(key: str, benchmark_sha: str, manifest_sha: str,
                     configs_by_id: dict, case_ids: set[str]) -> tuple[str, str]:
    """Resolve a raw resume key to (config_id, case_id), fail-closed.

    Verifies the benchmark/manifest hash parts, the model-SHA binding is left
    to the caller (it lives in the row), and that the trailing part resolves
    to a known config + known case. Foreign or unresolvable keys abort.

    Key layout is ``benchmark:model:manifest:config:case``; the two middle
    hashes are fixed-length, so parts are matched positionally instead of by
    blind splitting (config/case ids could theoretically contain colons,
    which are preserved by rejoining the tail).
    """
    parts = key.split(":")
    if (len(parts) < 5 or parts[0] != benchmark_sha or parts[2] != manifest_sha):
        raise CheckpointMismatchError(
            f"Raw resume key {key!r} names foreign benchmark/manifest hashes or "
            "is malformed; refusing to mix runs.")
    model_sha, config_id = parts[1], parts[3]
    case_id = ":".join(parts[4:])
    if config_id not in configs_by_id:
        raise CheckpointMismatchError(
            f"Raw resume key {key!r} names an unknown config; refusing.")
    if case_id not in case_ids:
        raise CheckpointMismatchError(
            f"Raw resume key {key!r} names an unknown case; refusing.")
    if not (isinstance(model_sha, str) and len(model_sha) == 64):
        raise CheckpointMismatchError(f"Raw resume key {key!r} is malformed.")
    return model_sha, config_id, case_id


def load_checkpoint(path: Path, benchmark_sha: str, manifest_sha: str) -> dict:
    """Load the checkpoint cache. Shape errors or hash drift abort."""
    if not path.exists():
        return {"benchmark_sha256": benchmark_sha, "manifest_sha256": manifest_sha,
                "states": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CheckpointMismatchError(f"Checkpoint {path} is unreadable: {exc}.")
    if not isinstance(data, dict) or not isinstance(data.get("states"), dict):
        raise CheckpointMismatchError(f"Checkpoint {path} has an unexpected shape.")
    if (data.get("benchmark_sha256") != benchmark_sha
            or data.get("manifest_sha256") != manifest_sha):
        raise CheckpointMismatchError(
            f"Checkpoint {path} names benchmark/manifest hashes "
            f"({data.get('benchmark_sha256')}, {data.get('manifest_sha256')}) "
            "that differ from this run; refusing to mix runs.")
    return data


def write_checkpoint_atomic(path: Path, benchmark_sha: str, manifest_sha: str,
                            states: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"benchmark_sha256": benchmark_sha, "manifest_sha256": manifest_sha,
               "updated_utc": utcnow(), "states": states}
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def finalize_outcome(status: int | None, error: str | None, body_text: str) -> str:
    """Single deterministic mapping from exact records to an outcome.

    Pure function of persisted raw data: used both live (after the raw row
    is fsynced) and during replay. Semantic inspection of the body happens
    only here, never before the raw persist.
    """
    handling = classify_http_status(status)
    if handling == "rate_limited":
        return "rate_limited"
    if handling == "retryable":
        return "transport_error" if status is None else f"http_{status}"
    if handling == "record_once":
        return f"http_{status}"
    # handling == "ok": body validity is a semantic observation, recorded once.
    try:
        payload = json.loads(body_text)
        valid = isinstance(payload, dict)
    except Exception:
        valid = False
    return "ok" if valid else "invalid_body"


def outcome_manual_retry_eligible(outcome: str) -> bool:
    """Failed-transport outcomes re-runnable ONLY via explicit --retry-failed."""
    if outcome == "transport_error":
        return True
    if outcome.startswith("http_"):
        try:
            return int(outcome.split("_", 1)[1]) >= 500
        except ValueError:
            return False
    return False


def replay_raw_authority(raw_attempt_paths: list[Path], benchmark_sha: str,
                         manifest_sha: str, configs_by_id: dict,
                         case_ids: set[str]) -> dict:
    """Rebuild logical completion states from RAW attempt files (authority).

    Returns the latest state for every resume key. RAW attempt numbering and
    the retry metadata are the authority: a later final group is accepted only
    when its first row explicitly names the previous eligible failure (or a
    prior rate-limit stop) as its reason. This permits ``--retry-failed`` to
    append a new result without making arbitrary duplicate finals ambiguous.
    """
    attempts_seen: set[tuple[str, int]] = set()
    rows_by_key: dict[str, list[dict]] = {}
    for path in raw_attempt_paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception as exc:
                    raise CheckpointMismatchError(
                        f"Raw file {path} line {lineno} is not valid JSON: {exc}.")
                if not isinstance(row, dict) or set(row) - RAW_ATTEMPT_KEYS:
                    raise CheckpointMismatchError(
                        f"Raw file {path} line {lineno} carries unexpected keys "
                        "(raw holds exact records only, never derived data).")
                key = row.get("resume_key")
                attempt = row.get("attempt")
                if (not isinstance(key, str) or not isinstance(attempt, int)
                        or isinstance(attempt, bool) or attempt < 1):
                    raise CheckpointMismatchError(
                        f"Raw file {path} line {lineno} lacks a valid resume_key/attempt.")
                if (key, attempt) in attempts_seen:
                    raise CheckpointMismatchError(
                        f"Raw file {path} holds a duplicated (resume_key, attempt) "
                        f"({key!r}, {attempt}); refusing to guess.")
                attempts_seen.add((key, attempt))
                model_sha, config_id, case_id = split_resume_key(
                    key, benchmark_sha, manifest_sha, configs_by_id, case_ids)
                if row.get("model_sha256") != configs_by_id[config_id]["model_sha256"]:
                    raise CheckpointMismatchError(
                        f"Raw row ({key!r}, attempt {attempt}) binds a model SHA "
                        "that differs from the manifest; refusing to mix runs.")
                if row.get("config_id") != config_id or row.get("case_id") != case_id:
                    raise CheckpointMismatchError(
                        f"Raw row ({key!r}, attempt {attempt}) disagrees with its own "
                        "resume key parts; refusing.")
                if (row.get("benchmark_sha256") != benchmark_sha
                        or row.get("manifest_sha256") != manifest_sha):
                    raise CheckpointMismatchError(
                        f"Raw row ({key!r}, attempt {attempt}) carries benchmark/manifest "
                        "hashes that differ from its resume key; refusing to mix runs.")
                if row.get("disposition") not in {"retry", "final"}:
                    raise CheckpointMismatchError(
                        f"Raw row ({key!r}, attempt {attempt}) has an unknown disposition.")
                if "retry_mode" not in row:
                    # Accept old single-group files; legacy duplicates cannot
                    # prove that the later request was explicitly authorized.
                    row = dict(row, retry_mode="legacy", retry_of_attempt=None,
                               retry_of_outcome=None)
                if row.get("retry_mode") not in {
                        "legacy", "initial", "retry_failed", "rate_limit_resume"}:
                    raise CheckpointMismatchError(
                        f"Raw row ({key!r}, attempt {attempt}) has an unknown retry mode.")
                rows_by_key.setdefault(key, []).append(row)

    latest: dict[str, dict] = {}
    for key, rows in rows_by_key.items():
        rows.sort(key=lambda row: row["attempt"])
        numbers = [row["attempt"] for row in rows]
        if numbers != list(range(1, numbers[-1] + 1)):
            raise CheckpointMismatchError(
                f"Raw attempts for {key!r} are not contiguous from attempt 1; refusing.")
        groups: list[list[dict]] = []
        group: list[dict] = []
        for row in rows:
            group.append(row)
            if row["disposition"] == "final":
                groups.append(group)
                group = []
        if group:
            raise CheckpointMismatchError(
                f"Raw attempts for {key!r} end in an unfinished technical retry group; "
                "resume requires a complete persisted group.")

        previous_outcome = None
        previous_attempt = None
        last_state = None
        for group_index, attempt_group in enumerate(groups):
            first = attempt_group[0]
            mode = first["retry_mode"]
            ref_attempt = first.get("retry_of_attempt")
            ref_outcome = first.get("retry_of_outcome")
            for row in attempt_group:
                if (row["retry_mode"] != mode
                        or row.get("retry_of_attempt") != ref_attempt
                        or row.get("retry_of_outcome") != ref_outcome):
                    raise CheckpointMismatchError(
                        f"Raw retry provenance changes within the attempt group for {key!r}.")
            if group_index == 0:
                if mode not in {"initial", "legacy"} or ref_attempt is not None or ref_outcome is not None:
                    raise CheckpointMismatchError(
                        f"The first raw attempt group for {key!r} has unexpected retry provenance.")
            else:
                if ref_attempt != previous_attempt or ref_outcome != previous_outcome:
                    raise CheckpointMismatchError(
                        f"Retry group for {key!r} does not point to the preceding final attempt.")
                if outcome_manual_retry_eligible(previous_outcome):
                    if mode != "retry_failed":
                        raise CheckpointMismatchError(
                            f"Retry after failed transport for {key!r} lacks --retry-failed provenance.")
                elif previous_outcome == "rate_limited":
                    if mode != "rate_limit_resume":
                        raise CheckpointMismatchError(
                            f"Attempt after HTTP 429 for {key!r} lacks a new-run resume marker.")
                else:
                    raise CheckpointMismatchError(
                        f"Raw history for {key!r} retries a non-retryable outcome "
                        f"({previous_outcome}); refusing to guess.")

            for prior in attempt_group[:-1]:
                if (prior["disposition"] != "retry"
                        or classify_http_status(prior.get("http_status")) != "retryable"):
                    raise CheckpointMismatchError(
                        f"Raw attempt {prior['attempt']} for {key!r} is marked retry "
                        "without a technical retryable status.")
            final = attempt_group[-1]
            if final["disposition"] != "final":
                raise CheckpointMismatchError(
                    f"Raw attempt group for {key!r} has no final disposition.")
            outcome = finalize_outcome(final.get("http_status"), final.get("error"),
                                       final.get("response_body_exact")
                                       if isinstance(final.get("response_body_exact"), str) else "")
            previous_outcome = outcome
            previous_attempt = final["attempt"]
            last_state = {"state": "pending" if outcome == "rate_limited" else "done",
                          "outcome": outcome, "attempts": len(attempt_group),
                          "last_attempt": final["attempt"],
                          "attempt_trace": [r["attempt"] for r in attempt_group],
                          "retry_mode": mode,
                          "retry_of_attempt": ref_attempt,
                          "retry_of_outcome": ref_outcome,
                          "config_id": final["config_id"],
                          "case_id": final["case_id"]}
        if last_state is not None:
            latest[key] = last_state
    return latest


# ---------------------------------------------------------------------------
# Failure taxonomy: bounded technical retry, never semantic retry, 429 stops
# ---------------------------------------------------------------------------

def classify_http_status(status: int | None) -> str:
    """Map an HTTP outcome to a handling class.

    - 'ok'                 : 2xx, record the body once.
    - 'rate_limited'       : 429, abort the whole run, no retry.
    - 'retryable'          : transport-level/5xx class, bounded retry.
    - 'record_once'        : anything else (4xx, invalid body, truncation):
                             persist once, never retry.
    Decided from the status code ONLY, so it is safe to apply before any
    body parsing.
    """
    if status is None:
        return "retryable"  # connection error / timeout: technical
    if 200 <= status < 300:
        return "ok"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "retryable"
    return "record_once"


def extract_transport(body_text: str) -> dict:
    """Transport-level fields derived ONLY from already-persisted raw bodies."""
    try:
        payload = json.loads(body_text)
    except Exception:
        return {"body_json_valid": False, "finish_reason": None, "usage": None,
                "truncated": False, "completed": False}
    if not isinstance(payload, dict):
        return {"body_json_valid": False, "finish_reason": None, "usage": None,
                "truncated": False, "completed": False}
    choices = payload.get("choices") or []
    finish = choices[0].get("finish_reason") if choices and isinstance(choices[0], dict) else None
    return {"body_json_valid": True, "finish_reason": finish,
            "usage": payload.get("usage"),
            "truncated": finish == "length",
            "completed": finish in ("stop", "eos", "end_of_turn")}


def extract_message_content(body_text: str) -> tuple[str, str]:
    """Return (content, source) from an already-persisted body. No gold involved."""
    try:
        payload = json.loads(body_text)
    except Exception:
        return "", "non_json_body"
    if not isinstance(payload, dict):
        return "", "non_json_body"
    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content, ("message_content" if content else "empty_content")
    return "", "no_message_content"


def has_repetition(text: str) -> bool:
    """Heuristic loop detector on already-persisted text. Observation only:
    recorded in parsed rows, never drives retries or verdicts."""
    if not isinstance(text, str):
        return False
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) >= 120:
        for width in (30, 60):
            if re.search(r"(.{%d,})\1{2,}" % width, normalized):
                return True
    tokens = normalized.split()
    if len(tokens) >= 18:
        tail = tokens[-9:]
        if len(tail) == 9 and tail[:3] == tail[3:6] == tail[6:]:
            return True
    return False


# ---------------------------------------------------------------------------
# Prompt building (gold never leaves the benchmark file)
# ---------------------------------------------------------------------------

def build_messages(system_prompt: str, user_template: str, case: dict) -> tuple[list[dict], str]:
    user_text = user_template.format(level=case["level"], task=case["task"],
                                     student_text=case["student_text"])
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}]
    return messages, sha256_text(json.dumps(messages, ensure_ascii=False))


# ---------------------------------------------------------------------------
# HTTP client (stdlib; injectable for tests)
# ---------------------------------------------------------------------------

class HttpClient:
    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds

    def post_json(self, url: str, payload: dict) -> tuple[int | None, str, str | None]:
        """Return (http_status_or_None, body_text, error). Never raises."""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"},
                                         method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.status, response.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            return exc.code, body, f"HTTPError:{exc.code}"
        except Exception as exc:
            return None, "", f"{type(exc).__name__}:{exc}"

    def get(self, url: str) -> tuple[int | None, str]:
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, ""
        except Exception:
            return None, ""


# ---------------------------------------------------------------------------
# Health rule: exactly 200, and a JSON {"status": ...} body must say "ok"
# ---------------------------------------------------------------------------

def is_healthy_response(status: int | None, body: str) -> bool:
    if status != 200:
        return False  # 404/400/503/anything-else: not healthy, no guessing
    if not body.strip():
        return True  # plain 200 with an empty body (some servers): accept
    try:
        payload = json.loads(body)
    except Exception:
        return True  # plain 200 with a non-JSON body: accept, nothing to bind
    if isinstance(payload, dict) and "status" in payload:
        return payload["status"] == "ok"
    return True


# ---------------------------------------------------------------------------
# Memory sampling: server peak RSS during the request, runner RSS, device GPU
# ---------------------------------------------------------------------------

class PeakSampler:
    """Peak RSS sampler for the server PID plus children, over one request.

    Degrades to explicit nulls (never fabricated numbers) when ``psutil`` is
    unavailable or the PID is unknown (e.g. injected fakes in tests).
    """

    def __init__(self, pid: int | None, interval_seconds: float = 0.05):
        self.pid = pid
        self.interval_seconds = interval_seconds
        self.peak_rss: int | None = None
        self.samples = 0
        self.sampled = False
        self.reason = "not-started"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _target(self) -> None:
        import psutil
        try:
            proc = psutil.Process(self.pid)
        except Exception as exc:
            self.reason = f"server-process-unavailable:{type(exc).__name__}"
            return
        while not self._stop.is_set():
            try:
                total = proc.memory_info().rss
                for child in proc.children(recursive=True):
                    try:
                        total += child.memory_info().rss
                    except Exception:
                        pass
                self.peak_rss = total if self.peak_rss is None else max(self.peak_rss, total)
                self.samples += 1
            except Exception as exc:
                self.reason = f"sampling-interrupted:{type(exc).__name__}"
                return
            self._stop.wait(self.interval_seconds)
        self.sampled = self.samples > 0
        if self.sampled:
            self.reason = "server-peak-rss-during-request"

    def start(self) -> None:
        if self.pid is None:
            self.reason = "no-server-pid"
            return
        try:
            import psutil  # noqa: F401  optional dependency, probed lazily
        except Exception:
            self.reason = "psutil-unavailable"
            return
        self._thread = threading.Thread(target=self._target, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=10)
        return {"server_peak_rss_bytes": self.peak_rss,
                "server_rss_samples": self.samples,
                "server_rss_sampled": self.sampled,
                "server_rss_note": self.reason}


def sample_runner_rss() -> dict:
    """Runner's own RSS (kept SEPARATE from the server measurement)."""
    try:
        import psutil
        return {"runner_rss_bytes": int(psutil.Process(os.getpid()).memory_info().rss),
                "runner_rss_sampled": True,
                "runner_rss_note": "runner-process RSS at row derivation time"}
    except Exception:
        return {"runner_rss_bytes": None, "runner_rss_sampled": False,
                "runner_rss_note": "psutil-unavailable"}


def parse_nvidia_smi_mib(text: str) -> int:
    """Sum the MiB integers of ``nvidia-smi --query-gpu=memory.used`` output."""
    return sum(int(tok) for tok in text.replace(",", " ").split() if tok.strip().isdigit())


def sample_gpu() -> dict:
    """Device-wide GPU memory used. Explicit unit + attribution limits."""
    base = {"gpu_used_bytes": None, "gpu_unit": "bytes", "gpu_sampled": False,
            "gpu_scope": ("device-wide total across ALL processes; NOT attributable "
                          "to this server process"),
            "gpu_note": "nvidia-smi-unavailable"}
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return base
    try:
        out = subprocess.run(
            [nvidia_smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=False)
    except Exception as exc:
        base["gpu_note"] = f"nvidia-smi-failed:{type(exc).__name__}"
        return base
    if out.returncode != 0:
        base["gpu_note"] = f"nvidia-smi-exit-{out.returncode}"
        return base
    try:
        base.update(gpu_used_bytes=parse_nvidia_smi_mib(out.stdout) * 1024 * 1024,
                    gpu_sampled=True, gpu_note="device-wide point sample")
    except Exception as exc:
        base["gpu_note"] = f"nvidia-smi-unparseable:{type(exc).__name__}"
    return base


# ---------------------------------------------------------------------------
# Server lifecycle: exactly one config loaded at a time, own child only
# ---------------------------------------------------------------------------

def check_port_free(port: int) -> None:
    """Best-effort free check. An occupied port aborts; NOTHING is killed."""
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise GateError(f"Port {port} is already occupied; refusing to kill "
                        f"foreign processes: {exc}.")
    finally:
        probe.close()


def check_argv_executable(argv: list[str]) -> None:
    """Refuse to spawn when argv[0] cannot be resolved. No guessing."""
    exe = argv[0]
    if Path(exe).is_absolute() or os.sep in exe or "/" in exe:
        if not Path(exe).is_file():
            raise GateError(f"Launch executable {exe!r} is not a file; refusing.")
    elif shutil.which(exe) is None:
        raise GateError(f"Launch executable {exe!r} not found on PATH; refusing.")


class ManagedServer:
    """Owns ONE server subprocess; the runner holds at most one instance.

    Cleanup touches only the owned child PID: terminate, wait, kill, close
    the log file. If ``__enter__`` fails, partial state is closed, never
    leaked. Foreign processes are never signalled.
    """

    def __init__(self, argv: list[str], port: int, health_url: str, log_path: Path,
                 popen_factory=subprocess.Popen, *, model_path: str | None = None,
                 model_sha256: str | None = None,
                 model_size_bytes: int | None = None):
        self.argv = resolve_argv(argv, RUNNER_DIR)
        self.port = port
        self.health_url = health_url
        self.log_path = log_path
        self.popen_factory = popen_factory
        self.model_path = model_path
        self.model_sha256 = model_sha256
        self.model_size_bytes = model_size_bytes
        self.model_integrity = None
        self.process = None
        self.pid: int | None = None
        self._log_handle = None

    def __enter__(self) -> "ManagedServer":
        check_argv_executable(self.argv)
        check_port_free(self.port)
        if any(value is not None for value in
               (self.model_path, self.model_sha256, self.model_size_bytes)):
            if self.model_path is None or self.model_sha256 is None:
                raise GateError("Model launch integrity check requires both manifest model path and SHA.")
            self.model_integrity = verify_model_file(
                self.model_path, self.model_sha256, self.model_size_bytes)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("ab")
        try:
            self.process = self.popen_factory(self.argv, stdout=self._log_handle,
                                              stderr=subprocess.STDOUT)
            self.pid = self.process.pid
        except Exception:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None
            self.process = None
            raise
        return self

    def wait_healthy(self, client: HttpClient, deadline_seconds: float,
                     interval_seconds: float) -> bool:
        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                return False  # owned server died during startup
            status, body = client.get(self.health_url)
            if is_healthy_response(status, body):
                return True
            time.sleep(interval_seconds)
        return False

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def __exit__(self, *_) -> None:
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()  # own child only
                try:
                    self.process.wait(timeout=15)
                except Exception:
                    try:
                        self.process.kill()  # own child only
                    except Exception:
                        pass
        finally:
            try:
                if self._log_handle is not None:
                    self._log_handle.close()
            except Exception:
                pass
            self.process = None
            self.pid = None


# ---------------------------------------------------------------------------
# Run planning / selection (gated: never a benchmark bypass)
# ---------------------------------------------------------------------------

def select_plan(cases: list[dict], configs: list[dict],
                config_filter: list[str] | None,
                case_filter: list[str] | None) -> list[tuple[dict, dict]]:
    if config_filter:
        wanted = set(config_filter)
        unknown = sorted(wanted - {c["config_id"] for c in configs})
        if unknown:
            raise GateError(f"Unknown --config selection: {unknown}.")
        configs = [c for c in configs if c["config_id"] in wanted]
    if case_filter:
        wanted_cases = set(case_filter)
        unknown_cases = sorted(wanted_cases - {c["id"] for c in cases})
        if unknown_cases:
            raise GateError(f"Unknown --case selection: {unknown_cases}.")
        cases = [c for c in cases if c["id"] in wanted_cases]
    return [(config, case) for config in configs for case in cases]


# ---------------------------------------------------------------------------
# Per-case execution: persist every attempt BEFORE any body parsing
# ---------------------------------------------------------------------------

def run_single_case(*, client: HttpClient, api_url: str, config: dict,
                    case: dict, system_prompt: str, user_template: str,
                    benchmark_sha: str, manifest_sha: str,
                    max_retries: int, persist_attempt,
                    sampler: PeakSampler | None = None,
                    start_attempt: int = 1,
                    retry_context: dict | None = None) -> dict:
    """POST one case; persist each attempt BEFORE parsing its body.

    Returns a ``final_info`` dict of exact facts (statuses, bodies, errors,
    sampler output). Body parsing into transport fields happens later in
    :func:`derive_parsed_row`, only after the raw rows are fsynced by the
    caller. Raises RateLimitedError on HTTP 429 (no retry, caller aborts).
    """
    messages, prompt_sha = build_messages(system_prompt, user_template, case)
    payload = {"messages": messages, "max_tokens": FIXED_MAX_TOKENS,
               "stream": False,
               # Sampling keys below come verbatim from the manifest; the runner
               # adds no temperature/top_p of its own and no grammar whatsoever.
               **{k: v for k, v in config["generation"].items()
                   if k != "max_tokens"}}
    key = resume_key(benchmark_sha, config["model_sha256"], manifest_sha,
                     config["config_id"], case["id"])
    retry_context = retry_context or {
        "retry_mode": "initial", "retry_of_attempt": None,
        "retry_of_outcome": None,
    }
    if sampler is None:
        sampler = PeakSampler(None)
    sampler.start()
    attempts: list[dict] = []
    outcome = "transport_error"
    final_status: int | None = None
    final_body = ""
    final_error: str | None = None
    try:
        attempt_no = start_attempt - 1
        while True:
            attempt_no += 1
            started = time.perf_counter()
            status, body, error = client.post_json(api_url, payload)
            latency = time.perf_counter() - started
            handling = classify_http_status(status)  # status code only: safe pre-parse
            if handling == "rate_limited":
                disposition = "final"
            elif handling == "retryable" and attempt_no <= max_retries:
                disposition = "retry"
            else:
                disposition = "final"
            row = {"resume_key": key, "attempt": attempt_no, "disposition": disposition,
                   "benchmark_sha256": benchmark_sha, "manifest_sha256": manifest_sha,
                   "model_sha256": config["model_sha256"],
                   "config_id": config["config_id"], "case_id": case["id"],
                   "http_status": status, "response_body_exact": body, "error": error,
                   "latency_seconds": latency, "recorded_utc": utcnow(),
                   "retry_mode": retry_context["retry_mode"],
                   "retry_of_attempt": retry_context.get("retry_of_attempt"),
                   "retry_of_outcome": retry_context.get("retry_of_outcome")}
            persist_attempt(row)  # fsync BEFORE any parsing of `body`
            attempts.append(row)
            if handling == "rate_limited":
                outcome, final_status, final_body, final_error = "rate_limited", status, body, error
                break
            if disposition == "retry":
                continue
            outcome = finalize_outcome(status, error, body)
            final_status, final_body, final_error = status, body, error
            break
    finally:
        sampler_result = sampler.stop()
    return {"resume_key": key, "config_id": config["config_id"], "case_id": case["id"],
            "level": case["level"], "prompt_sha256": prompt_sha,
            "outcome": outcome, "attempts": attempts,
            "attempt_trace": [a["attempt"] for a in attempts],
            "retry_context": dict(retry_context),
            "final_status": final_status, "final_body": final_body,
            "final_error": final_error, "payload_keys": sorted(payload.keys()),
            "sampler": sampler_result}


def derive_parsed_row(*, final_info: dict, config: dict,
                      benchmark_sha: str, manifest_sha: str,
                      server_pid: int | None, derived_seq: int,
                      rerun: bool = False,
                      retry_context: dict | None = None) -> dict:
    """Derive evaluator-ready fields from ALREADY-PERSISTED raw attempts.

    Must only be called after every attempt row is fsynced. Produces the
    per-case parsed row: ``raw_response`` is the exact
    ``choices[0].message.content`` string (or ``""``), plus telemetry.
    No gold, no student text anywhere.
    """
    body = final_info["final_body"]
    transport = extract_transport(body)
    content, source = extract_message_content(body)
    total_latency = sum(a.get("latency_seconds", 0.0) for a in final_info["attempts"])
    memory = dict(final_info["sampler"])
    memory.update(sample_runner_rss())
    memory.update(sample_gpu())
    retry_context = retry_context or final_info.get("retry_context") or {
        "retry_mode": "initial", "retry_of_attempt": None,
        "retry_of_outcome": None,
    }
    return {
        "resume_key": final_info["resume_key"],
        "derived_seq": derived_seq,
        # Attempts are appended to RAW before this derived row. Evaluators use
        # this trace plus RAW to prove authorization before selecting the latest.
        "rerun": rerun,
        "attempt_trace": list(final_info.get("attempt_trace", [])),
        "retry_mode": retry_context["retry_mode"],
        "retry_of_attempt": retry_context.get("retry_of_attempt"),
        "retry_of_outcome": retry_context.get("retry_of_outcome"),
        "benchmark_sha256": benchmark_sha,
        "manifest_sha256": manifest_sha,
        "model_sha256": config["model_sha256"],
        "model_ref": config["model_ref"],
        "config_id": config["config_id"],
        "case_id": final_info["case_id"],
        "level": final_info["level"],
        "prompt_sha256": final_info["prompt_sha256"],
        "raw_response": content,
        "content_source": source,
        "transport": {
            "http_status": final_info["final_status"],
            "attempts": len(final_info["attempts"]),
            "outcome": final_info["outcome"],
            "error": final_info["final_error"],
            "finish_reason": transport["finish_reason"],
            "usage": transport["usage"],
            "body_json_valid": transport["body_json_valid"],
            "truncated": transport["truncated"],
            "completed": transport["completed"],
            "repetition_or_loop": has_repetition(content),
            "latency_seconds_total": total_latency,
            # TTFT is unavailable without streaming; null with a note, never zero.
            "ttft_seconds": None,
            "ttft_note": "Non-streaming mode; TTFT unavailable (null, not zero).",
        },
        "memory": memory,
        "offload": config["offload"],  # readiness snapshot, verbatim or null
        "server_pid": server_pid,      # observed own child pid, or null
        "payload_keys": final_info["payload_keys"],
        "free_format": True,
        "recorded_utc": utcnow(),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def raw_path_for(out_dir: Path, config_id: str) -> Path:
    return out_dir / "raw" / config_id / "attempts.jsonl"


def parsed_path_for(out_dir: Path, config_id: str) -> Path:
    return out_dir / "parsed" / config_id / "responses.jsonl"


def run_config(*, config: dict, cases: list[dict], system_prompt: str,
               user_template: str, benchmark_sha: str, manifest_sha: str,
               out_dir: Path, checkpoint_path: Path, summary_log_path,
               client: HttpClient, args, states: dict,
               reopen_failed: bool, server_factory=None) -> dict:
    """Run one configuration: start server, health-check, loop cases, stop it."""
    api_url = f"http://127.0.0.1:{config['port']}{args.api_path}"
    health_url = f"http://127.0.0.1:{config['port']}{args.health_path}"
    raw_path = raw_path_for(out_dir, config["config_id"])
    parsed_path = parsed_path_for(out_dir, config["config_id"])
    stats = {"config_id": config["config_id"], "completed": 0, "skipped": 0,
             "failed": 0, "retried": 0, "rate_limited": False,
             "outcomes": {}}
    factory = server_factory or (lambda argv, port, log: ManagedServer(
        argv, port, health_url, log, model_path=config["model_ref"],
        model_sha256=config["model_sha256"],
        model_size_bytes=config.get("model_size_bytes")))
    with factory(config["argv"], config["port"],
                 out_dir / "logs" / f"server_{config['config_id']}.log") as server:
        if not server.wait_healthy(client, args.health_timeout, args.health_interval):
            raise GateError(f"Server for {config['config_id']!r} failed its health "
                            f"check at {health_url}; refusing to send cases.")
        server_pid = getattr(server, "pid", None)
        for case in cases:
            key = resume_key(benchmark_sha, config["model_sha256"], manifest_sha,
                             config["config_id"], case["id"])
            known = states.get(key)
            retry_context = {"retry_mode": "initial", "retry_of_attempt": None,
                             "retry_of_outcome": None}
            if known is not None and known.get("state") == "done":
                if (reopen_failed
                        and outcome_manual_retry_eligible(known.get("outcome", ""))):
                    retry_context = {
                        "retry_mode": "retry_failed",
                        "retry_of_attempt": known.get("last_attempt"),
                        "retry_of_outcome": known.get("outcome"),
                    }
                else:
                    stats["skipped"] += 1
                    continue
            elif known is not None and known.get("state") == "pending":
                if known.get("outcome") != "rate_limited":
                    raise CheckpointMismatchError(
                        f"Pending key {key!r} has an unexpected recorded outcome.")
                # A prior HTTP 429 terminated the previous invocation. Starting
                # this invocation is an explicit manual resume after that stop;
                # HTTP 429 is still never retried inside one invocation.
                retry_context = {
                    "retry_mode": "rate_limit_resume",
                    "retry_of_attempt": known.get("last_attempt"),
                    "retry_of_outcome": known.get("outcome"),
                }
            persisted: list[dict] = []

            def persist_attempt(row: dict) -> None:
                append_jsonl_fsync(raw_path, row)
                persisted.append(row)

            sampler = PeakSampler(server_pid)
            try:
                final_info = run_single_case(
                    client=client, api_url=api_url, config=config, case=case,
                    system_prompt=system_prompt, user_template=user_template,
                    benchmark_sha=benchmark_sha, manifest_sha=manifest_sha,
                    max_retries=args.max_retries, persist_attempt=persist_attempt,
                    sampler=sampler,
                    start_attempt=max_attempt_for_key(raw_path, key) + 1,
                    retry_context=retry_context)
            except RateLimitedError:
                raise
            # Raw attempts are fsynced; ONLY NOW derive + persist the parsed row.
            parsed = derive_parsed_row(final_info=final_info, config=config,
                                       benchmark_sha=benchmark_sha,
                                       manifest_sha=manifest_sha, server_pid=server_pid,
                                       derived_seq=count_jsonl_lines(parsed_path) + 1,
                                       rerun=retry_context["retry_mode"] != "initial",
                                       retry_context=retry_context)
            append_jsonl_fsync(parsed_path, parsed)
            outcome = final_info["outcome"]
            stats["outcomes"][outcome] = stats["outcomes"].get(outcome, 0) + 1
            if len(persisted) > 1:
                stats["retried"] += 1
            if outcome == "ok":
                stats["completed"] += 1
            else:
                stats["failed"] += 1
            if outcome == "rate_limited":
                states[key] = {"state": "pending", "outcome": outcome,
                               "attempts": len(persisted),
                               "last_attempt": final_info["attempt_trace"][-1],
                               "config_id": config["config_id"], "case_id": case["id"]}
                stats["rate_limited"] = True
                write_checkpoint_atomic(checkpoint_path, benchmark_sha, manifest_sha, states)
                raise RateLimitedError(
                    f"HTTP 429 while running {config['config_id']}/{case['id']}; "
                    "stopping the whole run immediately with no retry. "
                    "Completed rows are preserved; resume manually later.")
            states[key] = {"state": "done", "outcome": outcome,
                           "attempts": len(persisted),
                           "last_attempt": final_info["attempt_trace"][-1],
                           "config_id": config["config_id"], "case_id": case["id"]}
            write_checkpoint_atomic(checkpoint_path, benchmark_sha, manifest_sha, states)
    return stats


def execute(args, *, client_factory=None, server_factory=None) -> int:
    """Shared main-run path for real execution and dry-run planning."""
    benchmark_path = Path(args.benchmark)
    manifest_path = Path(args.manifest)
    # Gate 1: authorization ALWAYS (dry-run and selections included).
    benchmark_sha = require_authorization(
        benchmark_path, args.approved_benchmark_sha256, args.authorize_execution)
    benchmark_data, loaded_benchmark_sha = load_json_snapshot(benchmark_path)
    if loaded_benchmark_sha != benchmark_sha:
        raise AuthorizationError("Benchmark changed after authorization check; refusing inference.")
    meta, cases = validate_benchmark(benchmark_data)  # Gate 2
    manifest_data, manifest_sha = load_json_snapshot(manifest_path)
    configs = validate_manifest(manifest_data)  # Gate 3
    check_readiness(configs, load_json(Path(args.readiness_report)),  # Gate 4
                    manifest_sha)
    check_validation(load_json(Path(args.validation_report)),  # Gate 5
                     args.approved_benchmark_sha256)
    plan = select_plan(cases, configs, args.config, args.case)
    expected = len(plan)
    print(json.dumps({"mode": "dry-run" if args.dry_run else "run",
                      "benchmark_id": meta.get("benchmark_id"),
                      "benchmark_sha256": benchmark_sha,
                      "manifest_sha256": manifest_sha,
                      "configs": len({c["config_id"] for c, _ in plan}),
                      "cases": len({c2["id"] for _, c2 in plan}),
                      "planned_rows": expected,
                      "full_matrix_rows": EXPECTED_TOTAL_ROWS,
                      "selection": bool(args.config or args.case)}))
    if args.dry_run:
        # No server processes, no network: gates + plan only.
        return EXIT_OK

    out_dir = Path(args.out_dir)
    checkpoint_path = out_dir / "checkpoint.json"
    summary_path = out_dir / "reports" / "run_summary.json"
    configs_by_id = {c["config_id"]: c for c in configs}
    case_ids = {c["id"] for c in cases}
    # RAW authority: replay completions from raw attempt files first.
    raw_paths = [raw_path_for(out_dir, c["config_id"]) for c in configs]
    replayed = replay_raw_authority(raw_paths, benchmark_sha, manifest_sha,
                                    configs_by_id, case_ids)
    cached = load_checkpoint(checkpoint_path, benchmark_sha, manifest_sha)
    cached_states = cached.get("states", {})
    for key, entry in cached_states.items():
        if not isinstance(entry, dict) or entry.get("state") != "done":
            continue
        if key not in replayed or replayed[key].get("state") != "done":
            raise CheckpointMismatchError(
                f"Checkpoint claims {key!r} as done but RAW holds no final "
                "attempt for it; refusing (raw is the authority).")
    for key, entry in cached_states.items():
        if isinstance(entry, dict) and entry.get("state") == "pending":
            if key not in replayed:
                raise CheckpointMismatchError(
                    f"Checkpoint claims {key!r} is pending but RAW has no attempt "
                    "evidence; refusing (raw is the authority).")
    states: dict = {key: dict(info) for key, info in replayed.items()}
    write_checkpoint_atomic(checkpoint_path, benchmark_sha, manifest_sha, states)

    client = (client_factory or (lambda: HttpClient(args.request_timeout)))()
    per_config: list[dict] = []
    started_utc = utcnow()
    rate_limited = False
    # One configuration loaded at a time; configs run strictly sequentially.
    active_configs = [c for c in configs
                      if args.config is None or c["config_id"] in set(args.config)]
    wanted_cases = [c for c in cases
                    if args.case is None or c["id"] in set(args.case)]
    try:
        for config in active_configs:
            stats = run_config(config=config, cases=wanted_cases,
                               system_prompt=benchmark_data["system_prompt"],
                               user_template=benchmark_data["user_prompt_template"],
                               benchmark_sha=benchmark_sha, manifest_sha=manifest_sha,
                               out_dir=out_dir, checkpoint_path=checkpoint_path,
                               summary_log_path=None,
                               client=client, args=args, states=states,
                               reopen_failed=args.retry_failed,
                               server_factory=server_factory)
            per_config.append(stats)
            print(json.dumps({"config": config["config_id"], **stats}))
    except RateLimitedError as exc:
        rate_limited = True
        print(json.dumps({"fatal": "rate_limited", "detail": str(exc)}))
    summary = {"benchmark_id": meta.get("benchmark_id"),
               "benchmark_sha256": benchmark_sha, "manifest_sha256": manifest_sha,
               "started_utc": started_utc, "completed_utc": utcnow(),
               "planned_rows": expected, "full_matrix_rows": EXPECTED_TOTAL_ROWS,
               "rate_limited_stop": rate_limited,
               "retry_failed_flag": bool(args.retry_failed),
               "per_config": per_config,
               "completed_rows": sum(s["completed"] for s in per_config),
               "note": ("Transport records only: exact bodies, HTTP/error, usage, "
                        "finish_reason, latency, server peak RSS + device GPU. "
                        "No gold, no student text, no scores in this summary. "
                        "Manual retries append exact RAW attempts and traceable "
                        "parsed rows. Evaluators select by highest final attempt "
                        "only after validating the retry chain against RAW.")}
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    return EXIT_RATE_LIMITED if rate_limited else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default=str(RUNNER_DIR / "benchmark_development_120_v1.json"))
    parser.add_argument("--manifest", default=str(RUNNER_DIR / "manifests" / "experiment_manifest_120.json"))
    parser.add_argument("--readiness-report", default=str(RUNNER_DIR / "llama_cpp_readiness_report.json"))
    parser.add_argument("--validation-report",
                        default=str(RUNNER_DIR / "benchmark_120" / "strict_validation_120.json"))
    parser.add_argument("--out-dir", default=str(RUNNER_DIR / "results_120"))
    parser.add_argument("--authorize-execution", action="store_true",
                        help="Deliberate opt-in; required for ANY run incl. dry-run.")
    parser.add_argument("--approved-benchmark-sha256", required=True,
                        help="Exact approved bytes of the benchmark file (64 hex).")
    parser.add_argument("--config", action="append", default=None,
                        help="Restrict to config id(s); gates still fully apply.")
    parser.add_argument("--case", action="append", default=None,
                        help="Restrict to case id(s); gates still fully apply.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Gates + plan only; starts no server, opens no connections.")
    parser.add_argument("--retry-failed", action="store_true",
                        help="On manual resume ONLY, re-run keys whose recorded outcome "
                             "is a failed transport/5xx outcome. Nothing is retried "
                             "silently; semantic failures are never retried by this flag.")
    parser.add_argument("--api-path", default="/v1/chat/completions")
    parser.add_argument("--health-path", default="/health")
    parser.add_argument("--request-timeout", type=float, default=300.0)
    parser.add_argument("--health-timeout", type=float, default=180.0)
    parser.add_argument("--health-interval", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=2,
                        help="Bounded retries for TECHNICAL failures only (connection "
                             "errors, timeouts, HTTP 5xx). Semantic outcomes and "
                             "HTTP 429 are never retried.")
    # Deliberately no sampling/temperature/top_p/seed flags: generation comes
    # verbatim from the manifest and is never tuned from outputs.
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return execute(args)
    except AuthorizationError as exc:
        print(json.dumps({"fatal": "authorization", "detail": str(exc)}))
        return EXIT_GATE
    except (GateError, CheckpointMismatchError) as exc:
        print(json.dumps({"fatal": "gate", "detail": str(exc)}))
        return EXIT_GATE
    except RateLimitedError as exc:
        print(json.dumps({"fatal": "rate_limited", "detail": str(exc)}))
        return EXIT_RATE_LIMITED


if __name__ == "__main__":
    raise SystemExit(main())
