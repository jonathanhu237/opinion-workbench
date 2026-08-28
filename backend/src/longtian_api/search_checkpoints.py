"""SQLite proof validation shared by migration and batch checkpoint projections."""

import sqlite3
from dataclasses import dataclass
from typing import Literal

CheckpointBasis = Literal["explicit", "legacy_inferred", "mixed", "unknown"]


@dataclass(frozen=True, slots=True)
class Checkpoint:
    completed: int
    remaining: int
    next_position: int | None
    basis: CheckpointBasis
    available: bool


def valid_terms(rows: list[sqlite3.Row]) -> bool:
    return 1 <= len(rows) <= 20 and all(
        row["position"] == index
        and isinstance(row["value"], str)
        and 1 <= len(row["value"]) <= 200
        and row["value"] == row["value"].strip()
        for index, row in enumerate(rows)
    )


def legacy_prefix(run: sqlite3.Row, terms: list[sqlite3.Row]) -> int | None:
    """v1's fail-fast ordered starts prove only the preceding terms."""
    if not valid_terms(terms):
        return None
    position = run["current_term_position"]
    if position is not None and (
        type(position) is not int or not 0 <= position < len(terms)
    ):
        return None
    if run["status"] in {"completed_with_results", "completed_empty"}:
        return len(terms) if position == len(terms) - 1 else None
    return position or 0


def backfill_legacy_completions(connection: sqlite3.Connection, timestamp: str) -> None:
    for run in connection.execute("SELECT * FROM search_runs").fetchall():
        terms = connection.execute(
            "SELECT position, value FROM search_run_terms WHERE run_id = ? ORDER BY "
            "position",
            (run["id"],),
        ).fetchall()
        prefix = legacy_prefix(run, terms)
        if prefix is None:
            continue
        counts = connection.execute(
            """SELECT term_position, COUNT(*) AS count FROM search_run_content_terms
               WHERE run_id = ? GROUP BY term_position""",
            (run["id"],),
        ).fetchall()
        if any(row["count"] > run["max_results_per_term"] for row in counts):
            continue
        proof = (
            "legacy_run_succeeded"
            if run["status"] in {"completed_with_results", "completed_empty"}
            else "legacy_next_term_started"
        )
        for position in range(prefix):
            connection.execute(
                """
                INSERT INTO search_run_term_completions
                  (run_id, term_position, proof, result_count, completed_at,
                  recorded_at)
                VALUES (?, ?, ?, (
                  SELECT COUNT(*) FROM search_run_content_terms
                  WHERE run_id = ? AND term_position = ?
                ), NULL, ?)
                """,
                (run["id"], position, proof, run["id"], position, timestamp),
            )


def item_checkpoint(
    connection: sqlite3.Connection, batch_id: int, position: int
) -> Checkpoint:
    terms = connection.execute(
        "SELECT position, value FROM search_batch_terms WHERE batch_id = ? ORDER BY "
        "position",
        (batch_id,),
    ).fetchall()
    unavailable = Checkpoint(0, len(terms), None, "unknown", False)
    if not valid_terms(terms):
        return unavailable
    item = connection.execute(
        "SELECT platform FROM search_batch_items WHERE batch_id = ? AND position = ?",
        (batch_id, position),
    ).fetchone()
    runs = connection.execute(
        """
        SELECT runs.*, attempts.attempt_number FROM search_batch_attempts AS attempts
        JOIN search_runs AS runs ON runs.id = attempts.search_run_id
        WHERE attempts.batch_id = ? AND attempts.item_position = ?
        ORDER BY attempts.attempt_number
        """,
        (batch_id, position),
    ).fetchall()
    proven: set[int] = set()
    sources: set[str] = set()
    for number, run in enumerate(runs, 1):
        snapshot = connection.execute(
            "SELECT position, value FROM search_run_terms WHERE run_id = ? ORDER BY "
            "position",
            (run["id"],),
        ).fetchall()
        if (
            item is None
            or run["platform"] != item["platform"]
            or run["attempt_number"] != number
            or [tuple(row) for row in snapshot] != [tuple(row) for row in terms]
        ):
            return unavailable
        start = run["execution_start_term_position"]
        current = run["current_term_position"]
        if (
            type(start) is not int
            or not 0 <= start < len(terms)
            or (
                current is not None
                and (type(current) is not int or not start <= current < len(terms))
            )
        ):
            return unavailable
        if run["search_protocol_version"] == 1:
            prefix = legacy_prefix(run, snapshot)
            if prefix is None or start != 0:
                return unavailable
        else:
            prefix = None
            # A new attempt may start only at the already-proven prefix.
            if proven != set(range(start)):
                return unavailable
        proofs = connection.execute(
            """
            SELECT term_position, proof, result_count, completed_at
            FROM search_run_term_completions WHERE run_id = ? ORDER BY term_position
            """,
            (run["id"],),
        ).fetchall()
        for index, proof in enumerate(proofs, start):
            term_position = proof["term_position"]
            expected_proof = (
                (
                    "legacy_run_succeeded"
                    if run["status"] in {"completed_with_results", "completed_empty"}
                    else "legacy_next_term_started"
                )
                if prefix is not None
                else "worker_term_completed"
            )
            count = connection.execute(
                """SELECT COUNT(*) FROM search_run_content_terms
                   WHERE run_id = ? AND term_position = ?""",
                (run["id"], term_position),
            ).fetchone()[0]
            if (
                term_position != index
                or term_position >= len(terms)
                or proof["proof"] != expected_proof
                or proof["result_count"] != count
                or (prefix is not None and proof["completed_at"] is not None)
                or (
                    prefix is None
                    and (
                        proof["completed_at"] is None
                        or current is None
                        or term_position > current
                    )
                )
            ):
                return unavailable
            proven.add(term_position)
            sources.add("legacy" if prefix is not None else "explicit")
        if prefix is not None and len(proofs) != prefix:
            return unavailable
        if prefix is None:
            next_position = start + len(proofs)
            # A committed start is either the just-completed term or the next
            # unconfirmed term. A larger jump means completion evidence is gone.
            if current is not None and current not in {
                max(start, next_position - 1),
                next_position,
            }:
                return unavailable
            if run["status"] in {"completed_with_results", "completed_empty"} and (
                next_position != len(terms)
            ):
                return unavailable
    if proven != set(range(len(proven))):
        return unavailable
    completed = len(proven)
    basis: CheckpointBasis = (
        "mixed"
        if len(sources) == 2
        else "explicit"
        if "explicit" in sources
        else "legacy_inferred"
        if sources
        else "unknown"
    )
    return Checkpoint(
        completed,
        len(terms) - completed,
        completed if completed < len(terms) else None,
        basis,
        True,
    )
