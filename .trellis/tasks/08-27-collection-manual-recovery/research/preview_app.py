"""Isolated recovery UI fixture; never connects to a browser or model.

Run only in the code-only Centaurus validation snapshot with an explicitly supplied
RECOVERY_PREVIEW_DATABASE path. Synthetic search outcomes exercise the real API,
repository and frontend; they are not evidence of successful platform verification.
"""

import os
from pathlib import Path
from types import SimpleNamespace

from longtian_api.main import create_app
from longtian_api.services.media_crawler_auth_worker import (
    SearchWorkerItem,
    SearchWorkerResult,
)
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.search_runs import SearchRunService
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SyntheticWorker:
    def __init__(self):
        self.toutiao_attempts = 0
        self.toutiao_terms = []

    async def search(
        self, *, platform, terms, on_progress, on_item, on_term_completed, **_kwargs
    ):
        if platform != "toutiao":
            return SearchWorkerResult("login_required")
        self.toutiao_attempts += 1
        self.toutiao_terms.append(tuple(terms))
        for position, _term in enumerate(terms):
            await on_progress(position, len(terms))
            ids = ()
            if self.toutiao_attempts == 1:
                ids = (
                    ("900001",)
                    if position == 0
                    else ("900002",)
                    if position == 6
                    else ()
                )
            elif position == 0:
                ids = ("900002", "900003")
            for content_id in ids:
                await on_item(
                    position,
                    SearchWorkerItem(
                        content_id=content_id,
                        content_type="article",
                        title=f"模拟采集结果 {content_id[-1]}",
                        snippet="这是一条界面验收用的模拟内容，不是真实平台采集结果。",
                        creator_hash="0123456789abcdef",
                        publisher_name="测***号",
                        published_at_text="2026-08-28",
                        content_url=f"https://www.toutiao.com/article/{content_id}/",
                        discovered_at=1_788_000_000_000,
                    ),
                )
            if self.toutiao_attempts == 1 and position == 6:
                return SearchWorkerResult("structure_changed")
            await on_term_completed(position, len(ids))
        return SearchWorkerResult("completed_with_results")

    async def manual_page(self, *, action, **_kwargs):
        return SimpleNamespace(
            outcome="opened_homepage" if action == "show" else "not_present"
        )

    async def open_result(self, **_kwargs):
        return SimpleNamespace(outcome="browser_unavailable")


async def forbid_browser_process(*_args, **_kwargs):
    raise RuntimeError("Browser processes are disabled in this synthetic preview.")


class PreviewFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


database_path = Path(os.environ["RECOVERY_PREVIEW_DATABASE"]).resolve()
if not database_path.is_relative_to(Path("/tmp/longtian-recovery-validation.EcUhyX")):
    raise RuntimeError(
        "Preview database must be inside the isolated validation directory."
    )

worker = SyntheticWorker()
app = create_app(
    platform_connection_service_factory=lambda: PlatformConnectionService(
        process_launcher=forbid_browser_process
    ),
    monitoring_rule_service_factory=lambda: MonitoringRuleService(
        database_path=database_path
    ),
    search_run_service_factory=lambda monitoring_rules, platform_connections: (
        SearchRunService(
            monitoring_rules=monitoring_rules,
            worker=worker,
            browser_operations=platform_connections.browser_operations,
            database_path=database_path,
        )
    ),
)
app.mount(
    "/",
    PreviewFiles(
        directory=Path(__file__).resolve().parents[4] / "frontend" / "dist", html=True
    ),
)
