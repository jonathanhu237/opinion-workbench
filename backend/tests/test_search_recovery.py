"""Offline recovery acceptance: no user database, browser, network or model."""

import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_search_batches import _app, _wait_for_batch

import longtian_api.database as migration_module
from longtian_api.database import Database, _migrate_to_version_10
from longtian_api.repositories.search_batches import (
    SearchBatchRecoveryUnavailableError,
    SearchBatchRepository,
    SearchBatchRepositoryUnavailableError,
    SearchBatchStateChangedError,
)
from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchRunNotActiveError,
    SearchRunRepository,
    SearchRunRepositoryUnavailableError,
)
from longtian_api.services.collector_contracts import (
    ManualPageWorkerResult,
    SearchWorkerResult,
)
from longtian_api.services.search_batches import SearchBatchService
from longtian_api.services.settled_tasks import database_call


def _item(identity):
    return SearchContentInput(
        identity,
        "post",
        "公开内容",
        "",
        "",
        "",
        "",
        f"https://m.weibo.cn/detail/{identity}",
        "2026-08-28T00:00:00+00:00",
    )


def setup_batch(tmp_path: Path, terms=("词一", "词二"), platforms=("wb",)):
    database = Database(tmp_path / "recovery.sqlite3")
    database.initialize()
    batches, runs = SearchBatchRepository(database), SearchRunRepository(database)
    batch = batches.create_batch(
        monitoring_rule_id=1,
        rule_name="测试规则",
        terms=terms,
        platforms=platforms,
        max_results_per_term=10,
    )
    batches.mark_running(batch.id)
    run = batches.create_attempt(batch.id, 0)
    runs.mark_running(run.id)
    return database, batches, runs, batch.id, run.id


def control(batch):
    position = batch.current_item_position
    item = batch.items[position]
    return dict(
        item_position=position,
        expected_revision=batch.control_revision,
        expected_run_id=item.latest_attempt.run.id if item.latest_attempt else None,
    )


def test_six_completed_empty_terms_resume_at_seventh_and_keep_snapshot(tmp_path):
    terms = tuple(f"词{i}" for i in range(9))
    _, batches, runs, batch_id, run_id = setup_batch(tmp_path, terms)
    for position in range(6):
        runs.set_progress(run_id, position)
        runs.complete_term(run_id, position, 0)
    runs.set_progress(run_id, 6)
    runs.finish(run_id, "structure_changed")
    paused = batches.finish_item(batch_id, 0, "structure_changed")
    assert paused.items[0].checkpoint.completed == 6
    assert paused.items[0].checkpoint.basis == "explicit"
    args = control(paused)
    batches.continue_batch(batch_id, **args)
    with pytest.raises(SearchBatchStateChangedError):
        batches.skip_item(batch_id, **args)
    retry = batches.create_attempt(batch_id, 0)
    assert retry.execution_start_term_position == 6
    assert retry.terms == terms
    runs.mark_running(retry.id)
    runs.set_progress(retry.id, 6)
    runs.complete_term(retry.id, 6, 0)
    runs.set_progress(retry.id, 7)
    runs.finish(retry.id, "login_required")
    paused = batches.finish_item(batch_id, 0, "login_required")
    batches.continue_batch(batch_id, **control(paused))
    assert batches.create_attempt(batch_id, 0).execution_start_term_position == 7
    assert runs.get(run_id).status == "structure_changed"


def test_all_confirmed_but_failed_final_result_completes_without_new_attempt(tmp_path):
    _, batches, runs, batch_id, run_id = setup_batch(tmp_path)
    for position in range(2):
        runs.set_progress(run_id, position)
        runs.complete_term(run_id, position, 0)
    runs.finish(run_id, "browser_unavailable")
    paused = batches.finish_item(batch_id, 0, "browser_unavailable")
    assert paused.items[0].checkpoint.next_position is None
    resumed = batches.continue_batch(batch_id, **control(paused))
    assert resumed.items[0].completion_basis == "confirmed_terms"
    assert resumed.items[0].attempt_count == 1
    assert batches.finalize(batch_id).status == "completed"
    assert runs.get(run_id).status == "browser_unavailable"


def test_partial_results_union_keeps_earliest_kind_and_all_term_matches(tmp_path):
    _, batches, runs, batch_id, run_id = setup_batch(tmp_path)
    runs.set_progress(run_id, 0)
    runs.observe_item(run_id=run_id, term_position=0, item=_item("a"))
    runs.complete_term(run_id, 0, 1)
    runs.set_progress(run_id, 1)
    runs.observe_item(run_id=run_id, term_position=1, item=_item("b"))
    runs.finish(run_id, "manual_challenge_required")
    paused = batches.finish_item(batch_id, 0, "manual_challenge_required")
    batches.continue_batch(batch_id, **control(paused))
    retry = batches.create_attempt(batch_id, 0)
    runs.mark_running(retry.id)
    runs.set_progress(retry.id, 1)
    for identity in ("a", "b", "c"):
        runs.observe_item(run_id=retry.id, term_position=1, item=_item(identity))
    runs.complete_term(retry.id, 1, 3)
    runs.finish(retry.id, "completed_with_results")
    batches.finish_item(batch_id, 0, "completed_with_results")
    item = batches.get(batch_id).items[0]
    assert (item.new_count, item.repeated_count, item.total_count) == (3, 0, 3)
    records, total = batches.list_results(
        batch_id=batch_id, position=0, kind="all", limit=50, offset=0
    )
    assert total == 3
    first = next(r for r in records if r.result.platform_content_id == "a")
    assert first.source_run_id == run_id
    assert first.result.matched_terms == ("词一", "词二")
    assert runs.get(retry.id).repeated_count == 2
    assert (
        batches.list_results(
            batch_id=batch_id, position=0, kind="repeated", limit=1, offset=0
        )[1]
        == 0
    )


@pytest.mark.parametrize(
    "status",
    [
        "login_required",
        "manual_challenge_required",
        "platform_blocked_or_rate_limited",
        "structure_changed",
        "browser_unavailable",
        "timed_out",
        "internal_error",
    ],
)
def test_every_failure_pauses_and_skip_is_not_success(tmp_path, status):
    _, batches, runs, batch_id, run_id = setup_batch(tmp_path, platforms=("wb",))
    runs.finish(run_id, status)
    paused = batches.finish_item(batch_id, 0, status)
    assert paused.status == "paused_for_manual_action"
    skipped = batches.skip_item(batch_id, **control(paused))
    assert skipped.items[0].status == "skipped"
    assert batches.finalize(batch_id).status == "completed_with_failures"


def test_corrupt_proof_disables_continue_but_preserves_skip(tmp_path):
    database, batches, runs, batch_id, run_id = setup_batch(tmp_path)
    runs.set_progress(run_id, 0)
    runs.complete_term(run_id, 0, 0)
    runs.set_progress(run_id, 1)
    runs.complete_term(run_id, 1, 0)
    runs.finish(run_id, "internal_error")
    batches.finish_item(batch_id, 0, "internal_error")
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM search_run_term_completions WHERE term_position = 0"
        )
    paused = batches.get(batch_id)
    assert not paused.items[0].checkpoint.available
    with pytest.raises(SearchBatchRecoveryUnavailableError):
        batches.continue_batch(batch_id, **control(paused))
    assert batches.skip_item(batch_id, **control(paused)).items[0].status == "skipped"


@pytest.mark.parametrize("retained_proofs", [0, 2])
def test_current_position_cannot_jump_a_missing_completion_tail(
    tmp_path, retained_proofs
):
    database, batches, runs, batch_id, run_id = setup_batch(
        tmp_path, terms=tuple(f"词{position}" for position in range(9))
    )
    for position in range(6):
        runs.set_progress(run_id, position)
        runs.complete_term(run_id, position, 0)
    runs.set_progress(run_id, 6)
    runs.finish(run_id, "internal_error")
    batches.finish_item(batch_id, 0, "internal_error")
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM search_run_term_completions WHERE term_position >= ?",
            (retained_proofs,),
        )
    paused = batches.get(batch_id)
    assert not paused.items[0].checkpoint.available
    with pytest.raises(SearchBatchRecoveryUnavailableError):
        batches.continue_batch(batch_id, **control(paused))
    assert batches.skip_item(batch_id, **control(paused)).items[0].status == "skipped"
    assert runs.get(run_id).status == "internal_error"


def test_successful_v2_attempt_with_a_missing_final_proof_is_unavailable(tmp_path):
    database, batches, runs, batch_id, run_id = setup_batch(tmp_path)
    for position in range(2):
        runs.set_progress(run_id, position)
        runs.complete_term(run_id, position, 0)
    runs.finish(run_id, "completed_empty")
    batches.finish_item(batch_id, 0, "completed_empty")
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM search_run_term_completions WHERE term_position = 1"
        )
    assert not batches.get(batch_id).items[0].checkpoint.available
    assert runs.get(run_id).status == "completed_empty"


def test_checkpoint_accepts_both_sides_of_each_completion_commit(tmp_path):
    _, batches, runs, batch_id, run_id = setup_batch(tmp_path)
    assert batches.get(batch_id).items[0].checkpoint.available
    for position in range(2):
        runs.set_progress(run_id, position)
        started = batches.get(batch_id).items[0].checkpoint
        assert started.available and started.completed == position
        runs.complete_term(run_id, position, 0)
        completed = batches.get(batch_id).items[0].checkpoint
        assert completed.available and completed.completed == position + 1


@pytest.mark.parametrize(
    "status", ["completed_empty", "structure_changed", "cancelled"]
)
def test_api_exposes_terminal_attempt_before_item_finalization_without_rewriting(
    tmp_path, status
):
    worker = RecoveryWorker()
    with TestClient(_app(tmp_path / "recovery.sqlite3", worker)) as client:
        _, batches, runs, batch_id, run_id = setup_batch(tmp_path)
        for position in range(2):
            runs.set_progress(run_id, position)
            runs.complete_term(run_id, position, 0)
        terminal = runs.finish(run_id, status)
        response = client.get(f"/api/v1/search-batches/{batch_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "running"
        assert payload["current_item_position"] == 0
        assert payload["items"][0]["status"] == "running"
        assert payload["items"][0]["latest_attempt"]["run"]["status"] == status
        assert payload["items"][0]["latest_attempt"]["run"]["finished_at"] is not None
        assert payload["items"][0]["finished_at"] is None
        assert payload["items"][0]["completion_basis"] is None
        assert runs.get(run_id) == terminal
        assert worker.calls == worker.manual == []
        batches.finish_item(batch_id, 0, status)


@pytest.mark.parametrize("remaining_rows", [0, 1])
@pytest.mark.parametrize("action", ["skip", "cancel"])
def test_missing_child_snapshot_remains_readable_and_can_stop_without_search(
    tmp_path, remaining_rows, action
):
    database, batches, runs, batch_id, run_id = setup_batch(tmp_path)
    runs.finish(run_id, "structure_changed")
    batches.finish_item(batch_id, 0, "structure_changed")
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM search_run_terms WHERE run_id = ? AND position >= ?",
            (run_id, remaining_rows),
        )
    worker = RecoveryWorker()
    with TestClient(_app(database.path, worker)) as client:
        response = client.get(f"/api/v1/search-batches/{batch_id}")
        assert response.status_code == 200
        paused = response.json()
        item = paused["items"][0]
        assert item["recovery_available"] is False
        assert item["latest_attempt"]["run"]["term_count"] == remaining_rows
        assert paused["terms"] == ["词一", "词二"]
        history = client.get(f"/api/v1/search-batches/{batch_id}/items/0/attempts")
        assert history.status_code == 200
        assert history.json()["attempts"][0]["run"]["term_count"] == remaining_rows
        body = public_control(paused)
        unavailable = client.post(
            f"/api/v1/search-batches/{batch_id}/continue", json=body
        )
        assert unavailable.status_code == 409
        assert unavailable.json()["detail"]["code"] == (
            "search_batch_recovery_unavailable"
        )
        assert worker.calls == worker.manual == []
        stopped = client.post(
            f"/api/v1/search-batches/{batch_id}/{action}",
            json=body
            if action == "skip"
            else {"expected_revision": body["expected_revision"]},
        )
        assert stopped.status_code == 202
        assert stopped.json()["items"][0]["status"] == (
            "skipped" if action == "skip" else "cancelled"
        )
        assert worker.calls == []
        assert all(manual_action == "close" for _, manual_action in worker.manual)
    if remaining_rows == 0:
        with pytest.raises(SearchRunRepositoryUnavailableError):
            runs.get(run_id)


def test_cancel_fences_all_late_callbacks_and_preserves_proofs(tmp_path):
    _, batches, runs, batch_id, run_id = setup_batch(tmp_path)
    runs.set_progress(run_id, 0)
    runs.complete_term(run_id, 0, 0)
    before = batches.get(batch_id)
    batches.cancel_batch(batch_id, expected_revision=before.control_revision)
    for callback in (
        lambda: runs.set_progress(run_id, 1),
        lambda: runs.observe_item(run_id=run_id, term_position=0, item=_item("late")),
        lambda: runs.complete_term(run_id, 0, 0),
    ):
        with pytest.raises(SearchRunNotActiveError):
            callback()
    assert batches.get(batch_id).items[0].checkpoint.completed == 1


class RecoveryWorker:
    def __init__(self):
        self.calls = []
        self.manual = []

    async def search(self, *, terms, on_progress, on_term_completed, **kwargs):
        self.calls.append(tuple(terms))
        if len(self.calls) == 1:
            for position in range(2):
                await on_progress(position, len(terms))
                await on_term_completed(position, 0)
            await on_progress(2, len(terms))
            return SearchWorkerResult("structure_changed")
        for position in range(len(terms)):
            await on_progress(position, len(terms))
            await on_term_completed(position, 0)
        return SearchWorkerResult("completed_empty")

    async def manual_page(self, *, platform, action, **kwargs):
        self.manual.append((platform, action))
        return ManualPageWorkerResult(
            "opened_existing" if action == "show" else "closed"
        )

    async def discard_session(self):
        pass


def public_control(batch):
    item = batch["items"][batch["current_item_position"]]
    return dict(
        item_position=item["position"],
        expected_run_id=item["latest_attempt"]["run"]["id"]
        if item["latest_attempt"]
        else None,
        expected_revision=batch["control_revision"],
    )


def test_api_suffix_show_stale_controls_and_refresh_are_explicit(tmp_path):
    worker = RecoveryWorker()
    with TestClient(_app(tmp_path / "api.sqlite3", worker)) as client:
        created = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": 1, "platforms": ["wb"]},
        )
        assert created.status_code == 202
        identity = created.json()["id"]
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        body = public_control(paused)
        assert paused["items"][0]["completed_term_count"] == 2
        for _ in range(3):
            assert client.get(f"/api/v1/search-batches/{identity}").status_code == 200
        assert len(worker.calls) == 1
        assert (
            client.post(f"/api/v1/search-batches/{identity}/continue").status_code
            == 422
        )
        shown = client.post(f"/api/v1/search-batches/{identity}/manual-page", json=body)
        assert shown.json() == {"outcome": "opened_existing"}
        assert len(worker.calls) == 1
        assert (
            client.post(
                f"/api/v1/search-batches/{identity}/continue", json=body
            ).status_code
            == 202
        )
        complete = _wait_for_batch(client, identity, {"completed"})
        assert worker.calls[1] == tuple(paused["terms"][2:])
        assert complete["items"][0]["completed_term_count"] == 5
        assert complete["items"][0]["checkpoint_basis"] == "explicit"
        stale = client.post(f"/api/v1/search-batches/{identity}/skip", json=body)
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "search_batch_state_changed"


@pytest.mark.parametrize("failure", ["before_result_commit", "before_item_commit"])
def test_runner_fallback_settles_active_attempts_and_preserves_committed_success(
    tmp_path, monkeypatch, failure
):
    class EmptyWorker(RecoveryWorker):
        async def search(self, *, terms, on_progress, on_term_completed, **kwargs):
            self.calls.append(tuple(terms))
            for position in range(len(terms)):
                await on_progress(position, len(terms))
                await on_term_completed(position, 0)
            return SearchWorkerResult("completed_empty")

    original_run_finish = SearchRunRepository.finish
    original_item_finish = SearchBatchRepository.finish_item
    original_release_owner = SearchBatchService._release_owner
    released = threading.Event()
    interrupted = False
    committed_success = None

    def finish_run(repository, run_id, status):
        nonlocal interrupted, committed_success
        if failure == "before_result_commit" and not interrupted:
            interrupted = True
            raise SearchRunRepositoryUnavailableError
        result = original_run_finish(repository, run_id, status)
        if failure == "before_item_commit" and committed_success is None:
            committed_success = result
        return result

    def finish_item(repository, *args, **kwargs):
        nonlocal interrupted
        if failure == "before_item_commit" and not interrupted:
            interrupted = True
            raise SearchBatchRepositoryUnavailableError
        return original_item_finish(repository, *args, **kwargs)

    async def release_owner(service, owner):
        await original_release_owner(service, owner)
        released.set()

    monkeypatch.setattr(SearchRunRepository, "finish", finish_run)
    monkeypatch.setattr(SearchBatchRepository, "finish_item", finish_item)
    monkeypatch.setattr(SearchBatchService, "_release_owner", release_owner)
    worker = EmptyWorker()
    path = tmp_path / "fallback.sqlite3"
    with TestClient(_app(path, worker)) as client:
        identity = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": 1, "platforms": ["wb"]},
        ).json()["id"]
        failed = _wait_for_batch(client, identity, {"internal_error"})
        first = failed["items"][0]
        assert first["latest_attempt"]["run"]["status"] == (
            "internal_error" if failure == "before_result_commit" else "completed_empty"
        )
        assert first["status"] == (
            "failed" if failure == "before_result_commit" else "completed"
        )
        assert first["completion_basis"] == (
            None if failure == "before_result_commit" else "attempt_success"
        )
        assert len(worker.calls) == 1
        database = Database(path)
        with database.connect() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM search_runs "
                    "WHERE status IN ('queued','running')"
                ).fetchone()[0]
                == 0
            )
        if committed_success is not None:
            assert (
                SearchRunRepository(database).get(committed_success.id)
                == committed_success
            )
            assert first["finished_at"] == first["latest_attempt"]["run"]["finished_at"]
        assert released.wait(2)
        next_batch = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": 1, "platforms": ["wb"]},
        )
        assert next_batch.status_code == 202
        _wait_for_batch(client, next_batch.json()["id"], {"completed"})
        assert len(worker.calls) == 2


def test_restart_before_attempt_pauses_without_worker_calls(tmp_path):
    path = tmp_path / "restart.sqlite3"
    database = Database(path)
    database.initialize()
    repo = SearchBatchRepository(database)
    batch = repo.create_batch(
        monitoring_rule_id=1,
        rule_name="重启",
        terms=("词",),
        platforms=("wb",),
        max_results_per_term=10,
    )
    worker = RecoveryWorker()
    with TestClient(_app(path, worker)) as client:
        paused = client.get(f"/api/v1/search-batches/{batch.id}").json()
        assert paused["status"] == "paused_for_manual_action"
        assert paused["items"][0]["pause_reason"] == "process_interrupted"
        assert paused["items"][0]["latest_attempt"] is None
        assert worker.calls == worker.manual == []


def test_database_thread_is_drained_before_cancellation_returns():
    async def scenario():
        started, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def write():
            started.set()
            release.wait(timeout=2)
            finished.set()

        task = asyncio.create_task(database_call(write))
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    asyncio.run(scenario())


def _legacy_database(path):
    database = Database(path)
    with database.connect() as connection:
        for version in range(1, 10):
            getattr(migration_module, f"_migrate_to_version_{version}")(connection)
        connection.execute("""INSERT INTO search_batches
          (id, monitoring_rule_id, rule_name, max_results_per_term, status,
           current_item_position, created_at, started_at, finished_at)
          VALUES (1, 1, '历史规则', 10, 'completed_with_failures', NULL,
                  'created', 'started', 'finished')""")
        for position, term in enumerate(("词一", "词二", "词三")):
            connection.execute(
                "INSERT INTO search_batch_terms VALUES (1, ?, ?)", (position, term)
            )
        connection.execute("""INSERT INTO search_batch_items VALUES
          (1, 0, 'wb', 'failed', 'created', 'started', 'item-finished')""")
        connection.execute("""INSERT INTO search_runs
          (id, monitoring_rule_id, platform, rule_name, max_results_per_term, status,
           current_term_position, created_at, started_at, finished_at)
          VALUES (1, 1, 'wb', '历史规则', 10, 'structure_changed', 2,
                  'created', 'started', 'finished')""")
        connection.execute("""INSERT INTO search_run_terms
          SELECT 1, position, value FROM search_batch_terms WHERE batch_id = 1""")
        connection.execute(
            "INSERT INTO search_batch_attempts VALUES (1, 0, 1, 1, 'created')"
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 100 WHERE name = 'search_runs'"
        )
    return database


def test_migration_preserves_history_backfills_empty_terms_and_audits_old_recovery(
    tmp_path,
):
    database = _legacy_database(tmp_path / "legacy.sqlite3")
    with database.connect() as connection:
        before = [tuple(row) for row in connection.execute("SELECT * FROM search_runs")]
    database.initialize()
    database.initialize()
    repository = SearchBatchRepository(database)
    old = repository.get(1)
    assert old.items[0].checkpoint.completed == 2
    assert old.items[0].checkpoint.basis == "legacy_inferred"
    recovered = repository.recover_item(1, 0, expected_run_id=1, expected_revision=0)
    assert recovered.status == "paused_for_manual_action"
    assert recovered.items[0].latest_attempt.run.status == "structure_changed"
    with database.connect() as connection:
        after = [
            tuple(row)[: len(before[0])]
            for row in connection.execute("SELECT * FROM search_runs")
        ]
        assert before == after
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        proofs = connection.execute(
            "SELECT proof, result_count, completed_at FROM search_run_term_completions"
        ).fetchall()
        assert [tuple(row) for row in proofs] == [
            ("legacy_next_term_started", 0, None)
        ] * 2
        audit = connection.execute("SELECT * FROM search_batch_recoveries").fetchone()
        assert audit["previous_batch_finished_at"] == "finished"
        assert audit["previous_item_finished_at"] == "item-finished"
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM search_batch_recoveries")
    repository.continue_batch(1, **control(recovered))
    retry = repository.create_attempt(1, 0)
    assert retry.id == 101
    assert retry.execution_start_term_position == 2


def test_v10_migration_rollback_restores_all_prior_tables(tmp_path):
    database = _legacy_database(tmp_path / "rollback.sqlite3")

    class FailingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "PRAGMA user_version = 10":
                raise sqlite3.OperationalError("injected failure")
            return super().execute(sql, parameters)

    connection = sqlite3.connect(
        database.path, isolation_level=None, factory=FailingConnection
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with pytest.raises(sqlite3.OperationalError):
            _migrate_to_version_10(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute("SELECT COUNT(*) FROM search_batch_attempts").fetchone()[
                0
            ]
            == 1
        )
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name LIKE '%_v10' "
            "OR name = 'search_run_term_completions'"
        ).fetchall()
        assert "execution_start_term_position" not in {
            row["name"] for row in connection.execute("PRAGMA table_info(search_runs)")
        }
    finally:
        connection.close()


def test_cancel_during_manual_show_drains_before_releasing_owner(tmp_path):
    class HangingManual(RecoveryWorker):
        def __init__(self):
            super().__init__()
            self.started = threading.Event()
            self.cancelled = 0

        async def manual_page(self, *, platform, action, **kwargs):
            self.manual.append((platform, action))
            if action == "show":
                self.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await asyncio.sleep(0.01)
                    self.cancelled += 1
                    raise
            return ManualPageWorkerResult("closed")

    worker = HangingManual()
    with TestClient(_app(tmp_path / "show-cancel.sqlite3", worker)) as client:
        identity = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": 1, "platforms": ["wb"]},
        ).json()["id"]
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        body = public_control(paused)
        with ThreadPoolExecutor() as pool:
            showing = pool.submit(
                client.post, f"/api/v1/search-batches/{identity}/manual-page", json=body
            )
            assert worker.started.wait(2)
            cancelled = client.post(
                f"/api/v1/search-batches/{identity}/cancel",
                json={"expected_revision": body["expected_revision"]},
            )
            assert cancelled.status_code == 202
            assert showing.result(timeout=2).json() == {"outcome": "cancelled"}
        assert worker.cancelled == 1
        assert len(worker.calls) == 1
        assert worker.manual[-1] == ("wb", "close")
        assert (
            client.post(
                "/api/v1/search-batches",
                json={"monitoring_rule_id": 1, "platforms": ["wb"]},
            ).status_code
            == 202
        )


def test_restart_after_terminal_run_success_projects_success_without_search(tmp_path):
    _, batches, runs, batch_id, run_id = setup_batch(tmp_path, platforms=("wb",))
    for position in range(2):
        runs.set_progress(run_id, position)
        runs.complete_term(run_id, position, 0)
    done = runs.finish(run_id, "completed_empty")
    batches.reconcile_interrupted_items()
    after = batches.get(batch_id)
    assert after.items[0].status == "completed"
    assert after.items[0].finished_at == done.finished_at
    assert runs.get(run_id) == done
    assert after.status == "completed"


def test_two_continue_requests_create_at_most_one_retry(tmp_path):
    worker = RecoveryWorker()
    with TestClient(_app(tmp_path / "duplicate.sqlite3", worker)) as client:
        identity = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": 1, "platforms": ["wb"]},
        ).json()["id"]
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        body = public_control(paused)
        with ThreadPoolExecutor() as pool:
            requests = [
                pool.submit(
                    client.post,
                    f"/api/v1/search-batches/{identity}/continue",
                    json=body,
                )
                for _ in range(2)
            ]
            assert sorted(
                request.result(timeout=2).status_code for request in requests
            ) == [202, 409]
        completed = _wait_for_batch(client, identity, {"completed"})
        assert completed["items"][0]["attempt_count"] == 2
        assert len(worker.calls) == 2


@pytest.mark.parametrize("action", ["continue", "skip", "manual-page"])
def test_recovery_controls_strict_shapes_and_stale_identity(tmp_path, action):
    worker = RecoveryWorker()
    with TestClient(_app(tmp_path / "strict.sqlite3", worker)) as client:
        identity = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": 1, "platforms": ["wb"]},
        ).json()["id"]
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        body = public_control(paused)
        route = f"/api/v1/search-batches/{identity}/{action}"
        for invalid in (
            {},
            {**body, "expected_revision": True},
            {**body, "expected_run_id": "1"},
            {**body, "item_position": 5},
            {**body, "url": "https://unsafe.example"},
        ):
            response = client.post(route, json=invalid)
            assert response.status_code == 422
            assert response.json() == {
                "detail": {"code": "invalid_request", "message": "请求内容不正确。"}
            }
        stale = client.post(
            route, json={**body, "expected_run_id": body["expected_run_id"] + 1}
        )
        assert stale.status_code == 409
        assert stale.json() == {
            "detail": {
                "code": "search_batch_state_changed",
                "message": "采集任务状态已变化，请刷新后重试。",
            }
        }
        assert len(worker.calls) == 1 and not worker.manual


@pytest.mark.parametrize("status", ["completed", "cancelled", "internal_error"])
def test_historical_recovery_does_not_reopen_ineligible_batches(tmp_path, status):
    database = _legacy_database(tmp_path / "ineligible.sqlite3")
    database.initialize()
    with database.connect() as connection:
        connection.execute("UPDATE search_batches SET status = ?", (status,))
    from longtian_api.repositories.search_batches import (
        SearchBatchItemNotRecoverableError,
    )

    repo = SearchBatchRepository(database)
    with pytest.raises(SearchBatchItemNotRecoverableError):
        repo.recover_item(1, 0, expected_run_id=1, expected_revision=0)
    assert repo.get(1).status == status
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM search_batch_recoveries"
            ).fetchone()[0]
            == 0
        )


def test_legacy_corrupt_started_position_does_not_abort_migration_or_invent_proof(
    tmp_path,
):
    database = _legacy_database(tmp_path / "corrupt.sqlite3")
    with database.connect() as connection:
        connection.execute("UPDATE search_runs SET current_term_position = 1.5")
    database.initialize()
    repo = SearchBatchRepository(database)
    recovered = repo.recover_item(1, 0, expected_run_id=1, expected_revision=0)
    assert not recovered.items[0].checkpoint.available
    with pytest.raises(SearchBatchRecoveryUnavailableError):
        repo.continue_batch(1, **control(recovered))
    assert repo.skip_item(1, **control(recovered)).items[0].status == "skipped"
