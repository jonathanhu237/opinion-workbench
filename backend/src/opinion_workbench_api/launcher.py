"""Packaged local application launcher.

The launcher owns the server process, opens the normal browser, and keeps all
mutable state in the per-user application data directory.  It is deliberately
small enough to run from a PyInstaller build and does not assume that the
frozen executable is a Python interpreter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from opinion_workbench_api.application_paths import (
    DATA_DIR_ENV,
    ApplicationPaths,
    application_paths,
)
from opinion_workbench_api.main import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
READY_TIMEOUT_SECONDS = 30.0
STARTUP_PAGE_TIMEOUT_SECONDS = 30.0


class LaunchError(RuntimeError):
    """A user-actionable launcher failure without sensitive details."""


def _show_launch_error(message: str) -> None:
    """Make startup failures visible when the packaged exe has no console."""

    title = "舆情工作台"
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
        except Exception:
            # The log and stderr fallback still make failures diagnosable in
            # restricted desktop sessions and in test harnesses.
            pass
    try:
        print(f"{title}: {message}", file=sys.stderr)
    except Exception:
        pass


class InstanceLock:
    """Cross-platform process lock for one local application data root."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
            if os.name == "nt":
                import msvcrt

                if os.fstat(self._fd).st_size == 0:
                    os.write(self._fd, b"0")
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, ValueError):
            self.release()
            return False

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        except (OSError, ValueError):
            pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self) -> InstanceLock:
        if not self.acquire():
            raise LaunchError("应用已经在运行。")
        return self

    def __exit__(self, *_exc) -> None:
        self.release()


@dataclass(frozen=True, slots=True)
class LauncherConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    open_browser: bool = True
    data_root: Path | None = None
    static_dir: Path | None = None

    def validate(self) -> None:
        if self.host != DEFAULT_HOST:
            raise LaunchError("应用只允许监听本机地址。")
        if not 1024 <= self.port <= 65535:
            raise LaunchError("本机端口必须在 1024 到 65535 之间。")


class LocalApplication:
    """Start one packaged server and retain ownership until it exits."""

    def __init__(self, config: LauncherConfig | None = None) -> None:
        self.config = config or LauncherConfig()
        self.config.validate()
        if self.config.data_root is not None:
            os.environ[DATA_DIR_ENV] = str(self.config.data_root.absolute())
        self.paths = application_paths(self.config.data_root)
        self._logger = self._configure_logging(self.paths)
        self._lock = InstanceLock(self.paths.lock_path)

    @staticmethod
    def _configure_logging(paths: ApplicationPaths) -> logging.Logger:
        paths.ensure()
        logger = logging.getLogger("opinion-workbench.launcher")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.FileHandler(
                paths.log_dir / "launcher.log", encoding="utf-8"
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            )
            logger.addHandler(handler)
        return logger

    def _static_dir(self) -> Path:
        if self.config.static_dir is not None:
            return self.config.static_dir.absolute()
        configured = os.environ.get("OPINION_WORKBENCH_STATIC_DIR")
        if configured:
            return Path(configured).absolute()
        if getattr(sys, "frozen", False):
            return (
                Path(getattr(sys, "_MEIPASS", Path(sys.executable)))
                / "resources"
                / "static"
            )
        return Path(__file__).resolve().parents[3] / "frontend" / "dist"

    @staticmethod
    def _url(host: str, port: int) -> str:
        return f"http://{host}:{port}/"

    def _write_server_record(self) -> None:
        payload = {
            "pid": os.getpid(),
            "host": self.config.host,
            "port": self.config.port,
        }
        temporary = self.paths.server_record_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, self.paths.server_record_path)

    def _remove_server_record(self) -> None:
        try:
            self.paths.server_record_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            self._logger.warning("无法清理启动记录，请下次启动时重试。")

    @staticmethod
    def _health_url(host: str, port: int) -> str:
        return f"http://{host}:{port}/api/v1/health"

    def _reserve_listener(self) -> socket.socket:
        """Reserve the configured port before Uvicorn starts its task.

        Uvicorn reports a bind failure by calling ``sys.exit`` from its async
        startup path.  That exception is a process-level signal and can skip
        the launcher's normal error handling, especially in a console-less
        frozen process.  Owning the socket here turns the failure into a
        regular, user-visible ``LaunchError`` and removes the bind race.
        """

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind((self.config.host, self.config.port))
            listener.listen(socket.SOMAXCONN)
        except OSError as error:
            listener.close()
            raise LaunchError(
                "本地服务无法占用指定端口，请关闭占用该端口的程序后重试。"
            ) from error
        return listener

    def _ready(self, host: str, port: int) -> bool:
        try:
            with urllib.request.urlopen(
                self._health_url(host, port), timeout=1.0
            ) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _existing_instance(self) -> tuple[str, int] | None:
        try:
            payload = json.loads(
                self.paths.server_record_path.read_text(encoding="utf-8")
            )
            host = payload.get("host")
            port = payload.get("port")
            if (
                host != DEFAULT_HOST
                or type(port) is not int
                or not 1024 <= port <= 65535
            ):
                return None
            return host, port
        except (OSError, ValueError, TypeError):
            return None

    async def _wait_ready(self, server_task: asyncio.Task | None = None) -> None:
        deadline = asyncio.get_running_loop().time() + READY_TIMEOUT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            if server_task is not None and server_task.done():
                try:
                    server_task.result()
                except (SystemExit, KeyboardInterrupt):
                    raise LaunchError(
                        "本地服务无法启动，请查看 launcher.log 后重试。"
                    ) from None
                except Exception:
                    raise LaunchError(
                        "本地服务无法占用指定端口，请关闭占用该端口的程序后重试。"
                    ) from None
                raise LaunchError("本地服务提前退出，请查看 launcher.log 后重试。")
            if await asyncio.to_thread(self._ready, self.config.host, self.config.port):
                return
            await asyncio.sleep(0.2)
        raise LaunchError(
            "本地服务未能启动。请查看应用数据目录 logs\\launcher.log 后重试。"
        )

    async def _run_server(self) -> None:
        static_dir = self._static_dir()
        if not (static_dir / "index.html").is_file():
            raise LaunchError("安装包缺少前端页面文件，请重新构建安装包。")

        import uvicorn

        server_holder: dict[str, uvicorn.Server] = {}

        def request_shutdown() -> None:
            server = server_holder.get("server")
            if server is not None:
                server.should_exit = True

        application = create_app(
            static_dir=static_dir,
            packaged=True,
            lifecycle_enabled=True,
            lifecycle_on_expired=request_shutdown,
            automation_resume_on_startup=False,
        )
        config = uvicorn.Config(
            application,
            host=self.config.host,
            port=self.config.port,
            # PyInstaller's ``console=False`` executable exposes
            # ``sys.stdout``/``sys.stderr`` as None.  Uvicorn's default
            # logging dictionary resolves those streams during Config
            # construction and fails before the health endpoint is ready.
            # Launcher failures go to the application-owned log file instead.
            log_config=None,
            log_level="warning",
            access_log=False,
            ws_ping_interval=5.0,
            ws_ping_timeout=5.0,
        )
        server = uvicorn.Server(config)
        server_holder["server"] = server
        listener = self._reserve_listener()
        task = asyncio.create_task(
            server.serve([listener]), name="opinion-workbench-api-server"
        )
        try:
            await self._wait_ready(task)
            self._write_server_record()
            if self.config.open_browser:
                opened = await asyncio.to_thread(
                    webbrowser.open,
                    self._url(self.config.host, self.config.port),
                    2,
                )
                if not opened:
                    raise LaunchError("无法打开默认浏览器，请确认已安装浏览器后重试。")
                lifecycle = getattr(application.state, "application_lifecycle", None)
                if lifecycle is None or not await lifecycle.wait_for_first_page(
                    STARTUP_PAGE_TIMEOUT_SECONDS
                ):
                    raise LaunchError(
                        "默认浏览器未能打开系统页面，请检查浏览器后重试。"
                    )
            await task
            if task.exception() is not None:
                raise LaunchError("本地服务异常退出，请查看 launcher.log。")
        except asyncio.CancelledError:
            server.should_exit = True
            raise
        finally:
            server.should_exit = True
            if not task.done():
                try:
                    await asyncio.wait_for(task, 10)
                except (TimeoutError, asyncio.CancelledError):
                    task.cancel()
            listener.close()
            self._remove_server_record()

    async def run_async(self) -> int:
        if not self._lock.acquire():
            existing = self._existing_instance()
            if existing is not None and self._ready(*existing):
                if self.config.open_browser and not webbrowser.open(
                    self._url(*existing), new=2
                ):
                    raise LaunchError("无法打开已经运行的应用页面。")
                return 0
            raise LaunchError("应用正在启动或启动记录已失效，请稍后重试。")
        try:
            await self._run_server()
            return 0
        finally:
            self._lock.release()

    def run(self) -> int:
        try:
            return asyncio.run(self.run_async())
        except LaunchError as error:
            self._logger.error("%s", error)
            _show_launch_error(str(error))
            return 1
        except Exception:
            self._logger.exception("应用启动失败")
            _show_launch_error("应用启动失败，请查看应用数据目录 logs\\launcher.log。")
            return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the OpinionWorkbench local application"
    )
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--static-dir", type=Path, default=None)
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("OPINION_WORKBENCH_PORT", DEFAULT_PORT)),
    )
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--opinion-workbench-gallery-worker" in argv:
        from opinion_workbench_api.gallery_worker import main as gallery_main

        gallery_main()
        return 0
    try:
        args = _parser().parse_args(argv)
        return LocalApplication(
            LauncherConfig(
                port=args.port,
                open_browser=not args.no_browser,
                data_root=args.data_dir,
                static_dir=args.static_dir,
            )
        ).run()
    except LaunchError as error:
        _show_launch_error(str(error))
        return 1
    except Exception:
        _show_launch_error("应用启动失败，请检查应用数据目录和安装包后重试。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
