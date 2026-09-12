"""Project media candidates are not files and are never model inputs.

Only a bounded transfer result with verified bytes may upgrade an asset. Source
URLs stay inside the acquisition scope; public/persisted evidence uses opaque IDs.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from opinion_workbench_api.services.enrichment_models import (
    EnrichmentAsset,
    EnrichmentIssue,
)


@dataclass(frozen=True)
class MediaCandidate:
    asset_id: str
    position: int
    kind: Literal["image", "video"]
    url: str = field(repr=False)


@dataclass(frozen=True)
class MediaInventory:
    candidates: tuple[MediaCandidate, ...]
    assets: tuple[EnrichmentAsset, ...]
    issues: tuple[EnrichmentIssue, ...]
    modalities: tuple[str, ...]
    complete: bool


def missing_asset(candidate, code="media_missing"):
    return EnrichmentAsset(
        asset_id=candidate.asset_id,
        position=candidate.position,
        kind=candidate.kind,
        role="content",
        status="unavailable",
        blob_ref=None,
        sha256=None,
        mime_type=None,
        byte_size=None,
        width=None,
        height=None,
        duration_ms=None,
        audio_track="not_applicable" if candidate.kind == "image" else "unknown",
        coverage="unknown",
        issue_code=code,
    )


def media_inventory(parsed, budget):
    candidates, assets, issues, modalities = [], [], [], set()
    counts = Counter()
    incomplete = bool(parsed["post"].get("count", 0) != len(parsed["files"]))
    limits = set()
    for file in parsed["files"]:
        extension = str(file.get("metadata", {}).get("extension", "")).lower()
        kind = (
            "image"
            if extension in ("jpg", "jpeg", "png", "webp", "gif")
            else "video"
            if extension in ("mp4", "mov", "m3u8", "webm")
            else None
        )
        if kind is None:
            incomplete = True
            continue
        modalities.add(kind)
        if kind == "video":
            modalities.add("audio")
        counts[kind] += 1
        if counts[kind] > (budget.max_images if kind == "image" else budget.max_videos):
            limits.add(f"{kind}_limit")
            incomplete = True
            continue
        candidate = MediaCandidate(uuid4().hex, len(candidates), kind, file["url"])
        candidates.append(candidate)
        assets.append(missing_asset(candidate))
        issues.append(
            EnrichmentIssue(code="media_missing", asset_position=candidate.position)
        )
    issues.extend(
        EnrichmentIssue(code=code, asset_position=None) for code in sorted(limits)
    )
    # Unemitted live/unknown media is a gap, not proof of a text-only post.
    for post in (parsed["post"], parsed["post"].get("retweeted_status", {})):
        if not isinstance(post, dict):
            incomplete = True
            continue
        if post.get("pic_ids"):
            modalities.add("image")
        if (
            isinstance(post.get("page_info"), dict)
            and "media_info" in post["page_info"]
        ):
            modalities.update(("video", "audio"))
        if isinstance(post.get("mix_media_info"), dict):
            for item in post["mix_media_info"].get("items", []):
                if item.get("type") == "pic":
                    modalities.add("image")
                elif item.get("type") == "video":
                    modalities.update(("video", "audio"))
                else:
                    incomplete = True
    if incomplete:
        modalities.add("unknown")
        issues.append(EnrichmentIssue(code="inventory_unknown", asset_position=None))
    return MediaInventory(
        tuple(candidates),
        tuple(assets),
        tuple(issues),
        tuple(sorted(modalities, key=("image", "video", "audio", "unknown").index)),
        not incomplete,
    )
