"""Retention policy for owned originals, separate from immutable evidence."""

import asyncio
import os

from opinion_workbench_api.services.analysis_errors import AnalysisError
from opinion_workbench_api.services.enrichment_staging import MediaStagingError
from opinion_workbench_api.services.media_cache import CacheUnavailable
from opinion_workbench_api.services.settled_tasks import database_call, settle


class MediaRetention:
    def __init__(self, cache):
        self.cache = cache
        self._runner = None

    def read(self):
        with self.cache.connection() as connection:
            policy = dict(
                connection.execute(
                    "SELECT retention_days,capacity_mib,revision "
                    "FROM media_cache_policy"
                ).fetchone()
            )
            counts = connection.execute(
                """SELECT COALESCE(SUM(byte_size),0),COUNT(*),
                COALESCE(SUM(state='pending'),0) FROM media_cache_entries
                WHERE state!='cleared'"""
            ).fetchone()
            return dict(
                policy,
                reserved_bytes=counts[0],
                files=counts[1],
                pending_files=counts[2],
            )

    def update(self, payload):
        with self.cache._lock:
            with self.cache.connection(write=True) as connection:
                changed = connection.execute(
                    """UPDATE media_cache_policy SET
                    retention_days=?,capacity_mib=?,revision=revision+1
                    WHERE id=1 AND revision=?""",
                    (
                        payload.retention_days,
                        payload.capacity_mib,
                        payload.expected_revision,
                    ),
                )
                if changed.rowcount != 1:
                    raise AnalysisError("media_cache_policy_conflict")
            cleanup = self.collect()
            return {"policy": self.read(), "cleanup": cleanup}

    def clean(self, expected_revision):
        with self.cache._lock:
            if self.read()["revision"] != expected_revision:
                raise AnalysisError("media_cache_policy_conflict")
            return {"cleanup": self.collect(), "policy": self.read()}

    def collect(self):
        try:
            with self.cache._lock, self.cache._owned(exclusive=True) as descriptor:
                return self.collect_locked(descriptor)
        except (OSError, MediaStagingError, CacheUnavailable):
            return {"removed_files": 0, "removed_bytes": 0, "deferred": True}

    def collect_locked(self, descriptor, *, reserve=0, protect=frozenset()):
        result = {"removed_files": 0, "removed_bytes": 0, "deferred": False}
        if descriptor is None:
            return result
        with self.cache.connection(write=True) as connection:
            policy = connection.execute("SELECT * FROM media_cache_policy").fetchone()
            capacity = policy["capacity_mib"] * 1048576
            if reserve > capacity:
                return dict(result, deferred=True)
            rows = connection.execute(
                """SELECT * FROM media_cache_entries WHERE state!='cleared'
                ORDER BY created_at,sha256"""
            ).fetchall()
            names = {row["handle"] for row in rows}
            if set(os.listdir(descriptor)) - names:
                return dict(result, deferred=True)
            used = sum(row["byte_size"] for row in rows)
            cutoff = int(self.cache.clock()) - policy["retention_days"] * 86400
            ordered = sorted(
                rows,
                key=lambda row: (
                    not (row["created_at"] <= cutoff or row["state"] == "pending"),
                    row["created_at"],
                    row["sha256"],
                ),
            )
            for row in ordered:
                if row["sha256"] in protect:
                    continue
                if (
                    row["state"] != "pending"
                    and row["created_at"] > cutoff
                    and used + reserve <= capacity
                ):
                    continue
                try:
                    deleted, size = self.cache.remove_owned(descriptor, row)
                except (OSError, MediaStagingError, CacheUnavailable):
                    result["deferred"] = True
                    continue
                connection.execute(
                    "UPDATE media_cache_entries SET state='cleared' WHERE sha256=?",
                    (row["sha256"],),
                )
                used -= row["byte_size"]
                result["removed_files"] += int(deleted)
                result["removed_bytes"] += size
            result["deferred"] = result["deferred"] or used + reserve > capacity
        return result

    def start(self):
        if self._runner is None:
            self._runner = asyncio.create_task(
                self._maintain(), name="owned-media-retention"
            )

    async def _maintain(self):
        while True:
            await asyncio.sleep(60)
            try:
                await database_call(self.collect)
            except AnalysisError:
                continue

    async def shutdown(self):
        if self._runner is not None:
            self._runner.cancel()
            await settle(asyncio.gather(self._runner, return_exceptions=True))
            self._runner = None
