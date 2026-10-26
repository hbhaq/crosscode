import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crosscode.audit import write_audit, fenced
from crosscode.core import Config, ROOT, load_tasks, read
from crosscode.evaluator import evaluate_saved
from crosscode.report import records
from crosscode.runner import execute
from crosscode.providers import mock_generate
from crosscode.store import Store


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runs')
        self.root = Path(self.temp.name)
        self.tasks, source = load_tasks(True)
        self.config = Config(mock=True, design='shared-draft')
        self.manifest = {'tasks':self.tasks[:5], 'source':source}
        self.store = Store(self.root/'checkpoint.sqlite')
        self.metadata = {'config_hash':self.config.identity(), 'mock':True}

    def tearDown(self):
        self.temp.cleanup()

    def audit(self, annotations=None):
        with patch('crosscode.providers.http',side_effect=AssertionError('No paid analysis')):
            write_audit(self.config,self.manifest,self.store,records(self.config,self.manifest,self.store),
                        self.root/'audit',self.metadata,annotations or {})
        return read(self.root/'audit/index.json')

    def test_every_task_response_and_shared_stage_is_visible(self):
        def with_unicode_and_crlf(config,job,prompt):
            response,cost=mock_generate(config,job,prompt)
            response['text'] += '\r\nConfidence: café.\r\n````\r\nliteral response suffix\r\n'
            response['raw']['text']=response['text']
            return response,cost
        with patch('crosscode.providers.mock_generate',side_effect=with_unicode_and_crlf):
            execute(self.config,self.manifest,self.store,5,2)
        evaluate_saved(self.config,self.manifest,self.store)
        index = self.audit()
        self.assertEqual([t['task_id'] for t in index['tasks']],[t['task_id'] for t in self.manifest['tasks']])
        self.assertEqual(len(index['stages']),30)
        for key, stage in self.store.stages().items():
            folder = (self.root/'audit'/index['stages'][key]).parent
            self.assertEqual((folder/'response.txt').read_bytes(),stage['text'].encode('utf-8'))
            self.assertEqual((folder/'program.py').read_bytes(),stage['code'].encode('utf-8'))
            self.assertEqual(read(folder/'provider-response.json'),stage['raw'])
            self.assertEqual(read(folder/'evaluation.json')['passed'],stage['fixture_passed'])
            self.assertEqual((folder/'prompt.txt').read_text(encoding='utf-8'),stage['prompt'])
        for task in index['tasks']:
            folder = (self.root/'audit'/task['page']).parent
            requirements = read(folder/'requirements.json')
            self.assertNotIn('test', requirements)
            self.assertNotIn('canonical_solution', requirements)
            outcomes = read(folder/'outcomes.json')['workflows']
            by = {r['condition']:r for r in outcomes}
            self.assertEqual(by['A']['writer_stage'],by['AO']['writer_stage'])
            self.assertEqual(by['A']['writer_stage'],by['AA']['writer_stage'])
        self.assertEqual(self.store.ledger()['actual_usd'],0)

    def test_all_unstarted_work_and_unresolved_attempts_are_reported(self):
        stage = 'Synthetic/0:0:A:writer'
        self.store.reserve(stage,'Synthetic/0',0,.4,5,2)
        index = self.audit()
        self.assertEqual(len(index['tasks']),5)
        folder = (self.root/'audit'/index['stages'][stage]).parent
        text = (folder/'index.md').read_text(encoding='utf-8')
        self.assertIn('No response is available',text)
        self.assertIn('reserved',text)
        self.assertFalse((folder/'response.txt').exists())
        self.assertEqual(read(folder/'attempt-1.json')['state'],'reserved')
        self.assertEqual(self.store.ledger()['reserved_usd'],.4)

    def test_true_transitions_and_annotations_do_not_invent_causes(self):
        execute(self.config,self.manifest,self.store,5,2)
        evaluate_saved(self.config,self.manifest,self.store)
        index = self.audit({'Synthetic/0:0:AO': {'verified':True,'action':'Human checked the diff','interpretation':'Human supplied explanation'}})
        pages = '\n'.join(p.read_text(encoding='utf-8') for p in (self.root/'audit/tasks').rglob('repetition-*.md'))
        self.assertIn('Genuine reviewer fix',pages)
        self.assertIn('Genuine reviewer regression',pages)
        self.assertIn('Human-verified annotation',pages)
        self.assertIn('pending inspection',pages)
        self.assertIn('No cause is inferred from pass/fail alone',pages)
        self.assertTrue(any((self.root/'audit/tasks').rglob('*.diff')))
        self.assertTrue(fenced('before\n````\nafter').startswith('`````text\n'))


if __name__ == '__main__':
    unittest.main()
