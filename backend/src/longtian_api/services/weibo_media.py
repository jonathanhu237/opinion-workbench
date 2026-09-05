"""Bounded selected-post file transfer; never a URL handed to the model."""

import asyncio
import hashlib
import io
import time
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

import httpx
from PIL import Image

from longtian_api.services.enrichment_models import (
    AcquisitionDiagnostic,
    EnrichmentAsset,
    EnrichmentIssue,
)
from longtian_api.services.media_inventory import missing_asset
from longtian_api.services.settled_tasks import settle
from longtian_api.services.video_probe import VideoProbe, VideoProbeError


class MediaFailure(Exception):
    def __init__(self, code, *, status_code=None, basis=None):
        self.code = code
        self.status_code = status_code
        self.basis = basis
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
    def __init__(self, outcome, *, status_code=None, basis=None):
        self.outcome = outcome
        self.status_code = status_code
        self.basis = basis
        super().__init__(outcome)


_CHALLENGE_WORDS = (
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


async def _read_bounded_sample(response, allowance, limit=256 * 1024):
    """Read only the diagnostic prefix and charge bytes to the media budget."""

    remaining = min(limit, allowance.remaining_bytes)
    if remaining <= 0:
        return b""
    raw = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
        if not chunk:
            continue
        take = chunk[: remaining - len(raw)]
        raw.extend(take)
        allowance.charge(len(take))
        if len(raw) >= remaining:
            break
    return bytes(raw)


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
                    }[response.status_code],
                    status_code=response.status_code,
                    basis="http_status",
                )
            if response.status_code == 403:
                sample = (
                    (await _read_bounded_sample(response, allowance))
                    .decode("utf-8", errors="ignore")
                    .lower()
                )
                if any(word in sample for word in _CHALLENGE_WORDS):
                    raise MediaPause(
                        "manual_challenge_required",
                        status_code=403,
                        basis="explicit_platform_evidence",
                    )
                raise MediaFailure(
                    "asset_blocked", status_code=403, basis="http_status"
                )
            if 300 <= response.status_code < 400:
                raise MediaFailure(
                    "media_redirect",
                    status_code=response.status_code,
                    basis="http_status",
                )
            if response.status_code in (404, 410):
                raise MediaFailure(
                    "asset_unavailable",
                    status_code=response.status_code,
                    basis="http_status",
                )
            if response.status_code != 200:
                raise MediaFailure(
                    "download_failed",
                    status_code=response.status_code,
                    basis="http_status",
                )
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
    diagnostics=None,
):
    probe = probe or VideoProbe()
    prefetched = prefetched or {}
    diagnostics = diagnostics if diagnostics is not None else {}
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
                    diagnostic = _coerce_diagnostic(
                        prefetched_value.get("diagnostic"), candidate.position
                    )
                    if diagnostic is not None:
                        diagnostics[candidate.position] = diagnostic
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
            diagnostics[candidate.position] = _media_diagnostic(
                candidate.position,
                error.outcome,
                status_code=error.status_code,
                basis=error.basis,
            )
        except (httpx.TimeoutException, TimeoutError):
            assets[candidate.position] = missing_asset(candidate, "download_timeout")
            diagnostics[candidate.position] = _media_diagnostic(
                candidate.position,
                "parser_failed",
                basis="transport",
            )
        except httpx.HTTPError:
            assets[candidate.position] = missing_asset(candidate, "download_failed")
            diagnostics[candidate.position] = _media_diagnostic(
                candidate.position,
                "parser_failed",
                basis="transport",
            )
        except (MediaFailure, VideoProbeError) as error:
            code = getattr(error, "code", "parser_failed")
            assets[candidate.position] = missing_asset(candidate, code)
            diagnostics[candidate.position] = _media_diagnostic(
                candidate.position,
                code,
                status_code=getattr(error, "status_code", None),
                basis=getattr(error, "basis", None),
            )
    issues.extend(
        EnrichmentIssue(
            code=asset.issue_code,
            asset_position=asset.position,
            diagnostic=diagnostics.get(asset.position),
        )
        for asset in assets
        if asset.issue_code
    )
    return replace(inventory, assets=tuple(assets), issues=tuple(issues)), pause


def _diagnostic_outcome(code):
    return {
        "access_denied": "access_denied",
        "asset_blocked": "access_denied",
        "asset_unavailable": "asset_unavailable",
        "media_limit": "media_limit",
        "media_redirect": "media_redirect",
        "login_required": "login_required",
        "manual_challenge_required": "manual_challenge_required",
        "platform_blocked_or_rate_limited": "platform_blocked_or_rate_limited",
        "content_unavailable": "content_unavailable",
        "structure_changed": "structure_changed",
    }.get(code, "parser_failed")


def _media_diagnostic(position, outcome, *, status_code=None, basis=None):
    if type(status_code) is not int or not 100 <= status_code <= 599:
        status_code = None
    return AcquisitionDiagnostic(
        stage="media",
        outcome=_diagnostic_outcome(outcome),
        status_code=status_code,
        basis=basis
        if basis
        in {
            "http_status",
            "explicit_platform_evidence",
            "login_redirect",
            "platform_payload",
            "browser_dom_evidence",
            "upstream_exception",
            "transport",
        }
        else ("http_status" if status_code is not None else "upstream_exception"),
        asset_position=position,
        target="media_asset",
    )


def _coerce_diagnostic(value, position):
    if not isinstance(value, dict):
        return None
    try:
        diagnostic = AcquisitionDiagnostic.model_validate(value)
    except (TypeError, ValueError):
        return None
    if diagnostic.stage != "media":
        return None
    if diagnostic.asset_position is None:
        return diagnostic.model_copy(update={"asset_position": position})
    return diagnostic if diagnostic.asset_position == position else None
