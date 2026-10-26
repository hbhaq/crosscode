"""Transactional checkpoints and persistent conservative spending reservations."""
import json
import sqlite3
import time
import math
from contextlib import contextmanager
from pathlib import Path

class BudgetStop(Exception):
    pass

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS stages(key TEXT PRIMARY KEY, identity TEXT, record TEXT);
            CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, stage TEXT, task TEXT,
                attempt INTEGER, allowance REAL, cost REAL, state TEXT, record TEXT, started REAL);
            CREATE TABLE IF NOT EXISTS evaluations(key TEXT PRIMARY KEY, record TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def stages(self):
        with self.connect() as db:
            return {k: json.loads(r) for k, r in db.execute('SELECT key,record FROM stages')}

    def attempts(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM attempts ORDER BY id')]

    def ledger(self):
        rows = self.attempts()
        synthetic = {r['id'] for r in rows if (json.loads(r['record'] or '{}').get('raw') or {}).get('synthetic')}
        return {'actual_usd': sum(r['cost'] or 0 for r in rows),
                'reserved_usd': sum(r['allowance'] for r in rows if r['state'] in ('reserved', 'unresolved')),
                'recorded_attempts':len(rows), 'synthetic_attempts':len(synthetic),
                'billable_attempts':sum(r['id'] not in synthetic and (bool(r['cost']) or r['state'] in ('reserved','unresolved')) for r in rows),
                'unresolved_attempts': sum(r['state'] in ('reserved', 'unresolved') for r in rows)}

    def reserve(self, stage, task, attempt, allowance, max_total, max_task):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used, task_used = db.execute('''SELECT COALESCE(SUM(CASE WHEN state IN ('reserved','unresolved') THEN allowance ELSE COALESCE(cost,0) END),0),
              COALESCE(SUM(CASE WHEN task=? THEN CASE WHEN state IN ('reserved','unresolved') THEN allowance ELSE COALESCE(cost,0) END ELSE 0 END),0) FROM attempts''', (task,)).fetchone()
            if used + allowance > max_total + 1e-12 or task_used + allowance > max_task + 1e-12:
                raise BudgetStop('Cumulative spending plus reserved allowances would exceed budget')
            if db.execute('SELECT 1 FROM stages WHERE key=?', (stage,)).fetchone():
                raise BudgetStop('Stage already completed by another worker; purchased work will not be duplicated')
            if db.execute("SELECT 1 FROM attempts WHERE stage=? AND state IN ('reserved','unresolved')", (stage,)).fetchone():
                raise BudgetStop('This stage has unresolved usage; reconcile with vendor billing before retrying')
            return db.execute("INSERT INTO attempts(stage,task,attempt,allowance,state,started) VALUES(?,?,?,?, 'reserved',?)",
                              (stage, task, attempt, allowance, time.time())).lastrowid

    def finish(self, attempt_id, record, cost=None, stage=None, identity=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE attempts SET cost=?,state=?,record=? WHERE id=?',
                       (cost, 'settled' if cost is not None else 'unresolved', json.dumps(record), attempt_id))
            if stage:
                db.execute('INSERT OR REPLACE INTO stages VALUES(?,?,?)', (stage, identity, json.dumps(record)))

    def evaluations(self):
        with self.connect() as db:
            return {k: json.loads(r) for k, r in db.execute('SELECT key,record FROM evaluations')}

    def evaluation(self, key, record):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO evaluations VALUES(?,?)', (key, json.dumps(record)))

    def reconcile(self, attempt_id, cost, evidence):
        if not math.isfinite(cost) or cost < 0 or not evidence.strip():
            raise ValueError('A nonnegative verified cost and billing evidence are required')
        with self.connect() as db:
            row = db.execute('SELECT record FROM attempts WHERE id=?', (attempt_id,)).fetchone()
            if not row:
                raise ValueError('Unknown attempt')
            record = json.loads(row[0] or '{}')
            record['reconciliation'] = {'cost': cost, 'evidence': evidence, 'time': time.time()}
            db.execute("UPDATE attempts SET cost=?,state='settled',record=? WHERE id=?", (cost, json.dumps(record), attempt_id))
