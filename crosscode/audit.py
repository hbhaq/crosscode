"""Human-readable, inference-free audit of every selected task and saved attempt."""
import difflib
import json
import re
from collections import defaultdict
from pathlib import Path
from .core import digest, save


def fenced(value, language='text'):
    text = str(value)
    length = max([2]+[len(m) for m in re.findall(r'`+', text)])+1
    fence = '`'*length
    return fence+language+'\n'+text+('' if text.endswith('\n') else '\n')+fence+'\n'


def outcome(record, evidence):
    if not record:
        return 'No completed response saved'
    if record.get('status') != 'valid':
        return 'Invalid generation: '+record.get('status', 'unknown')
    if evidence.get('passed') is True:
        return 'PASS — supplied evaluator tests passed'
    if evidence.get('passed') is False:
        return 'FAIL — supplied evaluator tests failed ('+evidence.get('status', 'fail')+')'
    return 'Unscored — '+evidence.get('status', 'not evaluated')


def transition(row):
    if len(row['condition']) == 1:
        return 'Solo baseline; no reviewer'
    before, after = row['draft_outcome'], row['outcome']
    if before is None or after is None:
        return 'Unscorable review transition — missing draft or final outcome'
    return {(False, True): 'Genuine reviewer fix', (True, False): 'Genuine reviewer regression',
            (True, True): 'Kept passing outcome', (False, False): 'Kept failing outcome'}[before, after]


def write_audit(config, manifest, store, rows, out, metadata, annotations):
    """Export all saved stages once; workflows explicitly link intentional reuse."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stages, evaluations, attempts = store.stages(), store.evaluations(), store.attempts()
    grouped = defaultdict(list)
    for attempt in attempts:
        grouped[attempt['stage']].append(attempt)
    keys = set(stages) | set(grouped)
    for row in rows:
        keys.update([row['writer_key'], row['final_key']])
    links = {key: 'stages/'+digest(key)+'/index.md' for key in keys}
    save(out/'metadata.json', dict(metadata, population='all selected tasks and saved stages, including incomplete work'))
    for key in sorted(keys):
        folder = out/Path(links[key]).parent
        folder.mkdir(parents=True, exist_ok=True)
        record, ev = stages.get(key), evaluations.get(key,{})
        text = '# Saved stage\n\n'+fenced(key)
        text += outcome(record, ev)+'.\n\n'
        if record:
            text += 'Requested model: '+str(record.get('requested_model', record.get('settings',{}).get('model','unknown')))+'. '
            text += 'Returned model: '+str(record.get('returned_model','unavailable'))+'.\n\n'
            text += 'Generation status: '+str(record.get('status'))+'; stop reason: '+str(record.get('stop_reason','unavailable'))+'.\n\n'
            text += 'This response may be intentionally reused by multiple shared-draft workflows; its purchased call is counted once.\n\n'
            save(folder/'stage.json', record)
            for field, filename in [('text','response.txt'),('code','program.py'),('prompt','prompt.txt')]:
                if field in record:
                    (folder/filename).write_text(record[field], encoding='utf-8', newline='')
                    text += f'- [{filename}]({filename})\n'
            if 'raw' in record:
                save(folder/'provider-response.json', record['raw'])
                text += '- [Full saved provider response JSON](provider-response.json)\n'
            text += '- [Stage provenance, hashes, usage and settings](stage.json)\n\n'
            if 'text' in record:
                text += '## Exact final response text\n\n'+fenced(record['text'])+'\n'
            if 'code' in record:
                text += '## Parsed program\n\n'+fenced(record['code'],'python')+'\n'
        else:
            text += 'No response is available. This may be unstarted work or a reserved/failed call without a saved response; inspect the attempts below.\n\n'
        save(folder/'evaluation.json', ev)
        text += '## Evaluator evidence\n\n[Complete evaluator record](evaluation.json). Evidence is evaluation-only data; it is never sent to writers/reviewers.\n\n'
        text += fenced(json.dumps(ev,indent=2,ensure_ascii=False),'json')+'\n'
        for field, filename in [('sanitized_code','sanitized.py'),('evaluated_code','evaluated.py')]:
            if field in ev:
                (folder/filename).write_text(ev[field],encoding='utf-8',newline='')
                text += f'- [{filename}]({filename})\n'
        text += '\n## Every recorded attempt\n\n'
        if not grouped[key]:
            text += 'No API attempt was recorded for this stage.\n'
        for attempt in grouped[key]:
            aid = attempt['id']
            saved_record = json.loads(attempt['record'] or '{}')
            evidence = dict(attempt, record=saved_record)
            save(folder/f'attempt-{aid}.json', evidence)
            text += f'- [Attempt {aid}](attempt-{aid}.json): {attempt["state"]}; settled cost '+str(attempt['cost'])+' USD; allowance '+str(attempt['allowance'])+' USD.\n'
            if 'text' in saved_record:
                filename = f'attempt-{aid}-response.txt'
                (folder/filename).write_text(saved_record['text'],encoding='utf-8',newline='')
                text += f'  [Exact response text]({filename}).\n'
        text += '\n[Audit index](../../index.md). Configuration: `'+metadata['config_hash']+'`.\n'
        (folder/'index.md').write_text(text,encoding='utf-8')

    index = '# Crosscode — task audit\n\n'
    index += ('**SYNTHETIC DEMONSTRATION — not real model results.**\n\n' if config.mock else 'Saved experimental evidence; model results only where generation and evaluation actually completed.\n\n')
    index += 'Design: '+config.design+'. Configuration: `'+metadata['config_hash']+'`.\n\n'
    index += 'Every selected task appears, including unstarted/invalid work. Pass means the supplied evaluator tests passed, not proof that every possible requirement is satisfied. Failure traces describe observed evidence; causal explanations require inspection. Provider-private reasoning that was not returned cannot be recovered. No additional model calls are made by this export.\n\n'
    index += '| Task | Saved stages | Requested workflows | Details |\n| --- | --- | --- | --- |\n'
    task_exports = []
    for task in manifest['tasks']:
        task_id = task['task_id']
        slug = 'task-'+re.sub(r'[^A-Za-z0-9_.-]','_', task_id)[:48]+'-'+digest(task_id)[:12]
        folder = out/'tasks'/slug
        folder.mkdir(parents=True,exist_ok=True)
        task_rows = [r for r in rows if r['task_id']==task_id]
        task_keys = {k for r in task_rows for k in [r['writer_key'],r['final_key']]}
        completed = sum(k in stages for k in task_keys)
        index += f'| {task_id} | {completed} | {len(task_rows)} | [Requirements and outcomes](tasks/{slug}/index.md) |\n'
        public = {key:task.get(key) for key in ['task_id','instruct_prompt','complete_prompt','code_prompt','entry_point','libs','hard']}
        public.update(task_hash=digest(task), split=config.split, configuration_hash=metadata['config_hash'], design=config.design)
        save(folder/'requirements.json', public)
        text = '# '+task_id+'\n\n[Audit index](../../index.md).\n\n'
        text += 'Design: '+config.design+'. Configuration: `'+metadata['config_hash']+'`. [Dataset/settings provenance](../../metadata.json).\n\n'
        text += 'Task hash: `'+digest(task)+'`. Required entry point: `'+task.get('entry_point','task_func')+'`. Libraries: '+', '.join(task.get('libs',[]))+'.\n\n'
        text += '## Official requirements used by this run\n\n'+fenced(task[config.split+'_prompt'])+'\n'
        if config.split=='instruct':
            text += '## Permitted starter/interface\n\n'+fenced(task.get('code_prompt',''),'python')+'\n'
        text += '[Requirements JSON](requirements.json). Canonical solutions and hidden tests are not included in this requirements export; evaluator records may contain test-failure evidence.\n\n'
        text += '| Repetition | Condition | Actual writer draft | Final | Review transition | Details |\n| --- | --- | --- | --- | --- | --- |\n'
        summaries = []
        for row in task_rows:
            cond,rep = row['condition'],row['rep']
            writer, final = stages.get(row['writer_key']), stages.get(row['final_key'])
            writer_ev, final_ev = evaluations.get(row['writer_key'],{}), evaluations.get(row['final_key'],{})
            filename = f'repetition-{rep}-{cond}.md'
            before = outcome(writer, writer_ev)
            after = outcome(final, final_ev)
            review = transition(row)
            if row['not_run']:
                review = 'Not run / final stage unstarted; not scored as an incorrect program'
            text += f'| {rep} | {cond} | {before} | {after} | {review} | [Open]({filename}) |\n'
            detail = '# '+task_id+f' — {cond}, repetition {rep}\n\n[Task requirements and all conditions](index.md).\n\n'
            detail += 'Writer: '+(config.claude_model if cond[0]=='A' else config.gpt_model)+'. '
            detail += 'Reviewer: '+('none' if len(cond)==1 else config.claude_model if cond[1]=='A' else config.gpt_model)+'.\n\n'
            detail += 'Design: '+config.design+'. Configuration: `'+metadata['config_hash']+'`.\n\n'
            detail += '## Observed outcome\n\n'
            detail += '- Actual writer draft: '+before+'.\n- Final: '+after+'.\n- '+review+'.\n\n'
            detail += 'Writing cost: '+str(row['writing_cost'])+' USD; reviewing cost: '+str(row['reviewing_cost'])+' USD; writer/reviewer latency: '+str(row['writer_latency'])+' / '+str(row['reviewer_latency'])+' seconds. Unknown values are not zero; synthetic costs are illustrative only.\n\n'
            for label,key in [('Writer',row['writer_key']),('Final',row['final_key'])]:
                detail += f'- [{label}: exact response, program, prompt and evaluator evidence](../../{links[key]})\n'
            if len(cond)==2 and writer and final:
                diff = ''.join(difflib.unified_diff(writer['code'].splitlines(True),final['code'].splitlines(True),fromfile='writer.py',tofile='reviewed.py'))
                (folder/f'repetition-{rep}-{cond}.diff').write_text(diff,encoding='utf-8',newline='')
                detail += '\n## What changed\n\n'+('The parsed program is unchanged.\n' if writer['code']==final['code'] else fenced(diff,'diff'))+'\n'
            ann = annotations.get(f'{task_id}:{rep}:{cond}',{})
            label = 'Human-verified annotation' if ann.get('verified') is True else 'Provisional / pending inspection'
            detail += '## Explanation — '+label+'\n\n'
            detail += fenced(ann.get('action','pending inspection'))+'\n'+fenced(ann.get('interpretation','pending inspection'))+'\n'
            detail += 'No cause is inferred from pass/fail alone. In independent mode, comparison with a separate solo program is a pipeline comparison; only the draft above supports a genuine review transition.\n'
            (folder/filename).write_text(detail,encoding='utf-8')
            summaries.append(dict(row, observed_transition=review, writer_stage=links[row['writer_key']], final_stage=links[row['final_key']]))
        save(folder/'outcomes.json', {'task_id':task_id,'configuration_hash':metadata['config_hash'],'workflows':summaries})
        (folder/'index.md').write_text(text,encoding='utf-8')
        task_exports.append({'task_id':task_id,'page':f'tasks/{slug}/index.md','completed_stages':completed,'requested_workflows':len(task_rows)})
    save(out/'index.json',{'metadata':metadata,'tasks':task_exports,'stages':links})
    (out/'index.md').write_text(index,encoding='utf-8')
