import json
from pathlib import Path
from crosscode.core import Config, digest, load_tasks, save, select

root = Path(__file__).resolve().parents[1]
pool, source = load_tasks()
for n in [5,10]:
    tasks, _ = select(pool,'hard',str(n),42)
    save(root/'examples'/f'hard-{n}-manifest.json',{'source':source,'subset':'hard','seed':42,
        'task_count':n,'config_defaults_hash':Config().identity(),
        'tasks':[{'task_id':t['task_id'],'task_hash':digest(t),'libs':t['libs']} for t in tasks]})
    (root/'examples'/f'hard-{n}-ids.txt').write_text('\n'.join(t['task_id'] for t in tasks)+'\n')
