"""Presentation-only progress. Never changes settings, reservations or requests."""
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
import re
import sys
import threading
import time


class Progress:
    def __init__(self, interval=15.0, console=True, log_path=None, stream=None):
        self.interval = interval
        self.console = console
        self.log_path = Path(log_path) if log_path else None
        self.stream = stream if stream is not None else sys.stderr
        self.lock = threading.Lock()

    def event(self, message):
        # Print safe, single-line events, never response text, prompts or headers.
        message = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', str(message))
        line = '['+datetime.now().astimezone().isoformat(timespec='seconds')+'] '+message
        with self.lock:
            if self.console:
                try:
                    print(line, file=self.stream, flush=True)
                except (OSError, ValueError):
                    pass  # A closed console must not turn a purchased call into a failure.
            if self.log_path:
                try:
                    with self.log_path.open('a', encoding='utf-8') as file:
                        file.write(line+'\n')
                except (OSError, ValueError):
                    pass

    @contextmanager
    def wait(self, label):
        self.event('START '+label)
        stop = threading.Event()
        started = time.monotonic()
        def heartbeat():
            while not stop.wait(self.interval):
                self.event(f'WAIT {label} | elapsed {time.monotonic()-started:.0f}s (still waiting, no retry)')
        thread = threading.Thread(target=heartbeat, name='crosscode-progress', daemon=True)
        running = False
        try:
            try:
                thread.start()
                running = True
            except RuntimeError:
                pass
            yield
        finally:
            stop.set()
            if running:
                thread.join(timeout=1)


def emit(progress, message):
    if progress is not None:
        progress.event(message)


def watch(progress, message):
    return progress.wait(message) if progress is not None else nullcontext()


def generation_totals(store, total):
    # Aggregates only: avoid reading full response bodies just to show progress.
    try:
        with store.connect() as db:
            saved = db.execute('SELECT COUNT(*) FROM stages').fetchone()[0]
            spent, reserved = db.execute("""SELECT COALESCE(SUM(cost),0),
                COALESCE(SUM(CASE WHEN state IN ('reserved','unresolved') THEN allowance ELSE 0 END),0)
                FROM attempts""").fetchone()
        return f'saved stages {saved}/{total}; remaining {max(0,total-saved)} | spent ${spent:.6f}; reserved ${reserved:.6f}'
    except Exception:
        return 'progress totals unavailable; checkpoint accounting unchanged'
