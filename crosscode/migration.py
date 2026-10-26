"""Explicit evaluation-only continuation; never mutates the source run or calls models."""
import copy
import dataclasses
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time

from .core import Config, digest, prompt, read, save
from .evaluator import image_id, runtime_descriptor
from .runner import cache_identity
from .store import Store


def fork_evaluator(source, target, evaluator_image, verified_preflight=None,evaluator_egress_proxy_image=None):
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.parent != source.parent or not re.fullmatch(r'[A-Za-z0-9_-]+',target.name):
        raise ValueError('Destination must be a named run in the same runs directory')
    if target == source or target.exists():
        raise ValueError('Destination must be a new run; existing data will not be overwritten')
    if not re.fullmatch(r'(?:[^\s]+@)?sha256:[0-9a-f]{64}',evaluator_image):
        raise ValueError('An immutable evaluator image ID/digest is required')
    original_config = (source/'config.json').read_bytes()
    original_manifest = (source/'manifest.json').read_bytes()
    old_config = Config(**json.loads(original_config))
    old_manifest = json.loads(original_manifest)
    if old_manifest['config_hash'] != old_config.identity():
        raise ValueError('Source settings/prompts/source lock are incompatible; generation reuse is blocked')
    proxy=old_config.evaluator_egress_proxy_image if evaluator_egress_proxy_image is None else evaluator_egress_proxy_image
    if old_config.evaluator_image == evaluator_image and proxy == old_config.evaluator_egress_proxy_image:
        raise ValueError('The evaluator image/egress settings did not change')
    resolved_image = image_id(evaluator_image)
    if proxy:
        image_id(proxy)
    new_config = dataclasses.replace(old_config,evaluator_image=evaluator_image,evaluator_egress_proxy_image=proxy)
    manifest = copy.deepcopy(old_manifest)
    manifest['config_hash'] = new_config.identity()
    tasks = {t['task_id']:t for t in manifest['tasks']}
    staging = Path(tempfile.mkdtemp(prefix='.'+target.name+'-prepare-',dir=source.parent)).resolve()
    try:
        src = sqlite3.connect((source/'checkpoint.sqlite').as_uri()+'?mode=ro',uri=True)
        dst = sqlite3.connect(staging/'checkpoint.sqlite')
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        store = Store(staging/'checkpoint.sqlite')
        stages = store.stages()
        new_records = {}
        for key,record in stages.items():
            job = {field:record[field] for field in ['key','task_id','rep','arm','role','model','parent']}
            task = tasks[record['task_id']]
            parent = stages.get(record['parent']) if record['parent'] else None
            if record['parent'] and not parent:
                raise ValueError('A saved reviewer has no matching source draft')
            rendered = prompt(task,old_config.split,parent['code'] if parent else None)
            expected = cache_identity(old_config,job,task,rendered,parent)
            if record['prompt'] != rendered or record['identity'] != expected:
                raise ValueError('Saved generation input/cache mismatch; reuse is blocked for '+key)
            reused = copy.deepcopy(record)
            reused['reuse_provenance'] = {'source_run':source.name,'source_cache_identity':record['identity'],
                'source_configuration':old_config.identity(),'destination_configuration':new_config.identity(),
                'reason':'Only evaluator image/egress settings changed; exact prompt, task, parent draft and generation settings validated',
                'previous_reuse':record.get('reuse_provenance')}
            # Keep the original generation config_hash, request, response, usage and attempts.
            # Only the derived run's cache binding is new, with the original binding retained above.
            reused['identity'] = cache_identity(new_config,job,task,rendered,parent)
            new_records[key] = reused
        old_evaluations = len(store.evaluations())
        ledger = store.ledger()
        with store.connect() as db:
            for key,record in new_records.items():
                db.execute('UPDATE stages SET identity=?,record=? WHERE key=?',
                           (record['identity'],json.dumps(record),key))
            db.execute('DELETE FROM evaluations')  # Destination only; all programs must be rescored.
        migration = {'kind':'evaluator-only continuation','source_run':source.name,
            'source_configuration':old_config.identity(),'destination_configuration':new_config.identity(),
            'source_manifest_sha256':hashlib.sha256(original_manifest).hexdigest(),
            'old_image':old_config.evaluator_image,'new_image':evaluator_image,'resolved_image':resolved_image,
            'old_egress_proxy_image':old_config.evaluator_egress_proxy_image,'new_egress_proxy_image':proxy,
            'created_at':datetime.now(timezone.utc).isoformat(),'copied_stages':len(stages),
            'copied_attempts':len(store.attempts()),'prior_evaluations_not_reused':old_evaluations,
            'ledger_inherited':ledger,
            'accounting_note':'Prior purchases and reservations are inherited, not new calls. Do not sum spending across source and continuation runs.',
            'generation_settings_changed':False,'inference_calls_during_migration':0}
        manifest['migration'] = migration
        manifest.setdefault('history',[]).append({'kind':'evaluator-only continuation','source_run':source.name,
                                                'previous_manifest_hash':digest(old_manifest)})
        save(staging/'config.json',dataclasses.asdict(new_config))
        save(staging/'manifest.json',manifest)
        save(staging/'migration.json',migration)
        for filename in ['config.json','manifest.json','preflight.json']:
            if (source/filename).exists():
                dest = staging/'origin'/filename
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source/filename,dest)
        if (source/'controls.json').exists():
            shutil.copyfile(source/'controls.json',staging/'controls.json')
        if verified_preflight is not None:
            evidence = read(verified_preflight)
            runtime = runtime_descriptor(new_config)
            expected = digest({'image':resolved_image,'tasks':manifest['tasks'],'split':new_config.split,
                               'timeout':new_config.eval_timeout,'runtime':runtime})
            if evidence.get('key') != expected or not evidence.get('passed') or set(evidence.get('results',{})) != set(tasks) or not all(r.get('passed') is True for r in evidence['results'].values()):
                raise ValueError('Preflight evidence does not match the destination image and exact selected tasks')
            save(staging/'preflight.json',evidence)
        if (source/'config.json').read_bytes()!=original_config or (source/'manifest.json').read_bytes()!=original_manifest:
            raise ValueError('Source configuration/selection changed during migration; try again after it is stable')
        if target.exists():
            raise ValueError('Destination appeared during preparation; it will not be overwritten')
        # Windows antivirus/indexers can briefly hold a newly closed SQLite file.
        # Retry only the final filesystem rename; never repeat generation/copying.
        for attempt in range(4):
            try:
                staging.rename(target)
                break
            except PermissionError:
                if attempt == 3 or target.exists():
                    raise
                time.sleep(.1 * 2**attempt)
        return migration
    finally:
        # This is our own newly created staging directory, checked to stay in the runs root.
        if staging.exists():
            if staging.parent != source.parent or not staging.name.startswith('.'+target.name+'-prepare-'):
                raise ValueError('Unexpected staging path; refusing cleanup')
            shutil.rmtree(staging)
