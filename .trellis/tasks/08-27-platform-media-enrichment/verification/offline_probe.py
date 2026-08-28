"""Check the real local probe with generated media; never access user/platform data."""

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from tools.product_media import MediaError, MediaProbe, MediaStaging


def synthetic_mp4(*, audio: bool) -> bytes:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=64x64:r=2",
    ]
    if audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000"]
    command += ["-t", "1", "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p"]
    if audio:
        command += ["-c:a", "aac", "-b:a", "32k"]
    command += ["-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "pipe:1"]
    result = subprocess.run(
        command, stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=True
    )
    assert 0 < len(result.stdout) <= 6 * 1024 * 1024
    return result.stdout


async def run() -> None:
    findings = {}
    for with_audio in (True, False):
        payload = synthetic_mp4(audio=with_audio)
        with tempfile.TemporaryDirectory(prefix="longtian-synthetic-probe.") as path:
            root = Path(path).resolve()
            root.chmod(0o700)
            request_id = str(uuid4())
            operation = root / request_id.replace("-", "")
            operation.mkdir(mode=0o700)
            staging = MediaStaging(root, request_id)
            try:
                with staging.create(6 * 1024 * 1024) as writing:
                    writing.write(payload)
                    descriptor = writing.publish()
                try:
                    metadata = await MediaProbe(
                        os.environ.get("MEDIACRAWLER_FFPROBE")
                    ).inspect(
                        staging, descriptor["handle"], "video", "video/mp4"
                    )
                except MediaError as error:
                    assert not with_audio and error.code == "audio_missing"
                    findings["silent_video"] = error.code
                else:
                    assert with_audio
                    assert metadata["mime_type"] == "video/mp4"
                    assert (metadata["width"], metadata["height"]) == (64, 64)
                    assert metadata["audio_track"] == "present"
                    assert metadata["duration_ms"] > 0
                    findings["audio_video"] = {
                        "byte_size": len(payload),
                        "width": metadata["width"],
                        "height": metadata["height"],
                        "duration_ms": metadata["duration_ms"],
                        "audio_track": metadata["audio_track"],
                    }
            finally:
                staging.close(keep=False)
            assert not tuple(operation.iterdir())
    print(json.dumps(findings, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run())
