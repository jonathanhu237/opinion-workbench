"""Small contracts for the Windows entrypoint and frozen worker boundary."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from opinion_workbench_api.services.gallery_component import (
    GalleryComponent,
    _gallery_worker_command,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_windows_build_uses_pinned_mise_tools_and_backend_python():
    mise = (REPO_ROOT / "mise.toml").read_text(encoding="utf-8")
    build_path = REPO_ROOT / "windows" / "build.ps1"
    build = build_path.read_text(encoding="utf-8-sig")
    command = (REPO_ROOT / "windows" / "build.cmd").read_text(encoding="utf-8")

    assert 'node = "24.20.0"' in mise
    assert 'pnpm = "11.14.0"' in mise
    assert 'python = "3.11.16"' in mise
    assert 'uv = "0.12.10"' in mise
    assert 'Invoke-Tool "mise" @(' in build
    assert '"--python", "3.11"' in build
    assert '"--with", "pyinstaller==6.16.0"' in build
    assert ") $backend" in build
    assert "-InstallTools" in command
    assert build_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert (
        (REPO_ROOT / "windows" / "package-toolkit.ps1")
        .read_bytes()
        .startswith(b"\xef\xbb\xbf")
    )


def test_windows_zip_is_default_and_installer_is_opt_in():
    build = (REPO_ROOT / "windows" / "build.ps1").read_text(encoding="utf-8-sig")
    toolkit = (REPO_ROOT / "windows" / "package-toolkit.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "[switch]$Installer" in build
    assert "if ($Installer) { Build-Installer }" in build
    assert "if ($Installer -and -not (Find-InnoCompiler))" in build
    assert "if ($Installer -and $null -eq (Find-InnoCompiler))" in build
    assert "    Build-Backend\n    Build-Portable\n" in build
    assert '"dist\\windows\\OpinionWorkbench-Windows.zip"' in build
    portable = build.split("function Build-Portable {", 1)[1].split(
        "function Build-Installer {", 1
    )[0]
    assert '"app\\OpinionWorkbench"' in portable
    assert "OpinionWorkbenchGalleryWorker.exe" in portable
    assert "[System.IO.Compression.ZipFile]::CreateFromDirectory(" in portable
    assert (
        "$true" in portable
    )  # Keep a containing OpinionWorkbench directory in the ZIP.
    assert '"windows\\portable-readme.txt"' in toolkit
    assert (REPO_ROOT / "windows" / "portable-readme.txt").is_file()


@pytest.mark.parametrize("mode", ("present", "missing"))
def test_build_bootstrap_only_requires_winget_when_tools_are_missing(tmp_path, mode):
    """Exercise Install-OptionalTools with mocked PowerShell dependencies."""

    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Windows bootstrap contract")

    harness = tmp_path / "bootstrap-tools.ps1"
    harness.write_text(
        r"""
param(
    [Parameter(Mandatory = $true)][string]$BuildScript,
    [Parameter(Mandatory = $true)][ValidateSet("present", "missing")][string]$Mode
)

$source = Get-Content -Raw -LiteralPath $BuildScript
$match = [regex]::Match(
    $source,
    '(?ms)^function Install-OptionalTools \{.*?(?=\r?\nfunction Assert-Environment)'
)
if (-not $match.Success) { throw "Install-OptionalTools was not found" }
Invoke-Expression $match.Value

$script:invokeCount = 0
function Write-Step([string]$Message) { }
function Invoke-Tool([string]$File, [string[]]$Arguments, [string]$WorkingDirectory) {
    $script:invokeCount++
}

if ($Mode -eq "present") {
    function Has-Tool([string]$Name) { return $Name -eq "mise" }
    function Find-InnoCompiler { throw "ZIP builds must not require Inno Setup" }
    Install-OptionalTools
    if ($script:invokeCount -ne 0) { throw "winget was invoked unexpectedly" }
}
else {
    function Has-Tool([string]$Name) { return $false }
    function Find-InnoCompiler { return $null }
    $failed = $false
    try { Install-OptionalTools }
    catch { $failed = $true }
    if (-not $failed) { throw "missing tools did not fail without winget" }
    if ($script:invokeCount -ne 0) { throw "winget was invoked unexpectedly" }
}
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
            str(REPO_ROOT / "windows" / "build.ps1"),
            mode,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("mise") is None, reason="mise is required")
def test_pinned_mise_runtime_resolves_the_build_toolchain():
    expected = {
        "node": "24.20.0",
        "pnpm": "11.14.0",
        "python": "3.11.16",
    }
    for tool, version in expected.items():
        result = subprocess.run(
            ["mise", "x", "--", tool, "--version"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert version in result.stdout

    result = subprocess.run(
        [
            "mise",
            "x",
            "--",
            "uv",
            "run",
            "--locked",
            "--python",
            "3.11",
            "--with",
            "pyinstaller==6.16.0",
            "pyinstaller",
            "--version",
        ],
        cwd=REPO_ROOT / "backend",
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "6.16.0"


def test_frozen_distribution_contains_a_console_worker_and_hidden_launch_contract():
    spec = (REPO_ROOT / "windows" / "opinion-workbench.spec").read_text(
        encoding="utf-8"
    )
    component = (
        REPO_ROOT
        / "backend"
        / "src"
        / "opinion_workbench_api"
        / "services"
        / "gallery_component.py"
    ).read_text(encoding="utf-8")

    assert 'name="OpinionWorkbenchGalleryWorker"' in spec
    assert "console=True" in spec
    assert "OpinionWorkbenchGalleryWorker.exe" in component
    assert "CREATE_NO_WINDOW" in component


def test_gallery_worker_receives_only_runtime_environment(monkeypatch):
    captured = {}

    async def launcher(*_command, **options):
        captured.update(options)
        return object()

    for key, value in {
        "SystemRoot": r"C:\Windows",
        "WINDIR": r"C:\Windows",
        "TEMP": r"C:\Temp",
        "TMP": r"C:\Temp",
        "LANG": "zh_CN.UTF-8",
        "OPINION_WORKBENCH_UNRELATED_SECRET": "must-not-cross-process-boundary",
    }.items():
        monkeypatch.setenv(key, value)

    asyncio.run(GalleryComponent(launcher=launcher)._start())

    environment = captured["env"]
    assert environment["LANG"] == "zh_CN.UTF-8"
    assert environment["SystemRoot"] == r"C:\Windows"
    assert environment["WINDIR"] == r"C:\Windows"
    assert environment["TEMP"] == r"C:\Temp"
    assert environment["TMP"] == r"C:\Temp"
    assert "OPINION_WORKBENCH_UNRELATED_SECRET" not in environment


def test_gallery_worker_line_protocol_reaches_the_broker_before_returning():
    environment = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "-I", "-u", "-m", "opinion_workbench_api.gallery_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=REPO_ROOT / "backend",
        env=environment,
    )
    startup = {
        "content_id": "3600375418559878",
        "mode": "text_only",
        "cookies": {},
        "max_media_bytes": 1024,
        "max_images": 24,
        "max_videos": 1,
    }
    process.stdin.write(json.dumps(startup).encode() + b"\n")
    process.stdin.flush()
    request = json.loads(process.stdout.readline())
    assert request["kind"] == "request"
    assert request["stage"] == "detail"
    assert request["url"].startswith("https://weibo.com/ajax/statuses/show")

    response = {
        "kind": "response",
        "status_code": 404,
        "url": request["url"],
        "headers": {},
        "body": {"encoding": "json", "value": {}},
        "history": [],
        "cookies": {},
    }
    process.stdin.write(json.dumps(response).encode() + b"\n")
    process.stdin.close()
    remaining = process.stdout.read()
    process.wait(timeout=10)

    messages = [request, *map(json.loads, remaining.splitlines())]
    assert process.returncode == 0
    assert messages[-1]["kind"] == "error"
    assert messages[-1]["code"] in {"content_unavailable", "parser_failed"}


def test_frozen_worker_command_selects_the_sidecar_console_executable(
    tmp_path, monkeypatch
):
    from opinion_workbench_api.services import gallery_component

    executable = tmp_path / "OpinionWorkbench"
    executable.write_text("")
    worker = executable.with_name("OpinionWorkbenchGalleryWorker")
    worker.write_text("")
    monkeypatch.setattr(gallery_component.sys, "frozen", True, raising=False)
    monkeypatch.setattr(gallery_component.sys, "executable", str(executable))

    assert _gallery_worker_command() == (
        str(worker),
        "--opinion-workbench-gallery-worker",
    )


def test_development_worker_command_keeps_json_pipe_arguments():
    command = _gallery_worker_command()

    assert command[0] == sys.executable
    assert command[1:] == ("-I", "-u", "-m", "opinion_workbench_api.gallery_worker")
