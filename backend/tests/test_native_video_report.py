"""Native text-only reports ignore video metadata and media URLs."""

import asyncio
import shutil
import subprocess

import httpx
import pytest
from enrichment_fixtures import PNG
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_native_text_report import native_environment
from test_report_generations import generation_request
from topic_report_fixtures import finish


@pytest.fixture(scope="module")
def video_samples():
    executable = shutil.which("ffmpeg")
    if executable is None or shutil.which("ffprobe") is None:
        pytest.skip("Synthetic video qualification requires ffmpeg and ffprobe")

    def generate(*, duration="0.2", audio=True, codec="libx264"):
        args = [
            executable,
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:r=5",
        ]
        if audio:
            args.extend(["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000"])
        args.extend(
            [
                "-t",
                duration,
                "-c:v",
                codec,
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "frag_keyframe+empty_moov",
                "-f",
                "mp4",
                "pipe:1",
            ]
        )
        return subprocess.run(args, check=True, capture_output=True, timeout=15).stdout

    return {"valid": generate()}


def video_response(data, *, caption="龙田现场视频", image=False, status=200):
    def response(request):
        if request.url.host == "weibo.com":
            post = {
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text": caption or "龙田现场视频",
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "pic_ids": [],
                "page_info": {
                    "media_info": {
                        "stream_url": "https://f.video.weibocdn.com/selected.mp4"
                    }
                },
            }
            if image:
                post.update(
                    pic_ids=["one"],
                    pic_infos={
                        "one": {"largest": {"url": "https://wx1.sinaimg.cn/one.png"}}
                    },
                )
            return httpx.Response(200, json=post)
        assert "cookie" not in request.headers
        if request.url.path.endswith(".png"):
            return httpx.Response(
                200, content=PNG, headers={"content-type": "image/png"}
            )
        return httpx.Response(
            status, content=data, headers={"content-type": "video/mp4"}
        )

    return response


@pytest.mark.parametrize("caption,image", [("", False), ("龙田图文视频", True)])
def test_video_metadata_never_reaches_text_only_report(
    tmp_path, video_samples, caption, image
):
    app, _, model, requests = native_environment(
        tmp_path,
        response=video_response(video_samples["valid"], caption=caption, image=image),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{value['id']}").json()
        assert result["status"] == "completed", result
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"][0]
        assert attempt["input"]["status"] == "ready"
        assert attempt["input"]["assets"] == []
        assert attempt["input"]["detected_modalities"] == ["text"]
        content = next(
            messages for stage, messages in model.calls if stage == "initial"
        )[1]["content"]
        assert isinstance(content, str)
        assert "image_url" not in str(model.calls)
        assert "video_url" not in str(model.calls)
        assert len(requests) == 1


@pytest.mark.parametrize(
    "sample",
    ["silent", "long", "codec", "broken"],
)
def test_unusable_video_bytes_are_not_requested_or_reported(
    tmp_path, video_samples, sample
):
    # The old media qualification cases remain as input variations, but the
    # production boundary intentionally does not inspect or download them.
    data = video_samples["valid"] if sample != "broken" else b"not mp4"
    app, _, model, requests = native_environment(
        tmp_path, response=video_response(data, image=True)
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{value['id']}").json()
        assert result["status"] == "completed", result
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"][0]
        assert attempt["input"]["assets"] == []
        assert "image_url" not in str(model.calls)
        assert "video_url" not in str(model.calls)
        assert len(requests) == 1


def test_video_challenge_does_not_pause_text_only_report(tmp_path, video_samples):
    def response(request):
        if request.url.host == "weibo.com":
            return httpx.Response(
                200,
                json={
                    "ok": 1,
                    "id": 3600375418559878,
                    "idstr": "3600375418559878",
                    "text": "龙田现场视频",
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": ["one"],
                    "pic_infos": {
                        "one": {"largest": {"url": "https://wx1.sinaimg.cn/one.png"}}
                    },
                    "page_info": {
                        "media_info": {
                            "stream_url": "https://f.video.weibocdn.com/selected.mp4"
                        }
                    },
                },
            )
        return httpx.Response(403, content="安全验证".encode())

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{value['id']}").json()
        assert result["status"] == "completed"
        assert model.counts["initial"] == 1
        assert len(requests) == 1


def test_missing_video_probe_does_not_change_text_only_input(
    tmp_path, video_samples, monkeypatch
):
    from opinion_workbench_api.services import video_probe

    monkeypatch.setattr(video_probe.shutil, "which", lambda name: None)
    app, _, model, requests = native_environment(
        tmp_path, response=video_response(video_samples["valid"])
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"][0]
        assert attempt["input"]["assets"] == []
        assert isinstance(
            next(messages for stage, messages in model.calls if stage == "initial")[1][
                "content"
            ],
            str,
        )
        assert len(requests) == 1


def test_cancel_waits_for_owned_probe_start_and_exit(video_samples):
    from uuid import uuid4

    from opinion_workbench_api.services.media_inventory import MediaCandidate
    from opinion_workbench_api.services.video_probe import VideoProbe

    processes, arguments = [], []

    async def run():
        started, release = asyncio.Event(), asyncio.Event()

        async def launch(*args, **kwargs):
            process = await asyncio.create_subprocess_exec(*args, **kwargs)
            processes.append(process)
            arguments.extend(args)
            started.set()
            await release.wait()
            return process

        task = asyncio.create_task(
            VideoProbe(launcher=launch).inspect(
                MediaCandidate(
                    uuid4().hex, 0, "video", "https://f.video.weibocdn.com/secret.mp4"
                ),
                video_samples["valid"],
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)

    asyncio.run(run())
    assert len(processes) == 1 and processes[0].returncode is not None
    assert "pipe:0" in arguments and "pipe" in arguments
    assert not any("https://" in arg for arg in arguments)
