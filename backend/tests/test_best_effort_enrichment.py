"""Offline coverage and preview fallbacks for independent analysis."""

import json
from dataclasses import replace

import pytest
from pydantic import SecretStr

from longtian_api.repositories.search_runs import SearchResultSourceRecord
from longtian_api.schemas.analysis_evidence import SavedInput
from longtian_api.services.ai_analysis import (
    AIAnalysisError,
    AnalysisContext,
    SummaryEvidence,
    build_analysis_messages,
    build_summary_messages,
)
from longtian_api.services.ai_client import AIConfiguration
from longtian_api.services.content_enrichment import EnrichmentItem
from longtian_api.services.enrichment_models import (
    EnrichedContent,
    evidence_fingerprint,
)

CONFIGURATION = AIConfiguration(
    "https://api.example.com/v1",
    "text-model",
    1,
    SecretStr("private-key"),
)
CONTEXT = AnalysisContext(rule_name="龙田监控", terms=("龙田 投诉",))


def source() -> SearchResultSourceRecord:
    return SearchResultSourceRecord(
        run_id=3,
        result_id=4,
        platform="wb",
        platform_content_id="123",
        content_type="article",
        content_url="https://weibo.com/123",
        title="龙田街道道路积水",
        snippet="来源摘要反映雨后道路积水。",
        matched_terms=("龙田 投诉",),
        collection_active=False,
    )


def test_search_preview_is_analyzable_and_explicitly_partial():
    item = EnrichmentItem(source(), "lookup_miss").as_preview()
    saved = SavedInput.from_preview(
        platform=item.source.platform,
        title=item.source.title,
        snippet=item.source.snippet,
        acquired_at=1_750_000_000_000,
    )

    messages = build_analysis_messages(CONFIGURATION, item, CONTEXT)
    payload = json.loads(messages[1]["content"])

    assert saved.status == "partial"
    assert saved.evidence_coverage.level == "search_preview"
    assert saved.analysis_eligible
    assert payload["evidence_coverage"]["text_origin"] == "search_preview"
    assert payload["evidence_coverage"]["video"]["unknown"] == 1
    assert payload["source"] == {
        "platform": "wb",
        "title": source().title,
        "body": source().snippet,
    }


def test_legacy_input_gets_coverage_and_summary_carries_the_manifest():
    saved = SavedInput.from_preview(
        platform="wb",
        title="预览标题",
        snippet="预览摘要",
        acquired_at=1_750_000_000_000,
    )
    legacy = saved.model_dump()
    legacy.pop("coverage")
    decoded = SavedInput.model_validate(legacy)
    assert decoded.evidence_coverage == saved.evidence_coverage

    evidence = SummaryEvidence(
        source_id=4,
        title=saved.text.title,
        body=saved.text.body,
        evidence_coverage=saved.evidence_coverage,
        reason="来源与监控范围有关",
        evidence_summary="来源摘要保留为预览证据。",
    )
    payload = json.loads(
        build_summary_messages(
            CONTEXT,
            [evidence],
            {
                "total": 1,
                "relevant": 1,
                "irrelevant": 0,
                "uncertain": 0,
                "input_incomplete": 0,
                "failed": 0,
                "cancelled": 0,
                "interrupted": 0,
            },
        )[1]["content"]
    )
    assert payload["sources"][0]["evidence_coverage"]["level"] == "search_preview"


def test_partial_detail_text_survives_one_failed_media_asset():
    content = EnrichedContent.model_validate(
        {
            "schema_version": 1,
            "platform": "dy",
            "content_id": "123",
            "content_url": "https://www.douyin.com/video/123",
            "acquired_at": 1_750_000_000_000,
            "extractor_version": "dy-enrichment-v1",
            "status": "partial",
            "text": {
                "title": "详情标题",
                "body": "已保存的详情正文。",
                "coverage": "complete",
            },
            "detected_modalities": ["text", "image"],
            "media_inventory_complete": True,
            "assets": [
                {
                    "asset_id": "123e4567e89b42d3a456426614174000",
                    "position": 0,
                    "kind": "image",
                    "role": "content",
                    "status": "failed",
                    "blob_ref": None,
                    "sha256": None,
                    "mime_type": None,
                    "byte_size": None,
                    "width": None,
                    "height": None,
                    "duration_ms": None,
                    "audio_track": "not_applicable",
                    "coverage": "unknown",
                    "issue_code": "download_failed",
                }
            ],
            "issues": [{"code": "download_failed", "asset_position": 0}],
        }
    )
    item = EnrichmentItem(
        SearchResultSourceRecord(
            run_id=3,
            result_id=4,
            platform="dy",
            platform_content_id="123",
            content_type="video",
            content_url=content.content_url,
            title="搜索标题",
            snippet="搜索摘要",
            matched_terms=("龙田 投诉",),
            collection_active=False,
        ),
        "completed",
        content,
        evidence_fingerprint(content),
    )

    messages = build_analysis_messages(CONFIGURATION, item, CONTEXT)
    payload = json.loads(messages[1]["content"])

    assert payload["source"]["body"] == content.text.body
    coverage = payload["evidence_coverage"]
    assert coverage["level"] == "detail_text"
    assert coverage["image"] == {"expected": 1, "ready": 0, "failed": 1, "unknown": 0}
    assert "image_url" not in str(messages)


def test_empty_detail_falls_back_to_frozen_search_preview():
    payload = {
        "schema_version": 1,
        "platform": "wb",
        "content_id": "123",
        "content_url": "https://m.weibo.cn/detail/123",
        "acquired_at": 1_750_000_000_000,
        "extractor_version": "wb-enrichment-v1",
        "status": "unavailable",
        "text": {"title": "", "body": "", "coverage": "unavailable"},
        "detected_modalities": ["text", "unknown"],
        "media_inventory_complete": False,
        "assets": [],
        "issues": [{"code": "text_unavailable", "asset_position": None}],
    }
    content = EnrichedContent.model_validate(payload)
    item = EnrichmentItem(source(), "completed", content, evidence_fingerprint(content))

    assert not item.detail_analysis_eligible
    assert item.preview_analysis_eligible
    preview = item.as_preview()
    assert preview.preview and preview.content is None
    assert preview.input_fingerprint != item.input_fingerprint

    message = build_analysis_messages(CONFIGURATION, preview, CONTEXT)
    envelope = json.loads(message[1]["content"])
    assert envelope["evidence_coverage"]["level"] == "search_preview"
    assert envelope["source"]["body"] == source().snippet


def test_empty_detail_without_search_text_never_builds_model_input():
    payload = {
        "schema_version": 1,
        "platform": "wb",
        "content_id": "123",
        "content_url": "https://m.weibo.cn/detail/123",
        "acquired_at": 1_750_000_000_000,
        "extractor_version": "wb-enrichment-v1",
        "status": "unavailable",
        "text": {"title": "", "body": "", "coverage": "unavailable"},
        "detected_modalities": ["text", "unknown"],
        "media_inventory_complete": False,
        "assets": [],
        "issues": [{"code": "text_unavailable", "asset_position": None}],
    }
    content = EnrichedContent.model_validate(payload)
    empty_source = replace(source(), title="", snippet="")
    item = EnrichmentItem(
        empty_source, "completed", content, evidence_fingerprint(content)
    )

    assert not item.analysis_eligible
    with pytest.raises(AIAnalysisError, match="input_incomplete"):
        build_analysis_messages(CONFIGURATION, item, CONTEXT)
