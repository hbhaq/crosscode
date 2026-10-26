"""Real-container access checks; no provider calls or host candidate execution."""
from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crosscode.core import Config,read,save
from crosscode.evaluator import evaluate

root=Path(__file__).resolve().parents[1]
config=Config(**read(root/'runs/evaluator-wikibooks-validation/config.json'))
task={'task_id':'BigCodeBench/590','entry_point':'task_func','code_prompt':'def task_func(x):',
      'complete_prompt':'def task_func(x):\n    """Identity."""\n','instruct_prompt':'Return x.',
      'canonical_solution':'    return x\n',
      'test':'''import unittest
import os
import socket
import urllib.request
import urllib.error
class TestCases(unittest.TestCase):
    def test_approved_https(self):
        with urllib.request.urlopen('https://en.wikibooks.org/wiki/Main_Page',timeout=20) as response:
            self.assertEqual(response.status,200)
    def test_other_destinations_denied(self):
        for url in ['https://example.com/','https://127.0.0.1/','http://169.254.169.254/']:
            with self.assertRaises(urllib.error.URLError):
                urllib.request.urlopen(url,timeout=3)
    def test_direct_internet_denied(self):
        with self.assertRaises(OSError):
            socket.create_connection(('1.1.1.1',443),timeout=1)
    def test_no_credentials_or_host_bind(self):
        self.assertIsNone(os.environ.get('OPENAI_API_KEY'))
        self.assertIsNone(os.environ.get('ANTHROPIC_API_KEY'))
        self.assertFalse(os.path.exists('/host'))
        with self.assertRaises(OSError):
            open('/egress/unexpected','w')
    def test_identity(self):
        self.assertEqual(task_func(7),7)
'''}
result=evaluate(config,task,'def task_func(x):\n    return x\n')
save(root/'docs/verification/wikibooks-isolation-2026-10-26.json',result)
print(result['status'],result.get('passed'))
if result.get('passed') is not True:
    print(result)
    raise SystemExit(1)
