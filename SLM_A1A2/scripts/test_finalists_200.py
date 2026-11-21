"""Synthetic safety checks; never loads a model or scores benchmark outputs."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_finalists_200 as r


class Gates(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='finalists-safety-')
        self.root=Path(self.temp.name)
        self.cases=[{'id':str(i),'level':'A1','task':'A synthetic fixture.',
                     'student_text':'My fictional text.','gold':{'secret':'NEVER_SEND_GOLD'}} for i in range(200)]
        self.path=self.root/'benchmark.json';r.atomic(self.path,{'cases':self.cases})
        self.pin=r.sha(self.path)
        self.model=self.root/'model-fixture.txt';self.model.write_text('No model weights.')
        self.configs=[{'id':m+'--'+b.lower(),'model_id':m,'backend':b,'model_path':str(self.model),
                       'model_sha256':r.sha(self.model),'system_prompt_sha256':'synthetic'}
                      for m in r.MODELS for b in ('CPU','Vulkan')]
        self.manifest={'benchmark':str(self.path),'benchmark_sha256':self.pin,
                       'configurations':self.configs,'case_order':[c['id'] for c in self.cases],
                       'source_bindings':[],'context':2048,'seed':42,'thinking':False,'guided_json':True,'retries':0}
        self.mp=self.root/'manifest.json';r.atomic(self.mp,self.manifest)
    def tearDown(self):self.temp.cleanup()
    def test_case_order_must_cover_all_cases(self):
        bad=copy.deepcopy(self.manifest);bad['case_order'][-1]=bad['case_order'][0]
        with self.assertRaisesRegex(ValueError,'permutation'):r.bindings(bad,self.mp,self.pin)
    def test_no_duplicate_configuration_matrix(self):
        bad=copy.deepcopy(self.manifest);bad['configurations'][3]=bad['configurations'][0]
        with self.assertRaisesRegex(ValueError,'matrix'):r.bindings(bad,self.mp,self.pin)
    def test_gold_never_in_worker_prompt(self):
        prompt=r.user_prompt(self.cases[0])
        self.assertNotIn('NEVER_SEND_GOLD',prompt)
        self.assertEqual(prompt,'Level: A1\nTask: A synthetic fixture.\nStudent text: My fictional text.')
    def test_modified_model_rejected(self):
        self.model.write_text('Changed fixture.')
        with self.assertRaisesRegex(ValueError,'Model SHA'):r.bindings(self.manifest,self.mp,self.pin)
    def test_unclosed_start_prevents_native_restart(self):
        out=self.root/'out';cfg=self.configs[0];msha=r.sha(self.mp)
        r.append(out/'attempts'/(cfg['id']+'.jsonl'),{'case_id':'0','config_id':cfg['id'],
                'manifest_sha256':msha,'benchmark_sha256':self.pin})
        with patch.object(r,'OUT',out),patch.object(r,'Process') as native:
            with self.assertRaisesRegex(ValueError,'Unclosed attempt'):r.run(None,self.manifest,msha,{'cases':self.cases})
            native.assert_not_called()

    def test_raw_is_durable_before_telemetry_and_bad_json_is_not_retried(self):
        out=self.root/'out';manifest={**self.manifest,'configurations':self.configs[:1]}
        cfg=self.configs[0];msha=r.sha(self.mp);owner=self
        class FakeProcess:
            def __init__(self,*args):self.process=type('P',(),{'pid':123})();self.generations=0
            def send(self,req,timeout):
                if req['op']=='load':return {'backend':'CPU'}
                if self.generations:
                    starts=[json.loads(l) for l in (out/'attempts'/(cfg['id']+'.jsonl')).read_text().splitlines()]
                    owner.assertEqual(len(starts),self.generations)
                self.generations+=1
                return {'status':0,'raw_response':'invalid JSON on purpose','finish_reason':'length',
                        'native_seconds':.01,'output_tokens':3}
            def close(self):pass
        class FakeMonitor:
            def __init__(self,pid):self.count=0
            def reset(self):pass
            def finish(self):
                if self.count:
                    raw=out/'raw'/(cfg['id']+'.jsonl')
                    owner.assertEqual(len(raw.read_text().splitlines()),self.count)
                self.count+=1
                return {}
            def close(self):pass
        args=type('Args',(),{'manifest':self.mp})()
        with patch.object(r,'OUT',out),patch.object(r,'Process',FakeProcess),patch.object(r,'Monitor',FakeMonitor),patch.object(r,'gpu',return_value={}),contextlib.redirect_stdout(io.StringIO()):
            r.run(args,manifest,msha,{'cases':self.cases})
        rows=[json.loads(l) for l in (out/'raw'/(cfg['id']+'.jsonl')).read_text().splitlines()]
        self.assertEqual(len(rows),200)
        self.assertTrue(all(x['attempt']==1 and x['raw_response']=='invalid JSON on purpose' for x in rows))
        self.assertEqual(len({x['case_id'] for x in rows}),200)

    def test_native_technical_failure_stops_after_preserving_raw(self):
        out=self.root/'out';cfg=self.configs[0];msha=r.sha(self.mp)
        class FakeProcess:
            def __init__(self,*args):self.process=type('P',(),{'pid':123})();self.count=0
            def send(self,req,timeout):
                if req['op']=='load':return {}
                self.count+=1
                return {'status':0 if self.count==1 else -4,'raw_response':'partial','finish_reason':'error'}
            def close(self):pass
        class FakeMonitor:
            def __init__(self,pid):pass
            def reset(self):pass
            def finish(self):return {}
            def close(self):pass
        args=type('Args',(),{'manifest':self.mp})()
        with patch.object(r,'OUT',out),patch.object(r,'Process',FakeProcess),patch.object(r,'Monitor',FakeMonitor),patch.object(r,'gpu',return_value={}),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'Technical failure'):r.run(args,self.manifest,msha,{'cases':self.cases})
        rows=[json.loads(l) for l in (out/'raw'/(cfg['id']+'.jsonl')).read_text().splitlines()]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],-4)
        self.assertFalse((out/'completion.json').exists())

    def test_lost_telemetry_resumes_without_repeating_existing_answer(self):
        out=self.root/'out';cfg=self.configs[0];msha=r.sha(self.mp)
        manifest={**self.manifest,'configurations':[cfg]};generated=[];fail_once=[True]
        class FakeProcess:
            def __init__(self,*args):self.process=type('P',(),{'pid':123})()
            def send(self,req,timeout):
                if req['op']=='load':return {}
                if req['user']!=r.user_prompt(r.SYNTHETIC):
                    events=(out/'attempts'/(cfg['id']+'.jsonl')).read_text().splitlines()
                    generated.append(json.loads(events[-1])['case_id'])
                return {'status':0,'raw_response':'fixture','finish_reason':'stop','native_seconds':.01}
            def close(self):pass
        class FakeMonitor:
            def __init__(self,pid):self.first=True
            def reset(self):pass
            def finish(self):
                if not self.first and fail_once[0]:
                    fail_once[0]=False;raise OSError('Simulated lost telemetry after RAW fsync')
                self.first=False;return {}
            def close(self):pass
        args=type('Args',(),{'manifest':self.mp})()
        with patch.object(r,'OUT',out),patch.object(r,'Process',FakeProcess),patch.object(r,'Monitor',FakeMonitor),patch.object(r,'gpu',return_value={}),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(OSError,'lost telemetry'):r.run(args,manifest,msha,{'cases':self.cases})
            r.run(args,manifest,msha,{'cases':self.cases})
        self.assertEqual(len(generated),200);self.assertEqual(len(set(generated)),200)
        measurements=[json.loads(l) for l in (out/'telemetry'/(cfg['id']+'.jsonl')).read_text().splitlines()]
        self.assertEqual(len(measurements),200)
        lost=[x for x in measurements if x.get('measurement_lost_due_to_interruption')]
        self.assertEqual(len(lost),1);self.assertEqual(lost[0]['memory'],{})


if __name__=='__main__':unittest.main()
