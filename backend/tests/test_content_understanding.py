"""Neutral text/image/video envelopes, structured uncertainty and strict failure."""

import json
from dataclasses import replace

import pytest
from initial_analysis_fixtures import UNDERSTANDING
from test_ai_analysis import CONFIGURATION, KEY, USAGE, enriched_item

from longtian_api.database import Database
from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository
from longtian_api.services.ai_analysis import AIAnalysisError
from longtian_api.services.ai_client import AICompletion
from longtian_api.services.content_understanding import (
    build_understanding_messages,
    parse_understanding,
)


@pytest.mark.parametrize(
    "assets",
    [
        (),
        (("image", "image/png", b"checked-image"),),
        (("video", "video/mp4", b"checked-video-with-audio"),),
    ],
)
def test_same_neutral_contract_receives_actual_media_and_exact_prompt(tmp_path, assets):
    database = Database(tmp_path / "prompt.sqlite3")
    database.initialize()
    prompt = AnalysisSettingsRepository(database).read().initial_prompt
    item = enriched_item(assets=assets)
    messages = build_understanding_messages(CONFIGURATION, item, prompt)
    assert prompt.instructions in messages[0]["content"]
    assert "不做任何地域或主题相关性筛除" in messages[0]["content"]
    serialized = json.dumps(messages)
    assert "monitoring_scope" not in serialized
    assert "SEARCH_SNIPPET_NOT_FULL_TEXT" not in serialized
    for kind, _, _ in assets:
        assert f"{kind}_url" in serialized
    output = parse_understanding(
        AICompletion(json.dumps(UNDERSTANDING), USAGE), api_key=CONFIGURATION.api_key
    )
    assert output.uncertainties == UNDERSTANDING["uncertainties"]


@pytest.mark.parametrize(
    "changed",
    [
        {"decision": "irrelevant"},
        {"summary": "x" * 1501},
        {"location_clues": [{"excerpt": "a", "modality": "unknown"}]},
        {"media_observations": ["a"] * 13},
        {"uncertainties": " "},
        {
            "summary": "a" * 1500,
            "time_context": "b" * 500,
            "uncertainties": "c" * 500,
            "media_observations": ["d" * 400] * 12,
        },
    ],
)
def test_invalid_output_fails_without_repair_and_preserves_usage(changed):
    text = json.dumps({**UNDERSTANDING, **changed})
    with pytest.raises(AIAnalysisError) as error:
        parse_understanding(AICompletion(text, USAGE), api_key=CONFIGURATION.api_key)
    assert error.value.code == "invalid_schema" and error.value.usage == USAGE


def test_validation_diagnostics_keep_field_categories_without_model_text():
    value = {
        **UNDERSTANDING,
        "summary": [],
        "private-arbitrary-field": "secret-content",
    }
    with pytest.raises(AIAnalysisError) as caught:
        parse_understanding(
            AICompletion(json.dumps(value), USAGE), api_key=CONFIGURATION.api_key
        )
    assert "summary: string_type" in caught.value.validation_issues
    assert "unknown_field: extra_forbidden" in caught.value.validation_issues
    assert "private-arbitrary-field" not in str(caught.value.validation_issues)
    assert "secret-content" not in str(caught.value.validation_issues)


@pytest.mark.parametrize(
    "text",
    [
        '{"summary":NaN}',
        '{"summary":"a","summary":"b"}',
        "prefix {}",
        "```json\n{}\n``` trailing",
    ],
)
def test_strict_json_no_salvage(text):
    with pytest.raises(AIAnalysisError):
        parse_understanding(AICompletion(text, USAGE), api_key=CONFIGURATION.api_key)


def test_credential_and_changed_byte_rejection(tmp_path):
    with pytest.raises(AIAnalysisError, match="credential_leakage"):
        parse_understanding(
            AICompletion(json.dumps({**UNDERSTANDING, "summary": KEY}), USAGE),
            api_key=CONFIGURATION.api_key,
        )
    database = Database(tmp_path / "prompt.sqlite3")
    database.initialize()
    prompt = AnalysisSettingsRepository(database).read().initial_prompt
    item = enriched_item(assets=(("image", "image/png", b"verified"),))
    changed = replace(item, media=(replace(item.media[0], data=b"tampered"),))
    with pytest.raises(AIAnalysisError, match="input_incomplete"):
        build_understanding_messages(CONFIGURATION, changed, prompt)
