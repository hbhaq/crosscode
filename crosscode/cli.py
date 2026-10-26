from __future__ import annotations
import argparse
import dataclasses
import datetime
import json
import math
import re
from pathlib import Path
from .core import CONDITIONS, Config, ROOT, digest, load_tasks, plan, read, save, select, templates
from .store import Store
from .progress import Progress, emit, watch

def parser():
    p = argparse.ArgumentParser(prog='crosscode', description='Crosscode: one-pass cross-model review; no inference in dry-run/report/evaluate modes.')
    p.add_argument('command', nargs='?', choices=['run', 'expand', 'preflight', 'report', 'reconcile','fork-evaluator'], default='run')
    p.add_argument('--config', type=Path, help='JSON configuration; credentials only from environment')
    p.add_argument('--run-id')
    p.add_argument('--new-run-id', help='New destination run for an explicit evaluator-only continuation')
    p.add_argument('--resume', metavar='RUN_ID')
    p.add_argument('--runs-dir', type=Path, default=ROOT/'runs')
    p.add_argument('--subset', choices=['full','hard','non-hard'])
    p.add_argument('--tasks', help='Positive count or all (default 5)')
    p.add_argument('--seed', type=int)
    p.add_argument('--task-ids')
    p.add_argument('--task-file', type=Path)
    p.add_argument('--include-libs', help='Comma separated exact library names; all must match')
    p.add_argument('--exclude-libs', help='Comma separated exact library names; any match excludes')
    p.add_argument('--list-tasks', action='store_true')
    p.add_argument('--design', choices=['paper-independent', 'shared-draft'])
    p.add_argument('--conditions', help='all, baselines, cross-review, or comma separated A,O,AO,OA,AA,OO')
    p.add_argument('--max-cost-usd', type=float)
    p.add_argument('--max-task-cost-usd', type=float)
    p.add_argument('--gpt-model')
    p.add_argument('--claude-model')
    p.add_argument('--gpt-max-output-tokens', type=int)
    p.add_argument('--claude-max-output-tokens', type=int)
    p.add_argument('--gpt-effort', choices=['low','medium','high','xhigh','max'])
    p.add_argument('--claude-effort', choices=['low','medium','high','max'])
    p.add_argument('--parallelism', type=int)
    p.add_argument('--repeats', type=int)
    p.add_argument('--max-retries', type=int)
    p.add_argument('--api-timeout', type=float)
    p.add_argument('--eval-timeout', type=float)
    p.add_argument('--profile', choices=['personal','company'])
    p.add_argument('--phase', choices=['calibration','main'])
    p.add_argument('--mock', action='store_true', default=None)
    p.add_argument('--split', choices=['instruct','complete'])
    p.add_argument('--evaluator-image', help='Immutable Docker image ID sha256:... or repository@sha256:...')
    p.add_argument('--evaluator-egress-proxy-image',help='Explicit immutable Wikibooks-only proxy image; evaluator retains network=none')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--evaluate-only', action='store_true')
    p.add_argument('--report-only', action='store_true')
    p.add_argument('--attempt-id', type=int)
    p.add_argument('--verified-cost-usd', type=float)
    p.add_argument('--billing-evidence')
    p.add_argument('--annotations', type=Path)
    p.add_argument('--calibration-summary', type=Path, help='Saved representative pilot summary for an explicitly qualified expected-cost forecast')
    p.add_argument('--progress-interval', type=float, default=None, help='Seconds between waiting messages (default 15); presentation only')
    p.add_argument('--quiet-progress', action='store_true', default=None, help='Hide live console progress; keep progress.log; presentation only')
    p.add_argument('--verified-preflight', type=Path, help='Matching completed canonical preflight to validate and reuse during fork-evaluator')
    return p

def condition_ids(value):
    aliases = {'all': CONDITIONS, 'baselines': ('A','O'), 'cross-review': ('AO','OA')}
    result = aliases.get(value, tuple(value.split(',')))
    if not result or len(set(result)) != len(result) or set(result)-set(CONDITIONS):
        raise ValueError('Unknown or duplicate conditions')
    return tuple(c for c in CONDITIONS if c in result)

def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        dispatch(args)
    except (ValueError, FileNotFoundError, OSError, KeyError) as exc:
        p.exit(2, f'crosscode: {exc}\n')

def dispatch(args):
    supplied = read(args.config) if args.config else {}
    allowed = {f.name for f in dataclasses.fields(Config)} | {'subset','tasks','seed','include_libs','exclude_libs','parallelism','max_cost_usd','max_task_cost_usd','progress_interval','quiet_progress'}
    if set(supplied)-allowed:
        raise ValueError('Unknown config keys: '+str(set(supplied)-allowed))
    supplied.update({k: v for k,v in vars(args).items() if v is not None and k in allowed})
    if 'conditions' in supplied:
        supplied['conditions'] = condition_ids(supplied['conditions']) if isinstance(supplied['conditions'], str) else tuple(supplied['conditions'])
    run_id = args.resume or args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Run ID must contain only letters, digits, underscores and hyphens')
    directory = args.runs_dir/run_id
    fields = {f.name for f in dataclasses.fields(Config)}
    frozen = directory/'config.json'
    existing = frozen.exists()
    if existing:
        old = read(frozen)
        old['conditions'] = tuple(old['conditions'])
        for k,v in supplied.items():
            if args.command=='fork-evaluator' and k in ('evaluator_image','evaluator_egress_proxy_image'):
                continue
            if k in fields and old.get(k,getattr(Config(),k)) != v:
                raise ValueError(f'Frozen setting {k} differs. Create a new run ID.')
        config = Config(**old)
        manifest = read(directory/'manifest.json')
        if args.calibration_summary:
            raise ValueError('Calibration evidence is frozen at run creation')
        if config.identity() != manifest['config_hash']:
            raise ValueError('Configuration/prompts/source lock changed. Existing cache is incompatible; start a new run.')
        if args.command != 'expand':
            for k in ('tasks','subset','seed','include_libs','exclude_libs'):
                if k in supplied and str(supplied[k]) != str(manifest['selection'].get(k)):
                    raise ValueError('Resume cannot change task selection; use expand')
            if args.task_ids or args.task_file:
                raise ValueError('Resume cannot alter task IDs')
    else:
        if args.resume or args.command in ('expand','report','preflight','reconcile','fork-evaluator') or args.evaluate_only or args.report_only:
            raise ValueError('Existing --resume RUN_ID is required')
        config = Config(**{k:v for k,v in supplied.items() if k in fields})
        if config.design not in ('paper-independent', 'shared-draft') or set(config.conditions)-set(CONDITIONS):
            raise ValueError('Invalid design or conditions')
        if config.repeats < 1 or config.max_retries < 0 or min(config.gpt_max_output_tokens,config.claude_max_output_tokens,config.api_timeout,config.eval_timeout) <= 0:
            raise ValueError('Caps, repeats and timeouts must be positive; retries must be nonnegative')
        if args.task_ids and args.task_file:
            raise ValueError('--task-ids conflicts with --task-file')
        ids = args.task_ids.split(',') if args.task_ids else args.task_file.read_text().split() if args.task_file else None
        selection = {'subset': supplied.get('subset','full'), 'tasks': str(supplied.get('tasks','5')), 'seed': supplied.get('seed',42),
                     'include_libs': supplied.get('include_libs',''), 'exclude_libs': supplied.get('exclude_libs','')}
        pool, source = load_tasks(config.mock)
        selected, eligible = select(pool, selection['subset'], selection['tasks'], selection['seed'], ids,
                                    tuple(filter(None,selection['include_libs'].split(','))), tuple(filter(None,selection['exclude_libs'].split(','))))
        if args.list_tasks:
            print(json.dumps([{'task_id': t['task_id'], 'libs': t['libs']} for t in selected], indent=2))
            return
        manifest = {'project': 'Crosscode', 'config_hash': config.identity(), 'source': source, 'selection': selection,
                    'tasks': selected, 'eligible_ids': [t['task_id'] for t in eligible],
                    'eligible_hashes': {t['task_id']: digest(t) for t in eligible}, 'history': []}
        if args.calibration_summary:
            pilot = read(args.calibration_summary)
            if pilot.get('phase') != 'calibration' or bool(pilot.get('synthetic')) != config.mock:
                raise ValueError('Calibration evidence must be a labeled pilot with matching synthetic/live provenance')
            if pilot.get('prompt_templates_hash') != digest(templates()):
                raise ValueError('Calibration prompts differ from the current frozen templates')
            for key in ['design','gpt_model','claude_model','gpt_effort','claude_effort','gpt_max_output_tokens','claude_max_output_tokens','split']:
                if pilot['settings'].get(key) != getattr(config,key):
                    raise ValueError('Calibration setting differs: '+key)
            pilot['overlap_with_main_ids'] = sorted(set(pilot['task_ids']) & {t['task_id'] for t in selected})
            manifest['calibration'] = pilot
        save(frozen, dataclasses.asdict(config))
        save(directory/'manifest.json', manifest)
    if not config.conditions or len(set(config.conditions)) != len(config.conditions) or set(config.conditions)-set(CONDITIONS):
        raise ValueError('Unknown, duplicate or empty conditions')
    if config.gpt_effort not in ('low','medium','high','xhigh','max') or config.claude_effort not in ('low','medium','high','max'):
        raise ValueError('Unsupported effort; never silently substitute')
    if args.command=='fork-evaluator':
        if not args.new_run_id or not re.fullmatch(r'[A-Za-z0-9_-]+',args.new_run_id) or not args.evaluator_image:
            raise ValueError('fork-evaluator requires --new-run-id and an immutable --evaluator-image')
        from .migration import fork_evaluator
        migration = fork_evaluator(directory,args.runs_dir/args.new_run_id,args.evaluator_image,args.verified_preflight,
                                  evaluator_egress_proxy_image=args.evaluator_egress_proxy_image)
        print(json.dumps(migration,indent=2))
        print('Continuation ready: '+args.new_run_id+'. No inference calls made; all saved programs require destination-image evaluation.')
        return
    store = Store(directory/'checkpoint.sqlite')
    interval = supplied.get('progress_interval',15.0)
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError('--progress-interval must be positive and finite')
    progress = Progress(interval=interval,console=not supplied.get('quiet_progress',False),log_path=directory/'progress.log')
    if args.command == 'expand':
        n = len(manifest['eligible_ids']) if args.tasks == 'all' else int(args.tasks or 0)
        if n <= len(manifest['tasks']) or n > len(manifest['eligible_ids']):
            raise ValueError('Expansion count must exceed current count and not exceed frozen eligible pool')
        pool, source = load_tasks(config.mock)
        byid = {t['task_id']: t for t in pool}
        appended = [byid[k] for k in manifest['eligible_ids'][len(manifest['tasks']):n]]
        if any(digest(t) != manifest['eligible_hashes'][t['task_id']] for t in appended):
            raise ValueError('Dataset changed since manifest was frozen')
        manifest['history'].append({'previous_manifest_hash': digest(manifest), 'from': len(manifest['tasks']), 'to': n})
        manifest['tasks'].extend(appended)
        if manifest.get('calibration'):
            manifest['calibration']['overlap_with_main_ids'] = sorted(set(manifest['calibration']['task_ids']) & {t['task_id'] for t in manifest['tasks']})
        manifest['selection']['tasks'] = str(n)
        save(directory/'manifest.json', manifest)
        print(f'Expanded {run_id} to {n} tasks; saved stages and cumulative ledger preserved.')
        return
    if args.command == 'reconcile':
        if args.attempt_id is None or args.verified_cost_usd is None or not args.billing_evidence:
            raise ValueError('Reconcile requires --attempt-id, --verified-cost-usd and --billing-evidence')
        store.reconcile(args.attempt_id,args.verified_cost_usd,args.billing_evidence)
        print(json.dumps(store.ledger(), indent=2))
        return
    from .evaluator import evaluate_saved, preflight
    from .report import report
    if args.command == 'report' or args.report_only:
        with watch(progress, f'REPORT {run_id} | regenerate tables, figures and task audit (no inference)'):
            report(config, manifest, store, directory/'report', args.annotations)
        emit(progress, 'REPORT SAVED '+str(directory/'report'/'report.md'))
        print(directory/'report'/'report.md')
        return
    if args.command == 'preflight':
        if config.mock:
            raise ValueError('Mock runs have no real evaluator preflight')
        preflight(config, manifest, directory, progress=progress)
        print('Canonical preflight passed')
        return
    if args.evaluate_only:
        if not config.mock:
            preflight(config, manifest, directory, progress=progress)
        evaluate_saved(config, manifest, store, progress=progress)
        with watch(progress, f'REPORT {run_id} | regenerate saved results (no inference)'):
            report(config, manifest, store, directory/'report', args.annotations)
        emit(progress, 'REPORT SAVED '+str(directory/'report'/'report.md'))
        return
    # Runtime budget controls survive resumes independently of experimental identity.
    control_path = directory/'controls.json'
    controls = read(control_path) if control_path.exists() else {'max_cost_usd': 5.0, 'max_task_cost_usd': 2.0, 'parallelism': 1}
    controls.update({k: supplied[k] for k in controls if k in supplied})
    if any(not math.isfinite(v) or v<=0 for v in controls.values()) or int(controls['parallelism']) != controls['parallelism']:
        raise ValueError('Budgets and integer parallelism must be positive')
    save(control_path, controls)
    from .runner import execute, preview
    view = preview(config, manifest, store, controls['max_cost_usd'], controls['max_task_cost_usd'])
    view['run_id'] = run_id
    preflight_state = read(directory/'preflight.json') if (directory/'preflight.json').exists() else {}
    view['evaluator_preflight_completed'] = bool(preflight_state.get('passed') and set(preflight_state.get('results',{})) == {t['task_id'] for t in manifest['tasks']})
    print(json.dumps(view, indent=2),flush=True)
    if args.dry_run:
        return
    emit(progress, f'RUN {run_id} | log: {directory/"progress.log"}')
    if not config.mock:
        if config.gpt_model != 'gpt-6.1-sol' or config.claude_model != 'claude-opus-5-5':
            raise ValueError('Custom models require a reviewed pricing/parameter snapshot; live execution blocked, no substitution')
        if 'sha256:' not in config.evaluator_image:
            raise ValueError('Live execution requires immutable --evaluator-image SHA256; use a new run with the pinned image')
        preflight(config, manifest, directory, progress=progress)
        from .providers import availability
        with watch(progress, 'MODEL ACCESS read-only provider model checks (no inference)'):
            availability(config)
        emit(progress, 'MODEL ACCESS verified')
    summary = execute(config, manifest, store, controls['max_cost_usd'], controls['max_task_cost_usd'], controls['parallelism'],progress=progress)
    save(directory/'execution.json', summary)
    evaluate_saved(config, manifest, store, progress=progress)
    with watch(progress, f'REPORT {run_id} | generate tables, figures and task audit (no inference)'):
        report(config, manifest, store, directory/'report', args.annotations)
    emit(progress, 'REPORT SAVED '+str(directory/'report'/'report.md'))
    print(json.dumps(summary, indent=2))
    print(directory/'report'/'report.md')
