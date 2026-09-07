"""Run upstream single-post entry points with anonymous sessions and small budgets."""
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "runtime/tool-validation"
ART = WORK / "artifacts"
kind = sys.argv[1]
out = ART / kind
out.mkdir(exist_ok=True)
os.chdir(out)
events = []
started = time.monotonic()


def deadline(*_):
    raise TimeoutError("probe wall-clock budget of 75 seconds reached")


signal.signal(signal.SIGALRM, deadline)
signal.alarm(75)


def curl_budget():
    from curl_cffi.requests import AsyncSession, Response
    original = AsyncSession.request
    iterator = Response.aiter_content
    total = [0]
    admitted = [0]
    async def bounded(self, method, url, **kw):
        admitted[0] += 1
        if admitted[0] > (30 if kind.startswith("xhs") or kind == "ks-share" else 12):
            raise RuntimeError("probe request budget reached")
        kw["timeout"] = 15
        r = await original(self, method, url, **kw)
        events.append({"host": urlsplit(url).hostname, "path": urlsplit(url).path,
                       "status": r.status_code, "content_length": r.headers.get("content-length")})
        return r
    async def chunks(self, *a, **kw):
        async for chunk in iterator(self, *a, **kw):
            total[0] += len(chunk)
            if total[0] > 32 * 1024 * 1024:
                raise RuntimeError("probe byte budget reached")
            yield chunk
    AsyncSession.request = bounded
    Response.aiter_content = chunks


async def run():
    if kind in {"douyin-parse-video", "ks-parse-video"}:
        import dataclasses
        import httpx
        sys.path.insert(0, str(WORK / "upstream/parse-video/src"))
        from parse_video_py.parser import douyin, kuaishou
        parser_module = douyin if kind == "douyin-parse-video" else kuaishou
        async def observe(response):
            if len(events) >= 6:
                raise RuntimeError("probe request budget reached")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 8 * 1024 * 1024:
                    raise RuntimeError("probe response byte budget reached")
            response._content = bytes(body)
            events.append({"host": response.url.host, "path": response.url.path,
                           "status": response.status_code, "bytes": len(body)})
        parser_module.create_async_client = lambda **kw: httpx.AsyncClient(
            timeout=15, trust_env=False, event_hooks={"response": [observe]}, **kw)
        result["source_url"] = ("https://www.douyin.com/video/7538854540977671462"
                                if kind == "douyin-parse-video" else "https://v.kuaishou.com/Js096ZVF")
        parser = douyin.DouYin() if kind == "douyin-parse-video" else kuaishou.KuaiShou()
        data = await parser.parse_share_url(result["source_url"])
        if data.video_url:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, trust_env=False) as client:
                async with client.stream("GET", data.video_url) as response:
                    response.raise_for_status()
                    size = 0
                    with (out / "video.mp4").open("wb") as file:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 32 * 1024 * 1024:
                                raise RuntimeError("probe media byte budget reached")
                            file.write(chunk)
                    events.append({"host": response.url.host, "status": response.status_code, "bytes": size})
        return dataclasses.asdict(data)
    if kind.startswith("xhs"):
        curl_budget()
        sys.path.insert(0, str(WORK / "upstream/xhs"))
        from source import XHS
        links = json.loads((ART / "xhs-discovery-browser.json").read_text())["content_links"]
        target = "ins大字报风景手机壁纸合集24" if kind == "xhs-images" else "黄石国家公园一游客被野牛顶飞2米高"
        url = next(x["href"] for x in links if x["text"] == target)
        result["source_url"] = url.split("?")[0]
        result["url_has_discovery_token"] = True
        async with XHS(work_path=str(out), folder_name="media", timeout=15, max_retry=0,
                       record_data=False, download_record=False, cookie="") as app:
            return await app.extract(url, download=True, check_record=False)
    if kind in {"ks", "ks-rendered", "ks-share"}:
        curl_budget()
        sys.path.insert(0, str(WORK / "upstream/ks"))
        from source.config.config import Config
        Config.default.update(work_path=str(out), folder_name="media", max_retry=0,
                              timeout=15, max_workers=1, cookies="", data_record=False)
        Config.read = lambda self: Config.default.copy()
        from source import KS
        result["source_url"] = "https://www.kuaishou.com/short-video/3x5jvmsmmiahx3m"
        async with KS(server_mode=True) as app:
            if "--ignore-tool-record" in sys.argv:
                app.database.record = 0
                result["tool_history"] = "disabled via existing Database.record setting for bounded recovery probe"
            if kind == "ks-share" and "--cached-detail" in sys.argv:
                result["source_url"] = "https://v.kuaishou.com/Js096ZVF"
                result["acquisition"] = "reuse previously successful upstream metadata; no detail refetch"
                data = json.loads((out / "metadata.json").read_text())
                if not isinstance(data, dict):
                    import sqlite3
                    from source.record.manager import RecordManager
                    with sqlite3.connect(f"file:{out / 'Data/DetailData.db'}?mode=ro", uri=True) as database:
                        row = database.execute('SELECT * FROM Download WHERE 作品ID=?', ("3xdrexrgrq8nrq9",)).fetchone()
                    if row is None:
                        raise RuntimeError("no successful metadata cached by the isolated upstream tool")
                    data = dict(zip([field[0] for field in RecordManager.detail], row))
                if isinstance(data["download"], str):
                    data["download"] = data["download"].split()
                await app.download.run([data])
                return data
            if kind == "ks-share":
                result["source_url"] = "https://v.kuaishou.com/Js096ZVF"
                links = await app.examiner.run(result["source_url"])
                result["resolved_count"] = len(links)
                if not links: return "No detail link resolved"
                return await app.detail_one(links[0], download=True)
            if kind == "ks-rendered":
                async def rendered(*a, **kw):
                    return (ART / "ks-sample-browser.html").read_text()
                app.detail_html.run = rendered
                result["acquisition"] = "previously captured rendered browser HTML"
            return await app.detail_one(result["source_url"], download=True)
    if kind == "douyin-f2":
        import httpx
        sys.path.insert(0, str(WORK / "upstream/f2"))
        from f2.crawlers.base_crawler import BaseCrawler
        from f2.log.logger import logger, trace_logger
        logger.disabled = True
        trace_logger.disabled = True
        original_init = BaseCrawler.__init__
        def initialize(self, kwargs=None, **kw):
            original_init(self, (kwargs or {}) | {"max_tasks": 1, "max_connections": 1,
                                                 "max_retries": 1, "timeout": 12}, **kw)
        BaseCrawler.__init__ = initialize
        BaseCrawler._create_mount = lambda self, async_mode=False: {
            "all://": (httpx.AsyncHTTPTransport if async_mode else httpx.HTTPTransport)(retries=0)
        }
        # Observe status/body size only; never print token values or request headers.
        for client, asynchronous in [(httpx.Client, False), (httpx.AsyncClient, True)]:
            original = client.send
            def wrapper(original, asynchronous):
                def record(r):
                    events.append({"host": r.url.host, "path": r.url.path,
                                   "status": r.status_code, "bytes": len(r.content)})
                    return r
                if asynchronous:
                    async def send(self, *a, **kw):
                        if len(events) >= 6: raise RuntimeError("request budget reached")
                        return record(await original(self, *a, **kw))
                else:
                    def send(self, *a, **kw):
                        if len(events) >= 6: raise RuntimeError("request budget reached")
                        return record(original(self, *a, **kw))
                return send
            client.send = wrapper(original, asynchronous)
        from f2.apps.douyin.crawler import DouyinCrawler
        from f2.apps.douyin.model import PostDetail
        result["source_url"] = "https://www.douyin.com/video/7538854540977671462"
        async with DouyinCrawler({"cookie": "", "max_retries": 1, "timeout": 12}) as app:
            return await app.fetch_post_detail(PostDetail(aweme_id="7538854540977671462"))
    raise ValueError(kind)


result = {"probe": kind, "auth": "anonymous; no browser cookies imported"}
try:
    data = asyncio.run(run())
    valid_metadata = isinstance(data, dict) and bool(data) or isinstance(data, list) and any(isinstance(row, dict) and row for row in data)
    (out / ("metadata.json" if valid_metadata else "return-diagnostic.json")).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    result["return_type"] = type(data).__name__
    result["data_nonempty"] = bool(data)
    if isinstance(data, str): result["message"] = data
    if isinstance(data, dict): result["keys"] = list(data)
    if isinstance(data, list): result["rows"] = len(data)
    result["completed"] = True
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
finally:
    signal.alarm(0)
    result["network"] = events
    result["elapsed_s"] = round(time.monotonic() - started, 2)
    result["media"] = [{"name": p.name, "bytes": p.stat().st_size} for p in out.rglob("*") if p.is_file() and p.suffix.lower() in {".mp4", ".jpg", ".jpeg", ".png", ".webp"}]
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))
