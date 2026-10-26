import unittest
from crosscode.evaluator import preflight_diagnostics

class PreflightDiagnosticsTests(unittest.TestCase):
    def test_reports_only_observed_failure_modules_not_solution_text(self):
        result=preflight_diagnostics({
            'one':{'passed':True},
            'two':{'passed':False,'evidence':{'eval':{'two':[{'solution':"No module named 'do_not_infer_from_program'",'details':{'ALL':"No module named 'seaborn'"}}]}}},
            'three':{'passed':None,'stderr':"ModuleNotFoundError: No module named 'flask'"},
            'four':{'passed':False,'evidence':{'eval':{'four':[{'details':{'test': 'Temporary failure in name resolution'}}]}}}})
        self.assertEqual(result['passed'],1)
        self.assertEqual(result['missing_modules'],{'two':['seaborn'],'three':['flask']})
        self.assertEqual(result['failed_task_ids'],['two','three','four'])
        self.assertEqual(result['network_error_task_ids'],['four'])

if __name__=='__main__':
    unittest.main()
