from __future__ import annotations
import ast
import dataclasses
import hashlib
import json
import os
import math
import random
import re
from pathlib import Path

CONDITIONS = ('A', 'O', 'AO', 'OA', 'AA', 'OO')
PACKAGE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('CROSSCODE_HOME', PACKAGE.parent if (PACKAGE.parent/'sources.lock.json').exists() else Path.cwd()))

def source_lock():
    path = ROOT/'sources.lock.json'
    return read(path if path.exists() else PACKAGE/'resources'/'sources.lock.json')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

@dataclasses.dataclass(frozen=True)
class Config:
    design: str = 'paper-independent'
    conditions: tuple = CONDITIONS
    gpt_model: str = 'gpt-6.1-sol'
    claude_model: str = 'claude-opus-5-5'
    gpt_effort: str = 'medium'
    claude_effort: str = 'medium'
    gpt_max_output_tokens: int = 16384
    claude_max_output_tokens: int = 16384
    repeats: int = 1
    max_retries: int = 0
    api_timeout: float = 300
    eval_timeout: float = 300
    profile: str = 'personal'
    phase: str = 'main'
    mock: bool = False
    split: str = 'instruct'
    evaluator_image: str = ''
    evaluator_egress_proxy_image: str = ''
    bootstrap_seed: int = 42
    bootstrap_samples: int = 2000

    def __post_init__(self):
        if self.evaluator_egress_proxy_image and not re.fullmatch(r'(?:[^\s]+@)?sha256:[0-9a-f]{64}',self.evaluator_egress_proxy_image):
            raise ValueError('Evaluator egress proxy requires an immutable image ID/digest')
        if self.design not in ('paper-independent','shared-draft') or not self.conditions or len(set(self.conditions)) != len(self.conditions) or set(self.conditions)-set(CONDITIONS):
            raise ValueError('Invalid design or conditions')
        if self.gpt_effort not in ('low','medium','high','xhigh','max') or self.claude_effort not in ('low','medium','high','max'):
            raise ValueError('Unsupported effort')
        if self.phase not in ('calibration','main') or self.profile not in ('personal','company') or self.split not in ('instruct','complete'):
            raise ValueError('Invalid phase, profile or prompt split')
        for name in ['repeats','gpt_max_output_tokens','claude_max_output_tokens','bootstrap_samples']:
            value = getattr(self,name)
            if not isinstance(value,int) or isinstance(value,bool) or value < 1:
                raise ValueError(name+' must be a positive integer')
        if not isinstance(self.max_retries,int) or self.max_retries < 0:
            raise ValueError('max_retries must be a nonnegative integer')
        if any(not math.isfinite(v) or v<=0 for v in [self.api_timeout,self.eval_timeout]):
            raise ValueError('Timeouts must be positive and finite')

    def identity(self):
        settings=dataclasses.asdict(self)
        # Preserve every existing no-egress configuration/cache identity.
        if not settings['evaluator_egress_proxy_image']:
            settings.pop('evaluator_egress_proxy_image')
        payload={'protocol': 'crosscode-generation-v2-cache-write-accounting-anthropic-2026-10-21', 'settings':settings,
                 'prompts':templates(),'sources':source_lock()}
        if self.evaluator_egress_proxy_image:
            from .network_policy import EGRESS_POLICY
            payload['evaluation_egress_policy']=EGRESS_POLICY
        return digest(payload)

def templates():
    return {role: (Path(__file__).parent/'prompts'/f'{role}.txt').read_text(encoding='utf-8') for role in ['writer', 'reviewer']}

def prompt(task, split, draft=None):
    # Deliberate allowlist: no task dictionary serialization here.
    problem = task[f'{split}_prompt']
    starter = task['code_prompt'] if split == 'instruct' else ''
    return templates()['writer' if draft is None else 'reviewer'].format(problem=problem, starter_code=starter, writer_output=draft)

def parse(text):
    tagged = re.search(r'<solution>\s*(.*?)\s*</solution>', text, re.S)
    code = tagged.group(1) if tagged else text.strip()
    fence = re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```', code, re.S)
    if fence:
        code = fence.group(1)
    try:
        tree = ast.parse(code)
        if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'task_func' for n in tree.body):
            return code, 'parse_failure'
    except SyntaxError:
        return code, 'parse_failure'
    return code, 'valid'

def load_tasks(mock=False):
    if mock:
        fixture = ROOT/'fixtures/tasks.json'
        return read(fixture if fixture.exists() else PACKAGE/'resources'/'tasks.json'), {'revision': 'synthetic-v1', 'full': 20, 'hard': 10}
    import pyarrow.parquet as pq
    lock = source_lock()['datasets']
    rows = {}
    hard = set()
    for name in ['bigcodebench', 'bigcodebench-hard']:
        files = lock[name]['files']
        for file in files:
            path = ROOT/'data'/name/Path(file).name
            if not path.exists():
                raise ValueError('Dataset missing. Run python scripts/fetch_data.py first.')
            expected = lock[name].get('sha256', {}).get(file)
            if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('Dataset file checksum differs from source lock')
            data = pq.read_table(path).to_pylist()
            if name.endswith('-hard'):
                hard.update(r['task_id'] for r in data)
            else:
                rows.update((r['task_id'], r) for r in data)
    if not hard <= rows.keys():
        raise ValueError('Hard IDs do not belong to pinned full dataset')
    for key, row in rows.items():
        row['hard'] = key in hard
        if isinstance(row['libs'], str):
            row['libs'] = ast.literal_eval(row['libs'])
    return list(rows.values()), {'revision': lock, 'full': len(rows), 'hard': len(hard)}

def select(pool, subset='full', tasks='5', seed=42, ids=None, include=(), exclude=()):
    known = {t['task_id'] for t in pool}
    if ids is not None and (len(set(ids)) != len(ids) or set(ids)-known):
        raise ValueError('Duplicate or unknown task IDs')
    eligible = [t for t in pool if (subset == 'full' or bool(t['hard']) == (subset == 'hard'))
                and (not ids or t['task_id'] in ids)
                and (not include or set(include) <= set(t['libs'])) and not set(exclude)&set(t['libs'])]
    if ids and set(ids) != {t['task_id'] for t in eligible}:
        raise ValueError('Requested IDs conflict with subset/library filters')
    eligible.sort(key=lambda t: t['task_id'])
    random.Random(seed).shuffle(eligible)
    n = len(eligible) if tasks == 'all' else int(tasks)
    if n < 1 or n > len(eligible):
        raise ValueError(f'Requested {n} tasks from eligible pool of {len(eligible)}')
    return eligible[:n], eligible

def plan(config, tasks):
    jobs = []
    for task in tasks:
        for rep in range(config.repeats):
            writers = {}
            for cond in config.conditions:
                arm = cond if config.design == 'paper-independent' else cond[0]
                key = f'{task["task_id"]}:{rep}:{arm}:writer'
                if key not in writers:
                    jobs.append(dict(key=key, task_id=task['task_id'], rep=rep, arm=arm, role='writer', model=cond[0], parent=None))
                    writers[key] = True
                if len(cond) == 2:
                    jobs.append(dict(key=f'{task["task_id"]}:{rep}:{cond}:reviewer', task_id=task['task_id'], rep=rep,
                                     arm=cond, role='reviewer', model=cond[1], parent=key))
    return jobs

def workflow_keys(config, task_id, rep, cond):
    arm = cond if config.design == 'paper-independent' else cond[0]
    writer = f'{task_id}:{rep}:{arm}:writer'
    return writer, f'{task_id}:{rep}:{cond}:reviewer' if len(cond) == 2 else writer
