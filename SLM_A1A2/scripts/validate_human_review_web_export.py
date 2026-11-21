"""Validate an offline human-review web export without importing or writing it.

The validator binds the exported JSONL to its metadata and to the exact blind
packet recorded beside the coordinator crosswalk. It reuses the v2 review
contract, but never creates a human layer or changes evaluation artifacts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

import evaluate_benchmark_120 as frozen
import human_review_v2 as human
import prepare_human_review_v2 as prep


EXPORT_SCHEMA_VERSION = "human_review_web.export/1.0"
METADATA_FIELDS = frozenset({
    "schema_version",
    "packet_sha256",
    "reviews_sha256",
    "reviews_filename",
    "reviews_byte_count",
    "record_count",
    "exported_at",
    "original_judgments",
})
HEX_SHA256 = frozenset("0123456789abcdef")


class ExportValidationError(ValueError):
    """A validation error with a safe, non-identifying CLI code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in HEX_SHA256 for char in value))


def _load_reviews(raw: bytes) -> list[dict[str, Any]]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExportValidationError("invalid_reviews_jsonl") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(decoded.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = frozen.strict_json_loads(line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ExportValidationError("invalid_reviews_jsonl") from exc
        if not isinstance(record, dict):
            raise ExportValidationError("invalid_reviews_jsonl")
        records.append(record)
    return records


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = frozen.strict_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ExportValidationError("invalid_metadata") from exc
    if not isinstance(value, dict) or set(value) != METADATA_FIELDS:
        raise ExportValidationError("invalid_metadata")
    return value


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _validate_metadata(
    metadata: dict[str, Any],
    reviews_path: Path,
    reviews_raw: bytes,
    records: list[dict[str, Any]],
    packet_sha256: str,
) -> list[dict[str, Any]]:
    if metadata.get("schema_version") != EXPORT_SCHEMA_VERSION:
        raise ExportValidationError("invalid_metadata")
    if not _is_sha256(metadata.get("packet_sha256")) or metadata["packet_sha256"] != packet_sha256:
        raise ExportValidationError("artifact_integrity_mismatch")
    if not _is_sha256(metadata.get("reviews_sha256")) or metadata["reviews_sha256"] != _sha256(reviews_raw):
        raise ExportValidationError("artifact_integrity_mismatch")
    if metadata.get("reviews_filename") != reviews_path.name:
        raise ExportValidationError("artifact_integrity_mismatch")
    if (type(metadata.get("reviews_byte_count")) is not int
            or metadata["reviews_byte_count"] != len(reviews_raw)):
        raise ExportValidationError("artifact_integrity_mismatch")
    if (type(metadata.get("record_count")) is not int
            or metadata["record_count"] != len(records)):
        raise ExportValidationError("artifact_integrity_mismatch")
    if not _valid_utc_timestamp(metadata.get("exported_at")):
        raise ExportValidationError("invalid_metadata")

    judgments = metadata.get("original_judgments")
    if not isinstance(judgments, list):
        raise ExportValidationError("invalid_metadata")
    for item in judgments:
        if (not isinstance(item, dict)
                or set(item) != {"blind_output_id", "original_has_errors"}
                or not isinstance(item.get("blind_output_id"), str)
                or not item["blind_output_id"].strip()
                or (item["original_has_errors"] is not None
                    and type(item["original_has_errors"]) is not bool)):
            raise ExportValidationError("invalid_metadata")
    return judgments


def _packet_path_from_coordinator_record(crosswalk_path: Path) -> Path:
    """Resolve blind_packet exactly as the v2 importer does."""
    try:
        record = prep.reporting.load_json(crosswalk_path.parent / "packet_record.json")
        files = record["files"]
        if not isinstance(files, list):
            raise ValueError("invalid packet record")
        matches = [entry for entry in files
                   if isinstance(entry, dict)
                   and Path(entry.get("path", "")).name == "blind_packet.json"]
        if len(matches) != 1 or not isinstance(matches[0].get("path"), str):
            raise ValueError("invalid packet binding")
        return prep.reporting.REPO_DIR / matches[0]["path"]
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ExportValidationError("crosswalk_integrity_mismatch") from exc


def _load_bound_crosswalk_and_packet(crosswalk_path: Path) -> tuple[dict[str, Any], Path, str]:
    try:
        # Reuse the importer’s checks for the crosswalk’s packet_record binding,
        # exact packet hash, and reviewer-visible response/context digests.
        crosswalk = prep.load_verified_crosswalk(crosswalk_path)
        packet_path = _packet_path_from_coordinator_record(crosswalk_path)
        packet_raw = packet_path.read_bytes()
    except ExportValidationError:
        raise
    except Exception as exc:
        raise ExportValidationError("crosswalk_integrity_mismatch") from exc

    if not isinstance(crosswalk, dict) or not isinstance(crosswalk.get("items"), list):
        raise ExportValidationError("crosswalk_integrity_mismatch")
    return crosswalk, packet_path, _sha256(packet_raw)


def _trusted_rows_by_blind_id(
    crosswalk: dict[str, Any], rows: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    entries_by_id: dict[str, dict[str, Any]] = {}
    rows_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        pair = (row.get("config_id"), row.get("case_id"))
        if not all(isinstance(part, str) and part for part in pair):
            raise ExportValidationError("trusted_identity_mismatch")
        if pair in rows_by_pair:
            raise ExportValidationError("trusted_identity_mismatch")
        rows_by_pair[pair] = row

    rows_by_blind_id: dict[str, dict[str, Any]] = {}
    for entry in crosswalk["items"]:
        if not isinstance(entry, dict):
            raise ExportValidationError("crosswalk_integrity_mismatch")
        blind_id = entry.get("blind_output_id")
        if not isinstance(blind_id, str) or not blind_id or blind_id in entries_by_id:
            raise ExportValidationError("crosswalk_integrity_mismatch")
        entries_by_id[blind_id] = entry

        pair = (entry.get("config_id"), entry.get("case_id"))
        if not all(isinstance(part, str) and part for part in pair):
            raise ExportValidationError("crosswalk_integrity_mismatch")
        row = rows_by_pair.get(pair)
        if row is None:
            raise ExportValidationError("trusted_identity_mismatch")
        for field in human.IDENTITY_FIELDS:
            if entry.get(field) != row.get(field):
                raise ExportValidationError("trusted_identity_mismatch")
        if row.get("condition") not in ("correct", "incorrect"):
            raise ExportValidationError("trusted_identity_mismatch")
        rows_by_blind_id[blind_id] = row
    return entries_by_id, rows_by_blind_id


def validate_export(reviews_path: Path, metadata_path: Path, crosswalk_path: Path) -> dict[str, Any]:
    """Validate one web export and return a distribution-safe summary.

    The returned object includes blind IDs only. No path, reviewer identity,
    configuration, case, response text, or condition label is emitted.
    """
    reviews_path = Path(reviews_path)
    metadata_path = Path(metadata_path)
    crosswalk_path = Path(crosswalk_path)
    try:
        reviews_raw = reviews_path.read_bytes()
    except OSError as exc:
        raise ExportValidationError("invalid_reviews_jsonl") from exc
    records = _load_reviews(reviews_raw)
    metadata = _load_metadata(metadata_path)
    crosswalk, _packet_path, packet_sha256 = _load_bound_crosswalk_and_packet(crosswalk_path)
    judgments = _validate_metadata(metadata, reviews_path, reviews_raw, records, packet_sha256)

    if (crosswalk.get("schema_version") != "human_review_v2.crosswalk/1.0"
            or crosswalk.get("identity_fields") != list(human.IDENTITY_FIELDS)
            or any(not isinstance(entry, dict) or not isinstance(entry.get("scope"), str)
                   for entry in crosswalk["items"])):
        raise ExportValidationError("crosswalk_integrity_mismatch")
    scope_values = {entry["scope"] for entry in crosswalk["items"]}
    if len(scope_values) != 1 or not isinstance(next(iter(scope_values), None), str):
        raise ExportValidationError("crosswalk_integrity_mismatch")
    scope = next(iter(scope_values))
    if scope not in prep.v2.SCOPES:
        raise ExportValidationError("crosswalk_integrity_mismatch")
    try:
        _inventory, rows = prep.load_bound_rows(scope)
    except Exception as exc:
        raise ExportValidationError("trusted_source_validation_failed") from exc

    entries_by_id, rows_by_blind_id = _trusted_rows_by_blind_id(crosswalk, rows)
    review_ids: set[str] = set()
    assessability: dict[str, bool] = {}
    for record in records:
        blind_id = record.get("blind_output_id")
        if not isinstance(blind_id, str) or blind_id not in entries_by_id:
            raise ExportValidationError("invalid_review_identity")
        if blind_id in review_ids:
            # This offline export format has one completed review per blind
            # output; reviewer_id cannot make duplicate rows unambiguous.
            raise ExportValidationError("duplicate_blind_output_id")
        review_ids.add(blind_id)
        value = record.get("response_assessable")
        if type(value) is not bool:
            raise ExportValidationError("invalid_review_records")
        assessability[blind_id] = value

    judgment_by_id: dict[str, bool | None] = {}
    for item in judgments:
        blind_id = item["blind_output_id"]
        if blind_id in judgment_by_id or blind_id not in entries_by_id:
            raise ExportValidationError("invalid_original_judgments")
        judgment_by_id[blind_id] = item["original_has_errors"]

    if set(judgment_by_id) != review_ids:
        raise ExportValidationError("original_judgment_coverage_mismatch")

    discrepancies: list[str] = []
    unassessable: list[str] = []
    compared = 0
    for blind_id, judgment in judgment_by_id.items():
        is_assessable = assessability[blind_id]
        if judgment is None:
            if is_assessable:
                raise ExportValidationError("invalid_original_judgments")
            unassessable.append(blind_id)
            continue
        expected_has_errors = rows_by_blind_id[blind_id]["condition"] == "incorrect"
        compared += 1
        if judgment is not expected_has_errors:
            discrepancies.append(blind_id)

    # A disagreement is the result to report. In particular, a record may
    # have been anchored to the reviewer's control judgment while the trusted
    # condition says incorrect; running the gold-conditioned v2 validator
    # first would hide that disagreement as a generic schema error.
    if discrepancies:
        return {
            "status": "DISCREPANCIES",
            "record_count": len(records),
            "reviewed_blind_output_ids": sorted(review_ids),
            "compared_original_judgments": compared,
            "unassessable_blind_output_ids": sorted(unassessable),
            "discrepancy_blind_output_ids": sorted(discrepancies),
        }

    try:
        # The importer clones each record before hydrating its trusted identity.
        # This call validates v2 record rules without performing its write step.
        prep.validate_records(records, rows, crosswalk)
    except Exception as exc:
        raise ExportValidationError("invalid_review_records") from exc

    return {
        "status": "VALID",
        "record_count": len(records),
        "reviewed_blind_output_ids": sorted(review_ids),
        "compared_original_judgments": compared,
        "unassessable_blind_output_ids": sorted(unassessable),
        "discrepancy_blind_output_ids": sorted(discrepancies),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, required=True, help="Exported review JSONL")
    parser.add_argument("--metadata", type=Path, required=True, help="Export metadata JSON")
    parser.add_argument("--crosswalk", type=Path, required=True,
                        help="Coordinator-only identity crosswalk (required explicitly)")
    args = parser.parse_args(argv)
    try:
        report = validate_export(args.reviews, args.metadata, args.crosswalk)
    except ExportValidationError as exc:
        print(json.dumps({"status": "INVALID", "error": exc.code}, ensure_ascii=False))
        return 1
    except Exception:
        # Keep arbitrary local paths and private identity details out of stdout.
        print(json.dumps({"status": "INVALID", "error": "validation_failed"}, ensure_ascii=False))
        return 1

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 1 if report["status"] == "DISCREPANCIES" else 0


if __name__ == "__main__":
    raise SystemExit(main())
