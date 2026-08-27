"""Isolated manual UI acceptance server; never contacts a model provider.

Run on Centaurus from backend/ with uv. All configuration and credential data
is created inside a TemporaryDirectory and removed when the server exits.
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Never

import uvicorn

from longtian_api.main import create_app
from longtian_api.services.ai_client import AIConfiguration
from longtian_api.services.ai_errors import AIError
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService


class FakeModelClient:
    def __init__(self) -> None:
        self.calls = 0

    async def test_connection(self, configuration: AIConfiguration) -> None:
        self.calls += 1
        print(f"fake_model_calls={self.calls}", flush=True)
        if configuration.model == "qa-failure":
            raise AIError("ai_authentication_failed")

    async def aclose(self) -> None:
        print(f"fake_model_calls_final={self.calls}", flush=True)


async def reject_browser_launch(*_args: object, **_kwargs: object) -> Never:
    raise RuntimeError("Browser launch is disabled in the isolated AI UI check.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="longtian-ai-qa-") as directory:
        root = Path(directory)
        client = FakeModelClient()
        app = create_app(
            monitoring_rule_service_factory=lambda: MonitoringRuleService(
                database_path=root / "qa.sqlite3"
            ),
            platform_connection_service_factory=lambda: PlatformConnectionService(
                media_crawler_dir=root / "unused-mediacrawler",
                process_launcher=reject_browser_launch,
            ),
            ai_settings_service_factory=lambda database: AISettingsService(
                database=database, client=client
            ),
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
