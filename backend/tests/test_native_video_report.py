"""Synthetic MP4 bytes, real media probe, real application orchestration."""

import asyncio
import base64
import shutil
import subprocess

import httpx
import pytest
from enrichment_fixtures import PNG
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_native_text_report import native_environment, wait_status
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

    return {
        "valid": generate(),
        "silent": generate(audio=False),
        "long": generate(duration="31"),
        "codec": generate(codec="mpeg4"),
    }


def video_response(data, *, caption="龙田现场视频", image=False, status=200):
    def response(request):
        if request.url.host == "weibo.com":
            post = {
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text": caption,
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
def test_real_video_bytes_reach_model_and_report(
    tmp_path, video_samples, caption, image
):
    data = video_samples["valid"]
    app, _, model, requests = native_environment(
        tmp_path, response=video_response(data, caption=caption, image=image)
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
        asset = next(a for a in attempt["input"]["assets"] if a["kind"] == "video")
        assert asset["status"] == "ready" and asset["audio_track"] == "present"
        assert 0 < asset["duration_ms"] <= 30000 and asset["byte_size"] == len(data)
        parts = next(messages for stage, messages in model.calls if stage == "initial")[
            1
        ]["content"]
        videos = [part for part in parts if part["type"] == "video_url"]
        assert len(videos) == 1
        assert base64.b64decode(videos[0]["video_url"]["url"].split(",")[1]) == data
        sources = client.get(
            f"/api/v1/topic-reports/{result['report']['id']}/sources"
        ).json()["items"]
        assert sources[0]["evidence_coverage"]["video"]["ready"] == 1
        assert len(requests) == 2 + image
        cache = client.get(
            f"/api/v1/content-analyses/{attempt['id']}/media-cache"
        ).json()
        assert all(item["state"] == "cached" for item in cache["items"])
        original = client.get(
            f"/api/v1/content-analyses/{attempt['id']}/media/{asset['position']}"
        )
        assert (
            original.content == data and original.headers["content-type"] == "video/mp4"
        )
        assert client.get(f"/api/v1/report-generations/{value['id']}").json() == result
        assert len(requests) == 2 + image


@pytest.mark.parametrize(
    "sample,issue",
    [
        ("silent", "audio_missing"),
        ("long", "media_limit"),
        ("codec", "unsupported_codec"),
        ("broken", "invalid_media"),
    ],
)
def test_unusable_video_keeps_text_and_image_but_is_never_sent(
    tmp_path, video_samples, sample, issue
):
    app, _, model, _ = native_environment(
        tmp_path,
        response=video_response(video_samples.get(sample, b"not mp4"), image=True),
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
        assert attempt["input"]["assets"][1]["issue_code"] == issue
        parts = next(messages for stage, messages in model.calls if stage == "initial")[
            1
        ]["content"]
        assert sum(part["type"] == "image_url" for part in parts) == 1
        assert not any(part["type"] == "video_url" for part in parts)


def test_video_challenge_requires_continue_and_does_not_repeat_finished_image(
    tmp_path, video_samples
):
    allowed = False

    def response(request):
        result = video_response(
            video_samples["valid"], image=True, status=200 if allowed else 403
        )(request)
        if request.url.path.endswith(".mp4") and not allowed:
            return httpx.Response(403, content="安全验证".encode())
        return result

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        service = app.state.report_generation_service
        paused = client.portal.call(
            wait_status, service, value["id"], "paused_for_manual_action"
        )
        assert len(requests) == 3 and not model.calls
        allowed = True
        assert (
            client.get(f"/api/v1/report-generations/{value['id']}").json()["status"]
            == "paused_for_manual_action"
        )
        assert len(requests) == 3 and not model.calls
        assert (
            client.post(
                f"/api/v1/report-generations/{value['id']}/continue",
                json={"expected_revision": paused.control_revision},
            ).status_code
            == 200
        )
        client.portal.call(finish, service)
        assert (
            client.get(f"/api/v1/report-generations/{value['id']}").json()["status"]
            == "completed"
        )
        assert len(requests) == 4 and model.counts["initial"] == 1


def test_missing_probe_keeps_body_without_video_model_input(
    tmp_path, video_samples, monkeypatch
):
    from longtian_api.services import video_probe

    monkeypatch.setattr(video_probe.shutil, "which", lambda name: None)
    app, _, model, _ = native_environment(
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
        assert attempt["input"]["assets"][0]["issue_code"] == "probe_unavailable"
        assert isinstance(
            next(messages for stage, messages in model.calls if stage == "initial")[1][
                "content"
            ],
            str,
        )


def test_cancel_waits_for_owned_probe_start_and_exit(video_samples):
    from uuid import uuid4

    from longtian_api.services.media_inventory import MediaCandidate
    from longtian_api.services.video_probe import VideoProbe

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
