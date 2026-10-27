"""Server-private Agent bindings. Exported chat JSON never confers authority."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from contextlib import contextmanager
from weakref import WeakValueDictionary

_history_locks = WeakValueDictionary()
_history_locks_lock = RLock()

def local_history_key(path):
    return Path(history_key(path)).name


def owner_identity(username):
    # Anonymous deployments already share one history boundary. Do not invent a
    # browser-only identity that disappears on refresh or a server restart.
    return hashlib.sha256(('user:' + username if username else 'deployment:anonymous').encode()).hexdigest()


def history_key(path):
    return str(path).removesuffix('.json')


class BindingStore:
    def __init__(self, root):
        folder = Path(root) / 'agent_data'
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = folder / 'bindings.sqlite3'
        if self.path.is_symlink():
            raise ValueError('会话绑定文件不能是符号链接')
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS bindings (owner TEXT NOT NULL, history TEXT NOT NULL, record TEXT NOT NULL, PRIMARY KEY(owner, history))')
            db.execute('CREATE TABLE IF NOT EXISTS file_jobs (id TEXT PRIMARY KEY, sequence INTEGER UNIQUE NOT NULL, owner TEXT NOT NULL, conversation TEXT NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS artifact_receipts (owner TEXT NOT NULL, conversation TEXT NOT NULL, session TEXT NOT NULL, artifact TEXT NOT NULL, sequence INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(owner, conversation, session, artifact))')
            db.execute('CREATE TABLE IF NOT EXISTS deleted_histories (owner TEXT NOT NULL, history TEXT NOT NULL, conversation TEXT NOT NULL, record TEXT NOT NULL, PRIMARY KEY(owner, history, conversation))')
        os.chmod(self.path, 0o600)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, owner, path):
        with self._connect() as db:
            row = db.execute('SELECT record FROM bindings WHERE owner=? AND history=?', (owner, history_key(path))).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, owner, path, record):
        # Caller supplies no credentials. Reject accidental secret fields rather
        # than exporting or silently stripping a connection authority record.
        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.lower() in {'api_key', 'authorization', 'password', 'access_token', 'credential_values'}:
                        raise ValueError('不能将凭据保存在会话绑定中')
                    check(item)
            elif isinstance(value, list):
                for item in value: check(item)
        check(record)
        with self._connect() as db:
            db.execute('INSERT OR REPLACE INTO bindings SELECT ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM deleted_histories WHERE owner=? AND history=? AND conversation=?)',
                       (owner, history_key(path), json.dumps(record, ensure_ascii=False), owner, local_history_key(path), record.get('conversation_id', '')))

    def settle_task(self, owner, path, conversation, state):
        """Phase-only completion cannot wait on a background JSON file write."""
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT record FROM bindings WHERE owner=? AND history=?', (owner, history_key(path))).fetchone()
            if not row: return False
            record = json.loads(row[0])
            saved = record.get('state', {})
            if record.get('conversation_id') != conversation or any(saved.get(key) != state.get(key)
                    for key in ('generation', 'session_id', 'turn_id', 'outcome')): return False
            record['local_phase'] = 'settled'
            db.execute('UPDATE bindings SET record=? WHERE owner=? AND history=?',
                       (json.dumps(record, ensure_ascii=False), owner, history_key(path)))
            return True

    def copy_binding(self, owner, before, after):
        """Retain source authority until the history file migration completes."""
        with self._connect() as db:
            db.execute('INSERT INTO bindings SELECT owner, ?, record FROM bindings WHERE owner=? AND history=?',
                       (history_key(after), owner, history_key(before)))

    def rename(self, owner, before, after):
        with self._connect() as db:
            db.execute('UPDATE bindings SET history=? WHERE owner=? AND history=?', (history_key(after), owner, history_key(before)))

    def forget(self, owner, path):
        with self._connect() as db:
            db.execute('DELETE FROM bindings WHERE owner=? AND history=?', (owner, history_key(path)))

    @contextmanager
    def history_guard(self, owner, path):
        # Serialize local file writes with deletion in this server process.
        key = (str(self.path.resolve()), owner, local_history_key(path))
        with _history_locks_lock:
            lock = _history_locks.setdefault(key, RLock())
        with lock:
            yield

    def is_history_deleted(self, owner, path, conversation):
        with self._connect() as db:
            return db.execute('SELECT 1 FROM deleted_histories WHERE owner=? AND history=? AND conversation=?',
                              (owner, local_history_key(path), conversation)).fetchone() is not None

    def history_bindings(self, owner, path):
        with self._connect() as db:
            rows = db.execute('SELECT history, record FROM bindings WHERE owner=?', (owner,)).fetchall()
        return [(key, json.loads(record)) for key, record in rows if local_history_key(key) == local_history_key(path)]

    def delete_local_history(self, owner, path, conversations):
        # The receipt is a write barrier, not authority to resume/cancel a run.
        # Different new conversations may legitimately reuse the filename.
        with self._connect() as db:
            for conversation, record in conversations.items():
                db.execute('INSERT OR IGNORE INTO deleted_histories VALUES (?, ?, ?, ?)',
                           (owner, local_history_key(path), conversation, json.dumps(record, ensure_ascii=False)))
            jobs = db.execute('SELECT id, conversation, record FROM file_jobs WHERE owner=?', (owner,)).fetchall()
            for identifier, conversation, raw in jobs:
                job = json.loads(raw)
                if local_history_key(job['history']) == local_history_key(path) and conversation in conversations:
                    job['status'] = 'deleted'
                    db.execute('UPDATE file_jobs SET record=? WHERE id=?', (json.dumps(job, ensure_ascii=False), identifier))
                    db.execute('DELETE FROM artifact_receipts WHERE owner=? AND conversation=?', (owner, conversation))
            rows = db.execute('SELECT history FROM bindings WHERE owner=?', (owner,)).fetchall()
            for (key,) in rows:
                if local_history_key(key) == local_history_key(path):
                    db.execute('DELETE FROM bindings WHERE owner=? AND history=?', (owner, key))

    def deletion_receipt(self, owner, path, conversation):
        with self._connect() as db:
            row = db.execute('SELECT record FROM deleted_histories WHERE owner=? AND history=? AND conversation=?',
                             (owner, local_history_key(path), conversation)).fetchone()
        return json.loads(row[0]) if row else None
