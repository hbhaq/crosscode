import json
import pathlib
import shutil
import subprocess
import hashlib

root = pathlib.Path(__file__).resolve().parents[1]
fixtures = root/'fixtures'
fixtures.mkdir(exist_ok=True)
rows = []
for i in range(20):
    rows.append({'task_id':f'Synthetic/{i}', 'instruct_prompt':'Return x unchanged.',
        'complete_prompt':'def task_func(x):\n    """Return x unchanged."""\n', 'code_prompt':'def task_func(x):',
        'canonical_solution':'    return x\n', 'entry_point':'task_func', 'test':'# SYNTHETIC ONLY: not executed by offline demo',
        'hard':i<10,'libs':['math'] if i%2 else ['json']})
(fixtures/'tasks.json').write_text(json.dumps(rows,indent=2)+'\n')
licenses = root/'licenses'
licenses.mkdir(exist_ok=True)
lockpath = root/'sources.lock.json'
lock = json.loads(lockpath.read_text())
for name,repo in [('study','https://github.com/shawnzxiang/cross-model-review-code'),('bigcodebench','https://github.com/bigcode-project/bigcodebench')]:
    path = root/'.sources'/name
    sha = subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    lock[name] = {'url':repo, 'commit':sha,'license':'MIT' if name=='study' else 'Apache-2.0'}
    shutil.copyfile(path/'LICENSE',licenses/(name+'.LICENSE'))
    if name=='study':
        for role in ['writer','reviewer']:
            shutil.copyfile(path/'harness'/'prompts'/f'{role}_lcb.txt',licenses/(f'original_{role}_prompt.txt'))
for name,info in lock['datasets'].items():
    info['sha256'] = {f:hashlib.sha256((root/'data'/name/pathlib.Path(f).name).read_bytes()).hexdigest() for f in info['files']}
    shutil.copyfile(root/'data'/name/'README.md',licenses/(name+'.dataset-card.md'))
lock['paper'] = {'url':'https://arxiv.org/pdf/2607.21656','version':'2607.21656v1','inspected':'2026-10-24'}
lockpath.write_text(json.dumps(lock,indent=2)+'\n')
print('Prepared synthetic tasks, attribution, and immutable source lock')
