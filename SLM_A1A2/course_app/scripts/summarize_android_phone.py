"""Summarize the retained F8 phone integration phases without changing model outputs."""
import argparse,datetime,hashlib,json,pathlib,statistics

p=argparse.ArgumentParser(__doc__);p.add_argument('--directory',type=pathlib.Path,required=True);a=p.parse_args();root=a.directory
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def date(value):return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def kb(value):return int(value.split()[0])
def memory(folder,mode):
    path=root/folder/(mode+'-memory.jsonl')
    statuses=[json.loads(x) for x in (root/folder/'status.jsonl').read_text().splitlines() if x]
    statuses=[s for s in statuses if s['mode']==mode]
    stages=[];current=None
    for s in statuses:
        msg=s['message']
        if msg.startswith('MEMORY_ROUTE ') or msg.startswith('CACHE_REUSE '):current=None
        elif msg.startswith('Calibrando CPU:') or msg.startswith('Cargando CPU'):current='CPU'
        elif msg.startswith('Calibrando Vulkan/') or msg.startswith('Cargando Vulkan/'):current='Vulkan'
        stages.append((date(s['utc']),current))
    result={backend:{'samples':0,'peak_pss_mib':0,'peak_rss_mib':0,'peak_swap_pss_mib':0} for backend in ['CPU','Vulkan']}
    # Early controller files did not have UTC per sample. On Windows, birth time
    # anchors the original file opening; stage boundaries remain sampled estimates.
    anchor=getattr(path.stat(),'st_birthtime',path.stat().st_ctime)
    for line in path.read_text().splitlines():
        row=json.loads(line);when=date(row['utc']) if row.get('utc') else anchor+row['elapsed_s']
        eligible=[s for s in stages if s[0]<=when-2]
        if not eligible or eligible[-1][1] is None:continue
        group=result[eligible[-1][1]]
        workers=[x for x in row['processes'] if x.get('Name')=='libwriting_work']
        if not workers:continue
        group['samples']+=1
        for key,out in [('Pss','peak_pss_mib'),('VmRSS','peak_rss_mib'),('SwapPss','peak_swap_pss_mib')]:
            group[out]=max(group[out],sum(kb(x[key]) for x in row['processes'] if key in x)/1024)
    return result

models=[]
for name,folder,mem_folder,mem_mode in [('Gemma E2B UD-Q4','gemma-foreground','gemma-memory','gemma-memory'),('Qwen 3.5 4B Q4','qwen-foreground','qwen-foreground','qwen')]:
    kind='gemma' if name.startswith('Gemma') else 'qwen';doc=read(root/folder/(kind+'.json'));profile=doc['profile'];trials=profile['Trials']
    cpu=next(x for x in trials if x['Placement']['GpuLayers']==0);gpu=next(x for x in trials if x['Placement']['GpuLayers']>0)
    c=statistics.median(s['Seconds'] for s in cpu['Samples']);g=statistics.median(s['Seconds'] for s in gpu['Samples'])
    models.append({'model':name,'model_id':doc['model_id'],'model_sha256':doc['model_sha256'],'context':2048,'seed':42,'max_tokens':512,
        'cpu_median_s':c,'vulkan_median_s':g,'cpu_over_vulkan_speedup':c/g,'latency_reduction_percent':100*(1-g/c),
        'cpu_tokens':[s['Tokens'] for s in cpu['Samples']],'vulkan_tokens':[s['Tokens'] for s in gpu['Samples']],
        'cpu_parsers':[s['ParserStatus'] for s in cpu['Samples']],'vulkan_parsers':[s['ParserStatus'] for s in gpu['Samples']],
        'selected':doc['engine']['Backend'],'gpu_layers_tested':gpu['Placement']['GpuLayers'],
        'prepare_with_calibration_s':doc['prepare_including_verification_and_calibration_seconds'],
        'course_sessions':[{'usable':s['Usable'],'is_correct':s['Attempts'][0]['Parsed']['Value']['IsCorrect'],
            'parser':s['Attempts'][0]['Parsed']['Status'],'seconds':s['Attempts'][0]['Output']['Seconds'],
            'decode_tokens_s':s['Attempts'][0]['Output']['Metrics']['DecodeTokensPerSecond']} for s in doc['sessions']],
        'memory':memory(mem_folder,mem_mode)})
inventory=read(root/'inventory/inventory.json')
cache=read(root/'cache-reuse/gemma.json')
profiles=[read(f) for f in (root/'phone-data/files/adaptive-profiles').glob('*.json') if not f.name.startswith('trace-')]
same=any(x.get('Key')==cache['profile']['Key'] and x.get('DateUtc')==cache['profile']['DateUtc'] for x in profiles)
assert same and not any('Calibrando ' in s['message'] for s in map(json.loads,(root/'cache-reuse/status.jsonl').read_text().splitlines()))
result={'purpose':'PHONE_INTEGRATION_NOT_BENCHMARK','firmware':inventory['firmware'],'api':inventory['api'],
    'device':inventory['device'],'models':models,'ui_checks':len(read(root/'ui-foreground/ui.json')['checks']),
    'ui_success':read(root/'ui-foreground/ui.json')['success'],'physical_keyboard_opened':read(root/'ui-foreground/ui.json')['keyboard_opened'],
    'cache_reused_same_key_and_date':same,'cache_prepare_s':cache['prepare_including_verification_and_calibration_seconds'],
    'legacy_data_backup_byte_identical':(root/'previous-sessions-and-profiles.tar').read_bytes()==(root/'after-sessions-and-profiles.tar').read_bytes(),
    'downloads':[read(root/f/'download-resume.json') for f in ['download-resume','background-resume']],
    'memory_notes':['PSS/RSS are sampled sums of the app and native worker, not total unified CPU+GPU memory.',
        'KGSL GPU allocation counters were inaccessible. No dedicated VRAM peak is claimed.',
        'Earlier rows use Windows file birth time plus elapsed time; backend transitions have sampling uncertainty.',
        'Gemma memory was measured in a later technical phase, separate from foreground latency medians.']}
(root/'summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
