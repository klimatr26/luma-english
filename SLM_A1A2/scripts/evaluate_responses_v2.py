"""Post-hoc, read-only-source ERRANT analysis. Never performs SLM inference.

Writes exclusively to analysis_v2, keeps original evaluator/results immutable,
and never certifies human meaning/explanation quality automatically.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

import evaluate_benchmark_120 as frozen
import report_execution_results as reporting

LAB = Path(__file__).resolve().parents[1]
PROTOCOL = LAB / 'documentation/evaluation_v2_protocol.md'
OUTPUT = LAB / 'analysis_v2'
SCOPES = ('results_120', 'results_40_current_16')
VERSION = 'evaluation-v2.0'


def digest_text(text):
    if not isinstance(text, str):
        raise ValueError('Response content must be a string to bind its identity')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def metrics(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': precision,
            'recall': recall, 'f0_5': 1.25 * precision * recall /
            (0.25 * precision + recall) if precision + recall else 0.0}


def reconstruct_declarations(student, parsed):
    """Literal unique spans only. Do not choose ambiguous occurrences."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get('errors'), list):
        return {'status': 'unverified_shape', 'reconstructed_text': None}
    edits, noop = [], 0
    for item in parsed['errors']:
        if not isinstance(item, dict):
            return {'status': 'unverified_shape', 'reconstructed_text': None}
        original, correction = item.get('original'), item.get('correction')
        if not isinstance(original, str) or not original or not isinstance(correction, str):
            return {'status': 'unverified_shape', 'reconstructed_text': None}
        positions, offset = [], 0
        while True:
            position = student.find(original, offset)
            if position < 0:
                break
            positions.append(position)
            offset = position + 1
        if len(positions) != 1:
            return {'status': 'unverified_ambiguous_or_absent_fragment',
                    'reconstructed_text': None}
        start = positions[0]
        edits.append((start, start + len(original), correction))
        noop += original == correction
    edits.sort()
    if any(left[1] > right[0] for left, right in zip(edits, edits[1:])):
        return {'status': 'unverified_overlapping_fragments', 'reconstructed_text': None}
    result = student
    for start, end, correction in reversed(edits):
        result = result[:start] + correction + result[end:]
    consistent = result == parsed.get('corrected_text')
    return {'status': 'verified_matches_output' if consistent else 'verified_differs_output',
            'reconstructed_text': result, 'declared_edits': len(edits),
            'no_op_declarations': noop,
            'coherent_non_noop': consistent and noop == 0}


def evaluate_text(case, source_row, *, scope, benchmark_sha, manifest_sha, scorer):
    raw = source_row['raw_response']
    fmt = frozen.detect_format(raw)
    parsed = fmt.pop('parsed')
    schema_valid, schema_errors = frozen.validate_schema(parsed)
    fmt['schema_valid'] = schema_valid
    fmt['schema_errors'] = schema_errors
    fmt['strict_json_compliant'] = bool(fmt['parse_status'] == 'direct' and schema_valid
                                        and not fmt['has_fence'] and not fmt['text_outside_json'])
    view = frozen.case_view(case)
    student, gold = view['student_text'], view['gold']
    candidate = parsed.get('corrected_text') if isinstance(parsed, dict) else None
    observable = isinstance(candidate, str) and bool(candidate.strip())
    references = [gold['corrected_text']]
    alternatives = gold.get('acceptable_alternatives') or []
    if not isinstance(alternatives, list):
        raise ValueError('Complete references must be stored as a list')
    for alt in alternatives:
        if not isinstance(alt, str) or not alt.strip():
            raise ValueError('Invalid complete reference')
        if alt not in references:
            references.append(alt)
    # Count expected gold edits even when the response has no observable text.
    reference_count = scorer(student, references, student)['primary']['fn']
    gec = scorer(student, references, candidate) if observable else None
    declaration = reconstruct_declarations(student, parsed)
    flag = parsed.get('is_correct') if isinstance(parsed, dict) else None
    error_list = parsed.get('errors') if isinstance(parsed, dict) else None
    false_alarm = None
    if flag is False or (isinstance(error_list, list) and len(error_list) > 0):
        false_alarm = True
    elif flag is True and error_list == []:
        false_alarm = False
    changed = candidate != student if observable else None
    flag_ok = flag == gold['is_correct'] if isinstance(flag, bool) else None
    return {
        'schema_version': VERSION, 'scope': scope,
        'benchmark_sha256': benchmark_sha, 'manifest_sha256': manifest_sha,
        'config_id': source_row['config_id'], 'case_id': view['case_id'],
        'response_sha256': digest_text(raw), 'response_sha256_definition': 'sha256(UTF-8 raw_response)',
        'model_sha256': source_row.get('model_sha256'),
        'selected_attempt_trace': source_row.get('attempt_trace'),
        'level': view['level'], 'condition': view['condition'],
        'task': view['task'], 'student_text': student,
        'gold_primary_text': references[0], 'complete_references': references,
        'intentional_gold_errors': len(gold['errors']),
        'expected_primary_errant_edits': reference_count,
        'raw_response': raw, 'parsed_response': parsed, 'format': fmt,
        'corrected_text_observable': observable,
        'corrected_text_equal_primary': candidate == references[0] if observable else None,
        'corrected_text_equal_licensed_complete_reference': candidate in references if observable else None,
        'text_changed': changed, 'flag_correct': flag_ok,
        'control_false_alarm': false_alarm if view['condition'] == 'correct' else None,
        'control_fully_preserved': (not changed and flag is True and error_list == [])
                                  if view['condition'] == 'correct' and observable
                                  and isinstance(flag, bool) and isinstance(error_list, list) else None,
        'declarations': declaration, 'gec': gec,
        'primary_strict_verdict': None, 'primary_strict_detection': None,
        'human_confirmed': False, 'human_evaluation': None,
        'transport': source_row.get('transport'), 'memory': source_row.get('memory'),
    }


def aggregate(rows):
    errors = [r for r in rows if r['condition'] == 'incorrect']
    observed = [r for r in errors if r['gec'] is not None]
    totals = {}
    for field in ('primary', 'best_full_reference'):
        sums = {key: sum(r['gec'][field][key] for r in observed) for key in ('tp', 'fp', 'fn')}
        totals[field] = metrics(**sums) if observed else None
    all_gold = sum(r['expected_primary_errant_edits'] for r in errors)
    missing_gold = sum(r['expected_primary_errant_edits'] for r in errors if r['gec'] is None)
    controls = [r for r in rows if r['condition'] == 'correct']
    latencies = [r['transport']['latency_seconds_total'] for r in rows
                 if isinstance(r.get('transport'), dict)
                 and isinstance(r['transport'].get('latency_seconds_total'), (int, float))]
    return {
        'cases': len(rows), 'incorrect_cases_expected': len(errors),
        'incorrect_text_observable': len(observed),
        'incorrect_text_unobservable': len(errors) - len(observed),
        'expected_primary_errant_edits': all_gold,
        'unobservable_primary_errant_edits': missing_gold,
        'gec_conditional_on_observable_text': totals,
        'recall_all_primary_gold_unobservable_as_missed':
            totals['primary']['tp'] / all_gold if all_gold and observed else (0.0 if all_gold else None),
        'controls_expected': len(controls),
        'ctmr_modified_observed': sum(r['text_changed'] is True for r in controls),
        'ctmr_unobservable': sum(r['text_changed'] is None for r in controls),
        'cfar_false_alarm_observed': sum(r['control_false_alarm'] is True for r in controls),
        'cfar_unobservable': sum(r['control_false_alarm'] is None for r in controls),
        'fully_preserved_observed': sum(r['control_fully_preserved'] is True for r in controls),
        'fully_preserved_unobservable': sum(r['control_fully_preserved'] is None for r in controls),
        'parse_status': dict(Counter(r['format']['parse_status'] for r in rows)),
        'schema_valid': sum(r['format']['schema_valid'] for r in rows),
        'strict_json_compliant': sum(r['format']['strict_json_compliant'] for r in rows),
        'declarations': dict(Counter(r['declarations']['status'] for r in rows)),
        'declarations_coherent_non_noop': sum(r['declarations'].get('coherent_non_noop', False) for r in rows),
        'incorrect_text_equal_primary': sum(r['corrected_text_equal_primary'] is True for r in errors),
        'incorrect_text_equal_licensed_complete_reference':
            sum(r['corrected_text_equal_licensed_complete_reference'] is True for r in errors),
        'flag_correct_observed': sum(r['flag_correct'] is True for r in rows),
        'flag_unobservable': sum(r['flag_correct'] is None for r in rows),
        'incorrect_flag_correct_observed': sum(r['flag_correct'] is True for r in errors),
        'incorrect_flag_unobservable': sum(r['flag_correct'] is None for r in errors),
        'human_confirmed': sum(r['human_confirmed'] is True for r in rows),
        'latency_median_seconds_descriptive': statistics.median(latencies) if latencies else None,
        'schema_version': VERSION,
    }


def source_inventory(inv):
    """Only known existing scopes; never enumerate a final dataset."""
    paths = [inv.benchmark_path, reporting.MANIFEST, reporting.AUTHORIZATION_PATHS[inv.scope],
             inv.result_dir / 'reports/source_index.json', PROTOCOL,
             Path(__file__), reporting.EVALUATOR, reporting.RUNNER_DIR / 'scripts/report_execution_results.py',
             LAB / 'scripts/gec_alignment_v2.py', LAB / 'scripts/human_review_v2.py',
             LAB / 'benchmark_120/human_review_v2_schema.json',
             LAB / 'documentation/human_review_rubric_v2.md',
             LAB / 'requirements-evaluation-v2.txt']
    for config in inv.configurations:
        cid = config['config_id']
        paths.extend([inv.result_dir / 'raw' / cid / 'attempts.jsonl',
                      inv.result_dir / 'parsed' / cid / 'responses.jsonl',
                      inv.result_dir / 'evaluations' / cid / 'case_evaluations.jsonl'])
    index = reporting.load_json(inv.result_dir / 'reports/source_index.json')
    for field in ('source_inputs', 'generated_artifacts'):
        for item in index.get(field, []):
            if not item.get('sha256'):
                continue
            path = reporting.REPO_DIR / item['path']
            if reporting.sha256_file(path) != item['sha256']:
                raise ValueError(f'Frozen report source index mismatch: {path}')
            paths.append(path)
    return [{'path': reporting._relative(p), 'sha256': reporting.sha256_file(p)}
            for p in dict.fromkeys(paths)]


def assert_sources_unchanged(sources):
    for item in sources:
        if reporting.sha256_file(reporting.REPO_DIR / item['path']) != item['sha256']:
            raise ValueError('Input changed during analysis: ' + item['path'])


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def validate_primary_binding(primary, source_row, benchmark_sha, manifest_sha):
    provenance = primary.get('response_provenance') or {}
    trace = source_row.get('attempt_trace')
    if (not isinstance(trace, list) or not trace
            or primary.get('case_id') != source_row.get('case_id')
            or provenance.get('benchmark_sha256') != benchmark_sha
            or provenance.get('manifest_sha256') != manifest_sha
            or provenance.get('config_id') != source_row.get('config_id')
            or provenance.get('model_sha256') != source_row.get('model_sha256')
            or provenance.get('resume_key') != source_row.get('resume_key')
            or provenance.get('selected_attempt') != trace[-1]
            or provenance.get('attempt_trace') != trace
            or provenance.get('derived_seq') != source_row.get('derived_seq')):
        raise ValueError('Primary evaluation provenance differs from selected response')


def comparison_csv(path, summaries):
    flat = []
    for record in summaries:
        s = record['summary']
        row = {key: record[key] for key in ('config_id', 'family', 'quant')}
        row.update({k: v for k, v in s.items() if not isinstance(v, dict)})
        for variant, metric in s['gec_conditional_on_observable_text'].items():
            for key in ('tp', 'fp', 'fn', 'precision', 'recall', 'f0_5'):
                row[variant + '_' + key] = metric[key] if metric else None
        for kind in ('direct', 'recoverable', 'invalid'):
            row['parse_' + kind] = s['parse_status'].get(kind, 0)
        row['primary_frozen_tp'] = record['primary_frozen_tp']
        row['primary_frozen_fp'] = record['primary_frozen_fp']
        row['primary_frozen_fn'] = record['primary_frozen_fn']
        row['primary_frozen_f0_5'] = metrics(record['primary_frozen_tp'], record['primary_frozen_fp'],
                                          record['primary_frozen_fn'])['f0_5']
        flat.append(row)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)


def run(scope):
    if scope not in SCOPES:
        raise ValueError('Only the two collected scopes are supported')
    inv = reporting.load_scope_inventory(scope)
    out = OUTPUT / scope
    if out.exists():
        raise ValueError(f'Refusing to overwrite a previous v2 analysis: {out}')
    sources = source_inventory(inv)
    import gec_alignment_v2 as gec_engine
    engine = gec_engine.get_engine()
    manifest = reporting.load_json(reporting.MANIFEST)
    cases = {case['id']: case for case in inv.cases}
    out.mkdir(parents=True)
    write_json(out / 'start_record.json', {'version': VERSION, 'scope': scope,
              'analysis_kind': 'POST_HOC_VERSIONED_REEVALUATION_NOT_HUMAN_APPROVAL',
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'source_inputs': sources, 'engine': engine.metadata(),
              'benchmark_sha256': inv.benchmark_sha256, 'manifest_sha256': inv.manifest_sha256})
    summaries = []
    for config in inv.configurations:
        cid = config['config_id']
        selected, selection = frozen.select_authorized_latest_rows(
            reporting.load_jsonl(inv.result_dir / 'parsed' / cid / 'responses.jsonl'),
            inv.benchmark_sha256,
            attempt_rows=reporting.load_jsonl(inv.result_dir / 'raw' / cid / 'attempts.jsonl'),
            config_filter=cid, manifest_sha=inv.manifest_sha256, manifest_data=manifest)
        old = reporting.load_jsonl(inv.result_dir / 'evaluations' / cid / 'case_evaluations.jsonl')
        old_by_id = {row['case_id']: row for row in old}
        if (len(selected) != len(cases) or {row['case_id'] for row in selected} != set(cases)
                or len(old) != len(cases) or set(old_by_id) != set(cases)):
            raise ValueError('Incomplete or duplicate response/evaluation matrix')
        rows = []
        for selected_row in selected:
            case_id = selected_row['case_id']
            row = evaluate_text(cases[case_id], selected_row, scope=scope,
                                benchmark_sha=inv.benchmark_sha256, manifest_sha=inv.manifest_sha256,
                                scorer=gec_engine.score_text)
            primary = old_by_id[case_id]
            validate_primary_binding(primary, selected_row, inv.benchmark_sha256, inv.manifest_sha256)
            row['primary_strict_verdict'] = primary['verdict_provisional']
            row['primary_strict_detection'] = {k: primary[k] for k in ('tp', 'fp', 'fn')}
            rows.append(row)
        directory = out / 'configurations' / cid
        directory.mkdir(parents=True)
        with (directory / 'case_evaluations.jsonl').open('w', encoding='utf-8') as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        summary = aggregate(rows)
        record = {'config_id': cid, 'family': config['family'], 'quant': config['quant'],
                  'summary': summary, 'selection': selection,
                  **{'primary_frozen_' + k: sum(r['primary_strict_detection'][k] for r in rows
                                                if r['condition'] == 'incorrect') for k in ('tp', 'fp', 'fn')}}
        write_json(directory / 'summary.json', record)
        summaries.append(record)
        print(json.dumps({'scope': scope, 'config': cid, 'rows': len(rows),
                          'primary_conditional': summary['gec_conditional_on_observable_text']['primary'],
                          'observable': summary['incorrect_text_observable']}, ensure_ascii=False), flush=True)
    assert_sources_unchanged(sources)
    comparison_csv(out / 'configuration_summary.csv', summaries)
    scope_summary = {'version': VERSION, 'scope': scope, 'analysis_kind': 'POST_HOC_VERSIONED_REEVALUATION',
                     'benchmark_sha256': inv.benchmark_sha256, 'manifest_sha256': inv.manifest_sha256,
                     'human_confirmed': 0, 'original_sources_unchanged': True,
                     'configurations': summaries, 'engine': engine.metadata()}
    write_json(out / 'scope_summary.json', scope_summary)
    outputs = [{'path': reporting._relative(p), 'sha256': reporting.sha256_file(p)}
               for p in sorted(out.rglob('*')) if p.is_file()]
    write_json(out / 'completion_record.json', {'status': 'COMPLETE', 'scope': scope,
               'version': VERSION, 'completed_utc': datetime.now(timezone.utc).isoformat(),
               'response_rows': sum(s['summary']['cases'] for s in summaries),
               'source_inputs': sources, 'output_artifacts': outputs,
               'primary_scores_modified': False, 'gold_modified': False,
               'new_slm_inferences': 0, 'final_test_access': False, 'human_confirmed': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=SCOPES, required=True)
    run(parser.parse_args().scope)
