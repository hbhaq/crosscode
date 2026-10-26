"""Regenerate paper-style artifacts from checkpoints; this module never calls APIs."""
from __future__ import annotations
import csv
import difflib
import itertools
import json
import math
import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from .core import CONDITIONS, digest, read, save, templates, workflow_keys

TABLE2_COLUMNS = ['condition','passed','evaluated','denominator','pass_rate','ci_low','ci_high','sid_pp',
                  'mean_workflow_cost_usd','mean_workflow_latency_s','cross_condition_regression_rate','cross_condition_denominator']
COUNT_COLUMNS = ['condition','selected','attempted','valid','evaluated','passed','failed','not_run','infrastructure_failures','invalid_attempts']

def mcnemar(a, b):
    if len(a) != len(b):
        raise ValueError('Paired vectors must have equal lengths')
    x = sum(l and not r for l,r in zip(a,b))
    y = sum(r and not l for l,r in zip(a,b))
    n = x+y
    p = min(1., 2 * sum(math.comb(n,k) for k in range(min(x,y)+1)) / 2**n) if n else 1.
    return x,y,p if a else None

def bh(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [None]*len(values)
    running = 1.
    for rank in range(len(order),0,-1):
        i = order[rank-1]
        running = min(running, values[i]*len(order)/rank)
        result[i] = running
    return result

def cluster_ci(rows, field, seed=42, samples=2000):
    groups = defaultdict(list)
    for r in rows:
        if r.get(field) is not None:
            groups[r['task_id']].append(r[field])
    if len(groups) < 2:
        return None,None
    # Equal repeats per selected task; a task resample carries every available repeat.
    clusters = list(groups.values())
    rng = random.Random(seed)
    estimates = sorted(mean(v for _ in clusters for v in rng.choice(clusters)) for _ in range(samples))
    def quantile(q):
        pos = (len(estimates)-1)*q
        low = int(pos)
        high = min(low+1, len(estimates)-1)
        return estimates[low]+(pos-low)*(estimates[high]-estimates[low])
    return quantile(.025),quantile(.975)

def export_table(out, name, rows, metadata, columns=None):
    out.mkdir(parents=True, exist_ok=True)
    columns = columns or (list(rows[0]) if rows else ['message'])
    provenance = provenance_fields(metadata)
    def display(value):
        if value is None:
            return 'NA'
        if isinstance(value,float):
            return f'{value:.6g}'
        return str(value)
    with (out/(name+'.csv')).open('w',newline='',encoding='utf-8') as f:
        w = csv.DictWriter(f,fieldnames=columns+list(provenance))
        w.writeheader()
        w.writerows(dict({k: 'NA' if row.get(k) is None else row.get(k) for k in columns},**provenance) for row in rows)
    md = '| '+' | '.join(columns)+' |\n| '+' | '.join('---' for _ in columns)+' |\n'
    md += ''.join('| '+' | '.join(display(row.get(k)).replace('|','\\|').replace('\n',' ') for k in columns)+' |\n' for row in rows)
    (out/(name+'.md')).write_text('Provenance: `'+json.dumps(provenance,sort_keys=True)+'`\n\n'+md,encoding='utf-8')
    def tex(v):
        text = display(v)
        for a,b in [('\\', '\\textbackslash{}'), ('_',r'\_'), ('%',r'\%'), ('&',r'\&'), ('#',r'\#'), ('$',r'\$')]:
            text = text.replace(a,b)
        return text
    latex = '\\begin{tabular}{'+'l'*len(columns)+'}\n'+' & '.join(tex(k) for k in columns)+r' \\'+'\n'
    latex += '\n'.join(' & '.join(tex(row.get(k)) for k in columns)+r' \\' for row in rows)+'\n\\end{tabular}\n'
    (out/(name+'.tex')).write_text('% Crosscode provenance: '+json.dumps(provenance,sort_keys=True)+'\n'+latex,encoding='utf-8')
    save(out/(name+'.metadata.json'), metadata)
    return md

def provenance_fields(metadata):
    settings = metadata['settings']
    return {'configuration_hash':metadata['config_hash'],'design_mode':metadata['design'],
            'analysis_population':metadata.get('population','all saved work'),'phase':settings['phase'],
            'dataset_revision':json.dumps(metadata['dataset'].get('revision'),sort_keys=True),
            'subset':metadata['subset'],'selected_task_count':metadata['task_count'],
            'requested_models':';'.join(metadata['requested_models']),
            'returned_models':';'.join(metadata['returned_models']),
            'reasoning_efforts':settings['claude_effort']+' / '+settings['gpt_effort'],
            'output_token_caps':str(settings['claude_max_output_tokens'])+' / '+str(settings['gpt_max_output_tokens'])}

def records(config, manifest, store):
    stages, evaluations = store.stages(), store.evaluations()
    attempts = store.attempts()
    called = {a['stage'] for a in attempts}
    def stage_cost(key):
        calls = [a for a in attempts if a['stage'] == key]
        if any(a['cost'] is None for a in calls):
            return None
        if config.mock:
            return stages.get(key,{}).get('workflow_cost')
        return sum(a['cost'] for a in calls) if calls else None
    def stage_latency(key):
        calls = [json.loads(a['record'] or '{}') for a in attempts if a['stage']==key]
        return sum(a.get('latency',0) for a in calls) if calls else None
    rows = []
    for task in manifest['tasks']:
        for rep in range(config.repeats):
            for cond in config.conditions:
                wk,fk = workflow_keys(config, task['task_id'], rep, cond)
                w,f = stages.get(wk),stages.get(fk)
                ev, wev = evaluations.get(fk,{}),evaluations.get(wk,{})
                attempted = wk in called or fk in called
                # A valid writer waiting for a reviewer is budget-unstarted final work.
                not_run = not attempted or (bool(w) and not f and w['status']=='valid')
                status = f['status'] if f else w['status'] if w else 'api_failure_unknown' if attempted else 'not_run'
                infrastructure = ev.get('status','').startswith('infrastructure')
                outcome = ev.get('passed') if status=='valid' else None
                eligible = attempted and not not_run and not infrastructure and (status!='valid' or outcome is not None)
                writing_cost = stage_cost(wk)
                review_cost = stage_cost(fk) if fk != wk else 0.0
                wl = stage_latency(wk)
                rl = stage_latency(fk) if fk != wk else 0.
                rows.append({'task_id':task['task_id'], 'rep':rep, 'condition':cond, 'writer_key':wk, 'final_key':fk,
                             'attempted':attempted, 'valid':bool(f and f['status']=='valid'), 'not_run':not_run,
                             'status':status, 'infrastructure_failure':infrastructure, 'outcome':outcome,
                             'evaluation_status':ev.get('status'),
                             'draft_outcome':wev.get('passed'), 'reliability_eligible':eligible,
                             'writing_cost':writing_cost,'reviewing_cost':review_cost,
                             'workflow_cost':writing_cost+review_cost if writing_cost is not None and review_cost is not None else None,
                             'writer_latency':wl,'reviewer_latency':rl,
                             'workflow_latency':wl+rl if wl is not None and rl is not None else None})
    return rows

def statistics(rows, conditions, repeats, population):
    output = []
    for rep in range(repeats):
        by = {(r['task_id'],r['condition']):r for r in rows if r['rep']==rep}
        ids = sorted({r['task_id'] for r in rows if r['rep']==rep})
        # A single common population for the full pairwise correction family.
        ids = [i for i in ids if all((i,c) in by and (by[i,c]['outcome'] is not None if population=='complete-case' else by[i,c]['reliability_eligible']) for c in conditions)]
        family = []
        for a,b in itertools.combinations(conditions,2):
            av = [bool(by[i,a]['outcome']) for i in ids]
            bv = [bool(by[i,b]['outcome']) for i in ids]
            x,y,p = mcnemar(av,bv)
            family.append({'comparison':a+' versus '+b,'first':a,'second':b,'rep':rep,'paired_tasks':len(ids),
                           'first_only':x,'second_only':y,'p_value':p,'bh_adjusted':None,'family_size':len(conditions)*(len(conditions)-1)//2})
        valid = [r for r in family if r['p_value'] is not None]
        for row,q in zip(valid,bh([r['p_value'] for r in valid])):
            row['bh_adjusted'] = q
        output.extend(family)
    return output

def selected_comparisons(all_rows):
    selected = []
    for a,b in [('OA','O'),('OO','O'),('AO','A'),('AA','A'),('AA','AO'),('AO','OA')]:
        for row in all_rows:
            if {a,b}=={row['first'],row['second']}:
                r = dict(row)
                if a != row['first']:
                    r['first_only'],r['second_only'] = r['second_only'],r['first_only']
                r.update(comparison=a+' versus '+b,first=a,second=b)
                selected.append(r)
    return selected

def figure(out, metrics, metadata):
    cache = out.parent/'.matplotlib-cache'
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(cache.resolve()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    by = {r['condition']:r for r in metrics}
    fig, axes = plt.subplots(1,2,figsize=(12,5))
    for ax,field,label in zip(axes,['mean_workflow_cost_usd','mean_workflow_latency_s'],['Mean workflow cost per task (USD)','Mean workflow latency per task (seconds)']):
        locations = defaultdict(list)
        for c,r in by.items():
            if r[field] is not None and r['pass_rate'] is not None:
                locations[(round(r[field],10),round(r['pass_rate'],10))].append(c)
        for c,r in by.items():
            if r[field] is None or r['pass_rate'] is None:
                continue
            color = '#2768ad' if c[0]=='A' else '#c44e35'
            ax.scatter(r[field],r['pass_rate']*100,marker='o' if len(c)==1 else 'D',color=color,s=65,zorder=3)
            colliding = sorted(locations[(round(r[field],10),round(r['pass_rate'],10))])
            offset = [(-42,8),(0,20),(22,-20),(10,-32)][colliding.index(c)] if len(colliding)>1 else (6,7)
            ax.annotate(c,(r[field],r['pass_rate']*100),xytext=offset,textcoords='offset points',
                        arrowprops={'arrowstyle':'-','color':color,'lw':.6} if len(colliding)>1 else None)
        for a,b in [('A','AA'),('A','AO'),('O','OO'),('O','OA')]:
            if a in by and b in by and all(by[c][field] is not None and by[c]['pass_rate'] is not None for c in [a,b]):
                ax.annotate('',xy=(by[b][field],by[b]['pass_rate']*100),xytext=(by[a][field],by[a]['pass_rate']*100),
                            arrowprops={'arrowstyle':'->','color':'#2768ad' if a=='A' else '#c44e35','alpha':.6})
        ax.set_xlabel(label)
        ax.set_ylabel('Pass rate (%)')
        ax.set_ylim(-5,110)
        ax.grid(alpha=.2)
        ax.margins(x=.22)
    fig.legend(handles=[Line2D([],[],marker='o',linestyle='',color='gray',label='Solo'),Line2D([],[],marker='D',linestyle='',color='gray',label='Reviewed'),
                        Line2D([],[],color='#2768ad',label='Claude writer'),Line2D([],[],color='#c44e35',label='GPT writer')],loc='center',bbox_to_anchor=(.5,.075),ncol=4)
    label = 'SYNTHETIC DEMONSTRATION' if metadata['mock'] else 'Pilot / proof of concept' if metadata['task_count']<=10 else 'Crosscode experiment'
    fig.suptitle(label+' | '+metadata['design']+' | '+metadata['population'])
    fig.text(.02,.015,'Config '+metadata['config_hash'][:12]+'; full provenance: figure2.metadata.json',fontsize=7)
    fig.tight_layout(rect=(0,.12,1,.94))
    for ext in ['png','svg','pdf']:
        serialized = json.dumps(provenance_fields(metadata),sort_keys=True)
        embedded = {'Title':label,'Subject':serialized} if ext=='pdf' else {'Title':label,'Description':serialized}
        fig.savefig(out/('figure2.'+ext),dpi=180,metadata=embedded)
    plt.close(fig)
    save(out/'figure2.metadata.json', metadata)
    export_table(out,'figure2_data', metrics, metadata,columns=TABLE2_COLUMNS)

def inspection(out, rows, store, annotations, metadata):
    stages, evaluations = store.stages(), store.evaluations()
    examples = []
    # Deterministic rule: first two task IDs per transition and condition, then repetition.
    for cond in metadata['conditions']:
        if len(cond)==1:
            continue
        for before,after,label in [(False,True,'fix'),(True,False,'regression')]:
            candidates = sorted((r for r in rows if r['condition']==cond and r['draft_outcome'] is before and r['outcome'] is after),key=lambda r:(r['task_id'],r['rep']))[:2]
            for r in candidates:
                key = f'{r["task_id"]}:{r["rep"]}:{cond}'
                ann = annotations.get(key,{})
                verified = ann.get('verified') is True
                examples.append({'task_id':r['task_id'],'rep':r['rep'],'condition':cond,'actual_draft_outcome':before,'final_outcome':after,
                                 'reviewer_action':ann.get('action','pending inspection')+('' if verified else ' (provisional)'),
                                 'interpretation':ann.get('interpretation','pending inspection')+('' if verified else ' (provisional)'), 'transition':label})
                bundle = out/'inspection'/key.replace('/','_').replace(':','_')
                bundle.mkdir(parents=True,exist_ok=True)
                draft,final = stages[r['writer_key']]['code'],stages[r['final_key']]['code']
                (bundle/'draft.py').write_text(draft,encoding='utf-8')
                (bundle/'final.py').write_text(final,encoding='utf-8')
                (bundle/'change.diff').write_text(''.join(difflib.unified_diff(draft.splitlines(True),final.splitlines(True),fromfile='draft.py',tofile='final.py')),encoding='utf-8')
                save(bundle/'evidence.json',{'draft':evaluations.get(r['writer_key']),'final':evaluations.get(r['final_key']),'metadata':metadata})
                save(bundle/'task.json',next(t for t in metadata['manifest_tasks'] if t['task_id']==r['task_id']))
    return examples

def report(config, manifest, store, out, annotation_path=None):
    out = Path(out)
    rows = records(config,manifest,store)
    stages = store.stages()
    ownership = {}
    for row in rows:
        for key in (row['writer_key'],row['final_key']):
            ownership.setdefault(key,row['condition'])
    attributed = defaultdict(float)
    for attempt in store.attempts():
        attributed[ownership.get(attempt['stage'],'unassigned')] += attempt['cost'] or 0.0
    meta = {'project':'Crosscode','config_hash':config.identity(),'design':config.design,'mock':config.mock,
            'task_count':len(manifest['tasks']),'dataset':manifest['source'],'subset':manifest['selection']['subset'],
            'settings':read(out.parent/'config.json'), 'conditions':config.conditions,
            'returned_models':sorted({r.get('returned_model') for r in stages.values() if r.get('returned_model')}),
            'requested_models':[config.claude_model,config.gpt_model], 'ledger':store.ledger(),
            'calibration_evidence':manifest.get('calibration'),
            'evaluator_migration':manifest.get('migration'),
            'bootstrap':{'seed':config.bootstrap_seed,'samples':config.bootstrap_samples,'unit':'task clusters, all available repetitions retained','interval':'percentile 2.5%, 97.5%; undefined below 2 clusters'}}
    annotations = read(annotation_path) if annotation_path else {}
    out.mkdir(parents=True,exist_ok=True)
    calibration_groups = defaultdict(list)
    for stage in stages.values():
        if stage.get('usage'):
            calibration_groups[(stage['model'],stage['role'])].append(stage)
    calibration = {'phase':config.phase,'synthetic':config.mock,'configuration_hash':config.identity(),
                   'prompt_templates_hash':digest(templates()),
                   'settings':meta['settings'],'task_ids':[t['task_id'] for t in manifest['tasks']],
                   'generation_status_counts':dict(Counter(s['status'] for s in stages.values())),
                   'stop_reasons':dict(Counter(str(s.get('stop_reason')) for s in stages.values())),
                   'evaluator_status_counts':dict(Counter(e['status'] for e in store.evaluations().values())),
                   'ledger':store.ledger(), 'groups':[]}
    for (model,role), group in calibration_groups.items():
        calibration['groups'].append({'model':model,'role':role,'observations':len(group),
            'mean_input_tokens':mean(s['usage']['input_tokens'] for s in group),
            'mean_output_tokens':mean(s['usage']['output_tokens'] for s in group),
            'mean_latency_s':mean(s['latency'] for s in group),
            'mean_cost_usd':mean(s['workflow_cost'] for s in group if s.get('workflow_cost') is not None) if any(s.get('workflow_cost') is not None for s in group) else None,
            'truncations':sum(s.get('truncated',False) for s in group),
            'parse_failures':sum(s['status']=='parse_failure' for s in group)})
    save(out/'calibration_summary.json',calibration)
    save(out/'results.json', {'metadata':meta,'records':rows})
    export_table(out,'task_results',rows,meta)
    from .audit import write_audit
    write_audit(config,manifest,store,rows,out/'task-audit',meta,annotations)
    population_reports = []
    for population in ['complete-case','reliability-inclusive']:
        popout = out/population
        pm = dict(meta,population=population)
        outcome_index = {(r['task_id'],r['rep'],r['condition']):r['outcome'] for r in rows}
        good = {(r['task_id'],r['rep']) for r in rows if all(outcome_index.get((r['task_id'],r['rep'],c)) is not None for c in config.conditions)}
        poprows = [r for r in rows if (r['task_id'],r['rep']) in good] if population=='complete-case' else [r for r in rows if r['reliability_eligible']]
        metrics = []
        for cond in config.conditions:
            allc = [r for r in rows if r['condition']==cond]
            selected = [r for r in poprows if r['condition']==cond]
            scored = [dict(r,score=float(bool(r['outcome']))) for r in selected]
            denom = len(scored)
            low,high = cluster_ci(scored,'score',config.bootstrap_seed,config.bootstrap_samples)
            cost_low,cost_high = cluster_ci(selected,'workflow_cost',config.bootstrap_seed,config.bootstrap_samples)
            latency_low,latency_high = cluster_ci(selected,'workflow_latency',config.bootstrap_seed,config.bootstrap_samples)
            def average(field):
                values = [r[field] for r in selected if r[field] is not None]
                return mean(values) if values else None
            rate = mean(r['score'] for r in scored) if scored else None
            transitions = {(a,b):sum(r['draft_outcome'] is a and r['outcome'] is b for r in selected) for a,b in itertools.product([False,True],repeat=2)}
            metrics.append({'condition':cond,'selected':len(allc),'attempted':sum(r['attempted'] for r in allc),
                            'valid':sum(r['valid'] for r in allc),'evaluated':sum(r['outcome'] is not None for r in selected),
                            'passed':sum(r['outcome'] is True for r in selected),'failed':sum(r['outcome'] is False for r in selected),
                            'not_run':sum(r['not_run'] for r in allc), 'infrastructure_failures':sum(r['infrastructure_failure'] for r in allc),
                            'invalid_attempts':sum(r['attempted'] and not r['not_run'] and not r['valid'] for r in allc),
                            'denominator':denom,'pass_rate':rate,'ci_low':low,'ci_high':high,'sid_pp':None,
                            'mean_workflow_cost_usd':average('workflow_cost'),'mean_workflow_latency_s':average('workflow_latency'),
                            'workflow_cost_ci_low':cost_low,'workflow_cost_ci_high':cost_high,
                            'workflow_latency_ci_low':latency_low,'workflow_latency_ci_high':latency_high,
                            'mean_writer_latency_s':average('writer_latency'),'mean_reviewer_latency_s':average('reviewer_latency'),
                            'writing_cost_usd':sum(r['writing_cost'] or 0 for r in selected),'reviewing_cost_usd':sum(r['reviewing_cost'] or 0 for r in selected),
                            'workflow_cost_usd':sum(r['workflow_cost'] or 0 for r in selected),'cost_known_rows':sum(r['workflow_cost'] is not None for r in selected),
                            'actual_run_spending_attributed_usd':attributed[cond],
                            'cross_condition_regression_rate':None,'cross_condition_denominator':0,
                            'reviewer_fixes':transitions[False,True] if len(cond)==2 else None,
                            'reviewer_regressions':transitions[True,False] if len(cond)==2 else None,
                            'kept_pass':transitions[True,True] if len(cond)==2 else None,'kept_fail':transitions[False,False] if len(cond)==2 else None,
                            'unscorable_drafts':sum(r['draft_outcome'] is None for r in selected) if len(cond)==2 else None})
        by = {r['condition']:r for r in metrics}
        for m in metrics:
            cond = m['condition']
            if len(cond)==2 and cond[0] in by:
                baseline = by[cond[0]]
                if m['pass_rate'] is not None and baseline['pass_rate'] is not None:
                    m['sid_pp'] = (m['pass_rate']-baseline['pass_rate'])*100
                pairs = [(r,s) for r in poprows if r['condition']==cond and r['outcome'] is not None for s in poprows
                         if s['condition']==cond[0] and s['task_id']==r['task_id'] and s['rep']==r['rep'] and s['outcome'] is not None]
                m['cross_condition_denominator'] = len(pairs)
                m['cross_condition_regression_rate'] = sum(s['outcome'] and not r['outcome'] for r,s in pairs)/len(pairs) if pairs else None
                deltas = [dict(task_id=r['task_id'],delta=(int(bool(r['outcome']))-int(bool(s['outcome'])))*100,
                               regression=float(bool(s['outcome']) and not bool(r['outcome']))) for r,s in pairs]
                m['paired_delta_pp'] = mean(r['delta'] for r in deltas) if deltas else None
                m['paired_delta_ci_low'],m['paired_delta_ci_high'] = cluster_ci(deltas,'delta',config.bootstrap_seed,config.bootstrap_samples)
                m['cross_regression_ci_low'],m['cross_regression_ci_high'] = cluster_ci(deltas,'regression',config.bootstrap_seed,config.bootstrap_samples)
        # Uniform table columns even when baselines do not have a paired contrast.
        for m in metrics:
            for field in ['paired_delta_pp','paired_delta_ci_low','paired_delta_ci_high','cross_regression_ci_low','cross_regression_ci_high']:
                m.setdefault(field,None)
        table2 = export_table(popout,'table2',metrics,pm,columns=TABLE2_COLUMNS)
        counts = export_table(popout,'counts',metrics,pm,columns=COUNT_COLUMNS)
        transition_table = export_table(popout,'review_transitions',[m for m in metrics if len(m['condition'])==2],pm,
            columns=['condition','reviewer_fixes','reviewer_regressions','kept_pass','kept_fail','unscorable_drafts'])
        export_table(popout,'all_metrics',metrics,pm)
        matrix = []
        for writer,name in [('A','Claude Opus 5.5'),('O','GPT-6.1 Sol')]:
            base = by.get(writer,{}).get('pass_rate')
            row = {'writer':name,'solo_pass_rate':base}
            for reviewer,label in [('A','Claude'),('O','GPT')]:
                m = by.get(writer+reviewer,{})
                row[label+'_pass_rate'] = m.get('pass_rate')
                row[label+'_delta_pp'] = m.get('sid_pp')
            matrix.append(row)
        export_table(popout,'table3_data',matrix,pm)
        matrix_display = []
        for row in matrix:
            base = row['solo_pass_rate']
            display = {'writer':row['writer']+' (solo '+(f'{base*100:.1f}%' if base is not None else 'NA')+')'}
            for label in ['Claude','GPT']:
                rate,delta = row[label+'_pass_rate'],row[label+'_delta_pp']
                display[label+' reviewer'] = (f'{rate*100:.1f}%' if rate is not None else 'NA')+' ('+(f'{delta:+.1f} pp' if delta is not None else 'delta NA')+')'
            matrix_display.append(display)
        table3 = export_table(popout,'table3',matrix_display,pm)
        stats = statistics(rows,config.conditions,config.repeats,population)
        export_table(popout,'all_pairwise',stats,pm)
        table4 = export_table(popout,'table4',selected_comparisons(stats),pm)
        examples = inspection(popout,poprows,store,annotations,dict(pm,manifest_tasks=manifest['tasks']))
        table5 = export_table(popout,'table5',examples,pm,columns=['task_id','rep','condition','actual_draft_outcome','final_outcome','reviewer_action','interpretation','transition'])
        figure(popout,metrics,pm)
        title = 'SYNTHETIC DEMONSTRATION — no real model results' if config.mock else 'Pilot / proof of concept' if len(manifest['tasks'])<=10 else 'Experiment results'
        text = f'# Crosscode — {title}\n\nDesign: {config.design}. Population: {population}. Configuration: `{config.identity()}`.\n\n'
        text += '[Task-by-task audit: requirements, exact model responses, code and evaluator evidence](../task-audit/index.md).\n\n'
        text += 'Requested models: '+', '.join(meta['requested_models'])+'. Returned: '+', '.join(meta['returned_models'])+'.\n\n'
        text += f'Subset: {meta["subset"]}; selected tasks: {meta["task_count"]}; split: {config.split}; repeats: {config.repeats}. Both efforts: {config.claude_effort} / {config.gpt_effort}; output caps: {config.claude_max_output_tokens} / {config.gpt_max_output_tokens}.\n\n'
        text += 'Full dataset revisions, requested/returned identifiers, settings and population accompany every artifact in metadata sidecars.\n\n'
        if manifest.get('migration'):
            text += 'Evaluator-only continuation from `'+manifest['migration']['source_run']+'`: exact compatible generation outputs and their original provenance were retained; programs are rescored in this run\'s image. Spending includes inherited purchases/reservations; do not add it to the source run\'s spending. [Migration record](../../migration.json).\n\n'
        text += 'Dataset revision: `'+json.dumps(meta['dataset'].get('revision'),sort_keys=True)+'`.\n\n'
        text += 'Table 2: overall metrics (rates are fractions, SID is percentage points). `selected` and `attempted` count task-repetition workflows; denominator is explicit. CC includes only task-repetition pairs evaluated in every requested condition. Reliability includes terminal invalid attempts as failures; budget-unstarted finals and infrastructure failures are excluded.\n\n'+table2+'\n'
        text += 'Coverage and status counts (all selected workflows, with evaluated/pass/fail for this population):\n\n'+counts+'\n'
        text += 'Writer/reviewer costs and latencies, true review-transition counts, unknown-cost coverage and bootstrap intervals: [all metrics](all_metrics.csv).\n\n'
        text += 'Genuine transitions for the actual draft received by each reviewer (only observed before/after pairs contribute; drafts without scores are unscorable):\n\n'+transition_table+'\n'
        text += 'Table 3: writer-by-reviewer matrix; solo rate accompanies writer.\n\n'+table3+'\n'
        text += 'Table 4: exact paired McNemar, separately per repetition. BH family is all requested condition pairs in each population/repetition (15 for six conditions); full family exported. NA means no paired observations. No pooled task-repetition significance test.\n\n'+table4+'\n'
        text += 'Table 5: first two task IDs per condition and true same-draft transition, ordered by ID then repetition. Explanations require verified local annotations.\n\n'+(table5 if examples else 'No genuine same-draft fixes or regressions were observed in this population.\n')+'\n'
        text += '![Figure 2](figure2.png)\n\nFigure 2 uses precisely Table 2 coordinates; workflow costs include writer and reviewer, with intentional shared drafts charged to each hypothetical standalone workflow. Actual purchased calls are counted once in the ledger. Independent-mode arrows compare independently sampled pipelines.\n\n'
        text += f'Actual API spending (whole run): ${store.ledger()["actual_usd"]:.6f}; unresolved reservation: ${store.ledger()["reserved_usd"]:.6f}. '
        if config.mock:
            text += 'Costs on the plot are synthetic token-price examples, latency is a fixed synthetic fixture; actual API spending is zero. '
        text += 'Partial workflow cost sums include known values only; cost_known_rows identifies coverage. Actual run spending is attributed once to the first requested condition using each call (canonical condition order), across all selected work, independently of analysis population; shared writer attribution is bookkeeping. Cross-condition regression denominator is paired evaluated workflows; it does not identify reviewer-induced regressions. Same-draft transitions do.\n\n'
        text += f'Uncertainty: {config.bootstrap_samples} seeded percentile bootstrap resamples of task clusters (seed {config.bootstrap_seed}); all available repeats travel with their task. Below two tasks CI is undefined; tiny-sample bootstrap intervals can be degenerate and are not evidence of certainty. Repetition aggregates are descriptive.\n\n'
        text += 'Limitations: proof-of-concept samples do not establish a general winner. BigCodeBench replaces competitive programming with library-dependent functions; contamination is possible. No repository-scale validation. Medium effort and equal caps do not equate compute, cost or capability. Aliases and results are version-dependent. Local cost guards are not a provider billing guarantee.\n'
        (popout/'report.md').write_text(text,encoding='utf-8')
        population_reports.append(f'- [{population}]({population}/report.md)')
    (out/'report.md').write_text('# Crosscode\n\n'+('SYNTHETIC DEMONSTRATION; no real inference or benchmark results.\n\n' if config.mock else 'Pilot / proof of concept.\n\n')+'\n'.join(population_reports)+'\n\n[Task-by-task audit: requirements, exact responses, code and evaluator evidence](task-audit/index.md).\n\nProvenance: `'+json.dumps(provenance_fields(meta),sort_keys=True)+'`.\n\nSee [saved results](results.json).\n',encoding='utf-8')
