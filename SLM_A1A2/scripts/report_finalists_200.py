"""Render already-scored finalist measurements as Spanish project documentation.

No scoring, inference, selection of attempts, or modification of source results.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import sys

LAB=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(LAB))
import run_finalists_200 as r


def number(value,digits=3):
    return 'ND' if value is None else f'{value:.{digits}f}'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decision',type=Path,required=True)
    args=parser.parse_args()
    path=r.OUT/'reports/comparison.json';pin=r.sha(path);data=r.read_json(path)
    manifest=r.read_json(r.MANIFEST);decision=r.read_json(args.decision)
    groups=sorted(data['configurations'],key=lambda x:(x['model_id'],x['backend']))
    def model(s):return 'Gemma E2B UD-Q4_K_XL' if s['model_id'].startswith('13-') else 'Qwen3.5 4B Unsloth Q4_K_M'
    lines=['# Gemma E2B y Qwen3.5 4B en 200 preguntas nuevas','',
        'Comparación local de las configuraciones de producto, 17 de noviembre de 2026. '
        'Los mismos 200 textos fueron respondidos por ambos modelos en CPU y Vulkan: **800 respuestas puntuadas**. '
        'A1/A2: 100/100; incorrectos/controles: 150/50; 248 errores intencionales.','',
        decision['summary'],'','## Qué mide la precisión','',
        'El conjunto fue redactado y revisado de forma cruzada por IA, con fuentes congeladas antes de inferir. '
        'Las puntuaciones automáticas contrastan con esas referencias; **no son una evaluación humana de las explicaciones**. '
        'El proxy de caso resuelto exige un JSON utilizable, flag correcto y texto idéntico a una referencia completa licenciada. '
        'Las explicaciones y las sugerencias opcionales requieren revisión del investigador.','',
        '| Configuración | Backend | Proxy caso resuelto /200 | Flag correcto /200 | JSON utilizable /200 | Texto observable en incorrectos /150 |',
        '|---|---|---:|---:|---:|---:|']
    for s in groups:
        t=s['textual_evaluation'];usable=sum(s['app_parser'].get(k,0) for k in ('STRICT','RECOVERED'))
        lines.append(f"| {model(s)} | {s['backend']} | {s['automatic_task_success_proxy']} | {t['flag_correct_observed']} | {usable} | {t['incorrect_text_observable']} |")
    lines+=['','F0.5 da mayor peso a falsas correcciones que a omisiones. Se puntúan ediciones ERRANT en los textos incorrectos; '
        'las falsas alarmas en controles se publican aparte. La referencia primaria mide una reparación mínima; '
        'la mejor referencia completa licenciada admite las alternativas redactadas antes de observar respuestas.','',
        '| Configuración | Backend | Precisión ediciones primaria | Recall primario | F0.5 primario condicional | F0.5 multirreferencia condicional | F0.5 todo gold, no observable=FN |',
        '|---|---|---:|---:|---:|---:|---:|']
    for s in groups:
        t=s['textual_evaluation']['gec_conditional_on_observable_text'];p=t['primary'];m=t['best_full_reference']
        lines.append('| '+' | '.join([model(s),s['backend'],
            *(number(p[k] if p else None,4) for k in ('precision','recall','f0_5')),
            number(m['f0_5'] if m else None,4),number(s['gec_all_gold_missing_as_fn']['f0_5'],4)])+' |')
    lines+=['','## Controles y contrato','',
        '| Configuración | Backend | CTMR /50 (ND) | CFAR /50 (ND) | STRICT | RECOVERED | INCONSISTENT | INVALID_JSON / INVALID_SCHEMA | Ediciones reconstruyen salida /200 | length |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for s in groups:
        t=s['textual_evaluation'];p=s['app_parser']
        lines.append('| '+' | '.join([model(s),s['backend'],
            f"{t['ctmr_modified_observed']} ({t['ctmr_unobservable']})",f"{t['cfar_false_alarm_observed']} ({t['cfar_unobservable']})",
            *(str(p.get(k,0)) for k in ('STRICT','RECOVERED','INCONSISTENT')),
            f"{p.get('INVALID_JSON',0)} / {p.get('INVALID_SCHEMA',0)}",str(t['declarations_coherent_non_noop']),
            str(s['finish_reason'].get('length',0))])+' |')
    lines+=['','CTMR cuenta controles cuyo texto se modificó; CFAR cuenta alarmas de error en controles. ND no equivale a cero. '
        'JSON utilizable describe estructura/coherencia básica, no corrección lingüística. '
        'La generación fue restringida por gramática, igual que en la app; no se atribuye el formato al modelo sin esa ayuda. '
        '`length` indica que se alcanzó el límite y no implica por sí solo JSON incompleto.','',
        '## Tiempo y memoria','',
        '| Configuración | Backend | Mediana (s) | Media (s) | p95 (s) | Tokens salida, media | Tokens/s decode, mediana |',
        '|---|---|---:|---:|---:|---:|---:|']
    for s in groups:
        n=s['native_latency_seconds']
        lines.append('| '+' | '.join([model(s),s['backend'],*(number(n[k]) for k in ('median','mean','p95')),
            number(s['output_tokens']['mean'],1),number(s['decode_tokens_per_second']['median'],1)])+' |')
    lines+=['','| Configuración | Backend | Prefill, mediana (s) | Decode, mediana (s) | Tokens entrada, mediana |',
            '|---|---|---:|---:|---:|']
    for s in groups:
        raw_path=r.OUT/'raw'/(s['config_id']+'.jsonl')
        bound=next(p for p in data['sources'] if Path(p['path']).resolve()==raw_path.resolve())
        assert r.sha(raw_path)==bound['sha256']
        raw=[json.loads(line) for line in raw_path.read_text(encoding='utf-8').splitlines()]
        lines.append('| '+' | '.join([model(s),s['backend'],
            *(number(statistics.median(x[k] for x in raw)) for k in ('prompt_seconds','decode_seconds','prompt_tokens'))])+' |')
    lines+=['','Latencia de generación nativa; carga y calentamiento se informan por separado en el JSON técnico. '
        'Cada petición borra el contexto, sin reutilizar el prefijo. Las respuestas pueden tener distinta longitud; '
        'la latencia combina el coste del backend y la respuesta que realmente produce.','',
        '| Configuración | Backend | Pico RSS árbol (GiB) | Pico privado comprometido (GiB) | Pico VRAM dispositivo (GiB) | VRAM previa a carga (MiB) | Casos con RAM / VRAM | RAM libre mínima sistema (GiB) |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for s in groups:
        m=s['memory'];cov=s['memory_case_coverage']
        conv=lambda k,unit:number(m[k]/unit if m[k] is not None else None)
        before=', '.join(str(x['baseline_gpu'].get('used_mib','ND')) for x in s['load_states'])
        lines.append('| '+' | '.join([model(s),s['backend'],conv('worker_rss_peak_bytes',2**30),
            conv('worker_private_peak_bytes',2**30),conv('device_vram_peak_mib',1024),before,
            f"{cov['worker_rss_peak_bytes']} / {cov['device_vram_peak_mib']}",conv('system_available_min_bytes',2**30)])+' |')
    lines+=['','RSS incluye el worker y sus descendientes, para incluir el intérprete real detrás del lanzador de Windows; '
        'no incluye toda la interfaz Avalonia. La memoria privada comprometida puede no estar residente. '
        'Los picos son observados por muestreo, incluidos carga/calentamiento. '
        'VRAM es la memoria total del dispositivo, también usada por otras aplicaciones; no es una atribución exclusiva al modelo. '
        'La inicialización de plugins puede crear un contexto Vulkan incluso con cero capas de modelo en GPU.','',
        '## Comparaciones pareadas','',
        'Intervalos bootstrap del 95 %, 2000 remuestreos estratificados por nivel/condición; '
        'describen variación entre estos casos sintéticos. No corrigen sesgo del gold IA ni convierten los bloques en un experimento térmico contrabalanceado. '
        'Los intervalos F0.5 usan todo el gold con no observables como FN.','']
    for c in data['bootstrap']['comparisons']:
        title=c['comparison']+' / '+c.get('backend',c.get('model_id',''))
        lines.append('- **'+title+'**: '+ '; '.join(k+' = ['+', '.join(number(x,4) for x in v)+']' for k,v in c.items() if k.endswith('ci95'))+'.')
    lines+=['','| Modelo | RAW idéntico CPU/Vulkan /200 | Texto corregido idéntico observable /200 | Éxito sólo CPU | Éxito sólo Vulkan |',
        '|---|---:|---:|---:|---:|']
    for a in data['cpu_gpu_agreement']:
        lines.append(f"| {a['model_id']} | {a['identical_raw']} | {a['identical_corrected_text_observable']} | {len(a['cpu_success_vulkan_failure'])} | {len(a['vulkan_success_cpu_failure'])} |")
    lines+=['','## Interpretación para la aplicación','',decision['processing'],'',decision['textual_quality'],'',
        decision['default_recommendation'],'',decision['mobile_followup'],'','## Reproducción y límites','',
        'Pesos descargables Q4 de Unsloth y prompts revisados por familia; contexto 2048, 512 tokens, semilla 42, thinking desactivado, llama.cpp b12359. '
        'Qwen tiene un GGUF distinto del convertido local usado en 120. La comparación es entre configuraciones completas de producto. '
        'Hardware y muestreo exacto están en el manifiesto. Una configuración y una secuencia activas por vez.','',
        'El intento inicial interrumpido por codificación queda archivado completo y excluido de la puntuación. '
        'La matriz se reinició con UTF-8 explícito, conservando sin cambios dataset y configuración. '
        '[Incidencia y corrección técnica](finalists_200_execution_20261117.md).','',
        '[Protocolo previo](finalists_200_protocol_20261117.md), [validación del conjunto](../benchmark_200/validation.md), '
        '[resultados JSON](../results_finalists_200_v1/reports/comparison.json), '
        '[tabla CSV](../results_finalists_200_v1/reports/comparison.csv), '
        '[muestra sin puntuar para revisión del investigador](../results_finalists_200_v1/reports/researcher_review_sample.json).','',
        f"Benchmark SHA-256 `{data['benchmark_sha256']}`. Manifiesto `{data['manifest_sha256']}`. JSON de resultados `{pin}`.",'']
    target=LAB/'documentation/finalists_200_results_20261117.md'
    if target.exists():raise ValueError('Report already exists')
    target.write_text('\n'.join(lines),encoding='utf-8')
    assert r.sha(path)==pin
    r.atomic(r.OUT/'reports/presentation_record.json',{'score_sha256':pin,
        'renderer_sha256':r.sha(Path(__file__)),'decision_sha256':r.sha(args.decision),
        'markdown_sha256':r.sha(target),'new_inferences':0})
    print(target)


if __name__=='__main__':main()
