"""下载缓存的离线验证：共享锁、原子公布、崩溃恢复及受限清理。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from modules.agent import artifact_cache
from modules.agent.artifact_cache import ArtifactCache, ArtifactBusy, ArtifactCacheError
from modules.agent.secure_io import SecureDirectory, SecureIOError


@pytest.fixture
def cache_root(tmp_path):
    return tmp_path.resolve() / 'owner-cache'


def _entries(cache):
    with cache._index_guard():
        return cache._read_index()['entries']


def test_complete_download_is_durable_and_coalesced(cache_root):
    """完成文件跨缓存对象重复使用，既不重下也不残留临时文件。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', '中文报告.txt', expected_size=6) as download:
            assert not download.ready and download.path is None
            download.write(b'abc')
            download.write(b'def')
            path = download.commit()
            assert download.ready and download.size == 6
            assert path.read_bytes() == b'abcdef'
            assert download.commit() == path
        assert not list(cache.path.glob('*.part'))
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', '中文报告.txt', expected_size=6) as download:
            assert download.ready and download.path == path and download.size == 6
            with pytest.raises(ArtifactCacheError):
                download.write(b'no rewrite')
    assert path.read_bytes() == b'abcdef'


def test_owner_session_and_artifact_id_isolation(cache_root):
    """不同所有者、会话及同名不同标识不会共享本地文件。"""
    paths = []
    for root, session, artifact in [(cache_root, 'sess_one', 'a'), (cache_root, 'sess_two', 'a'),
        (cache_root.with_name('other-owner'), 'sess_one', 'a'), (cache_root, 'sess_one', 'b')]:
        with ArtifactCache(root, session) as cache:
            with cache.acquire(artifact, 'same.txt') as download:
                download.write(artifact.encode())
                paths.append(download.commit())
    assert len(set(paths)) == 4
    assert all(path.is_file() for path in paths)


@pytest.mark.parametrize('name', ['../../outside', r'C:\folder\NUL', '报告' * 200 + '.csv', 'CON', '.....'])
def test_remote_names_cannot_escape_cache(cache_root, name):
    """远端名称仅用于安全文件名，不成为本地目录或 Windows 设备。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', name) as download:
            download.write(b'content')
            path = download.commit()
            assert path.parent == cache.path and len(path.name.encode('utf-8')) <= 245


@pytest.mark.parametrize('received,expected', [(b'short', 20), (b'too long', 1)])
def test_incomplete_or_oversized_download_never_becomes_ready(cache_root, received, expected):
    """长度校验失败清理自己的未完成文件，不发布下载结果。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with pytest.raises(ArtifactCacheError, match='长度'):
            with cache.acquire('art_one', 'file', expected_size=expected) as download:
                download.write(received)
                download.commit()
        assert not _entries(cache)
        assert not list(cache.path.glob('*.part'))
        assert not list(cache.path.glob(hashlib.sha256(b'art_one').hexdigest() + '-*'))


def test_download_exception_and_normal_uncommitted_exit_cleanup(cache_root):
    """网络错误或取消时退出上下文，都只清理本次临时文件。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        for interrupted in (False, True):
            try:
                with cache.acquire('art_one', 'file') as download:
                    download.write(b'partial')
                    if interrupted:
                        raise RuntimeError('合成中断')
            except RuntimeError:
                pass
            assert not _entries(cache)
            assert not list(cache.path.glob('*.part'))


def test_second_download_is_busy_without_touching_active_data(cache_root):
    """同一文件不阻塞等待，也不重复创建临时文件。"""
    with ArtifactCache(cache_root, 'sess_one') as first:
        with first.acquire('art_one', 'file') as download:
            download.write(b'live')
            download.stream.flush()
            temporary = first.path / download.entry['temporary']
            with ArtifactCache(cache_root, 'sess_one') as second:
                assert temporary.read_bytes() == b'live'
                with pytest.raises(ArtifactBusy):
                    second.acquire('art_one', 'file')
            assert temporary.read_bytes() == b'live'
            download.commit()


def test_index_busy_is_nonblocking_and_does_not_start_download(cache_root):
    """短暂的索引竞争返回忙，之后仍可重试。"""
    with ArtifactCache(cache_root, 'sess_one') as first:
        with first._index_guard():
            with ArtifactCache(cache_root, 'sess_one') as second:
                with pytest.raises(ArtifactBusy):
                    second.acquire('art_one', 'file')
                assert not list(second.path.glob('*.part'))
        with first.acquire('art_one', 'file') as download:
            download.write(b'after busy')
            download.commit()


def test_unindexed_files_and_unrelated_directories_are_never_removed(cache_root):
    """无索引临时文件、旧目录和原始上传数据均不归清理器所有。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        original = cache.path / 'user-original.txt'
        unknown = cache.path / ('.agent-download-' + 'a' * 64 + '-' + 'b' * 32 + '.part')
        legacy = cache.path / 'chuanhu-agent-artifacts-unmarked'
        legacy.mkdir()
        active_preparation = cache.path / 'chuanhu-agent-inputs-active'
        active_preparation.mkdir()
        files = [original, unknown, legacy / 'partial', active_preparation / 'upload']
        for file in files:
            file.write_bytes(b'preserve original')
    with ArtifactCache(cache_root, 'sess_one'):
        assert all(file.read_bytes() == b'preserve original' for file in files)


def test_unindexed_destination_cannot_be_overwritten(cache_root):
    """即使名称碰巧吻合，也不覆盖无完成凭据的用户文件。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        destination = cache.path / (hashlib.sha256(b'art_one').hexdigest() + '-file')
        destination.write_bytes(b'user original')
        with pytest.raises(ArtifactCacheError, match='占用'):
            cache.acquire('art_one', 'file')
        assert destination.read_bytes() == b'user original'


def test_destination_created_during_download_is_never_clobbered(cache_root):
    """下载期间出现的同名文件仍不能被原子公布覆盖。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with pytest.raises((OSError, ArtifactCacheError)):
            with cache.acquire('art_one', 'file') as download:
                download.write(b'downloaded')
                destination = cache.path / download.entry['name']
                destination.write_bytes(b'user original')
                download.commit()
        assert destination.read_bytes() == b'user original'


def test_cached_content_changes_are_detected_even_at_same_size(cache_root):
    """缓存同大小改写也不能误报命中，更不能覆盖修改后的文件。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', 'file') as download:
            download.write(b'original')
            path = download.commit()
        path.write_bytes(b'modified')
        with pytest.raises(ArtifactCacheError, match='内容'):
            cache.acquire('art_one', 'file')
        assert path.read_bytes() == b'modified'


@pytest.mark.skipif(os.name == 'nt', reason='Windows junction 安全性由 secure_io 的原生平台用例验证')
def test_symlink_cache_root_and_final_file_are_rejected(cache_root, tmp_path):
    """缓存根或成品被替换为链接时不读取链接目标。"""
    outside = tmp_path / 'outside'
    outside.mkdir()
    cache_root.symlink_to(outside, target_is_directory=True)
    with pytest.raises((OSError, SecureIOError)):
        ArtifactCache(cache_root, 'sess_one')
    cache_root.unlink()
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', 'file') as download:
            download.write(b'original')
            path = download.commit()
        original = outside / 'original'
        original.write_bytes(b'original')
        path.unlink()
        path.symlink_to(original)
        with pytest.raises((OSError, SecureIOError)):
            cache.acquire('art_one', 'file')
        assert original.read_bytes() == b'original'


def _child(cache_root):
    script = '''
import sys
from modules.agent.artifact_cache import ArtifactCache
with ArtifactCache(sys.argv[1], 'sess_one') as cache:
    with cache.acquire('art_one', 'file', expected_size=8) as download:
        download.write(b'partial')
        download.stream.flush()
        print(download.entry['temporary'], flush=True)
        sys.stdin.readline()
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', script, str(cache_root)],
        cwd=Path(__file__).resolve().parents[2], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    temporary = process.stdout.readline().strip()
    assert temporary.startswith('.agent-download-'), process.stderr.read()
    return process, temporary


def test_live_process_partial_is_preserved_and_crashed_process_is_cleaned(cache_root):
    """真实子进程持锁时保留下载，进程被终止后下次使用回收孤儿。"""
    process, temporary = _child(cache_root)
    try:
        with ArtifactCache(cache_root, 'sess_one') as cache:
            partial = cache.path / temporary
            assert partial.read_bytes() == b'partial'
            with pytest.raises(ArtifactBusy):
                cache.acquire('art_one', 'file', expected_size=8)
        process.kill()
        process.communicate(timeout=10)
        assert partial.exists()
        with ArtifactCache(cache_root, 'sess_one') as cache:
            assert not partial.exists() and not _entries(cache)
            with cache.acquire('art_one', 'file', expected_size=8) as download:
                download.write(b'complete')
                assert download.commit().read_bytes() == b'complete'
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_crash_after_atomic_promotion_recovers_complete_file(cache_root):
    """在公布成品与完成索引之间强制退出，恢复时校验并保留成品。"""
    script = '''
import os, sys
from modules.agent import artifact_cache
original = artifact_cache._promote
def crash_after_promotion(*args):
    original(*args)
    os._exit(71)
artifact_cache._promote = crash_after_promotion
with artifact_cache.ArtifactCache(sys.argv[1], 'sess_one') as cache:
    with cache.acquire('art_one', 'file', expected_size=8) as download:
        download.write(b'complete')
        download.commit()
'''
    result = subprocess.run([sys.executable, '-c', script, str(cache_root)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10)
    assert result.returncode == 71, result.stderr
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', 'file', expected_size=8) as download:
            assert download.ready and download.path.read_bytes() == b'complete'
        assert not list(cache.path.glob('*.part'))


def test_invalid_index_never_deletes_paths_outside_managed_namespace(cache_root):
    """损坏或伪造索引不能授权删除任意文件。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        original = cache.path / 'user-original'
        original.write_bytes(b'preserve')
        key = hashlib.sha256(b'art_one').hexdigest()
        cache.directory.write_json(artifact_cache._INDEX, {'version': 1, 'session': cache.session_hash,
            'entries': {key: {'state': 'writing', 'name': key + '-file', 'temporary': 'user-original'}}})
    with pytest.raises(ArtifactCacheError):
        ArtifactCache(cache_root, 'sess_one')
    assert original.read_bytes() == b'preserve'


def test_owner_and_session_identifiers_are_not_written_in_cache_receipts(tmp_path):
    """索引和缓存路径只保存作用域散列，不复制用户标识、会话标识或密钥。"""
    owner, session, artifact = 'synthetic-owner@example.invalid', 'sess_private_synthetic_id', 'art_private_synthetic_id'
    root = tmp_path.resolve() / hashlib.sha256(owner.encode()).hexdigest()
    with ArtifactCache(root, session) as cache:
        with cache.acquire(artifact, 'output.txt') as download:
            download.write(b'public synthetic output')
            path = download.commit()
        saved = (cache.path / artifact_cache._INDEX).read_text()
        for value in (owner, session, artifact, 'api_key', 'authorization'):
            assert value not in saved and value not in str(path)
        assert cache.path.parent == root
        assert cache.path.name == hashlib.sha256(session.encode()).hexdigest()


def test_missing_cached_file_is_downloaded_again(cache_root):
    """已完成缓存被正常移走后允许重下，不永久卡在失效凭据上。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', 'file') as download:
            download.write(b'first')
            path = download.commit()
        path.unlink()
        with cache.acquire('art_one', 'file') as download:
            assert not download.ready
            download.write(b'again')
            assert download.commit().read_bytes() == b'again'


def test_close_during_index_contention_defers_only_own_cleanup(cache_root):
    """退出时索引忙可暂留部分文件，下一次使用会安全回收。"""
    with ArtifactCache(cache_root, 'sess_one') as cache:
        download = cache.acquire('art_one', 'file')
        download.write(b'partial')
        temporary = cache.path / download.entry['temporary']
        with cache._index_guard():
            download.close()
        assert temporary.exists()
    with ArtifactCache(cache_root, 'sess_one') as cache:
        assert not temporary.exists() and not _entries(cache)


def test_runtime_repeated_and_contending_cache_downloads_are_coalesced(cache_root, monkeypatch):
    """运行时重复读取复用成品；争用保持 preparing，随后恢复为 ready。"""
    from types import SimpleNamespace
    from modules.agent import runtime
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('离线测试禁止网络')))
    calls = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_bytes(self):
            yield b'complete'
    def content(identifier, *, session_id):
        calls.append((identifier, session_id))
        return Response()
    artifacts = SimpleNamespace(list=lambda *args, **kwargs: [
        {'id': 'art_one', 'filename': 'file.txt', 'size_bytes': 8, 'turn_id': 'turn_one'}],
        with_streaming_response=SimpleNamespace(content=content))
    client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(artifacts=artifacts))))
    with ArtifactCache(cache_root, 'sess_one') as cache:
        with cache.acquire('art_one', 'file.txt', expected_size=8) as held:
            held.write(b'complete')
            pending = runtime.download_artifacts(client, 'sess_one', cache_root=cache_root, live=True)
            assert pending[0]['status'] == 'preparing' and 'path' not in pending[0]
            terminal = runtime.download_artifacts(client, 'sess_one', cache_root=cache_root)
            assert terminal[0]['status'] == 'failed' and '重试' in terminal[0]['error']
            assert not calls
            path = held.commit()
    first = runtime.download_artifacts(client, 'sess_one', cache_root=cache_root)
    second = runtime.download_artifacts(client, 'sess_one', cache_root=cache_root)
    assert first[0]['status'] == second[0]['status'] == 'ready'
    assert first[0]['path'] == second[0]['path'] == str(path)
    assert not calls
    third = runtime.download_artifacts(client, 'sess_other', cache_root=cache_root)
    assert third[0]['status'] == 'ready' and len(calls) == 1
    assert third[0]['path'] != str(path)


def test_windows_promotion_uses_native_handle_and_never_replaces_destination(monkeypatch):
    """执行 Windows 分支的参数合同，确保符号可用且原生 Flags 不允许覆盖。"""
    import ctypes
    from types import SimpleNamespace
    class RenameInformation(ctypes.Structure):
        _fields_ = [('Flags', ctypes.c_uint32), ('RootDirectory', ctypes.c_void_p),
                    ('FileNameLength', ctypes.c_uint32), ('FileName', ctypes.c_uint16 * 1)]
    class IOStatus(ctypes.Structure):
        _fields_ = [('StatusOrPointer', ctypes.c_void_p), ('Information', ctypes.c_size_t)]
    captured = []
    def rename(handle, status, buffer, size, kind):
        info = RenameInformation.from_buffer(buffer)
        encoded = ctypes.string_at(ctypes.addressof(buffer) + RenameInformation.FileName.offset, info.FileNameLength)
        captured.append((handle, info.Flags, info.RootDirectory, encoded.decode('utf-16-le'), kind))
        return 0
    api = SimpleNamespace(RenameInformation=RenameInformation, IOStatus=IOStatus,
        native=SimpleNamespace(NtSetInformationFile=rename), check_status=lambda status: None)
    directory = SimpleNamespace(_backend=lambda: SimpleNamespace(api=api, handles=[7, 11]))
    monkeypatch.setattr(artifact_cache, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setitem(sys.modules, 'msvcrt', SimpleNamespace(get_osfhandle=lambda descriptor: descriptor + 100))
    artifact_cache._promote(directory, '.managed-partial', '成品.txt', 23)
    assert captured == [(123, 0, 11, '成品.txt', 65)]


def test_empty_remote_listing_still_cleans_crashed_partial(cache_root):
    """远端列表为空也先回收已退出下载，不让提前返回遗留部分文件。"""
    from types import SimpleNamespace
    from modules.agent import runtime
    process, temporary = _child(cache_root)
    try:
        process.kill()
        process.communicate(timeout=10)
        partial = cache_root / hashlib.sha256(b'sess_one').hexdigest() / temporary
        assert partial.exists()
        artifacts = SimpleNamespace(list=lambda *args, **kwargs: [])
        client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(artifacts=artifacts))))
        assert runtime.download_artifacts(client, 'sess_one', cache_root=cache_root) == []
        assert not partial.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
