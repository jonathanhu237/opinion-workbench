"""Bounded local MP4 inspection. The probe receives bytes, never a URL/path."""

import asyncio
import hashlib
import json
import math
import shutil

from opinion_workbench_api.services.enrichment_models import EnrichmentAsset
from opinion_workbench_api.services.settled_tasks import settle


class VideoProbeError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class VideoProbe:
    def __init__(self, *, executable=None, launcher=asyncio.create_subprocess_exec):
        self.executable = executable
        self.launcher = launcher

    async def inspect(self, candidate, data):
        if (
            len(data) < 24
            or data[4:8] != b"ftyp"
            or not 16 <= int.from_bytes(data[:4], "big") <= len(data)
            or data[8:12]
            not in {b"isom", b"iso2", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1"}
        ):
            raise VideoProbeError("invalid_media")
        metadata = await self._run(data)
        try:
            streams = metadata["streams"]
            videos = [s for s in streams if s["codec_type"] == "video"]
            audio = [s for s in streams if s["codec_type"] == "audio"]
            if (
                len(videos) != 1
                or len(streams) != len(videos) + len(audio)
                or len(audio) > 1
            ):
                raise VideoProbeError("unsupported_media_type")
            if videos[0]["codec_name"] != "h264" or (
                audio and audio[0]["codec_name"] != "aac"
            ):
                raise VideoProbeError("unsupported_codec")
            if not audio:
                raise VideoProbeError("audio_missing")
            width, height = videos[0]["width"], videos[0]["height"]
            duration = float(metadata["format"]["duration"])
            if (
                not math.isfinite(duration)
                or not 0 < duration <= 30
                or not 1 <= width <= 1920
                or not 1 <= height <= 1920
                or width * height > 1920 * 1080
            ):
                raise VideoProbeError("media_limit")
            # Count actual decoded frames, not just metadata or a cover image.
            decoded = await self._run(data, decode=True)
            for stream in decoded["streams"]:
                frames = int(stream["nb_read_frames"])
                maximum = 1800 if stream["codec_type"] == "video" else 6000
                if not 1 <= frames <= maximum:
                    raise VideoProbeError("media_limit")
            if len(decoded["streams"]) != len(streams):
                raise VideoProbeError("probe_failed")
        except (ValueError, KeyError, TypeError, OverflowError):
            raise VideoProbeError("probe_failed") from None
        return EnrichmentAsset(
            asset_id=candidate.asset_id,
            position=candidate.position,
            kind="video",
            role="content",
            status="ready",
            blob_ref=candidate.asset_id,
            sha256=hashlib.sha256(data).hexdigest(),
            mime_type="video/mp4",
            byte_size=len(data),
            width=width,
            height=height,
            duration_ms=max(1, round(duration * 1000)),
            audio_track="present",
            coverage="complete",
            issue_code=None,
        )

    async def _run(self, data, *, decode=False):
        executable = self.executable or shutil.which("ffprobe")
        if not executable:
            raise VideoProbeError("probe_unavailable")
        args = [
            executable,
            "-v",
            "error",
            "-max_alloc",
            "33554432",
            "-threads",
            "1",
            "-protocol_whitelist",
            "pipe",
            "-format_whitelist",
            "mov",
            "-enable_drefs",
            "0",
            "-use_absolute_path",
            "0",
            "-probesize",
            "6291456",
            "-analyzeduration",
            "1000000",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,nb_read_frames",
            "-of",
            "json",
        ]
        if decode:
            args.extend(["-codec_whitelist", "h264,aac", "-count_frames"])
        args.extend(["-i", "pipe:0"])
        launch = asyncio.create_task(
            self.launcher(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=16384,
                env={"LANG": "C.UTF-8"},
            )
        )
        try:
            process = await asyncio.shield(launch)
        except asyncio.CancelledError:

            async def finish_starting():
                await self._stop(await launch)

            await settle(finish_starting())
            raise
        except OSError:
            raise VideoProbeError("probe_unavailable") from None
        try:

            async def feed():
                try:
                    process.stdin.write(data)
                    await process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    process.stdin.close()

            async def read(stream, maximum):
                raw = await stream.read(maximum + 1)
                if len(raw) > maximum:
                    raise VideoProbeError("probe_failed")
                # read(n) may return a partial pipe chunk; drain to the bound.
                while more := await stream.read(maximum + 1 - len(raw)):
                    raw += more
                    if len(raw) > maximum:
                        raise VideoProbeError("probe_failed")
                return raw

            async with asyncio.timeout(5):
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(feed())
                    output = tasks.create_task(read(process.stdout, 16384))
                    errors = tasks.create_task(read(process.stderr, 8192))
                await process.wait()
                if process.returncode != 0 or errors.result():
                    raise VideoProbeError("probe_failed")
                return json.loads(output.result())
        except TimeoutError:
            raise
        except (ValueError, OSError, ExceptionGroup):
            raise VideoProbeError("probe_failed") from None
        finally:
            await settle(self._stop(process))

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
        process.stdin.close()
