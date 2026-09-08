"""One-time removal of directories owned by the retired media pipeline."""

import logging
import os
import re
import stat
from errno import EEXIST, ELOOP, ENOENT, ENOTDIR, ENOTEMPTY
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

MANAGED_MEDIA_ROOTS = ("original-media", "media")
_HANDLE = re.compile(r"[0-9a-f]{32}(?:\.part)?\Z")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_NON_RETRYABLE_FILESYSTEM_ERRORS = {EEXIST, ELOOP, ENOENT, ENOTDIR, ENOTEMPTY}


class _OwnershipMismatchError(OSError):
    """The named managed root no longer refers to the verified directory."""


def purge_managed_media(runtime_root: Path, *, connection=None) -> dict[str, object]:
    """Remove only media files whose project ownership can be proved.

    ``original-media`` is checked against the cache table rows while they are
    still available during the v38 migration. The temporary ``media`` spool is
    checked against its UUID operation directories and opaque file names. Any
    mixed or suspicious root is left in place and reported.
    """

    result = {
        "removed_roots": [],
        "removed_files": 0,
        "errors": [],
        "retryable_errors": [],
        "complete": True,
    }
    _purge_original_media(runtime_root / "original-media", connection, result)
    _purge_spool(runtime_root / "media", result)
    if result["errors"]:
        result["complete"] = False
        logger.warning(
            "Retired media cleanup incomplete: %s", "; ".join(result["errors"])
        )
    return result


def _private_root(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o700
    )


def _is_private_directory(info: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o700
    )


def _is_empty(descriptor: int) -> bool:
    with os.scandir(descriptor) as entries:
        return next(entries, None) is None


def _remove_root(path: Path, descriptor: int, identity: os.stat_result) -> None:
    """Remove ``path`` only while its named entry still names ``descriptor``."""

    parent = os.open(path.parent, _DIRECTORY_FLAGS)
    try:
        named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (identity.st_dev, identity.st_ino):
            raise _OwnershipMismatchError("managed root was replaced")
        os.rmdir(path.name, dir_fd=parent)
    finally:
        os.close(parent)


def _record_error(result, name: str, message: str, *, retryable: bool = False) -> None:
    error = f"{name}: {message}"
    result["errors"].append(error)
    if retryable:
        result["retryable_errors"].append(error)


def _record_filesystem_error(result, name: str, error: OSError) -> None:
    _record_error(
        result,
        name,
        str(error),
        retryable=getattr(error, "errno", None)
        not in _NON_RETRYABLE_FILESYSTEM_ERRORS,
    )


def _purge_original_media(path: Path, connection, result) -> None:
    try:
        present = path.exists() or path.is_symlink()
    except OSError as error:
        _record_filesystem_error(result, "original-media", error)
        return
    if not present:
        return
    try:
        private = _private_root(path)
    except OSError as error:
        _record_filesystem_error(result, "original-media", error)
        return
    if not private:
        _record_error(result, "original-media", "unmanaged root")
        return
    if connection is None:
        _record_error(result, "original-media", "cache ownership unavailable")
        return
    try:
        owner = connection.execute("SELECT * FROM media_cache_owner").fetchone()
        rows = connection.execute(
            "SELECT handle,device,inode FROM media_cache_entries"
        ).fetchall()
    except Exception:
        _record_error(result, "original-media", "cache ownership unavailable")
        return
    try:
        descriptor = os.open(path, _DIRECTORY_FLAGS)
    except FileNotFoundError:
        return
    except OSError as error:
        _record_filesystem_error(result, "original-media", error)
        return
    try:
        info = os.fstat(descriptor)
        if not _is_private_directory(info):
            _record_error(result, "original-media", "unmanaged root")
            return
        if owner is None or (info.st_dev, info.st_ino) != (
            owner["device"],
            owner["inode"],
        ):
            _record_error(result, "original-media", "ownership mismatch")
            return
        known = {row["handle"]: row for row in rows}
        removable = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                row = known.get(entry.name)
                if row is None:
                    _record_error(
                        result, "original-media", f"unmanaged entry: {entry.name}"
                    )
                    continue
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    _record_error(
                        result, "original-media", f"unmanaged entry: {entry.name}"
                    )
                    continue
                file_info = entry.stat(follow_symlinks=False)
                if (
                    file_info.st_uid != os.geteuid()
                    or stat.S_IMODE(file_info.st_mode) != 0o600
                    or row["device"] is None
                    or row["inode"] is None
                    or (file_info.st_dev, file_info.st_ino)
                    != (row["device"], row["inode"])
                ):
                    _record_error(
                        result, "original-media", f"ownership mismatch: {entry.name}"
                    )
                    continue
                removable.append(entry.name)
        for name in removable:
            try:
                os.unlink(name, dir_fd=descriptor)
            except FileNotFoundError:
                # A concurrent cleanup already removed this owned inode.
                continue
            except OSError as error:
                _record_error(result, "original-media", str(error), retryable=True)
                continue
            result["removed_files"] += 1
        if _is_empty(descriptor):
            try:
                _remove_root(path, descriptor, info)
            except FileNotFoundError:
                pass
            except _OwnershipMismatchError as error:
                _record_error(result, "original-media", str(error))
            except OSError as error:
                _record_filesystem_error(result, "original-media", error)
            else:
                result["removed_roots"].append("original-media")
    except OSError as error:
        _record_filesystem_error(result, "original-media", error)
    finally:
        os.close(descriptor)


def _purge_spool(path: Path, result) -> None:
    try:
        present = path.exists() or path.is_symlink()
    except OSError as error:
        _record_filesystem_error(result, "media", error)
        return
    if not present:
        return
    try:
        private = _private_root(path)
    except OSError as error:
        _record_filesystem_error(result, "media", error)
        return
    if not private:
        _record_error(result, "media", "unmanaged root")
        return
    try:
        descriptor = os.open(path, _DIRECTORY_FLAGS)
    except FileNotFoundError:
        return
    except OSError as error:
        _record_filesystem_error(result, "media", error)
        return
    try:
        info = os.fstat(descriptor)
        if not _is_private_directory(info):
            _record_error(result, "media", "unmanaged root")
            return
        with os.scandir(descriptor) as operations:
            for operation in operations:
                if (
                    operation.is_symlink()
                    or not operation.is_dir(follow_symlinks=False)
                    or not _is_uuid4_handle(operation.name)
                ):
                    _record_error(
                        result, "media", f"unmanaged operation: {operation.name}"
                    )
                    continue
                try:
                    operation_fd = os.open(
                        operation.name, _DIRECTORY_FLAGS, dir_fd=descriptor
                    )
                except FileNotFoundError:
                    continue
                except OSError as error:
                    _record_error(
                        result,
                        "media",
                        f"operation ownership mismatch: {operation.name}",
                        retryable=error.errno not in _NON_RETRYABLE_FILESYSTEM_ERRORS,
                    )
                    continue
                try:
                    op_info = os.fstat(operation_fd)
                    if not _is_private_directory(op_info):
                        _record_error(
                            result,
                            "media",
                            f"operation ownership mismatch: {operation.name}",
                        )
                        continue
                    removable = []
                    with os.scandir(operation_fd) as files:
                        for entry in files:
                            if (
                                entry.is_symlink()
                                or not entry.is_file(follow_symlinks=False)
                                or _HANDLE.fullmatch(entry.name) is None
                            ):
                                _record_error(
                                    result,
                                    "media",
                                    f"unmanaged staged file: {entry.name}",
                                )
                                continue
                            file_info = entry.stat(follow_symlinks=False)
                            if (
                                file_info.st_uid != os.geteuid()
                                or stat.S_IMODE(file_info.st_mode) != 0o600
                            ):
                                _record_error(
                                    result,
                                    "media",
                                    f"staged file ownership mismatch: {entry.name}",
                                )
                                continue
                            removable.append(entry.name)
                    for name in removable:
                        try:
                            os.unlink(name, dir_fd=operation_fd)
                        except FileNotFoundError:
                            continue
                        except OSError as error:
                            _record_error(result, "media", str(error), retryable=True)
                            continue
                        result["removed_files"] += 1
                    if _is_empty(operation_fd):
                        try:
                            os.rmdir(operation.name, dir_fd=descriptor)
                        except FileNotFoundError:
                            pass
                        except OSError as error:
                            if getattr(error, "errno", None) not in {EEXIST, ENOTEMPTY}:
                                _record_error(
                                    result, "media", str(error), retryable=True
                                )
                finally:
                    os.close(operation_fd)
        if _is_empty(descriptor):
            try:
                _remove_root(path, descriptor, info)
            except FileNotFoundError:
                pass
            except _OwnershipMismatchError as error:
                _record_error(result, "media", str(error))
            except OSError as error:
                _record_filesystem_error(result, "media", error)
            else:
                result["removed_roots"].append("media")
    except OSError as error:
        _record_filesystem_error(result, "media", error)
    finally:
        os.close(descriptor)


def _is_uuid4_handle(value: str) -> bool:
    try:
        return UUID(hex=value).version == 4
    except (ValueError, AttributeError):
        return False
