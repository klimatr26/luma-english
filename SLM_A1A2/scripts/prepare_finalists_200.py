"""Validate new held-out sources and freeze the paired product experiment."""
from __future__ import annotations

import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import run_finalists_200 as run


def normalized(text):
    return ' '.join(re.findall(r"[\w']+", text.casefold()))


def validate_cases(cases):
    errors = []
    ids = [c['id'] for c in cases]
    if len(ids) != 200 or len(set(ids)) != 200: errors.append('Expected 200 distinct IDs')
    counts = Counter((c['level'], c['condition']) for c in cases)
    if counts != Counter({('A1','incorrect'):75,('A1','correct'):25,('A2','incorrect'):75,('A2','correct'):25}):
        errors.append(f'Wrong strata: {counts}')
    for level in ('A1','A2'):
        distribution = Counter(len(c['gold']['errors']) for c in cases if c['level']==level and c['condition']=='incorrect')
        if distribution != Counter({1:42,2:20,3:10,4:3}): errors.append(f'{level} wrong error counts: {distribution}')
    for c in cases:
        try:
            gold = c['gold']; text = c['student_text']; spans = []
            words = len(re.findall(r"\b\w+(?:['’]\w+)*\b", text))
            low, high = (15,60) if c['level']=='A1' else (25,100)
            if not low <= words <= high: raise ValueError(f'Words={words} outside {low}..{high}')
            c['length_words'] = words
            if gold['is_correct'] is not (c['condition']=='correct'): raise ValueError('Condition/flag mismatch')
            if c['condition']=='correct' and (gold['errors'] or gold['corrected_text'] != text):
                raise ValueError('Modified/annotated control')
            for e in gold['errors']:
                if not e['original'] or text.count(e['original']) != 1: raise ValueError('Original not unique: '+e['original'])
                if e['original'] == e['correction']: raise ValueError('No-op annotation')
                if not e['explanation'] or not e['type']: raise ValueError('Missing annotation')
                start=text.index(e['original']); spans.append((start,start+len(e['original']),e['correction']))
            spans.sort()
            if any(a[1]>b[0] for a,b in zip(spans,spans[1:])): raise ValueError('Overlapping annotations')
            rebuilt=text
            for start,end,replacement in reversed(spans): rebuilt=rebuilt[:start]+replacement+rebuilt[end:]
            if rebuilt != gold['corrected_text']: raise ValueError('Reconstruction mismatch')
            refs=gold.get('acceptable_alternatives',[])
            if not isinstance(refs,list) or any(not isinstance(r,str) or not r.strip() for r in refs):
                raise ValueError('Invalid complete alternatives')
        except (KeyError,ValueError) as e: errors.append(c.get('id','?')+': '+str(e))
    return errors


def similarities(cases, old):
    normalized_cases = [(c['id'], normalized(c['student_text'])) for c in cases]
    old_cases = [(c['id'], normalized(c['student_text'])) for c in old]
    def trigrams(s):
        words=s.split(); return set(zip(words,words[1:],words[2:]))
    candidates=[]
    for index,(cid,text) in enumerate(normalized_cases):
        for other,otext in normalized_cases[:index] + old_cases:
            ta,tb=trigrams(text),trigrams(otext)
            jac=len(ta&tb)/len(ta|tb) if ta|tb else 0
            ratio=SequenceMatcher(None,text,otext,autojunk=False).ratio()
            if ratio>=.78 or jac>=.45 or text==otext:
                candidates.append({'case_id':cid,'other_id':other,'sequence_ratio':round(ratio,5),
                                   'trigram_jaccard':round(jac,5),'exact':text==otext})
    return candidates


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--freeze',action='store_true')
    a=ap.parse_args()
    root=LAB/'benchmark_200'
    if (LAB/'benchmark_finalists_200_v1.json').exists():
        raise ValueError('Frozen dataset already exists; never overwrite its validation')
    sources=[root/'drafts'/f'{level}_cases.json' for level in ('A1','A2')]
    cases=[c for source in sources for c in run.read_json(source)]
    issues=validate_cases(cases)
    old=[c for name in ('benchmark_smoke_test_v2.json','benchmark_development_120_v1.json')
           for c in run.read_json(LAB/name)['cases']]
    # Prefix old identities because the older phases share their local IDs.
    for index,c in enumerate(old): c['id']=('old40/' if index<40 else 'old120/')+c['id']
    pairs=similarities(cases,old)
    run.atomic(root/'validation.json',{'structural_issues':issues,'similarity_candidates':pairs,
               'sources':[{'path':str(p.relative_to(LAB)),'sha256':run.sha(p)} for p in sources],
               'cases':len(cases),'intentional_errors':sum(len(c['gold']['errors']) for c in cases),
               'similarity_caveat':'String checks do not establish absence of paraphrases.'})
    print(json.dumps({'issues':issues,'similarity_candidates':len(pairs)}))
    if issues: raise SystemExit(1)
    if not a.freeze: return
    review=run.read_json(root/'editorial_resolutions.json')
    expected={p.name:run.sha(p) for p in sources}
    if (review.get('source_sha256')!=expected or review.get('pending_issues')!=[]
            or review.get('complete_independent_ai_review') is not True):
        raise ValueError('Independent editorial resolutions must bind both exact sources')
    for level in ('A1','A2'):
        review_path=root/f'{level}_review_findings.json'
        independent=run.read_json(review_path)
        ids={c['id'] for c in cases if c['level']==level}
        reviewed=independent['reviewed_case_ids']
        if (len(reviewed)!=100 or set(reviewed)!=ids
                or independent['source_sha256']!=expected[f'{level}_cases.json']):
            raise ValueError('Independent review must cover the exact current 100 cases: '+level)
        if review.get('independent_review_sha256',{}).get(review_path.name)!=run.sha(review_path):
            raise ValueError('Independent review hash is not bound: '+level)
        decisions=review.get('editorial_decisions',[])
        for finding in independent['findings']:
            if not any(d['level']==level and d['case_id']==finding['case_id'] and d.get('resolution') for d in decisions):
                raise ValueError('Editorial finding needs a resolution: '+finding['case_id'])
    resolved={(p['case_id'],p['other_id']) for p in review.get('similarity_resolutions',[])}
    if any(p['exact'] or (p['case_id'],p['other_id']) not in resolved for p in pairs):
        raise ValueError('Similarity candidates require explicit resolutions')
    target=LAB/'benchmark_finalists_200_v1.json'
    if target.exists(): raise ValueError('Frozen dataset already exists')
    import platform, psutil
    gpu_info=subprocess.run(['nvidia-smi','--query-gpu=name,uuid,pci.bus_id,driver_version,memory.total',
                            '--format=csv,noheader,nounits'],capture_output=True,text=True,check=True,timeout=15).stdout.strip().splitlines()
    display=json.loads(subprocess.run(['powershell','-NoProfile','-Command',
        'Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID,DriverVersion | ConvertTo-Json -Compress'],
        capture_output=True,text=True,check=True,timeout=20).stdout)
    displays=display if isinstance(display,list) else [display]
    if len(gpu_info)!=1 or len(displays)!=1: raise ValueError('Single-adapter experiment required to bind VRAM telemetry')
    host={'platform':platform.platform(),'cpu_count_logical':psutil.cpu_count(),
          'cpu_count_physical':psutil.cpu_count(logical=False),'ram_total_bytes':psutil.virtual_memory().total,
          'ram_available_before_bytes':psutil.virtual_memory().available,
          'nvidia_gpu':gpu_info[0],'display_adapters':displays}
    run.atomic(target,{'benchmark_id':'writing_a1_a2_finalists_200_v1','version':1,
        'metadata':{'purpose':'Held-out comparison of two frozen product configurations; no prompt tuning',
            'editorial_review':'AI authored and independently AI reviewed; not human validated',
            'source_sha256':expected,'editorial_resolutions_sha256':run.sha(root/'editorial_resolutions.json'),
            'post_output_policy':'Never edit gold after outputs; invalidations apply to all configurations'},
        'cases':cases})
    catalog=run.read_json(LAB/'cross_demo/WritingApp.Shared/Assets/catalog.json')
    prompts=run.read_json(LAB/'cross_demo/WritingApp.Shared/Assets/prompts.json')
    model_ids=['13-gemma4-e2b-ud-q4-k-xl','portable-unsloth-qwen35-4b-q4-k-m']
    native=LAB/'cross_demo/native/artifacts/b12359/win-x64'
    parser_assembly=LAB/'logs/finalists_200_20261117/parser/FinalistsParser.dll'
    code=[LAB/'run_finalists_200.py',Path(__file__),LAB/'documentation/finalists_200_protocol_20261117.md',
          LAB/'scripts/analyze_finalists_200.py',LAB/'scripts/evaluate_responses_v2.py',
          LAB/'scripts/gec_alignment_v2.py',LAB/'scripts/evaluate_benchmark_120.py',
          LAB/'demo/WritingDemo.Core/FeedbackParser.cs',LAB/'demo/WritingDemo.Core/Contracts.cs',
          LAB/'scripts/finalists_parser/Program.cs',LAB/'scripts/finalists_parser/FinalistsParser.csproj',parser_assembly,
          LAB/'requirements-evaluation-v2.txt',
          LAB/'cross_demo/native/src/writing_llama_bridge.cpp',
          LAB/'cross_demo/native/include/writing_llama_bridge.h',
          LAB/'cross_demo/native/include/writing_json_grammar.h',
          LAB/'cross_demo/native/include/writing_prompt_policy.h',LAB/'cross_demo/native/include/vulkan_version_policy.h',
          LAB/'cross_demo/WritingApp.Shared/Assets/prompts.json',LAB/'cross_demo/WritingApp.Shared/Assets/catalog.json']
    bindings=[{'path':str(p.resolve()),'sha256':run.sha(p)} for p in [*sorted(native.glob('*.dll')),*code]]
    configs=[]
    # Four sequential blocks. The same seeded permutation is used in every block.
    order=[(model_ids[0],'Vulkan'),(model_ids[1],'CPU'),(model_ids[0],'CPU'),(model_ids[1],'Vulkan')]
    for mid,backend in order:
        model=next(m for m in catalog if m['Id']==mid)
        prompt=prompts[model['Family']]
        configs.append({'id':mid+'--'+backend.lower(),'model_id':mid,'family':model['Family'],
            'backend':backend,'quantization':model['Quantization'],
            'model_path':str((LAB/'models'/model['RelativePath']).resolve()),
            'model_sha256':model['Sha256'],'model_bytes':model['SizeBytes'],
            'source_url':model['SourceUrl'],'sampling':model['Sampling'],
            'system_prompt':prompt,'system_prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    case_order=[c['id'] for c in cases]; random.Random(20261117).shuffle(case_order)
    run.atomic(run.MANIFEST,{'scope':'finalists_200_product_v1','created_utc':run.now(),
        'authorization':{'source':'Explicit user request of 2026-11-17',
            'scope':'200 same questions for Gemma E2B and Qwen3.5 4B, each CPU and GPU',
            'planned_answers':800,'human_gold_approval':False},
        'benchmark':str(target.resolve()),'benchmark_sha256':run.sha(target),'case_count':200,
        'native_directory':str(native.resolve()),'llama_cpp_commit':'b1b770d90d94cad9e9ea5b993bdbc383a522fb28',
        'context':2048,'seed':42,'thinking':False,'guided_json':True,'retries':0,
        'host':host,
        'parser_assembly':str(parser_assembly.resolve()),'parser_assembly_sha256':run.sha(parser_assembly),
        'scorer_versions':{'errant':'3.0.2','spacy':'3.8.7','en-core-web-sm':'3.8.0'},
        'native_timeout_seconds':120,'warmup_per_load':1,'source_bindings':bindings,
        'case_order':case_order,'configurations':configs})
    print(json.dumps({'frozen_benchmark_sha256':run.sha(target),'manifest_sha256':run.sha(run.MANIFEST)}))


if __name__=='__main__': main()
