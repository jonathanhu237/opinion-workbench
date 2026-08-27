"""POSIX permission-protected plaintext files, not an encrypted vault.

All access is relative to no-follow directory descriptors. Never scan runtime or
delete unreferenced files: after a crash an orphan is safer than guessed cleanup.
"""

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
