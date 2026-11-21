"""Read-only-source scoring of the frozen 800-answer product comparison."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics as stats
import sys
import uuid

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import run_finalists_200 as run
import evaluate_responses_v2 as v2
import gec_alignment_v2 as gec

OUT = run.OUT


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        for row in rows: f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')


def inventory():
    manifest = run.read_json(run.MANIFEST); msha = run.sha(run.MANIFEST)
    benchmark = run.read_json(manifest['benchmark']); bsha = run.sha(manifest['benchmark'])
    completion = run.read_json(OUT/'completion.json')
    for binding in manifest['source_bindings']:
        if run.sha(binding['path'])!=binding['sha256']: raise ValueError('Changed frozen code/runtime: '+binding['path'])
    if (manifest['benchmark_sha256'] != bsha or completion['benchmark_sha256'] != bsha
            or completion['manifest_sha256'] != msha): raise ValueError('Completion binding mismatch')
    expected = {c['id'] for c in manifest['configurations']}
    if set(completion['configurations']) != expected: raise ValueError('Incomplete configuration matrix')
    cases = {c['id']:c for c in benchmark['cases']}
    sources = [{'path':str(run.MANIFEST),'sha256':msha},
               {'path':manifest['benchmark'],'sha256':bsha},
               {'path':str(OUT/'completion.json'),'sha256':run.sha(OUT/'completion.json')}]
    sources.extend(manifest['source_bindings'])
    data = {}
    for cfg in manifest['configurations']:
        cid = cfg['id']; path = OUT/'raw'/(cid+'.jsonl')
        bound = next(r for r in completion['raw_files'] if Path(r['path']).resolve()==path.resolve())
        if run.sha(path) != bound['sha256']: raise ValueError('Changed RAW after completion')
        raw = jsonl(path); telemetry_path = OUT/'telemetry'/(cid+'.jsonl')
        memories = jsonl(telemetry_path)
        if (len(raw)!=200 or {r['case_id'] for r in raw}!=cases.keys()
                or len(memories)!=200 or {r['case_id'] for r in memories}!=cases.keys()):
            raise ValueError('Incomplete/duplicate case or telemetry matrix')
        memory = {r['case_id']:r for r in memories}
        for row in raw:
            case = cases[row['case_id']]
            if (row['manifest_sha256']!=msha or row['benchmark_sha256']!=bsha or row['config_id']!=cid
                    or row['model_sha256']!=cfg['model_sha256'] or row['attempt']!=1
                    or row['system_prompt_sha256']!=cfg['system_prompt_sha256']
                    or row['user_prompt_sha256']!=hashlib.sha256(run.user_prompt(case).encode()).hexdigest()):
                raise ValueError('RAW identity mismatch')
            mem = memory[row['case_id']]
            if (mem['manifest_sha256']!=msha or mem['config_id']!=cid
                    or mem['response_sha256']!=hashlib.sha256(row['raw_response'].encode()).hexdigest()):
                raise ValueError('Telemetry response binding mismatch')
            row['memory']=mem['memory']
        for source in (path,telemetry_path,OUT/'attempts'/(cid+'.jsonl')):
            sources.append({'path':str(source),'sha256':run.sha(source)})
        for readiness in sorted((OUT/'readiness').glob(cid+'-*.json')):
            if run.read_json(readiness)['manifest_sha256']!=msha:raise ValueError('Stale readiness under same config ID')
            sources.append({'path':str(readiness),'sha256':run.sha(readiness)})
        data[cid]=raw
    return manifest, cases, data, sources


def prepare_parser():
    manifest,cases,data,_=inventory()
    rows=[{'config_id':cid,'case_id':r['case_id'],'raw_response':r['raw_response'],
           'student_text':cases[r['case_id']]['student_text'],'manifest_sha256':run.sha(run.MANIFEST)} for cid,group in data.items() for r in group]
    write_jsonl(OUT/'analysis/app-parser-input.jsonl',rows)
    print(json.dumps({'parser_rows':len(rows)}))


def describe(values):
    import numpy as np
    a=np.asarray(values,dtype=float)
    return {'n':len(values),'mean':float(a.mean()),'median':float(np.median(a)),
            'p95':float(np.quantile(a,.95)),'min':float(a.min()),'max':float(a.max())}


def success(row, parser_status):
    return (parser_status in ('STRICT','RECOVERED') and row['flag_correct'] is True
            and row['corrected_text_equal_licensed_complete_reference'] is True)


def score_group(cfg, raw, cases, bsha, msha, parser):
    evaluated=[]
    for row in raw:
        case=cases[row['case_id']]
        source={**row,'transport':{'latency_seconds_total':row['native_seconds']}}
        result=v2.evaluate_text(case,source,scope='finalists_200_product_v1',
                                benchmark_sha=bsha,manifest_sha=msha,scorer=gec.score_text)
        status=parser[(cfg['id'],case['id'])]
        result['app_parser_status']=status
        result['automatic_task_success_proxy']=success(result,status)
        result['finish_reason']=row['finish_reason']
        result['native_seconds']=row['native_seconds']
        result['output_tokens']=row['output_tokens']
        evaluated.append(result)
    usable=[r['native_seconds'] for r in evaluated if r['app_parser_status'] in ('STRICT','RECOVERED')]
    warmups=[]
    for path in sorted((OUT/'readiness').glob(cfg['id']+'-*.json')):
        warmups.append(run.read_json(path))
    memories=[r['memory'] for r in raw]+[r['load_warmup_memory'] for r in warmups]
    aggregate=v2.aggregate(evaluated)
    conditional=aggregate['gec_conditional_on_observable_text']['primary']
    all_gold=(v2.metrics(conditional['tp'],conditional['fp'],conditional['fn']+aggregate['unobservable_primary_errant_edits'])
              if conditional else v2.metrics(0,0,aggregate['expected_primary_errant_edits']))
    summary={'config_id':cfg['id'],'model_id':cfg['model_id'],'backend':cfg['backend'],
        'model_sha256':cfg['model_sha256'],'model_bytes':cfg['model_bytes'],
        'automatic_task_success_proxy':sum(r['automatic_task_success_proxy'] for r in evaluated),
        'app_parser':dict(Counter(r['app_parser_status'] for r in evaluated)),
        'finish_reason':dict(Counter(r['finish_reason'] for r in raw)),
        'textual_evaluation':aggregate,'gec_all_gold_missing_as_fn':all_gold,
        'native_latency_seconds':describe([r['native_seconds'] for r in raw]),
        'call_wall_seconds':describe([r['wall_seconds'] for r in raw]),
        'usable_latency_seconds':describe(usable) if usable else None,
        'output_tokens':describe([r['output_tokens'] for r in raw]),
        'end_to_end_output_tokens_per_second':describe([r['output_tokens']/r['native_seconds'] for r in raw]),
        'decode_tokens_per_second':describe([r['decoded_tokens']/r['decode_seconds'] for r in raw
                                             if r['decode_seconds']>0]),
        'memory':{key:(min(values) if 'min_' in key else max(values)) if values else None
                  for key in ('worker_rss_peak_bytes','worker_private_peak_bytes','device_vram_peak_mib',
                              'system_available_min_bytes','gpu_temperature_max_c')
                  for values in [[m[key] for m in memories if m.get(key) is not None]]},
        'memory_case_coverage':{key:sum(r['memory'].get(key) is not None for r in raw)
                       for key in ('worker_rss_peak_bytes','worker_private_peak_bytes','device_vram_peak_mib')},
        'load_states':[{'state':r['state'],'baseline_gpu':r['baseline_gpu']} for r in warmups],
        'subgroups':{level:{'textual_evaluation':v2.aggregate([r for r in evaluated if r['level']==level]),
                    'automatic_task_success_proxy':sum(r['automatic_task_success_proxy'] for r in evaluated if r['level']==level)}
                    for level in ('A1','A2')}}
    return summary,evaluated


def bootstrap(groups,cases):
    import numpy as np
    order=sorted(cases)
    strata=[[i for i,cid in enumerate(order) if (cases[cid]['level'],cases[cid]['condition'])==(level,condition)]
            for level in ('A1','A2') for condition in ('incorrect','correct')]
    rng=np.random.default_rng(20261117)
    indexes=np.concatenate([rng.choice(s,size=(2000,len(s)),replace=True) for s in strata],axis=1)
    arrays={}
    for cid,rows in groups.items():
        lookup={r['case_id']:r for r in rows}
        values=[]
        for case_id in order:
            r=lookup[case_id]; g=r['gec']['primary'] if r['condition']=='incorrect' and r['gec'] else {'tp':0,'fp':0,'fn':r['expected_primary_errant_edits']}
            values.append([g['tp'],g['fp'],g['fn'],int(r['automatic_task_success_proxy']),r['native_seconds']])
        a=np.asarray(values,dtype=float); draw=a[indexes]
        sums=draw[:,:,:3].sum(axis=1)
        # The aggregate is equivalent to v2's conditional score when every text is observable.
        f=np.divide(1.25*sums[:,0],1.25*sums[:,0]+.25*sums[:,2]+sums[:,1],
                    out=np.zeros(2000),where=(1.25*sums[:,0]+.25*sums[:,2]+sums[:,1])!=0)
        arrays[cid]={'f0_5_all_gold_missing_as_fn':f,'task_success_rate':draw[:,:,3].mean(axis=1),
                     'latency_median':np.median(draw[:,:,4],axis=1)}
    comparisons=[]
    def interval(a): return [float(x) for x in np.quantile(a,[.025,.975])]
    for backend in ('cpu','vulkan'):
        gemma=next(k for k in groups if k.startswith('13-') and k.endswith('--'+backend))
        qwen=next(k for k in groups if k.startswith('portable-') and k.endswith('--'+backend))
        comparisons.append({'comparison':'Gemma minus Qwen','backend':backend,
            'f0_5_difference_ci95':interval(arrays[gemma]['f0_5_all_gold_missing_as_fn']-arrays[qwen]['f0_5_all_gold_missing_as_fn']),
            'task_success_rate_difference_ci95':interval(arrays[gemma]['task_success_rate']-arrays[qwen]['task_success_rate']),
            'qwen_over_gemma_latency_ratio_ci95':interval(arrays[qwen]['latency_median']/arrays[gemma]['latency_median'])})
    for prefix in ('13-','portable-'):
        cpu=next(k for k in groups if k.startswith(prefix) and k.endswith('--cpu'))
        vk=next(k for k in groups if k.startswith(prefix) and k.endswith('--vulkan'))
        comparisons.append({'comparison':'Vulkan minus CPU','model_id':cpu.rsplit('--',1)[0],
            'f0_5_difference_ci95':interval(arrays[vk]['f0_5_all_gold_missing_as_fn']-arrays[cpu]['f0_5_all_gold_missing_as_fn']),
            'task_success_rate_difference_ci95':interval(arrays[vk]['task_success_rate']-arrays[cpu]['task_success_rate']),
            'cpu_over_vulkan_latency_ratio_ci95':interval(arrays[cpu]['latency_median']/arrays[vk]['latency_median'])})
    return {'replicates':2000,'seed':20261117,'strata':['level','condition'],
            'scope':'conditional on these AI-authored/reviewed synthetic cases','comparisons':comparisons}


def cpu_gpu_agreement(groups):
    result=[]
    for prefix in ('13-','portable-'):
        cpu=next(v for k,v in groups.items() if k.startswith(prefix) and k.endswith('--cpu'))
        vk=next(v for k,v in groups.items() if k.startswith(prefix) and k.endswith('--vulkan'))
        a={r['case_id']:r for r in cpu}; b={r['case_id']:r for r in vk}
        def value(r,key):return r['parsed_response'].get(key) if isinstance(r['parsed_response'],dict) else None
        result.append({'model_id':cpu[0]['config_id'].rsplit('--',1)[0],'cases':200,
            'identical_raw':sum(a[k]['raw_response']==b[k]['raw_response'] for k in a),
            'identical_corrected_text_observable':sum(a[k]['corrected_text_observable'] and b[k]['corrected_text_observable']
                       and value(a[k],'corrected_text')==value(b[k],'corrected_text') for k in a),
            'cpu_success_vulkan_failure':[k for k in a if a[k]['automatic_task_success_proxy'] and not b[k]['automatic_task_success_proxy']],
            'vulkan_success_cpu_failure':[k for k in a if b[k]['automatic_task_success_proxy'] and not a[k]['automatic_task_success_proxy']]})
    return result


def analyze():
    manifest,cases,data,sources=inventory(); msha=run.sha(run.MANIFEST); bsha=manifest['benchmark_sha256']
    parsed_path=OUT/'analysis/app-parser-output.jsonl'; parser_rows=jsonl(parsed_path)
    parser={(r['config_id'],r['case_id']):r['status'] for r in parser_rows}
    if len(parser_rows)!=800 or len(parser)!=800:raise ValueError('Expected exact parser coverage')
    for p in parser_rows:
        r=next(r for r in data[p['config_id']] if r['case_id']==p['case_id'])
        if (p['manifest_sha256']!=msha or p['parser_assembly_sha256']!=manifest['parser_assembly_sha256']
                or p['response_sha256']!=hashlib.sha256(r['raw_response'].encode()).hexdigest()
                or p['student_text_sha256']!=hashlib.sha256(cases[p['case_id']]['student_text'].encode()).hexdigest()):
            raise ValueError('Stale parser output')
    versions=gec.get_engine().metadata()['versions']
    if any(versions.get(k)!=v for k,v in manifest['scorer_versions'].items()):raise ValueError('Changed scorer environment')
    if (OUT/'reports').exists():raise ValueError('Scored report already published')
    stage=OUT/'analysis'/('scoring-'+uuid.uuid4().hex)
    summaries=[]; groups={}
    for cfg in manifest['configurations']:
        summary,rows=score_group(cfg,data[cfg['id']],cases,bsha,msha,parser)
        summaries.append(summary);groups[cfg['id']]=rows
        write_jsonl(stage/(cfg['id']+'.jsonl'),rows)
        print(json.dumps({'scored':cfg['id'],'cases':len(rows)}),flush=True)
    record={'benchmark_sha256':bsha,'manifest_sha256':msha,'configurations':summaries,
            'bootstrap':bootstrap(groups,cases),'cpu_gpu_agreement':cpu_gpu_agreement(groups),
            'scorer':gec.get_engine().metadata(),'human_confirmed_cases':0,
            'sources':sources+[{'path':str(parsed_path),'sha256':run.sha(parsed_path)}]}
    report=stage/'comparison.json'
    run.atomic(report,record)
    with (stage/'comparison.csv').open('x',encoding='utf-8',newline='') as f:
        fields=['config_id','task_success_proxy','flag_correct','f0_5_primary','f0_5_multiref',
                'ctmr','cfar','usable','latency_median_seconds','latency_p95_seconds','rss_peak_bytes','device_vram_peak_mib']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for s in summaries:
            t=s['textual_evaluation'];g=t['gec_conditional_on_observable_text']
            writer.writerow(dict(zip(fields,[s['config_id'],s['automatic_task_success_proxy'],t['flag_correct_observed'],
                g['primary']['f0_5'] if g['primary'] else None,g['best_full_reference']['f0_5'] if g['best_full_reference'] else None,t['ctmr_modified_observed'],t['cfar_false_alarm_observed'],
                sum(s['app_parser'].get(x,0) for x in ('STRICT','RECOVERED')),s['native_latency_seconds']['median'],
                s['native_latency_seconds']['p95'],s['memory']['worker_rss_peak_bytes'],s['memory']['device_vram_peak_mib']],strict=True)))
    # A deterministic sample for researcher review, with all four configurations.
    import random
    selected=[]
    for level in ('A1','A2'):
        for condition,n in [('incorrect',7),('correct',3)]:
            pool=sorted(k for k,c in cases.items() if (c['level'],c['condition'])==(level,condition))
            selected.extend(random.Random('20261117/'+level+'/'+condition).sample(pool,n))
    sample={'purpose':'Researcher review, not completed human scores','cases':[
        {'case':cases[k],'responses':[{key:r[key] for key in ['config_id','raw_response','app_parser_status']}
                      for rows in groups.values() for r in rows if r['case_id']==k],
         'human_verdict':None,'explanation_correct':None,'notes':''} for k in selected]}
    run.atomic(stage/'researcher_review_sample.json',sample)
    for source in sources:
        if run.sha(source['path'])!=source['sha256']:raise ValueError('Source changed during scoring')
    stage.rename(OUT/'reports')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepare-parser-input',action='store_true')
    args=ap.parse_args()
    if args.prepare_parser_input:prepare_parser()
    else:analyze()
