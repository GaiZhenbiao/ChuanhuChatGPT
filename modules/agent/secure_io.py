"""附件与准备记录的安全文件操作，不使用先检查路径再普通打开的降级方案。

POSIX 使用目录描述符和 O_NOFOLLOW；Windows 使用 NTFS 目录句柄、相对
NtCreateFile 与句柄重命名。所有重解析点（包括 junction）均拒绝。Windows
仅支持 Windows 10 1709+ 的本地物理盘符 NTFS 路径，其他文件系统、
SUBST 别名及命名空间安全失败。Windows
会刷写文件内容并原子替换，但不承诺断电后目录项与 POSIX fsync 等同。
"""
from contextlib import AbstractContextManager
import ctypes
import errno
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
from uuid import uuid4


class SecureIOError(ValueError):
    """文件类型、路径或读取一致性不满足安全要求。"""


def _absolute_path(value):
    try:
        path = Path(os.fspath(value))
    except (TypeError, ValueError):
        raise SecureIOError('安全文件路径无效') from None
    if not path.is_absolute() or '..' in path.parts or '\x00' in str(path):
        raise SecureIOError('安全文件操作需要不含上级跳转的绝对路径')
    return path


def _name(value):
    if (not isinstance(value, str) or not value or value in ('.', '..')
            or any(char in value for char in ('/', '\\', '\x00'))):
        raise SecureIOError('安全文件操作只接受单个文件名')
    return value


def _windows_parts(value):
    """拒绝设备名、备用数据流和 Windows 会隐式改写的名字。"""
    path = PureWindowsPath(os.fspath(value))
    if not path.is_absolute() or not re.fullmatch(r'[A-Za-z]:', path.drive):
        raise SecureIOError('Windows 安全文件操作仅支持本地 NTFS 盘符路径')
    for part in path.parts[1:]:
        _windows_name(part)
    return path


def _windows_name(value):
    _name(value)
    if (any(ord(char) < 32 or char in ':<>"|?*' for char in value)
            or value.endswith((' ', '.'))
            or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])',
                            value.split('.')[0], re.IGNORECASE)):
        raise SecureIOError('Windows 文件名包含设备名、备用数据流或歧义字符')
    return value


def _read_fd(descriptor, max_bytes):
    if type(max_bytes) is not int or max_bytes < 0:
        os.close(descriptor)
        raise ValueError('读取上限必须是非负整数')
    with os.fdopen(descriptor, 'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise SecureIOError('文件必须是普通文件，不能是目录、链接或设备')
        if before.st_size > max_bytes:
            raise SecureIOError('文件超过安全读取大小上限')
        contents = source.read(max_bytes + 1)
        after = os.fstat(source.fileno())
    stamp = lambda value: (value.st_dev, value.st_ino, value.st_size,
                           value.st_mtime_ns, value.st_ctime_ns)
    if len(contents) > max_bytes:
        raise SecureIOError('文件超过安全读取大小上限')
    if stamp(before) != stamp(after) or len(contents) != before.st_size:
        raise SecureIOError('读取期间文件已变化，请重新选择')
    return contents


class _FileLock(AbstractContextManager):
    """持有一个由内核随进程退出释放的排他锁。"""
    def __init__(self, descriptor):
        self.descriptor = descriptor
        try:
            if os.name == 'nt':
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise BlockingIOError(errno.EAGAIN, '附件准备锁已被占用') from None
                    raise
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.descriptor is not None:
            descriptor, self.descriptor = self.descriptor, None
            os.close(descriptor)

    def __exit__(self, *args):
        self.close()


class _PosixDirectory:
    def __init__(self, path):
        if (not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY')
                or os.open not in os.supports_dir_fd):
            raise SecureIOError('当前系统不支持安全目录句柄')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        self.descriptor = os.open(path.anchor, flags)
        try:
            for part in path.parts[1:]:
                descriptor = os.open(part, flags, dir_fd=self.descriptor)
                os.close(self.descriptor)
                self.descriptor = descriptor
        except BaseException:
            self.close()
            raise

    def open(self, name, *, write=False, create=False, exclusive=False, metadata=False):
        flags = (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK
        if create:
            flags |= os.O_CREAT
        if exclusive:
            flags |= os.O_EXCL
        descriptor = os.open(name, flags, 0o600, dir_fd=self.descriptor)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise SecureIOError('文件必须是普通文件，不能是目录、链接或设备')
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def write(self, name, contents):
        temporary = name + '.' + uuid4().hex + '.tmp'
        descriptor = self.open(temporary, write=True, create=True, exclusive=True)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=self.descriptor, dst_dir_fd=self.descriptor)
            os.fsync(self.descriptor)
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=self.descriptor)
            except FileNotFoundError:
                pass
            raise

    def unlink(self, name):
        os.unlink(name, dir_fd=self.descriptor)

    def close(self):
        if self.descriptor is not None:
            descriptor, self.descriptor = self.descriptor, None
            os.close(descriptor)


class _WindowsAPI:
    """仅在 Windows 加载的窄接口；不用路径字符串重新打开已校验的目录。

    原生接口定义来自 Microsoft 的 NtCreateFile、NtSetInformationFile、
    FILE_RENAME_INFORMATION 文档。ctypes 结构使用固定宽度 Windows 类型。
    """
    READ_ATTRIBUTES, SYNCHRONIZE, DELETE = 0x80, 0x100000, 0x10000
    READ_DATA, WRITE_DATA, TRAVERSE = 0x1, 0x2, 0x20
    DIRECTORY, NON_DIRECTORY, SYNCHRONOUS, OPEN_REPARSE = 0x1, 0x40, 0x20, 0x200000
    SHARE_READ, SHARE_WRITE, SHARE_DELETE = 0x1, 0x2, 0x4
    OPEN, CREATE, OPEN_IF = 1, 2, 3
    REPARSE_ATTRIBUTE, DIRECTORY_ATTRIBUTE, DEVICE_ATTRIBUTE = 0x400, 0x10, 0x40

    def __init__(self, *, kernel=None, native=None):
        from ctypes import wintypes
        self.kernel = kernel if kernel is not None else ctypes.WinDLL('kernel32', use_last_error=True)
        self.native = native if native is not None else ctypes.WinDLL('ntdll', use_last_error=True)
        handle, ulong, ushort = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint16

        class UnicodeString(ctypes.Structure):
            _fields_ = [('Length', ushort), ('MaximumLength', ushort), ('Buffer', handle)]

        class ObjectAttributes(ctypes.Structure):
            _fields_ = [('Length', ulong), ('RootDirectory', handle),
                        ('ObjectName', ctypes.POINTER(UnicodeString)), ('Attributes', ulong),
                        ('SecurityDescriptor', handle), ('SecurityQualityOfService', handle)]

        class IOStatus(ctypes.Structure):
            _fields_ = [('StatusOrPointer', handle), ('Information', ctypes.c_size_t)]

        class FileTime(ctypes.Structure):
            _fields_ = [('low', ulong), ('high', ulong)]

        class FileInformation(ctypes.Structure):
            _fields_ = [('attributes', ulong), ('creation', FileTime),
                        ('access', FileTime), ('write', FileTime),
                        ('volume', ulong), ('size_high', ulong), ('size_low', ulong),
                        ('links', ulong), ('index_high', ulong), ('index_low', ulong)]

        class RenameInformation(ctypes.Structure):
            _fields_ = [('Flags', ulong), ('RootDirectory', handle),
                        ('FileNameLength', ulong), ('FileName', ctypes.c_uint16 * 1)]

        self.UnicodeString, self.ObjectAttributes, self.IOStatus = UnicodeString, ObjectAttributes, IOStatus
        self.FileInformation, self.RenameInformation = FileInformation, RenameInformation
        self.native.NtCreateFile.argtypes = [ctypes.POINTER(handle), ulong, ctypes.POINTER(ObjectAttributes),
            ctypes.POINTER(IOStatus), handle, ulong, ulong, ulong, ulong, handle, ulong]
        self.native.NtCreateFile.restype = ctypes.c_int32
        self.native.NtSetInformationFile.argtypes = [handle, ctypes.POINTER(IOStatus), handle, ulong, ulong]
        self.native.NtSetInformationFile.restype = ctypes.c_int32
        self.native.RtlNtStatusToDosError.argtypes = [ctypes.c_int32]
        self.native.RtlNtStatusToDosError.restype = ulong
        self.kernel.CloseHandle.argtypes = [handle]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.WriteFile.argtypes = [handle, handle, ulong, ctypes.POINTER(ulong), handle]
        self.kernel.WriteFile.restype = wintypes.BOOL
        self.kernel.FlushFileBuffers.argtypes = [handle]
        self.kernel.FlushFileBuffers.restype = wintypes.BOOL
        self.kernel.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ulong]
        self.kernel.QueryDosDeviceW.restype = ulong
        self.kernel.GetFileType.argtypes = [handle]
        self.kernel.GetFileType.restype = ulong
        self.kernel.GetFileInformationByHandle.argtypes = [handle, ctypes.POINTER(FileInformation)]
        self.kernel.GetFileInformationByHandle.restype = wintypes.BOOL
        self.kernel.GetVolumeInformationByHandleW.argtypes = [handle, wintypes.LPWSTR, ulong,
            ctypes.POINTER(ulong), ctypes.POINTER(ulong), ctypes.POINTER(ulong), wintypes.LPWSTR, ulong]
        self.kernel.GetVolumeInformationByHandleW.restype = wintypes.BOOL

    def check_status(self, status):
        if status < 0:
            raise ctypes.WinError(self.native.RtlNtStatusToDosError(status))

    def volume_root(self, drive):
        # 一次绑定物理卷，拒绝 SUBST 路径及网络映射，避免盘符展开隐藏中间链接。
        mapping = ctypes.create_unicode_buffer(32768)
        if not self.kernel.QueryDosDeviceW(drive, mapping, len(mapping)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not re.fullmatch(r'\\Device\\HarddiskVolume[0-9]+', mapping.value):
            raise SecureIOError('Windows 安全文件操作不支持 SUBST 别名或网络映射盘')
        return mapping.value + '\\'

    def open(self, name, parent=None, *, directory=False, write=False, create=False,
             exclusive=False, delete=False, shared_write=False, metadata=False):
        encoded = name.encode('utf-16-le')
        if len(encoded) > 65532:
            raise SecureIOError('Windows 文件名过长')
        buffer = ctypes.create_string_buffer(encoded + b'\x00\x00')
        unicode_name = self.UnicodeString(len(encoded), len(encoded) + 2, ctypes.addressof(buffer))
        # OBJ_DONT_REPARSE 拒绝解析期间的重解析；不折叠大小写敏感目录的名字。
        attributes = self.ObjectAttributes(ctypes.sizeof(self.ObjectAttributes), parent,
                                           ctypes.pointer(unicode_name), 0x1000, None, None)
        access = self.READ_ATTRIBUTES | self.SYNCHRONIZE
        if directory:
            access |= self.TRAVERSE
        elif not metadata:
            access |= self.READ_DATA
        if write:
            access |= self.WRITE_DATA
        if delete:
            access |= self.DELETE
        options = self.OPEN_REPARSE | self.SYNCHRONOUS | (self.DIRECTORY if directory else self.NON_DIRECTORY)
        disposition = self.CREATE if exclusive else self.OPEN_IF if create else self.OPEN
        # 目录禁止被重命名；子项始终从句柄相对打开，不重新解释目录上的重解析点。
        sharing = self.SHARE_READ | (self.SHARE_WRITE if directory or shared_write or metadata else 0)
        if not directory and not shared_write:
            sharing |= self.SHARE_DELETE
        if exclusive:
            sharing = 0
        result, status = ctypes.c_void_p(), self.IOStatus()
        self.check_status(self.native.NtCreateFile(ctypes.byref(result), access, ctypes.byref(attributes),
            ctypes.byref(status), None, 0x80, sharing, disposition, options, None, 0))
        try:
            self.validate(result.value, directory=directory)
            return result.value
        except BaseException:
            self.close(result.value)
            raise

    def validate(self, handle, *, directory=False):
        info = self.FileInformation()
        if not self.kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if (self.kernel.GetFileType(handle) != 1
                or info.attributes & (self.REPARSE_ATTRIBUTE | self.DEVICE_ATTRIBUTE)
                or bool(info.attributes & self.DIRECTORY_ATTRIBUTE) != directory):
            raise SecureIOError('Windows 文件包含重解析点或不是要求的普通文件类型')

    def validate_volume(self, handle):
        filesystem = ctypes.create_unicode_buffer(32)
        if not self.kernel.GetVolumeInformationByHandleW(handle, None, 0, None, None, None,
                                                         filesystem, len(filesystem)):
            raise ctypes.WinError(ctypes.get_last_error())
        if filesystem.value != 'NTFS':
            raise SecureIOError('Windows 安全文件操作仅支持本地 NTFS 文件系统')

    def descriptor(self, handle, *, write=False):
        import msvcrt
        try:
            return msvcrt.open_osfhandle(handle, (os.O_RDWR if write else os.O_RDONLY) | os.O_BINARY)
        except BaseException:
            self.close(handle)
            raise

    def write(self, handle, contents):
        offset = 0
        while offset < len(contents):
            block = ctypes.create_string_buffer(contents[offset:offset + 1024 * 1024])
            written = ctypes.c_uint32()
            if not self.kernel.WriteFile(handle, block, len(block) - 1, ctypes.byref(written), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if not 0 < written.value <= len(block) - 1:
                raise OSError('Windows 文件写入未取得进展')
            offset += written.value
        if not self.kernel.FlushFileBuffers(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def replace(self, handle, parent, name):
        encoded = name.encode('utf-16-le')
        size = ctypes.sizeof(self.RenameInformation) + len(encoded)
        buffer = ctypes.create_string_buffer(size)
        info = self.RenameInformation.from_buffer(buffer)
        info.Flags, info.RootDirectory, info.FileNameLength = 0x3, parent, len(encoded)
        ctypes.memmove(ctypes.addressof(buffer) + self.RenameInformation.FileName.offset, encoded, len(encoded))
        status = self.IOStatus()
        # FileRenameInformationEx + POSIX 语义允许读取者继续持有旧记录句柄。
        # 不支持该原语的 Windows 版本安全失败，不降级为路径复制覆盖。
        self.check_status(self.native.NtSetInformationFile(handle, ctypes.byref(status), buffer, size, 65))

    def delete(self, handle):
        disposition, status = ctypes.c_ubyte(1), self.IOStatus()
        self.check_status(self.native.NtSetInformationFile(handle, ctypes.byref(status),
                                                           ctypes.byref(disposition), 1, 13))

    def close(self, handle):
        if not self.kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


class _WindowsDirectory:
    def __init__(self, path, *, api=None):
        self.api, self.handles = api or _WindowsAPI(), []
        path = _windows_parts(path)
        try:
            root = self.api.open(self.api.volume_root(path.drive), directory=True)
            self.handles.append(root)
            self.api.validate_volume(root)
            for part in path.parts[1:]:
                self.handles.append(self.api.open(part, self.handles[-1], directory=True))
        except BaseException:
            self.close()
            raise

    def open(self, name, *, write=False, create=False, exclusive=False, metadata=False):
        _windows_name(name)
        handle = self.api.open(name, self.handles[-1], write=write, create=create,
                               exclusive=exclusive, shared_write=write and not exclusive, metadata=metadata)
        return self.api.descriptor(handle, write=write)

    def write(self, name, contents):
        _windows_name(name)
        temporary = name + '.' + uuid4().hex + '.tmp'
        handle = self.api.open(temporary, self.handles[-1], write=True, create=True,
                               exclusive=True, delete=True)
        replaced = False
        try:
            self.api.write(handle, contents)
            self.api.replace(handle, self.handles[-1], name)
            replaced = True
        finally:
            try:
                if not replaced:
                    # 通过原句柄删除临时文件，避免错误路径清理删除了替换对象。
                    self.api.delete(handle)
            finally:
                self.api.close(handle)

    def unlink(self, name):
        handle = self.api.open(_windows_name(name), self.handles[-1], delete=True)
        try:
            self.api.delete(handle)
        finally:
            self.api.close(handle)

    def close(self):
        while self.handles:
            self.api.close(self.handles.pop())


class SecureDirectory(AbstractContextManager):
    """固定可信目录，所有方法只接受一个直接子文件名。

    lock 返回已获取的锁；占用时抛出 BlockingIOError。文件缺失保留
    FileNotFoundError，安全校验失败抛出 SecureIOError。调用方负责把
    内部异常转换为不泄漏本地路径的用户提示。
    """
    def __init__(self, path):
        self.path = _absolute_path(path)
        self._directory = _WindowsDirectory(self.path) if os.name == 'nt' else _PosixDirectory(self.path)

    def _backend(self):
        if self._directory is None:
            raise SecureIOError('安全目录已关闭')
        return self._directory

    def read_bytes(self, name, max_bytes=16 * 1024 * 1024):
        return _read_fd(self._backend().open(_name(name)), max_bytes)

    def read_json(self, name, max_bytes=16 * 1024 * 1024):
        return json.loads(self.read_bytes(name, max_bytes).decode('utf-8'))

    def write_json(self, name, value):
        name = _name(name)
        contents = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        # 已存在的链接或设备安全失败；检查后替换只更换目录项，不跟随末级链接。
        self.exists(name)
        self._backend().write(name, contents)

    def touch(self, name):
        descriptor = self._backend().open(_name(name), create=True, metadata=True)
        os.close(descriptor)

    def unlink(self, name, *, missing_ok=True):
        try:
            self._backend().unlink(_name(name))
        except FileNotFoundError:
            if not missing_ok:
                raise

    def exists(self, name):
        try:
            descriptor = self._backend().open(_name(name), metadata=True)
        except FileNotFoundError:
            return False
        os.close(descriptor)
        return True

    def lock(self, name, *, create=True):
        return _FileLock(self._backend().open(_name(name), write=True, create=create))

    def close(self):
        if self._directory is not None:
            directory, self._directory = self._directory, None
            directory.close()

    def __exit__(self, *args):
        self.close()


def read_regular_file(path, roots, max_bytes):
    """只读取可信根目录内的普通文件，并检查大小与读取期间的变化。"""
    path = _absolute_path(path)
    roots = tuple(_absolute_path(root) for root in roots)
    if os.name == 'nt':
        _windows_parts(path)
        # NTFS 的目录可以区分大小写；不以 WindowsPath 的大小写折叠授予访问。
        contained = any(path.parts[:len(root.parts)] == root.parts and len(path.parts) > len(root.parts)
                        for root in roots)
    else:
        contained = any(path != root and path.is_relative_to(root) for root in roots)
    if not contained:
        raise SecureIOError('文件不在可信目录中')
    with SecureDirectory(path.parent) as directory:
        return directory.read_bytes(path.name, max_bytes)
