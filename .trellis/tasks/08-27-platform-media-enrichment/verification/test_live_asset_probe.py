"""Task-helper regressions: fake transport/probe, real isolated temporary staging."""

import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

LOCATOR = "https://source.invalid/private?token=SENTINEL_LOCATOR"


@pytest.fixture
def probe_module():
    specification = importlib.util.spec_from_file_location(
        "task_live_asset_probe", Path(__file__).with_name("live_asset_probe.py")
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def request():
    return {"platform": "wb", "kind": "image", "url": LOCATOR}


@pytest.mark.parametrize("kind", [[], {}, None, False, 1])
def test_nonstring_kind_is_invalid_before_any_resource(probe_module, monkeypatch, kind):
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid input must not allocate staging or construct a downloader")

    monkeypatch.setattr(probe_module, "MediaStaging", forbidden)
    monkeypatch.setattr(probe_module, "MediaDownloader", forbidden)
    assert asyncio.run(probe_module.run({**request(), "kind": kind})) == {
        "outcome": "invalid_input"
    }


@pytest.fixture
def fake_operation(probe_module, monkeypatch):
    captured = SimpleNamespace(roots=[], descriptors=[], calls=[], close_error=None)
    real_staging = probe_module.MediaStaging

    def staging(root, request_id):
        owned = real_staging(root, request_id)
        captured.roots.append(root)
        captured.descriptors.extend((owned._root_fd, owned._directory_fd))
        assert root.stat().st_mode & 0o777 == 0o700
        return owned

    class Downloader:
        def __init__(self, *, platform, max_total_bytes):
            assert platform == "wb"
            assert max_total_bytes == 6 * 1024 * 1024

        async def download(self, url, owned):
            captured.calls.append(url)
            with owned.create(16) as writing:
                writing.write(b"fixture")
                return {**writing.publish(), "declared_mime": "image/png"}

        async def close(self):
            if captured.close_error is not None:
                raise captured.close_error

    class Probe:
        def __init__(self, _executable):
            pass

        async def inspect(self, _owned, _handle, kind, declared_mime):
            assert kind == "image" and declared_mime == "image/png"
            return {"mime_type": "image/png", "width": 1, "height": 1}

    monkeypatch.setattr(probe_module, "MediaStaging", staging)
    monkeypatch.setattr(probe_module, "MediaDownloader", Downloader)
    monkeypatch.setattr(probe_module, "MediaProbe", Probe)
    return probe_module, captured


def assert_cleaned(captured):
    assert len(captured.roots) == 1
    assert not captured.roots[0].exists()
    for descriptor in captured.descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_success_reports_only_metadata_and_owned_cleanup(fake_operation):
    module, captured = fake_operation
    result = asyncio.run(module.run(request()))
    assert result["outcome"] == "ready"
    assert result["owned_operation_empty"] is True
    assert result["temporary_root_removed"] is True
    assert result["byte_size"] == 7
    assert captured.calls == [LOCATOR]
    assert "SENTINEL" not in json.dumps(result)
    assert str(captured.roots[0]) not in json.dumps(result)
    assert_cleaned(captured)


@pytest.mark.parametrize("cancel", [False, True])
def test_downloader_close_failure_still_closes_staging(fake_operation, cancel):
    module, captured = fake_operation
    captured.close_error = asyncio.CancelledError() if cancel else RuntimeError(LOCATOR)
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        asyncio.run(module.run(request()))
    assert captured.calls == [LOCATOR]
    assert_cleaned(captured)


def test_main_sanitizes_close_error_without_locator_or_path(
    fake_operation, monkeypatch, capsys
):
    module, captured = fake_operation
    captured.close_error = RuntimeError(LOCATOR)
    monkeypatch.setattr(
        module.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(json.dumps(request()).encode())),
    )
    module.main()
    output = capsys.readouterr()
    assert json.loads(output.out) == {"outcome": "probe_internal_error"}
    assert output.err == "" and "SENTINEL" not in output.out
    assert str(captured.roots[0]) not in output.out
    assert_cleaned(captured)


def test_main_input_cap_stops_before_resource_creation(
    probe_module, monkeypatch, capsys
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("oversized input must not allocate staging")

    monkeypatch.setattr(probe_module, "MediaStaging", forbidden)
    monkeypatch.setattr(
        probe_module.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"x" * 16385))
    )
    probe_module.main()
    output = capsys.readouterr()
    assert json.loads(output.out) == {"outcome": "invalid_input"}
    assert output.err == ""
