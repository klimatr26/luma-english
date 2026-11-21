"""Synthetic amendment provenance tests, without importing any real ratings."""
import copy
import unittest

from apply_human_review_clarifications import apply_changes


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        self.backup = {"entries": [
            {"blind_output_id": "synthetic-1", "completed": True, "original_has_errors": True,
             "review": {"reviewer_id": "SYNTHETIC_ONLY", "rationale": "Original fixture comment", "review_date": "2026-10-19", "detection": 2, "clean_text_handling": "NA"}},
            {"blind_output_id": "synthetic-2", "completed": True, "original_has_errors": False,
             "review": {"reviewer_id": "SYNTHETIC_ONLY", "rationale": "Must remain unchanged"}}]}
        self.ledger = {"schema_version": "human_review_clarifications/1.0", "status": "USER_CONFIRMED",
                       "source_backup_sha256": "a"*64, "reviewer_id": "SYNTHETIC_ONLY",
                       "confirmation": {"user_reply_verbatim": "Synthetic confirmation, not a human review"},
                       "changes": [{"blind_output_id": "synthetic-1", "patches": [
                           {"field": "original_has_errors", "before": True, "after": False},
                           {"field": "review.detection", "before": 2, "after": "NA"},
                           {"field": "review.clean_text_handling", "before": "NA", "after": 2}]}]}

    def test_only_confirmed_fields_change_and_source_is_not_mutated(self):
        saved = copy.deepcopy(self.backup)
        output = apply_changes(self.backup, self.ledger, "a"*64)
        self.assertEqual(self.backup, saved)
        self.assertEqual(output["entries"][1], saved["entries"][1])
        self.assertEqual(output["entries"][0]["review"]["review_date"], "2026-10-19")
        self.assertEqual(output["entries"][0]["review"]["rationale"], "Original fixture comment")
        self.assertEqual(output["entries"][0]["review"]["clean_text_handling"], 2)
        self.assertFalse(output["entries"][0]["original_has_errors"])

    def test_missing_confirmation_wrong_hash_or_wrong_reviewer_rejected(self):
        for field, value in (("status", "PROPOSED"), ("source_backup_sha256", "b"*64),
                             ("reviewer_id", "another-reviewer"), ("confirmation", {})):
            ledger = copy.deepcopy(self.ledger)
            ledger[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                apply_changes(self.backup, ledger, "a"*64)

    def test_stale_old_value_and_bool_integer_confusion_rejected(self):
        for before in (False, 1):
            ledger = copy.deepcopy(self.ledger)
            ledger["changes"][0]["patches"][0]["before"] = before
            with self.subTest(before=before), self.assertRaises(ValueError):
                apply_changes(self.backup, ledger, "a"*64)

    def test_identity_override_unknown_and_duplicate_patches_rejected(self):
        for kind in ("private-field", "unknown-id", "duplicate-id", "duplicate-field"):
            ledger = copy.deepcopy(self.ledger)
            if kind == "private-field":
                ledger["changes"][0]["patches"][0]["field"] = "review.reviewer_id"
            elif kind == "unknown-id":
                ledger["changes"][0]["blind_output_id"] = "unknown"
            elif kind == "duplicate-id":
                ledger["changes"].append(copy.deepcopy(ledger["changes"][0]))
            else:
                ledger["changes"][0]["patches"].append(copy.deepcopy(ledger["changes"][0]["patches"][0]))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                apply_changes(self.backup, ledger, "a"*64)


if __name__ == "__main__":
    unittest.main()
