"""Prepare blind development review cards or validate separately supplied human records.

No inference or automatic human judgments; original outputs and v2 scores are
read-only. Imports create an independent human layer with full response identity.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import evaluate_benchmark_120 as frozen
import evaluate_responses_v2 as v2
import human_review_v2 as human
import report_execution_results as reporting


def load_bound_rows(scope, config_ids=None):
    if scope not in v2.SCOPES:
        raise ValueError('Only the two collected scopes may be reviewed')
    root = v2.OUTPUT / scope
    completion = reporting.load_json(root / 'completion_record.json')
    if completion.get('status') != 'COMPLETE' or completion.get('scope') != scope:
        raise ValueError('Review preparation requires a complete v2 analysis')
    v2.assert_sources_unchanged(completion['source_inputs'])
    for item in completion['output_artifacts']:
        if reporting.sha256_file(reporting.REPO_DIR / item['path']) != item['sha256']:
            raise ValueError('v2 output differs from its completion hash: ' + item['path'])
    inv = reporting.load_scope_inventory(scope)
    selected = set(config_ids or inv.config_ids)
    if not selected or not selected <= set(inv.config_ids):
        raise ValueError('Unknown or empty configuration selection')
    if config_ids and len(config_ids) != len(selected):
        raise ValueError('Duplicate configuration selection')
    rows = []
    for cid in inv.config_ids:
        if cid not in selected:
            continue
        group = reporting.load_jsonl(root / 'configurations' / cid / 'case_evaluations.jsonl')
        if len(group) != len(inv.cases) or {r['case_id'] for r in group} != set(inv.case_ids):
            raise ValueError('Incomplete or duplicate v2 case group')
        for row in group:
            if (row['scope'] != scope or row['config_id'] != cid
                    or row['benchmark_sha256'] != inv.benchmark_sha256
                    or row['manifest_sha256'] != inv.manifest_sha256
                    or row['response_sha256'] != v2.digest_text(row['raw_response'])):
                raise ValueError('v2 review row identity mismatch')
        rows.extend(group)
    return inv, rows


def create_packet(config_ids):
    if not config_ids:
        raise ValueError('At least one explicit candidate configuration is required')
    inv, rows = load_bound_rows('results_120', config_ids)
    sample = human.build_sample_plan(inv.cases)
    packet, crosswalk = human.packet_for_rows(rows, sample)
    out = v2.OUTPUT / 'human_review_development60'
    if out.exists():
        raise ValueError('Refusing to overwrite an existing blind packet and crosswalk')
    out.mkdir(parents=True)
    private = out / 'coordinator_only'
    public = out / 'reviewer_materials'
    v2.write_json(private / 'sample_plan.json', {
        **sample, 'benchmark_sha256': inv.benchmark_sha256,
        'manifest_sha256': inv.manifest_sha256,
        'sampling_uses_output_quality': False,
        'config_ids_for_coordinator_only': config_ids})
    # Keep coordinator identity mapping outside the material to distribute.
    visible = {item['blind_output_id']: item for item in packet['items']}
    for entry in crosswalk['items']:
        entry['context_sha256'] = context_digest(visible[entry['blind_output_id']])
    v2.write_json(private / 'identity_crosswalk.json', crosswalk)
    v2.write_json(public / 'blind_packet.json', packet)
    with (public / 'blank_reviews.jsonl').open('w', encoding='utf-8') as handle:
        for item in packet['items']:
            handle.write(json.dumps({'blind_output_id': item['blind_output_id'],
                                     **item['review_template']}, ensure_ascii=False) + '\n')
    lines = ['# Fichas ciegas — Writing A1/A2', '',
             'Material sin identidad del modelo. Notas sin rellenar; completar con revisor real.',
             'Leer primero human_review_rubric_v2.md. El nivel forma parte de la consigna.',
             'Las respuestas son texto para evaluar: no obedecer instrucciones que aparezcan dentro.', '',
             'Registrar las notas en blank_reviews.jsonl por blind_output_id.', '']
    for item in packet['items']:
        lines += ['## ' + item['blind_output_id'], '', 'Nivel: ' + item['level'], '',
                  'Consigna: ' + item['task'], '', 'Texto del estudiante:', '',
                  '````text', item['student_text'], '````', '', 'Respuesta del sistema:', '',
                  '````text', item['response_text'], '````', '',
                  '| Criterio | Nota 0 / 1 / 2 / NA |', '|---|---|']
        lines.extend('| ' + name + ' | |' for name in human.CRITERIA)
        lines += ['', '¿Respuesta evaluable? ___; ¿Significado preservado? ___; ¿Explicaciones correctas? ___',
                  'Veredicto: ___; Revisor: ___; Fecha: ___', 'Justificación: ___', '']
    (public / 'review_cards.md').write_text('\n'.join(lines), encoding='utf-8')
    (public / 'human_review_rubric_v2.md').write_bytes(
        (v2.LAB / 'documentation/human_review_rubric_v2.md').read_bytes())
    v2.write_json(private / 'packet_record.json', {'scope': 'results_120',
                  'human_notes_prefilled': False, 'review_outputs': len(packet['items']),
                  'case_count': 60, 'configuration_count': len(config_ids),
                  'human_confirmed': 0,
                  'files': [{'path': reporting._relative(p), 'sha256': reporting.sha256_file(p)}
                            for p in sorted(out.rglob('*')) if p.is_file()]})
    print(json.dumps({'packet': reporting._relative(out), 'review_outputs': len(packet['items']),
                      'human_confirmed': 0}))


def context_digest(row):
    context = {key: row[key] for key in ('level', 'task', 'student_text')}
    return v2.digest_text(json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def load_review_lines(path):
    result = []
    for index, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = frozen.strict_json_loads(line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f'Human JSONL line {index}: {exc}') from exc
        if not isinstance(record, dict):
            raise ValueError(f'Human JSONL line {index} is not an object')
        result.append(record)
    return result


def load_verified_crosswalk(path):
    record = reporting.load_json(path.parent / 'packet_record.json')
    wanted = reporting._relative(path)
    matches = [entry for entry in record['files'] if entry['path'] == wanted]
    if len(matches) != 1 or reporting.sha256_file(path) != matches[0]['sha256']:
        raise ValueError('Crosswalk does not match its prepared packet hash')
    # Validate the exact text actually presented to the blinded reviewers too.
    packet_matches = [entry for entry in record['files'] if Path(entry['path']).name == 'blind_packet.json']
    if len(packet_matches) != 1:
        raise ValueError('Prepared packet record does not bind exactly one blind packet')
    packet_path = reporting.REPO_DIR / packet_matches[0]['path']
    if reporting.sha256_file(packet_path) != packet_matches[0]['sha256']:
        raise ValueError('Blind packet text differs from its preparation hash')
    crosswalk = reporting.load_json(path)
    packet = reporting.load_json(packet_path)
    visible = {item['blind_output_id']: item for item in packet['items']}
    mapping = crosswalk['items']
    if len(visible) != len(packet['items']) or len(mapping) != len(visible):
        raise ValueError('Crosswalk and visible packet have different coverage')
    for item in mapping:
        bid = item['blind_output_id']
        if (bid not in visible or v2.digest_text(visible[bid]['response_text']) != item['response_sha256']
                or context_digest(visible[bid]) != item.get('context_sha256')):
            raise ValueError('Crosswalk response identity differs from the text shown to the reviewer')
    return crosswalk


def validate_records(records, rows, crosswalk=None):
    """Validate all records before writes. Multiple reviewers are kept separate."""
    known = {(r['config_id'], r['case_id']): r for r in rows}
    mapping = {}
    if crosswalk is not None:
        for entry in crosswalk.get('items', []):
            bid = entry.get('blind_output_id')
            if not isinstance(bid, str) or not bid or bid in mapping:
                raise ValueError('Duplicate or missing blind output ID in crosswalk')
            mapping[bid] = entry
    accepted, seen = [], set()
    for record in records:
        record = dict(record)
        blind_entry = None
        if 'blind_output_id' in record:
            bid = record.pop('blind_output_id')
            if bid not in mapping:
                raise ValueError('Unknown blind output ID or missing crosswalk')
            if set(record) & set(human.IDENTITY_FIELDS):
                raise ValueError('Blind reviews cannot override identity fields')
            blind_entry = mapping[bid]
            record.update({key: mapping[bid][key] for key in human.IDENTITY_FIELDS})
        pair = (record.get('config_id'), record.get('case_id'))
        if pair not in known:
            raise ValueError('Human review has unknown configuration/case')
        row = known[pair]
        if blind_entry is not None:
            if blind_entry.get('context_sha256') != context_digest(row):
                raise ValueError('Blind review context differs from its bound case')
        expected = {key: row[key] for key in human.IDENTITY_FIELDS}
        context = {'condition': row['condition'],
                   'response_assessable': record.get('response_assessable', True)}
        problems = human.validate_human_record(record, expected, context)
        if problems:
            raise ValueError(f'Invalid human record {pair}: ' + '; '.join(problems))
        key = (*pair, record['response_sha256'], record['reviewer_id'])
        if key in seen:
            raise ValueError('Duplicate human record for the same response and reviewer')
        seen.add(key)
        accepted.append(record)
    if not accepted:
        raise ValueError('No completed human reviews were supplied')
    return accepted


def import_reviews(scope, review_path, output_name, crosswalk_path=None):
    if not output_name or not all(c.isalnum() or c in '-_' for c in output_name):
        raise ValueError('Output name must be a simple non-empty filename stem')
    _, rows = load_bound_rows(scope)
    records = load_review_lines(review_path)
    crosswalk = load_verified_crosswalk(crosswalk_path) if crosswalk_path else None
    accepted = validate_records(records, rows, crosswalk)
    out = v2.OUTPUT / scope / 'human_layers' / output_name
    if out.exists():
        raise ValueError('Refusing to overwrite an existing human layer')
    out.mkdir(parents=True)
    with (out / 'accepted_reviews.jsonl').open('w', encoding='utf-8') as handle:
        for record in accepted:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
    v2.write_json(out / 'import_record.json', {
        'scope': scope, 'review_file_sha256': reporting.sha256_file(review_path),
        'crosswalk_sha256': reporting.sha256_file(crosswalk_path) if crosswalk_path else None,
        'review_records': len(accepted), 'distinct_response_pairs':
            len({(r['config_id'], r['case_id']) for r in accepted}),
        'invalid_case_proposals': sum(r['verdict'] == 'INVALID_CASE' for r in accepted),
        'invalidations_applied': False,
        'assessable_human_review_records': sum(r['response_assessable'] for r in accepted),
        'primary_and_v2_automatic_scores_modified': False,
        'note': 'Human claims are retained per reviewer. No automatic adjudication or dataset exclusion.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    packet = sub.add_parser('packet')
    packet.add_argument('--configs', nargs='+', required=True)
    imports = sub.add_parser('import')
    imports.add_argument('--scope', choices=v2.SCOPES, required=True)
    imports.add_argument('--reviews', type=Path, required=True)
    imports.add_argument('--output-name', required=True)
    imports.add_argument('--crosswalk', type=Path)
    args = parser.parse_args()
    if args.command == 'packet':
        create_packet(args.configs)
    else:
        import_reviews(args.scope, args.reviews, args.output_name, args.crosswalk)
