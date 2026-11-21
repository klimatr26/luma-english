"""Paired 200-case product-profile CPU/Vulkan experiment; no historical writes.

The native worker receives only system/user prompts, never the gold reference.
One returned answer per case; no quality retries. Native crashes/timeouts stop
the run after preserving the attempt. RAW is fsynced before progress updates.
"""
from __future__ import annotations

import argparse
import ctypes as C
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

LAB = Path(__file__).resolve().parent
MANIFEST = LAB / 'manifests/finalists_200_20261117.json'
OUT = LAB / 'results_finalists_200_v1'
CASE_COUNT = 200
MODELS = ('13-gemma4-e2b-ud-q4-k-xl', 'portable-unsloth-qwen35-4b-q4-k-m')
SYNTHETIC = {'id': 'readiness-outside-test', 'level': 'A1',
             'task': 'Write two sentences about something you own.',
             'student_text': 'I has a green notebook. I use it every morning.'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


def append(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n')
        f.flush(); os.fsync(f.fileno())


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def user_prompt(case):
    return f"Level: {case['level']}\nTask: {case['task']}\nStudent text: {case['student_text']}"


class NativeBridge:
    def __init__(self, directory):
        self.directory = str(Path(directory).resolve())
        self.search = os.add_dll_directory(self.directory)
        self.dll = C.CDLL(str(Path(self.directory) / 'writing_llama_bridge.dll'))
        self.handle = C.c_void_p()
        self.dll.wg_abi_version.restype = C.c_int32
        if self.dll.wg_abi_version() != 2: raise ValueError('Unexpected native ABI')
        i, f, p, u = C.c_int32, C.c_float, C.c_void_p, C.c_uint32
        self.dll.wg_load.argtypes = [C.c_char_p, i, i, C.c_char_p, p, C.POINTER(p), p, u]
        self.dll.wg_load.restype = i
        self.dll.wg_generate.argtypes = [p, C.c_char_p, C.c_char_p, i, i, i, f, f, i, f, f, f, f,
                                       p, C.POINTER(p), C.POINTER(u), C.POINTER(i), C.POINTER(C.c_double), p, u]
        self.dll.wg_generate.restype = i
        self.dll.wg_free_text.argtypes = [p]
        self.dll.wg_unload.argtypes = [p]
        self.dll.wg_get_last_metrics.argtypes = [p, C.POINTER(i), C.POINTER(i), C.POINTER(i),
                                               C.POINTER(C.c_double), C.POINTER(C.c_double), C.POINTER(i)]
        self.dll.wg_get_last_metrics.restype = i
        for name in ['wg_copy_backend', 'wg_copy_device', 'wg_copy_fallback_reason']:
            getattr(self.dll, name).argtypes = [p, p, u]
        self.dll.wg_get_offloaded_layers.argtypes = [p]
        self.dll.wg_get_offloaded_layers.restype = i

    def copy(self, name):
        result = C.create_string_buffer(4096)
        getattr(self.dll, name)(self.handle, result, len(result))
        return result.value.decode('utf-8', errors='replace')

    def load(self, config, context):
        error = C.create_string_buffer(4096)
        started = time.perf_counter()
        status = self.dll.wg_load(config['model_path'].encode(), 1 if config['backend'] == 'Vulkan' else 2,
                                  context, self.directory.encode(), None, C.byref(self.handle), error, len(error))
        if status != 0: raise RuntimeError(f'Native load {status}: {error.value.decode(errors="replace")}')
        actual = self.copy('wg_copy_backend')
        if actual != config['backend']: raise RuntimeError(f'Unexpected fallback: {actual}')
        return {'backend': actual, 'device': self.copy('wg_copy_device'),
                'fallback': self.copy('wg_copy_fallback_reason'),
                'offloaded_layers': self.dll.wg_get_offloaded_layers(self.handle),
                'load_seconds': time.perf_counter() - started}

    def generate(self, config, request):
        s = config['sampling']; output = C.c_void_p(); size = C.c_uint32()
        finish = C.c_int32(-1); seconds = C.c_double(); error = C.create_string_buffer(4096)
        started = time.perf_counter()
        status = self.dll.wg_generate(self.handle, config['system_prompt'].encode(), request['user'].encode(),
                    42, s['MaxTokens'], 1, s['Temperature'], s['TopP'], s['TopK'], s['MinP'],
                    s['RepeatPenalty'], s['PresencePenalty'], s['FrequencyPenalty'], None,
                    C.byref(output), C.byref(size), C.byref(finish), C.byref(seconds), error, len(error))
        elapsed = time.perf_counter() - started
        try: raw = C.string_at(output, size.value).decode('utf-8') if output else ''
        finally:
            if output: self.dll.wg_free_text(output)
        pt, ot, dt, closed = C.c_int32(), C.c_int32(), C.c_int32(), C.c_int32()
        ps, ds = C.c_double(), C.c_double()
        self.dll.wg_get_last_metrics(self.handle, C.byref(pt), C.byref(ot), C.byref(dt),
                                    C.byref(ps), C.byref(ds), C.byref(closed))
        return {'status': status, 'error': error.value.decode(errors='replace') or None,
                'raw_response': raw, 'finish_reason': {0: 'stop', 1: 'length', 2: 'cancelled'}.get(finish.value, 'error'),
                'native_seconds': seconds.value, 'wall_seconds': elapsed,
                'prompt_tokens': pt.value, 'output_tokens': ot.value, 'decoded_tokens': dt.value,
                'prompt_seconds': ps.value, 'decode_seconds': ds.value,
                'closed_thinking_prefill': bool(closed.value)}

    def close(self):
        if self.handle: self.dll.wg_unload(self.handle); self.handle = C.c_void_p()


def worker(manifest_path, config_id):
    manifest = read_json(manifest_path)
    config = next(c for c in manifest['configurations'] if c['id'] == config_id)
    bridge = NativeBridge(manifest['native_directory'])
    try:
        for line in sys.stdin:
            req = json.loads(line)
            if req['op'] == 'load': result = bridge.load(config, manifest['context'])
            elif req['op'] == 'generate': result = bridge.generate(config, req)
            elif req['op'] == 'exit': break
            else: raise ValueError('Unknown operation')
            print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    finally: bridge.close()


def gpu():
    try:
        r = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu,uuid',
                            '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
        lines = r.stdout.strip().splitlines()
        if len(lines) != 1: raise ValueError('This experiment requires one NVIDIA adapter')
        fields = [x.strip() for x in lines[0].split(',')]
        used, total, temp, utilization = map(int, fields[:4])
        return {'used_mib': used, 'total_mib': total, 'temperature_c': temp, 'utilization_percent': utilization,
                'uuid': fields[4], 'timestamp_utc': now()}
    except Exception as e: return {'unavailable_reason': str(e)}


class Monitor:
    """Observed peaks, not allocator-exact maxima. VRAM is device-wide under WDDM."""
    def __init__(self, pid):
        import psutil
        self.psutil = psutil; self.process = psutil.Process(pid)
        self.lock = threading.Lock(); self.stop_event = threading.Event()
        self.latest_gpu = gpu(); self.stats = {}; self.reset()
        self.ram_thread = threading.Thread(target=self.ram_loop, daemon=True)
        self.gpu_thread = threading.Thread(target=self.gpu_loop, daemon=True)
        self.ram_thread.start(); self.gpu_thread.start()

    def reset(self):
        with self.lock:
            self.stats = {'worker_rss_peak_bytes': None, 'worker_private_peak_bytes': None,
                          'system_available_min_bytes': None, 'device_vram_peak_mib': None,
                          'gpu_temperature_max_c': None, 'gpu_utilization_max_percent': None,
                          'ram_samples': 0, 'vram_samples': 0, 'gpu_samples': []}
        self.sample_ram(); self.sample_gpu(gpu())

    def sample_ram(self):
        try:
            processes = [self.process, *self.process.children(recursive=True)]
            memories = []
            for process in processes:
                try: memories.append(process.memory_info())
                except self.psutil.Error: pass
            available = self.psutil.virtual_memory().available
            with self.lock:
                self.stats['ram_samples'] += 1
                for key, value in [('worker_rss_peak_bytes', sum(m.rss for m in memories)),
                                   ('worker_private_peak_bytes', sum(getattr(m, 'private', m.pagefile) for m in memories))]:
                    if value is not None: self.stats[key] = max(self.stats[key] or 0, value)
                current = self.stats['system_available_min_bytes']
                self.stats['system_available_min_bytes'] = available if current is None else min(available, current)
        except self.psutil.Error: pass

    def sample_gpu(self, value):
        with self.lock:
            self.latest_gpu = value
            if 'used_mib' in value:
                self.stats['vram_samples'] += 1
                self.stats['device_vram_peak_mib'] = max(self.stats['device_vram_peak_mib'] or 0, value['used_mib'])
                self.stats['gpu_temperature_max_c'] = max(self.stats['gpu_temperature_max_c'] or 0, value['temperature_c'])
                self.stats['gpu_utilization_max_percent'] = max(self.stats['gpu_utilization_max_percent'] or 0, value['utilization_percent'])
                self.stats['gpu_samples'].append(value)

    def ram_loop(self):
        while not self.stop_event.wait(.05): self.sample_ram()

    def gpu_loop(self):
        while not self.stop_event.wait(1): self.sample_gpu(gpu())

    def finish(self):
        self.sample_ram(); self.sample_gpu(gpu())
        with self.lock: return {**self.stats, 'gpu_samples': list(self.stats['gpu_samples'])}

    def close(self):
        self.stop_event.set(); self.ram_thread.join(2); self.gpu_thread.join(10)


class Process:
    def __init__(self, manifest_path, config_id, log):
        log.parent.mkdir(parents=True, exist_ok=True)
        self.log = log.open('a', encoding='utf-8')
        self.process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker',
                          '--manifest', str(manifest_path), '--config', config_id],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                          text=True, encoding='utf-8', bufsize=1,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.replies = queue.Queue()
        def read():
            try:
                for line in self.process.stdout: self.replies.put(line)
            finally: self.replies.put(None)
        self.thread = threading.Thread(target=read, daemon=True); self.thread.start()

    def send(self, request, timeout):
        self.process.stdin.write(json.dumps(request, ensure_ascii=False) + '\n'); self.process.stdin.flush()
        try: line = self.replies.get(timeout=timeout)
        except queue.Empty: raise TimeoutError(f'Native worker exceeded {timeout}s') from None
        if line is None: raise RuntimeError(f'Native worker exited: {self.process.poll()}')
        return json.loads(line)

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('{"op":"exit"}\n'); self.process.stdin.flush()
                self.process.wait(5)
            except (OSError, subprocess.TimeoutExpired):
                import psutil
                try:
                    owned = psutil.Process(self.process.pid)
                    for child in owned.children(recursive=True):
                        try: child.kill()
                        except psutil.Error: pass
                except psutil.Error: pass
                self.process.kill(); self.process.wait(10)
        self.log.close()


def bindings(manifest, manifest_path, approved_sha):
    if manifest['benchmark_sha256'] != approved_sha or sha(manifest['benchmark']) != approved_sha:
        raise ValueError('Exact frozen benchmark SHA required')
    data = read_json(manifest['benchmark'])
    if len(data['cases']) != CASE_COUNT or len(manifest['configurations']) != 4:
        raise ValueError('Expected exactly 200 cases and four configurations')
    expected={(model,backend) for model in MODELS for backend in ('CPU','Vulkan')}
    if ({(c['model_id'],c['backend']) for c in manifest['configurations']} != expected
            or len({c['id'] for c in manifest['configurations']}) != 4):
        raise ValueError('Expected the exact two-model CPU/Vulkan matrix')
    if (manifest['context']!=2048 or manifest['seed']!=42 or manifest['thinking'] is not False
            or manifest['guided_json'] is not True or manifest['retries']!=0):
        raise ValueError('Product generation settings must remain frozen')
    if len({x['id'] for x in data['cases']}) != CASE_COUNT: raise ValueError('Duplicate case IDs')
    case_ids = {x['id'] for x in data['cases']}
    if len(manifest['case_order']) != CASE_COUNT or set(manifest['case_order']) != case_ids:
        raise ValueError('Case order must be an exact permutation of all 200 IDs')
    for rec in manifest['source_bindings']:
        if sha(rec['path']) != rec['sha256']: raise ValueError('Source/runtime changed: ' + rec['path'])
    done = set()
    for c in manifest['configurations']:
        key = (c['model_path'], c['model_sha256'])
        if key not in done:
            if sha(key[0]) != key[1]: raise ValueError('Model SHA mismatch')
            done.add(key)
    return data, sha(manifest_path)


def execute(args):
    manifest = read_json(args.manifest)
    data, manifest_sha = bindings(manifest, args.manifest, args.benchmark_sha256)
    import msvcrt
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'runner.lock').open('a+b') as lock:
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        try: return run(args, manifest, manifest_sha, data)
        finally:
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def run(args, manifest, manifest_sha, data):
    cases = {c['id']: c for c in data['cases']}; completed = []
    for cfg in manifest['configurations']:
        raw_path = OUT / 'raw' / (cfg['id'] + '.jsonl')
        journal_path = OUT / 'attempts' / (cfg['id'] + '.jsonl')
        telemetry_path = OUT / 'telemetry' / (cfg['id'] + '.jsonl')
        rows = []
        if raw_path.exists():
            rows = [json.loads(line) for line in raw_path.read_text(encoding='utf-8').splitlines()]
        seen = set()
        for row in rows:
            if (row['manifest_sha256'] != manifest_sha or row['benchmark_sha256'] != manifest['benchmark_sha256']
                    or row['config_id'] != cfg['id'] or row['model_sha256'] != cfg['model_sha256']
                    or row['case_id'] not in cases or row['case_id'] in seen):
                raise ValueError('Mixed, stale, or duplicate RAW')
            seen.add(row['case_id'])
            if row['status'] != 0: raise ValueError('A technical failed attempt requires explicit resolution; no automatic retry')
        journal = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines()] if journal_path.exists() else []
        started_ids = set()
        for event in journal:
            cid = event['case_id']
            if (event['config_id'] != cfg['id'] or event['manifest_sha256'] != manifest_sha or
                    event['benchmark_sha256'] != manifest['benchmark_sha256'] or cid in started_ids or cid not in cases):
                raise ValueError('Stale or duplicate attempt journal')
            started_ids.add(cid)
        if started_ids != seen:
            raise ValueError('Unclosed attempt or RAW without start journal; explicit resolution required, never automatic replay')
        recorded = [json.loads(line) for line in telemetry_path.read_text(encoding='utf-8').splitlines()] if telemetry_path.exists() else []
        measured_ids=set()
        raw_lookup={row['case_id']:row for row in rows}
        for measurement in recorded:
            cid=measurement['case_id']
            if (cid in measured_ids or cid not in raw_lookup or measurement['config_id']!=cfg['id']
                    or measurement['manifest_sha256']!=manifest_sha
                    or measurement['response_sha256']!=hashlib.sha256(raw_lookup[cid]['raw_response'].encode()).hexdigest()):
                raise ValueError('Duplicate, stale, or unbound telemetry')
            measured_ids.add(cid)
        for cid in seen-measured_ids:
            # Preserve the existing answer; never regenerate it to recover a missed measurement.
            append(telemetry_path, {'config_id':cfg['id'],'case_id':cid,'manifest_sha256':manifest_sha,
                'response_sha256':hashlib.sha256(raw_lookup[cid]['raw_response'].encode()).hexdigest(),
                'measurement_lost_due_to_interruption':True,'memory':{}})
        if len(seen) == CASE_COUNT:
            completed.append(cfg['id']); continue
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        baseline = gpu()
        log_path=OUT / 'logs' / f"{cfg['id']}-{timestamp}.log"
        process = Process(args.manifest, cfg['id'], log_path)
        monitor = Monitor(process.process.pid)
        try:
            state = process.send({'op': 'load'}, 180)
            if log_path.exists():
                log=log_path.read_text(encoding='utf-8',errors='replace')
                placed=re.findall(r'offloaded (\d+)/(\d+) layers to GPU',log)
                state['offload_evidence_log']=list(map(int,placed[-1])) if placed else None
                device_lines=[line for line in log.splitlines() if 'using device Vulkan' in line]
                state['physical_gpu_log']=device_lines[-1] if device_lines else None
                if cfg['backend']=='Vulkan':
                    if not placed or placed[-1][0]!=placed[-1][1]:raise RuntimeError('Full Vulkan offload not confirmed in native log')
                    pci=':'.join(manifest['host']['nvidia_gpu'].split(',')[2].strip().lower().split(':')[-2:])
                    if not state['physical_gpu_log'] or pci not in state['physical_gpu_log'].lower():
                        raise RuntimeError('Vulkan physical adapter does not match VRAM adapter')
            warmup = process.send({'op': 'generate', 'user': user_prompt(SYNTHETIC)}, 120)
            atomic(OUT / 'readiness' / f"{cfg['id']}-{timestamp}.json", {
                'manifest_sha256': manifest_sha, 'state': state, 'outside_benchmark': True,
                'synthetic': SYNTHETIC, 'warmup': warmup, 'baseline_gpu': baseline,
                'load_warmup_memory': monitor.finish(), 'worker_pid': process.process.pid})
            if warmup['status'] != 0: raise RuntimeError('Synthetic readiness failed')
            print(json.dumps({'config': cfg['id'], 'ready': state, 'already_complete': len(seen)}), flush=True)
            for cid in manifest['case_order']:
                if cid in seen: continue
                case = cases[cid]; prompt = user_prompt(case)
                started = now()
                append(journal_path, {'case_id': cid, 'config_id': cfg['id'], 'attempt': 1,
                       'benchmark_sha256': manifest['benchmark_sha256'], 'manifest_sha256': manifest_sha,
                       'started_utc': started})
                monitor.reset()
                try:
                    answer = process.send({'op': 'generate', 'user': prompt}, 120)
                except Exception as e:
                    answer = {'status': -999, 'error': repr(e), 'raw_response': '', 'finish_reason': 'technical_error'}
                row = {'benchmark_sha256': manifest['benchmark_sha256'], 'manifest_sha256': manifest_sha,
                       'model_sha256': cfg['model_sha256'], 'config_id': cfg['id'], 'case_id': cid,
                       'timestamp_utc': started, 'seed': 42, 'attempt': 1,
                       'system_prompt_sha256': cfg['system_prompt_sha256'],
                       'user_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                       **answer}
                append(raw_path, row); rows.append(row); seen.add(cid)
                append(telemetry_path, {'config_id': cfg['id'], 'case_id': cid, 'manifest_sha256': manifest_sha,
                       'response_sha256': hashlib.sha256(answer['raw_response'].encode()).hexdigest(),
                       'memory': monitor.finish()})
                if answer['status'] != 0: raise RuntimeError('Technical failure preserved; stopping all configurations')
                if len(seen) % 10 == 0:
                    atomic(OUT / 'progress.json', {'updated_utc': now(), 'config': cfg['id'],
                           'cases_complete': len(seen), 'completed_configs': completed})
                    print(json.dumps({'config': cfg['id'], 'completed': len(seen),
                           'last_seconds': answer['native_seconds'], 'last_finish': answer['finish_reason']}), flush=True)
            if seen != cases.keys(): raise ValueError('Incomplete configuration coverage')
            completed.append(cfg['id'])
        finally:
            process.close(); monitor.close()
    atomic(OUT / 'completion.json', {'manifest_sha256': manifest_sha, 'benchmark_sha256': manifest['benchmark_sha256'],
           'completed_utc': now(), 'configurations': completed,
           'raw_files': [{'path': str(OUT / 'raw' / (cid + '.jsonl')),
                          'sha256': sha(OUT / 'raw' / (cid + '.jsonl'))} for cid in completed]})
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=MANIFEST)
    p.add_argument('--worker', action='store_true'); p.add_argument('--config')
    p.add_argument('--execute', action='store_true'); p.add_argument('--benchmark-sha256')
    a = p.parse_args()
    if a.worker:
        worker(a.manifest, a.config); return 0
    if not a.execute or not a.benchmark_sha256:
        p.error('--execute and --benchmark-sha256 are required for the authorized 800-answer experiment')
    return execute(a)


if __name__ == '__main__':
    raise SystemExit(main())
