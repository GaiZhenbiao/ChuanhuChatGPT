"""按服务端所有者与会话隔离的下载缓存，以及可恢复的临时文件生命周期。

调用方只能传入服务端生成的 cache_root，不能使用浏览器提交的本地路径。
仅清理由本模块索引记录、且其排他锁已释放的临时文件；不扫描删除目录树。
"""
from contextlib import AbstractContextManager, contextmanager
from copy import deepcopy
import ctypes
import hashlib
import os
from pathlib import Path
import re

from . import secure_io
from .secure_io import SecureDirectory, SecureIOError
from uuid import uuid4


_INDEX = '.agent-artifact-cache.json'
_INDEX_LOCK = '.agent-artifact-cache.lock'
_HASH = re.compile(r'[a-f0-9]{64}')
_TEMP = re.compile(r'\.agent-download-([a-f0-9]{64})-([a-f0-9]{32})\.part')


class ArtifactCacheError(ValueError):
    """缓存不完整或受到修改，不能把本地文件当成已验证下载。"""


class ArtifactBusy(BlockingIOError):
    """其他进程正在下载或更新索引；本次不等待，下次观察时再试。"""


def _digest(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ArtifactCacheError('文件缓存标识无效')
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _filename(value):
    if not isinstance(value, str) or not value:
        raise ArtifactCacheError('文件缓存名称无效')
    name = re.sub(r'[^\w.\-]', '_', value).strip(' ._') or 'artifact'
    stem, suffix = os.path.splitext(name)
    if len(suffix.encode('utf-8')) > 24:
        stem, suffix = name, ''
    stem = stem.encode('utf-8')[:180 - len(suffix.encode('utf-8'))].decode('utf-8', errors='ignore') or 'artifact'
    return stem + suffix


def _ensure_directory(value):
    """逐组件创建私有目录，不允许 mkdir 的普通路径解析跟随链接。"""
    path = secure_io._absolute_path(value)
    if os.name == 'nt':
        api = secure_io._WindowsAPI()
        windows = secure_io._windows_parts(path)
        handles = []
        try:
            handles.append(api.open(api.volume_root(windows.drive), directory=True))
            api.validate_volume(handles[0])
            for part in windows.parts[1:]:
                handles.append(api.open(part, handles[-1], directory=True, create=True))
        finally:
            while handles:
                api.close(handles.pop())
    else:
        if not hasattr(os, 'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
            raise SecureIOError('当前系统不支持安全缓存目录')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(path.anchor, flags)
        try:
            for part in path.parts[1:]:
                try:
                    next_descriptor = os.open(part, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
        finally:
            os.close(descriptor)
    return path


def _verified_file(directory, name, size, digest):
    """从固定句柄逐块校验完整缓存，避免把同大小的修改误当作缓存命中。"""
    descriptor = directory._backend().open(name)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if before.st_size != size:
            raise ArtifactCacheError('文件缓存长度已变化')
        hasher = hashlib.sha256()
        while block := stream.read(1024 * 1024):
            hasher.update(block)
        after = os.fstat(stream.fileno())
    stamp = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if stamp(before) != stamp(after) or hasher.hexdigest() != digest:
        raise ArtifactCacheError('文件缓存内容已变化')


def _promote(directory, temporary, destination, descriptor):
    """原子公布完整文件且绝不覆盖碰巧出现的未登记文件。"""
    backend = directory._backend()
    if os.name == 'nt':
        import msvcrt
        api = backend.api
        encoded = destination.encode('utf-16-le')
        size = ctypes.sizeof(api.RenameInformation) + len(encoded)
        buffer = ctypes.create_string_buffer(size)
        info = api.RenameInformation.from_buffer(buffer)
        info.Flags, info.RootDirectory, info.FileNameLength = 0, backend.handles[-1], len(encoded)
        ctypes.memmove(ctypes.addressof(buffer) + api.RenameInformation.FileName.offset, encoded, len(encoded))
        status = api.IOStatus()
        api.check_status(api.native.NtSetInformationFile(msvcrt.get_osfhandle(descriptor),
            ctypes.byref(status), buffer, size, 65))
    else:
        # 同一目录硬链接的创建原子且不可覆盖；随后移除旧临时目录项。
        os.link(temporary, destination, src_dir_fd=backend.descriptor,
                dst_dir_fd=backend.descriptor, follow_symlinks=False)
        target = None
        try:
            target = backend.open(destination)
            source_stat, target_stat = os.fstat(descriptor), os.fstat(target)
            if (source_stat.st_dev, source_stat.st_ino) != (target_stat.st_dev, target_stat.st_ino):
                raise ArtifactCacheError('下载临时文件在公布期间已变化')
        except BaseException:
            directory.unlink(destination)
            raise
        finally:
            if target is not None:
                os.close(target)
        directory.unlink(temporary)
        os.fsync(backend.descriptor)


class ArtifactCache(AbstractContextManager):
    """一个服务端所有者下的单个会话缓存；构造时尝试回收已退出下载。"""
    def __init__(self, cache_root, session_id):
        self.session_hash = _digest(session_id)
        self.path = _ensure_directory(secure_io._absolute_path(cache_root) / self.session_hash)
        self.directory = SecureDirectory(self.path)
        try:
            self.cleanup()
        except BaseException:
            self.close()
            raise

    @contextmanager
    def _index_guard(self):
        try:
            lock = self.directory.lock(_INDEX_LOCK)
        except BlockingIOError:
            raise ArtifactBusy('文件缓存索引正忙，请稍后重试') from None
        with lock:
            yield

    def _read_index(self):
        try:
            value = self.directory.read_json(_INDEX)
        except FileNotFoundError:
            return {'version': 1, 'session': self.session_hash, 'entries': {}}
        if (not isinstance(value, dict) or value.get('version') != 1
                or value.get('session') != self.session_hash or not isinstance(value.get('entries'), dict)):
            raise ArtifactCacheError('文件缓存索引无效')
        for key, entry in value['entries'].items():
            if (not isinstance(key, str) or not _HASH.fullmatch(key) or not isinstance(entry, dict)
                    or entry.get('state') not in ('writing', 'promoting', 'ready')
                    or not isinstance(entry.get('name'), str)
                    or entry['name'] != key + '-' + _filename(entry['name'][65:])):
                raise ArtifactCacheError('文件缓存索引条目无效')
            if entry['state'] != 'ready':
                temporary = entry.get('temporary')
                match = _TEMP.fullmatch(temporary) if isinstance(temporary, str) else None
                if not match or match.group(1) != key:
                    raise ArtifactCacheError('临时文件缓存标识无效')
            if entry['state'] in ('promoting', 'ready'):
                if (type(entry.get('size')) is not int or entry['size'] < 0
                        or not isinstance(entry.get('sha256'), str) or not _HASH.fullmatch(entry['sha256'])):
                    raise ArtifactCacheError('完整文件缓存凭据无效')
        return value

    def _save_index(self, value):
        self.directory.write_json(_INDEX, value)

    @staticmethod
    def _lock_name(key):
        return '.agent-artifact-' + key + '.lock'

    def cleanup(self):
        """只探测非阻塞锁；存活下载、输入准备目录和无索引文件一律保留。"""
        try:
            with self._index_guard():
                index = self._read_index()
                changed = False
                for key, entry in list(index['entries'].items()):
                    if entry['state'] == 'ready':
                        continue
                    try:
                        lock = self.directory.lock(self._lock_name(key), create=False)
                    except (BlockingIOError, FileNotFoundError):
                        continue
                    with lock:
                        if entry['state'] == 'promoting' and self.directory.exists(entry['name']):
                            # 进程可能在原子提升成功后、索引提交前退出，保留并验证成品。
                            _verified_file(self.directory, entry['name'], entry['size'], entry['sha256'])
                            self.directory.unlink(entry['temporary'])
                            entry.pop('temporary')
                            entry['state'] = 'ready'
                        else:
                            self.directory.unlink(entry['temporary'])
                            del index['entries'][key]
                        changed = True
                if changed:
                    self._save_index(index)
        except ArtifactBusy:
            # 索引忙时不打断正常缓存使用，也不推断其他下载已经失效。
            return False
        return True

    def acquire(self, artifact_id, name, expected_size=None):
        """取得下载排他权；命中时 ready 为真，否则 write 后 commit。"""
        if expected_size is not None and (type(expected_size) is not int or expected_size < 0):
            raise ArtifactCacheError('已发布文件长度无效')
        key = _digest(artifact_id)
        try:
            lock = self.directory.lock(self._lock_name(key))
        except BlockingIOError:
            raise ArtifactBusy('此文件正在其他进程下载，请稍后重试') from None
        try:
            with self._index_guard():
                index = self._read_index()
                entry = index['entries'].get(key)
                if entry is not None and entry['state'] != 'ready':
                    if entry['state'] == 'promoting' and self.directory.exists(entry['name']):
                        _verified_file(self.directory, entry['name'], entry['size'], entry['sha256'])
                        self.directory.unlink(entry['temporary'])
                        entry.pop('temporary')
                        entry['state'] = 'ready'
                    else:
                        self.directory.unlink(entry['temporary'])
                        del index['entries'][key]
                        entry = None
                    self._save_index(index)
                if entry is not None and not self.directory.exists(entry['name']):
                    del index['entries'][key]
                    entry = None
                destination = key + '-' + _filename(name)
                if entry is not None:
                    if entry['name'] != destination or (expected_size is not None and entry['size'] != expected_size):
                        raise ArtifactCacheError('已发布文件信息与缓存不一致')
                else:
                    # 未被索引记录的同名文件可能是用户文件，绝不覆盖或推断为完成下载。
                    if self.directory.exists(destination):
                        raise ArtifactCacheError('文件缓存目标已被其他文件占用')
                    entry = {'state': 'writing', 'name': destination,
                             'temporary': '.agent-download-' + key + '-' + uuid4().hex + '.part'}
                    index['entries'][key] = entry
                    self._save_index(index)
            if entry['state'] == 'ready':
                _verified_file(self.directory, entry['name'], entry['size'], entry['sha256'])
            return ArtifactDownload(self, key, lock, deepcopy(entry), expected_size)
        except BaseException:
            lock.close()
            raise

    def close(self):
        if self.directory is not None:
            directory, self.directory = self.directory, None
            directory.close()

    def __exit__(self, *args):
        self.close()


class ArtifactDownload(AbstractContextManager):
    """下载句柄负责临时数据和锁；未提交退出会清理自己的临时文件。"""
    def __init__(self, cache, key, lock, entry, expected_size):
        self.cache, self.key, self.lock, self.entry = cache, key, lock, entry
        self.expected_size, self.ready, self.size = expected_size, entry['state'] == 'ready', entry.get('size', 0)
        self.path = cache.path / entry['name'] if self.ready else None
        self.stream = None
        self.hasher = hashlib.sha256()
        if not self.ready:
            backend = cache.directory._backend()
            if os.name == 'nt':
                handle = backend.api.open(entry['temporary'], backend.handles[-1], write=True,
                                           create=True, exclusive=True, delete=True)
                descriptor = backend.api.descriptor(handle, write=True)
            else:
                descriptor = backend.open(entry['temporary'], write=True, create=True, exclusive=True)
            self.stream = os.fdopen(descriptor, 'wb')

    def write(self, chunk):
        if self.ready or self.stream is None:
            raise ArtifactCacheError('此文件下载已完成或关闭')
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError('下载块必须为字节')
        self.stream.write(chunk)
        self.hasher.update(chunk)
        self.size += len(chunk)
        if self.expected_size is not None and self.size > self.expected_size:
            raise ArtifactCacheError('文件下载长度超过已发布长度')

    def commit(self):
        if self.ready:
            return self.path
        if self.stream is None:
            raise ArtifactCacheError('此文件下载已关闭')
        self.stream.flush()
        os.fsync(self.stream.fileno())
        if (os.fstat(self.stream.fileno()).st_size != self.size
                or self.expected_size is not None and self.size != self.expected_size):
            raise ArtifactCacheError('文件下载长度与已发布长度不一致')
        with self.cache._index_guard():
            index = self.cache._read_index()
            if index['entries'].get(self.key) != self.entry:
                raise ArtifactCacheError('文件缓存下载凭据已变化')
            self.entry.update(state='promoting', size=self.size, sha256=self.hasher.hexdigest())
            index['entries'][self.key] = deepcopy(self.entry)
            self.cache._save_index(index)
            try:
                _promote(self.cache.directory, self.entry['temporary'], self.entry['name'], self.stream.fileno())
            except FileExistsError:
                # 明确未提升的名称冲突不留下可误认成品的凭据。
                self.entry['state'] = 'writing'
                index['entries'][self.key] = deepcopy(self.entry)
                self.cache._save_index(index)
                raise
            self.stream.close()
            self.stream = None
            self.entry.pop('temporary')
            self.entry['state'] = 'ready'
            index['entries'][self.key] = deepcopy(self.entry)
            self.cache._save_index(index)
            self.path, self.ready = self.cache.path / self.entry['name'], True
        return self.path

    def close(self):
        if self.lock is None:
            return
        try:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            if not self.ready:
                try:
                    with self.cache._index_guard():
                        index = self.cache._read_index()
                        entry = index['entries'].get(self.key)
                        if entry is not None and entry == self.entry and entry['state'] != 'ready':
                            if entry['state'] == 'promoting' and self.cache.directory.exists(entry['name']):
                                # 提升可能已成功，交给下一次恢复校验，不删除成品。
                                pass
                            else:
                                self.cache.directory.unlink(entry['temporary'])
                                del index['entries'][self.key]
                                self.cache._save_index(index)
                except ArtifactBusy:
                    # 另一个下载短暂持有索引锁；由下一次使用回收本次残留。
                    pass
        finally:
            lock, self.lock = self.lock, None
            lock.close()

    def __exit__(self, exc_type, *args):
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise
