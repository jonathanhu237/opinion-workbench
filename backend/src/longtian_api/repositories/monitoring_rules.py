"""SQLite repository for monitoring-rule aggregates."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from longtian_api.database import Database


@dataclass(frozen=True)
class MonitoringRuleRecord:
    """Complete repository projection in stable term order."""

    id: int
    name: str
    terms: tuple[str, ...]
    enabled: bool


@dataclass(frozen=True)
class PreparedMonitoringRule:
    """Validated values and normalized identities accepted by the repository."""

    name: str
    normalized_name: str
    terms: tuple[tuple[str, str], ...]
    enabled: bool


class MonitoringRuleRepositoryError(Exception):
    """Base class for product-safe repository categories."""


class MonitoringRuleNameConflictError(MonitoringRuleRepositoryError):
    """A normalized rule name already exists."""


class MonitoringRuleNotFoundError(MonitoringRuleRepositoryError):
    """The requested stable rule ID does not exist."""


class MonitoringRuleRepositoryUnavailableError(MonitoringRuleRepositoryError):
    """SQLite could not complete an operation safely."""


class MonitoringRuleRepository:
    """Own monitoring-rule SQL, transactions, and deterministic assembly."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def initialize(self) -> None:
        self._database.initialize()

    def list(self, *, enabled: bool | None = None) -> tuple[MonitoringRuleRecord, ...]:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                if enabled is None:
                    rows = connection.execute(
                        """
                        SELECT
                          rules.id,
                          rules.name,
                          rules.enabled,
                          terms.value,
                          terms.position
                        FROM monitoring_rules AS rules
                        LEFT JOIN monitoring_rule_terms AS terms
                          ON terms.rule_id = rules.id
                        ORDER BY rules.id ASC, terms.position ASC
                        """
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT
                          rules.id,
                          rules.name,
                          rules.enabled,
                          terms.value,
                          terms.position
                        FROM monitoring_rules AS rules
                        LEFT JOIN monitoring_rule_terms AS terms
                          ON terms.rule_id = rules.id
                        WHERE rules.enabled = ?
                        ORDER BY rules.id ASC, terms.position ASC
                        """,
                        (int(enabled),),
                    ).fetchall()
                return _assemble_records(rows)
            finally:
                connection.close()

    def create(self, rule: PreparedMonitoringRule) -> MonitoringRuleRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            if _name_exists(connection, rule.normalized_name):
                raise MonitoringRuleNameConflictError
            timestamp = _utc_timestamp()
            cursor = connection.execute(
                """
                INSERT INTO monitoring_rules (
                  name, normalized_name, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    rule.name,
                    rule.normalized_name,
                    int(rule.enabled),
                    timestamp,
                    timestamp,
                ),
            )
            rule_id = cursor.lastrowid
            if rule_id is None:
                raise sqlite3.DatabaseError("SQLite did not return an inserted rule ID")
            _insert_terms(connection, rule_id, rule.terms)
            return _read_record(connection, rule_id)

    def replace(
        self, rule_id: int, rule: PreparedMonitoringRule
    ) -> MonitoringRuleRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            if not _rule_exists(connection, rule_id):
                raise MonitoringRuleNotFoundError
            if _name_exists(connection, rule.normalized_name, excluding_id=rule_id):
                raise MonitoringRuleNameConflictError
            timestamp = _utc_timestamp()
            connection.execute(
                """
                UPDATE monitoring_rules
                SET name = ?, normalized_name = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    rule.name,
                    rule.normalized_name,
                    int(rule.enabled),
                    timestamp,
                    rule_id,
                ),
            )
            connection.execute(
                "DELETE FROM monitoring_rule_terms WHERE rule_id = ?", (rule_id,)
            )
            _insert_terms(connection, rule_id, rule.terms)
            return _read_record(connection, rule_id)

    def delete(self, rule_id: int) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM monitoring_rules WHERE id = ?", (rule_id,)
            )
            if cursor.rowcount == 0:
                raise MonitoringRuleNotFoundError

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


@contextmanager
def _translate_storage_errors() -> Iterator[None]:
    try:
        yield
    except (MonitoringRuleNameConflictError, MonitoringRuleNotFoundError):
        raise
    except (OSError, sqlite3.Error):
        raise MonitoringRuleRepositoryUnavailableError from None


def _name_exists(
    connection: sqlite3.Connection,
    normalized_name: str,
    *,
    excluding_id: int | None = None,
) -> bool:
    if excluding_id is None:
        row = connection.execute(
            "SELECT 1 FROM monitoring_rules WHERE normalized_name = ?",
            (normalized_name,),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT 1
            FROM monitoring_rules
            WHERE normalized_name = ? AND id != ?
            """,
            (normalized_name, excluding_id),
        ).fetchone()
    return row is not None


def _rule_exists(connection: sqlite3.Connection, rule_id: int) -> bool:
    row = connection.execute(
        "SELECT 1 FROM monitoring_rules WHERE id = ?", (rule_id,)
    ).fetchone()
    return row is not None


def _insert_terms(
    connection: sqlite3.Connection,
    rule_id: int,
    terms: Sequence[tuple[str, str]],
) -> None:
    connection.executemany(
        """
        INSERT INTO monitoring_rule_terms (
          rule_id, value, normalized_value, position
        ) VALUES (?, ?, ?, ?)
        """,
        (
            (rule_id, value, normalized_value, position)
            for position, (value, normalized_value) in enumerate(terms)
        ),
    )


def _read_record(connection: sqlite3.Connection, rule_id: int) -> MonitoringRuleRecord:
    rows = connection.execute(
        """
        SELECT
          rules.id,
          rules.name,
          rules.enabled,
          terms.value,
          terms.position
        FROM monitoring_rules AS rules
        LEFT JOIN monitoring_rule_terms AS terms
          ON terms.rule_id = rules.id
        WHERE rules.id = ?
        ORDER BY terms.position ASC
        """,
        (rule_id,),
    ).fetchall()
    records = _assemble_records(rows)
    if not records:
        raise MonitoringRuleNotFoundError
    return records[0]


def _assemble_records(rows: Sequence[sqlite3.Row]) -> tuple[MonitoringRuleRecord, ...]:
    collected: dict[int, tuple[str, bool, list[str]]] = {}
    for row in rows:
        rule_id = int(row["id"])
        if rule_id not in collected:
            collected[rule_id] = (str(row["name"]), bool(row["enabled"]), [])
        term = row["value"]
        if term is not None:
            collected[rule_id][2].append(str(term))

    records: list[MonitoringRuleRecord] = []
    for rule_id, (name, enabled, terms) in collected.items():
        if not terms:
            raise sqlite3.DatabaseError("Monitoring rule has no terms")
        records.append(
            MonitoringRuleRecord(
                id=rule_id,
                name=name,
                terms=tuple(terms),
                enabled=enabled,
            )
        )
    return tuple(records)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
