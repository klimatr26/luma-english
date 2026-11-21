"""Fail-closed authorization helpers; importing this module never runs inference."""

import hashlib
from pathlib import Path


class AuthorizationError(ValueError):
    """The exact frozen development benchmark has not been authorized."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_authorization(benchmark_path, approved_sha256, authorize_execution):
    """Require both deliberate authorization and the exact approved file bytes.

    This is an execution guard, not evidence that a human has approved the gold.
    Readiness/validation must be checked independently by the calling runner.
    """
    if authorize_execution is not True:
        raise AuthorizationError("Main inference disabled: explicit authorization flag required.")
    if not isinstance(approved_sha256, str) or len(approved_sha256) != 64:
        raise AuthorizationError("The approved benchmark SHA-256 is required.")
    if any(char not in "0123456789abcdef" for char in approved_sha256):
        raise AuthorizationError("Approved SHA-256 must be 64 lowercase hexadecimal characters.")
    actual = sha256_file(benchmark_path)
    if actual != approved_sha256:
        raise AuthorizationError("Benchmark bytes differ from the approved SHA-256; refusing inference.")
    return actual
