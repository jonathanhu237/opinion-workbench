"""Read-only homepage workbench service."""

from datetime import UTC, datetime

from longtian_api.repositories.workbench import WorkbenchRepository
from longtian_api.schemas.workbench import WorkbenchSnapshot
from longtian_api.services.workbench_errors import WorkbenchError


class WorkbenchService:
    def __init__(
        self,
        database,
        *,
        repository=None,
        clock=None,
        available=True,
        automation_available=True,
    ):
        self.repository = repository or WorkbenchRepository(
            database, automation_available=automation_available
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self.available = available

    def read(self) -> WorkbenchSnapshot:
        if not self.available:
            raise WorkbenchError("workbench_unavailable")
        try:
            observed_at = self._clock().astimezone(UTC).isoformat()
            return self.repository.read(observed_at)
        except WorkbenchError:
            raise
        except Exception:
            raise WorkbenchError("workbench_unavailable") from None
