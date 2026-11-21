"""Explicitly targeted physical-phone integration; diagnostics APK only, never uninstalls or clears data."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import datetime

APP = Path(__file__).resolve().parents[1]
PACKAGE = 'org.kevinlima.writinglab'

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--mode', choices=['inventory','selection','background-guard','automatic','ui','gemma','minicpm','qwen','gemma-memory','download-start','download-resume'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fresh', action='store_true', help='Archive prior calibration before measuring; retains RAW traces.')
    parser.add_argument('--import-model', help='Inventory only: import a catalogue GGUF from this app\'s technical-imports external staging directory.')
    args = parser.parse_args()
    if args.import_model and args.mode != 'inventory': parser.error('--import-model is only valid with inventory.')
    if args.import_model and not re.fullmatch(r'[A-Za-z0-9-]{1,100}', args.import_model): parser.error('Expected a safe catalogue model ID.')
    if not re.fullmatch(r'[A-Za-z0-9-]{1,60}', args.run) or args.serial.startswith('emulator-'):
        parser.error('Expected a physical serial and a safe, explicit run ID.')
    adb = Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk/platform-tools/adb.exe'
    prefix = [str(adb), '-s', args.serial]
    args.output.mkdir(parents=True, exist_ok=True)
    remote = f'files/phone-verification/{args.run}'
    def run(*command, check=True):
        result = subprocess.run([*prefix, *command], capture_output=True, timeout=30)
        if check and result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace') + result.stdout.decode(errors='replace'))
        return result
    def text(*command, check=True):
        return run(*command, check=check).stdout.decode('utf-8',errors='replace').strip()
    def environment():
        power=text('shell','dumpsys','power')
        policy=text('shell','dumpsys','window','policy')
        focus=text('shell','dumpsys','window')
        return {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'awake':bool(re.search(r'^\s*mWakefulness=Awake\s*$',power,re.M)),
            'keyguard_showing':bool(re.search(r'^\s*(?:showing|mIsShowing)=true\s*$',policy,re.M)),
            'app_focused':any(PACKAGE in line and 'mCurrentFocus=' in line for line in focus.splitlines())}
    if text('get-state') != 'device': raise RuntimeError('ADB device is not ready.')
    if text('shell','getprop','ro.kernel.qemu') == '1': raise RuntimeError('Use verify_android_emulator.py for an emulator.')
    if text('shell','run-as',PACKAGE,'id','-u',check=False).isdigit() is False:
        raise RuntimeError('Install the signed automation APK as an update first.')
    performance=args.mode in ('gemma','minicpm','qwen','gemma-memory','automatic')
    if performance:
        ready=environment()
        (args.output/'environment-before.json').write_text(json.dumps(ready,indent=2)+'\n',encoding='utf-8')
        if not ready['awake'] or ready['keyguard_showing']:
            raise RuntimeError('Unlock the phone and keep the app visible before measuring foreground latency.')
    uid=text('shell','run-as',PACKAGE,'id','-u')
    existing = run('shell','run-as',PACKAGE,'test','-f',f'{remote}/{args.mode}.json',check=False)
    if existing.returncode == 0: raise RuntimeError('This phase already has a report; choose another run ID to preserve evidence.')
    run('shell','am','force-stop',PACKAGE)
    extras=['--es','import-model',args.import_model] if args.import_model else []
    print(text('shell','am','start','-n',PACKAGE+'/.PhoneVerificationActivity','--es','run',args.run,'--es','mode',args.mode,'--ez','fresh',str(args.fresh).lower(),*extras),flush=True)
    deadline = time.monotonic()+1500
    started=time.monotonic(); last=''; next_memory=0; next_status=0; next_environment=time.monotonic()+10; report=None; interrupted=False
    with (args.output/(args.mode+'-memory.jsonl')).open('w',encoding='utf-8') as memory:
        while time.monotonic()<deadline:
            response=run('shell','run-as',PACKAGE,'cat',f'{remote}/{args.mode}.json',check=False)
            if response.returncode==0:
                try: report=json.loads(response.stdout); break
                except json.JSONDecodeError: pass
            if performance and time.monotonic()>=next_environment:
                current=environment()
                with (args.output/'environment.jsonl').open('a',encoding='utf-8') as guard:
                    guard.write(json.dumps(current)+'\n')
                if not current['awake'] or current['keyguard_showing'] or not current['app_focused']:
                    (args.output/'background-interruption.json').write_text(json.dumps(current,indent=2)+'\n',encoding='utf-8')
                    run('shell','am','force-stop',PACKAGE)
                    interrupted=True
                    print('Stopped own diagnostic app: foreground conditions were lost; this attempt cannot supply foreground latency.',flush=True)
                    break
                next_environment=time.monotonic()+10
            if time.monotonic()>=next_status:
                status=text('shell','run-as',PACKAGE,'tail','-n','1',f'{remote}/status.jsonl',check=False)
                if status and status!=last:
                    try: print(json.loads(status)['message'],flush=True)
                    except json.JSONDecodeError: print(status[:180],flush=True)
                    last=status
                next_status=time.monotonic()+2
            if time.monotonic()>=next_memory:
                main_pid=text('shell','pidof',PACKAGE,check=False).split()
                if main_pid and main_pid[0].isdigit():
                    pid=main_pid[0]
                    owned=text('shell','ps','-U',uid,'-o','PID,PPID,NAME',check=False)
                    pids=[row.split()[0] for row in owned.splitlines()[1:] if row.split() and row.split()[0].isdigit()
                        and (row.split()[-1]==PACKAGE or row.split()[-1]=='libwriting_worker.so')]
                    script='for lp in '+ ' '.join(pids)+'; do echo PROCESS=$lp; cat /proc/$lp/status /proc/$lp/smaps_rollup 2>/dev/null; done'
                    snapshot=text('shell','run-as',PACKAGE,'sh','-c',shlex.quote(script),check=False)
                    entries=[]
                    for part in snapshot.split('PROCESS=')[1:]:
                        lines=part.splitlines(); entry={'pid':int(lines[0])}
                        for line in lines[1:]:
                            match=re.fullmatch(r'(Name|VmRSS|VmHWM|Pss|SwapPss):\s+(.+)',line)
                            if match: entry[match[1]]=match[2]
                        entries.append(entry)
                    memory.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_s':time.monotonic()-started,'stage':last,'processes':entries})+'\n');memory.flush()
                next_memory=time.monotonic()+3
            time.sleep(.35)
    for name in [args.mode+'.json',args.mode+'-checkpoint.json',args.mode+'-history.json','status.jsonl','history.json','history.csv','download-ticket.json']:
        result=run('exec-out','run-as',PACKAGE,'cat',remote+'/'+name,check=False)
        if result.returncode==0:
            if name.endswith('.json'):
                try: json.loads(result.stdout)
                except (json.JSONDecodeError,UnicodeDecodeError): continue
            elif name.endswith('.csv') and not result.stdout.startswith(b'id,activity_id,'): continue
            elif name.endswith('.jsonl') and not result.stdout.startswith(b'{'): continue
            (args.output/name).write_bytes(result.stdout)
    # Only the foreground app is captured; no global logcat or unrelated app contents.
    foreground=text('shell','dumpsys','window',check=False)
    if any(PACKAGE in line and 'mCurrentFocus=' in line for line in foreground.splitlines()):
        shot=run('exec-out','screencap','-p',check=False).stdout
        if shot.startswith(b'\x89PNG\r\n\x1a\n'): (args.output/(args.mode+'.png')).write_bytes(shot)
    print(json.dumps({'mode':args.mode,'success':report.get('success') if report else None,
        'checks':len(report.get('checks',[])) if report else 0,'exception':report.get('exception') if report else 'No report'},ensure_ascii=False),flush=True)
    if interrupted or not report or report.get('success') is not True: raise RuntimeError('Phone phase did not pass. Inspect retained evidence.')

if __name__=='__main__': main()
