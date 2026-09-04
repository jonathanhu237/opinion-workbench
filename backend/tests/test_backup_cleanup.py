"""Filesystem-only validation for explicit backup cleanup inventories."""

from pathlib import Path

import pytest

from longtian_api.backup_cleanup import move_backup_inventory


def test_backup_inventory_preserves_paths_moves_sidecars_and_protects_runtime(
    tmp_path: Path,
) -> None:
    listed = [
        tmp_path / "runtime" / "a" / "before.sqlite3",
        tmp_path / "runtime" / "b" / "before.sqlite3",
    ]
    for source in listed:
        source.parent.mkdir(parents=True)
        source.write_text(source.parent.name)
    Path(f"{listed[0]}-wal").write_text("wal")
    unlisted = tmp_path / "runtime" / "keep.sqlite3"
    unlisted.write_text("keep")
    runtime_database = tmp_path / "runtime" / "longtian.sqlite3"
    runtime_database.write_text("live")
    browser_profile = tmp_path / "runtime" / "browser" / "managed-chrome"
    browser_profile.mkdir(parents=True)
    (browser_profile / "Cookies").write_text("session")
    trash = tmp_path / "trash"

    moves = move_backup_inventory(
        tmp_path,
        ["runtime/a/before.sqlite3", "runtime/b/before.sqlite3"],
        trash,
        protected_paths=(runtime_database, browser_profile),
    )

    assert {move.source for move in moves} == {
        listed[0],
        listed[1],
        Path(f"{listed[0]}-wal"),
    }
    assert not listed[0].exists() and not listed[1].exists()
    assert (trash / "runtime" / "a" / "before.sqlite3").read_text() == "a"
    assert (trash / "runtime" / "b" / "before.sqlite3").read_text() == "b"
    assert (trash / "runtime" / "a" / "before.sqlite3-wal").read_text() == "wal"
    assert unlisted.read_text() == "keep"
    assert runtime_database.read_text() == "live"
    assert (browser_profile / "Cookies").read_text() == "session"


def test_backup_inventory_preflights_protected_and_existing_destinations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "runtime" / "before.sqlite3"
    source.parent.mkdir(parents=True)
    source.write_text("backup")
    protected = tmp_path / "runtime" / "protected.sqlite3"
    protected.write_text("live")

    with pytest.raises(ValueError, match="Protected path"):
        move_backup_inventory(
            tmp_path,
            ["runtime/protected.sqlite3"],
            tmp_path / "trash",
            protected_paths=(protected,),
        )
    assert protected.read_text() == "live"

    destination = tmp_path / "trash" / "runtime" / "before.sqlite3"
    destination.parent.mkdir(parents=True)
    destination.write_text("existing")
    with pytest.raises(FileExistsError):
        move_backup_inventory(tmp_path, ["runtime/before.sqlite3"], tmp_path / "trash")
    assert source.read_text() == "backup"
