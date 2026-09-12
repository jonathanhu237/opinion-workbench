"""Preflighted, collision-safe movement of explicitly listed SQLite backups."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupMove:
    """One database file (or SQLite sidecar) moved to the recovery area."""

    source: Path
    destination: Path


def move_backup_inventory(
    root: Path,
    relative_paths: Sequence[str],
    trash_root: Path,
    *,
    protected_paths: Sequence[Path] = (),
) -> tuple[BackupMove, ...]:
    """Move an explicit backup inventory without flattening destination names.

    Every source and destination is preflighted before the first move. Relative
    paths are retained below ``trash_root`` so same-named files from different
    directories cannot overwrite one another. Existing ``-wal`` and ``-shm``
    sidecars move with their database. The caller can pass protected files or
    directories such as the live database and managed browser profile.
    """

    root = root.resolve()
    trash_root = trash_root.resolve()
    protected = tuple(path.resolve() for path in protected_paths)
    inventory: list[tuple[Path, Path]] = []
    seen_sources: set[Path] = set()
    seen_destinations: set[Path] = set()

    for raw_path in relative_paths:
        relative = Path(raw_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.suffix != ".sqlite3"
        ):
            raise ValueError(f"Invalid backup inventory path: {raw_path!r}")
        source = (root / relative).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        if source in seen_sources:
            raise ValueError(f"Duplicate backup inventory path: {raw_path!r}")
        if source == trash_root or trash_root in source.parents:
            raise ValueError("Backup inventory may not include the Trash area")
        if any(source == path or path in source.parents for path in protected):
            raise ValueError(f"Protected path appears in backup inventory: {source}")
        seen_sources.add(source)

        for candidate in (
            source,
            Path(f"{source}-wal"),
            Path(f"{source}-shm"),
        ):
            if not candidate.exists():
                continue
            if not candidate.is_file():
                raise ValueError(f"Backup sidecar is not a regular file: {candidate}")
            destination = trash_root / relative.parent / candidate.name
            if destination in seen_destinations or destination.exists():
                raise FileExistsError(destination)
            seen_destinations.add(destination)
            inventory.append((candidate, destination))

    moves: list[BackupMove] = []
    for source, destination in inventory:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moves.append(BackupMove(source=source, destination=destination))
    return tuple(moves)
