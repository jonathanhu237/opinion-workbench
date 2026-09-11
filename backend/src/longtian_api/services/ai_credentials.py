"""POSIX permission-protected plaintext files, not an encrypted vault.

All access is relative to no-follow directory descriptors. Never scan runtime or
delete unreferenced files: after a crash an orphan is safer than guessed cleanup.
"""

import ctypes
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import SecretStr

MAX_KEY_BYTES = 4096
_REFERENCE = re.compile(r"[0-9a-f]{32}\.key\Z")


class AICredentialError(Exception):
    pass


def valid_api_key(value: str) -> bool:
    return 1 <= len(value) <= MAX_KEY_BYTES and all(33 <= ord(c) <= 126 for c in value)


class AICredentialStore:
    def __init__(self, runtime: Path) -> None:
        self._runtime = runtime

    @contextmanager
    def _directory(self, *, create: bool = False) -> Iterator[int]:
        descriptors: list[int] = []
        try:
            if os.name != "posix":
                raise AICredentialError()
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            runtime_fd = os.open(self._runtime, flags)
            descriptors.append(runtime_fd)
            runtime_info = os.fstat(runtime_fd)
            if runtime_info.st_uid != os.geteuid() or runtime_info.st_mode & 0o022:
                raise AICredentialError()
            parent_fd = runtime_fd
            for name in ("secrets", "ai"):
                if create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                    except FileExistsError:
                        pass
                child_fd = os.open(name, flags, dir_fd=parent_fd)
                descriptors.append(child_fd)
                info = os.fstat(child_fd)
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise AICredentialError()
                parent_fd = child_fd
            yield parent_fd
        except OSError:
            raise AICredentialError() from None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def create(self, key: SecretStr) -> str:
        value = key.get_secret_value()
        if not valid_api_key(value):
            raise AICredentialError()
        if os.name == "nt":
            return self._create_windows(value)
        reference = f"{uuid4().hex}.key"
        with self._directory(create=True) as directory:
            descriptor = os.open(
                reference,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb", closefd=False) as output:
                    output.write(value.encode("ascii"))
                    output.flush()
                    os.fsync(descriptor)
                os.fsync(directory)
            except BaseException:
                os.unlink(reference, dir_fd=directory)
                raise
            finally:
                os.close(descriptor)
        return reference

    def read(self, reference: str) -> SecretStr:
        self._validate_reference(reference)
        if os.name == "nt":
            return self._read_windows(reference)
        with self._directory() as directory:
            descriptor = os.open(
                reference,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
            try:
                self._validate_file(os.fstat(descriptor))
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    data = source.read(MAX_KEY_BYTES + 1)
            finally:
                os.close(descriptor)
        try:
            value = data.decode("ascii")
        except UnicodeError:
            raise AICredentialError() from None
        if not valid_api_key(value):
            raise AICredentialError()
        return SecretStr(value)

    def remove(self, reference: str) -> None:
        """Remove exactly one superseded/rolled-back owned regular file."""
        self._validate_reference(reference)
        if os.name == "nt":
            self._remove_windows(reference)
            return
        with self._directory() as directory:
            self._validate_file(
                os.stat(reference, dir_fd=directory, follow_symlinks=False)
            )
            os.unlink(reference, dir_fd=directory)
            os.fsync(directory)

    @staticmethod
    def _validate_reference(reference: str) -> None:
        if _REFERENCE.fullmatch(reference) is None:
            raise AICredentialError()

    @staticmethod
    def _validate_file(info: os.stat_result) -> None:
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 1 <= info.st_size <= MAX_KEY_BYTES
        ):
            raise AICredentialError()

    @contextmanager
    def _windows_directory(self, *, create: bool = False) -> Iterator[Path]:
        """Open the Windows credential directory projection.

        Windows does not expose the POSIX descriptor and mode guarantees used
        by the original store.  The files below are therefore encrypted with
        the current user's DPAPI key, and path traversal/reparse-point checks
        still make the storage location deterministic.  A plaintext fallback
        is deliberately not provided when DPAPI is unavailable.
        """

        if os.name != "nt":
            raise AICredentialError()
        runtime = self._runtime.absolute()
        try:
            if runtime.exists() and (
                _windows_reparse_point(runtime) or not runtime.is_dir()
            ):
                raise AICredentialError()
            if create:
                runtime.mkdir(parents=True, exist_ok=True)
            secrets = runtime / "secrets"
            ai = secrets / "ai"
            for directory in (secrets, ai):
                if directory.exists() and (
                    _windows_reparse_point(directory) or not directory.is_dir()
                ):
                    raise AICredentialError()
                if create:
                    directory.mkdir(exist_ok=True)
            if not ai.is_dir():
                raise AICredentialError()
            yield ai
        except (OSError, ValueError):
            raise AICredentialError() from None

    def _create_windows(self, value: str) -> str:
        reference = f"{uuid4().hex}.key"
        encrypted = _protect_windows(value.encode("ascii"))
        with self._windows_directory(create=True) as directory:
            path = directory / reference
            try:
                with path.open("xb") as output:
                    output.write(encrypted)
                    output.flush()
                    os.fsync(output.fileno())
            except (OSError, ValueError):
                raise AICredentialError() from None
        return reference

    def _read_windows(self, reference: str) -> SecretStr:
        with self._windows_directory() as directory:
            path = directory / reference
            try:
                if _windows_reparse_point(path) or not path.is_file():
                    raise AICredentialError()
                data = path.read_bytes()
            except (OSError, ValueError):
                raise AICredentialError() from None
        value = _unprotect_windows(data)
        try:
            decoded = value.decode("ascii")
        except UnicodeError:
            raise AICredentialError() from None
        if not valid_api_key(decoded):
            raise AICredentialError()
        return SecretStr(decoded)

    def _remove_windows(self, reference: str) -> None:
        with self._windows_directory() as directory:
            path = directory / reference
            try:
                if _windows_reparse_point(path) or not path.is_file():
                    raise AICredentialError()
                path.unlink()
            except (OSError, ValueError):
                raise AICredentialError() from None


_DPAPI_PREFIX = b"LONGTIAN-DPAPI-1\x00"


def _windows_reparse_point(path: Path) -> bool:
    """Reject Windows links/junctions without following their target."""

    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False
    except OSError:
        return True


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _protect_windows(data: bytes) -> bytes:
    """Encrypt one credential using the current Windows user's DPAPI key."""

    if os.name != "nt":
        raise AICredentialError()
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        input_blob = _DataBlob(len(data), source)
        output_blob = _DataBlob()
        flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
        if not crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        ):
            raise AICredentialError()
        try:
            encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)
        return _DPAPI_PREFIX + encrypted
    except (AttributeError, OSError, ValueError, ctypes.ArgumentError):
        raise AICredentialError() from None


def _unprotect_windows(data: bytes) -> bytes:
    """Decrypt a DPAPI credential, rejecting all other on-disk formats."""

    if os.name != "nt" or not data.startswith(_DPAPI_PREFIX):
        raise AICredentialError()
    encrypted = data[len(_DPAPI_PREFIX) :]
    if not encrypted or len(encrypted) > MAX_KEY_BYTES * 4:
        raise AICredentialError()
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        source = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
        input_blob = _DataBlob(len(encrypted), source)
        output_blob = _DataBlob()
        flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
        if not crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        ):
            raise AICredentialError()
        try:
            value = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)
        if not 1 <= len(value) <= MAX_KEY_BYTES:
            raise AICredentialError()
        return value
    except (AttributeError, OSError, ValueError, ctypes.ArgumentError):
        raise AICredentialError() from None
