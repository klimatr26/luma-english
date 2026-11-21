"""Sample only the requested app UID, including exec workers hidden by task/children restrictions."""
import argparse,datetime,json,os,pathlib,re,shlex,subprocess,time
p=argparse.ArgumentParser(__doc__)
p.add_argument('--serial',required=True);p.add_argument('--output',type=pathlib.Path,required=True)
p.add_argument('--until-report',type=pathlib.Path,required=True);p.add_argument('--seconds',type=int,default=600)
a=p.parse_args();pkg='org.kevinlima.writinglab'
prefix=[str(pathlib.Path(os.environ['LOCALAPPDATA'])/'Android/Sdk/platform-tools/adb.exe'),'-s',a.serial]
def call(*cmd):
    return subprocess.run([*prefix,*cmd],capture_output=True,timeout=20).stdout.decode('utf-8',errors='replace').strip()
uid=call('shell','run-as',pkg,'id','-u')
if not uid.isdigit():raise RuntimeError('Expected a debuggable app UID.')
a.output.parent.mkdir(parents=True,exist_ok=True);end=time.monotonic()+a.seconds
with a.output.open('w',encoding='utf-8') as out:
    while time.monotonic()<end and not a.until_report.exists():
        owned=call('shell','ps','-U',uid,'-o','PID,PPID,NAME')
        ids=[r.split()[0] for r in owned.splitlines()[1:] if r.split() and r.split()[0].isdigit() and r.split()[-1] in (pkg,'libwriting_worker.so')]
        script='for lp in '+ ' '.join(ids)+'; do echo PROCESS=$lp; cat /proc/$lp/status /proc/$lp/smaps_rollup 2>/dev/null; done'
        raw=call('shell','run-as',pkg,'sh','-c',shlex.quote(script)) if ids else ''
        entries=[]
        for part in raw.split('PROCESS=')[1:]:
            lines=part.splitlines();entry={'pid':int(lines[0])}
            for line in lines[1:]:
                m=re.fullmatch(r'(Name|VmRSS|VmHWM|Pss|SwapPss):\s+(.+)',line)
                if m:entry[m[1]]=m[2]
            entries.append(entry)
        out.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'processes':entries})+'\n');out.flush()
        time.sleep(2)
print('Memory sampling finished.')
