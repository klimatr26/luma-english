"""Human import fixtures; these are not real human judgments."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import human_review_v2 as human
import prepare_human_review_v2 as prep


def fixtures():
    row = {'scope': 'synthetic', 'benchmark_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64,
           'response_sha256': 'c' * 64, 'config_id': 'synthetic_config', 'case_id': 'synthetic_case',
           'condition': 'incorrect', 'level': 'A1', 'task': 'Synthetic task.',
           'student_text': 'Synthetic student text.'}
    record = {key: row[key] for key in human.IDENTITY_FIELDS}
    record.update(schema_version=human.HUMAN_REVIEW_SCHEMA_VERSION,
                  reviewer_id='SYNTHETIC_FIXTURE_ONLY', review_date='2026-10-11',
                  rationale='Synthetic test record, not a human benchmark evaluation.',
                  response_assessable=True, meaning_preserved=True, explanations_ok=True,
                  verdict='CORRECT')
    record.update({criterion: 2 for criterion in human.CRITERIA})
    record['clean_text_handling'] = 'NA'
    return row, record


class ImportTests(unittest.TestCase):
    def test_complete_traceable_fixture_is_validated_without_regrading(self):
        row, record = fixtures()
        self.assertEqual(prep.validate_records([record], [row]), [record])
        self.assertNotIn('human_confirmed', row)

    def test_legacy_reviewer_rationale_only_does_not_confirm(self):
        row, record = fixtures()
        for key in human.CRITERIA:
            record.pop(key)
        record.pop('meaning_preserved'); record.pop('explanations_ok')
        with self.assertRaisesRegex(ValueError, 'missing required'):
            prep.validate_records([record], [row])

    def test_wrong_response_hash_rejected(self):
        row, record = fixtures(); record['response_sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'identity'):
            prep.validate_records([record], [row])

    def test_same_reviewer_duplicate_rejected_but_second_reviewer_retained(self):
        row, record = fixtures()
        with self.assertRaisesRegex(ValueError, 'Duplicate human record'):
            prep.validate_records([record, copy.deepcopy(record)], [row])
        other = copy.deepcopy(record); other['reviewer_id'] = 'SECOND_SYNTHETIC_FIXTURE'
        self.assertEqual(len(prep.validate_records([record, other], [row])), 2)

    def test_blind_reviews_are_hydrated_only_with_bound_identity(self):
        row, record = fixtures()
        blind = {key: val for key, val in record.items() if key not in human.IDENTITY_FIELDS}
        blind['blind_output_id'] = 'br-fixture'
        crosswalk = {'items': [{'blind_output_id': 'br-fixture',
                               'context_sha256': prep.context_digest(row),
                               **{key: row[key] for key in human.IDENTITY_FIELDS}}]}
        self.assertEqual(prep.validate_records([blind], [row], crosswalk), [record])
        blind['config_id'] = 'override'
        with self.assertRaisesRegex(ValueError, 'cannot override'):
            prep.validate_records([blind], [row], crosswalk)

    def test_duplicate_crosswalk_rejected(self):
        row, record = fixtures()
        entry = {'blind_output_id': 'br-fixture', **{key: row[key] for key in human.IDENTITY_FIELDS}}
        with self.assertRaisesRegex(ValueError, 'Duplicate or missing'):
            prep.validate_records([record], [row], {'items': [entry, dict(entry)]})

    def test_nan_and_duplicate_json_keys_fail_before_write(self):
        with tempfile.TemporaryDirectory(prefix='human-v2-fixture-') as tmp:
            path = Path(tmp) / 'fixture.jsonl'
            for raw in ['{"x":NaN}', '{"x":1,"x":2}']:
                path.write_text(raw, encoding='utf-8')
                with self.assertRaises(ValueError):
                    prep.load_review_lines(path)

    def test_crosswalk_is_bound_to_text_shown_to_reviewer(self):
        with tempfile.TemporaryDirectory(prefix='blind-v2-fixture-') as tmp:
            root = Path(tmp); private = root / 'coordinator_only'; private.mkdir()
            public = root / 'reviewer_materials'; public.mkdir()
            packet_path = public / 'blind_packet.json'
            cross_path = private / 'identity_crosswalk.json'
            raw = 'Synthetic response.'
            visible = {'blind_output_id': 'br-fixture', 'response_text': raw,
                       'level': 'A1', 'task': 'Synthetic task.', 'student_text': 'Synthetic text.'}
            packet_path.write_text(json.dumps({'items': [visible]}), encoding='utf-8')
            mapping = {'items': [{'blind_output_id': 'br-fixture',
                                  'context_sha256': prep.context_digest(visible),
                                  'response_sha256': prep.v2.digest_text(raw)}]}
            cross_path.write_text(json.dumps(mapping), encoding='utf-8')
            record = {'files': [{'path': prep.reporting._relative(p),
                                 'sha256': prep.reporting.sha256_file(p)}
                                for p in (packet_path, cross_path)]}
            (private / 'packet_record.json').write_text(json.dumps(record), encoding='utf-8')
            self.assertEqual(prep.load_verified_crosswalk(cross_path), mapping)
            packet_path.write_text(json.dumps({'items': [{'blind_output_id': 'br-fixture',
                                                          'response_text': 'Changed response.'}]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Blind packet text differs'):
                prep.load_verified_crosswalk(cross_path)

    def test_blank_templates_are_not_human_reviews(self):
        row, record = fixtures()
        for key in human.REVIEW_FIELDS:
            record[key] = None
        with self.assertRaises(ValueError):
            prep.validate_records([record], [row])

    def test_empty_import_is_rejected(self):
        row, _ = fixtures()
        with self.assertRaisesRegex(ValueError, 'No completed'):
            prep.validate_records([], [row])

    def test_empty_candidate_selection_is_not_all_configs(self):
        with self.assertRaisesRegex(ValueError, 'explicit candidate'):
            prep.create_packet([])

    def test_same_response_cannot_be_crossmapped_to_another_case_context(self):
        row, record = fixtures()
        blind = {key: val for key, val in record.items() if key not in human.IDENTITY_FIELDS}
        blind['blind_output_id'] = 'br-fixture'
        crosswalk = {'items': [{'blind_output_id': 'br-fixture',
                               'context_sha256': prep.context_digest({**row, 'student_text': 'Different case.'}),
                               **{key: row[key] for key in human.IDENTITY_FIELDS}}]}
        with self.assertRaisesRegex(ValueError, 'context differs'):
            prep.validate_records([blind], [row], crosswalk)


if __name__ == '__main__':
    unittest.main()
