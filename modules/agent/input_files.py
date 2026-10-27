"""Private, immutable copies of already-preprocessed Agent input uploads.

The caller owns authentication and binds one instance to one conversation. This
module never trusts a browser-supplied path outside the configured upload roots,
and never uploads, indexes, or executes a file. Snapshots remain readable after
pending selections are removed; call ``close`` only after all senders finish.
"""
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
from threading import RLock
from typing import Mapping
from uuid import uuid4


MAX_FILE_BYTES = 50 * 1024 * 1024


class InputFileError(ValueError):
    """A selected upload or a staged snapshot cannot be used safely."""


@dataclass(frozen=True)
class InputFile:
    input_id: str
    name: str
    basename: str
    size: int
    sha256: str
    staged_path: str
    remote_path: str

    def to_dict(self):
        return asdict(self)


def _absolute_path(value):
    try:
        path = Path(os.fspath(value))
    except (TypeError, ValueError):
        raise InputFileError('附件路径无效') from None
    if not path.is_absolute() or '..' in path.parts:
        raise InputFileError('附件必须来自当前上传目录')
    return path


def _read_file(path, roots):
    """在可信目录内读取固定的普通文件句柄，保留跨平台防链接检查。"""
    from modules.agent.secure_io import read_regular_file, SecureIOError
    try:
        return read_regular_file(_absolute_path(path), roots, MAX_FILE_BYTES)
    except (OSError, SecureIOError) as error:
        if '上限' in str(error):
            raise InputFileError('单个附件不能超过 50 MiB') from None
        raise InputFileError('附件无法安全读取，可能已移除、变化或包含链接') from None


def _safe_basename(name):
    safe = re.sub(r'[^\w.\-]', '_', name, flags=re.UNICODE).strip(' ._') or 'attachment'
    stem, suffix = os.path.splitext(safe)
    if len(suffix.encode('utf-8')) > 24:
        stem, suffix = safe, ''
    available = 180 - len(suffix.encode('utf-8'))
    stem = stem.encode('utf-8')[:available].decode('utf-8', errors='ignore') or 'attachment'
    return stem + suffix


def read_snapshot_file(record, *, staging_root):
    """Return verified bytes from a trusted send snapshot, including JSON records.

    ``staging_root`` must come from the conversation's server-side stager, never
    from a client request. No remote ID or path grants local file access.
    """
    if isinstance(record, Mapping):
        try:
            record = InputFile(**record)
        except TypeError:
            raise InputFileError('附件快照格式无效') from None
    if not isinstance(record, InputFile):
        raise InputFileError('附件快照格式无效')
    if (not isinstance(record.input_id, str) or not re.fullmatch(r'[a-f0-9]{32}', record.input_id)
            or not isinstance(record.name, str) or not record.name
            or not isinstance(record.basename, str) or record.basename != _safe_basename(record.basename)
            or type(record.size) is not int or not 0 <= record.size <= MAX_FILE_BYTES
            or not isinstance(record.sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', record.sha256)):
        raise InputFileError('附件快照格式无效')
    root = _absolute_path(staging_root)
    expected = root / record.input_id / record.basename
    if (_absolute_path(record.staged_path) != expected
            or record.remote_path != f'/workspace/inputs/{record.input_id}/{record.basename}'):
        raise InputFileError('附件快照路径不匹配')
    contents = _read_file(expected, (root,))
    if len(contents) != record.size or hashlib.sha256(contents).hexdigest() != record.sha256:
        raise InputFileError('附件快照已变化，请重新选择')
    return contents


class AgentInputFiles:
    """One conversation's pending selection and retained immutable snapshots."""

    def __init__(self, upload_roots=None, *, staging_parent=None):
        if upload_roots is None:
            from gradio.utils import get_upload_folder
            upload_roots = (get_upload_folder(),)
        configured_roots = tuple(_absolute_path(root) for root in upload_roots)
        if not configured_roots:
            raise InputFileError('必须指定可信上传目录')
        # Only server-configured roots may resolve aliases such as macOS /tmp
        # and /var. Never resolve the untrusted remainder of an upload path.
        try:
            root_pairs = tuple((root, root.resolve()) for root in configured_roots)
        except (OSError, RuntimeError):
            raise InputFileError('可信上传目录无法解析') from None
        self.upload_roots = tuple(dict.fromkeys(canonical for _, canonical in root_pairs))
        prefixes = dict(root_pairs)
        prefixes.update((root, root) for root in self.upload_roots)
        self._upload_prefixes = tuple(sorted(prefixes.items(), key=lambda pair: len(pair[0].parts), reverse=True))
        self.staging_root = Path(tempfile.mkdtemp(prefix='chuanhu-agent-inputs-', dir=staging_parent)).resolve()
        self.staging_root.chmod(0o700)
        self._lock = RLock()
        self._pending = ()
        self._known = {}
        self._closed = False

    def _check_open(self):
        if self._closed:
            raise InputFileError('此附件会话已关闭')

    def _input_path(self, value):
        path = _absolute_path(value)
        for prefix, canonical in self._upload_prefixes:
            if path != prefix and path.is_relative_to(prefix):
                return canonical / path.relative_to(prefix)
        raise InputFileError('附件不在可信上传目录中')

    def _stage(self, value):
        path = self._input_path(value)
        contents = _read_file(path, self.upload_roots)
        digest = hashlib.sha256(contents).hexdigest()
        key = (str(path), digest)
        if key in self._known:
            record = self._known[key]
            read_snapshot_file(record, staging_root=self.staging_root)
            return record
        input_id = uuid4().hex
        basename = _safe_basename(path.name)
        directory = self.staging_root / input_id
        directory.mkdir(mode=0o700)
        destination = directory / basename
        try:
            with destination.open('xb') as target:
                target.write(contents)
            destination.chmod(0o400)
        except BaseException:
            shutil.rmtree(directory)
            raise
        record = InputFile(input_id, path.name, basename, len(contents), digest, str(destination),
                           f'/workspace/inputs/{input_id}/{basename}')
        self._known[key] = record
        return record

    def set_pending(self, paths):
        """Replace the selection atomically; repeated upload events reuse IDs."""
        with self._lock:
            self._check_open()
            if paths is None:
                paths = ()
            if isinstance(paths, (str, bytes, os.PathLike)):
                raise InputFileError('请传入附件路径列表')
            staged = {}
            for path in paths:
                record = self._stage(path)
                staged[record.input_id] = record
            self._pending = tuple(staged.values())
            return self._pending

    def add(self, paths):
        """Add uploads without changing the earlier pending selection on error."""
        with self._lock:
            previous = self._pending
            added = self.set_pending(paths)
            self._pending = tuple({record.input_id: record for record in (*previous, *added)}.values())
            return self._pending

    def snapshot(self):
        with self._lock:
            self._check_open()
            return self._pending

    def remove(self, input_id):
        with self._lock:
            self._check_open()
            self._pending = tuple(record for record in self._pending if record.input_id != input_id)
            return self._pending

    def clear(self):
        return self.set_pending(())

    def mark_submitted(self, input_ids):
        """Retain snapshots, but give later selections fresh sandbox paths.

        A running Agent can modify an installed file. The listing API supplies
        only its size, so a previous upload receipt cannot verify its contents
        after a turn has used it. Unsent preparation retries still reuse IDs.
        """
        with self._lock:
            self._check_open()
            used = set(input_ids)
            self._known = {key: record for key, record in self._known.items() if record.input_id not in used}

    def close(self):
        """Delete retained copies only when no in-flight snapshot still uses them."""
        with self._lock:
            if not self._closed:
                def remove_readonly(function, value, failure):
                    # Windows 的只读副本需要先恢复写位；绝不修改目录外或链接目标。
                    path = Path(value)
                    if path.is_symlink() or not (path == self.staging_root or self.staging_root in path.resolve().parents):
                        raise failure[1]
                    path.chmod(0o700)
                    function(value)
                shutil.rmtree(self.staging_root, onerror=remove_readonly)
                self._pending = ()
                self._known.clear()
                self._closed = True
