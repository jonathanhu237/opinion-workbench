"""Portable, origin-independent UI preferences; no credentials are stored here."""

import json
import os
import tempfile
import threading
from pathlib import Path

_ALLOWED = frozenset({1, 2, 4, 8, 16})


class SummaryPreferenceService:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def read(self) -> int:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            value = data.get("summary_concurrency") if isinstance(data, dict) else None
            return value if type(value) is int and value in _ALLOWED else 8
        except (OSError, ValueError):
            return 8

    def update(self, value: int) -> int:
        if type(value) is not int or value not in _ALLOWED:
            raise ValueError("invalid summary concurrency")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=".preferences-",
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    json.dump({"summary_concurrency": value}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return value
