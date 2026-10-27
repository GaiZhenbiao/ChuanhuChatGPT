"""安全文件后端的离线合同、竞争条件及原生平台验证。"""
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
from types import SimpleNamespace

import pytest

from modules.agent import secure_io
from modules.agent.secure_io import SecureDirectory, SecureIOError, read_regular_file


@pytest.fixture
def trusted(tmp_path):
    root = tmp_path / '可信目录'
    root.mkdir()
    # macOS 临时目录的配置别名只在测试根创建时规范化。
    return root.resolve()


def test_bounded_regular_file_read(trusted):
    """普通文件完整读取，边界大小允许，超限提前拒绝。"""
    path = trusted / '报告.txt'
    path.write_bytes(b'abc')
    assert read_regular_file(path, [trusted], 3) == b'abc'
    with pytest.raises(SecureIOError, match='大小上限'):
        read_regular_file(path, [trusted], 2)
    path.write_bytes(b'')
    assert read_regular_file(path, [trusted], 0) == b''


@pytest.mark.parametrize('kind', ['outside', 'sibling', 'root', 'relative', 'traversal'])
def test_untrusted_containment_rejected(trusted, kind):
    """拒绝目录本身、兄弟目录及上级跳转，不能依靠字符串前缀授权。"""
    outside = trusted.parent / 'outside'
    outside.write_bytes(b'private synthetic fixture')
    paths = {'outside': outside, 'sibling': trusted.with_name(trusted.name + '-other') / 'file',
             'root': trusted, 'relative': Path('file'), 'traversal': trusted / '..' / 'outside'}
    with pytest.raises(SecureIOError):
        read_regular_file(paths[kind], [trusted], 100)


@pytest.mark.skipif(os.name == 'nt', reason='原生 Windows 的符号链接与 junction 在专用测试中验证')
@pytest.mark.parametrize('kind', ['root', 'ancestor', 'directory', 'leaf', 'fifo'])
def test_posix_links_and_nonregular_files_rejected(trusted, kind):
    """逐级拒绝符号链接，FIFO 不阻塞，目录不能作为普通文件读取。"""
    nested = trusted / 'nested'
    nested.mkdir()
    file = nested / 'file'
    file.write_bytes(b'fixture')
    candidate, root = file, trusted
    if kind == 'root':
        root = trusted.parent / 'alias'
        root.symlink_to(trusted, target_is_directory=True)
        candidate = root / 'nested' / 'file'
    elif kind == 'ancestor':
        alias = trusted / 'alias'
        alias.symlink_to(nested, target_is_directory=True)
        candidate = alias / 'file'
    elif kind == 'directory':
        candidate = nested
    elif kind == 'leaf':
        candidate = nested / 'link'
        candidate.symlink_to(file)
    else:
        candidate = nested / 'pipe'
        os.mkfifo(candidate)
    with pytest.raises((OSError, SecureIOError)):
        read_regular_file(candidate, [root], 100)


def test_read_detects_identity_and_metadata_changes(trusted, monkeypatch):
    """读取后元数据改变即拒绝返回内容。"""
    path = trusted / 'file'
    path.write_bytes(b'abc')
    original = secure_io.os.fstat
    count = 0
    def changed(descriptor):
        nonlocal count
        value = original(descriptor)
        count += 1
        # POSIX 在 open 也检查普通文件类型；Windows 通过原生句柄检查。
        after_count = 3 if os.name != 'nt' else 2
        if count == after_count:
            return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev, st_ino=value.st_ino,
                st_size=value.st_size, st_mtime_ns=value.st_mtime_ns + 1, st_ctime_ns=value.st_ctime_ns)
        return value
    monkeypatch.setattr(secure_io.os, 'fstat', changed)
    with pytest.raises(SecureIOError, match='已变化'):
        read_regular_file(path, [trusted], 10)


@pytest.mark.skipif(os.name == 'nt', reason='Windows 目录句柄禁止重命名，见原生 Windows 用例')
def test_pinned_directory_cannot_be_redirected_by_rename(trusted):
    """根路径被换为外部符号链接后，读写仍只作用于已固定目录。"""
    (trusted / 'file').write_bytes(b'trusted')
    outside = trusted.parent / 'outside'
    outside.mkdir()
    (outside / 'file').write_bytes(b'outside')
    (outside / 'receipt').write_text('{"outside":true}')
    moved = trusted.with_name('moved')
    with SecureDirectory(trusted) as directory:
        trusted.rename(moved)
        trusted.symlink_to(outside, target_is_directory=True)
        assert directory.read_bytes('file', 20) == b'trusted'
        directory.write_json('receipt', {'trusted': True})
        assert json.loads((moved / 'receipt').read_text()) == {'trusted': True}
        assert json.loads((outside / 'receipt').read_text()) == {'outside': True}


@pytest.mark.skipif(os.name == 'nt', reason='此注入验证 POSIX 的 openat 竞争窗口')
def test_directory_swap_between_checks_and_open_is_rejected(trusted, monkeypatch):
    """攻击发生在真正打开子目录之前时，O_NOFOLLOW 仍拒绝跟随。"""
    nested = trusted / 'nested'
    nested.mkdir()
    (nested / 'file').write_bytes(b'trusted')
    outside = trusted.parent / 'outside'
    outside.mkdir()
    (outside / 'file').write_bytes(b'outside')
    original = os.open
    def racing_open(path, flags, *args, **kwargs):
        if path == 'nested':
            nested.rename(trusted / 'moved')
            nested.symlink_to(outside, target_is_directory=True)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', racing_open)
    monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {racing_open})
    with pytest.raises(OSError):
        read_regular_file(nested / 'file', [trusted], 20)


def test_journal_and_cancel_roundtrip(trusted):
    """JSON 原子替换、取消标记、缺失语义及幂等关闭保持一致。"""
    directory = SecureDirectory(trusted)
    with directory:
        assert not directory.exists('cancel')
        with pytest.raises(FileNotFoundError):
            directory.read_json('missing')
        directory.write_json('receipt', {'状态': '准备中'})
        directory.write_json('receipt', {'状态': '已就绪'})
        assert directory.read_json('receipt') == {'状态': '已就绪'}
        directory.touch('cancel')
        directory.touch('cancel')
        assert directory.exists('cancel')
        directory.unlink('cancel')
        directory.unlink('cancel')
        assert not directory.exists('cancel')
        with pytest.raises(FileNotFoundError):
            directory.unlink('cancel', missing_ok=False)
        assert not list(trusted.glob('*.tmp'))
        if os.name != 'nt':
            assert (trusted / 'receipt').stat().st_mode & 0o777 == 0o600
    directory.close()
    with pytest.raises(SecureIOError, match='已关闭'):
        directory.read_json('receipt')


@pytest.mark.parametrize('name', ['', '.', '..', '../outside', 'nested/file', 'nested\\file', '\x00'])
def test_directory_methods_reject_nonlocal_names(trusted, name):
    """所有公开文件操作只允许直接子项，不接受额外路径片段。"""
    with SecureDirectory(trusted) as directory:
        for action in (directory.read_bytes, directory.read_json, directory.touch,
                       directory.exists, directory.unlink, directory.lock):
            with pytest.raises(SecureIOError):
                action(name)
        with pytest.raises(SecureIOError):
            directory.write_json(name, {})


def test_invalid_json_never_overwrites_previous_receipt(trusted):
    """不可序列化的数据不产生半份记录，也不覆盖旧记录。"""
    with SecureDirectory(trusted) as directory:
        directory.write_json('receipt', {'old': True})
        with pytest.raises(ValueError):
            directory.write_json('receipt', {'invalid': float('nan')})
        assert directory.read_json('receipt') == {'old': True}
        assert not list(trusted.glob('*.tmp'))


@pytest.mark.skipif(os.name == 'nt', reason='Windows 的句柄重命名故障由原生接口测试覆盖')
def test_failed_replace_preserves_previous_receipt_and_cleans_up(trusted, monkeypatch):
    """原子替换失败不能把部分文件当作成功记录。"""
    with SecureDirectory(trusted) as directory:
        directory.write_json('receipt', {'old': True})
        def failed(*args, **kwargs):
            raise OSError('合成替换故障')
        monkeypatch.setattr(os, 'replace', failed)
        with pytest.raises(OSError, match='合成替换故障'):
            directory.write_json('receipt', {'new': True})
        assert directory.read_json('receipt') == {'old': True}
        assert not list(trusted.glob('*.tmp'))


def test_same_process_and_subprocess_lock_exclusion(trusted):
    """锁跨对象和跨进程互斥，释放后原锁文件可以继续使用。"""
    script = '''
import sys
from modules.agent.secure_io import SecureDirectory
with SecureDirectory(sys.argv[1]) as directory:
    try:
        lock = directory.lock('lock')
    except BlockingIOError:
        print('busy')
    else:
        print('acquired')
        lock.close()
'''
    with SecureDirectory(trusted) as directory:
        with pytest.raises(FileNotFoundError):
            directory.lock('missing', create=False)
        with directory.lock('lock'):
            with pytest.raises(BlockingIOError):
                directory.lock('lock')
            result = subprocess.run([sys.executable, '-c', script, str(trusted)], cwd=Path(__file__).resolve().parents[2],
                                    capture_output=True, text=True, timeout=10, check=True)
            assert result.stdout.strip() == 'busy'
        result = subprocess.run([sys.executable, '-c', script, str(trusted)], cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, text=True, timeout=10, check=True)
        assert result.stdout.strip() == 'acquired'


def test_process_exit_releases_lock(trusted):
    """进程异常终止也由内核释放锁，不依赖删除锁文件。"""
    script = '''
import sys
from modules.agent.secure_io import SecureDirectory
with SecureDirectory(sys.argv[1]) as directory:
    lock = directory.lock('lock')
    print('held', flush=True)
    sys.stdin.readline()
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', script, str(trusted)], cwd=Path(__file__).resolve().parents[2],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'held'
        with SecureDirectory(trusted) as directory:
            with pytest.raises(BlockingIOError):
                directory.lock('lock')
            process.kill()
            process.communicate(timeout=10)
            with directory.lock('lock'):
                pass
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


@pytest.mark.parametrize('path', [r'\\server\share\file', r'\\?\C:\file', r'\\.\NUL', r'C:relative',
    r'C:\root\..\outside', r'C:\root\file:secret', r'C:\root\NUL.txt', r'C:\root\COM1',
    'C:\\root\\tail.', 'C:\\root\\tail ', 'C:\\root\\a\x00b'])
def test_windows_ambiguous_and_device_paths_fail_closed(path):
    """无需伪装操作系统，直接验证 Windows 路径准入规则。"""
    with pytest.raises(SecureIOError):
        secure_io._windows_parts(path)


def test_windows_unicode_local_path_is_accepted():
    """支持常规盘符和中文文件名。"""
    assert secure_io._windows_parts(r'C:\附件\报告.txt') == PureWindowsPath(r'C:\附件\报告.txt')


class FakeWindowsAPI:
    """只验证后端调用协议；不冒充真实 NTFS 安全验证。"""
    def __init__(self, *, reject=None, filesystem=True):
        self.opened, self.closed, self.reject, self.filesystem = [], [], reject, filesystem
    def volume_root(self, drive):
        return '\\Device\\HarddiskVolume3\\'
    def open(self, name, parent=None, **flags):
        if name == self.reject:
            raise SecureIOError('合成重解析点')
        handle = len(self.opened) + 1
        self.opened.append((handle, name, parent, flags))
        return handle
    def validate_volume(self, handle):
        if not self.filesystem:
            raise SecureIOError('合成不支持的文件系统')
    def close(self, handle):
        self.closed.append(handle)


def test_windows_directory_traverses_relative_handles_and_retains_ancestors():
    """仅根目录使用绝对 NT 路径，每个后续名字都绑定上一级句柄。"""
    api = FakeWindowsAPI()
    directory = secure_io._WindowsDirectory(PureWindowsPath(r'C:\one\two'), api=api)
    assert [(name, parent) for _, name, parent, _ in api.opened] == [('\\Device\\HarddiskVolume3\\', None), ('one', 1), ('two', 2)]
    assert all(flags == {'directory': True} for _, _, _, flags in api.opened)
    assert not api.closed
    directory.close()
    directory.close()
    assert api.closed == [3, 2, 1]


@pytest.mark.parametrize('reject,filesystem', [('two', True), (None, False)])
def test_windows_directory_failure_closes_all_acquired_handles(reject, filesystem):
    """原生打开或文件系统检查失败时，不泄漏已经取得的目录句柄。"""
    api = FakeWindowsAPI(reject=reject, filesystem=filesystem)
    with pytest.raises(SecureIOError):
        secure_io._WindowsDirectory(PureWindowsPath(r'C:\one\two'), api=api)
    assert api.closed == list(reversed([handle for handle, *_ in api.opened]))


@pytest.mark.skipif(os.name != 'nt', reason='需要真实 Windows NTFS；Linux 不声称已验证')
def test_windows_native_directory_handle_blocks_rename(trusted):
    """原生目录句柄持有期间，攻击者不能替换路径指向。"""
    with SecureDirectory(trusted) as directory:
        directory.write_json('receipt', {'原生': True})
        with pytest.raises(OSError):
            trusted.rename(trusted.with_name('moved'))
        assert directory.read_json('receipt') == {'原生': True}


@pytest.mark.skipif(os.name != 'nt', reason='需要真实 Windows NTFS junction；Linux 不声称已验证')
def test_windows_native_junction_is_rejected(trusted):
    """junction 不需要开发者模式，也必须拒绝而不能跟随。"""
    target = trusted.parent / 'outside'
    target.mkdir()
    (target / 'file').write_bytes(b'outside synthetic fixture')
    junction = trusted / 'junction'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(target)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    try:
        with pytest.raises((OSError, SecureIOError)):
            read_regular_file(junction / 'file', [trusted], 100)
    finally:
        os.rmdir(junction)


@pytest.mark.skipif(os.name != 'nt', reason='需要真实 Windows 原生句柄重命名')
def test_windows_native_failed_replace_preserves_previous_receipt(trusted, monkeypatch):
    """原生重命名失败时清理原临时句柄，旧记录仍完整可读。"""
    with SecureDirectory(trusted) as directory:
        directory.write_json('receipt', {'old': True})
        def failed(*args, **kwargs):
            raise OSError('合成句柄重命名失败')
        monkeypatch.setattr(directory._directory.api, 'replace', failed)
        with pytest.raises(OSError, match='合成句柄重命名失败'):
            directory.write_json('receipt', {'new': True})
        assert directory.read_json('receipt') == {'old': True}
        assert not list(trusted.glob('*.tmp'))


@pytest.mark.skipif(os.name == 'nt', reason='真实 Windows 的链接创建需要权限，另有 junction 验证')
@pytest.mark.parametrize('action', ['read_bytes', 'read_json', 'write_json', 'touch', 'exists', 'lock'])
def test_existing_leaf_symlinks_are_rejected_for_all_io(trusted, action):
    """读写、锁和取消标记不接受已有末级链接。"""
    outside = trusted.parent / 'outside'
    outside.write_text('{"outside":true}')
    (trusted / 'link').symlink_to(outside)
    with SecureDirectory(trusted) as directory:
        with pytest.raises((OSError, SecureIOError)):
            if action == 'write_json':
                directory.write_json('link', {'new': True})
            else:
                getattr(directory, action)('link')
    assert outside.read_text() == '{"outside":true}'


class NativeFunction:
    """让合成函数保留 ctypes 的签名属性，但不执行系统调用。"""
    def __init__(self, callback):
        self.callback = callback
    def __call__(self, *args):
        return self.callback(*args)


class NativeWindowsHarness:
    """逐项捕获真实原生适配层的参数；不模拟 NTFS 的安全保证。"""
    def __init__(self):
        import ctypes
        self.calls, self.closed, self.attributes, self.file_type = [], [], 0, 1
        self.writes, self.flushed, self.updated = [], [], []
        self.mapping = '\\Device\\HarddiskVolume3'
        self.kernel = SimpleNamespace(
            CloseHandle=NativeFunction(lambda handle: self.closed.append(handle) or 1),
            GetFileType=NativeFunction(lambda handle: self.file_type),
            QueryDosDeviceW=NativeFunction(self.query_drive),
            GetFileInformationByHandle=NativeFunction(self.information),
            GetVolumeInformationByHandleW=NativeFunction(self.volume),
            WriteFile=NativeFunction(self.write),
            FlushFileBuffers=NativeFunction(lambda handle: self.flushed.append(handle) or 1))
        self.native = SimpleNamespace(NtCreateFile=NativeFunction(self.open),
            NtSetInformationFile=NativeFunction(self.update), RtlNtStatusToDosError=NativeFunction(lambda status: 5))
        self.api = secure_io._WindowsAPI(kernel=self.kernel, native=self.native)
    def open(self, result, access, attributes, status, allocation, file_attributes,
             sharing, disposition, options, ea, ea_length):
        import ctypes
        value = attributes._obj
        name = ctypes.string_at(value.ObjectName.contents.Buffer, value.ObjectName.contents.Length).decode('utf-16-le')
        self.calls.append(dict(name=name, parent=value.RootDirectory, access=access, sharing=sharing,
                               disposition=disposition, options=options, attributes=value.Attributes))
        result._obj.value = 123
        return 0
    def query_drive(self, drive, mapping, size):
        mapping.value = self.mapping
        return len(self.mapping) + 2
    def information(self, handle, info):
        info._obj.attributes = self.attributes
        return 1
    def volume(self, handle, volume, volume_size, serial, maximum, flags, filesystem, size):
        filesystem.value = 'NTFS'
        return 1
    def write(self, handle, block, size, written, overlapped):
        import ctypes
        self.writes.append(ctypes.string_at(block, size))
        written._obj.value = size
        return 1
    def update(self, handle, status, buffer, size, kind):
        import ctypes
        self.updated.append((handle, kind, ctypes.string_at(buffer, size)))
        return 0


def test_native_windows_abi_structures_and_relative_open_flags():
    """检查 Windows 固定宽度结构、Unicode 字节长度及不跟随标志。"""
    import ctypes
    harness = NativeWindowsHarness()
    api = harness.api
    assert ctypes.sizeof(api.FileInformation) == 52
    assert ctypes.sizeof(api.IOStatus) == ctypes.sizeof(ctypes.c_void_p) * 2
    assert api.RenameInformation.FileName.offset == (20 if ctypes.sizeof(ctypes.c_void_p) == 8 else 12)
    assert api.open('报告.txt', 456) == 123
    call = harness.calls[-1]
    assert call['name'] == '报告.txt' and call['parent'] == 456
    assert call['options'] & api.OPEN_REPARSE
    assert call['options'] & api.NON_DIRECTORY
    assert call['options'] & api.SYNCHRONOUS
    assert call['disposition'] == api.OPEN
    assert call['sharing'] == api.SHARE_READ | api.SHARE_DELETE
    assert call['access'] & api.READ_DATA and not call['access'] & api.WRITE_DATA
    assert call['attributes'] == 0x1000
    harness.attributes = api.DIRECTORY_ATTRIBUTE
    api.open('nested', 456, directory=True)
    call = harness.calls[-1]
    assert call['options'] & api.DIRECTORY
    assert call['options'] & api.OPEN_REPARSE
    assert call['access'] & api.TRAVERSE
    assert not call['sharing'] & api.SHARE_DELETE


@pytest.mark.parametrize('attributes,file_type,directory', [(0x400, 1, False), (0x410, 1, True),
    (0x40, 1, False), (0x10, 1, False), (0, 1, True), (0, 3, False)])
def test_native_windows_invalid_handle_types_are_closed(attributes, file_type, directory):
    """重解析点、设备及目录类型不匹配都会关闭已获得的句柄。"""
    harness = NativeWindowsHarness()
    harness.attributes, harness.file_type = attributes, file_type
    with pytest.raises(SecureIOError):
        harness.api.open('file', 456, directory=directory)
    assert harness.closed == [123]


def test_native_windows_write_flush_and_rename_uses_original_handle():
    """刷写和重命名只使用原句柄，目标名绑定可信目录句柄。"""
    import ctypes
    harness = NativeWindowsHarness()
    api = harness.api
    api.open('temporary', 456, write=True, create=True, exclusive=True, delete=True)
    call = harness.calls[-1]
    assert call['disposition'] == api.CREATE and call['sharing'] == 0
    assert call['access'] & api.WRITE_DATA and call['access'] & api.DELETE
    api.write(123, b'content\x00bytes')
    assert b''.join(harness.writes) == b'content\x00bytes' and harness.flushed == [123]
    api.replace(123, 456, '记录.json')
    handle, kind, raw = harness.updated[-1]
    info = api.RenameInformation.from_buffer_copy(raw)
    assert handle == 123 and kind == 65
    assert info.Flags == 3 and info.RootDirectory == 456
    assert raw[api.RenameInformation.FileName.offset:][:info.FileNameLength].decode('utf-16-le') == '记录.json'
    api.delete(123)
    assert harness.updated[-1] == (123, 13, b'\x01')


@pytest.mark.skipif(os.name != 'nt', reason='需要真实 Windows NTFS，验证原生打开时发生的 junction 替换')
def test_windows_native_junction_swap_at_open_is_rejected(trusted, monkeypatch):
    """检查路径之后、实际打开之前置入 junction 也不能越界读取。"""
    nested = trusted / 'nested'
    nested.mkdir()
    (nested / 'file').write_bytes(b'trusted')
    outside = trusted.parent / 'outside'
    outside.mkdir()
    (outside / 'file').write_bytes(b'outside synthetic fixture')
    original = secure_io._WindowsAPI.open
    def racing_open(api, name, *args, **kwargs):
        if name == 'nested':
            nested.rename(trusted / 'moved')
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(nested), str(outside)],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
        return original(api, name, *args, **kwargs)
    monkeypatch.setattr(secure_io._WindowsAPI, 'open', racing_open)
    try:
        with pytest.raises((OSError, SecureIOError)):
            read_regular_file(nested / 'file', [trusted], 100)
    finally:
        if nested.exists():
            os.rmdir(nested)


def test_native_windows_marker_handles_do_not_conflict_with_writers():
    """取消标记只请求元数据访问，兼容同时创建或检查同一标记。"""
    harness = NativeWindowsHarness()
    api = harness.api
    api.open('cancel', 456, create=True, metadata=True)
    call = harness.calls[-1]
    assert call['disposition'] == api.OPEN_IF
    assert not call['access'] & (api.READ_DATA | api.WRITE_DATA)
    assert call['sharing'] == api.SHARE_READ | api.SHARE_WRITE | api.SHARE_DELETE


@pytest.mark.skipif(os.name != 'nt', reason='需要真实 Windows NTFS 检验并发句柄共享模式')
def test_windows_native_marker_read_during_touch_is_safe(trusted, monkeypatch):
    """在 touch 尚未关闭句柄时读取标记，取消检查不得发生共享冲突。"""
    with SecureDirectory(trusted) as directory:
        api = directory._directory.api
        original = api.descriptor
        checking = False
        def check_while_open(handle, *, write=False):
            nonlocal checking
            if not checking:
                checking = True
                assert directory.exists('cancel')
            return original(handle, write=write)
        monkeypatch.setattr(api, 'descriptor', check_while_open)
        directory.touch('cancel')
        assert checking


@pytest.mark.skipif(os.name != 'nt', reason='需要真实 Windows NTFS 检验打开目标的原子替换')
def test_windows_native_replace_allows_existing_reader(trusted):
    """后台更新记录时，已有读取者仍读取旧完整内容，新读取者取得新记录。"""
    with SecureDirectory(trusted) as directory:
        directory.write_json('receipt', {'old': True})
        descriptor = directory._directory.open('receipt')
        try:
            directory.write_json('receipt', {'new': True})
            assert json.loads(os.read(descriptor, 100)) == {'old': True}
            assert directory.read_json('receipt') == {'new': True}
        finally:
            os.close(descriptor)


@pytest.mark.parametrize('mapping', [r'\??\C:\root\junction\nested',
    r'\Device\LanmanRedirector\server\share', r'\Device\HarddiskVolume3\junction',
    r'\Device\HarddiskVolumeShadowCopy1'])
def test_native_windows_drive_mappings_fail_closed(mapping):
    """SUBST、多级设备别名及网络盘不能绕过逐组件目录检查。"""
    harness = NativeWindowsHarness()
    harness.mapping = mapping
    with pytest.raises(SecureIOError):
        harness.api.volume_root('X:')
    assert not harness.calls


def test_native_windows_drive_binds_one_physical_root():
    """盘符仅查找一次，后续打开使用已确定的物理卷路径。"""
    harness = NativeWindowsHarness()
    assert harness.api.volume_root('C:') == '\\Device\\HarddiskVolume3\\'
