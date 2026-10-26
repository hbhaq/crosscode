"""Audit pilot/main overlap without inference or evaluator execution."""
import json
import pathlib
import sys

pilot, main = [json.loads(pathlib.Path(p).read_text()) for p in sys.argv[1:3]]
overlap = sorted({t['task_id'] for t in pilot['tasks']} & {t['task_id'] for t in main['tasks']})
print(json.dumps({'pilot_config_hash':pilot['config_hash'],'main_config_hash':main['config_hash'],
                  'overlap_count':len(overlap),'overlap_ids':overlap,'disjoint':not overlap},indent=2))
