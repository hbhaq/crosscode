"""Read-only source/continuation integrity check; no inference."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crosscode.core import Config,read,save,prompt
from crosscode.runner import cache_identity

root=Path(__file__).resolve().parents[1]
def snapshot(name):
    directory=root/'runs'/name
    config=Config(**read(directory/'config.json'))
    manifest=read(directory/'manifest.json')
    db=sqlite3.connect((directory/'checkpoint.sqlite').as_uri()+'?mode=ro',uri=True)
    try:
        stages={key:json.loads(value) for key,value in db.execute('SELECT key,record FROM stages')}
        attempts=db.execute('SELECT * FROM attempts ORDER BY id').fetchall()
    finally:
        db.close()
    assert config.identity()==manifest['config_hash']
    tasks={task['task_id']:task for task in manifest['tasks']}
    for key,record in stages.items():
        job={field:record[field] for field in ['key','task_id','rep','arm','role','model','parent']}
        parent=stages.get(record['parent'])
        rendered=prompt(tasks[record['task_id']],config.split,parent['code'] if parent else None)
        assert record['prompt']==rendered
        assert record['identity']==cache_identity(config,job,tasks[record['task_id']],rendered,parent),key
    return directory,stages,attempts

source,old_stages,old_attempts=snapshot('docker-hard-five-check')
destination,new_stages,new_attempts=snapshot('docker-hard-fifty-fixed')
assert new_attempts==old_attempts
assert set(old_stages)==set(new_stages)
for key,record in old_stages.items():
    assert record=={field:value for field,value in new_stages[key].items() if field not in ['identity','reuse_provenance']}|{'identity':record['identity']}
evidence={'source_run':source.name,'continuation_run':destination.name,'saved_stages':len(old_stages),
          'recorded_attempts':len(old_attempts),'all_cache_bindings_verified':True,
          'exact_outputs_prompts_usage_attempts_preserved':True,
          'source_config_sha256':hashlib.sha256((source/'config.json').read_bytes()).hexdigest(),
          'source_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
          'migration':read(destination/'migration.json')}
save(root/'docs/verification/continuation-integrity-2026-10-26.json',evidence)
print(json.dumps({key:value for key,value in evidence.items() if key!='migration'},indent=2))
