"""Shared results filters explicitly use global first-entry time, not publication."""

from datetime import UTC, datetime

from longtian_api.repositories.results import ResultsRepository
from longtian_api.services.analysis_errors import AnalysisError


class ResultsService:
    def __init__(self, database):
        self.repository = ResultsRepository(database)

    def list(
        self,
        *,
        first_seen_from: datetime | None = None,
        first_seen_to: datetime | None = None,
        **kwargs,
    ):
        if any(
            value is not None and value.tzinfo is None
            for value in (first_seen_from, first_seen_to)
        ):
            raise AnalysisError("invalid_result_interval")
        if (
            first_seen_from is not None
            and first_seen_to is not None
            and first_seen_from >= first_seen_to
        ):
            raise AnalysisError("invalid_result_interval")
        return self.repository.list(
            first_seen_from=first_seen_from.astimezone(UTC).isoformat()
            if first_seen_from
            else None,
            first_seen_to=first_seen_to.astimezone(UTC).isoformat()
            if first_seen_to
            else None,
            **kwargs,
        )
