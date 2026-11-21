"""Synthetic tests for read-only offline web-export validation."""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate_responses_v2 as v2
import human_review_v2 as human
import prepare_human_review_v2 as prep
import report_execution_results as reporting
import validate_human_review_web_export as web_export


BLIND_ID = "br-synthetic-0001"


def make_fixture(root: Path, *, assessable: bool = True, judgment: bool | None = True):
    row = {
        "scope": "results_120",
        "benchmark_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "response_sha256": hashlib.sha256(b"Synthetic response.").hexdigest(),
        "config_id": "SYNTHETIC_CONFIG_PRIVATE",
        "case_id": "SYNTHETIC_CASE_PRIVATE",
        "condition": "incorrect",
        "level": "A1",
        "task": "Synthetic task.",
        "student_text": "Synthetic student text.",
    }
    visible = {
        "blind_output_id": BLIND_ID,
        "level": row["level"],
        "task": row["task"],
        "student_text": row["student_text"],
        "response_text": "Synthetic response.",
    }
    crosswalk_entry = {
        "blind_output_id": BLIND_ID,
        **{key: row[key] for key in human.IDENTITY_FIELDS},
        "context_sha256": prep.context_digest(visible),
    }
    packet_path = root / "reviewer_materials" / "blind_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text(json.dumps({"items": [visible]}, ensure_ascii=False), encoding="utf-8")
    crosswalk_path = root / "coordinator_only" / "identity_crosswalk.json"
    crosswalk_path.parent.mkdir(parents=True)
    crosswalk_path.write_text(json.dumps({
        "schema_version": "human_review_v2.crosswalk/1.0",
        "identity_fields": list(human.IDENTITY_FIELDS),
        "items": [crosswalk_entry],
    }, ensure_ascii=False), encoding="utf-8")
    packet_record = {
        "files": [
            {"path": reporting._relative(path), "sha256": reporting.sha256_file(path)}
            for path in (crosswalk_path, packet_path)
        ]
    }
    (crosswalk_path.parent / "packet_record.json").write_text(
        json.dumps(packet_record, ensure_ascii=False), encoding="utf-8")

    human_says_control = assessable and judgment is False
    review = {
        "blind_output_id": BLIND_ID,
        "schema_version": human.HUMAN_REVIEW_SCHEMA_VERSION,
        "reviewer_id": "SYNTHETIC_FIXTURE_ONLY",
        "review_date": "2026-10-11",
        "response_assessable": assessable,
        "rationale": "Synthetic test record, not a human benchmark evaluation.",
        "meaning_preserved": True if assessable else "NA",
        "explanations_ok": True if assessable else "NA",
        "verdict": "CORRECT" if assessable else "INVALID_CASE",
    }
    for criterion in human.CRITERIA:
        if not assessable:
            review[criterion] = "NA"
        elif human_says_control and criterion in ("detection", "correction"):
            review[criterion] = "NA"
        elif human_says_control and criterion == "clean_text_handling":
            review[criterion] = 2
        elif not human_says_control and criterion == "clean_text_handling":
            review[criterion] = "NA"
        else:
            review[criterion] = 2
    reviews_path = root / "reviews.jsonl"
    reviews_raw = (json.dumps(review, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    reviews_path.write_bytes(reviews_raw)
    metadata_path = root / "export_metadata.json"
    metadata = {
        "schema_version": web_export.EXPORT_SCHEMA_VERSION,
        "packet_sha256": reporting.sha256_file(packet_path),
        "reviews_sha256": hashlib.sha256(reviews_raw).hexdigest(),
        "reviews_filename": reviews_path.name,
        "reviews_byte_count": len(reviews_raw),
        "record_count": 1,
        "exported_at": "2026-10-11T12:00:00Z",
        "original_judgments": [{
            "blind_output_id": BLIND_ID,
            "original_has_errors": judgment,
        }],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return row, review, reviews_path, metadata_path, crosswalk_path, packet_path


class WebExportValidationTests(unittest.TestCase):
    def run_fixture(self, root: Path, **kwargs):
        row, review, reviews, metadata, crosswalk, packet = make_fixture(root, **kwargs)
        with patch.object(prep, "load_bound_rows", return_value=(None, [row])):
            result = web_export.validate_export(reviews, metadata, crosswalk)
        return result, review, (reviews, metadata, crosswalk, packet)

    def test_valid_export_is_read_only_and_emits_only_blind_identities(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            root = Path(tmp)
            result, _review, paths = self.run_fixture(root)
            before = {path: path.read_bytes() for path in paths}
            # Repeat with a non-mutating wrapper around the canonical validator.
            row = {
                "scope": "results_120", "benchmark_sha256": "a" * 64,
                "manifest_sha256": "b" * 64,
                "response_sha256": hashlib.sha256(b"Synthetic response.").hexdigest(),
                "config_id": "SYNTHETIC_CONFIG_PRIVATE", "case_id": "SYNTHETIC_CASE_PRIVATE",
                "condition": "incorrect", "level": "A1", "task": "Synthetic task.",
                "student_text": "Synthetic student text.",
            }
            original_validate = prep.validate_records

            def checked_validate(records, rows, crosswalk):
                snapshot = copy.deepcopy(records)
                accepted = original_validate(records, rows, crosswalk)
                self.assertEqual(records, snapshot)
                return accepted

            with patch.object(prep, "load_bound_rows", return_value=(None, [row])), \
                    patch.object(prep, "validate_records", side_effect=checked_validate):
                result = web_export.validate_export(paths[0], paths[1], paths[2])

            self.assertEqual(result["status"], "VALID")
            self.assertEqual(result["compared_original_judgments"], 1)
            self.assertEqual(result["discrepancy_blind_output_ids"], [])
            self.assertEqual(result["reviewed_blind_output_ids"], [BLIND_ID])
            self.assertNotIn("config_id", json.dumps(result))
            self.assertNotIn("case_id", json.dumps(result))
            self.assertNotIn("SYNTHETIC_CONFIG_PRIVATE", json.dumps(result))
            self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_auxiliary_judgment_discrepancy_is_reported_with_blind_id(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            row, review, reviews, metadata, crosswalk, _packet = make_fixture(
                Path(tmp), judgment=False)
            human_record = {key: value for key, value in review.items() if key != "blind_output_id"}
            human_record.update({key: row[key] for key in human.IDENTITY_FIELDS})
            # The rubric anchors are internally valid under the reviewer's
            # control judgment even though the trusted row is an error case.
            self.assertEqual(human.validate_human_record(
                human_record,
                {key: row[key] for key in human.IDENTITY_FIELDS},
                "correct",
            ), [])
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])), \
                    patch.object(prep, "validate_records", side_effect=AssertionError(
                        "gold-conditioned validation must follow the comparison")) as validator:
                result = web_export.validate_export(reviews, metadata, crosswalk)
            validator.assert_not_called()
        self.assertEqual(result["status"], "DISCREPANCIES")
        self.assertEqual(result["discrepancy_blind_output_ids"], [BLIND_ID])

    def test_null_judgment_is_allowed_only_for_unassessable_and_is_not_compared(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            result, _review, _paths = self.run_fixture(Path(tmp), assessable=False, judgment=None)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["compared_original_judgments"], 0)
        self.assertEqual(result["unassessable_blind_output_ids"], [BLIND_ID])
        self.assertEqual(result["discrepancy_blind_output_ids"], [])

    def test_null_judgment_for_assessable_review_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            row, _review, reviews, metadata, crosswalk, _packet = make_fixture(
                Path(tmp), assessable=True, judgment=None)
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])):
                with self.assertRaisesRegex(web_export.ExportValidationError, "invalid_original_judgments"):
                    web_export.validate_export(reviews, metadata, crosswalk)

    def test_exported_ids_must_exactly_cover_completed_review_ids(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            row, _review, reviews, metadata, crosswalk, _packet = make_fixture(Path(tmp))
            data = json.loads(metadata.read_text(encoding="utf-8"))
            data["original_judgments"] = []
            metadata.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])):
                with self.assertRaisesRegex(web_export.ExportValidationError, "original_judgment_coverage_mismatch"):
                    web_export.validate_export(reviews, metadata, crosswalk)

    def test_duplicate_jsonl_blind_id_is_rejected_even_with_different_reviewer(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            root = Path(tmp)
            row, review, reviews, metadata, crosswalk, _packet = make_fixture(root)
            second = dict(review)
            second["reviewer_id"] = "SECOND_SYNTHETIC_FIXTURE"
            reviews_raw = reviews.read_bytes() + (
                json.dumps(second, ensure_ascii=False, allow_nan=False) + "\n"
            ).encode("utf-8")
            reviews.write_bytes(reviews_raw)
            data = json.loads(metadata.read_text(encoding="utf-8"))
            data["reviews_sha256"] = hashlib.sha256(reviews_raw).hexdigest()
            data["reviews_byte_count"] = len(reviews_raw)
            data["record_count"] = 2
            metadata.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])):
                with self.assertRaisesRegex(web_export.ExportValidationError, "duplicate_blind_output_id"):
                    web_export.validate_export(reviews, metadata, crosswalk)

    def test_reviews_hash_and_packet_hash_are_bound_to_metadata(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            row, _review, reviews, metadata, crosswalk, _packet = make_fixture(Path(tmp))
            data = json.loads(metadata.read_text(encoding="utf-8"))
            data["reviews_sha256"] = "0" * 64
            metadata.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])):
                with self.assertRaisesRegex(web_export.ExportValidationError, "artifact_integrity_mismatch"):
                    web_export.validate_export(reviews, metadata, crosswalk)

    def test_packet_metadata_must_match_packet_record_bound_blind_packet(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            row, _review, reviews, metadata, crosswalk, _packet = make_fixture(Path(tmp))
            data = json.loads(metadata.read_text(encoding="utf-8"))
            data["packet_sha256"] = "0" * 64
            metadata.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])):
                with self.assertRaisesRegex(web_export.ExportValidationError, "artifact_integrity_mismatch"):
                    web_export.validate_export(reviews, metadata, crosswalk)

    def test_unbound_changed_blind_packet_fails_crosswalk_integrity(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            row, _review, reviews, metadata, crosswalk, packet = make_fixture(Path(tmp))
            packet.write_text('{"items":[]}', encoding="utf-8")
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])):
                with self.assertRaisesRegex(web_export.ExportValidationError, "crosswalk_integrity_mismatch"):
                    web_export.validate_export(reviews, metadata, crosswalk)

    def test_cli_requires_explicit_crosswalk_and_reports_discrepancy_ids_only(self):
        with tempfile.TemporaryDirectory(prefix="web-export-synthetic-") as tmp:
            root = Path(tmp)
            row, _review, reviews, metadata, crosswalk, _packet = make_fixture(root, judgment=False)
            with self.assertRaises(SystemExit):
                web_export.main(["--reviews", str(reviews), "--metadata", str(metadata)])

            output = io.StringIO()
            with patch.object(prep, "load_bound_rows", return_value=(None, [row])), \
                    redirect_stdout(output):
                code = web_export.main([
                    "--reviews", str(reviews), "--metadata", str(metadata),
                    "--crosswalk", str(crosswalk),
                ])
            self.assertEqual(code, 1)
            printed = output.getvalue()
            self.assertIn(BLIND_ID, printed)
            self.assertNotIn("SYNTHETIC_CONFIG_PRIVATE", printed)
            self.assertNotIn("SYNTHETIC_CASE_PRIVATE", printed)


if __name__ == "__main__":
    unittest.main()
