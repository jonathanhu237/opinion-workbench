"""One local output retry, with separate provider accounting for both calls."""

from longtian_api.services.ai_client import AIUsage

RETRYABLE_OUTPUT_ERRORS = frozenset(
    {"invalid_json", "invalid_schema", "invalid_citations"}
)


def usage_records(row):
    yield row
    if row["retry_attempted"]:
        yield {**dict(row), "attempted": 1, "usage_json": row["retry_usage_json"]}


def combined_usage(row):
    records = list(usage_records(row))
    if any(record["usage_json"] is None for record in records):
        return None
    values = [AIUsage.model_validate_json(record["usage_json"]) for record in records]
    if len(values) == 1:
        return values[0]
    try:
        return AIUsage(
            prompt_tokens=sum(value.prompt_tokens for value in values),
            completion_tokens=sum(value.completion_tokens for value in values),
            total_tokens=sum(value.total_tokens for value in values),
        )
    except ValueError:
        return None
