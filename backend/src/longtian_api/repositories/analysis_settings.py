"""Immutable prompt versions and explicit provider-bound authorization."""

import hashlib
import sqlite3

from longtian_api.repositories.analysis_shared import (
    AnalysisRepository,
    date,
    timestamp,
)
from longtian_api.schemas.analysis_settings import (
    INITIAL_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    AnalysisSettings,
    AutomationSettings,
    AutomationUpdate,
    PromptStage,
    PromptUpdate,
    PromptVersion,
)
from longtian_api.services.ai_errors import AIError
from longtian_api.services.analysis_errors import AnalysisError


def read_prompt(connection: sqlite3.Connection, version_id: int) -> PromptVersion:
    row = connection.execute(
        "SELECT * FROM analysis_prompt_versions WHERE id=?", (version_id,)
    ).fetchone()
    if row is None:
        raise AnalysisError("analysis_storage_unavailable")
    return PromptVersion(**{**dict(row), "created_at": date(row["created_at"])})


class AnalysisSettingsRepository(AnalysisRepository):
    def __init__(self, database, *, available=False):
        super().__init__(database)
        self.available = available

    def read(self) -> AnalysisSettings:
        with self.connection() as connection:
            return self._read(connection)

    def _read(self, connection) -> AnalysisSettings:
        row = connection.execute(
            "SELECT * FROM analysis_settings WHERE id=1"
        ).fetchone()
        if row is None:
            raise AnalysisError("analysis_storage_unavailable")
        return AnalysisSettings(
            initial_prompt=read_prompt(connection, row["initial_prompt_version_id"]),
            report_prompt=read_prompt(connection, row["report_prompt_version_id"]),
            automation=AutomationSettings(
                enabled=bool(row["enabled"]),
                revision=row["revision"],
                approved_configuration_revision=row["approved_configuration_revision"],
                activation_content_id=row["activation_content_id"],
                available=self.available,
            ),
        )

    def save_prompt(
        self, stage: PromptStage, payload: PromptUpdate
    ) -> AnalysisSettings:
        # stage is an application Literal, never a user-controlled SQL identifier.
        column = (
            "initial_prompt_version_id"
            if stage == "initial"
            else "report_prompt_version_id"
        )
        with self.connection(write=True) as connection:
            current = self._read(connection)
            prompt = (
                current.initial_prompt if stage == "initial" else current.report_prompt
            )
            if prompt.id != payload.expected_version_id:
                raise AnalysisError("analysis_prompt_changed")
            if prompt.instructions != payload.instructions:
                version_id = connection.execute(
                    """INSERT INTO
                      analysis_prompt_versions(stage,instructions,content_hash,schema_version,created_at)
                       VALUES (?,?,?,?,?)""",
                    (
                        stage,
                        payload.instructions,
                        hashlib.sha256(payload.instructions.encode()).hexdigest(),
                        INITIAL_SCHEMA_VERSION
                        if stage == "initial"
                        else REPORT_SCHEMA_VERSION,
                        timestamp(),
                    ),
                ).lastrowid
                connection.execute(
                    f"UPDATE analysis_settings SET {column}=? WHERE id=1", (version_id,)
                )
            return self._read(connection)

    def save_automation(self, payload: AutomationUpdate) -> AnalysisSettings:
        with self.connection(write=True) as connection:
            current = self._read(connection)
            if current.automation.revision != payload.expected_revision:
                raise AnalysisError("analysis_policy_changed")
            if payload.enabled:
                provider = connection.execute(
                    "SELECT revision FROM ai_settings WHERE id=1"
                ).fetchone()
                if provider is None:
                    raise AIError("ai_configuration_required")
                if provider["revision"] != payload.configuration_revision:
                    raise AIError("ai_configuration_changed")
            if (
                current.automation.enabled,
                current.automation.approved_configuration_revision,
            ) != (
                payload.enabled,
                payload.configuration_revision,
            ):
                connection.execute(
                    """UPDATE analysis_settings SET
                      enabled=?,approved_configuration_revision=?,revision=revision+1
                       WHERE id=1""",
                    (int(payload.enabled), payload.configuration_revision),
                )
            return self._read(connection)
