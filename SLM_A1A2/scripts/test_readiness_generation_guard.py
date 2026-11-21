import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from readiness_generation_guard import (REPEAT_IDS, sha256, load_authorization,
                                         check_budget, claim_generation)


class ReadinessBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lab = self.tmp.name
        self.out = os.path.join(self.lab, 'logs', 'new')
        os.makedirs(self.out)
        self.configs = [{'id': cid, 'model_sha256': 'b' * 64} for cid in REPEAT_IDS]
        entries = []
        for cid in sorted(REPEAT_IDS):
            path = os.path.join(self.lab, 'logs', cid + '.request.json')
            with open(path, 'wb') as stream:
                stream.write(b'{"historical": true}')
            entries.append({'id': cid, 'model_sha256': 'b' * 64,
                            'prior_request_count': 1, 'additional_requests': 1,
                            'prior_request_path': os.path.relpath(path, self.lab),
                            'prior_request_sha256': sha256(path)})
        self.record = {'scope': 'four_nonthinking_readiness_repetitions',
                       'manifest_sha256': 'a' * 64, 'human_authorized': True,
                       'user_instruction': 'Explicit fixture authorization',
                       'main_benchmark_authorized': False, 'configurations': entries}
        self.path = os.path.join(self.lab, 'auth.json')

    def load(self, record=None, manifest_sha='a' * 64):
        with open(self.path, 'w', encoding='utf-8') as stream:
            json.dump(self.record if record is None else record, stream)
        with patch('readiness_generation_guard.APPROVED_RECORD_SHA256', sha256(self.path)):
            return load_authorization(self.path, manifest_sha, self.configs)

    def test_modified_authorization_cannot_self_approve(self):
        self.load()
        with self.assertRaises(ValueError):
            load_authorization(self.path, 'a' * 64, self.configs)

    def test_four_permits_preserve_history_and_are_consumed_once(self):
        auth = self.load()
        for entry in self.record['configurations']:
            cid = entry['id']
            claim = claim_generation(self.lab, cid, auth, 'a' * 64, self.out)
            self.assertTrue(claim['repeat'])
            self.assertEqual(sha256(os.path.join(self.lab, entry['prior_request_path'])), entry['prior_request_sha256'])
            with self.assertRaises(ValueError):
                claim_generation(self.lab, cid, auth, 'a' * 64, self.out)

    def test_unapproved_config_first_only(self):
        auth = self.load()
        self.assertFalse(claim_generation(self.lab, 'other', auth, 'a' * 64, self.out)['repeat'])
        with self.assertRaises(ValueError):
            check_budget(self.lab, 'other', auth)

    def test_no_authorization_cannot_repeat(self):
        with self.assertRaises(ValueError):
            check_budget(self.lab, next(iter(REPEAT_IDS)), None)

    def test_wrong_manifest_scope_or_count_rejected(self):
        with self.assertRaises(ValueError):
            self.load(manifest_sha='c' * 64)
        for key, value in [('scope', 'generic_retry'), ('human_authorized', False),
                           ('main_benchmark_authorized', True)]:
            record = copy.deepcopy(self.record)
            record[key] = value
            with self.assertRaises(ValueError):
                self.load(record)
        record = copy.deepcopy(self.record)
        record['configurations'][0]['additional_requests'] = 2
        with self.assertRaises(ValueError):
            self.load(record)
        record['configurations'][0]['additional_requests'] = True
        with self.assertRaises(ValueError):
            self.load(record)

    def test_history_altered_extra_missing_or_path_escape_rejected(self):
        entry = self.record['configurations'][0]
        auth = self.load()
        cid = entry['id']
        with open(os.path.join(self.out, cid + '.request.json'), 'w') as stream:
            stream.write('{}')
        with self.assertRaises(ValueError):
            check_budget(self.lab, cid, auth)
        os.remove(os.path.join(self.out, cid + '.request.json'))
        prior = os.path.join(self.lab, entry['prior_request_path'])
        with open(prior, 'w') as stream:
            stream.write('{}')
        with self.assertRaises(ValueError):
            check_budget(self.lab, cid, auth)
        os.remove(prior)
        with self.assertRaises(ValueError):
            check_budget(self.lab, cid, auth)
        auth['by_id'][cid]['prior_request_path'] = '../outside.request.json'
        with self.assertRaises(ValueError):
            check_budget(self.lab, cid, auth)


if __name__ == '__main__':
    unittest.main()
