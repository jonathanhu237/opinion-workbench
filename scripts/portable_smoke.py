#!/usr/bin/env python3
"""Exercise a disposable extracted package without platform or model requests."""

import argparse
import base64
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def page_lease(port: int) -> socket.socket:
    connection = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    connection.sendall(
        (
            f"GET /api/v1/lifecycle/ws HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            f"Origin: http://127.0.0.1:{port}\r\n\r\n"
        ).encode()
    )
    response = b""
    while b"\r\n\r\n" not in response and len(response) < 16384:
        part = connection.recv(1024)
        if not part:
            break
        response += part
    if not response.startswith(b"HTTP/1.1 101 "):
        connection.close()
        raise RuntimeError("packaged lifecycle handshake failed")
    return connection


def check_worker(app: Path, env: dict[str, str], cwd: str) -> None:
    worker = app / (
        "LongtianGalleryWorker.exe" if os.name == "nt" else "LongtianGalleryWorker"
    )
    startup = {
        "content_id": "3600375418559878",
        "mode": "text_only",
        "cookies": {},
        "max_media_bytes": 1024,
        "max_images": 24,
        "max_videos": 1,
    }
    response = {
        "kind": "response",
        "status_code": 404,
        "url": "https://weibo.com/ajax/statuses/show?id=3600375418559878",
        "headers": {},
        "body": {"encoding": "json", "value": {}},
        "history": [],
        "cookies": {},
    }
    result = subprocess.run(
        [str(worker), "--longtian-gallery-worker"],
        input=json.dumps(startup) + "\n" + json.dumps(response) + "\n",
        text=True,
        capture_output=True,
        timeout=30,
        env=env,
        cwd=cwd,
    )
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    if (
        result.returncode
        or not lines
        or lines[0].get("kind") != "request"
        or lines[-1].get("kind") != "error"
    ):
        raise RuntimeError("packaged helper failed its offline broker protocol check")


def smoke(program: Path, app: Path) -> None:
    program, app = program.resolve(), app.resolve()
    data = app / "data"
    if data.exists():
        raise RuntimeError(
            "smoke requires a fresh disposable extraction; data already exists"
        )
    with tempfile.TemporaryDirectory(prefix="longtian-smoke-driver-") as temp:
        log_path = Path(temp) / "process.log"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("LONGTIAN_", "PYTHON"))
        }
        # The driver can use Python; the child must not depend on developer PATH.
        env["PATH"] = (
            os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32")
            if os.name == "nt"
            else "/usr/bin:/bin"
        )
        check_worker(app, env, temp)
        with log_path.open("w+b") as log:
            proc = subprocess.Popen(
                [str(program), "--no-browser", "--port", str(port)],
                cwd=temp,
                env=env,
                stdout=log,
                stderr=log,
            )
            lease = None
            try:
                deadline = time.monotonic() + 45
                record = data / "server.json"
                while not record.exists():
                    if proc.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("packaged launcher did not become ready")
                    time.sleep(0.2)
                if json.loads(record.read_text())["port"] != port:
                    raise RuntimeError("unexpected server identity")
                lease = page_lease(port)
                base = f"http://127.0.0.1:{port}"
                for endpoint in ("/api/v1/health", "/", "/api/v1/summary-preferences"):
                    with urllib.request.urlopen(base + endpoint, timeout=5) as response:
                        if response.status != 200:
                            raise RuntimeError("packaged HTTP check failed")
                if not (data / "longtian.sqlite3").is_file():
                    raise RuntimeError("portable database missing")
                # Disconnect the last UI page, exercising the normal cross-OS
                # shutdown contract instead of unsupported Windows SIGINT.
                lease.close()
                lease = None
                proc.wait(timeout=25)
                if proc.returncode != 0:
                    raise RuntimeError("packaged launcher exited unsuccessfully")
            except BaseException as error:
                log.flush()
                detail = log_path.read_text(errors="replace")[-5000:]
                raise RuntimeError(f"{error}\n{detail}") from error
            finally:
                if lease is not None:
                    lease.close()
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
    print("Packaged startup, portable data, HTTP and page-close shutdown passed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program", type=Path)
    parser.add_argument("--cwd", required=True, type=Path)
    args = parser.parse_args()
    smoke(args.program, args.cwd)


if __name__ == "__main__":
    main()
