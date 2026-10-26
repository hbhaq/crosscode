"""Runs only inside the credential-free evaluator image."""
import json
import os
import sys
from pathlib import Path

payload = json.load(sys.stdin)
os.chdir('/work')
task = payload['task']
Path('/tmp/problems.jsonl').write_text(json.dumps(task)+'\n')
# Official loader checks the override before attempting network downloads.
os.environ['BIGCODEBENCH_OVERRIDE_PATH'] = '/tmp/problems.jsonl'
os.environ['HF_HOME'] = '/tmp/huggingface'
os.environ['XDG_CACHE_HOME'] = '/tmp/cache'
os.environ['HF_DATASETS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
if os.environ.get('CROSSCODE_EGRESS_SOCKET'):
    from egress_relay import start
    egress_relay = start()
    import urllib.request
    opener=urllib.request.build_opener()
    opener.addheaders=[('User-Agent','CrosscodeBenchmark/0.1 (BigCodeBench reproducibility pilot)')]
    urllib.request.install_opener(opener)
from bigcodebench.sanitize import sanitize
from bigcodebench.evaluate import evaluate
raw = payload['code']
evaluated = sanitize(raw, entrypoint=task['entry_point'])
Path('/work/samples.jsonl').write_text(json.dumps({'task_id': task['task_id'], 'solution': evaluated})+'\n')
evaluate(split=payload['split'], subset='full', samples='/work/samples.jsonl', execution='local',
         selective_evaluate=task['task_id'], calibrated=True, parallel=1, pass_k='1',
         max_as_limit=3072, max_data_limit=3072, max_stack_limit=10)
result = json.loads(Path('/work/samples_eval_results.json').read_text())
item = result['eval'][task['task_id']][0]
print('CROSSCODE_RESULT='+json.dumps({'status': item['status'], 'passed': item['status'] == 'pass',
    'evidence': result, 'raw_code': raw, 'sanitized_code': evaluated,
    'evaluated_code': task['code_prompt']+'\n    pass\n'+evaluated}))
