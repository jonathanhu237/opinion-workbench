from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Stable process health contract consumed by the local frontend."""

    status: Literal["ok"]
    service: Literal["longtian-public-opinion-api"]
