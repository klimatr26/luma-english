"""Report integration on synthetic rows only."""
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import evaluate_responses_v2 as v2
import report_evaluation_v2 as report
from test_evaluate_responses_v2 import case, evaluate, payload, row


class ReportTests(unittest.TestCase):
    def test_subgroups_categories_and_coverage_do_not_mix_controls_into_gec(self):
        wrong = evaluate(case(), row(payload()))
        wrong['gec']['primary']['category_lineage'] = {'R:VERB:SVA': {'tp': 1, 'fp': 0, 'fn': 0}}
        control = case('correct'); control['id'] = 'A1-C001'
        p = {'is_correct': True, 'corrected_text': control['student_text'], 'errors': [], 'feedback': 'Good.'}
        good = evaluate(control, row(p))
        good['gec']['primary']['category_lineage'] = {}
        rows = [wrong, good]
        summary = {'configurations': [{'config_id': 'synthetic', 'summary': v2.aggregate(rows)}]}
        inv = SimpleNamespace(config_ids=['synthetic'], configurations=[{'config_id': 'synthetic'}])
        with tempfile.TemporaryDirectory(prefix='report-v2-fixture-') as tmp:
            out = Path(tmp); scope = out / 'synthetic'; scope.mkdir()
            (scope / 'scope_summary.json').write_text(json.dumps(summary), encoding='utf-8')
            (scope / 'completion_record.json').write_text('{"status":"synthetic"}', encoding='utf-8')
            with patch.object(v2, 'OUTPUT', out), patch.object(report.review, 'load_bound_rows', return_value=(inv, rows)):
                report.create('synthetic')
                with self.assertRaisesRegex(ValueError, 'overwrite'):
                    report.create('synthetic')
            with (scope / 'reports/subgroup_summary.csv').open(encoding='utf-8') as stream:
                subgroups = list(csv.DictReader(stream))
            level = next(r for r in subgroups if r['dimension'] == 'level')
            self.assertEqual(level['cases'], '2'); self.assertEqual(level['incorrect_cases_expected'], '1')
            self.assertEqual(level['tp'], '1'); self.assertEqual(level['controls'], '1')
            with (scope / 'reports/errant_categories.csv').open(encoding='utf-8') as stream:
                categories = list(csv.DictReader(stream))
            self.assertEqual(len(categories), 1)
            self.assertEqual(categories[0]['tp'], '1')
            record = json.loads((scope / 'reports/report_record.json').read_text(encoding='utf-8'))
            self.assertEqual(record['new_slm_inferences'], 0)
            self.assertEqual(record['human_confirmed'], 0)


if __name__ == '__main__':
    unittest.main()
