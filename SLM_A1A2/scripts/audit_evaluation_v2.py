"""Audit v2 artifacts and byte equality to the prior local Git delivery."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import evaluate_responses_v2 as v2
import human_review_v2 as human
import prepare_human_review_v2 as prep
import report_execution_results as reporting

BASELINE = 'feb818d'


def audit():
    source_paths, output_paths = {}, {}
    scope_checks = []
    for scope in v2.SCOPES:
        inv, rows = prep.load_bound_rows(scope)
        root = v2.OUTPUT / scope
        completion = reporting.load_json(root / 'completion_record.json')
        for item in completion['source_inputs']:
            source_paths[item['path']] = item['sha256']
        for item in completion['output_artifacts']:
            output_paths[item['path']] = item['sha256']
        report_record = reporting.load_json(root / 'reports/report_record.json')
        if report_record['input_completion_sha256'] != reporting.sha256_file(root / 'completion_record.json'):
            raise ValueError('Report completion binding differs')
        if report_record['report_code_sha256'] != reporting.sha256_file(v2.LAB / 'scripts/report_evaluation_v2.py'):
            raise ValueError('Canonical report code binding differs')
        for item in report_record['artifacts']:
            if reporting.sha256_file(reporting.REPO_DIR / item['path']) != item['sha256']:
                raise ValueError('Derived report hash mismatch')
            output_paths[item['path']] = item['sha256']
        if len(rows) != len(inv.cases) * len(inv.configurations) or any(r['human_confirmed'] for r in rows):
            raise ValueError('Unexpected row coverage or synthetic human confirmation')
        summary = reporting.load_json(root / 'scope_summary.json')
        if sum(r['summary']['cases'] for r in summary['configurations']) != len(rows):
            raise ValueError('Summary row count differs')
        for config in summary['configurations']:
            subset = [r for r in rows if r['config_id'] == config['config_id']]
            if config['summary'] != v2.aggregate(subset):
                raise ValueError('Summary is not reproducible from its case rows')
        scope_checks.append({'scope': scope, 'rows': len(rows), 'configurations': len(inv.configurations),
                            'human_confirmed': 0, 'sources_unchanged': True})
    preserved_git = []
    new_files, ignored_raw = [], []
    new_source_paths = {
        'SLM_A1A2/scripts/evaluate_responses_v2.py', 'SLM_A1A2/scripts/gec_alignment_v2.py',
        'SLM_A1A2/scripts/human_review_v2.py', 'SLM_A1A2/documentation/evaluation_v2_protocol.md',
        'SLM_A1A2/documentation/human_review_rubric_v2.md',
        'SLM_A1A2/benchmark_120/human_review_v2_schema.json', 'SLM_A1A2/requirements-evaluation-v2.txt',
    }
    for relative, wanted_sha in source_paths.items():
        blob = subprocess.run(['git', 'show', BASELINE + ':' + relative],
                              cwd=reporting.REPO_DIR, capture_output=True, check=False)
        if blob.returncode == 0:
            if hashlib.sha256(blob.stdout).hexdigest() != wanted_sha:
                raise ValueError('Original tracked input differs from baseline Git bytes: ' + relative)
            preserved_git.append(relative)
        elif relative in new_source_paths:
            new_files.append(relative)
        elif '/raw/' in relative or '/parsed/' in relative:
            ignored_raw.append(relative)
        else:
            raise ValueError('Unaccounted source absent from prior Git delivery: ' + relative)
    packet_root = v2.OUTPUT / 'human_review_development60'
    private = packet_root / 'coordinator_only'
    crosswalk = prep.load_verified_crosswalk(private / 'identity_crosswalk.json')
    packet = reporting.load_json(packet_root / 'reviewer_materials/blind_packet.json')
    sample = reporting.load_json(private / 'sample_plan.json')
    plan_again = human.build_sample_plan(reporting.load_scope_inventory('results_120').cases)
    if sample['selected_case_ids'] != plan_again['selected_case_ids']:
        raise ValueError('Human sample differs from fixed seeded selection')
    if len(packet['items']) != 180 or len(crosswalk['items']) != 180:
        raise ValueError('Human packet count differs')
    forbidden = set(human.IDENTITY_FIELDS) | {'condition', 'gold', 'primary_strict_verdict', 'human_confirmed'}
    for item in packet['items']:
        if forbidden & set(item) or any(value is not None for key, value in item['review_template'].items()
                                      if key != 'schema_version'):
            raise ValueError('Human packet leaks model/case identity or contains prefilled judgment')
        if item['level'] not in ('A1', 'A2'):
            raise ValueError('Missing level for human appropriateness criterion')
    # Blank cards cannot enter the human layer as completed human judgments.
    blank = prep.load_review_lines(packet_root / 'reviewer_materials/blank_reviews.jsonl')
    _, candidate_rows = prep.load_bound_rows('results_120', sample['config_ids_for_coordinator_only'])
    try:
        prep.validate_records(blank, candidate_rows, crosswalk)
    except ValueError:
        blank_rejected = True
    else:
        raise ValueError('Blank templates were incorrectly accepted as human reviews')
    result = {'status': 'COMPLETE_AUDITED', 'audited_utc': datetime.now(timezone.utc).isoformat(),
              'version': v2.VERSION, 'analysis_kind': 'POST_HOC_VERSIONED_REEVALUATION',
              'scopes': scope_checks, 'new_slm_inferences': 0, 'final_test_access': False,
              'human_confirmed': 0, 'human_packet_outputs': 180, 'human_packet_cases': 60,
              'blank_human_templates_rejected': blank_rejected,
              'baseline_git_commit': BASELINE, 'original_git_inputs_byte_identical': preserved_git,
              'new_analysis_sources': new_files, 'raw_parsed_bound_to_git_preserved_source_index': ignored_raw,
              'source_inputs': [{'path': p, 'sha256': sha} for p, sha in sorted(source_paths.items())],
              'derived_artifacts': [{'path': p, 'sha256': sha} for p, sha in sorted(output_paths.items())],
              'audit_code_sha256': reporting.sha256_file(Path(__file__))}
    v2.write_json(v2.LAB / 'manifests/evaluation_v2_audit_20261011.json', result)
    print(json.dumps({'status': result['status'], 'rows': sum(s['rows'] for s in scope_checks),
                      'git_preserved_inputs': len(preserved_git), 'output_hashes': len(output_paths),
                      'blank_human_templates_rejected': blank_rejected, 'new_slm_inferences': 0}))


if __name__ == '__main__':
    audit()
