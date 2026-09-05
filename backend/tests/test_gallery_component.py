"""Pinned real parser, isolated process, synthetic platform transport only."""

import asyncio

from enrichment_fixtures import PNG

from longtian_api.services.gallery_component import GalleryComponent, UpstreamResponse


def test_single_text_post_uses_the_selected_identity_and_no_recursive_requests():
    calls = []

    async def fetch(url):
        calls.append(url)
        return {
            "ok": 1,
            "id": 3600375418559878,
            "idstr": "3600375418559878",
            "text": "龙田街道道路施工公告。",
            "isLongText": False,
            "created_at": "Thu Sep 03 10:00:00 +0800 2026",
            "user": {"id": 1234567890, "screen_name": "测试作者"},
        }

    async def run():
        return await GalleryComponent().extract("3600375418559878", fetch=fetch)

    result = asyncio.run(run())
    assert result["post"]["idstr"] == "3600375418559878"
    assert result["post"]["text"] == "龙田街道道路施工公告。"
    assert result["files"] == []
    assert calls == [
        "https://weibo.com/ajax/statuses/show?id=3600375418559878&isGetLongText=true"
    ]


def test_cancel_waits_for_the_parser_to_exit_and_stops_pending_lookup():
    processes = []
    stopped = []

    async def launch(*args, **kwargs):
        process = await asyncio.create_subprocess_exec(*args, **kwargs)
        processes.append(process)
        return process

    async def run():
        entered = asyncio.Event()

        async def fetch(url):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)

        task = asyncio.create_task(
            GalleryComponent(launcher=launch).extract("3600375418559878", fetch=fetch)
        )
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert stopped == [True]
    assert len(processes) == 1 and processes[0].returncode is not None


def test_long_text_lookup_is_bounded_to_the_same_post():
    calls = []

    async def fetch(url):
        calls.append(url)
        return {
            "ok": 1,
            "id": 3600375418559878,
            "idstr": "3600375418559878",
            "text": "完整长正文" * 500
            if len(calls) == 2
            else '摘要<span class="expand">展开</span>',
            "isLongText": True,
            "created_at": "Thu Sep 03 10:00:00 +0800 2026",
        }

    result = asyncio.run(GalleryComponent().extract("3600375418559878", fetch=fetch))
    assert result["post"]["text"] == "完整长正文" * 500
    assert len(calls) == 2 and calls[0] == calls[1]


def test_access_challenge_is_returned_to_owner_without_a_visitor_or_retry_call():
    class NeedsManualAction(Exception):
        pass

    calls = []

    async def fetch(url):
        calls.append(url)
        raise NeedsManualAction()

    import pytest

    with pytest.raises(NeedsManualAction):
        asyncio.run(GalleryComponent().extract("3600375418559878", fetch=fetch))
    assert len(calls) == 1


def test_media_urls_form_a_bounded_inventory_not_ready_files():
    from longtian_api.services.enrichment_models import EnrichmentBudget
    from longtian_api.services.media_inventory import media_inventory

    async def fetch(url):
        return {
            "ok": 1,
            "id": 3600375418559878,
            "idstr": "3600375418559878",
            "text": "龙田现场图与视频",
            "created_at": "Thu Sep 03 10:00:00 +0800 2026",
            "pic_ids": ["one", "two"],
            "pic_infos": {
                "one": {"largest": {"url": "https://wx1.sinaimg.cn/large/one.jpg"}},
                "two": {"largest": {"url": "https://wx2.sinaimg.cn/large/two.png"}},
            },
            "page_info": {
                "media_info": {
                    "stream_url": "https://f.video.weibocdn.com/selected.mp4"
                }
            },
        }

    parsed = asyncio.run(GalleryComponent().extract("3600375418559878", fetch=fetch))
    inventory = media_inventory(parsed, EnrichmentBudget())
    assert [value.kind for value in inventory.candidates] == ["image", "image", "video"]
    assert len(inventory.assets) == 3
    assert all(
        asset.status == "unavailable" and asset.blob_ref is None
        for asset in inventory.assets
    )
    assert inventory.complete is True
    limited = media_inventory(parsed, EnrichmentBudget(max_images=1))
    assert len(limited.assets) == 2
    assert any(issue.code == "image_limit" for issue in limited.issues)


def test_upstream_component_preserves_request_context_and_downloads_media():
    requests = []

    async def request(value):
        requests.append(value)
        if value.stage == "detail":
            return UpstreamResponse(
                status_code=200,
                url=value.url,
                headers={"content-type": "application/json"},
                body={
                    "ok": 1,
                    "id": 3600375418559878,
                    "idstr": "3600375418559878",
                    "text": "龙田现场图片",
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": ["one"],
                    "pic_infos": {
                        "one": {
                            "largest": {"url": "https://wx1.sinaimg.cn/large/one.png"}
                        }
                    },
                },
            )
        return UpstreamResponse(
            status_code=200,
            url=value.url,
            headers={"content-type": "image/png"},
            body=PNG,
        )

    result = asyncio.run(
        GalleryComponent().extract(
            "3600375418559878",
            cookies={"SUB": "session-only"},
            request_fetch=request,
            max_media_bytes=len(PNG),
        )
    )

    assert result["post"]["text"] == "龙田现场图片"
    assert result["downloads"] == {
        0: {"data": PNG, "mime_type": "image/png", "status": "ready"}
    }
    assert [value.stage for value in requests] == ["detail", "media"]
    assert requests[0].headers["Referer"] == "https://weibo.com/"
    assert requests[0].headers["Origin"] == "https://weibo.com"
    assert "SUB=session-only" in requests[0].headers["Cookie"]
    assert "Cookie" not in requests[1].headers
