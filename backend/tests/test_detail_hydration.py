"""Rendered detail hydration and selected-post boundaries across platforms."""

import asyncio
from uuid import uuid4

from test_native_weibo_discovery import BrowserFixture

from opinion_workbench_api.services.enrichment_models import EnrichmentBudget
from opinion_workbench_api.services.native_browser_contracts import BrowserUnavailable
from opinion_workbench_api.services.native_weibo import (
    NativeWeiboCollector,
    _generic_detail_barrier,
    _generic_detail_text,
)
from opinion_workbench_api.services.weibo_dom import document


def test_douyin_waits_for_rendered_caption_and_ignores_other_video_text():
    identity = "7531607496412450108"
    caption = f'''<div data-e2e="detail-video-info" data-e2e-aweme-id="{identity}">
      <h1><span>原帖完整配文 <a>#话题</a></span></h1></div>
      <div data-e2e="detail-video-info" data-e2e-aweme-id="7531607496412450109">
      <h1>另一条推荐视频</h1></div>'''

    class HydratingBrowser(BrowserFixture):
        updates = 0

        async def wait_detail_update(self):
            self.updates += 1
            self.html = caption

    async def run():
        browser = HydratingBrowser(["<title>抖音</title>"])
        result = await NativeWeiboCollector(browser=browser).enrich(
            request_id=uuid4(),
            platform="dy",
            content_id=identity,
            content_url=f"https://www.douyin.com/video/{identity}",
            term="原帖",
            budget=EnrichmentBudget(),
        )
        assert browser.updates == 1
        assert result.outcome == "completed"
        assert result.content.text.coverage == "complete"
        assert result.content.text.body == "原帖完整配文 #话题"

    asyncio.run(run())


def test_xhs_follows_matching_search_card_after_soft_404_without_saving_access_url():
    identity = "6a9f82190000000011035652"
    canonical = f"https://www.xiaohongshu.com/explore/{identity}"

    class SearchBrowser(BrowserFixture):
        opened = []

        async def navigate(self, url):
            await super().navigate(url)
            self.url = "https://www.xiaohongshu.com/404?error_code=300031"

        async def open_xhs_search_result(self, search_url, content_id):
            self.opened.append((search_url, content_id))
            self.url = canonical + "?xsec_token=synthetic"
            self.html = """<div id="noteContainer"><div class="note-content">
              <div id="detail-desc"><span>笔记原文</span><a>#深圳</a></div></div>
              <div class="comments">评论者说了很多不属于原帖的内容</div></div>"""
            return True

    async def run():
        browser = SearchBrowser(["<title>小红书 - 你访问的页面不见了</title>"])
        result = await NativeWeiboCollector(browser=browser).enrich(
            request_id=uuid4(),
            platform="xhs",
            content_id=identity,
            content_url=canonical,
            term="深圳 投诉",
            budget=EnrichmentBudget(),
        )
        assert len(browser.opened) == 1
        assert browser.opened[0][1] == identity
        assert result.outcome == "completed"
        assert result.content.content_url == canonical
        assert "synthetic" not in result.content.model_dump_json()
        assert result.content.text.body == "笔记原文#深圳"

    asyncio.run(run())


def test_soft_404_is_not_analyzable_post_text():
    root = document("<title>你访问的页面不见了</title><p>当前笔记暂时无法浏览</p>")
    assert (
        _generic_detail_barrier("https://www.xiaohongshu.com/404", root, 200)
        == "content_unavailable"
    )


def test_douyin_redirect_retries_dom_read_while_owned_page_is_alive():
    class RedirectingBrowser(BrowserFixture):
        reads = 0
        updates = 0

        async def snapshot(self):
            self.reads += 1
            if self.reads == 1:
                raise BrowserUnavailable()
            return await super().snapshot()

        async def wait_detail_update(self):
            self.updates += 1

    async def run():
        browser = RedirectingBrowser(["<title>原帖话题 - 抖音</title>"])
        result = await NativeWeiboCollector(browser=browser).enrich(
            request_id=uuid4(),
            platform="dy",
            content_id="7531607496412450108",
            content_url="https://www.douyin.com/video/7531607496412450108",
            term="原帖",
            budget=EnrichmentBudget(),
        )
        assert result.outcome == "completed"
        assert browser.reads == 2
        assert browser.updates == 1

    asyncio.run(run())


def test_kuaishou_caption_excludes_comments_and_actions():
    root = document("""<div class="short-video-info"><p class="video-info-title">
      <span>作品配文</span><span>#话题</span></p><div>分享 举报 评论文字</div></div>""")
    assert _generic_detail_text(root, platform="ks") == ("作品配文#话题", False)


def test_hidden_player_error_and_post_mentions_do_not_pause_collection():
    root = document("""<title>遇到验证码怎么办</title>
      <div class="player-error" style="display:none;">
        <p class="error-title">无法连接网络，请稍后再试</p></div>
      <p class="video-info-title">有人让我登录后查看，出现验证码。</p>""")
    assert (
        _generic_detail_barrier("https://www.kuaishou.com/short-video/abc", root, 200)
        is None
    )
    root = document('<div role="dialog">访问频繁，请稍后再试</div>')
    assert (
        _generic_detail_barrier("https://www.kuaishou.com/short-video/abc", root, 200)
        == "platform_blocked_or_rate_limited"
    )


def test_plain_403_is_access_denied_without_claiming_a_manual_challenge():
    root = document("<p>Forbidden</p>")
    assert (
        _generic_detail_barrier("https://www.kuaishou.com/short-video/abc", root, 403)
        == "access_denied"
    )


def test_comment_tails_respect_parent_visibility_without_crashing():
    root = document("""<main><!-- hydration marker -->正在加载</main>
      <div hidden><!-- player marker -->无法连接网络，请稍后再试</div>""")
    assert (
        _generic_detail_barrier("https://www.douyin.com/video/123", root, 200) is None
    )
    root = document("<main><!-- hydration marker -->访问频繁，请稍后再试</main>")
    assert (
        _generic_detail_barrier("https://www.douyin.com/video/123", root, 200)
        == "platform_blocked_or_rate_limited"
    )


def test_xhs_loaded_note_with_title_and_empty_description_is_text_input():
    class LoadedBrowser(BrowserFixture):
        async def wait_detail_update(self):
            raise AssertionError("A loaded title-only note must not wait for a body")

    async def run():
        browser = LoadedBrowser(
            [
                '<div id="noteContainer"><div id="detail-title">维权举报电话清单</div>'
                '<div id="detail-desc"></div>'
                '<div class="comments">评论不属于原帖</div></div>'
            ]
        )
        result = await NativeWeiboCollector(browser=browser).enrich(
            request_id=uuid4(),
            platform="xhs",
            content_id="6a4a3d0f000000000602010b",
            content_url="https://www.xiaohongshu.com/explore/6a4a3d0f000000000602010b",
            term="龙田社区 投诉",
            budget=EnrichmentBudget(),
        )
        assert result.outcome == "completed"
        assert result.content.text.title == "维权举报电话清单"
        assert result.content.text.body == ""

    asyncio.run(run())
