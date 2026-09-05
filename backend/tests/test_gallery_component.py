"""Pinned real parser, isolated process, synthetic platform transport only."""

import asyncio

from enrichment_fixtures import PNG

from longtian_api.gallery_worker import BridgeResponse, _classify_response
from longtian_api.services.gallery_component import GalleryComponent, UpstreamResponse


def test_upstream_classification_requires_trusted_redirect_or_platform_evidence():
    arbitrary = BridgeResponse(
        {
            "kind": "response",
            "status_code": 302,
            "url": "https://weibo.com/ajax/statuses/show?id=3600375418559878",
            "headers": {"Location": "https://untrusted.example/login"},
            "body": {"encoding": "base64", "value": ""},
        }
    )
    assert _classify_response(arbitrary, stage="detail") == "access_denied"

    misleading = BridgeResponse(
        {
            "kind": "response",
            "status_code": 403,
            "url": "https://weibo.com/ajax/statuses/show?id=3600375418559878",
            "headers": {"Location": "https://untrusted.example/challenge"},
            "body": {"encoding": "base64", "value": ""},
        }
    )
    assert _classify_response(misleading, stage="detail") == "access_denied"

    login = BridgeResponse(
        {
            "kind": "response",
            "status_code": 302,
            "url": "https://weibo.com/ajax/statuses/show?id=3600375418559878",
            "headers": {"Location": "https://passport.weibo.com/visitor/login"},
            "body": {"encoding": "base64", "value": ""},
        }
    )
    assert _classify_response(login, stage="detail") == "login_required"

    challenge = BridgeResponse(
        {
            "kind": "response",
            "status_code": 302,
            "url": "https://weibo.com/ajax/statuses/show?id=3600375418559878",
            "headers": {"Location": "https://security.weibo.com/verify"},
            "body": {"encoding": "base64", "value": ""},
        }
    )
    assert _classify_response(challenge, stage="detail") == (
        "manual_challenge_required"
    )

    user_text = BridgeResponse(
        {
            "kind": "response",
            "status_code": 403,
            "url": "https://weibo.com/ajax/statuses/show?id=3600375418559878",
            "headers": {"Content-Type": "application/json"},
            "body": {
                "encoding": "json",
                "value": {"ok": 0, "text": "这是一条提到验证码的普通内容"},
            },
        }
    )
    assert _classify_response(user_text, stage="detail") == "access_denied"


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


def test_upstream_media_resume_downloads_only_pending_files_without_detail_lookup():
    requests = []

    async def request(value):
        requests.append(value)
        return UpstreamResponse(
            status_code=200,
            url=value.url,
            headers={"content-type": "image/png"},
            body=PNG,
        )

    result = asyncio.run(
        GalleryComponent().acquire_media(
            "3600375418559878",
            post={"idstr": "3600375418559878", "text": "已保存正文"},
            files=[
                {
                    "url": "https://wx1.sinaimg.cn/large/pending.png",
                    "metadata": {
                        "extension": "png",
                        "filename": "pending.png",
                        "num": 2,
                    },
                }
            ],
            cookies={"SUB": "session-only"},
            request_fetch=request,
            max_media_bytes=len(PNG),
        )
    )

    assert result["post"]["idstr"] == "3600375418559878"
    assert result["downloads"][1]["status"] == "ready"
    assert [value.stage for value in requests] == ["media"]


def test_upstream_media_count_budget_prevents_excluded_downloads():
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
                    "text": "两张现场图",
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": ["one", "two"],
                    "pic_infos": {
                        "one": {
                            "largest": {"url": "https://wx1.sinaimg.cn/large/one.png"}
                        },
                        "two": {
                            "largest": {"url": "https://wx2.sinaimg.cn/large/two.png"}
                        },
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
            max_images=1,
        )
    )

    assert len([value for value in requests if value.stage == "media"]) == 1
    assert len(result["files"]) == 2
