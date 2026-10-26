"""Optional real-container evaluator smoke test. Never uses a provider API."""
import os
import unittest
from crosscode.core import Config
from crosscode.evaluator import evaluate, image_id

@unittest.skipUnless(os.environ.get('CROSSCODE_TEST_IMAGE'), 'Docker engine/image unavailable or integration not enabled')
class DockerIntegration(unittest.TestCase):
    def test_official_selected_evaluator(self):
        image=image_id(os.environ['CROSSCODE_TEST_IMAGE'])
        c=Config(evaluator_image=image)
        task={'task_id':'BigCodeBench/0','entry_point':'task_func', 'code_prompt':'def task_func(x):',
              'complete_prompt':'def task_func(x):\n    """Identity."""\n', 'instruct_prompt':'Return x.',
              'canonical_solution':'    return x\n',
              'test':'import unittest\nclass TestCases(unittest.TestCase):\n    def test_identity(self):\n        self.assertEqual(task_func(7),7)\n'}
        correct=evaluate(c,task,'def task_func(x):\n    return x\n')
        wrong=evaluate(c,task,'def task_func(x):\n    return x+1\n')
        self.assertIs(correct.get('passed'),True,correct)
        self.assertIs(wrong.get('passed'),False,wrong)
        self.assertEqual(set(correct['evidence']['eval']),{'BigCodeBench/0'})
