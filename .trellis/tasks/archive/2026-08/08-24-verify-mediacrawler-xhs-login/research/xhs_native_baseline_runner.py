"""Secret-safe two-run baseline helper for Xiaohongshu authentication.

Run from an isolated temporary working directory. The working directory owns
the Chrome profile; this helper only imports MediaCrawler source from the
explicit ``MEDIACRAWLER_SOURCE_ROOT`` environment variable.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


source_root = Path(os.environ["MEDIACRAWLER_SOURCE_ROOT"]).resolve()
sys.path.insert(0, str(source_root))

import config  # noqa: E402
from media_platform.xhs.client import XiaoHongShuClient  # noqa: E402
from media_platform.xhs.core import XiaoHongShuCrawler  # noqa: E402
from media_platform.xhs.login import XiaoHongShuLogin  # noqa: E402
from tools import utils  # noqa: E402


def configure_auth_only_run() -> None:
    config.PLATFORM = "xhs"
    config.XHS_INTERNATIONAL = False
    config.LOGIN_TYPE = "qrcode"
    config.CRAWLER_TYPE = "auth_validation"
    config.ENABLE_IP_PROXY = False
    config.ENABLE_CDP_MODE = True
    config.CDP_CONNECT_EXISTING = False
    config.CDP_HEADLESS = False
    config.SAVE_LOGIN_STATE = True
    config.AUTO_CLOSE_BROWSER = True
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_GET_WORDCLOUD = False
    config.SAVE_DATA_OPTION = "jsonl"


async def run() -> int:
    configure_auth_only_run()

    events: list[str] = []
    pong_results: list[bool] = []
    login_entered = 0
    qrcode_shown = 0
    collection_calls = 0

    original_pong = XiaoHongShuClient.pong
    original_begin = XiaoHongShuLogin.begin
    original_show_qrcode = utils.show_qrcode
    original_search = XiaoHongShuCrawler.search
    original_detail = XiaoHongShuCrawler.get_specified_notes
    original_creators = XiaoHongShuCrawler.get_creators_and_notes

    async def observed_pong(client: XiaoHongShuClient) -> bool:
        result = bool(await original_pong(client))
        pong_results.append(result)
        events.append("pong_true" if result else "pong_false")
        print(f"AUTH_VALIDATION_PONG result={str(result).lower()}", flush=True)
        return result

    async def observed_begin(login: XiaoHongShuLogin) -> None:
        nonlocal login_entered
        login_entered += 1
        events.append("login_entered")
        print("AUTH_VALIDATION_LOGIN entered=true", flush=True)
        await original_begin(login)

    def suppress_terminal_qrcode(_: str) -> None:
        nonlocal qrcode_shown
        qrcode_shown += 1
        events.append("qrcode_visible_in_browser")
        print("AUTH_VALIDATION_QR_READY visible_browser=true", flush=True)

    async def reject_collection(*args, **kwargs):
        nonlocal collection_calls
        collection_calls += 1
        raise AssertionError("auth_validation unexpectedly entered content collection")

    XiaoHongShuClient.pong = observed_pong
    XiaoHongShuLogin.begin = observed_begin
    utils.show_qrcode = suppress_terminal_qrcode
    XiaoHongShuCrawler.search = reject_collection
    XiaoHongShuCrawler.get_specified_notes = reject_collection
    XiaoHongShuCrawler.get_creators_and_notes = reject_collection

    crawler = XiaoHongShuCrawler()
    post_start_pong = False
    exit_code = 0
    try:
        await crawler.start()
        post_start_pong = bool(await crawler.xhs_client.pong())
        if not post_start_pong:
            exit_code = 2
    except SystemExit:
        events.append("login_ended_without_success")
        exit_code = 3
    except BaseException as exc:
        events.append(f"error_{type(exc).__name__}")
        print(f"AUTH_VALIDATION_ERROR type={type(exc).__name__}", flush=True)
        exit_code = 4
    finally:
        manager = getattr(crawler, "cdp_manager", None)
        context = getattr(crawler, "browser_context", None)
        if manager is not None:
            try:
                await manager.cleanup(force=True)
            except BaseException as exc:
                print(
                    f"AUTH_VALIDATION_CLEANUP_ERROR type={type(exc).__name__}",
                    flush=True,
                )
                exit_code = 5
        elif context is not None:
            try:
                await context.close()
            except BaseException as exc:
                print(
                    f"AUTH_VALIDATION_CLEANUP_ERROR type={type(exc).__name__}",
                    flush=True,
                )
                exit_code = 5

        XiaoHongShuClient.pong = original_pong
        XiaoHongShuLogin.begin = original_begin
        utils.show_qrcode = original_show_qrcode
        XiaoHongShuCrawler.search = original_search
        XiaoHongShuCrawler.get_specified_notes = original_detail
        XiaoHongShuCrawler.get_creators_and_notes = original_creators

    results = ",".join(str(result).lower() for result in pong_results)
    sequence = ",".join(events)
    print(
        "AUTH_VALIDATION_SUMMARY "
        f"exit_code={exit_code} login_entered={login_entered} "
        f"qrcode_shown={qrcode_shown} pong_results={results} "
        f"post_start_pong={str(post_start_pong).lower()} "
        f"collection_calls={collection_calls} sequence={sequence}",
        flush=True,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
