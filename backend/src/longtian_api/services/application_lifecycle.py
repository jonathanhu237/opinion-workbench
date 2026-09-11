"""Page leases used by the packaged local application.

The browser is the user-facing process.  A short-lived WebSocket lease lets
the backend distinguish a refresh or an additional tab from the last page
going away.  The server's WebSocket ping/pong settings keep a background tab
alive even when JavaScript timers are throttled; the application heartbeat is
still useful for diagnostics and for servers that do not provide transport
ping support.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.websockets import WebSocket, WebSocketDisconnect

LifecycleCallback = Callable[[], Awaitable[None] | None]
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ApplicationLifecycle:
    """Track active UI pages and request process shutdown after the last one."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        grace_seconds: float = 10.0,
        on_expired: LifecycleCallback | None = None,
        clock: Callable[[], float] = monotonic,
        allowed_hosts: tuple[str, ...] = tuple(_LOCAL_HOSTS),
    ) -> None:
        if grace_seconds <= 0:
            raise ValueError("grace_seconds must be positive")
        self.enabled = enabled
        self.grace_seconds = grace_seconds
        self._on_expired = on_expired
        self._clock = clock
        self._allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        self._leases: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._expiry_task: asyncio.Task | None = None
        self._closed = False
        self._expired = False
        self._first_page = asyncio.Event()

    @property
    def active_count(self) -> int:
        return len(self._leases)

    async def register(self, lease_id: str | None = None) -> str:
        """Register one page and cancel any pending empty-page shutdown."""

        async with self._lock:
            if self._closed:
                raise RuntimeError("application lifecycle is closed")
            identity = lease_id or uuid4().hex
            self._leases[identity] = self._clock()
            self._first_page.set()
            self._expired = False
            if self._expiry_task is not None:
                self._expiry_task.cancel()
                self._expiry_task = None
            return identity

    async def heartbeat(self, lease_id: str) -> bool:
        """Refresh one lease, returning false for a stale/unknown page."""

        async with self._lock:
            if self._closed or lease_id not in self._leases:
                return False
            self._leases[lease_id] = self._clock()
            return True

    async def release(self, lease_id: str) -> None:
        """Release one page and arm the delayed empty-page shutdown."""

        async with self._lock:
            self._leases.pop(lease_id, None)
            if self._closed or self._leases or self._expiry_task is not None:
                return
            self._expiry_task = asyncio.create_task(
                self._expire_after_grace(), name="application-page-expiry"
            )

    async def wait_for_first_page(self, timeout: float) -> bool:
        """Wait until the first same-origin UI page owns a lease."""

        if not self.enabled or timeout <= 0:
            return False
        try:
            await asyncio.wait_for(self._first_page.wait(), timeout)
        except (TimeoutError, asyncio.CancelledError):
            return False
        return True

    def _same_origin_local(self, websocket: WebSocket) -> bool:
        """Accept only a browser page served by this local HTTP origin."""

        host_header = websocket.headers.get("host")
        origin = websocket.headers.get("origin")
        if not host_header or not origin:
            return False
        try:
            host_parts = urlsplit(f"//{host_header}")
            origin_parts = urlsplit(origin)
            request_host = (host_parts.hostname or "").lower()
            origin_host = (origin_parts.hostname or "").lower()
            request_port = host_parts.port
            websocket_scheme = websocket.url.scheme.lower()
            expected_origin_scheme = (
                "https" if websocket_scheme in {"wss", "https"} else "http"
            )
            default_port = 443 if expected_origin_scheme == "https" else 80
            origin_port = origin_parts.port or default_port
        except ValueError:
            return False
        if request_host not in self._allowed_hosts or origin_host != request_host:
            return False
        if host_parts.username or host_parts.password:
            return False
        if (
            origin_parts.scheme != expected_origin_scheme
            or origin_parts.username
            or origin_parts.password
            or origin_parts.path not in ("", "/")
            or origin_parts.query
            or origin_parts.fragment
        ):
            return False
        expected_port = request_port or default_port
        return origin_port == expected_port

    async def _expire_after_grace(self) -> None:
        try:
            await asyncio.sleep(self.grace_seconds)
            async with self._lock:
                if self._closed or self._leases or self._expired:
                    return
                self._expired = True
                callback = self._on_expired
            if callback is not None:
                result = callback()
                if inspect.isawaitable(result):
                    await result
        except asyncio.CancelledError:
            return
        finally:
            current = asyncio.current_task()
            async with self._lock:
                if self._expiry_task is current:
                    self._expiry_task = None

    async def handle_websocket(self, websocket: WebSocket) -> None:
        """Serve one browser page lease over a same-origin WebSocket."""

        if not self.enabled or self._closed:
            await websocket.close(code=1008, reason="application lifecycle disabled")
            return
        if not self._same_origin_local(websocket):
            await websocket.close(code=1008, reason="same-origin page required")
            return
        await websocket.accept()
        lease_id = await self.register()
        try:
            await websocket.send_json(
                {"type": "ready", "heartbeat_seconds": 4, "grace_seconds": 10}
            )
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict) or message.get("type") != "heartbeat":
                    continue
                if not await self.heartbeat(lease_id):
                    return
                await websocket.send_json({"type": "heartbeat", "ok": True})
        except (WebSocketDisconnect, RuntimeError, ValueError):
            # Closing a browser tab is an expected lifecycle event.  Transport
            # failures are handled by the same delayed release path.
            pass
        finally:
            await self.release(lease_id)

    async def shutdown(self) -> None:
        async with self._lock:
            self._closed = True
            self._leases.clear()
            expiry = self._expiry_task
            self._expiry_task = None
        if expiry is not None:
            expiry.cancel()
            try:
                await expiry
            except asyncio.CancelledError:
                pass
