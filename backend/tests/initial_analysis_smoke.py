"""Loopback-only UI acceptance app. All provider and media work is synthetic.

Run from backend: PYTHONPATH=src:tests uv run --frozen uvicorn
initial_analysis_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr
from summary_fixtures import BASE, KEY, MODEL, seed_run
from test_content_analysis_api import api_fixture

from opinion_workbench_api.schemas.ai_settings import AISettingsUpdate


def create_smoke_app():
    temporary = TemporaryDirectory(prefix="opinion-workbench-initial-smoke-")
    app, database, model, media = api_fixture(Path(temporary.name), count=101)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:46081"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )
    seed_run(database, 2, start=5000, rule_name="另一条历史采集规则")
    media.partial.add("1008")
    media.body = "合成验收材料：来源称龙田附近道路积水，未说明行政区与确切时间。"
    complete = model.complete

    async def slow_synthetic_completion(configuration, **kwargs):
        await asyncio.sleep(0.06)
        return await complete(configuration, **kwargs)

    model.complete = slow_synthetic_completion
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original_lifespan(application):
                application.state.ai_settings_service.save(
                    AISettingsUpdate(
                        base_url=BASE,
                        model=MODEL,
                        api_key=SecretStr(KEY),
                    )
                )
                yield
        finally:
            temporary.cleanup()

    app.router.lifespan_context = lifespan

    @app.get("/api/v1/initial-analysis-smoke/counters")
    def counters() -> dict[str, int]:
        return {
            "synthetic_model_calls": len(model.calls),
            "synthetic_media_calls": len(media.calls),
        }

    return app
