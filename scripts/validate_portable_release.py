#!/usr/bin/env python3
"""Validate immutable release inputs before allowing a draft-only upload."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

PLATFORMS = {"Windows-x64": "x86_64", "macOS-arm64": "arm64"}
TAG = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")


def audit_archive(path: Path, version: str, commit: str, platform: str) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive members")
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name:
                raise ValueError("unsafe archive path")
            if not member.parts or member.parts[0] != "OpinionWorkbench":
                raise ValueError("unexpected archive root")
            if len(member.parts) > 1 and member.parts[1].lower() in {
                "data",
                "runtime",
                "logs",
                "secrets",
                "browser",
                "node_modules",
                ".git",
                ".env",
                "reports",
                "final_reports",
            }:
                raise ValueError("private or development data in archive")
            if member.suffix.lower() in {".sqlite3", ".sqlite", ".log"}:
                raise ValueError("runtime data in archive")
        metadata = dict(
            line.split("=", 1)
            for line in archive.read("OpinionWorkbench/BUILD-METADATA.txt")
            .decode("utf-8-sig")
            .splitlines()
            if "=" in line
        )
        if any(
            metadata.get(key) != value
            for key, value in {
                "version": version,
                "source": commit,
                "architecture": PLATFORMS[platform],
            }.items()
        ):
            raise ValueError("archive identity mismatch")
        executable = "OpinionWorkbench.exe" if platform == "Windows-x64" else "OpinionWorkbench"
        worker = (
            "OpinionWorkbenchGalleryWorker.exe"
            if platform == "Windows-x64"
            else "OpinionWorkbenchGalleryWorker"
        )
        for required in (executable, worker, "_internal/resources/static/index.html"):
            if f"OpinionWorkbench/{required}" not in names:
                raise ValueError("missing runtime resource")
        if platform == "macOS-arm64":
            for executable in (executable, worker, "启动.command"):
                if (
                    not (archive.getinfo(f"OpinionWorkbench/{executable}").external_attr >> 16)
                    & 0o111
                ):
                    raise ValueError("missing executable permission")


def validate_assets(root: Path, tag: str, commit: str) -> None:
    expected = {f"OpinionWorkbench-{tag}-{p}.zip" for p in PLATFORMS}
    files = [p for p in root.rglob("*") if p.is_file()]
    if sorted(p.name for p in files) != sorted(
        expected | {n + ".sha256" for n in expected}
    ):
        raise ValueError("exactly two versioned ZIPs and matching checksums required")
    for path in files:
        if path.name not in expected:
            continue
        checksum = path.with_name(path.name + ".sha256")
        fields = checksum.read_text(encoding="utf-8-sig").split()
        if len(fields) != 2 or fields[1] != path.name:
            raise ValueError("checksum must refer to the matching basename")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != fields[0].lower():
            raise ValueError("checksum mismatch")
        platform = next(p for p in PLATFORMS if path.name.endswith(f"-{p}.zip"))
        audit_archive(path, tag, commit, platform)


def validate_remote(repository: str, tag: str, commit: str, run=subprocess.run) -> None:
    result = run(
        ["gh", "api", "--include", f"repos/{repository}/releases/tags/{tag}"],
        capture_output=True,
        text=True,
        check=False,
    )
    response = result.stdout.replace("\r\n", "\n")
    header, separator, body = response.partition("\n\n")
    first_line = header.splitlines()[0] if header else ""
    if result.returncode:
        if result.returncode == 1 and re.fullmatch(r"HTTP/\S+ 404(?: .*|)", first_line):
            return
        raise ValueError("release lookup failed; refusing to upload")
    if not separator or not re.fullmatch(r"HTTP/\S+ 200(?: .*|)", first_line):
        raise ValueError("unexpected release response")
    release = json.loads(body)
    if not isinstance(release, dict) or release.get("draft") is not True:
        raise ValueError("refusing to overwrite a published release")
    if release.get("target_commitish") != commit:
        raise ValueError("draft source differs from requested commit")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("commit")
    parser.add_argument("--assets", type=Path, default=Path("assets"))
    args = parser.parse_args()
    if not TAG.fullmatch(args.tag) or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("semantic version tag and full source SHA required")
    if not os.environ.get("GH_TOKEN") or not os.environ.get("GITHUB_REPOSITORY"):
        parser.error("GitHub repository and token required")
    validate_assets(args.assets, args.tag, args.commit)
    validate_remote(os.environ["GITHUB_REPOSITORY"], args.tag, args.commit)
    print("Portable assets verified; draft-only upload permitted.")


if __name__ == "__main__":
    main()
