import dataclasses
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crosscode.core import Config, ROOT, load_tasks, read, save
from crosscode.evaluator import evaluate_saved, preflight
from crosscode.migration import fork_evaluator
from crosscode.runner import execute
from crosscode.store import Store
from crosscode.cli import main

OLD_IMAGE = 'sha256:'+'1'*64
NEW_IMAGE = 'sha256:'+'2'*64


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runs')
        self.root = Path(self.temp.name)
        self.source = self.root/'original'
        self.source.mkdir()
        self.target = self.root/'continued'
        self.config = Config(mock=True,evaluator_image=OLD_IMAGE)
        self.tasks,self.source_info = load_tasks(True)
        self.manifest = {'config_hash':self.config.identity(),'tasks':self.tasks[:2],
                         'source':self.source_info,'selection':{'subset':'full','tasks':'2'},
                         'eligible_ids':[t['task_id'] for t in self.tasks],'history':[]}
        save(self.source/'config.json',dataclasses.asdict(self.config))
        save(self.source/'manifest.json',self.manifest)
        save(self.source/'controls.json',{'max_cost_usd':10,'max_task_cost_usd':3,'parallelism':1})
        save(self.source/'preflight.json',{'passed':False,'results':{}})
        self.store = Store(self.source/'checkpoint.sqlite')
        execute(self.config,self.manifest,self.store,10,3)
        evaluate_saved(self.config,self.manifest,self.store)

    def tearDown(self):
        self.temp.cleanup()

    def fork(self, **kwargs):
        with patch('crosscode.migration.image_id',return_value=NEW_IMAGE),patch('crosscode.providers.http',side_effect=AssertionError('No model calls during migration')):
            return fork_evaluator(self.source,self.target,NEW_IMAGE,**kwargs)

    def test_preserves_source_responses_attempts_spending_and_reuses_generation(self):
        self.store.reconcile(1,.123,'Synthetic billing fixture, no real purchase')
        # SQLite may create transient WAL/shared-memory sidecars even for a
        # read-only snapshot; compare durable files and logical records.
        source_files = {p.name:p.read_bytes() for p in self.source.iterdir() if p.is_file() and not p.name.endswith(('-shm','-wal'))}
        old_stages, old_attempts, old_ledger = self.store.stages(),self.store.attempts(),self.store.ledger()
        migration = self.fork()
        self.assertEqual(source_files,{p.name:p.read_bytes() for p in self.source.iterdir() if p.is_file() and not p.name.endswith(('-shm','-wal'))})
        target = Store(self.target/'checkpoint.sqlite')
        self.assertEqual(target.attempts(),old_attempts)
        self.assertEqual(target.ledger(),old_ledger)
        self.assertEqual(target.evaluations(),{})
        new_config = Config(**read(self.target/'config.json'))
        self.assertNotEqual(new_config.identity(),self.config.identity())
        old_settings=json.loads(json.dumps(dataclasses.asdict(self.config)))
        new_settings=json.loads(json.dumps(dataclasses.asdict(new_config)))
        changes = {k for k,v in old_settings.items() if new_settings[k]!=v}
        self.assertEqual(changes,{'evaluator_image'})
        for key,r in target.stages().items():
            for field in ['text','raw','code','code_hash','prompt','usage','config_hash','cost']:
                self.assertEqual(r[field],old_stages[key][field])
            self.assertEqual(r['reuse_provenance']['source_cache_identity'],old_stages[key]['identity'])
        with patch('crosscode.providers.mock_generate',side_effect=AssertionError('Do not repurchase copied stages')):
            result = execute(new_config,read(self.target/'manifest.json'),target,10,3)
        self.assertEqual(result['completed_stages'],20)
        self.assertEqual(target.ledger(),old_ledger)
        evaluate_saved(new_config,read(self.target/'manifest.json'),target)
        self.assertEqual(len(target.evaluations()),20)
        self.assertTrue(all(target.evaluations()[k]['identity']!=self.store.evaluations()[k]['identity'] for k in target.evaluations()))
        self.assertEqual(migration['inference_calls_during_migration'],0)

    def test_rejects_incompatible_saved_prompt_and_does_not_leave_partial_run(self):
        with self.store.connect() as db:
            key,raw = db.execute('SELECT key,record FROM stages LIMIT 1').fetchone()
            r=json.loads(raw)
            r['prompt']='changed prompt'
            db.execute('UPDATE stages SET record=? WHERE key=?',(json.dumps(r),key))
        with self.assertRaisesRegex(ValueError,'mismatch'):
            self.fork()
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.continued-prepare-*')))

    def test_never_overwrites_existing_destination(self):
        self.target.mkdir()
        marker=self.target/'keep.txt'
        marker.write_text('User data')
        with self.assertRaises(ValueError):
            self.fork()
        self.assertEqual(marker.read_text(),'User data')

    def test_retains_unknown_usage_and_reservations(self):
        self.manifest['tasks']=self.tasks[:3]
        save(self.source/'manifest.json',self.manifest)
        self.store.reserve('Synthetic/2:0:A:writer','Synthetic/2',0,.4,10,3)
        self.fork()
        target=Store(self.target/'checkpoint.sqlite')
        self.assertEqual(target.ledger(),self.store.ledger())
        self.assertEqual(target.ledger()['unresolved_attempts'],1)
        self.assertEqual(target.ledger()['reserved_usd'],.4)

    def test_only_matching_verified_preflight_can_be_inherited(self):
        candidate=self.root/'candidate'
        candidate.mkdir()
        c=dataclasses.replace(self.config,evaluator_image=NEW_IMAGE)
        with patch('crosscode.evaluator.image_id',return_value=NEW_IMAGE),patch('crosscode.evaluator.evaluate',return_value={'status':'pass','passed':True}):
            evidence=preflight(c,self.manifest,candidate)
        self.fork(verified_preflight=candidate/'preflight.json')
        self.assertEqual(read(self.target/'preflight.json'),evidence)
        with patch('crosscode.evaluator.image_id',return_value=NEW_IMAGE),patch('crosscode.evaluator.evaluate',side_effect=AssertionError('Matching preflight should be cached')):
            preflight(c,read(self.target/'manifest.json'),self.target)

    def test_mismatched_preflight_is_rejected(self):
        path=self.root/'wrong-preflight.json'
        save(path,{'passed':True,'key':'wrong','results':{}})
        with self.assertRaisesRegex(ValueError,'Preflight evidence'):
            self.fork(verified_preflight=path)
        self.assertFalse(self.target.exists())

    def test_cli_creates_explicit_continuation_without_inference(self):
        with patch('crosscode.migration.image_id',return_value=NEW_IMAGE),patch('crosscode.providers.http',side_effect=AssertionError('No API calls')),contextlib.redirect_stdout(io.StringIO()):
            main(['fork-evaluator','--runs-dir',str(self.root),'--resume','original',
                  '--new-run-id','continued','--evaluator-image',NEW_IMAGE])
        self.assertEqual(read(self.target/'config.json')['evaluator_image'],NEW_IMAGE)
        self.assertEqual(read(self.source/'config.json')['evaluator_image'],OLD_IMAGE)
        self.assertEqual(len(Store(self.target/'checkpoint.sqlite').stages()),20)

    def test_cli_rejects_generation_setting_change_during_evaluator_fork(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main(['fork-evaluator','--runs-dir',str(self.root),'--resume','original',
                  '--new-run-id','continued','--evaluator-image',NEW_IMAGE,'--gpt-effort','high'])
        self.assertFalse(self.target.exists())

    def test_proxy_only_fork_preserves_and_reuses_generations(self):
        proxy_image='sha256:'+'3'*64
        with patch('crosscode.migration.image_id',return_value=OLD_IMAGE):
            fork_evaluator(self.source,self.target,OLD_IMAGE,evaluator_egress_proxy_image=proxy_image)
        config=Config(**read(self.target/'config.json'))
        self.assertEqual(config.evaluator_egress_proxy_image,proxy_image)
        with patch('crosscode.providers.mock_generate',side_effect=AssertionError('No repurchase')):
            execute(config,read(self.target/'manifest.json'),Store(self.target/'checkpoint.sqlite'),10,3)
        self.assertEqual(Store(self.target/'checkpoint.sqlite').ledger(),self.store.ledger())


if __name__=='__main__':
    unittest.main()
