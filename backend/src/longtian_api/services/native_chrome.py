"""Own one local Chrome process and one bounded platform page.

This is application runtime code, not an agent browser-control utility. It never
attaches to the daily browser, exports credential files, calls platform APIs, or
changes fingerprints. The collector receives only rendered DOM and scoped
session state in memory; only coordination files are read from the profile.
"""

import asyncio
import os
import re
import socket
import stat
import sys
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from longtian_api.services.native_browser_contracts import (
    BrowserUnavailable,
)
from longtian_api.services.settled_tasks import settle

_NAVIGATION_DOMAINS = (
    "weibo.com",
    "weibo.cn",
    "sinaimg.cn",
    "sinajs.cn",
    "sina.com.cn",
    "toutiao.com",
    "toutiaoimg.com",
    "kuaishou.com",
    "kwai.com",
    "douyin.com",
    "iesdouyin.com",
    "xiaohongshu.com",
    "xhscdn.com",
)


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
        self._process = self._playwright = self._browser = self._page = None
        self._check_page = None
        self._lease = None
        self._closing = False
        self._status = 200
        self._check_status = 200

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
            self._clear_stale_chrome_locks()
        except BaseException:
            os.close(fd)
            raise
        self._lease = fd

    def _stale_chrome_lock(self):
        """Only a demonstrably dead local owner qualifies for automatic cleanup."""
        lock = self.profile / "SingletonLock"
        if not lock.is_symlink():
            return False
        try:
            host, pid = os.readlink(lock).rsplit("-", 1)
            if host != socket.gethostname() or not pid.isdecimal() or int(pid) <= 0:
                return False
            try:
                os.kill(int(pid), 0)
            except ProcessLookupError:
                return True
            return False
        except (OSError, ValueError):
            return False

    def _clear_stale_chrome_locks(self):
        # Called under the application profile lease. Remove only these links,
        # never the socket targets, credential files or application lease file.
        links = []
        for name in ("SingletonCookie", "SingletonSocket", "SingletonLock"):
            path = self.profile / name
            if os.path.lexists(path):
                meta = path.lstat()
                if not stat.S_ISLNK(meta.st_mode) or meta.st_uid != os.getuid():
                    raise BrowserUnavailable()
                links.append((path, meta, os.readlink(path)))
        if not links:
            return
        if not self._stale_chrome_lock():
            raise BrowserUnavailable()
        socket_link = self.profile / "SingletonSocket"
        if socket_link.is_symlink():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.2)
                try:
                    probe.connect(str(socket_link.resolve()))
                except (FileNotFoundError, ConnectionRefusedError):
                    pass
                except OSError:
                    raise BrowserUnavailable() from None
                else:
                    raise BrowserUnavailable()
        # Check all identities before mutating; retain ambiguous/live owners.
        for path, meta, target in links:
            current = path.lstat()
            if (current.st_dev, current.st_ino) != (
                meta.st_dev,
                meta.st_ino,
            ) or os.readlink(path) != target:
                raise BrowserUnavailable()
        if not self._stale_chrome_lock():
            raise BrowserUnavailable()
        for path, _, _ in links:
            path.unlink()

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

    async def start(self):
        await self._ensure()
        try:
            if self._page is None or self._page.is_closed():
                context = self._browser.contexts[0]
                self._page = await self._bounded(context.new_page())
                self._bind_page(self._page)
                # Chrome loads the site normally, including login frames,
                # callbacks, WebSockets, popups and service workers. Collection
                # scope and cancellation are controlled by the caller's tasks.
        except Exception:
            await self.close_page()
            raise BrowserUnavailable() from None

    def _bind_page(self, page):
        page.set_default_timeout(5000)
        page.on("response", lambda response: self._response(response, page))

    def _response(self, response, page):
        if (
            response.request.is_navigation_request()
            and response.frame == page.main_frame
        ):
            if page is self._check_page:
                self._check_status = response.status
            elif page is self._page:
                self._status = response.status

    def _check(self):
        if not self.available or self._page is None or self._page.is_closed():
            raise BrowserUnavailable()

    async def navigate(self, url):
        self._validate_navigation_url(url)
        self._check()
        self._status = 200
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            self._check()
            # Preserve a potentially useful loaded challenge page for parsing.
            if self._page.url == "about:blank":
                raise BrowserUnavailable() from None

    @staticmethod
    def _validate_navigation_url(url):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or not any(
                host == domain or host.endswith("." + domain)
                for domain in _NAVIGATION_DOMAINS
            )
        ):
            raise BrowserUnavailable()

    async def start_check_page(self):
        await self._ensure()
        try:
            await self.close_check_page()
            context = self._browser.contexts[0]
            self._check_page = await self._bounded(context.new_page())
            self._check_status = 200
            self._bind_page(self._check_page)
        except Exception:
            await self.close_check_page()
            raise BrowserUnavailable() from None

    def _check_page_ready(self):
        if (
            not self.available
            or self._check_page is None
            or self._check_page.is_closed()
        ):
            raise BrowserUnavailable()

    async def navigate_check(self, url):
        self._validate_navigation_url(url)
        self._check_page_ready()
        self._check_status = 200
        try:
            await self._check_page.goto(
                url, wait_until="domcontentloaded", timeout=20_000
            )
        except Exception:
            self._check_page_ready()
            if self._check_page.url == "about:blank":
                raise BrowserUnavailable() from None

    async def snapshot_check(self):
        self._check_page_ready()
        try:
            value = await self._bounded(self._check_page.content())
            self._check_page_ready()
            return self._check_page.url, value, self._check_status
        except BrowserUnavailable:
            raise
        except Exception:
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
        except BrowserUnavailable:
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

    async def show(self):
        await self.start()
        await self.bring_to_front()

    async def close_page(self):
        failed = await self._close_page_object("_check_page")
        failed = await self._close_page_object("_page") or failed
        if failed and not self._closing:
            # A page we failed to close must not keep browsing after ownership
            # is released. Stop only our dedicated process, never another Chrome.
            await self.shutdown()

    async def close_check_page(self):
        failed = await self._close_page_object("_check_page")
        if failed and not self._closing:
            await self.shutdown()

    async def _close_page_object(self, attribute):
        page = getattr(self, attribute)
        failed = False
        try:
            if page is not None and not page.is_closed():
                await self._bounded(page.close())
        except Exception:
            failed = True
        finally:
            setattr(self, attribute, None)
        return failed

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
