"""Bounded selected-post file transfer; never a URL handed to the model."""

import asyncio
import hashlib
import io
import time
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

import httpx
from PIL import Image

from longtian_api.services.enrichment_models import EnrichmentAsset, EnrichmentIssue
from longtian_api.services.media_inventory import missing_asset
from longtian_api.services.settled_tasks import settle
from longtian_api.services.video_probe import VideoProbe, VideoProbeError


class MediaFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def allowed_media_url(url):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        return (
            parts.scheme == "https"
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and not parts.fragment
            and "\\" not in url
            and len(url) <= 4096
            and not any(ord(c) <= 32 for c in url)
            and any(
                host == suffix or host.endswith("." + suffix)
                for suffix in ("sinaimg.cn", "weibocdn.com")
            )
        )
    except ValueError:
        return False


def image_asset(candidate, data, mime_type):
    formats = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
    if mime_type not in formats:
        raise MediaFailure("unsupported_media_type")
    try:
        with Image.open(io.BytesIO(data), formats=[formats[mime_type]]) as value:
            width, height = value.size
            if (
                not 1 <= width <= 32768
                or not 1 <= height <= 32768
                or width * height > 40_000_000
            ):
                raise MediaFailure("media_limit")
            if getattr(value, "n_frames", 1) != 1:
                raise MediaFailure("unsupported_media_type")
            value.verify()
        with Image.open(io.BytesIO(data), formats=[formats[mime_type]]) as value:
            value.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise MediaFailure("invalid_media") from None
    return EnrichmentAsset(
        asset_id=candidate.asset_id,
        position=candidate.position,
        kind="image",
        role="content",
        status="ready",
        blob_ref=candidate.asset_id,
        sha256=hashlib.sha256(data).hexdigest(),
        mime_type=mime_type,
        byte_size=len(data),
        width=width,
        height=height,
        duration_ms=None,
        audio_track="not_applicable",
        coverage="complete",
        issue_code=None,
    )


@dataclass
class TransferAllowance:
    remaining_bytes: int
    deadline: float

    def charge(self, size):
        remaining = self.remaining_bytes
        self.remaining_bytes = max(0, remaining - size)
        if size > remaining:
            raise MediaFailure("media_limit")


class MediaPause(Exception):
    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(outcome)


async def download_media(candidate, *, client, before_request, allowance, probe):
    if not allowed_media_url(candidate.url):
        raise MediaFailure("unsafe_media_url")
    if allowance.remaining_bytes <= 0:
        raise MediaFailure("media_limit")
    async with asyncio.timeout(min(20, allowance.deadline - time.monotonic())):
        await before_request()
        async with client.stream(
            "GET",
            candidate.url,
            headers={"Accept": "image/*" if candidate.kind == "image" else "video/mp4"},
        ) as response:
            if response.status_code in (401, 429):
                raise MediaPause(
                    {
                        401: "login_required",
                        429: "platform_blocked_or_rate_limited",
                    }[response.status_code]
                )
            if response.status_code == 403:
                sample = (
                    (await response.aread())[: 256 * 1024]
                    .decode("utf-8", errors="ignore")
                    .lower()
                )
                if any(
                    word in sample
                    for word in (
                        "安全验证",
                        "请完成验证",
                        "滑动验证",
                        "拖动滑块",
                        "验证码",
                        "captcha",
                        "challenge",
                        "异常访问",
                        "访问异常",
                    )
                ):
                    raise MediaPause("manual_challenge_required")
                raise MediaFailure("asset_blocked")
            if 300 <= response.status_code < 400:
                raise MediaFailure("media_redirect")
            if response.status_code in (404, 410):
                raise MediaFailure("asset_unavailable")
            if response.status_code != 200:
                raise MediaFailure("download_failed")
            mime_type = (
                response.headers.get("content-type", "").split(";")[0].strip().lower()
            )
            accepted = (
                ("image/png", "image/jpeg", "image/webp")
                if candidate.kind == "image"
                else ("video/mp4",)
            )
            if mime_type not in accepted:
                raise MediaFailure("unsupported_media_type")
            raw = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                allowance.charge(len(chunk))
                raw.extend(chunk)
            data = bytes(raw)
            if not data:
                raise MediaFailure("invalid_media")
        asset = (
            await settle(asyncio.to_thread(image_asset, candidate, data, mime_type))
            if candidate.kind == "image"
            else await probe.inspect(candidate, data)
        )
        return asset, data


async def transfer_media(
    inventory,
    *,
    client,
    sink,
    before_request,
    budget,
    checkpoint,
    probe=None,
    on_progress=None,
    prefetched=None,
):
    probe = probe or VideoProbe()
    prefetched = prefetched or {}
    assets = list(inventory.assets)
    issues = [issue for issue in inventory.issues if issue.asset_position is None]
    pause = None
    allowance = TransferAllowance(
        budget.max_total_bytes - sum(len(data) for _, data in checkpoint.values()),
        time.monotonic() + 100,
    )
    for candidate in inventory.candidates:
        if pause is not None:
            continue
        try:
            prefetched_value = prefetched.get(candidate.position)
            if prefetched_value is not None:
                if prefetched_value.get("status") != "ready":
                    assets[candidate.position] = missing_asset(
                        candidate, prefetched_value.get("issue_code", "download_failed")
                    )
                    continue
                data = prefetched_value.get("data")
                mime_type = prefetched_value.get("mime_type")
                if not isinstance(data, bytes) or not isinstance(mime_type, str):
                    raise MediaFailure("invalid_media")
                allowance.charge(len(data))
                if candidate.kind == "image":
                    asset = await settle(
                        asyncio.to_thread(image_asset, candidate, data, mime_type)
                    )
                else:
                    if mime_type != "video/mp4":
                        raise MediaFailure("unsupported_media_type")
                    asset = await probe.inspect(candidate, data)
                checkpoint[candidate.asset_id] = (asset, data)
            elif candidate.asset_id in checkpoint:
                asset, data = checkpoint[candidate.asset_id]
            else:
                asset, data = await download_media(
                    candidate,
                    client=client,
                    before_request=before_request,
                    allowance=allowance,
                    probe=probe,
                )
                checkpoint[candidate.asset_id] = (asset, data)
            if sink is None:
                raise MediaFailure("download_failed")
            await settle(asyncio.to_thread(sink.write_asset, candidate.asset_id, data))
            assets[candidate.position] = asset
            if on_progress is not None:
                pending_issues = [
                    EnrichmentIssue(
                        code=value.issue_code, asset_position=value.position
                    )
                    for value in assets
                    if value.issue_code
                ]
                await on_progress(
                    replace(
                        inventory,
                        assets=tuple(assets),
                        issues=tuple(issues + pending_issues),
                    )
                )
        except MediaPause as error:
            pause = error.outcome
        except (httpx.TimeoutException, TimeoutError):
            assets[candidate.position] = missing_asset(candidate, "download_timeout")
        except httpx.HTTPError:
            assets[candidate.position] = missing_asset(candidate, "download_failed")
        except (MediaFailure, VideoProbeError) as error:
            assets[candidate.position] = missing_asset(candidate, error.code)
    issues.extend(
        EnrichmentIssue(code=asset.issue_code, asset_position=asset.position)
        for asset in assets
        if asset.issue_code
    )
    return replace(inventory, assets=tuple(assets), issues=tuple(issues)), pause
