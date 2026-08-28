"""UTC interval arithmetic independent of browser work and monotonic waiting."""

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware clock is required")
    return value.astimezone(UTC)


def due_range(
    due: datetime, now: datetime, minutes: int
) -> tuple[int, datetime, datetime]:
    """Inclusive missed range and first future due, without a per-minute loop."""
    interval = timedelta(minutes=minutes)
    count = (utc(now) - utc(due)) // interval + 1
    if count < 1:
        raise ValueError("Occurrence is not due")
    return count, due + interval * (count - 1), due + interval * count
