"""Read-only final audit of collected execution, prompts, offload and integrity."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
sys.path.insert(0, str(LAB))
import run_benchmark_120 as runner


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8*1024**2), b''):
            digest.update(data)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def audit():
    manifest_path = LAB/'manifests/experiment_manifest_120.json'
    manifest = read(manifest_path)
    msha = sha(manifest_path)
    require(msha == '8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255', 'Manifest changed')
    require(sha(LAB/'run_benchmark_120.py') == read(LAB/'manifests/execution_start_record_20261011.json')['runners_sha256']['run_benchmark_120.py'], 'Shared runner changed during execution')
    old_evaluator = subprocess.run(['git','cat-file','blob','179bb78:SLM_A1A2/scripts/evaluate_benchmark_120.py'], cwd=REPO, capture_output=True, check=True).stdout
    require(hashlib.sha256(old_evaluator).hexdigest() == sha(LAB/'scripts/evaluate_benchmark_120.py'), 'Primary evaluator changed after preparation')
    scopes = []
    for name, filename, cases_count in [('results_120','benchmark_development_120_v1.json',120), ('results_40_current_16','benchmark_smoke_test_v2.json',40)]:
        root = LAB/name
        benchmark = read(LAB/filename)
        cases = {c['id']:c for c in benchmark['cases']}
        report = read(root/'reports/scope_summary.json')
        require(report['coverage']['status']=='COMPLETE' and report['coverage']['verified_final_raw_cases']==cases_count*16, 'Incomplete verified scope')
        prompt_count, raw_count, nonempty_reasoning, malformed_reasoning = 0,0,0,0
        offload, finishes, source_hashes = [], {}, []
        for cfg in manifest['configurations']:
            cid = cfg['config_id']
            pp = root/'parsed'/cid/'responses.jsonl'
            ap = root/'raw'/cid/'attempts.jsonl'
            rows = [json.loads(l) for l in pp.read_text(encoding='utf-8').splitlines() if l.strip()]
            attempts = [json.loads(l) for l in ap.read_text(encoding='utf-8').splitlines() if l.strip()]
            require(len(rows)==cases_count and len(attempts)==cases_count, 'Unexpected retry or duplicate rows')
            require({r['case_id'] for r in rows} == set(cases), 'Case matrix differs')
            for row in rows:
                _, expected = runner.build_messages(benchmark['system_prompt'], benchmark['user_prompt_template'], cases[row['case_id']])
                require(row['prompt_sha256']==expected, 'Prompt fingerprint differs from canonical builder')
                require(not {'gold','errors','corrected_text'} & set(row['payload_keys']), 'Gold request key found')
                require(row['transport']['outcome']=='ok' and row['manifest_sha256']==msha, 'Transport/manifest identity failure')
                prompt_count += 1
                finish = row['transport']['finish_reason']
                finishes[finish] = finishes.get(finish,0)+1
            for attempt in attempts:
                require(attempt['http_status']==200 and attempt['attempt']==1 and attempt['disposition']=='final', 'Non-initial/failing attempt found')
                body = json.loads(attempt['response_body_exact'])
                message = body['choices'][0]['message']
                reasoning = message.get('reasoning_content')
                nonempty_reasoning += isinstance(reasoning,str) and bool(reasoning.strip())
                malformed_reasoning += reasoning is not None and not isinstance(reasoning,str)
                raw_count += 1
            log_path = root/'logs'/f'server_{cid}.log'
            log = log_path.read_text(encoding='utf-8',errors='replace')
            matches = re.findall(r'offloaded\s+(\d+)\s*/\s*(\d+)\s*layers', log, re.I)
            require(matches and all(int(n)>0 for n,total in matches) and 'cuda' in log.lower(), 'Missing actual CUDA/offload evidence')
            offload.append({'config_id':cid,'layers':matches[-1][0]+'/'+matches[-1][1], 'server_log_sha256':sha(log_path)})
            source_hashes.extend({'path':str(p.relative_to(REPO)).replace('\\','/'),'sha256':sha(p)} for p in (pp,ap))
        require(nonempty_reasoning==0 and malformed_reasoning==0,'Non-thinking response contract anomaly')
        run = read(root/'reports/run_summary.json')
        require(not run['rate_limited_stop'] and all(r['failed']==0 and r['retried']==0 for r in run['per_config']), 'Run failures/retries found')
        scopes.append({'scope':name,'rows':prompt_count,'exact_raw_attempts':raw_count,'canonical_prompt_fingerprints_verified':prompt_count,
                       'nonempty_reasoning_contents':nonempty_reasoning,'malformed_reasoning_contents':malformed_reasoning,
                       'finish_reasons':finishes,'actual_cuda_offload':offload,'source_hashes':source_hashes,
                       'benchmark_sha256':sha(LAB/filename),'started_utc':run['started_utc'],'completed_utc':run['completed_utc']})
    baseline = read(LAB/'benchmark_40_archive/phase1_baseline_hashes.json')
    git_blobs = 0
    for record in baseline['files']:
        p = LAB/record['path']
        require(p.stat().st_size==record['size_bytes'] and sha(p)==record['sha256'], 'Historical artifact changed')
        blob = subprocess.run(['git','cat-file','blob','f2eb39e:'+str(p.relative_to(REPO)).replace('\\','/')],cwd=REPO,capture_output=True)
        if blob.returncode==0:
            require(hashlib.sha256(blob.stdout).hexdigest()==record['sha256'],'Historical Git blob differs')
            git_blobs += 1
    runtime = read(LAB/'manifests/runtime_asset_hashes_120.json')
    for entry in runtime['files']:
        p = REPO/entry['path']
        require(p.stat().st_size==entry['size_bytes'] and sha(p)==entry['sha256'],'Runtime asset changed')
    for c in manifest['configurations']:
        require(runner.check_port_free(c['port']) is None, 'Owned port still in use')
    result = {'status':'EXECUTION_COMPLETE_AUDITED','audited_utc':datetime.now(timezone.utc).isoformat(),
              'manifest_sha256':msha,'total_new_rows':sum(s['rows'] for s in scopes),'scopes':scopes,
              'primary_evaluator_unchanged_from_preparation':True,'historical_artifacts_byte_identical':len(baseline['files']),
              'historical_git_blobs_byte_identical':git_blobs,'recorded_runtime_assets_hash_verified':len(runtime['files']),
              'all16_model_ports_free_after_cleanup':True,'final_test_access':False,
              'audit_code_sha256':sha(Path(__file__))}
    (LAB/'manifests/execution_completion_audit_20261011.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='scopes'}))


if __name__=='__main__':
    audit()
