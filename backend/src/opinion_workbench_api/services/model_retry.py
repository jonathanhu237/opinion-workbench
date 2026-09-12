"""Bounded model retries with separate accounting for every network call."""

import asyncio
import inspect
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from opinion_workbench_api.services.ai_client import MAX_USAGE_TOKENS, AIUsage
from opinion_workbench_api.services.ai_errors import (
    AIError,
    transient_rate_limit_evidence,
)

MODEL_RATE_LIMIT_MAX_RETRIES = 2
MODEL_RATE_LIMIT_MAX_WAIT_SECONDS = 60.0
MODEL_RATE_LIMIT_BASE_SECONDS = 1.0
# The gate normally emits at most three events, but keep its diagnostic
# history bounded even when a caller supplies an unusually large retry budget.
MODEL_RATE_LIMIT_HISTORY_MAX = 256
MODEL_RETRY_NOTICE_MAX_NUMBER = 100

RETRYABLE_OUTPUT_ERRORS = frozenset(
    {"invalid_json", "invalid_schema", "invalid_citations"}
)


@dataclass(frozen=True, slots=True)
class ModelRateLimitEvent:
    """One provider rate-limit response, including an unknown usage result."""

    error: AIError
    retry_number: int
    delay_seconds: float
    will_retry: bool
    context: object | None = None

    @property
    def usage(self) -> AIUsage | None:
        value = getattr(self.error, "usage", None)
        if isinstance(value, AIUsage):
            return value
        try:
            return AIUsage.model_validate(value) if value is not None else None
        except (TypeError, ValueError):
            return None


class ModelRateLimitGate:
    """Coordinate a bounded, task-wide set of 429 retries.

    The gate delays all consumers after a provider says the shared destination is
    limited.  Retry count and wait budget are shared by the gate rather than
    reset for every worker (or for an output-format retry).  It never retries
    timeouts, malformed streams, or calls that already produced a parseable
    response.  Each rate-limit response is retained in ``history`` so callers
    can persist both known and unknown usage.
    """

    def __init__(
        self,
        *,
        max_retries: int = MODEL_RATE_LIMIT_MAX_RETRIES,
        max_wait_seconds: float = MODEL_RATE_LIMIT_MAX_WAIT_SECONDS,
        on_retry: Callable[[ModelRateLimitEvent], Any] | None = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._until = 0.0
        self._waited = 0.0
        self._retry_count = 0
        self._event_count = 0
        self._max_retries = max(0, int(max_retries))
        self._max_wait_seconds = max(0.0, float(max_wait_seconds))
        self._on_retry = on_retry
        self._history: list[ModelRateLimitEvent] = []

    @property
    def retries(self) -> int:
        return self._retry_count

    @property
    def waited_seconds(self) -> float:
        return self._waited

    @property
    def history(self) -> tuple[ModelRateLimitEvent, ...]:
        return tuple(self._history)

    async def complete(self, complete, *args, retry_context=None, **kwargs):
        while True:
            await self._wait_for_gate()
            try:
                return await complete(*args, **kwargs)
            except AIError as error:
                if not error.transient_rate_limit:
                    raise
                async with self._lock:
                    self._event_count += 1
                    retry_number = min(self._event_count, MODEL_RETRY_NOTICE_MAX_NUMBER)
                    delay = self._delay(error, self._retry_count)
                    will_retry = (
                        self._retry_count < self._max_retries
                        and self._waited + delay <= self._max_wait_seconds
                    )
                    if will_retry:
                        now = asyncio.get_running_loop().time()
                        self._retry_count += 1
                        self._waited += delay
                        self._until = max(self._until, now + delay)
                    event = ModelRateLimitEvent(
                        error=error,
                        retry_number=retry_number,
                        delay_seconds=delay if will_retry else 0.0,
                        will_retry=will_retry,
                        context=retry_context,
                    )
                    self._history.append(event)
                    if len(self._history) > MODEL_RATE_LIMIT_HISTORY_MAX:
                        del self._history[
                            : len(self._history) - MODEL_RATE_LIMIT_HISTORY_MAX
                        ]
                await self._notify(event)
                if not will_retry:
                    raise

    def _delay(self, error: AIError, retry_index: int) -> float:
        delay = error.retry_after_seconds
        if delay is not None:
            return max(0.0, float(delay))
        base = min(
            self._max_wait_seconds,
            MODEL_RATE_LIMIT_BASE_SECONDS * (2**retry_index),
        )
        return max(0.0, base * random.uniform(1.0, 1.25))

    async def _notify(self, event: ModelRateLimitEvent) -> None:
        if self._on_retry is None:
            return
        value = self._on_retry(event)
        if inspect.isawaitable(value):
            await value

    async def _wait_for_gate(self) -> None:
        while True:
            async with self._lock:
                delay = self._until - asyncio.get_running_loop().time()
            if delay <= 0:
                return
            await asyncio.sleep(delay)


def _row_value(row, key: str, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _validated_usage(value):
    """Return canonical provider usage, or ``None`` for unknown accounting."""
    try:
        if isinstance(value, AIUsage):
            return AIUsage.model_validate(value.model_dump(mode="json"))
        if isinstance(value, str):
            return AIUsage.model_validate_json(value)
        return AIUsage.model_validate(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _history_entry(value):
    """Normalize one persisted rate-limit event for bounded compaction."""
    if not isinstance(value, dict):
        return {"attempted": 1, "accounted": 0, "usage": None}
    usage = _validated_usage(value.get("usage"))
    attempted = value.get("attempted", 1)
    accounted = value.get("accounted", 1 if usage is not None else 0)
    if (
        type(attempted) is not int
        or attempted < 1
        or attempted > MAX_USAGE_TOKENS
        or type(accounted) is not int
        or accounted < 0
        or accounted > attempted
        or (usage is None and accounted != 0)
        or (usage is not None and accounted == 0)
    ):
        return {"attempted": 1, "accounted": 0, "usage": None}
    return {
        "attempted": attempted,
        "accounted": accounted,
        "usage": usage.model_dump(mode="json") if usage is not None else None,
    }


def _compact_history(values):
    """Preserve counts and known tokens when event detail reaches its bound."""
    attempted = accounted = prompt = completion = total = 0
    count_overflow = False
    for value in values:
        entry = _history_entry(value)
        attempted += entry["attempted"]
        accounted += entry["accounted"]
        usage = _validated_usage(entry["usage"])
        if usage is not None:
            prompt += usage.prompt_tokens
            completion += usage.completion_tokens
            total += usage.total_tokens
        if attempted > MAX_USAGE_TOKENS or accounted > MAX_USAGE_TOKENS:
            count_overflow = True
            attempted = min(attempted, MAX_USAGE_TOKENS)
            accounted = min(accounted, MAX_USAGE_TOKENS)
    usage = None
    try:
        usage = AIUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
        )
    except ValueError:
        # An overflowing sum cannot be exposed as a trustworthy token total.
        # Mark the compacted record unknown as well; otherwise a reader could
        # see accounted == attempted with null token fields and incorrectly
        # reconstruct a complete zero-token aggregate.
        accounted = 0
    if count_overflow or accounted == 0:
        # The bounded public counters cannot represent the full history, or no
        # event had validated usage. In either case do not serialize a
        # synthetic zero-token usage record.
        accounted = 0
        usage = None
    return [
        {
            "attempted": attempted,
            "accounted": accounted,
            "usage": usage.model_dump(mode="json") if usage is not None else None,
        }
    ]


def append_rate_limit_history(raw, usage, *, max_entries=16):
    """Append one event without erasing known usage from corrupt/full history.

    Normal model execution produces far fewer than ``max_entries`` events per
    attempt.  If old data is unexpectedly full, collapse it into one aggregate
    record that retains attempted/accounted counts and token totals, then add
    the new event.  This keeps storage bounded without turning a known prefix
    into a clean zero.
    """
    unknown_history = False
    try:
        values = json.loads(raw or "[]")
        if not isinstance(values, list):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError):
        values = [{"attempted": 1, "accounted": 0, "usage": None}]
        unknown_history = True
    normalized = [_history_entry(value) for value in values]
    if unknown_history or len(normalized) >= max_entries:
        normalized = _compact_history(normalized)
    normalized.append(_history_entry({"usage": usage}))
    return normalized


def _rate_limit_records(row):
    raw = _row_value(row, "rate_limit_attempts_json")
    if raw is None:
        return
    try:
        values = json.loads(raw)
        if not isinstance(values, list):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError):
        # A corrupt history is still an attempted request with unknown usage.
        yield {
            **dict(row),
            "attempted": 1,
            "accounted": 0,
            "usage_json": None,
            "reused_from_attempt_id": None,
            "reused_from_node_id": None,
        }
        return
    for value in values:
        entry = _history_entry(value)
        usage_json = (
            AIUsage.model_validate(entry["usage"]).model_dump_json()
            if entry["usage"] is not None
            else None
        )
        # Preserve both repository row spellings.  Content-analysis rows use
        # ``reused_from_attempt_id`` while topic-report nodes use
        # ``reused_from_node_id``; aggregate readers must not lose or reject a
        # known rate-limit usage record because it came from this synthetic
        # per-call projection.  Compact entries carry their aggregate count in
        # ``accounted`` while retaining a single bounded token total.
        yield {
            **dict(row),
            "attempted": entry["attempted"],
            "accounted": entry["accounted"],
            "usage_json": usage_json,
            "reused_from_attempt_id": None,
            "reused_from_node_id": None,
        }


def _final_rate_limit_is_retryable(row) -> bool:
    """Tell whether the terminal rate-limit error is already in history."""
    try:
        error = json.loads(_row_value(row, "error_json"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(error, dict) or error.get("code") != "ai_rate_limited":
        return False
    diagnostic = error.get("provider_diagnostic")
    if not isinstance(diagnostic, dict):
        return False
    return transient_rate_limit_evidence(
        diagnostic.get("provider_code"), diagnostic.get("retry_after_seconds")
    )


def usage_records(row):
    """Yield the initial, format-retry, and rate-limit network attempts.

    ``attempted=1`` is the legacy projection for the current/last ordinary
    model response. A terminal transient rate-limit response is instead already
    represented by the rate history, so do not count that marker twice. If a
    format retry had a completed first response, its ordinary marker remains
    meaningful even when the second response is the terminal rate limit.
    """
    rate_records = list(_rate_limit_records(row))
    terminal_rate = bool(rate_records) and _final_rate_limit_is_retryable(row)
    ordinary = {
        **dict(row),
        "attempted": 1,
        "accounted": (
            1 if _validated_usage(_row_value(row, "usage_json")) is not None else 0
        ),
        "usage_json": (
            _validated_usage(_row_value(row, "usage_json")).model_dump_json()
            if _validated_usage(_row_value(row, "usage_json")) is not None
            else None
        ),
    }
    ordinary_attempted = bool(
        _row_value(row, "attempted", 0) or _row_value(row, "retry_attempted", 0)
    )
    if ordinary_attempted and (
        not terminal_rate or _row_value(row, "retry_attempted", 0)
    ):
        yield ordinary
    if _row_value(row, "retry_attempted", 0) and not terminal_rate:
        retry_usage = _validated_usage(_row_value(row, "retry_usage_json"))
        yield {
            **dict(row),
            "attempted": 1,
            "accounted": 1 if retry_usage is not None else 0,
            "usage_json": retry_usage.model_dump_json() if retry_usage else None,
        }
    yield from rate_records


def combined_usage(row):
    """Return known token usage without turning unknown calls into zeroes."""
    values = [
        AIUsage.model_validate_json(record["usage_json"])
        for record in usage_records(row)
        if record["usage_json"] is not None
    ]
    if not values:
        return None
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
