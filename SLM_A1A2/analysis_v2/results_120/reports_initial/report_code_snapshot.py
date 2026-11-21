"""Tables/subgroups from completed v2 analysis; no inference or human scores."""
import csv
import json
from pathlib import Path

import evaluate_responses_v2 as v2
import prepare_human_review_v2 as review
import report_execution_results as reporting


def create(scope):
    inv, rows = review.load_bound_rows(scope)
    out = v2.OUTPUT / scope / 'reports'
    if out.exists():
        raise ValueError('Refusing to overwrite existing v2 reports')
    out.mkdir(parents=True)
    source_summary = reporting.load_json(v2.OUTPUT / scope / 'scope_summary.json')
    subgroup_rows, categories = [], []
    for cid in inv.config_ids:
        group = [r for r in rows if r['config_id'] == cid]
        dimensions = {
            'level': lambda r: r['level'],
            'gold_error_count': lambda r: str(r['intentional_gold_errors']),
        }
        # Word counter belongs to the frozen benchmark utility; the grouping is descriptive.
        from evaluate_benchmark_120 import count_words
        dimensions['word_length'] = lambda r: 'short_<=30' if count_words(r['student_text']) <= 30 \
            else 'medium_31-60' if count_words(r['student_text']) <= 60 else 'long_>60'
        for dimension, key in dimensions.items():
            values = sorted({key(r) for r in group})
            for value in values:
                subset = [r for r in group if key(r) == value]
                summary = v2.aggregate(subset)
                metric = summary['gec_conditional_on_observable_text']['primary']
                subgroup_rows.append({'config_id': cid, 'dimension': dimension, 'value': value,
                    'cases': len(subset), 'incorrect_cases_expected': summary['incorrect_cases_expected'],
                    'incorrect_text_observable': summary['incorrect_text_observable'],
                    **{k: metric[k] if metric else None for k in ('tp', 'fp', 'fn', 'precision', 'recall', 'f0_5')},
                    'recall_all_primary_gold_unobservable_as_missed':
                        summary['recall_all_primary_gold_unobservable_as_missed'],
                    'controls': summary['controls_expected'],
                    'ctmr_modified': summary['ctmr_modified_observed'],
                    'ctmr_unknown': summary['ctmr_unobservable'],
                    'cfar_alarm': summary['cfar_false_alarm_observed'],
                    'cfar_unknown': summary['cfar_unobservable']})
        counts = {}
        for row in group:
            if row['condition'] != 'incorrect' or row['gec'] is None:
                continue
            for category, values in row['gec']['primary']['category_lineage'].items():
                bucket = counts.setdefault(category, {'tp': 0, 'fp': 0, 'fn': 0})
                for field in bucket:
                    bucket[field] += values[field]
        for category, values in sorted(counts.items()):
            categories.append({'config_id': cid, 'errant_category': category, **v2.metrics(**values),
                               'scope': 'incorrect cases with observable corrected_text'})
    for filename, data in [('subgroup_summary.csv', subgroup_rows), ('errant_categories.csv', categories)]:
        with (out / filename).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]))
            writer.writeheader(); writer.writerows(data)
    lines = ['# Evaluación textual v2 — ' + scope, '',
             'Análisis posterior de respuestas existentes. No es confirmación humana de feedback.',
             'F0.5 es condicional al texto observable; leer su cobertura y el recall sobre todo el gold.',
             'Ref. primaria y mejores alternativas completas se publican aparte; no hay nuevas referencias.', '',
             '| Configuración | Texto observable incorrectos | P | R | F0.5 primaria | F0.5 multirref. | R todo gold | CTMR (ND) | CFAR (ND) | Esquema | JSON estricto | Flag incorrectos correcto |',
             '|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|']
    for record in source_summary['configurations']:
        s = record['summary']; primary = s['gec_conditional_on_observable_text']['primary']
        multi = s['gec_conditional_on_observable_text']['best_full_reference']
        fmt = lambda x: f'{x:.4f}' if x is not None else 'ND'
        metric = {k: primary[k] if primary else None for k in ('precision', 'recall', 'f0_5')}
        lines.append('| ' + ' | '.join([record['config_id'],
            f"{s['incorrect_text_observable']}/{s['incorrect_cases_expected']}",
            *(fmt(metric[k]) for k in ('precision', 'recall', 'f0_5')),
            fmt(multi['f0_5'] if multi else None), fmt(s['recall_all_primary_gold_unobservable_as_missed']),
            f"{s['ctmr_modified_observed']}/{s['controls_expected']} ({s['ctmr_unobservable']})",
            f"{s['cfar_false_alarm_observed']}/{s['controls_expected']} ({s['cfar_unobservable']})",
            str(s['schema_valid']), str(s['strict_json_compliant']),
            f"{s['incorrect_flag_correct_observed']}/{s['incorrect_cases_expected']}"]) + ' |')
    lines += ['', 'ND es no observable, no cero. CFAR usa una OR de tres valores: una alarma explícita se observa aunque el otro campo sea desconocido. Preservación completa v2 se refiere a texto/flag/lista de ediciones; el esquema se mide por separado.',
              'Las 31 categorías intencionales y los tipos extraídos por ERRANT son taxonomías distintas. errant_categories.csv conserva la segunda sin forzar una equivalencia. Los subgrupos no se suman como observaciones independientes. Grupos de longitud sin casos no tienen rendimiento observado.',
              'La referencia primaria contiene ' + str(source_summary['configurations'][0]['summary']['expected_primary_errant_edits']) + ' ediciones ERRANT en los textos incorrectos esperados; la agrupación puede diferir de las anotaciones intencionales.',
              'Las métricas originales siguen en sus carpetas intactas. El CSV configuration_summary.csv del nivel superior conserva TP/FP/FN/F0.5 originales junto a la evaluación v2 para comparar definiciones, sin confundirlas.',
              '', '## Reproducción', '', '```powershell',
              f'.\.venv_eval_v2\Scripts\python.exe scripts/report_evaluation_v2.py --scope {scope}',
              '```', 'Los scripts rechazan sobrescribir una entrega ya preparada. Para otro análisis, usar una versión explícita y conservar la anterior.', '']
    (out / 'scope_report.md').write_text('\n'.join(lines), encoding='utf-8')
    v2.write_json(out / 'report_record.json', {'scope': scope,
        'input_completion_sha256': reporting.sha256_file(v2.OUTPUT / scope / 'completion_record.json'),
        'report_code_sha256': reporting.sha256_file(Path(__file__)),
        'human_confirmed': 0, 'new_slm_inferences': 0,
        'artifacts': [{'path': reporting._relative(p), 'sha256': reporting.sha256_file(p)}
                      for p in sorted(out.iterdir()) if p.is_file()]})
    print(json.dumps({'scope': scope, 'subgroup_rows': len(subgroup_rows), 'errant_category_rows': len(categories)}))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=v2.SCOPES, required=True)
    create(parser.parse_args().scope)
