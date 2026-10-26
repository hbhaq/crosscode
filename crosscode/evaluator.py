"""Only Docker executes candidate programs. No host execution path exists."""
import json
import re
import subprocess
import uuid
from contextlib import nullcontext
from .core import digest, read, save
from .progress import emit, watch
from .network_policy import EGRESS_POLICY
from .egress import EgressSetupError, restricted_broker

def preflight_diagnostics(results):
    failed = []
    missing = {}
    network_errors = []
    for task_id,result in results.items():
        if result.get('passed') is True:
            continue
        failed.append(task_id)
        details = [str(result.get('stderr',''))]
        for row in result.get('evidence',{}).get('eval',{}).get(task_id,[]):
            details.extend(str(value) for value in row.get('details',{}).values())
        modules = sorted(set(re.findall(r'No module named [\"\']([A-Za-z0-9_.]+)[\"\']','\n'.join(details))))
        if modules:
            missing[task_id] = modules
        if any(marker in '\n'.join(details) for marker in ['Temporary failure in name resolution','Network is unreachable','Name or service not known']):
            network_errors.append(task_id)
    return {'checked':len(results),'passed':len(results)-len(failed),'failed_task_ids':failed,
            'missing_modules':missing,'network_error_task_ids':network_errors}

def image_id(image):
    if not image:
        raise ValueError('Evaluator image missing: build docker/Dockerfile and configure --evaluator-image')
    proc = subprocess.run(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise ValueError('Docker engine/image unavailable: '+proc.stderr.strip())
    return proc.stdout.strip()

def docker_command(image, name, timeout,egress_volume=None):
    command = ['docker', 'run', '--rm', '--name', name, '-i', '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '128',
            '--memory', '4g', '--cpus', '2', '--ulimit', 'nofile=1024:1024',
            '--user', '65534:65534', '--tmpfs', '/tmp:rw,nosuid,nodev,size=1g',
            '--tmpfs', '/work:rw,exec,nosuid,nodev,size=1g,uid=65534,gid=65534,mode=0700',
            '-e', 'HOME=/tmp', '-e', 'MPLCONFIGDIR=/tmp/matplotlib',
            '-e', 'HF_HUB_OFFLINE=1', '-e', 'HF_DATASETS_OFFLINE=1']
    if egress_volume:
        command += ['--mount',f'type=volume,source={egress_volume},target=/egress,readonly,volume-nocopy',
                    '-e','CROSSCODE_EGRESS_SOCKET=/egress/proxy.sock']
        for variable in ['HTTPS_PROXY','HTTP_PROXY','https_proxy','http_proxy']:
            command += ['-e',variable+'=http://127.0.0.1:3128']
        command += ['-e','ALL_PROXY=','-e','all_proxy=','-e','NO_PROXY=localhost,127.0.0.1','-e','no_proxy=localhost,127.0.0.1']
    return command+[image]

def runtime_descriptor(config):
    plain=docker_command(config.evaluator_image,'<container>',config.eval_timeout)
    if not config.evaluator_egress_proxy_image:
        return plain  # Backward-compatible identity for all existing offline runs.
    return {'offline_command':plain,'allowed_task_command':docker_command(config.evaluator_image,'<container>',config.eval_timeout,'<private-socket-volume>'),
            'proxy_image':config.evaluator_egress_proxy_image,'policy':EGRESS_POLICY}

def evaluate(config, task, code, canonical=False):
    name = 'crosscode-'+uuid.uuid4().hex
    payload = {'task': task, 'code': code, 'split': config.split}
    needs_egress=bool(config.evaluator_egress_proxy_image and task['task_id'] in EGRESS_POLICY['task_ids'])
    context=restricted_broker(config.evaluator_egress_proxy_image,name,config.eval_timeout) if needs_egress else nullcontext((None,config.eval_timeout))
    try:
        with context as (volume,remaining):
            command = docker_command(config.evaluator_image,name,config.eval_timeout,volume)
            try:
                proc = subprocess.run(command,input=json.dumps(payload),capture_output=True,text=True,
                                      encoding='utf-8',errors='replace',timeout=remaining)
                marker = 'CROSSCODE_RESULT='
                lines = [l[len(marker):] for l in proc.stdout.splitlines() if l.startswith(marker)]
                if proc.returncode or not lines:
                    return {'status':'infrastructure_failure','passed':None,'stderr':proc.stderr[-10000:],'stdout':proc.stdout[-10000:]}
                result=json.loads(lines[-1])
                result['image']=config.evaluator_image
                result['runtime']=runtime_descriptor(config)
                result['restricted_egress_used']=needs_egress
                return result
            finally:
                subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)
    except subprocess.TimeoutExpired:
        return {'status': 'infrastructure_timeout', 'passed': None}
    except EgressSetupError as exc:
        return {'status':'infrastructure_failure','passed':None,'stderr':str(exc)}

def preflight(config, manifest, run_dir, progress=None):
    with watch(progress, 'PREFLIGHT inspect Docker image'):
        image = image_id(config.evaluator_image)
        if config.evaluator_egress_proxy_image:
            image_id(config.evaluator_egress_proxy_image)
    runtime = runtime_descriptor(config)
    key = digest({'image': image, 'tasks': manifest['tasks'], 'split': config.split,
                  'timeout': config.eval_timeout, 'runtime': runtime})
    path = run_dir/'preflight.json'
    if path.exists():
        old = read(path)
        if old.get('key') == key and old.get('passed'):
            emit(progress, f'PREFLIGHT CACHE all {len(manifest["tasks"])} selected canonical solutions already passed; reuse verified preflight')
            return old
    results = {}
    for number,t in enumerate(manifest['tasks'],1):
        code = t['complete_prompt'] + '\n' + t['canonical_solution']
        with watch(progress, f'PREFLIGHT {number}/{len(manifest["tasks"])} | {t["task_id"]} | canonical solution [Docker]'):
            results[t['task_id']] = evaluate(config, t, code, canonical=True)
        save(path, {'key': key, 'image': image, 'passed': False, 'results': results})
        emit(progress, f'PREFLIGHT SAVED {number}/{len(manifest["tasks"])} | {t["task_id"]} | {results[t["task_id"]]["status"]}')
    diagnostics = preflight_diagnostics(results)
    result = {'key': key, 'image': image, 'runtime': runtime,'diagnostics':diagnostics,
              'passed': all(r.get('passed') is True for r in results.values()), 'results': results}
    save(path, result)
    if not result['passed']:
        modules = sorted({module for values in diagnostics['missing_modules'].values() for module in values})
        hint = ' Missing Python modules: '+', '.join(modules)+'.' if modules else ''
        if diagnostics['network_error_task_ids']:
            hint += ' Network/DNS failures observed for '+', '.join(diagnostics['network_error_task_ids'])+'; current evaluator network is disabled.'
        emit(progress, f'PREFLIGHT FAILED {len(diagnostics["failed_task_ids"])}/{len(results)} canonical solutions; paid generation blocked.'+hint+' Inspect preflight.json.')
        raise ValueError('Canonical evaluator preflight failed.'+hint+' Inspect preflight.json. Paid execution blocked.')
    emit(progress, 'PREFLIGHT PASSED; all selected canonical solutions verified')
    return result

def evaluate_saved(config, manifest, store, progress=None):
    tasks = {t['task_id']: t for t in manifest['tasks']}
    existing = store.evaluations()
    stages = store.stages()
    total = sum(record['status']=='valid' for record in stages.values())
    number = 0
    emit(progress, f'EVALUATION {total} valid saved programs (drafts and final stages; shared stages counted once)')
    for key, record in stages.items():
        if record['status']=='valid':
            number += 1
        evkey = digest({'stage': key, 'code': record['code_hash'], 'image': config.evaluator_image, 'mock': config.mock,
                        'runtime': runtime_descriptor(config),
                        'timeout': config.eval_timeout, 'split': config.split})
        if existing.get(key, {}).get('identity') == evkey and existing[key].get('passed') is not None:
            emit(progress, f'EVAL CACHE {number}/{total} | {key} | saved outcome reused')
            continue
        if record['status'] != 'valid':
            continue
        with watch(progress, f'EVAL {number}/{total} | {key} | '+('synthetic fixture' if config.mock else 'Docker tests')):
            if config.mock:
                result = {'status': 'synthetic_pass' if record['fixture_passed'] else 'synthetic_fail',
                          'passed': record['fixture_passed'], 'synthetic': True}
            else:
                result = evaluate(config, tasks[record['task_id']], record['code'])
        result['identity'] = evkey
        result['code_hash'] = record['code_hash']
        store.evaluation(key, result)
        emit(progress, f'EVAL SAVED {number}/{total} | {key} | {result["status"]}')
    emit(progress, 'EVALUATION FINISHED')
