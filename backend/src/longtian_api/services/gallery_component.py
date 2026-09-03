"""One disposable upstream parser with a project-controlled lookup broker."""

import asyncio
import json
import re
import sys

from longtian_api.services.settled_tasks import settle

FRAME_LIMIT = 2 * 1024 * 1024


class ComponentError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class GalleryComponent:
    def __init__(self, *, launcher=asyncio.create_subprocess_exec):
        self._launcher = launcher

    async def extract(self, content_id, *, fetch):
        if not re.fullmatch(r"[1-9][0-9]{5,23}", content_id):
            raise ComponentError("invalid_identity")
        launch = asyncio.create_task(
            self._launcher(
                sys.executable,
                "-I",
                "-u",
                "-m",
                "longtian_api.gallery_worker",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=FRAME_LIMIT,
                env={"LANG": "C.UTF-8"},
            )
        )
        try:
            process = await asyncio.shield(launch)
        except asyncio.CancelledError:

            async def finish_starting():
                process = await launch
                await self._stop(process)

            await settle(finish_starting())
            raise
        try:
            async with asyncio.timeout(30):
                await self._send(process, {"content_id": content_id})
                requests = 0
                expected = (
                    "https://weibo.com/ajax/statuses/show?id="
                    + content_id
                    + "&isGetLongText=true"
                )
                while True:
                    raw = await process.stdout.readline()
                    if not raw.endswith(b"\n") or len(raw) > FRAME_LIMIT:
                        raise ComponentError("invalid_output")
                    message = json.loads(raw)
                    if message.get("kind") == "request":
                        if requests >= 2 or message.get("url") != expected:
                            raise ComponentError("lookup_out_of_scope")
                        requests += 1
                        body = await fetch(expected)
                        await self._send(process, {"kind": "response", "body": body})
                    elif message.get("kind") == "result":
                        post = message.get("post")
                        if (
                            not isinstance(post, dict)
                            or str(post.get("idstr", post.get("id"))) != content_id
                            or not isinstance(message.get("files"), list)
                        ):
                            raise ComponentError("identity_mismatch")
                        await process.wait()
                        if process.returncode != 0:
                            raise ComponentError("parser_failed")
                        return {"post": post, "files": message["files"]}
                    elif message.get("kind") == "error":
                        code = message.get("code")
                        raise ComponentError(
                            "content_unavailable"
                            if code == "content_unavailable"
                            else "parser_failed"
                        )
                    else:
                        raise ComponentError("invalid_output")
        except (ValueError, OSError):
            raise ComponentError("invalid_output") from None
        finally:
            await settle(self._stop(process))

    async def _send(self, process, message):
        raw = json.dumps(message, ensure_ascii=True).encode() + b"\n"
        if len(raw) > FRAME_LIMIT:
            raise ComponentError("input_limit")
        process.stdin.write(raw)
        await process.stdin.drain()

    async def _stop(self, process):
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        if process.stdin is not None:
            process.stdin.close()
