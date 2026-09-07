"""Read public pages in a fresh, task-owned Chrome profile; never attach to 9222."""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "runtime/tool-validation"
PAGES = {
    "toutiao-article": "https://www.toutiao.com/article/7514236619541545498/",
    "xhs-discovery": "https://www.xiaohongshu.com/explore",
    "ks-discovery": "https://www.kuaishou.com/short-video",
    "douyin-video": "https://www.douyin.com/video/7538854540977671462",
    "ks-sample": "https://www.kuaishou.com/short-video/3x5jvmsmmiahx3m",
    "ks-home": "https://www.kuaishou.com/",
    "weitoutiao": "https://www.toutiao.com/w/1856110464770120/",
}


async def main():
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(WORK / "browser"), channel="chrome", headless=False,
            viewport={"width": 1280, "height": 900},
        )
        try:
            for label, url in PAGES.items():
                if sys.argv[1:] and label not in sys.argv[1:]:
                    continue
                page = await ctx.new_page()
                result = {"source_url": url, "mode": "fresh task-owned Chrome; anonymous"}
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    await page.wait_for_timeout(4500)
                    result.update(status=response.status if response else None,
                                  url=page.url, title=await page.title())
                    result["visible_text"] = (await page.locator("body").inner_text(timeout=5000))[:14000]
                    result["content_links"] = await page.locator("a[href]").evaluate_all(
                        "els => els.map(e => ({text:e.innerText,href:e.href})).filter(e => /explore\\/|short-video\\/|article\\/|video\\//.test(e.href)).slice(0,35)"
                    )
                    (WORK / "artifacts" / f"{label}-browser.html").write_text(await page.content())
                    await page.screenshot(path=str(WORK / "artifacts" / f"{label}-browser.png"))
                except Exception as exc:
                    result["error"] = f"{type(exc).__name__}: {str(exc)[:250]}"
                (WORK / "artifacts" / f"{label}-browser.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
                print(json.dumps({k: (v[:1100] if k == "visible_text" else v)
                                  for k, v in result.items() if k != "content_links"}, ensure_ascii=False), flush=True)
                await page.close()
        finally:
            await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
