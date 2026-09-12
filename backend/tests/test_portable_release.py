"""Portable preference isolation and fail-closed release artifact contracts."""

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from topic_report_fixtures import api_environment

from opinion_workbench_api.api.v1.summary_preferences import SummaryPreference
from opinion_workbench_api.application_paths import default_data_root
from opinion_workbench_api.services.summary_preferences import SummaryPreferenceService

ROOT = Path(__file__).resolve().parents[2]
module_spec = importlib.util.spec_from_file_location(
    "portable_release_guard", ROOT / "scripts" / "validate_portable_release.py"
)
guard = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(guard)
SHA = "a" * 40


@pytest.mark.parametrize("value", [True, "8", 8.0, 0, 3, 17, None])
def test_preference_rejects_non_contract_values(value):
    with pytest.raises(ValidationError):
        SummaryPreference(summary_concurrency=value)


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "not json",
        '{"summary_concurrency":true}',
        '{"summary_concurrency":"4"}',
    ],
)
def test_invalid_portable_preference_falls_back(tmp_path, raw):
    path = tmp_path / "preferences.json"
    path.write_text(raw)
    assert SummaryPreferenceService(path).read() == 8


def test_preference_persists_at_injected_database_not_global_runtime(tmp_path):
    app, database, _, _ = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.put(
            "/api/v1/summary-preferences", json={"summary_concurrency": 4}
        )
        assert response.status_code == 200, response.text
        assert (
            client.get("/api/v1/summary-preferences").json()["summary_concurrency"] == 4
        )
    path = database.path.parent / "preferences.json"
    assert SummaryPreferenceService(path).read() == 4
    moved = tmp_path / "new folder 中文" / "preferences.json"
    moved.parent.mkdir()
    path.rename(moved)
    assert SummaryPreferenceService(moved).read() == 4


def test_frozen_default_data_moves_with_executable_not_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("OPINION_WORKBENCH_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        sys, "executable", str(tmp_path / "folder 中文" / "OpinionWorkbench")
    )
    monkeypatch.chdir(tmp_path)
    assert default_data_root() == tmp_path / "folder 中文" / "data"


def make_asset(root, platform, *, source=SHA, extra=None):
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"OpinionWorkbench-v1.2.3-{platform}.zip"
    exe = "OpinionWorkbench.exe" if platform == "Windows-x64" else "OpinionWorkbench"
    worker = (
        "OpinionWorkbenchGalleryWorker.exe"
        if platform == "Windows-x64"
        else "OpinionWorkbenchGalleryWorker"
    )
    files = {
        "BUILD-METADATA.txt": (
            f"version=v1.2.3\nsource={source}\n"
            f"architecture={guard.PLATFORMS[platform]}\n"
        ),
        exe: "test executable",
        worker: "test helper",
        "_internal/resources/static/index.html": "test page",
    }
    if platform == "macOS-arm64":
        files["启动.command"] = "#!/bin/bash\n"
    if extra:
        files.update(extra)
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            info = zipfile.ZipInfo("OpinionWorkbench/" + name)
            info.external_attr = 0o100755 << 16
            archive.writestr(info, text)
    path.with_name(path.name + ".sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name
    )
    return path


def test_complete_matching_assets_pass(tmp_path):
    for platform in guard.PLATFORMS:
        make_asset(tmp_path, platform)
    guard.validate_assets(tmp_path, "v1.2.3", SHA)


@pytest.mark.parametrize(
    "fault", ["missing", "mixed_commit", "private_data", "checksum", "wrong_name"]
)
def test_invalid_release_assets_are_rejected(tmp_path, fault):
    make_asset(tmp_path, "Windows-x64")
    if fault != "missing":
        path = make_asset(
            tmp_path,
            "macOS-arm64",
            source="b" * 40 if fault == "mixed_commit" else SHA,
            extra={"data/preferences.json": "{}"} if fault == "private_data" else None,
        )
        if fault == "checksum":
            path.write_bytes(b"corrupt")
        if fault == "wrong_name":
            path.rename(path.with_name("OpinionWorkbench-v2.0.0-macOS-arm64.zip"))
    with pytest.raises(ValueError):
        guard.validate_assets(tmp_path, "v1.2.3", SHA)


@pytest.mark.parametrize(
    "draft,commit", [(False, SHA), (True, "main"), (True, ""), (True, "b" * 40)]
)
def test_existing_release_requires_draft_same_commit(draft, commit):
    result = SimpleNamespace(
        returncode=0,
        stdout="HTTP/2.0 200 OK\n\n"
        + json.dumps({"draft": draft, "target_commitish": commit}),
    )
    with pytest.raises(ValueError):
        guard.validate_remote("owner/repo", "v1.2.3", SHA, run=lambda *a, **k: result)


def test_release_lookup_requires_confirmed_404_and_accepts_same_commit_draft():
    for result in [
        SimpleNamespace(returncode=1, stdout="HTTP/2.0 404 Not Found\n\n{}"),
        SimpleNamespace(
            returncode=0,
            stdout="HTTP/2.0 200 OK\n\n"
            + json.dumps({"draft": True, "target_commitish": SHA}),
        ),
    ]:
        guard.validate_remote(
            "owner/repo", "v1.2.3", SHA, run=lambda *a, r=result, **k: r
        )
    for result in [
        SimpleNamespace(returncode=1, stdout="network 404"),
        SimpleNamespace(returncode=1, stdout="HTTP/2.0 403 Forbidden\n\n{}"),
    ]:
        with pytest.raises(ValueError):
            guard.validate_remote(
                "owner/repo", "v1.2.3", SHA, run=lambda *a, r=result, **k: r
            )
