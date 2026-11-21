"""Post-hoc mechanical diagnostics. Never regrade, infer, or edit frozen gold.

Exact corrected-text matching and equivalent edit reconstruction are descriptive
observations, not human semantic/explanation approval. Primary frozen scores
remain unchanged. Ambiguous/overlapping predicted fragments stay unverified.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import evaluate_benchmark_120 as evaluator
import report_execution_results as reporting


def reconstruct_unique_edits(student, parsed):
    if not isinstance(parsed, dict) or not isinstance(parsed.get('errors'), list):
        return None, 'unverified_shape'
    edits = []
    for entry in parsed['errors']:
        if not isinstance(entry, dict):
            return None, 'unverified_shape'
        original, correction = entry.get('original'), entry.get('correction')
        if not isinstance(original, str) or not original or not isinstance(correction, str):
            return None, 'unverified_shape'
        positions = []
        offset = 0
        while True:
            pos = student.find(original, offset)
            if pos < 0:
                break
            positions.append(pos)
            offset = pos + 1
        if len(positions) != 1:
            return None, 'unverified_ambiguous_or_absent_fragment'
        start = positions[0]
        edits.append((start, start + len(original), correction))
    edits.sort()
    if any(a[1] > b[0] for a, b in zip(edits, edits[1:])):
        return None, 'unverified_overlapping_fragments'
    text = student
    for start, end, correction in reversed(edits):
        text = text[:start] + correction + text[end:]
    return text, 'unique_nonoverlapping_literal_edits'


def analyze(scope):
    inv = reporting.load_scope_inventory(scope)
    reports = inv.result_dir / 'reports'
    collected = reporting.load_json(reports / 'scope_summary.json')
    if (collected.get('coverage', {}).get('status') != 'COMPLETE'
            or collected.get('benchmark', {}).get('sha256') != inv.benchmark_sha256
            or collected.get('manifest', {}).get('sha256') != inv.manifest_sha256):
        raise ValueError('Diagnostics require complete identity-bound primary reports')
    manifest = reporting.load_json(reporting.MANIFEST)
    cases = {c['id']: c for c in inv.cases}
    summaries, rows, sources = [], [], []
    for config in inv.configurations:
        cid = config['config_id']
        base = inv.result_dir
        pp = base / 'parsed' / cid / 'responses.jsonl'
        ap = base / 'raw' / cid / 'attempts.jsonl'
        ep = base / 'evaluations' / cid / 'case_evaluations.jsonl'
        source_rows, _ = evaluator.select_authorized_latest_rows(
            reporting.load_jsonl(pp), inv.benchmark_sha256,
            attempt_rows=reporting.load_jsonl(ap), config_filter=cid,
            manifest_sha=inv.manifest_sha256, manifest_data=manifest)
        predictions = {r['case_id']: r for r in source_rows}
        evaluations = {e['case_id']: e for e in reporting.load_jsonl(ep)}
        if set(predictions) != set(cases) or set(evaluations) != set(cases):
            raise ValueError('Incomplete or mixed configuration input')
        for p in (pp, ap, ep):
            sources.append({'path': reporting._relative(p), 'sha256': reporting.sha256_file(p)})
        counts = Counter()
        examples = []
        for case_id, case in cases.items():
            e = evaluations[case_id]
            row = predictions[case_id]
            view = evaluator.case_view(case)
            pred = evaluator.detect_format(row.get('raw_response'))['parsed']
            text, state = reconstruct_unique_edits(view['student_text'], pred)
            equivalent = text == view['gold']['corrected_text'] if text is not None else None
            same_output = (text == pred.get('corrected_text')) if text is not None else None
            match = e.get('corrected_text_match')
            is_incorrect = e['condition'] == 'incorrect'
            gap = is_incorrect and match == 'exact_primary' and e['verdict_provisional'] != 'CORRECT'
            counts['cases'] += 1
            counts['incorrect_cases'] += is_incorrect
            counts['exact_primary_all_cases'] += match == 'exact_primary'
            counts['exact_primary_incorrect_cases'] += is_incorrect and match == 'exact_primary'
            counts['licensed_fulltext_alternative_incorrect_cases'] += is_incorrect and match == 'alternative'
            counts['primary_text_match_but_not_strict_correct'] += gap
            counts['unique_edit_effect_matches_primary_incorrect_cases'] += bool(is_incorrect and equivalent and same_output)
            counts['edit_reconstruction_unverified_incorrect_cases'] += bool(is_incorrect and text is None)
            record = {'config_id': cid, 'case_id': case_id, 'level': e['level'],
                      'condition': e['condition'], 'primary_verdict_unchanged': e['verdict_provisional'],
                      'corrected_text_match': match, 'primary_text_match_but_not_strict_correct': gap,
                      'edit_reconstruction_state': state, 'declared_edit_effect_matches_gold_primary': equivalent,
                      'declared_edit_effect_matches_predicted_text': same_output,
                      'response_provenance': e.get('response_provenance')}
            rows.append(record)
            if gap and equivalent and same_output and len(examples) < 3:
                examples.append({**record,
                    'gold_pairs': [[x['original'], x['correction']] for x in view['gold']['errors']],
                    'predicted_pairs': [[x['original'], x['correction']] for x in pred['errors']]})
        summaries.append({'config_id': cid, **counts, 'mechanical_examples': examples})
    result = {'scope': scope, 'analysis_kind': 'POST_HOC_DESCRIPTIVE_DIAGNOSTIC_NOT_A_NEW_PRIMARY_SCORE',
              'generated_utc': datetime.now(timezone.utc).isoformat(),
              'benchmark_sha256': inv.benchmark_sha256, 'manifest_sha256': inv.manifest_sha256,
              'diagnostic_code_sha256': reporting.sha256_file(Path(__file__)),
              'primary_evaluator_code_sha256': reporting.sha256_file(reporting.EVALUATOR),
              'source_inputs': sources, 'primary_scores_modified': False,
              'human_semantic_confirmation': False,
              'limits': 'Literal fragment granularity can penalize valid declarations. Exact gold text or equivalent unique edit effects do not confirm explanations, flag correctness, dialect variants or generalization. Ambiguous/overlapping fragments are unverified, never guessed.',
              'configuration_summaries': summaries}
    (reports / 'annotation_granularity_diagnostic.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (reports / 'annotation_granularity_cases.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v
                             for k, v in row.items()})
    print(json.dumps({'scope': scope, 'diagnostic_rows': len(rows), 'primary_scores_modified': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['results_120', 'results_40_current_16'], required=True)
    analyze(parser.parse_args().scope)
