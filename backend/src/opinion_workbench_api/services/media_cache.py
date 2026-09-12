"""Project-owned, bounded original cache. Reads never download or repair files."""

import fcntl
import hashlib
import os
import stat
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

from opinion_workbench_api.repositories.analysis_shared import AnalysisRepository
from opinion_workbench_api.services.enrichment_models import (
    EnrichedContent,
    validate_handle,
)
from opinion_workbench_api.services.enrichment_staging import (
    MediaStagingError,
    _directory_flags,
    _open_directory_path,
    _private_directory,
    _same_inode,
    _valid_media_bytes,
)


class CacheUnavailable(Exception):
    pass


class CacheLease:
    def __init__(self, descriptor=None, data=None):
        self.descriptor = descriptor
        self.data = data or {}

    def close(self):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
        self.data.clear()


class MediaCache(AnalysisRepository):
    def __init__(self, database, *, clock=time.time):
        super().__init__(database)
        self.root = database.path.parent / "original-media"
        self.clock = clock
        self._lock = threading.RLock()
        from opinion_workbench_api.services.media_retention import MediaRetention

        self.retention = MediaRetention(self)

    def _check_root(self, descriptor):
        current = _open_directory_path(self.root)
        try:
            _private_directory(os.fstat(current))
            if not _same_inode(os.fstat(descriptor), os.fstat(current)):
                raise CacheUnavailable
        finally:
            os.close(current)

    def _open(self, *, create=False, exclusive=False):
        descriptor = None
        try:
            with self.connection(write=create) as connection:
                owner = connection.execute("SELECT * FROM media_cache_owner").fetchone()
                if owner is None:
                    if not create:
                        return None
                    parent = _open_directory_path(self.root.parent)
                    try:
                        info = os.fstat(parent)
                        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                            raise CacheUnavailable
                        # Never adopt a pre-existing directory, even if empty.
                        os.mkdir(self.root.name, 0o700, dir_fd=parent)
                        descriptor = os.open(
                            self.root.name, _directory_flags(), dir_fd=parent
                        )
                        info = os.fstat(descriptor)
                        connection.execute(
                            "INSERT INTO media_cache_owner VALUES (1,?,?)",
                            (info.st_dev, info.st_ino),
                        )
                        os.fsync(parent)
                    finally:
                        os.close(parent)
                else:
                    descriptor = _open_directory_path(self.root)
                    info = os.fstat(descriptor)
                    if (info.st_dev, info.st_ino) != (owner["device"], owner["inode"]):
                        raise CacheUnavailable
                _private_directory(os.fstat(descriptor))
            fcntl.flock(
                descriptor,
                (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB,
            )
            self._check_root(descriptor)
            result, descriptor = descriptor, None
            return result
        except (OSError, MediaStagingError):
            raise CacheUnavailable from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @contextmanager
    def _owned(self, *, create=False, exclusive=False):
        descriptor = self._open(create=create, exclusive=exclusive)
        try:
            yield descriptor
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _read(self, descriptor, row):
        if descriptor is None:
            return "missing", None
        if row["state"] != "ready":
            return ("cleared" if row["state"] == "cleared" else "unavailable"), None
        fd = None
        try:
            self._check_root(descriptor)
            validate_handle(row["handle"])
            fd = os.open(
                row["handle"],
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=descriptor,
            )
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != (row["device"], row["inode"])
                or info.st_size != row["byte_size"]
            ):
                return "corrupt", None
            with os.fdopen(fd, "rb", closefd=False) as file:
                raw = file.read(row["byte_size"] + 1)
            after = os.fstat(fd)
            self._check_root(descriptor)
            if (
                len(raw) != row["byte_size"]
                or hashlib.sha256(raw).hexdigest() != row["sha256"]
                or info.st_mtime_ns != after.st_mtime_ns
                or info.st_ctime_ns != after.st_ctime_ns
            ):
                return "corrupt", None
            return "cached", raw
        except FileNotFoundError:
            return "missing", None
        except (OSError, MediaStagingError, CacheUnavailable):
            return "unavailable", None
        finally:
            if fd is not None:
                os.close(fd)

    def save(self, content_id, content, media):
        blobs = {blob.asset_id: blob for blob in media}
        assets = [asset for asset in content.assets if asset.status == "ready"]
        if not assets:
            return True
        try:
            with self._lock, self._owned(create=True, exclusive=True) as descriptor:
                with self.connection() as connection:
                    existing = {
                        row[0]
                        for row in connection.execute(
                            "SELECT sha256 FROM media_cache_entries WHERE state='ready'"
                        )
                    }
                reserve = sum(
                    {
                        asset.sha256: asset.byte_size
                        for asset in assets
                        if asset.sha256 not in existing
                    }.values()
                )
                self.retention.collect_locked(
                    descriptor,
                    reserve=reserve,
                    protect={asset.sha256 for asset in assets},
                )
                for asset in assets:
                    blob = blobs.get(asset.asset_id)
                    if (
                        blob is None
                        or blob.mime_type != asset.mime_type
                        or len(blob.data) != asset.byte_size
                        or hashlib.sha256(blob.data).hexdigest() != asset.sha256
                        or not _valid_media_bytes(blob.data, asset)
                    ):
                        raise CacheUnavailable
                    self._save_one(descriptor, content_id, asset, blob.data)
            return True
        except (OSError, MediaStagingError, CacheUnavailable):
            # The verified temporary input is still usable when originals cannot
            # be retained. Never turn cache failure into fake acquired evidence.
            return False

    def _save_one(self, descriptor, content_id, asset, data):
        with self.connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM media_cache_entries WHERE sha256=?", (asset.sha256,)
            ).fetchone()
            if row is not None and row["state"] != "cleared":
                state, _ = self._read(descriptor, row)
                if state != "cached":
                    # Replacement/removal needs the cleanup policy; no overwrite.
                    raise CacheUnavailable
                connection.execute(
                    "INSERT OR IGNORE INTO media_cache_bindings VALUES (?,?)",
                    (content_id, asset.sha256),
                )
                return
            known = {
                r[0]
                for r in connection.execute(
                    "SELECT handle FROM media_cache_entries WHERE state!='cleared'"
                )
            }
            if len(known) >= 10000 or set(os.listdir(descriptor)) - known:
                raise CacheUnavailable
            used = connection.execute(
                """SELECT COALESCE(SUM(byte_size),0) FROM media_cache_entries
                WHERE state!='cleared'"""
            ).fetchone()[0]
            capacity = connection.execute(
                "SELECT capacity_mib*1048576 FROM media_cache_policy"
            ).fetchone()[0]
            if used + len(data) > capacity:
                raise CacheUnavailable
            handle = uuid4().hex
            connection.execute(
                """INSERT INTO media_cache_entries
                VALUES (?,?,?,?,?,'pending',NULL,NULL)
                ON CONFLICT(sha256) DO UPDATE SET handle=excluded.handle,
                byte_size=excluded.byte_size,mime_type=excluded.mime_type,
                created_at=excluded.created_at,state='pending',device=NULL,inode=NULL""",
                (asset.sha256, handle, len(data), asset.mime_type, int(self.clock())),
            )
            connection.execute(
                "INSERT OR IGNORE INTO media_cache_bindings VALUES (?,?)",
                (content_id, asset.sha256),
            )
        # Reservation is durable before the file exists. A crash leaves a known,
        # bounded pending entry, not an invisible file or a false ready record.
        self._check_root(descriptor)
        fd = os.open(
            handle,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        try:
            info = os.fstat(fd)
            with self.connection(write=True) as connection:
                connection.execute(
                    """UPDATE media_cache_entries SET device=?,inode=?
                    WHERE sha256=? AND state='pending'""",
                    (info.st_dev, info.st_ino, asset.sha256),
                )
            with os.fdopen(fd, "wb", closefd=False) as file:
                file.write(data)
                file.flush()
                os.fsync(fd)
            info = os.fstat(fd)
            self._check_root(descriptor)
            os.fsync(descriptor)
            with self.connection(write=True) as connection:
                connection.execute(
                    """UPDATE media_cache_entries SET state='ready',device=?,inode=?
                    WHERE sha256=? AND state='pending'""",
                    (info.st_dev, info.st_ino, asset.sha256),
                )
        finally:
            os.close(fd)

    def _rows(self, connection, content_id):
        return {
            row["sha256"]: row
            for row in connection.execute(
                """SELECT e.* FROM media_cache_entries e JOIN media_cache_bindings b
            ON b.sha256=e.sha256 WHERE b.content_id=?""",
                (content_id,),
            )
        }

    def remove_owned(self, descriptor, row):
        """Called under the exclusive cache lock, only for a recorded inode."""
        self._check_root(descriptor)
        validate_handle(row["handle"])
        try:
            info = os.stat(row["handle"], dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return False, 0
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or (info.st_dev, info.st_ino) != (row["device"], row["inode"])
        ):
            raise CacheUnavailable
        self._check_root(descriptor)
        os.unlink(row["handle"], dir_fd=descriptor)
        os.fsync(descriptor)
        return True, info.st_size

    def describe(self, content_id, assets):
        with self.connection() as connection:
            rows = self._rows(connection, content_id)
        descriptor = None
        try:
            try:
                descriptor = self._open()
                available = True
            except CacheUnavailable:
                available = False
            items = []
            for asset in assets:
                row = rows.get(asset.sha256)
                state = (
                    "not_acquired"
                    if asset.status != "ready"
                    else "not_stored"
                    if row is None
                    else "cleared"
                    if row["state"] == "cleared"
                    else self._read(descriptor, row)[0]
                    if available
                    else "unavailable"
                )
                items.append(
                    dict(
                        position=asset.position,
                        kind=asset.kind,
                        state=state,
                        byte_size=asset.byte_size if state == "cached" else None,
                    )
                )
            return {"items": items}
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def acquire(self, content_id, assets):
        try:
            descriptor = self._open()
        except CacheUnavailable:
            return CacheLease()
        lease = CacheLease(descriptor)
        try:
            with self.connection() as connection:
                rows = self._rows(connection, content_id)
            for asset in assets:
                row = rows.get(asset.sha256)
                if asset.status == "ready" and row is not None:
                    state, data = self._read(descriptor, row)
                    if (
                        state == "cached"
                        and row["mime_type"] == asset.mime_type
                        and row["byte_size"] == asset.byte_size
                    ):
                        lease.data[asset.position] = data
            return lease
        except BaseException:
            lease.close()
            raise

    def material(self, attempt):
        if attempt.input_fingerprint is None:
            return None
        with self.connection() as connection:
            row = connection.execute(
                """SELECT content_json FROM content_materials
                WHERE content_id=? AND input_fingerprint=?""",
                (attempt.source.result_id, attempt.input_fingerprint),
            ).fetchone()
            return (
                EnrichedContent.model_validate_json(row[0]) if row and row[0] else None
            )
