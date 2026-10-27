"""Bounded local completion timings. Never collect provider IDs or user data.

monotonic timestamps are comparable across the worker and parent on one host.
No timers, sleeps, network calls, or new logging handlers are added.
Existing local logging runs on a bounded, best-effort diagnostic queue.
"""
import json
import logging
import math
import re
import time
from queue import Queue, Full
from threading import Thread
from uuid import uuid4

STAGES = frozenset({'public_segment_done', 'root_terminal', 'gate_checked',
    'reconcile_start', 'reconcile_end', 'result_received', 'persistence_start',
    'persistence_end', 'task_unlocked', 'ui_final_frame'})
REASONS = frozenset({'root_not_started', 'terminal_unverified', 'stream_gap',
    'snapshot_overlap', 'incomplete_coverage', 'missing_output', 'unfinished_items',
    'unsettled_items', 'output_positions'})


def new_timing():
    return {'trace': uuid4().hex, 'stages': {}, 'gate_reasons': []}


def safe_timing(value):
    if not isinstance(value, dict) or not isinstance(value.get('trace'), str) or not re.fullmatch(r'[a-f0-9]{32}', value['trace']):
        return None
    stages = value.get('stages')
    if not isinstance(stages, dict): return None
    reasons = value.get('gate_reasons')
    if not isinstance(reasons, (list, tuple)): return None
    return {'trace': value['trace'], 'stages': {key: stamp for key, stamp in stages.items()
            if key in STAGES and type(stamp) in (int, float) and 0 <= stamp <= 1e15 and math.isfinite(stamp)},
            'gate_reasons': sorted({reason for reason in reasons if type(reason) is str and reason in REASONS})}


def mark(timing, stage):
    if timing is not None and stage in STAGES:
        timing['stages'][stage] = time.monotonic()


_reports = Queue(maxsize=64)


def _write_reports():
    while True:
        safe = _reports.get()
        try:
            logging.getLogger(__name__).info('agent_completion_timing %s', json.dumps(safe, sort_keys=True))
        except Exception:
            pass
        finally:
            _reports.task_done()


# Logger I/O never runs on the persistence, release, or UI projection thread.
Thread(target=_write_reports, name='agent-completion-timing', daemon=True).start()


def report(timing):
    """Best-effort bounded local diagnostic; congestion drops rather than waits."""
    try:
        safe = safe_timing(timing)
        if safe is not None: _reports.put_nowait(safe)
    except (Full, TypeError, ValueError):
        pass
