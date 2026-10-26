import contextlib
import dataclasses
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from crosscode.cli import main
from crosscode.core import Config, ROOT, load_tasks, read
from crosscode.evaluator import evaluate_saved, preflight
from crosscode.progress import Progress
from crosscode.runner import execute
from crosscode.store import Store


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runs')
        self.root = Path(self.temp.name)
        self.store = Store(self.root/'checkpoint.sqlite')
        tasks,_ = load_tasks(True)
        self.manifest = {'tasks':tasks[:1]}
        self.config = Config(mock=True,conditions=('A',))
        self.output = io.StringIO()
        self.progress = Progress(interval=.01,stream=self.output,log_path=self.root/'progress.log')

    def tearDown(self):
        self.temp.cleanup()

    def test_heartbeat_is_flushed_and_stops_without_retry(self):
        arrived = threading.Event()
        class Stream(io.StringIO):
            flush_count = 0
            def write(self, text):
                result = super().write(text)
                if 'WAIT ' in text:
                    arrived.set()
                return result
            def flush(self):
                self.flush_count += 1
        stream = Stream()
        p = Progress(interval=.01,stream=stream)
        with p.wait('API fixture'):
            self.assertTrue(arrived.wait(1))
        saved = stream.getvalue()
        threading.Event().wait(.03)
        self.assertEqual(saved,stream.getvalue())
        self.assertIn('still waiting, no retry',saved)
        self.assertGreater(stream.flush_count,0)

    def test_resume_logging_does_not_repurchase_or_change_saved_work(self):
        identity = self.config.identity()
        execute(self.config,self.manifest,self.store,5,2)
        stages,ledger = self.store.stages(),self.store.ledger()
        with patch('crosscode.providers.mock_generate',side_effect=AssertionError('Cached work must not regenerate')):
            result = execute(self.config,self.manifest,self.store,5,2,progress=self.progress)
        self.assertEqual(stages,self.store.stages())
        self.assertEqual(ledger,result['ledger'])
        self.assertEqual(identity,self.config.identity())
        self.assertIn('CACHE Synthetic/0',self.output.getvalue())
        self.assertIn('saved stages 1/1; remaining 0',self.output.getvalue())

    def test_unknown_usage_logs_attempt_id_without_secret_and_retains_reservation(self):
        c = dataclasses.replace(self.config,mock=False)
        with patch('crosscode.providers.generate',side_effect=ConnectionResetError('SECRET_KEY_AND_PROMPT')):
            result = execute(c,self.manifest,self.store,5,2,progress=self.progress)
        text = self.output.getvalue()
        self.assertIn('attempt ID 1',text)
        self.assertIn('ConnectionResetError',text)
        self.assertIn('reconcile billing',text)
        self.assertNotIn('SECRET_KEY_AND_PROMPT',text)
        self.assertEqual(result['ledger']['unresolved_attempts'],1)
        self.assertGreater(result['ledger']['reserved_usd'],0)
        self.assertEqual(self.store.attempts()[0]['state'],'unresolved')

    def test_evaluation_messages_preserve_cached_evidence(self):
        execute(self.config,self.manifest,self.store,5,2)
        evaluate_saved(self.config,self.manifest,self.store,progress=self.progress)
        evidence = self.store.evaluations()
        self.assertIn('EVAL SAVED 1/1',self.output.getvalue())
        evaluate_saved(self.config,self.manifest,self.store,progress=self.progress)
        self.assertEqual(evidence,self.store.evaluations())
        self.assertIn('EVAL CACHE 1/1',self.output.getvalue())

    def test_preflight_logging_does_not_invalidate_verified_cache(self):
        c = dataclasses.replace(self.config,mock=False,evaluator_image='sha256:fixture')
        with patch('crosscode.evaluator.image_id',return_value='sha256:fixture'),patch('crosscode.evaluator.evaluate',return_value={'status':'pass','passed':True}) as check:
            first = preflight(c,self.manifest,self.root,progress=self.progress)
            second = preflight(c,self.manifest,self.root,progress=self.progress)
        self.assertEqual(first,second)
        self.assertEqual(check.call_count,1)
        self.assertIn('PREFLIGHT CACHE',self.output.getvalue())

    def test_runtime_flags_leave_frozen_configuration_and_dry_run_unchanged(self):
        args = ['--runs-dir',str(self.root),'--run-id','log-settings','--mock','--tasks','1','--dry-run']
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(self.output):
            main(args+['--progress-interval','0.1'])
        folder = self.root/'log-settings'
        config = (folder/'config.json').read_bytes()
        manifest = (folder/'manifest.json').read_bytes()
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(self.output):
            main(['--runs-dir',str(self.root),'--resume','log-settings','--dry-run','--progress-interval','99','--quiet-progress'])
        self.assertEqual(config,(folder/'config.json').read_bytes())
        self.assertEqual(manifest,(folder/'manifest.json').read_bytes())
        self.assertNotIn('progress_interval',read(folder/'config.json'))
        self.assertFalse((folder/'progress.log').exists())
        self.assertEqual(self.output.getvalue(),'')

    def test_quiet_console_keeps_log_and_concurrent_events_stay_whole(self):
        p = Progress(console=False,stream=self.output,log_path=self.root/'progress.log')
        threads = [threading.Thread(target=lambda n=n:[p.event(f'worker {n} event {i}') for i in range(5)]) for n in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        lines = (self.root/'progress.log').read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines),20)
        self.assertTrue(all(line.startswith('[') and '] worker ' in line for line in lines))
        self.assertEqual(self.output.getvalue(),'')

    def test_closed_console_or_log_cannot_fail_generation(self):
        self.output.close()
        p = Progress(stream=self.output,log_path=self.root/'missing'/'log.txt')
        result = execute(self.config,self.manifest,self.store,5,2,progress=p)
        self.assertEqual(result['completed_stages'],1)
        self.assertEqual(next(iter(self.store.stages().values()))['status'],'valid')
        self.assertEqual(result['ledger']['unresolved_attempts'],0)


if __name__=='__main__':
    unittest.main()
