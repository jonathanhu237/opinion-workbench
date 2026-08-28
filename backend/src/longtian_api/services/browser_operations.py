"""Atomic admission for browser operations shared across product features."""

import asyncio
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BrowserOperationOwner:
    feature: Literal[
        "platform_connection",
        "search_run",
        "search_batch",
        "search_result_open",
        "content_enrichment",
    ]
    request_id: UUID


class BrowserOperationCoordinator:
    """Permit one browser-unsafe product operation at a time."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: BrowserOperationOwner | None = None

    async def try_claim(self, owner: BrowserOperationOwner) -> bool:
        async with self._lock:
            if self._owner is not None:
                return False
            self._owner = owner
            return True

    async def release(self, owner: BrowserOperationOwner) -> None:
        async with self._lock:
            if self._owner == owner:
                self._owner = None

    async def is_owned_by(self, owner: BrowserOperationOwner) -> bool:
        async with self._lock:
            return self._owner == owner
