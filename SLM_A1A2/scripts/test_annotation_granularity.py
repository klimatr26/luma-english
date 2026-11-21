import copy
import unittest
from analyze_annotation_granularity import reconstruct_unique_edits
from report_execution_results import _configuration_csv_rows


class GranularityDiagnosticTests(unittest.TestCase):
    def test_shorter_valid_fragments_reconstruct_without_regrading_or_mutation(self):
        source = 'Our teacher meet us. Lina bring pencils.'
        pred = {'errors': [{'original': 'meet', 'correction': 'meets'},
                           {'original': 'bring', 'correction': 'brings'}]}
        before = copy.deepcopy(pred)
        text, state = reconstruct_unique_edits(source, pred)
        self.assertEqual(text, 'Our teacher meets us. Lina brings pencils.')
        self.assertEqual(state, 'unique_nonoverlapping_literal_edits')
        self.assertEqual(pred, before)
        self.assertNotIn('verdict', pred)

    def test_ambiguous_or_absent_fragment_never_guesses_location(self):
        for original in ['go', 'leave']:
            text, state = reconstruct_unique_edits('I go and they go.', {'errors': [
                {'original': original, 'correction': 'goes'}]})
            self.assertIsNone(text)
            self.assertEqual(state, 'unverified_ambiguous_or_absent_fragment')

    def test_overlapping_edits_are_unverified(self):
        text, state = reconstruct_unique_edits('She go home.', {'errors': [
            {'original': 'She go', 'correction': 'She goes'},
            {'original': 'go home', 'correction': 'goes home'}]})
        self.assertIsNone(text)
        self.assertEqual(state, 'unverified_overlapping_fragments')

    def test_observed_zero_format_count_differs_from_uncollected(self):
        base = {'config_id': 'test', 'model_id': 'test', 'telemetry': {},
                'execution_complete': True, 'expected_cases': 1,
                'selected_parsed_cases': 1, 'raw_final_cases': 1,
                'missing_cases': 0, 'technical_failure_cases': 0,
                'evaluation': {'format': {'parse_status_counts': {'invalid': 1}}}}
        row = _configuration_csv_rows([base])[0]
        self.assertEqual(row['parse_direct'], 0)
        self.assertEqual(row['parse_recoverable'], 0)
        self.assertEqual(row['parse_invalid'], 1)
        base['evaluation'] = None
        self.assertIsNone(_configuration_csv_rows([base])[0]['parse_direct'])


if __name__ == '__main__':
    unittest.main()
