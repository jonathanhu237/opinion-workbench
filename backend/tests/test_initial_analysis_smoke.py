"""The isolated UI fixture permits only its explicitly forwarded UI origin."""

import pytest
from fastapi.testclient import TestClient
from initial_analysis_smoke import create_smoke_app

UI_ORIGIN = "http://127.0.0.1:46081"


def test_smoke_cross_origin_reads_are_visible_without_model_or_media_work():
    with TestClient(create_smoke_app(), base_url="http://127.0.0.1:46082") as client:
        response = client.get("/api/v1/results", headers={"Origin": UI_ORIGIN})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == UI_ORIGIN
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["total"] == 103
        assert client.get("/api/v1/initial-analysis-smoke/counters").json() == {
            "synthetic_model_calls": 0,
            "synthetic_media_calls": 0,
        }
        untrusted = client.get(
            "/api/v1/results", headers={"Origin": "http://127.0.0.1:46083"}
        )
        assert "access-control-allow-origin" not in untrusted.headers


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_smoke_preflight_is_narrow_and_has_no_work(method):
    with TestClient(create_smoke_app(), base_url="http://127.0.0.1:46082") as client:
        headers = {
            "Origin": UI_ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        }
        response = client.options("/api/v1/content-analysis-jobs", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == UI_ORIGIN
        assert response.headers["access-control-allow-methods"] == "GET, POST, PUT"
        assert "access-control-allow-credentials" not in response.headers
        assert (
            client.options(
                "/api/v1/content-analysis-jobs",
                headers={**headers, "Origin": "https://untrusted.example"},
            ).status_code
            == 400
        )
        assert (
            client.options(
                "/api/v1/content-analysis-jobs",
                headers={**headers, "Access-Control-Request-Method": "DELETE"},
            ).status_code
            == 400
        )
        assert client.get("/api/v1/initial-analysis-smoke/counters").json() == {
            "synthetic_model_calls": 0,
            "synthetic_media_calls": 0,
        }
