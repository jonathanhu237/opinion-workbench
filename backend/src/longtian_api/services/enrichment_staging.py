"""Owned, descriptor-relative binary handoff from the product worker.

No constructor I/O, public paths, startup scans or recursive cleanup. Each scope
can remove only the directory it created, and only its flat opaque file names.
"""

import hashlib
import os
import stat
import struct
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from longtian_api.services.enrichment_models import (
    MAX_MANIFEST_BYTES,
    EnrichedContent,
    EnrichmentAsset,
    EnrichmentValidationError,
    ManifestDescriptor,
    decode_json_object,
    validate_handle,
)


class MediaStagingError(Exception):
    """Constant-only filesystem validation or ownership failure."""


@dataclass(frozen=True, slots=True)
class ValidatedMedia:
    asset_id: str
    mime_type: str
    data: bytes = field(repr=False)


def _directory_flags() -> int:
    if os.name != "posix":
        raise MediaStagingError
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_directory_path(path: Path) -> int:
    """Walk trusted absolute configuration without following any symlink."""
    if not path.is_absolute() or ".." in path.parts:
        raise MediaStagingError
    descriptor = os.open(path.anchor, _directory_flags())
    try:
        for part in path.parts[1:]:
            child = os.open(part, _directory_flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _private_directory(info: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise MediaStagingError


def _same_inode(first: os.stat_result, second: os.stat_result) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


class MediaSpool:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create_operation(self, request_id: UUID) -> "MediaOperation":
        """Create one new private operation, only after explicit admission."""
        if not isinstance(request_id, UUID) or request_id.version != 4:
            raise MediaStagingError
        root_fd = operation_fd = None
        try:
            parent_fd = _open_directory_path(self.root.parent)
            try:
                info = os.fstat(parent_fd)
                if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                    raise MediaStagingError
                try:
                    os.mkdir(self.root.name, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                root_fd = os.open(self.root.name, _directory_flags(), dir_fd=parent_fd)
                _private_directory(os.fstat(root_fd))
            finally:
                os.close(parent_fd)
            os.mkdir(request_id.hex, 0o700, dir_fd=root_fd)
            operation_fd = os.open(request_id.hex, _directory_flags(), dir_fd=root_fd)
            _private_directory(os.fstat(operation_fd))
            os.fsync(root_fd)
            operation = MediaOperation(self.root, request_id, root_fd, operation_fd)
            root_fd = operation_fd = None
            return operation
        except BaseException as error:
            # Allocation has not returned an owner to the service yet. Reclaim
            # only the empty directory whose descriptor proves our mkdir; a
            # replaced entry or a populated directory is never guessed cleanup.
            if root_fd is not None and operation_fd is not None:
                try:
                    original = os.fstat(operation_fd)
                    named = os.stat(
                        request_id.hex, dir_fd=root_fd, follow_symlinks=False
                    )
                    if (
                        stat.S_ISDIR(named.st_mode)
                        and _same_inode(original, named)
                        and not os.listdir(operation_fd)
                    ):
                        os.rmdir(request_id.hex, dir_fd=root_fd)
                except OSError:
                    pass
            if isinstance(error, (OSError, ValueError)):
                raise MediaStagingError from None
            raise
        finally:
            if operation_fd is not None:
                os.close(operation_fd)
            if root_fd is not None:
                os.close(root_fd)


class MediaOperation:
    def __init__(self, root: Path, request_id: UUID, root_fd: int, directory_fd: int):
        self.request_id = request_id
        self._root = root
        self._root_fd = root_fd
        self._directory_fd = directory_fd
        self._root_identity = os.fstat(root_fd)
        self._directory_identity = os.fstat(directory_fd)
        self._closed = False

    def _check_identity(self) -> None:
        if self._closed:
            raise MediaStagingError
        _private_directory(os.fstat(self._root_fd))
        _private_directory(os.fstat(self._directory_fd))
        parent_fd = _open_directory_path(self._root.parent)
        try:
            current_root = os.stat(
                self._root.name, dir_fd=parent_fd, follow_symlinks=False
            )
            current_operation = os.stat(
                self.request_id.hex, dir_fd=self._root_fd, follow_symlinks=False
            )
            if (
                not _same_inode(current_root, self._root_identity)
                or not _same_inode(current_operation, self._directory_identity)
                or not stat.S_ISDIR(current_root.st_mode)
                or not stat.S_ISDIR(current_operation.st_mode)
            ):
                raise MediaStagingError
        finally:
            os.close(parent_fd)

    def _read_file(
        self, handle: str, byte_size: int, digest: str, maximum: int
    ) -> bytes:
        try:
            validate_handle(handle)
            self._check_identity()
            if not 1 <= byte_size <= maximum:
                raise MediaStagingError
            descriptor = os.open(
                handle,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self._directory_fd,
            )
            try:
                initial = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(initial.st_mode)
                    or initial.st_uid != os.geteuid()
                    or stat.S_IMODE(initial.st_mode) != 0o600
                    or initial.st_nlink != 1
                    or initial.st_size != byte_size
                ):
                    raise MediaStagingError
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    data = source.read(byte_size + 1)
                final = os.fstat(descriptor)
                named = os.stat(
                    handle, dir_fd=self._directory_fd, follow_symlinks=False
                )
                if (
                    len(data) != byte_size
                    or hashlib.sha256(data).hexdigest() != digest
                    or not _same_inode(final, named)
                    or (initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns)
                    != (final.st_size, final.st_mtime_ns, final.st_ctime_ns)
                ):
                    raise MediaStagingError
            finally:
                os.close(descriptor)
            self._check_identity()
            return data
        except (OSError, ValueError, EnrichmentValidationError):
            raise MediaStagingError from None

    def read_manifest(self, descriptor: ManifestDescriptor) -> dict[str, object]:
        try:
            return decode_json_object(
                self._read_file(
                    descriptor.handle,
                    descriptor.byte_size,
                    descriptor.sha256,
                    MAX_MANIFEST_BYTES,
                )
            )
        except EnrichmentValidationError:
            raise MediaStagingError from None

    def read_assets(
        self, content: EnrichedContent, maximum: int
    ) -> tuple[ValidatedMedia, ...]:
        media = []
        total = 0
        for asset in content.assets:
            if asset.status != "ready":
                continue
            if (
                asset.blob_ref is None
                or asset.byte_size is None
                or asset.sha256 is None
            ):
                raise MediaStagingError
            data = self._read_file(
                asset.blob_ref, asset.byte_size, asset.sha256, maximum
            )
            total += len(data)
            if total > maximum or not _valid_media_bytes(data, asset):
                raise MediaStagingError
            media.append(ValidatedMedia(asset.asset_id, asset.mime_type or "", data))
        return tuple(media)

    def cleanup(self) -> None:
        """Remove flat entries only while the original directory identity holds."""
        if self._closed:
            return
        try:
            self._check_identity()
            names = os.listdir(self._directory_fd)
            if len(names) > 128:
                raise MediaStagingError
            for name in names:
                handle = (
                    name[1:-5]
                    if name.startswith(".") and name.endswith(".part")
                    else name
                )
                validate_handle(handle)
                info = os.stat(name, dir_fd=self._directory_fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    raise MediaStagingError
            for name in names:
                os.unlink(name, dir_fd=self._directory_fd)
            self._check_identity()
            os.rmdir(self.request_id.hex, dir_fd=self._root_fd)
            os.fsync(self._root_fd)
        except (OSError, ValueError, EnrichmentValidationError):
            raise MediaStagingError from None
        finally:
            self._closed = True
            os.close(self._directory_fd)
            os.close(self._root_fd)


def _valid_media_bytes(data: bytes, asset: EnrichmentAsset) -> bool:
    if asset.kind == "video":
        return (
            asset.mime_type == "video/mp4"
            and len(data) >= 24
            and data[4:8] == b"ftyp"
            and 16 <= int.from_bytes(data[:4], "big") <= len(data)
            and data[8:12]
            in {b"isom", b"iso2", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1"}
        )
    try:
        if asset.mime_type == "image/png":
            if (
                len(data) < 45
                or data[:8] != b"\x89PNG\r\n\x1a\n"
                or data[8:16] != b"\x00\x00\x00\rIHDR"
                or data[-12:] != b"\x00\x00\x00\x00IEND\xaeB`\x82"
            ):
                return False
            dimensions = struct.unpack(">II", data[16:24])
        elif asset.mime_type == "image/webp":
            if (
                len(data) < 30
                or data[:4] != b"RIFF"
                or data[8:12] != b"WEBP"
                or int.from_bytes(data[4:8], "little") + 8 != len(data)
            ):
                return False
            if data[12:16] == b"VP8X" and not data[20] & 2:
                dimensions = (
                    1 + int.from_bytes(data[24:27], "little"),
                    1 + int.from_bytes(data[27:30], "little"),
                )
            elif data[12:16] == b"VP8L" and data[20] == 0x2F:
                bits = int.from_bytes(data[21:25], "little")
                dimensions = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
            elif data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
                dimensions = (
                    int.from_bytes(data[26:28], "little") & 0x3FFF,
                    int.from_bytes(data[28:30], "little") & 0x3FFF,
                )
            else:
                return False
        elif asset.mime_type == "image/jpeg":
            dimensions = _jpeg_dimensions(data)
        else:
            return False
        return dimensions == (asset.width, asset.height)
    except (ValueError, IndexError, struct.error):
        return False


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError
    offset = 2
    while offset + 4 < len(data):
        if data[offset] != 0xFF:
            raise ValueError
        marker = data[offset + 1]
        if marker == 0xFF:
            offset += 1
            continue
        size = int.from_bytes(data[offset + 2 : offset + 4], "big")
        if size < 2 or offset + size + 2 > len(data):
            raise ValueError
        if marker in {0xC0, 0xC1, 0xC2} and size >= 8:
            return (
                int.from_bytes(data[offset + 7 : offset + 9], "big"),
                int.from_bytes(data[offset + 5 : offset + 7], "big"),
            )
        offset += size + 2
    raise ValueError
