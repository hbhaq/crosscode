import contextlib
import csv
import dataclasses
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from crosscode.core import Config, digest, load_tasks, plan, prompt, read, save, select, workflow_keys
from crosscode.providers import allowance, generate, mock_generate, price, request_body
from crosscode.runner import cache_identity, execute, preview
from crosscode.evaluator import docker_command, evaluate_saved
from crosscode.store import Store, BudgetStop
from crosscode.report import bh, cluster_ci, mcnemar, records, report, statistics
from crosscode.cli import main

class CrosscodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'runs')
        self.root = Path(self.temp.name)
        self.pool, self.source = load_tasks(True)
        self.config = Config(mock=True, bootstrap_samples=100)
        self.manifest = {'tasks':self.pool[:5], 'config_hash':self.config.identity(),
                         'source':self.source,'selection':{'subset':'full'}}
        self.store = Store(self.root/'checkpoint.sqlite')

    def tearDown(self):
        self.temp.cleanup()

    def test_stable_sampling_and_validation(self):
        a,_ = select(self.pool,tasks='5')
        b,_ = select(self.pool,tasks='10')
        self.assertEqual(a,b[:5])
        self.assertEqual(len(select(self.pool,'hard','5')[0]),5)
        self.assertEqual(len(select(self.pool,'non-hard','all')[0]),10)
        for options in [dict(tasks='99'),dict(tasks='0'),dict(ids=['unknown']),dict(ids=['Synthetic/1','Synthetic/1']),dict(include=('none',))]:
            with self.assertRaises(ValueError):
                select(self.pool,**options)

    def test_call_planning_and_prerequisites(self):
        self.assertEqual(len(plan(self.config,self.pool[:1])),10)
        shared = dataclasses.replace(self.config,design='shared-draft')
        self.assertEqual(len(plan(shared,self.pool[:1])),6)
        self.assertEqual(len(plan(dataclasses.replace(shared,conditions=('AO','AA')),self.pool[:1])),3)
        self.assertEqual(len(plan(dataclasses.replace(self.config,conditions=('AO','OA')),self.pool[:1])),4)

    def test_cache_and_intentional_reuse(self):
        self.assertNotEqual(workflow_keys(self.config,'id',0,'A')[0],workflow_keys(self.config,'id',0,'AO')[0])
        shared = dataclasses.replace(self.config,design='shared-draft')
        self.assertEqual(workflow_keys(shared,'id',0,'A')[0],workflow_keys(shared,'id',0,'AO')[0])
        j = plan(self.config,self.pool[:1])[0]
        rendered = prompt(self.pool[0],'instruct')
        one = cache_identity(self.config,j,self.pool[0],rendered,None)
        self.assertNotEqual(one,cache_identity(dataclasses.replace(self.config,gpt_effort='high'),j,self.pool[0],rendered,None))
        self.assertNotEqual(one,cache_identity(self.config,dict(j,arm='AA'),self.pool[0],rendered,None))
        for change in [dict(gpt_model='new-model'),dict(claude_max_output_tokens=1000),dict(design='shared-draft')]:
            self.assertNotEqual(one,cache_identity(dataclasses.replace(self.config,**change),j,self.pool[0],rendered,None))
        self.assertNotEqual(cache_identity(self.config,j,self.pool[0],rendered,{'code_hash':'draft1'}),
                            cache_identity(self.config,j,self.pool[0],rendered,{'code_hash':'draft2'}))

    def test_prompt_allowlist(self):
        task = dict(self.pool[0],test='SECRET_TEST',canonical_solution='SECRET_REFERENCE',question='SECRET_UNPERMITTED')
        text = prompt(task,'instruct','def task_func(x):\n    return x')
        for secret in ['SECRET_TEST','SECRET_REFERENCE','SECRET_UNPERMITTED']:
            self.assertNotIn(secret,text)
        self.assertNotIn('confidence',text)
        self.assertIn('SUBMITTED SOLUTION',text)

    def test_provider_requests_defaults(self):
        c = Config()
        o,a = request_body(c,'O','hi'),request_body(c,'A','hi')
        self.assertEqual(o['model'],'gpt-6.1-sol')
        self.assertEqual(o['reasoning'],{'effort':'medium'})
        self.assertEqual(o['max_output_tokens'],16384)
        self.assertEqual(a['model'],'claude-opus-5-5')
        self.assertEqual(a['output_config'],{'effort':'medium'})
        self.assertEqual(a['max_tokens'],16384)
        self.assertEqual(a['thinking'],{'type':'adaptive'})
        for req in [a,o]:
            self.assertEqual(req['tools'],[])
            self.assertNotIn('temperature',req)
            self.assertNotIn('seed',req)

    def test_provider_usage_and_stop(self):
        raw = {'model':'returned','status':'incomplete','incomplete_details':{'reason':'max_output_tokens'},
               'output':[{'type':'reasoning','content':[{'type':'output_text','text':'SECRET_REASONING'}]},
                         {'type':'message','content':[{'type':'output_text','text':'final'}]}],
               'usage':{'input_tokens':100,'output_tokens':50,'input_tokens_details':{'cached_tokens':20},'output_tokens_details':{'reasoning_tokens':40}}}
        with patch('crosscode.providers.http',return_value=raw):
            r,cost = generate(Config(),{'model':'O'},'hi')
        self.assertEqual(r['text'],'final')
        self.assertTrue(r['truncated'])
        self.assertEqual(r['returned_model'],'returned')
        self.assertAlmostEqual(cost,(80*2+20*.1+50*10)/1e6)
        self.assertAlmostEqual(price('A',{'input_tokens':100,'output_tokens':50,'cache_read_input_tokens':20,'cache_creation_input_tokens':10}),(400+1000+4+50)/1e6)
        self.assertAlmostEqual(price('O',{'input_tokens':12000,'output_tokens':100,'input_tokens_details':{
            'cached_tokens':4000,'cache_write_tokens':7000,'cache_write_tokens_details':{'ttl_30m_tokens':3000,'ttl_12h_tokens':4000}}}),
            (1000*2+4000*.1+3000*2.5+4000*5+100*10)/1e6)
        self.assertAlmostEqual(price('A',{'input_tokens':100,'output_tokens':50,'cache_creation_input_tokens':10,
            'cache_creation':{'ephemeral_1h_input_tokens':4}}),(400+1000+6*5+4*8)/1e6)
        raw = {'model':'opus','stop_reason':'max_tokens','content':[{'type':'thinking','thinking':'SECRET'},{'type':'text','text':'code'}],'usage':{'input_tokens':10,'output_tokens':20}}
        with patch('crosscode.providers.http',return_value=raw):
            r,_ = generate(Config(),{'model':'A'},'hi')
        self.assertEqual(r['text'],'code')
        self.assertTrue(r['truncated'])

    def test_budget_atomic_and_resume(self):
        results=[]
        def reserve(i):
            try:
                results.append(self.store.reserve(str(i),'task',0,.6,1,1))
            except BudgetStop:
                pass
        workers=[threading.Thread(target=reserve,args=(i,)) for i in range(8)]
        for w in workers:w.start()
        for w in workers:w.join()
        self.assertEqual(len(results),1)
        self.store.finish(results[0],{'error':'timeout'})
        resumed = Store(self.store.path)
        self.assertAlmostEqual(resumed.ledger()['reserved_usd'],.6)
        with self.assertRaises(BudgetStop):
            resumed.reserve('later','task',0,.5,1,1)
        resumed.reconcile(results[0],.2,'Provider invoice test-fixture')
        self.assertAlmostEqual(resumed.ledger()['actual_usd'],.2)
        self.assertEqual(resumed.ledger()['reserved_usd'],0)

    def test_unknown_usage_stops_and_is_not_free(self):
        c=dataclasses.replace(self.config,mock=False)
        with patch('crosscode.providers.generate',side_effect=TimeoutError):
            execute(c,self.manifest,self.store,10,10)
        self.assertEqual(len(self.store.attempts()),1)
        self.assertGreater(self.store.ledger()['reserved_usd'],0)
        with patch('crosscode.providers.generate') as call:
            execute(c,self.manifest,self.store,10,10)
            call.assert_not_called()

    def test_explicit_retries_no_hidden_retry(self):
        c=dataclasses.replace(self.config,mock=False,max_retries=1,conditions=('A',))
        j=plan(c,self.pool[:1])[0]
        fixture,_=mock_generate(c,j,'hi')
        error=urllib.error.HTTPError('https://fixture',429,'rate',{},None)
        with patch('crosscode.providers.generate',side_effect=[error,(fixture,.01)]) as call:
            execute(c,dict(self.manifest,tasks=self.pool[:1]),self.store,10,10)
        self.assertEqual(call.call_count,2)
        self.assertEqual(len(self.store.attempts()),2)
        self.assertAlmostEqual(self.store.ledger()['actual_usd'],.01)

    def test_truncation_is_terminal(self):
        c=dataclasses.replace(self.config,conditions=('A',),max_retries=3)
        j=plan(c,self.pool[:1])[0]
        fixture,cost=mock_generate(c,j,'hi')
        fixture['truncated']=True
        with patch('crosscode.providers.mock_generate',return_value=(fixture,cost)) as call:
            execute(c,dict(self.manifest,tasks=self.pool[:1]),self.store,10,10)
        self.assertEqual(call.call_count,1)
        self.assertEqual(next(iter(self.store.stages().values()))['status'],'truncation')

    def test_resume_no_repurchase_and_shared_draft(self):
        c=dataclasses.replace(self.config,design='shared-draft')
        execute(c,self.manifest,self.store,5,2,parallelism=3)
        self.assertEqual(len(self.store.stages()),30)
        with patch('crosscode.providers.mock_generate') as call:
            execute(c,self.manifest,self.store,5,2)
            call.assert_not_called()
        for j in plan(c,self.manifest['tasks']):
            if j['parent']:
                records=self.store.stages()
                self.assertIn(records[j['parent']]['code'],records[j['key']]['prompt'])
                self.assertEqual(records[j['key']]['parent_hash'],records[j['parent']]['code_hash'])

    def test_dry_run_calls_zero(self):
        with patch('crosscode.providers.http',side_effect=AssertionError('network forbidden')):
            v=preview(self.config,self.manifest,self.store,5,2)
            self.assertEqual(v['planned_generation_calls'],50)
            self.assertEqual(v['inference_calls_in_dry_run'],0)

    def test_budget_unstarted_is_not_incorrect(self):
        c=dataclasses.replace(self.config,mock=False)
        with patch('crosscode.providers.generate') as call:
            result=execute(c,self.manifest,self.store,.00001,.00001)
            call.assert_not_called()
        self.assertTrue(result['messages'])
        rs=records(c,self.manifest,self.store)
        self.assertTrue(all(r['not_run'] for r in rs))
        self.assertFalse(any(r['reliability_eligible'] for r in rs))
        self.assertTrue(all(r['outcome'] is None for r in rs))

    def test_infrastructure_and_parse_denominators(self):
        c=dataclasses.replace(self.config,conditions=('A',))
        execute(c,self.manifest,self.store,5,2)
        evaluate_saved(c,self.manifest,self.store)
        key=workflow_keys(c,self.pool[0]['task_id'],0,'A')[0]
        self.store.evaluation(key,{'status':'infrastructure_failure','passed':None})
        # A terminal parse failure remains attempted and counts in reliability.
        second=workflow_keys(c,self.pool[1]['task_id'],0,'A')[0]
        with self.store.connect() as db:
            record=json.loads(db.execute('SELECT record FROM stages WHERE key=?',(second,)).fetchone()[0])
            record['status']='parse_failure'
            db.execute('UPDATE stages SET record=? WHERE key=?',(json.dumps(record),second))
        rs=records(c,self.manifest,self.store)
        self.assertEqual(sum(r['reliability_eligible'] for r in rs),4)
        self.assertEqual(sum(r['outcome'] is not None for r in rs),3)
        self.assertEqual(sum(r['infrastructure_failure'] for r in rs),1)

    def test_five_to_ten_execution_reuses_paid_work(self):
        execute(self.config,self.manifest,self.store,5,2)
        before=self.store.stages()
        expanded=dict(self.manifest,tasks=self.pool[:10])
        with patch('crosscode.providers.mock_generate',wraps=mock_generate) as call:
            execute(self.config,expanded,self.store,5,2)
        self.assertEqual(call.call_count,50)
        after=self.store.stages()
        self.assertEqual(len(after),100)
        self.assertTrue(all(before[k]==after[k] for k in before))

    def test_numeric_controls_reject_nan(self):
        for setting in [dict(api_timeout=float('nan')),dict(repeats=1.5),dict(max_retries=-1)]:
            with self.assertRaises(ValueError):
                Config(**setting)
        with self.assertRaises(ValueError):
            self.store.reconcile(1,float('nan'),'invalid')

    def test_stats_known_examples(self):
        self.assertEqual(mcnemar([True]*6,[False]*6),(6,0,.03125))
        self.assertEqual(mcnemar([],[]),(0,0,None))
        self.assertEqual(bh([.01,.04,.03]),[.03,.04,.04])
        self.assertEqual(cluster_ci([{'task_id':'one','x':1}],'x'),(None,None))
        r=[{'task_id':str(i),'x':i%2} for i in range(10)]
        self.assertEqual(cluster_ci(r,'x',42,100),cluster_ci(r,'x',42,100))

    def test_evaluation_selected_and_denominators(self):
        execute(self.config,self.manifest,self.store,5,2)
        evaluate_saved(self.config,self.manifest,self.store)
        rs=records(self.config,self.manifest,self.store)
        self.assertEqual(len(rs),30)
        self.assertEqual({r['task_id'] for r in rs},{t['task_id'] for t in self.manifest['tasks']})
        stats=statistics(rs,self.config.conditions,1,'complete-case')
        self.assertEqual(len(stats),15)
        self.assertEqual({r['paired_tasks'] for r in stats},{5})
        self.assertTrue(any(r['draft_outcome'] is True and r['outcome'] is False for r in rs if len(r['condition'])==2))
        self.assertTrue(any(r['draft_outcome'] is False and r['outcome'] is True for r in rs if len(r['condition'])==2))
        # Repetitions form separate exact-test families, never pooled rows.
        twice=rs+[dict(r,rep=1) for r in rs]
        stats=statistics(twice,self.config.conditions,2,'complete-case')
        self.assertEqual(len(stats),30)
        self.assertEqual({r['paired_tasks'] for r in stats},{5})

    def test_docker_no_credentials_or_mounts(self):
        cmd=docker_command('sha256:fixture','fixture',1)
        self.assertIn('none',cmd)
        self.assertIn('--read-only',cmd)
        self.assertIn('--pids-limit',cmd)
        self.assertNotIn('--volume',cmd)
        self.assertFalse(any('API_KEY' in c for c in cmd))
        self.assertIn('65534:65534',cmd)

    def test_cli_expansion_resume_and_frozen_settings(self):
        base=['--runs-dir',str(self.root)]
        with contextlib.redirect_stdout(io.StringIO()):
            main(base+['--run-id','expandtest','--mock','--tasks','5','--dry-run'])
            before=read(self.root/'expandtest'/'manifest.json')
            main(['expand']+base+['--resume','expandtest','--tasks','10'])
            after=read(self.root/'expandtest'/'manifest.json')
        self.assertEqual(before['tasks'],after['tasks'][:5])
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main(base+['--resume','expandtest','--tasks','11','--dry-run'])
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main(base+['--resume','expandtest','--gpt-effort','high','--dry-run'])

    def test_report_figure_table_agree(self):
        execute(self.config,self.manifest,self.store,5,2)
        evaluate_saved(self.config,self.manifest,self.store)
        save(self.root/'config.json',dataclasses.asdict(self.config))
        report(self.config,self.manifest,self.store,self.root/'report')
        for pop in ['complete-case','reliability-inclusive']:
            folder=self.root/'report'/pop
            self.assertEqual((folder/'table2.csv').read_bytes(),(folder/'figure2_data.csv').read_bytes())
            for suffix in ['png','svg','pdf']:
                self.assertGreater((folder/f'figure2.{suffix}').stat().st_size,100)
            stats=list(csv.DictReader((folder/'all_pairwise.csv').read_text().splitlines()))
            self.assertEqual(len(stats),15)
            metrics=list(csv.DictReader((folder/'table2.csv').read_text().splitlines()))
            self.assertEqual({m['denominator'] for m in metrics},{'5'})
        self.assertEqual(self.store.ledger()['actual_usd'],0)

if __name__=='__main__':
    unittest.main()
