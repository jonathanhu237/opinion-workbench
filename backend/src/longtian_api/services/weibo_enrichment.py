"""Selected-post lookups owned by the project, with a network-free parser."""

import asyncio
import json
import time

import httpx

from longtian_api.services.collector_contracts import EnrichmentWorkerResult
from longtian_api.services.enrichment_models import EnrichedContent
from longtian_api.services.gallery_component import ComponentError, GalleryComponent
from longtian_api.services.media_inventory import media_inventory
from longtian_api.services.native_browser_contracts import BrowserUnavailable
from longtian_api.services.weibo_dom import barrier, document, text_of
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
        try:
            cookies = await self.browser.weibo_cookies()
            if not cookies.get("SUB"):
                raise WeiboAccessError("login_required")
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(10, connect=5),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                # Only the corresponding Weibo cookies are given to the broker,
                # not to the parser process, command line or a global cookie jar.
                cookie_header = "; ".join(
                    f"{name}={value}"
                    for name, value in cookies.items()
                    if name in ("SUB", "SUBP")
                )

                async def fetch(url):
                    expected = (
                        f"https://weibo.com/ajax/statuses/show?id={content_id}"
                        "&isGetLongText=true"
                    )
                    if url != expected:
                        raise WeiboAccessError("structure_changed")
                    await self.before_request()
                    async with client.stream(
                        "GET",
                        url,
                        headers={
                            "Cookie": cookie_header,
                            "Accept": "application/json",
                        },
                    ) as response:
                        if response.status_code in (401, 301, 302, 303, 307, 308):
                            raise WeiboAccessError("login_required")
                        if response.status_code == 403:
                            raise WeiboAccessError("manual_challenge_required")
                        if response.status_code == 429:
                            raise WeiboAccessError("platform_blocked_or_rate_limited")
                        if response.status_code in (404, 410):
                            raise WeiboAccessError("content_unavailable")
                        if response.status_code != 200:
                            raise WeiboAccessError("internal_error")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 1024 * 1024:
                                raise WeiboAccessError("structure_changed")
                    try:
                        value = json.loads(raw)
                    except (ValueError, UnicodeError):
                        state = barrier(
                            document(raw.decode("utf-8", errors="replace")), url, 200
                        )
                        raise WeiboAccessError(state or "structure_changed") from None
                    if not isinstance(value, dict):
                        raise WeiboAccessError("structure_changed")
                    if "ok" not in value:
                        raise WeiboAccessError("structure_changed")
                    if value.get("ok") != 1:
                        message = str(value.get("msg", value.get("message", "")))
                        for words, outcome in (
                            (("登录", "login"), "login_required"),
                            (("频繁", "频次"), "platform_blocked_or_rate_limited"),
                            (("验证", "异常访问"), "manual_challenge_required"),
                        ):
                            if any(word in message for word in words):
                                raise WeiboAccessError(outcome)
                    return value

                if self._checkpoint is None:
                    parsed = await self.parser.extract(content_id, fetch=fetch)
                    inventory = media_inventory(parsed, budget)
                    checkpoint = {}
                else:
                    _, parsed, inventory, checkpoint = self._checkpoint

            async def save_progress(current_inventory):
                if on_content is None:
                    return
                await on_content(
                    project_text(
                        parsed,
                        content_id,
                        content_url,
                        budget,
                        inventory=current_inventory,
                    )
                )

            await save_progress(inventory)
            # A separate empty cookie jar prevents account credentials from
            # being forwarded to CDN hosts, including cookies set by detail IO.
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
                )
            content = project_text(
                parsed, content_id, content_url, budget, inventory=result_inventory
            )
            if pause is not None:
                # One selected post, at most the media byte budget. Retain bytes
                # only for explicit in-process continuation; originals become
                # durable with the separate persistent-cache ticket.
                self._checkpoint = (key, parsed, inventory, checkpoint)
            else:
                self.reset()
            return EnrichmentWorkerResult(pause or "completed", content=content)
        except asyncio.CancelledError:
            self.reset()
            raise
        except WeiboAccessError as error:
            return EnrichmentWorkerResult(error.outcome)
        except BrowserUnavailable:
            return EnrichmentWorkerResult("browser_unavailable")
        except (TimeoutError, httpx.TimeoutException):
            return EnrichmentWorkerResult("timed_out")
        except ComponentError as error:
            return EnrichmentWorkerResult(
                "content_unavailable"
                if error.code == "content_unavailable"
                else "structure_changed"
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
