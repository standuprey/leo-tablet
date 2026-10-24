"""Private SQLite startup and explicit, thread-confined transaction ownership."""

import os
import sqlite3
import stat
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from leo_kiosk.domain.errors import StorageError, ValidationError

if TYPE_CHECKING:
    from .migrations import Migration


DEFAULT_BUSY_TIMEOUT_MS = 3_000


def default_database_path() -> Path:
    configured = os.environ.get("XDG_DATA_HOME", "")
    base = Path(configured)
    if not configured or not base.is_absolute():
        base = Path.home() / ".local" / "share"
    return base / "leo-kiosk" / "catalog.sqlite3"


def _prepare_path(path: Path | None) -> Path:
    target = default_database_path() if path is None else Path(path).absolute()
    if path is None and target.parent.is_symlink():
        raise StorageError("The application data directory cannot be a symlink")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path is None:
        target.parent.chmod(0o700)
    # Explicit override directories belong to the caller; never chmod shared parents.
    fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise StorageError("The database must be a regular private file")
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    return target


def open_database(
    path: Path | None = None,
    migrations: Sequence["Migration"] = (),
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Open/migrate on the owning thread; caller must close the returned connection.

    Upgrades require the previous kiosk process to be stopped. Explicit path
    overrides must use caller-controlled directories. No work happens on import.
    """
    from .migrations import apply_migrations, validate_migrations

    if type(busy_timeout_ms) is not int or not 1 <= busy_timeout_ms <= 60_000:
        raise ValidationError("SQLite busy timeout must be an integer from 1 to 60000 ms")
    ordered = validate_migrations(migrations)
    connection: sqlite3.Connection | None = None
    try:
        target = _prepare_path(path)
        connection = sqlite3.connect(
            target.as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            timeout=busy_timeout_ms / 1000,
            check_same_thread=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StorageError("Database integrity check failed; existing data was not reset")
        if connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
            raise StorageError("SQLite WAL mode is unavailable")
        connection.execute("PRAGMA synchronous = FULL")
        apply_migrations(connection, ordered, target, busy_timeout_ms)
        return connection
    except (OSError, sqlite3.Error) as exc:
        if connection is not None:
            connection.close()
        raise StorageError("Cannot initialize database; existing data was not reset") from exc
    except BaseException:
        if connection is not None:
            connection.close()
        raise


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Own one transaction, retaining caller/domain errors and rejecting nesting."""
    if connection.in_transaction:
        raise StorageError("Nested transactions are not supported; use the caller's scope")
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException as exc:
        try:
            if connection.in_transaction:
                connection.rollback()
        except sqlite3.Error as rollback_error:
            raise StorageError(
                "Database rollback failed; retain the unsaved draft"
            ) from rollback_error
        if isinstance(exc, sqlite3.Error):
            raise StorageError("Database transaction failed; no success was recorded") from exc
        raise
