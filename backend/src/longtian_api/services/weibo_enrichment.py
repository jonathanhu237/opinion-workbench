"""Selected-post lookups owned by the project and bounded upstream acquisition."""

import asyncio
import time
from urllib.parse import urlsplit

import httpx

from longtian_api.services.collector_contracts import EnrichmentWorkerResult
from longtian_api.services.enrichment_models import EnrichedContent
from longtian_api.services.gallery_component import (
    ComponentError,
    GalleryComponent,
    UpstreamRequest,
    UpstreamResponse,
)
from longtian_api.services.media_inventory import media_inventory
from longtian_api.services.native_browser_contracts import BrowserUnavailable
from longtian_api.services.weibo_dom import document, text_of
from longtian_api.services.weibo_media import transfer_media


class WeiboAccessError(Exception):
    def __init__(self, outcome):
        super().__init__(outcome)
        self.outcome = outcome


class WeiboEnricher:
    def __init__(self, *, browser, transport=None, request_gap_seconds=2):
        self.browser = browser
        self.transport = transport
        self.parser = GalleryComponent()
        self.request_gap_seconds = request_gap_seconds
        self._last_request = 0
        self._checkpoint = None

    def reset(self):
        self._checkpoint = None

    async def before_request(self):
        await asyncio.sleep(
            max(0, self.request_gap_seconds - (time.monotonic() - self._last_request))
        )
        self._last_request = time.monotonic()

    async def enrich(
        self,
        *,
        request_id,
        platform,
        content_id,
        content_url,
        term,
        budget,
        media_sink=None,
        on_content=None,
    ):
        if platform != "wb":
            return EnrichmentWorkerResult("content_unavailable")
        key = (content_id, content_url, budget)
        if self._checkpoint is not None and self._checkpoint[0] != key:
            self.reset()
        from_checkpoint = self._checkpoint is not None
        detail_payload = None
        detail_checkpoint_saved = False
        save_detail_checkpoint = None
        try:
            cookies = await self.browser.weibo_cookies()
            if not cookies.get("SUB"):
                raise WeiboAccessError("login_required")
            scoped_cookies = {
                name: value
                for name, value in cookies.items()
                if name in ("SUB", "SUBP") and isinstance(value, str)
            }

            async def save_detail_checkpoint():
                nonlocal detail_checkpoint_saved
                if (
                    from_checkpoint
                    or detail_checkpoint_saved
                    or detail_payload is None
                    or on_content is None
                ):
                    return
                partial_post = {
                    key: value
                    for key, value in detail_payload.items()
                    if key
                    not in {"pic_ids", "pic_infos", "page_info", "mix_media_info"}
                }
                partial = {"post": partial_post, "files": []}
                await on_content(
                    project_text(
                        partial,
                        content_id,
                        content_url,
                        budget,
                        inventory=media_inventory(partial, budget),
                    ),
                    force=True,
                )
                detail_checkpoint_saved = True

            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(10, connect=5),
                follow_redirects=False,
                trust_env=False,
            ) as client:

                async def request_fetch(request: UpstreamRequest):
                    nonlocal detail_payload
                    expected = (
                        f"https://weibo.com/ajax/statuses/show?id={content_id}"
                        "&isGetLongText=true"
                    )
                    if request.stage == "detail" and request.url != expected:
                        raise WeiboAccessError("structure_changed")
                    headers = dict(request.headers)
                    host = (urlsplit(request.url).hostname or "").lower()
                    if request.stage == "media" and not (
                        host == "weibo.com" or host.endswith(".weibo.com")
                    ):
                        headers.pop("Cookie", None)
                        headers.pop("cookie", None)
                    await self.before_request()
                    async with client.stream(
                        request.method,
                        request.url,
                        headers=headers,
                        content=request.body,
                        # The upstream detail call may follow the platform's
                        # login redirect so it can be classified from history;
                        # media redirects are intentionally kept at the CDN
                        # boundary and recorded as a missing asset.
                        follow_redirects=request.allow_redirects
                        if request.stage == "detail"
                        else False,
                    ) as response:
                        limit = (
                            1024 * 1024
                            if request.stage == "detail"
                            else budget.max_total_bytes
                        )
                        raw = bytearray()
                        overflow = False
                        async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                            if len(raw) + len(chunk) > limit:
                                overflow = True
                                break
                            raw.extend(chunk)
                        body = bytes(raw)
                        response_headers = dict(response.headers)
                        if overflow and response.status_code < 400:
                            body = b""
                            response_headers["x-longtian-error"] = (
                                "detail_limit"
                                if request.stage == "detail"
                                else "media_limit"
                            )
                        value = body
                        if request.stage == "detail" and response.status_code < 400:
                            try:
                                value = response.json()
                            except (ValueError, UnicodeError):
                                value = body
                            if isinstance(value, dict):
                                detail_payload = value
                        return UpstreamResponse(
                            status_code=response.status_code,
                            url=str(response.url),
                            headers=response_headers,
                            body=value,
                            history=tuple(
                                (item.status_code, str(item.url))
                                for item in response.history
                            ),
                            cookies=dict(response.cookies.items()),
                        )

                if not from_checkpoint:
                    parsed = await self.parser.extract(
                        content_id,
                        request_fetch=request_fetch,
                        cookies=scoped_cookies,
                        max_media_bytes=budget.max_total_bytes,
                    )
                    inventory = media_inventory(parsed, budget)
                    checkpoint = {}
                    prefetched = parsed.get("downloads", {})
                else:
                    _, parsed, inventory, checkpoint = self._checkpoint
                    prefetched = {}

            async def save_progress(current_inventory, *, force=False):
                if on_content is None:
                    return
                await on_content(
                    project_text(
                        parsed,
                        content_id,
                        content_url,
                        budget,
                        inventory=current_inventory,
                    ),
                    force=force,
                )

            if not from_checkpoint:
                await save_progress(inventory)
            # A separate empty cookie jar is retained for recovery of old
            # paused sessions. New acquisitions use the upstream downloader
            # through ``prefetched`` and never need a second media request.
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(15, connect=5),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                result_inventory, pause = await transfer_media(
                    inventory,
                    client=client,
                    sink=media_sink,
                    before_request=self.before_request,
                    budget=budget,
                    checkpoint=checkpoint,
                    on_progress=save_progress,
                    prefetched=prefetched,
                )
            if not from_checkpoint:
                pause = pause or parsed.get("pause_reason")
            content = project_text(
                parsed, content_id, content_url, budget, inventory=result_inventory
            )
            if pause is not None:
                # One selected post, at most the media byte budget. Retain bytes
                # only for explicit in-process continuation; originals become
                # durable with the separate persistent-cache ticket.
                self._checkpoint = (key, parsed, result_inventory, checkpoint)
            else:
                self.reset()
            return EnrichmentWorkerResult(pause or "completed", content=content)
        except asyncio.CancelledError:
            if detail_payload is not None and save_detail_checkpoint is not None:
                try:
                    await asyncio.shield(save_detail_checkpoint())
                except (Exception, asyncio.CancelledError):
                    pass
            self.reset()
            raise
        except WeiboAccessError as error:
            return EnrichmentWorkerResult(error.outcome)
        except BrowserUnavailable:
            return EnrichmentWorkerResult("browser_unavailable")
        except (TimeoutError, httpx.TimeoutException):
            return EnrichmentWorkerResult("timed_out")
        except ComponentError as error:
            known = {
                "content_unavailable",
                "login_required",
                "manual_challenge_required",
                "platform_blocked_or_rate_limited",
                "access_denied",
            }
            return EnrichmentWorkerResult(
                error.code if error.code in known else "structure_changed"
            )
        except (httpx.HTTPError, ValueError):
            return EnrichmentWorkerResult("structure_changed")


def _post_text(post):
    raw = (
        post.get("longText", {}).get("longTextContent")
        if isinstance(post.get("longText"), dict)
        else None
    )
    plain = False
    if not isinstance(raw, str):
        raw = post.get("text_raw")
        plain = isinstance(raw, str)
    if not isinstance(raw, str):
        raw = post.get("text", "")
    root = document(raw) if isinstance(raw, str) and raw and not plain else None
    text = raw.strip() if plain else text_of(root) if root is not None else ""
    incomplete = root is not None and bool(
        root.xpath(
            '//*[contains(concat(" ", normalize-space(@class), " "), " expand ")]'
        )
    )
    return text, incomplete, raw == ""


def project_text(parsed, identity, url, budget, *, inventory=None):
    inventory = inventory or media_inventory(parsed, budget)
    post = parsed["post"]
    body, incomplete, empty_caption = _post_text(post)
    if "retweeted_status" in post:
        original = post["retweeted_status"]
        if isinstance(original, dict):
            quoted, quote_incomplete, _ = _post_text(original)
            if quoted:
                body += "\n\n【转发附带原帖】\n" + quoted
            incomplete = (
                incomplete
                or quote_incomplete
                or not quoted
                or bool(
                    original.get("retweeted_status")
                    or (original.get("isLongText") and not original.get("longText"))
                )
            )
        else:
            incomplete = True
    issues = []
    coverage = "complete"
    explicit_empty_caption = empty_caption and bool(inventory.assets)
    if not body and not explicit_empty_caption:
        coverage = "unavailable"
        issues.append({"code": "text_unavailable", "asset_position": None})
    elif incomplete:
        coverage = "partial"
        issues.append({"code": "text_incomplete", "asset_position": None})
    if len(body) > budget.max_text_chars:
        body = body[: budget.max_text_chars]
        coverage = "partial"
        issues.append({"code": "text_limit", "asset_position": None})
    issues.extend(issue.model_dump() for issue in inventory.issues)
    return EnrichedContent(
        schema_version=1,
        platform="wb",
        content_id=identity,
        content_url=url,
        acquired_at=time.time_ns() // 1_000_000,
        extractor_version="wb-enrichment-v1",
        status="ready"
        if not issues
        else "partial"
        if body or any(a.status == "ready" for a in inventory.assets)
        else "unavailable",
        text={"title": "", "body": body, "coverage": coverage},
        detected_modalities=["text", *inventory.modalities],
        media_inventory_complete=inventory.complete,
        assets=list(inventory.assets),
        issues=issues,
    )
