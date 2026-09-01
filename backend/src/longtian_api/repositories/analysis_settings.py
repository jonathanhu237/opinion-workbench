"""Immutable prompt versions and explicit provider-bound authorization."""

import hashlib
import sqlite3
from collections.abc import Mapping

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
    PromptChoice,
    PromptSnapshot,
    PromptStage,
    PromptVersion,
)
from longtian_api.services.ai_errors import AIError
from longtian_api.services.analysis_errors import AnalysisError


def read_prompt(
    connection: sqlite3.Connection,
    version_id: int,
    *,
    mode: str | None = None,
) -> PromptVersion:
    row = connection.execute(
        "SELECT * FROM analysis_prompt_versions WHERE id=?", (version_id,)
    ).fetchone()
    if row is None:
        raise AnalysisError("analysis_storage_unavailable")
    default_instructions = _default_instructions(str(row["stage"]))
    default_hash = hashlib.sha256(default_instructions.encode("utf-8")).hexdigest()
    default_row = connection.execute(
        """SELECT id FROM analysis_prompt_versions
           WHERE stage=? AND schema_version=? AND content_hash=?
             AND instructions=? ORDER BY id LIMIT 1""",
        (row["stage"], row["schema_version"], default_hash, default_instructions),
    ).fetchone()
    prompt = PromptVersion(
        **{
            **dict(row),
            "created_at": date(row["created_at"]),
            "version_id": version_id,
            "mode": mode
            or (
                "default"
                if default_row is not None and int(default_row["id"]) == version_id
                else "custom"
            ),
        }
    )
    expected_schema = (
        INITIAL_SCHEMA_VERSION if prompt.stage == "initial" else REPORT_SCHEMA_VERSION
    )
    if prompt.schema_version != expected_schema:
        raise AnalysisError("analysis_storage_unavailable")
    if (
        hashlib.sha256(prompt.instructions.encode("utf-8")).hexdigest()
        != prompt.content_hash
    ):
        raise AnalysisError("analysis_storage_unavailable")
    # ``mode`` is an execution-source assertion, not presentation metadata.
    # A row marked as the built-in default must still contain the current
    # code-owned template; otherwise a corrupted/raw SQL update could make a
    # future operation silently execute custom text as the default.
    if mode == "default" and prompt.instructions != default_instructions:
        raise AnalysisError("analysis_storage_unavailable")
    # A collision is unsafe for every source mode: the same digest is part of
    # the cache key and execution proof, so reading either colliding row could
    # alias work generated from a different prompt.  Fail closed even for a
    # historical/custom row rather than trusting a collision merely because it
    # is not currently being presented as the built-in default.
    collision = connection.execute(
        """SELECT 1 FROM analysis_prompt_versions
           WHERE stage=? AND schema_version=? AND content_hash=?
             AND instructions<>? LIMIT 1""",
        (
            prompt.stage,
            prompt.schema_version,
            prompt.content_hash,
            prompt.instructions,
        ),
    ).fetchone()
    if collision is not None:
        raise AnalysisError("analysis_storage_unavailable")
    return prompt


def _prompt_schema(stage: PromptStage) -> str:
    return INITIAL_SCHEMA_VERSION if stage == "initial" else REPORT_SCHEMA_VERSION


def _default_instructions(stage: PromptStage) -> str:
    from longtian_api.schemas.analysis_settings import (
        DEFAULT_INITIAL_INSTRUCTIONS,
        DEFAULT_REPORT_INSTRUCTIONS,
    )

    return (
        DEFAULT_INITIAL_INSTRUCTIONS
        if stage == "initial"
        else DEFAULT_REPORT_INSTRUCTIONS
    )


def _snapshot(prompt: PromptVersion, mode: str) -> PromptSnapshot:
    return PromptSnapshot(
        mode=mode,
        version_id=prompt.id,
        instructions=prompt.instructions,
        content_hash=prompt.content_hash,
        schema_version=prompt.schema_version,
    )


def prompt_snapshot(
    connection: sqlite3.Connection,
    stage: PromptStage,
    version_id: int,
    *,
    mode: str | None = None,
) -> PromptSnapshot:
    """Read and validate an immutable prompt row as an execution snapshot."""

    prompt = read_prompt(connection, version_id, mode=mode)
    if prompt.stage != stage:
        raise AnalysisError("analysis_storage_unavailable")
    resolved_mode = mode or (
        "default" if prompt.instructions == _default_instructions(stage) else "custom"
    )
    if resolved_mode not in {"default", "custom", "legacy"}:
        raise AnalysisError("analysis_storage_unavailable")
    return _snapshot(prompt, resolved_mode)


def _canonical_default(
    connection: sqlite3.Connection, stage: PromptStage, *, create: bool = True
) -> PromptVersion:
    """Return the code-owned built-in row, failing closed on hash collisions."""

    instructions = _default_instructions(stage)
    schema = _prompt_schema(stage)
    digest = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
    rows = connection.execute(
        """SELECT * FROM analysis_prompt_versions
           WHERE stage=? AND schema_version=? AND content_hash=? ORDER BY id""",
        (stage, schema, digest),
    ).fetchall()
    if rows:
        # A digest collision is storage corruption even when a valid-looking
        # canonical row is present alongside it.  Do not silently select the
        # matching row and leave a colliding version available to future
        # admissions.
        if any(row["instructions"] != instructions for row in rows):
            raise AnalysisError("analysis_storage_unavailable")
        return read_prompt(connection, rows[0]["id"])
    if not create:
        raise AnalysisError("analysis_storage_unavailable")
    row = connection.execute(
        """INSERT INTO analysis_prompt_versions(
          stage,instructions,content_hash,schema_version,created_at)
          VALUES (?,?,?,?,?) RETURNING id""",
        (stage, instructions, digest, schema, timestamp()),
    ).fetchone()
    return read_prompt(connection, row[0])


def resolve_prompt_choice(
    connection: sqlite3.Connection,
    stage: PromptStage,
    choice: PromptChoice | Mapping[str, object] | None,
) -> PromptSnapshot:
    """Resolve a default/custom choice to an immutable version row.

    The helper intentionally compares the complete text after selecting by
    digest.  A matching digest with different text is treated as corrupted
    storage instead of silently trusting a collision.
    """

    if choice is None:
        choice = {"mode": "default"}
    mode = (
        choice.get("mode")
        if isinstance(choice, Mapping)
        else getattr(choice, "mode", None)
    )
    if isinstance(choice, Mapping):
        expected_keys = {"mode"} if mode == "default" else {
            "mode",
            "instructions",
        }
        if set(choice) != expected_keys:
            raise AnalysisError("invalid_analysis_prompt")
    if mode == "default":
        return _snapshot(_canonical_default(connection, stage), "default")
    if mode != "custom":
        raise AnalysisError("invalid_analysis_prompt")
    instructions = (
        choice.get("instructions")
        if isinstance(choice, Mapping)
        else getattr(choice, "instructions", None)
    )
    if not isinstance(instructions, str):
        raise AnalysisError("invalid_analysis_prompt")
    try:
        if (
            not 1 <= len(instructions) <= 8000
            or not instructions.strip()
            or "\x00" in instructions
        ):
            raise ValueError
        instructions.encode("utf-8", errors="strict")
    except (ValueError, UnicodeError):
        raise AnalysisError("invalid_analysis_prompt") from None
    digest = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
    schema = _prompt_schema(stage)
    rows = connection.execute(
        """SELECT * FROM analysis_prompt_versions
           WHERE stage=? AND schema_version=? AND content_hash=? ORDER BY id""",
        (stage, schema, digest),
    ).fetchall()
    if rows:
        if any(row["instructions"] != instructions for row in rows):
            raise AnalysisError("analysis_storage_unavailable")
        return _snapshot(read_prompt(connection, rows[0]["id"]), "custom")
    row = connection.execute(
        """INSERT INTO analysis_prompt_versions(
          stage,instructions,content_hash,schema_version,created_at)
          VALUES (?,?,?,?,?) RETURNING id""",
        (stage, instructions, digest, schema, timestamp()),
    ).fetchone()
    return _snapshot(read_prompt(connection, row[0]), "custom")


def resolve_prompt_version(
    connection: sqlite3.Connection,
    stage: PromptStage,
    version_id: int,
    *,
    mode: str | None = None,
) -> PromptSnapshot:
    """Resolve a previously frozen version for legacy/internal callers."""

    return prompt_snapshot(connection, stage, version_id, mode=mode)


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
            # The settings endpoint is an immutable catalog, not a mutable
            # prompt editor.  Historical pointers remain in storage for old
            # jobs, while all new product choices resolve through these
            # code-owned defaults or task-local custom versions.
            initial_prompt=_canonical_default(connection, "initial", create=False),
            report_prompt=_canonical_default(connection, "report", create=False),
            automation=AutomationSettings(
                enabled=bool(row["enabled"]),
                revision=row["revision"],
                approved_configuration_revision=row["approved_configuration_revision"],
                activation_content_id=row["activation_content_id"],
                available=self.available,
            ),
        )

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
