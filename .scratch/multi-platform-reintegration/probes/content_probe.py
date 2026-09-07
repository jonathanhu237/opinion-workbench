"""Small, isolated upstream-tool probes; no application database or browser cookies."""
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


def requests_budget():
    import requests
    original = requests.Session.request
    remaining = [32 * 1024 * 1024]

    def bounded(self, method, url, **kw):
        if len(events) >= 12:
            raise RuntimeError("probe request budget reached")
        kw["timeout"] = 15
        kw["stream"] = True
        r = original(self, method, url, **kw)
        data = bytearray()
        for chunk in r.iter_content(65536):
            data.extend(chunk)
            remaining[0] -= len(chunk)
            if len(data) > 8 * 1024 * 1024 or remaining[0] < 0:
                r.close()
                raise RuntimeError("probe byte budget reached")
        r._content = bytes(data)
        r._content_consumed = True
        events.append({"host": urlsplit(url).hostname, "path": urlsplit(url).path,
                       "status": r.status_code, "bytes": len(data)})
        return r

    requests.Session.request = bounded


def image_check(paths):
    from PIL import Image
    result = []
    for file in paths:
        file = Path(file)
        with Image.open(file) as img:
            row = {"file": file.name, "bytes": file.stat().st_size, "size": img.size, "format": img.format}
            img.verify()
        result.append(row)
    return result


result = {"probe": kind, "auth": "anonymous; no browser cookies imported"}
try:
    if kind == "toutiao-rendered":
        sys.path.insert(0, str(WORK / "upstream/news"))
        from news_crawler.toutiao_news.toutaio_news import ToutiaoNewsCrawler
        import trafilatura
        html = (ART / "toutiao-article-browser.html").read_text()
        crawler = ToutiaoNewsCrawler("https://www.toutiao.com/article/7514236619541545498/", save_path=str(out))
        try:
            data = crawler.parse_content(html)
            result["newscrawler"] = data.model_dump() if hasattr(data, "model_dump") else data
        except Exception as exc:
            result["newscrawler_error"] = f"{type(exc).__name__}: {exc}"
        body = trafilatura.extract(html, include_comments=False, output_format="json", with_metadata=True)
        result["trafilatura"] = json.loads(body) if body else None
    elif kind == "weitoutiao":
        requests_budget()
        sys.path.insert(0, str(WORK / "upstream/weitoutiao"))
        from toutiao_crawler import ToutiaoCrawler
        crawler = ToutiaoCrawler(timeout=15, delay=0, retries=1)
        result["source_url"] = "https://www.toutiao.com/w/1856110464770120/"
        data = crawler.article(result["source_url"])
        result["metadata"] = data
        result["images"] = image_check(crawler.download_images(data, out / "images"))
    elif kind == "toutiao-article-image":
        requests_budget()
        import requests
        metadata = json.loads((ART / "toutiao-rendered/result.json").read_text())["newscrawler"]
        paths = []
        for index, url in enumerate(metadata["images"], 1):
            response = requests.get(url, headers={"Referer": metadata["news_url"]})
            response.raise_for_status()
            path = out / f"image-{index}.jpg"
            path.write_bytes(response.content)
            paths.append(path)
        result["images"] = image_check(paths)
    elif kind == "toutiao-video":
        import yt_dlp
        result["source_url"] = "https://www.toutiao.com/video/7543075682374238759/"
        class QuietLogger:
            def debug(self, msg): pass
            def warning(self, msg): events.append({"warning": msg})
            def error(self, msg): events.append({"error": msg})
        def budget(progress):
            if progress.get("downloaded_bytes", 0) > 32 * 1024 * 1024:
                raise RuntimeError("probe byte budget reached")
        with yt_dlp.YoutubeDL({
            "outtmpl": str(out / "%(id)s.%(ext)s"), "noplaylist": True,
            "socket_timeout": 15, "retries": 0, "extractor_retries": 0,
            "fragment_retries": 0, "max_filesize": 32 * 1024 * 1024,
            "format": "best[filesize<=33554432]/worst",
            "logger": QuietLogger(), "progress_hooks": [budget],
            "writeinfojson": True, "noprogress": True,
        }) as ydl:
            info = ydl.extract_info(result["source_url"], download=True)
            result["metadata"] = {k: info.get(k) for k in ["id", "title", "description", "uploader", "timestamp", "duration", "view_count", "like_count", "comment_count", "ext"]}
            result["downloaded_files"] = [{"name": p.name, "bytes": p.stat().st_size} for p in out.glob("*.mp4")]
    else:
        raise ValueError(kind)
    result["completed"] = True
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {str(exc)[:700]}"
finally:
    signal.alarm(0)
    result["network"] = events
    result["elapsed_s"] = round(time.monotonic() - started, 2)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    brief = {k: v for k, v in result.items() if k not in {"metadata", "newscrawler", "trafilatura"}}
    for name in ["metadata", "newscrawler", "trafilatura"]:
        if isinstance(result.get(name), dict):
            brief[name] = {k: (len(v) if isinstance(v, (str, list)) else v) for k, v in result[name].items()}
    print(json.dumps(brief, ensure_ascii=False, default=str))
