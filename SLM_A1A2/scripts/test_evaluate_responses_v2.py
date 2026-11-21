"""Synthetic v2 pipeline tests; no model inference or collected-data edits."""
import hashlib
import copy
import json
import unittest
from unittest.mock import Mock

import evaluate_responses_v2 as v2


def fake_scorer(source, references, candidate):
    """Fixture only: demonstrates that text scoring is independent of declarations."""
    scores = [v2.metrics(int(candidate == ref and source != ref),
                        int(candidate not in (source, ref)),
                        int(candidate != ref and source != ref)) for ref in references]
    best = max(range(len(scores)), key=lambda index: (scores[index]['f0_5'], -index))
    return {'primary': scores[0], 'best_full_reference': scores[best],
            'best_reference_index': best, 'reference_scores': scores}


def case(condition='incorrect'):
    source = 'The teacher meet Lina.' if condition == 'incorrect' else 'The teacher meets Lina.'
    return {'id': 'A1-E001', 'level': 'A1', 'condition': condition,
            'task': 'Describe a lesson.', 'student_text': source,
            'gold': {'is_correct': condition == 'correct', 'corrected_text': 'The teacher meets Lina.',
                     'errors': [{'original': 'teacher meet', 'correction': 'teacher meets'}]
                               if condition == 'incorrect' else [], 'acceptable_alternatives': []}}


def row(payload):
    return {'config_id': 'synthetic', 'raw_response': json.dumps(payload), 'attempt_trace': [1]}


def payload(original='meet', correction='meets'):
    return {'is_correct': False, 'corrected_text': 'The teacher meets Lina.',
            'errors': [{'original': original, 'correction': correction,
                        'type': 'SUBJECT_VERB_AGREEMENT', 'explanation': 'Singular subject.'}],
            'feedback': 'Check the verb.'}


def evaluate(c, r, scorer=fake_scorer):
    return v2.evaluate_text(c, r, scope='synthetic', benchmark_sha='b' * 64,
                            manifest_sha='m' * 64, scorer=scorer)


class DeclarationTests(unittest.TestCase):
    def test_short_and_context_fragments_have_identical_effect(self):
        source = 'The teacher meet Lina.'
        for p in [payload(), payload('teacher meet', 'teacher meets')]:
            result = v2.reconstruct_declarations(source, p)
            self.assertEqual(result['status'], 'verified_matches_output')
            self.assertTrue(result['coherent_non_noop'])

    def test_combined_repairs_are_coherent(self):
        result = v2.reconstruct_declarations('He go and she work.',
            {'errors': [{'original': 'He go and she work', 'correction': 'He goes and she works'}],
             'corrected_text': 'He goes and she works.'})
        self.assertEqual(result['status'], 'verified_matches_output')

    def test_repeated_fragment_is_never_guessed(self):
        result = v2.reconstruct_declarations('I like cats and cats.',
            {'errors': [{'original': 'cats', 'correction': 'dogs'}], 'corrected_text': 'I like dogs and cats.'})
        self.assertEqual(result['status'], 'unverified_ambiguous_or_absent_fragment')

    def test_overlap_is_unverified(self):
        result = v2.reconstruct_declarations('The teacher meet Lina.',
            {'errors': [{'original': 'teacher meet', 'correction': 'teacher meets'},
                        {'original': 'meet', 'correction': 'meets'}], 'corrected_text': 'The teacher meets Lina.'})
        self.assertEqual(result['status'], 'unverified_overlapping_fragments')

    def test_correction_elsewhere_does_not_realize_declaration(self):
        result = v2.reconstruct_declarations('I have a dog. She have a dog.',
            {'errors': [{'original': 'I have', 'correction': 'I has'}],
             'corrected_text': 'I have a dog. She has a dog.'})
        self.assertEqual(result['status'], 'verified_differs_output')

    def test_deletion_allowed_and_noop_separate(self):
        result = v2.reconstruct_declarations('I am am happy.',
            {'errors': [{'original': 'am am', 'correction': 'am'}], 'corrected_text': 'I am happy.'})
        self.assertTrue(result['coherent_non_noop'])
        result = v2.reconstruct_declarations('I am happy.',
            {'errors': [{'original': 'happy', 'correction': 'happy'}], 'corrected_text': 'I am happy.'})
        self.assertEqual(result['no_op_declarations'], 1)
        self.assertFalse(result['coherent_non_noop'])


class EvaluationTests(unittest.TestCase):
    def test_fragment_granularity_does_not_drive_text_metric(self):
        result = evaluate(case(), row(payload()))
        self.assertEqual(result['gec']['primary']['tp'], 1)
        self.assertTrue(result['declarations']['coherent_non_noop'])
        self.assertFalse(result['human_confirmed'])
        self.assertEqual(result['response_sha256'], hashlib.sha256(row(payload())['raw_response'].encode()).hexdigest())

    def test_schema_and_text_quality_remain_separate(self):
        p = payload(); p['extra'] = True
        result = evaluate(case(), row(p))
        self.assertFalse(result['format']['schema_valid'])
        self.assertEqual(result['gec']['primary']['tp'], 1)

    def test_missing_text_is_not_substituted_with_original(self):
        scorer = Mock(side_effect=fake_scorer)
        result = evaluate(case(), {'config_id': 'synthetic', 'raw_response': 'No JSON'}, scorer)
        self.assertIsNone(result['gec'])
        self.assertIsNone(result['text_changed'])
        self.assertFalse(result['corrected_text_observable'])
        self.assertEqual(scorer.call_count, 1)  # count gold edits only
        summary = v2.aggregate([result])
        self.assertIsNone(summary['gec_conditional_on_observable_text']['primary'])
        self.assertEqual(summary['unobservable_primary_errant_edits'], 1)
        self.assertEqual(summary['recall_all_primary_gold_unobservable_as_missed'], 0)

    def test_empty_text_unobservable(self):
        p = payload(); p['corrected_text'] = '  '
        result = evaluate(case(), row(p))
        self.assertFalse(result['corrected_text_observable'])

    def test_missing_control_flag_is_unknown_not_no_false_alarm(self):
        p = {'corrected_text': case('correct')['student_text'], 'errors': [], 'feedback': ''}
        result = evaluate(case('correct'), row(p))
        self.assertIsNone(result['control_false_alarm'])
        self.assertIsNone(result['control_fully_preserved'])
        summary = v2.aggregate([result])
        self.assertEqual(summary['cfar_unobservable'], 1)

    def test_false_alarm_without_text_modification(self):
        p = payload(); p['errors'] = []
        result = evaluate(case('correct'), row(p))
        self.assertFalse(result['text_changed'])
        self.assertTrue(result['control_false_alarm'])

    def test_known_alarm_visible_despite_other_unknown_field(self):
        for p in [{'corrected_text': case('correct')['student_text'], 'is_correct': False},
                  {'corrected_text': case('correct')['student_text'], 'errors': [{'original': 'x'}]}]:
            result = evaluate(case('correct'), row(p))
            self.assertTrue(result['control_false_alarm'])

    def test_only_complete_references_passed_not_error_cartesian(self):
        c = case(); c['gold']['acceptable_alternatives'] = ['The teacher does meet Lina.']
        c['gold']['errors'][0]['acceptable_corrections'] = ['made-up per-error variant']
        scorer = Mock(side_effect=fake_scorer)
        evaluate(c, row(payload()), scorer)
        refs = scorer.call_args.args[1]
        self.assertEqual(refs, ['The teacher meets Lina.', 'The teacher does meet Lina.'])

    def test_conditional_denominator_and_conservative_recall(self):
        good = evaluate(case(), row(payload()))
        missing = evaluate(case(), {'config_id': 'synthetic', 'raw_response': 'No JSON'})
        summary = v2.aggregate([good, missing])
        self.assertEqual(summary['incorrect_text_observable'], 1)
        self.assertEqual(summary['gec_conditional_on_observable_text']['primary']['recall'], 1)
        self.assertEqual(summary['recall_all_primary_gold_unobservable_as_missed'], .5)

    def test_primary_binding_requires_resume_key_model_and_exact_selected_attempt(self):
        source = {'case_id': 'synthetic_case', 'config_id': 'synthetic_config',
                  'model_sha256': 'm' * 64, 'resume_key': 'group-a',
                  'attempt_trace': [1], 'derived_seq': 1}
        provenance = {key: source[key] for key in ('config_id', 'model_sha256', 'resume_key',
                                                 'attempt_trace', 'derived_seq')}
        provenance.update(benchmark_sha256='b' * 64, manifest_sha256='f' * 64, selected_attempt=1)
        primary = {'case_id': source['case_id'], 'response_provenance': provenance}
        v2.validate_primary_binding(primary, source, 'b' * 64, 'f' * 64)
        for key, value in [('resume_key', 'group-b'), ('model_sha256', 'different-model'),
                           ('selected_attempt', 2), ('derived_seq', 2)]:
            wrong = copy.deepcopy(primary); wrong['response_provenance'][key] = value
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'provenance differs'):
                v2.validate_primary_binding(wrong, source, 'b' * 64, 'f' * 64)

    def test_malformed_complete_reference_container_is_rejected(self):
        c = case(); c['gold']['acceptable_alternatives'] = 'not an array'
        with self.assertRaisesRegex(ValueError, 'list'):
            evaluate(c, row(payload()))


if __name__ == '__main__':
    unittest.main()
