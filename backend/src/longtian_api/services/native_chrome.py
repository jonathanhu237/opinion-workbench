"""Own one local Chrome process and one bounded Weibo page.

This is application runtime code, not an agent browser-control utility. It never
attaches to the daily browser, exports credential files, calls platform APIs, or
changes fingerprints. The selected-post broker may receive only the dedicated
Weibo session in memory; only coordination files are read from the profile.
"""

import asyncio
import os
import re
import stat
import sys
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from longtian_api.services.native_browser_contracts import (
    BrowserBudgetExceeded,
    BrowserUnavailable,
)
from longtian_api.services.settled_tasks import settle


class ManagedChrome:
    def __init__(
        self,
        *,
        profile: Path,
        launcher=asyncio.create_subprocess_exec,
        playwright_factory=None,
        on_disconnected=None,
        control_timeout_seconds=5,
    ):
        self.profile = profile.absolute()
        self._launcher = launcher
        self._playwright_factory = playwright_factory
        self._on_disconnected = on_disconnected
        self._control_timeout = control_timeout_seconds
        self._process = self._playwright = self._browser = self._page = self._cdp = None
        self._lease = None
        self._frozen = True
        self._closing = False
        self._requests = self._max_requests = 0
        self._exhausted = False
        self._status = 200
        self._request_tasks = set()

    @property
    def available(self):
        return self._browser is not None and self._browser.is_connected()

    @property
    def page_present(self):
        """Whether the managed browser currently owns a usable page."""
        return self._page is not None and not self._page.is_closed() and self.available

    async def _bounded(self, operation):
        async with asyncio.timeout(self._control_timeout):
            return await operation

    async def _send(self, method, params=None):
        return await self._bounded(self._cdp.send(method, params))

    async def _launch_owned(self, *args, **kwargs):
        launch = asyncio.create_task(self._launcher(*args, **kwargs))
        try:
            self._process = await asyncio.shield(launch)
        except asyncio.CancelledError:

            async def retain_process():
                self._process = await launch

            # The caller's failure path must own even a just-starting process.
            await settle(retain_process())
            raise

    def _prepare_profile(self):
        if sys.platform != "darwin" or self.profile.parts[-3:] != (
            "runtime",
            "browser",
            "managed-chrome",
        ):
            raise BrowserUnavailable()
        for path in (self.profile, *self.profile.parents):
            if path.is_symlink():
                raise BrowserUnavailable()
        self.profile.mkdir(mode=0o700, parents=True, exist_ok=True)
        meta = self.profile.stat()
        if (
            not stat.S_ISDIR(meta.st_mode)
            or meta.st_uid != os.getuid()
            or meta.st_mode & 0o077
        ):
            raise BrowserUnavailable()
        import fcntl

        # Same advisory lease as the legacy runtime: never race two Chromes.
        fd = os.open(
            self.profile / ".longtian-browser-owner.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
            ):
                raise BrowserUnavailable()
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                if os.path.lexists(self.profile / name):
                    raise BrowserUnavailable()
        except BaseException:
            os.close(fd)
            raise
        self._lease = fd

    def _endpoint_record(self):
        try:
            fd = os.open(
                self.profile / "DevToolsActivePort",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            )
        except FileNotFoundError:
            return None
        try:
            meta = os.fstat(fd)
            if (
                not stat.S_ISREG(meta.st_mode)
                or meta.st_uid != os.getuid()
                or meta.st_size > 4096
            ):
                raise BrowserUnavailable()
            value = os.read(fd, 4097).decode("ascii")
            matched = re.fullmatch(
                r"([0-9]{1,5})\n(/devtools/browser/[a-zA-Z0-9-]+)\n?", value
            )
            if not matched or not 1 <= int(matched[1]) <= 65535:
                return None
            return meta.st_mtime_ns, f"ws://127.0.0.1:{matched[1]}{matched[2]}"
        finally:
            os.close(fd)

    async def _ensure(self):
        if self.available:
            return
        if self._process is not None:
            await self.shutdown()
        self._closing = False
        try:
            self._prepare_profile()
            previous = self._endpoint_record()
            executable = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            await self._launch_owned(
                executable,
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",
                f"--user-data-dir={self.profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-startup-window",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            deadline = monotonic() + 20
            endpoint = None
            while monotonic() < deadline:
                if self._process.returncode is not None:
                    raise BrowserUnavailable()
                candidate = self._endpoint_record()
                if candidate is not None and candidate != previous:
                    endpoint = candidate[1]
                    break
                await asyncio.sleep(0.1)
            if endpoint is None:
                raise BrowserUnavailable()
            if self._playwright_factory is None:
                from playwright.async_api import async_playwright

                self._playwright_factory = async_playwright
            self._playwright = await self._playwright_factory().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                endpoint,
                timeout=10_000,
                no_defaults=True,
            )
            self._browser.on("disconnected", self._disconnected)
        except BaseException as error:
            await settle(self.shutdown())
            if isinstance(error, asyncio.CancelledError):
                raise
            raise BrowserUnavailable() from None

    def _disconnected(self):
        if not self._closing and self._on_disconnected:
            task = asyncio.create_task(self._on_disconnected(None))
            task.add_done_callback(
                lambda done: None if done.cancelled() else done.exception()
            )

    async def start(self, *, max_requests):
        await self._ensure()
        try:
            if self._page is None or self._page.is_closed():
                context = self._browser.contexts[0]
                self._page = await self._bounded(context.new_page())
                self._page.set_default_timeout(5000)
                self._cdp = await self._bounded(context.new_cdp_session(self._page))
                await self._send("Network.enable")
                await self._send("Network.setBypassServiceWorker", {"bypass": True})
                # Fetch interception includes each redirected request, unlike
                # Playwright's route callback which only sees the initial URL.
                self._cdp.on("Fetch.requestPaused", self._request_paused)
                await self._send(
                    "Fetch.enable",
                    {
                        "patterns": [{"urlPattern": "*", "requestStage": "Request"}],
                    },
                )
                await self._page.route_web_socket("**/*", lambda socket: socket.close())
                self._page.on("response", self._response)
                self._page.on("popup", lambda page: asyncio.create_task(page.close()))
            self._requests = 0
            self._max_requests = max_requests
            self._exhausted = False
            self._frozen = False
        except Exception:
            await self.close_page()
            raise BrowserUnavailable() from None

    def _response(self, response):
        if (
            response.request.is_navigation_request()
            and response.frame == self._page.main_frame
        ):
            self._status = response.status

    def _request_paused(self, event):
        task = asyncio.create_task(self._handle_request(event))
        self._request_tasks.add(task)
        task.add_done_callback(self._request_done)

    def _request_done(self, task):
        self._request_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self._frozen = True

    async def _handle_request(self, event):
        request = event["requestId"]
        try:
            parts = urlsplit(event["request"]["url"])
            host = parts.hostname or ""
            in_scope = (
                parts.scheme == "https"
                and not parts.username
                and not parts.password
                and parts.port in (None, 443)
                and any(
                    host == domain or host.endswith("." + domain)
                    for domain in (
                        "weibo.com",
                        "weibo.cn",
                        "sinaimg.cn",
                        "sinajs.cn",
                        "sina.com.cn",
                    )
                )
            )
        except (KeyError, ValueError):
            in_scope = False
        if self._requests >= self._max_requests:
            self._exhausted = True
        if self._frozen or self._exhausted or not in_scope:
            await self._send(
                "Fetch.failRequest",
                {
                    "requestId": request,
                    "errorReason": "Aborted",
                },
            )
            return
        self._requests += 1
        await self._send("Fetch.continueRequest", {"requestId": request})

    def _check(self):
        if self._exhausted:
            raise BrowserBudgetExceeded("requests")
        if not self.available or self._page is None or self._page.is_closed():
            raise BrowserUnavailable()

    async def navigate(self, url):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc not in (
            "weibo.com",
            "www.weibo.com",
            "m.weibo.cn",
            "s.weibo.com",
        ):
            raise BrowserUnavailable()
        self._check()
        self._status = 200
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            self._check()
            # Preserve a potentially useful loaded challenge page for parsing.
            if self._page.url == "about:blank":
                raise BrowserUnavailable() from None

    async def bring_to_front(self):
        self._check()
        try:
            await self._bounded(self._page.bring_to_front())
        except Exception:
            raise BrowserUnavailable() from None

    async def snapshot(self):
        self._check()
        try:
            # Serialized rendered DOM only; never cookies/storage/global state.
            value = await self._bounded(self._page.content())
            self._check()
            return self._page.url, value, self._status
        except (BrowserBudgetExceeded, BrowserUnavailable):
            raise
        except Exception:
            raise BrowserUnavailable() from None

    async def weibo_cookies(self):
        """Runtime-only, scoped ephemeral credentials for the owned HTTP broker."""
        await self._ensure()
        try:
            values = await self._bounded(
                self._browser.contexts[0].cookies(["https://weibo.com/"])
            )
            return {
                cookie["name"]: cookie["value"]
                for cookie in values
                if cookie["name"] in ("SUB", "SUBP")
                and cookie["domain"].lstrip(".") == "weibo.com"
            }
        except Exception:
            raise BrowserUnavailable() from None

    async def freeze(self):
        self._frozen = True
        if self._cdp is not None and self.available:
            try:
                await self._send("Page.stopLoading")
            except Exception:
                await self.close_page()

    async def show(self):
        existing = (
            self._page is not None and not self._page.is_closed() and self.available
        )
        await self.start(max_requests=1200)
        if not existing:
            await self.navigate("https://weibo.com/")
        await self.bring_to_front()

    async def close_page(self):
        self._frozen = True
        failed = False
        try:
            if self._page is not None and not self._page.is_closed():
                await self._bounded(self._page.close())
        except Exception:
            failed = True
        finally:
            tasks = tuple(self._request_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await self._bounded(asyncio.gather(*tasks, return_exceptions=True))
            self._page = self._cdp = None
        if failed and not self._closing:
            # A page we failed to close must not keep browsing after ownership
            # is released. Stop only our dedicated process, never another Chrome.
            await self.shutdown()

    async def shutdown(self):
        self._closing = True
        try:
            await self.close_page()
        finally:
            try:
                try:
                    if self._playwright is not None:
                        await self._bounded(self._playwright.stop())
                except Exception:
                    pass
                if self._process is not None and self._process.returncode is None:
                    try:
                        self._process.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(self._process.wait(), 5)
                    except TimeoutError:
                        try:
                            self._process.kill()
                        except ProcessLookupError:
                            pass
                        await asyncio.wait_for(self._process.wait(), 5)
            finally:
                self._playwright = self._browser = None
                if self._process is None or self._process.returncode is not None:
                    self._process = None
                    if self._lease is not None:
                        os.close(self._lease)
                        self._lease = None


def native_collector_factory(
    *, browser_profile_dir, on_progress, on_session_disconnected
):
    from longtian_api.services.native_weibo import NativeWeiboCollector

    return NativeWeiboCollector(
        browser=ManagedChrome(
            profile=browser_profile_dir,
            on_disconnected=on_session_disconnected,
        ),
        on_progress=on_progress,
    )
