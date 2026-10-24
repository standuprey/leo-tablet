"""Checked migration batches and SQLite snapshot backups, never executescript."""

import hashlib
import os
import sqlite3
import tempfile
import time
from collections.abc import Sequence
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from leo_kiosk.domain.errors import StorageError, ValidationError

from .database import transaction


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version < 1:
            raise ValidationError("Migration versions must be positive integers")
        if (
            not isinstance(self.statements, tuple)
            or not self.statements
            or not all(isinstance(s, str) and s.strip() for s in self.statements)
        ):
            raise ValidationError("Migrations require an immutable batch of SQL statements")

    @property
    def checksum(self) -> str:
        return hashlib.sha256("\0".join(self.statements).encode()).hexdigest()


def validate_migrations(migrations: Sequence[Migration]) -> tuple[Migration, ...]:
    ordered = tuple(migrations)
    if any(not isinstance(m, Migration) or m.version != i for i, m in enumerate(ordered, 1)):
        raise ValidationError("Supply all migrations consecutively from version 1, in order")
    return ordered


def _backup(connection: sqlite3.Connection, path: Path, version: int, timeout_ms: int) -> Path:
    fd, name = tempfile.mkstemp(
        prefix=f"{path.name}.before-v{version}.", suffix=".partial", dir=path.parent
    )
    os.close(fd)
    partial = Path(name)
    deadline = time.monotonic() + timeout_ms / 1000

    def progress(status: int, remaining: int, total: int) -> None:
        if status != sqlite3.SQLITE_DONE and time.monotonic() >= deadline:
            raise StorageError("Database backup timed out; upgrade was not started")

    try:
        with closing(sqlite3.connect(partial, timeout=timeout_ms / 1000)) as destination:
            connection.backup(destination, pages=256, progress=progress, sleep=0.01)
        with partial.open("rb") as stream:
            os.fsync(stream.fileno())
        completed = partial.with_suffix(".bak")
        partial.rename(completed)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)  # Persist the backup name before schema changes begin.
        finally:
            os.close(directory_fd)
        return completed
    except BaseException:
        with suppress(OSError):
            partial.unlink(missing_ok=True)
        raise


def _authorize_migration(
    action: int, arg1: str | None, arg2: str | None, database: str | None, source: str | None
) -> int:
    forbidden = (
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_PRAGMA,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
    )
    return sqlite3.SQLITE_DENY if action in forbidden else sqlite3.SQLITE_OK


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Sequence[Migration],
    path: Path,
    timeout_ms: int,
) -> None:
    ordered = validate_migrations(migrations)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT GLOB 'sqlite_*'"
        )
    }
    initialized = "schema_migrations" in tables
    if tables and not initialized:
        raise StorageError("Unrecognized database schema; existing data was not reset")
    history = (
        [
            tuple(row)
            for row in connection.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version"
            )
        ]
        if initialized
        else []
    )
    expected = [(m.version, m.checksum) for m in ordered]
    if len(history) > len(expected) or history != expected[: len(history)]:
        raise StorageError("Database schema is newer or migration history is incompatible")
    pending = ordered[len(history) :]
    if initialized and not pending:
        return
    if initialized:
        _backup(connection, path, ordered[-1].version, timeout_ms)
    with transaction(connection):
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY CHECK (version > 0), "
            "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        connection.set_authorizer(_authorize_migration)
        try:
            for migration in pending:
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version, checksum, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.checksum, datetime.now(UTC).isoformat()),
                )
        finally:
            connection.set_authorizer(None)
