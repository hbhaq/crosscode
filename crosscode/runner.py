import dataclasses
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from .core import digest, parse, plan, prompt, read, save
from . import providers
from .store import BudgetStop
from .progress import emit, generation_totals, watch

def cache_identity(config, job, task, rendered, parent):
    return digest({'config': config.identity(), 'job': job, 'dataset_task': digest(task),
                   'provider': 'openai' if job['model'] == 'O' else 'anthropic',
                   'settings': providers.settings(config, job['model']), 'prompt': digest(rendered),
                   'parent_draft': parent.get('code_hash') if parent else None})

def execute(config, manifest, store, max_cost, max_task_cost, parallelism=1, progress=None):
    if store.ledger()['unresolved_attempts']:
        emit(progress, 'STOP unresolved usage from an earlier attempt; reconcile billing before generation')
        return {'messages': ['Unresolved usage from an earlier attempt; reconcile vendor billing before generation.'],
                'ledger': store.ledger(), 'completed_stages': len(store.stages()), 'planned_stages': len(plan(config, manifest['tasks']))}
    jobs = plan(config, manifest['tasks'])
    tasks = {t['task_id']: t for t in manifest['tasks']}
    stop = threading.Event()
    messages = []
    emit(progress, f'GENERATION {len(tasks)} selected tasks; {parallelism} worker(s) | '+generation_totals(store,len(jobs)))
    emit(progress, 'Saved-stage counts include terminal errors; they are not test-pass counts.')

    def task_pipeline(task_id):
        for job in [j for j in jobs if j['task_id'] == task_id]:
            if stop.is_set():
                return
            stages = store.stages()
            parent = stages.get(job['parent']) if job['parent'] else None
            label = f'{task_id} | {job["arm"]} | repetition {job["rep"]+1}/{config.repeats} | {job["role"]}'
            if job['parent'] and (not parent or parent['status'] != 'valid'):
                emit(progress, 'SKIP '+label+' | required writer draft is unavailable/invalid')
                continue
            task = tasks[task_id]
            rendered = prompt(task, config.split, parent['code'] if parent else None)
            identity = cache_identity(config, job, task, rendered, parent)
            if job['key'] in stages:
                if stages[job['key']]['identity'] != identity:
                    raise ValueError('Incompatible cache identity. Start a separate run.')
                emit(progress, 'CACHE '+label+' | saved output reused; no API call')
                continue
            previous = [a for a in store.attempts() if a['stage'] == job['key']]
            for attempt in range(len(previous), config.max_retries + 1):
                allowance = 0.0 if config.mock else providers.allowance(job['model'], rendered, providers.settings(config, job['model'])['max_output_tokens'])
                try:
                    aid = store.reserve(job['key'], task_id, attempt, allowance, max_cost, max_task_cost)
                except BudgetStop as exc:
                    emit(progress, 'STOP '+label+' | '+str(exc)+' | '+generation_totals(store,len(jobs)))
                    messages.append(str(exc))
                    stop.set()
                    return
                base = {**job, 'identity': identity, 'config_hash': config.identity(), 'task_hash': digest(task),
                        'prompt': rendered, 'prompt_hash': digest(rendered), 'parent_hash': parent['code_hash'] if parent else None,
                        'settings': providers.settings(config, job['model']), 'pricing': providers.PRICING,
                        'attempt_id': aid, 'attempt': attempt, 'code': '', 'code_hash': digest('')}
                emit(progress, f'RESERVED attempt ID {aid} | allowance ${allowance:.6f} | '+generation_totals(store,len(jobs)))
                started = time.time()
                try:
                    request_label = label+f' | {base["settings"]["model"]} | attempt ID {aid} ({attempt+1}/{config.max_retries+1})'
                    with watch(progress, ('MOCK ' if config.mock else 'API ')+request_label):
                        result, cost = (providers.mock_generate if config.mock else providers.generate)(config, job, rendered)
                    code, status = parse(result['text'])
                    if result['truncated']:
                        status = 'truncation'
                    elif result.get('provider_complete') is False:
                        status = 'incomplete_response'
                    base.update(result, code=code, code_hash=digest(code), status=status)
                    base['raw_response_hash'] = digest(result['raw'])
                    base['raw_text_hash'] = digest(result['text'])
                    base['cost'] = cost
                    base['workflow_cost'] = providers.price(job['model'], result['usage']) if config.mock else cost
                    store.finish(aid, base, cost, job['key'], identity)
                    emit(progress, 'SAVED '+request_label+f' | {status}; stop={result.get("stop_reason")}; {result.get("latency",0):.1f}s | '+generation_totals(store,len(jobs)))
                    if cost is None:
                        emit(progress, f'STOP attempt ID {aid} has unknown usage; reservation retained; reconcile billing')
                        stop.set()
                        messages.append('Unknown response usage; reservation retained')
                        return
                    # Truncation and parsing are terminal, never silently regenerated.
                    break
                except Exception as exc:
                    # No exception string logging: vendor/network messages may echo secrets.
                    known_unbilled = isinstance(exc, urllib.error.HTTPError) and exc.code in (400,401,403,404,422,429)
                    base.update(status='api_failure', error_type=type(exc).__name__,
                                http_status=getattr(exc, 'code', None), latency=time.time()-started,
                                requested_model=providers.settings(config, job['model'])['model'], returned_model=None)
                    retry = known_unbilled and getattr(exc, 'code', None) == 429 and attempt < config.max_retries
                    base['retry_planned'] = retry
                    store.finish(aid, base, 0.0 if known_unbilled else None, None if retry else job['key'], identity)
                    emit(progress, 'ERROR '+label+f' | attempt ID {aid}; {type(exc).__name__}; HTTP {getattr(exc,"code",None)}; {base["latency"]:.1f}s | '+generation_totals(store,len(jobs)))
                    if retry:
                        emit(progress, f'RETRY attempt ID {aid} returned known-unbilled 429; using declared retry allowance')
                    if not known_unbilled:
                        emit(progress, f'STOP attempt ID {aid} may have incurred a charge; reservation retained; reconcile billing')
                        messages.append('Unknown usage after API error; reservation retained. Reconcile billing before further generation.')
                        stop.set()
                    if not retry:
                        break
    with ThreadPoolExecutor(max_workers=parallelism) as pool:
        list(pool.map(task_pipeline, tasks))
    emit(progress, 'GENERATION STOPPED' if stop.is_set() else 'GENERATION FINISHED')
    emit(progress, generation_totals(store,len(jobs)))
    return {'messages': messages, 'ledger': store.ledger(), 'completed_stages': len(store.stages()), 'planned_stages': len(jobs)}

def preview(config, manifest, store, max_cost, max_task_cost):
    jobs = plan(config, manifest['tasks'])
    cached = store.stages()
    estimates = []
    for job in jobs:
        if job['key'] in cached:
            continue
        task = next(t for t in manifest['tasks'] if t['task_id'] == job['task_id'])
        rendered = prompt(task, config.split, '' if job['parent'] else None)
        # Reviewer text is unknown. Use the maximum accepted input band; larger
        # actual inputs are rejected before a reservation or inference call.
        if job['parent']:
            estimates.append((200000 * providers.max_input_rate(job['model']) + providers.settings(config, job['model'])['max_output_tokens'] * providers.PRICING[job['model']]['output'])/1e6)
            continue
        try:
            estimates.append(providers.allowance(job['model'], rendered, providers.settings(config, job['model'])['max_output_tokens']))
        except ValueError:
            estimates.append(None)
    expected = 'Unavailable: no calibration pilot data'
    pilot = manifest.get('calibration')
    if pilot:
        means = {(g['model'],g['role']):g['mean_cost_usd'] for g in pilot['groups']}
        remaining = [j for j in jobs if j['key'] not in cached]
        if all(means.get((j['model'],j['role'])) is not None for j in remaining):
            expected = {'remaining_mean_cost_usd': sum(means[j['model'],j['role']] for j in remaining),
                        'method': 'Sum of compatible pilot per-model/per-role sample means; not guaranteed; assumes representative task/token usage, omits unknown future retries',
                        'pilot_configuration': pilot['configuration_hash'], 'overlap_ids': pilot['overlap_with_main_ids']}
    return {'task_ids': [t['task_id'] for t in manifest['tasks']], 'source': manifest['source'],
            'design': config.design, 'conditions': config.conditions, 'repetitions': config.repeats,
            'configuration_hash': config.identity(), 'planned_generation_calls': len(jobs),
            'cached_stages': len(cached), 'remaining_stages': len(jobs)-len(cached),
            'settings': dataclasses.asdict(config), 'pricing': providers.PRICING,
            'expected_cost': expected,
            'conservative_remaining_allowances_usd': sum(estimates) if all(x is not None for x in estimates) else None,
            'budget_check': 'Conservative plan fits total budget' if all(x is not None for x in estimates) and sum(estimates)+sum(store.ledger()[k] for k in ['actual_usd','reserved_usd']) <= max_cost else 'Full conservative plan does not fit; execution will checkpoint before a reservation exceeds either limit',
            'allowance_note': 'Input byte bounds, output caps; reviewer allowance depends on actual saved draft. Not a billing guarantee.',
            'max_cost_usd': max_cost, 'max_task_cost_usd': max_task_cost,
            'ledger': store.ledger(), 'inference_calls_in_dry_run': 0}
