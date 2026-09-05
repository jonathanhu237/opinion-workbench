"""Selected-post lookups owned by the project and bounded upstream acquisition."""

import asyncio
import time
from collections import Counter
from urllib.parse import urlsplit

import httpx

from longtian_api.services.collector_contracts import EnrichmentWorkerResult
from longtian_api.services.enrichment_models import (
    AcquisitionDiagnostic,
    EnrichedContent,
)
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
        self._manual_target_url = None

    def reset(self):
        self._checkpoint = None
        self._manual_target_url = None

    @property
    def manual_target_url(self):
        """Validated selected-post context for an explicit manual recovery."""
        return self._manual_target_url

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
                        # Redirects must return through the broker as a
                        # response. Following them inside httpx would hide
                        # hops from the request budget and could cross the
                        # credential boundary before classification.
                        follow_redirects=False,
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
                        max_images=budget.max_images,
                        max_videos=budget.max_videos,
                    )
                    inventory = media_inventory(parsed, budget)
                    checkpoint = {}
                    prefetched = _remap_prefetched(parsed, inventory, budget)
                    acquisition_pause = parsed.get("pause_reason")
                    acquisition_diagnostic = _diagnostic(parsed.get("diagnostic"))
                else:
                    _, parsed, inventory, checkpoint = self._checkpoint
                    pending_pairs = _pending_upstream_pairs(
                        parsed, inventory, budget, checkpoint
                    )
                    pending_files = [file for _, file in pending_pairs]
                    remaining_bytes = budget.max_total_bytes - sum(
                        len(data) for _, data in checkpoint.values()
                    )
                    if pending_files and remaining_bytes > 0:
                        resumed = await self.parser.acquire_media(
                            content_id,
                            post=parsed["post"],
                            files=pending_files,
                            request_fetch=request_fetch,
                            cookies=scoped_cookies,
                            max_media_bytes=remaining_bytes,
                            max_images=budget.max_images,
                            max_videos=budget.max_videos,
                        )
                        prefetched = _remap_prefetched(
                            resumed,
                            inventory,
                            budget,
                            files=pending_files,
                            pairs=pending_pairs,
                        )
                        acquisition_pause = resumed.get("pause_reason")
                        acquisition_diagnostic = _diagnostic(resumed.get("diagnostic"))
                    else:
                        prefetched = {
                            candidate.position: {
                                "status": "unavailable",
                                "issue_code": "media_limit",
                            }
                            for candidate in inventory.candidates
                            if candidate.asset_id not in checkpoint
                        }
                        acquisition_pause = None
                        acquisition_diagnostic = None

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
                        diagnostic=acquisition_diagnostic,
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
                media_diagnostics = {}
                result_inventory, pause = await transfer_media(
                    inventory,
                    client=client,
                    sink=media_sink,
                    before_request=self.before_request,
                    budget=budget,
                    checkpoint=checkpoint,
                    on_progress=save_progress,
                    prefetched=prefetched,
                    diagnostics=media_diagnostics,
                )
            pause = pause or acquisition_pause
            if acquisition_diagnostic is None and media_diagnostics:
                acquisition_diagnostic = next(iter(media_diagnostics.values()))
            content = project_text(
                parsed,
                content_id,
                content_url,
                budget,
                inventory=result_inventory,
                diagnostic=acquisition_diagnostic,
            )
            if pause is not None:
                # One selected post, at most the media byte budget. Retain bytes
                # only for explicit in-process continuation; originals become
                # durable with the separate persistent-cache ticket.
                self._checkpoint = (key, parsed, result_inventory, checkpoint)
                self._manual_target_url = content_url
            else:
                self.reset()
            return EnrichmentWorkerResult(
                pause or "completed",
                content=content,
                diagnostic=acquisition_diagnostic,
            )
        except asyncio.CancelledError:
            if detail_payload is not None and save_detail_checkpoint is not None:
                try:
                    await asyncio.shield(save_detail_checkpoint())
                except (Exception, asyncio.CancelledError):
                    pass
            self.reset()
            raise
        except WeiboAccessError as error:
            if error.outcome in {
                "login_required",
                "manual_challenge_required",
                "platform_blocked_or_rate_limited",
            }:
                self._manual_target_url = content_url
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
            outcome = error.code if error.code in known else "structure_changed"
            if outcome in {
                "login_required",
                "manual_challenge_required",
                "platform_blocked_or_rate_limited",
            }:
                self._manual_target_url = content_url
            return EnrichmentWorkerResult(
                outcome,
                diagnostic=_component_diagnostic(error),
            )
        except (httpx.HTTPError, ValueError):
            return EnrichmentWorkerResult("structure_changed")


def _diagnostic(value):
    if value is None:
        return None
    try:
        return AcquisitionDiagnostic.model_validate(value)
    except (TypeError, ValueError):
        return None


def _component_diagnostic(error):
    outcome = (
        error.code
        if error.code
        in {
            "access_denied",
            "asset_blocked",
            "asset_unavailable",
            "content_unavailable",
            "login_required",
            "manual_challenge_required",
            "media_limit",
            "media_redirect",
            "parser_failed",
            "platform_blocked_or_rate_limited",
            "structure_changed",
        }
        else "structure_changed"
    )
    stage = error.stage if error.stage in ("detail", "media") else "detail"
    status_code = (
        error.status_code
        if type(error.status_code) is int and 100 <= error.status_code <= 599
        else None
    )
    asset_position = (
        error.asset_position
        if type(error.asset_position) is int and 0 <= error.asset_position <= 24
        else None
    )
    basis = (
        error.basis
        if error.basis
        in {
            "http_status",
            "explicit_platform_evidence",
            "login_redirect",
            "platform_payload",
            "browser_dom_evidence",
            "upstream_exception",
            "transport",
        }
        else ("http_status" if status_code is not None else "upstream_exception")
    )
    return AcquisitionDiagnostic(
        stage=stage,
        outcome=outcome,
        status_code=status_code,
        basis=basis,
        asset_position=asset_position,
        target="media_asset" if stage == "media" else "selected_post",
    )


def _media_kind(file):
    extension = str(file.get("metadata", {}).get("extension", "")).lower()
    if extension in ("jpg", "jpeg", "png", "webp", "gif"):
        return "image"
    if extension in ("mp4", "mov", "m3u8", "webm"):
        return "video"
    return None


def _candidate_file_pairs(parsed, inventory, budget):
    """Pair compact application positions with their original upstream files."""
    counts = Counter()
    pairs = []
    for file in parsed.get("files", ()):
        kind = _media_kind(file)
        if kind is None:
            continue
        counts[kind] += 1
        limit = budget.max_images if kind == "image" else budget.max_videos
        if counts[kind] > limit:
            continue
        if len(pairs) >= len(inventory.candidates):
            break
        pairs.append((inventory.candidates[len(pairs)], file))
    return pairs


def _remap_prefetched(parsed, inventory, budget, *, files=None, pairs=None):
    """Map gallery-dl's source positions to the compact inventory positions."""
    downloads = parsed.get("downloads", {}) if isinstance(parsed, dict) else {}
    if not isinstance(downloads, dict):
        return {}
    source = parsed if files is None else {"files": files}
    pairs = pairs or _candidate_file_pairs(source, inventory, budget)
    mapped = {}
    for candidate, file in pairs:
        metadata = file.get("metadata", {})
        number = metadata.get("num")
        source_position = number - 1 if type(number) is int else None
        if source_position in downloads:
            mapped[candidate.position] = downloads[source_position]
    return mapped


def _pending_upstream_pairs(parsed, inventory, budget, checkpoint):
    return [
        (candidate, file)
        for candidate, file in _candidate_file_pairs(parsed, inventory, budget)
        if candidate.asset_id not in checkpoint
    ]


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


def project_text(parsed, identity, url, budget, *, inventory=None, diagnostic=None):
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
    if diagnostic is not None and diagnostic.asset_position is not None:
        for issue in issues:
            if issue.get("asset_position") == diagnostic.asset_position:
                issue["diagnostic"] = diagnostic.model_dump()
                break
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
