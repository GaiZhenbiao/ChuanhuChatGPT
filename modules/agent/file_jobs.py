"""Bounded, durable file work; no turn admission slot and no stale model saves.

Jobs retain provider session/turn identity and their original conversation. Only
file fields are merged under the history write barrier. Credentials are held by
a live executor and never enter the SQLite journal or exported history.
"""
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
from queue import Queue, Full
import tempfile
from threading import RLock, Thread
from uuid import uuid4

from . import transcript
from .store import history_key


def get_job(store, identifier):
    with store._connect() as db:
        row = db.execute('SELECT record FROM file_jobs WHERE id=?', (identifier,)).fetchone()
    return json.loads(row[0]) if row else None


def jobs_for(store, owner, conversation):
    with store._connect() as db:
        rows = db.execute('SELECT record FROM file_jobs WHERE owner=? AND conversation=? ORDER BY sequence', (owner, conversation)).fetchall()
    return [json.loads(row[0]) for row in rows]


def records_for(store, owner, conversation, session):
    with store._connect() as db:
        rows = db.execute('SELECT record FROM artifact_receipts WHERE owner=? AND conversation=? AND session=? ORDER BY sequence, artifact', (owner, conversation, session)).fetchall()
    return [json.loads(row[0]) for row in rows]


def pending(store, owner, conversation):
    return any(job['status'] in ('pending', 'running') for job in jobs_for(store, owner, conversation))


def create_job(store, *, owner, conversation, history, session, turn, generation, connection_ref, artifact_ids=None, cache_owner=None, log_updates=True):
    # Caller owns history_guard; deletion is checked again for every receipt.
    if store.is_history_deleted(owner, history, conversation): return None
    if not isinstance(session, str) or not session or not isinstance(turn, str) or not turn: return None
    ids = sorted(set(artifact_ids)) if artifact_ids is not None else None
    for job in jobs_for(store, owner, conversation):
        if job['session_id'] == session and job['turn_id'] == turn and job['artifact_ids'] == ids:
            if job['status'] in ('pending', 'running') or ids is None and job['status'] == 'done': return job
    record = dict(id=uuid4().hex, owner=owner, conversation_id=conversation, history=history_key(history),
        session_id=session, turn_id=turn, generation=generation, connection_ref=deepcopy(connection_ref),
        artifact_ids=ids, status='pending', error=None, cache_owner=cache_owner, log_updates=bool(log_updates))
    with store._connect() as db:
        db.execute('BEGIN IMMEDIATE')
        record['sequence'] = db.execute('SELECT COALESCE(MAX(sequence), 0)+1 FROM file_jobs').fetchone()[0]
        db.execute('INSERT INTO file_jobs VALUES (?, ?, ?, ?, ?)', (record['id'], record['sequence'], owner, conversation, json.dumps(record, ensure_ascii=False)))
    return record


def move_jobs(store, owner, conversation, before, after):
    # Rename holds both history guards; callbacks re-read this alias after locking.
    with store._connect() as db:
        for job in jobs_for(store, owner, conversation):
            if job['history'] == history_key(before):
                job['history'] = history_key(after)
                db.execute('UPDATE file_jobs SET record=? WHERE id=?', (json.dumps(job, ensure_ascii=False), job['id']))


def _merge_snapshot(previous, records, conversation, session):
    incoming = transcript.normalize([], scope_id=conversation, artifacts=records, session_id=session,
                                    capture={'items': 'not_collected', 'artifacts': 'partial'})
    return transcript.merge(previous, incoming) if previous else incoming


def overlay_model(model):
    records = records_for(model._store(), model._owner, model._conversation_id, model._state.get('session_id'))
    if records:
        model._merge_artifacts(records)
        model._transcript = _merge_snapshot(model._transcript, model._artifacts, model._conversation_id, model._state.get('session_id'))


def _atomic_document(path, document):
    # File metadata never changes the chat's recency or text compatibility rows.
    stat = path.stat()
    descriptor, temporary = tempfile.mkstemp(prefix='.agent-files-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            validated = json.loads(transcript.serialize(document))
            for key in ('history', 'chatbot'):
                if key in document: validated[key] = document[key]
            stream.write(json.dumps(validated, ensure_ascii=False, allow_nan=False, indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        os.utime(temporary, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _guarded(store, identifier, apply):
    # A callback captured before rename must follow the durable alias, rather
    # than resurrect the old filename. No model lock is taken under this guard.
    while True:
        job = get_job(store, identifier)
        if job is None: return False
        with store.history_guard(job['owner'], job['history']):
            current = get_job(store, identifier)
            if current is None: return False
            if current['history'] != job['history']: continue
            if store.is_history_deleted(current['owner'], current['history'], current['conversation_id']):
                current.update(status='deleted')
                _put_job(store, current)
                return False
            return apply(current)


def _put_job(store, job):
    with store._connect() as db:
        db.execute('UPDATE file_jobs SET record=? WHERE id=?', (json.dumps(job, ensure_ascii=False), job['id']))


def _validate_record(store, job, record):
    if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not record['id']: return None
    if job['artifact_ids'] is not None and record['id'] not in job['artifact_ids']: return None
    allowed = {'id', 'session_id', 'turn_id', 'name', 'remote_path', 'type', 'size', 'status', 'path', 'error', 'message_item_id', 'created_at'}
    value = {key:deepcopy(value) for key, value in record.items() if key in allowed}
    value.setdefault('name', 'artifact')
    if record.get('session_id') == job['session_id'] and record.get('turn_id') == job['turn_id']:
        if value.get('status') == 'ready':
            path = Path(value.get('path', ''))
            root = Path(tempfile.gettempdir()).resolve()
            cache = store.path.parent / 'artifacts' / str(job.get('cache_owner') or '')
            trusted = (root in path.resolve().parents and any(parent.name.startswith('chuanhu-agent-artifacts-') for parent in path.parents)) or bool(job.get('cache_owner') and cache.resolve() in path.resolve().parents)
            if path.is_symlink() or not path.is_file() or not trusted or (type(value.get('size')) is int and value['size'] != path.stat().st_size):
                value.update(status='failed', error='文件缓存校验失败，请重新获取')
                value.pop('path', None)
        return value
    if record.get('session_id') == job['session_id'] and isinstance(record.get('turn_id'), str) and record['turn_id']:
        return None  # Session-level list can already contain a later turn.
    # Preserve metadata, but unproven/conflicting ownership cannot get a link
    # or inherit the job's captured turn. The next explicit retry may resolve it.
    value.update(session_id=None, turn_id=None, status='failed', error='文件归属尚未确认，请重新获取')
    value.pop('path', None)
    value.pop('message_item_id', None)
    return value


def apply_receipts(store, identifier, records, history_root):
    def apply(job):
        binding = store.get(job['owner'], job['history'])
        if (not binding or binding.get('conversation_id') != job['conversation_id']
                or binding.get('state', {}).get('session_id') != job['session_id']): return False
        with store._connect() as db:
            for value in records:
                record = _validate_record(store, job, value)
                if record is None: continue
                row = db.execute('SELECT sequence, record FROM artifact_receipts WHERE owner=? AND conversation=? AND session=? AND artifact=?',
                    (job['owner'], job['conversation_id'], job['session_id'], record['id'])).fetchone()
                if row:
                    old = json.loads(row[1])
                    if row[0] > job['sequence']: continue
                    if old.get('turn_id') and record.get('turn_id') and old['turn_id'] != record['turn_id']: continue
                    if old.get('status') == 'ready' and record.get('status') == 'preparing': continue
                db.execute('INSERT OR REPLACE INTO artifact_receipts VALUES (?, ?, ?, ?, ?, ?)',
                    (job['owner'], job['conversation_id'], job['session_id'], record['id'], job['sequence'], json.dumps(record, ensure_ascii=False)))
        merged = {record['id']: record for record in binding.get('artifacts', [])}
        merged.update((record['id'], record) for record in records_for(store, job['owner'], job['conversation_id'], job['session_id']))
        binding['artifacts'] = list(merged.values())
        binding['transcript'] = _merge_snapshot(binding.get('transcript'), binding['artifacts'], job['conversation_id'], job['session_id'])
        path = Path(history_root) / (job['history'] + '.json')
        if path.is_symlink() or path.resolve().parent != Path(history_root).resolve() or not path.is_file(): return False
        document = json.loads(path.read_text(encoding='utf-8'))
        snapshot = document.get('agent_transcript')
        if not snapshot or snapshot.get('scope_id') != job['conversation_id']: return False
        document['agent_transcript'] = _merge_snapshot(snapshot, binding['artifacts'], job['conversation_id'], job['session_id'])
        _atomic_document(path, document)
        # Task settlement updates only local_phase without this JSON guard.
        # Read the latest private record in the short SQLite transaction and
        # patch file fields only, preserving that phase and every run field.
        with store._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT record FROM bindings WHERE owner=? AND history=?', (job['owner'],job['history'])).fetchone()
            if not row: return False
            latest = json.loads(row[0])
            if latest.get('conversation_id') != job['conversation_id'] or latest.get('state', {}).get('session_id') != job['session_id']: return False
            latest['artifacts'] = binding['artifacts']
            latest['transcript'] = _merge_snapshot(latest.get('transcript'), binding['artifacts'], job['conversation_id'], job['session_id'])
            db.execute('UPDATE bindings SET record=? WHERE owner=? AND history=?', (json.dumps(latest,ensure_ascii=False),job['owner'],job['history']))
        return True
    return _guarded(store, identifier, apply)


class FileJobRegistry:
    def __init__(self, workers=2, capacity=32):
        self.queue = Queue(maxsize=capacity)
        self.workers, self.lock, self.active, self.started = workers, RLock(), set(), False

    def submit(self, store, job, runner, history_root):
        if job is None or job['status'] not in ('pending', 'running'): return False
        key = (str(store.path.resolve()), job['id'])
        with self.lock:
            if key in self.active: return False
            if not self.started:
                self.started = True
                for _ in range(self.workers): Thread(target=self._watch, name='agent-file-job', daemon=True).start()
            self.active.add(key)
            try: self.queue.put_nowait((store, job['id'], runner, history_root, key))
            except Full:
                self.active.remove(key)
                return False  # Still durable pending; resume/poll can admit it later.
            return True

    def _watch(self):
        while True:
            store, identifier, runner, history_root, key = self.queue.get()
            try: self._run(store, identifier, runner, history_root)
            except Exception:
                logging.exception('Agent 文件回填失败，任务收据保留供重试')
            finally:
                with self.lock: self.active.discard(key)
                self.queue.task_done()

    def _run(self, store, identifier, runner, history_root):
        def started(job):
            if job['status'] not in ('pending', 'running'): return False
            job.update(status='running', error=None)
            _put_job(store, job)
            return job
        job = _guarded(store, identifier, started)
        if not job: return
        def cancelled():
            current = get_job(store, identifier)
            return not current or store.is_history_deleted(current['owner'], current['history'], current['conversation_id'])
        error = None
        try:
            binding = store.get(job['owner'], job['history']) or {}
            existing = {record['id']:record for record in binding.get('artifacts', [])}
            existing.update((record['id'],record) for record in records_for(store, job['owner'], job['conversation_id'], job['session_id']))
            ready = [record['id'] for record in existing.values()
                     if record.get('session_id') == job['session_id'] and record.get('status') == 'ready' and Path(record.get('path', '')).is_file()]
            command = dict(action='download', session_id=job['session_id'], turn_id=job['turn_id'],
                artifact_ids=job['artifact_ids'], skip_artifact_ids=ready if job['artifact_ids'] is None else [], _observe_cancel=cancelled)
            for message in runner(command):
                if cancelled(): return
                if message.get('type') == 'error': error = message.get('message') or '文件获取失败，可重试'
                records = message.get('artifacts', message.get('artifact_metadata'))
                if isinstance(records, list):
                    before = {record['id']:record for record in (store.get(job['owner'], get_job(store, identifier)['history']) or {}).get('artifacts', [])}
                    if apply_receipts(store, identifier, records, history_root) and job.get('log_updates', True) and callable(getattr(runner, 'log_artifacts', None)):
                        updated = records_for(store, job['owner'], job['conversation_id'], job['session_id'])
                        changed = [record for record in updated if record != before.get(record['id'])]
                        runner.log_artifacts(job, changed)
        except Exception as caught:
            error = '文件获取未完成，请重试'
            logging.exception('Agent 文件任务失败，保留原会话及文件收据')
        current_job = get_job(store, identifier)
        existing = {record['id']:record for record in (store.get(job['owner'], current_job['history']) or {}).get('artifacts', [])}
        existing.update((record['id'],record) for record in records_for(store, job['owner'], job['conversation_id'], job['session_id']))
        unfinished = [dict(record, status='failed', error=error or '文件获取未完成，请重试')
            for record in existing.values()
            if (record.get('status') == 'preparing' or error and job['artifact_ids'] is not None and record.get('status') != 'ready') and record.get('turn_id') == job['turn_id']
            and (job['artifact_ids'] is None or record['id'] in job['artifact_ids'])]
        if unfinished:
            try:
                apply_receipts(store, identifier, unfinished, history_root)
            except Exception:
                error = '文件记录保存未完成，请重试'
                logging.exception('Agent 文件失败状态未能写入历史，仍保留可重试任务收据')
        def finish(current):
            current.update(status='failed' if error else 'done', error=error)
            _put_job(store, current)
            return True
        _guarded(store, identifier, finish)


FILE_JOBS = FileJobRegistry()
