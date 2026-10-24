import errno
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from leo_kiosk.domain.errors import StorageError
from leo_kiosk.storage import database, migrations
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.migrations import Migration

BASE = Migration(1, ("CREATE TABLE items (name TEXT)", "INSERT INTO items VALUES ('kept')"))
UPGRADE = Migration(2, ("ALTER TABLE items ADD COLUMN rating INTEGER",))


@pytest.fixture
def existing(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    open_database(path, (BASE,)).close()
    return path


def assert_original(path):
    with closing(open_database(path, (BASE,))) as connection:
        assert connection.execute("SELECT name FROM items").fetchone()[0] == "kept"
        assert connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 1
        assert not connection.in_transaction


def test_corruption_is_reported_without_resetting_the_file(tmp_path):
    path = tmp_path / "broken.sqlite3"
    original = b"not a SQLite database\x00"
    path.write_bytes(original)
    with pytest.raises(StorageError, match="not reset"):
        open_database(path)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "failure", [PermissionError(errno.EACCES, "read-only"), OSError(errno.ENOSPC, "disk full")]
)
def test_file_open_failures_preserve_existing_data(existing, monkeypatch, failure):
    def fail_open(*args, **kwargs):
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(database.os, "open", fail_open)
        with pytest.raises(StorageError) as error:
            open_database(existing, (BASE, UPGRADE))
        assert error.value.__cause__ is failure
    assert_original(existing)


def test_read_only_writes_are_typed_and_do_not_change_data(existing):
    with closing(open_database(existing, (BASE,))) as connection:
        connection.execute("PRAGMA query_only = ON")
        with pytest.raises(StorageError):
            with transaction(connection):
                connection.execute("DELETE FROM items")
        assert not connection.in_transaction
    assert_original(existing)


def test_real_sqlite_full_error_rolls_back_without_filling_the_host_disk(existing):
    with closing(open_database(existing, (BASE,))) as connection:
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        connection.execute(f"PRAGMA max_page_count = {pages}")
        with pytest.raises(StorageError) as error:
            with transaction(connection):
                connection.execute("INSERT INTO items VALUES (zeroblob(?))", (page_size * 10,))
        assert error.value.__cause__.sqlite_errorcode == sqlite3.SQLITE_FULL
        assert not connection.in_transaction
    assert_original(existing)


def test_locked_writer_respects_bounded_busy_timeout(existing):
    with closing(open_database(existing, (BASE,), busy_timeout_ms=20)) as owner:
        with closing(open_database(existing, (BASE,), busy_timeout_ms=20)) as contender:
            with transaction(owner):
                started = time.monotonic()
                with pytest.raises(StorageError) as error:
                    with transaction(contender):
                        pytest.fail("contending writer cannot enter")
                assert error.value.__cause__.sqlite_errorcode == sqlite3.SQLITE_BUSY
                assert time.monotonic() - started < 2
    assert_original(existing)


def test_failed_upgrade_rolls_back_every_pending_version_and_keeps_backup(existing):
    second = Migration(2, ("CREATE TABLE extra (id)", "UPDATE items SET name = 'changed'"))
    broken = Migration(3, ("INSERT INTO missing_table VALUES (1)",))
    with pytest.raises(StorageError):
        open_database(existing, (BASE, second, broken))
    assert_original(existing)
    with closing(sqlite3.connect(existing)) as connection:
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'extra'"
        ).fetchall()
    backups = list(existing.parent.glob("*.before-v3.*.bak"))
    assert len(backups) == 1
    assert_original(backups[0])


@pytest.mark.parametrize(
    "statement",
    [
        "COMMIT",
        "END",
        "ROLLBACK",
        "SAVEPOINT unsafe",
        "PRAGMA user_version = 999",
        "SELECT 1; COMMIT",
        "ATTACH DATABASE ':memory:' AS unsafe",
        "VACUUM",
    ],
)
def test_migration_cannot_escape_its_transaction(existing, statement):
    unsafe = Migration(2, ("CREATE TABLE extra (id)", statement))
    with pytest.raises(StorageError):
        open_database(existing, (BASE, unsafe))
    assert_original(existing)
    with closing(sqlite3.connect(existing)) as connection:
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'extra'"
        ).fetchall()


@pytest.mark.parametrize("mode", ["newer", "edited", "gap"])
def test_incompatible_history_fails_closed_without_backup(existing, mode):
    supplied = ()
    if mode == "edited":
        supplied = (Migration(1, ("CREATE TABLE other (id)",)),)
    elif mode == "gap":
        with closing(sqlite3.connect(existing)) as connection:
            connection.execute("UPDATE schema_migrations SET version = 2")
            connection.commit()
        supplied = (BASE, UPGRADE)
    with pytest.raises(StorageError, match="history is incompatible"):
        open_database(existing, supplied)
    with closing(sqlite3.connect(existing)) as connection:
        assert connection.execute("SELECT name FROM items").fetchone()[0] == "kept"
    assert not list(existing.parent.glob("*.bak"))


def test_unknown_nonempty_database_is_not_adopted_or_replaced(tmp_path):
    path = tmp_path / "unrelated.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE unrelated (value)")
        connection.execute("INSERT INTO unrelated VALUES ('preserve')")
        connection.commit()
    with pytest.raises(StorageError, match="Unrecognized"):
        open_database(path, (BASE,))
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchone()[0] == "preserve"


def test_unwritable_backup_location_prevents_upgrade(existing, monkeypatch):
    def fail_backup_file(*args, **kwargs):
        raise PermissionError("no backup storage")

    with monkeypatch.context() as patch:
        patch.setattr(migrations.tempfile, "mkstemp", fail_backup_file)
        with pytest.raises(StorageError):
            open_database(existing, (BASE, UPGRADE))
    assert_original(existing)


@pytest.mark.parametrize("failure", ["interrupted", "timeout"])
def test_partial_backup_is_removed_and_not_advertised_as_valid(
    existing,
    monkeypatch,
    fake_clock,
    failure,
):
    real_connect = sqlite3.connect

    class BrokenBackup(sqlite3.Connection):
        def backup(self, target, **kwargs):
            target.execute("CREATE TABLE incomplete_copy (id)")
            if failure == "timeout":
                fake_clock.advance(10)
                kwargs["progress"](sqlite3.SQLITE_BUSY, 1, 1)
            raise OSError("simulated interrupted backup")

    def connect(*args, **kwargs):
        return real_connect(*args, **kwargs, factory=BrokenBackup)

    with monkeypatch.context() as patch:
        patch.setattr(database.sqlite3, "connect", connect)
        patch.setattr(migrations.time, "monotonic", fake_clock)
        with pytest.raises(StorageError):
            open_database(existing, (BASE, UPGRADE))
    assert not list(existing.parent.glob("*.partial"))
    assert not list(existing.parent.glob("*.bak"))
    assert_original(existing)


def test_fresh_failed_upgrade_does_not_record_partial_history(tmp_path):
    path = tmp_path / "fresh.sqlite3"
    broken = Migration(1, ("CREATE TABLE partial (id)", "INSERT INTO missing VALUES (1)"))
    with pytest.raises(StorageError):
        open_database(path, (broken,))
    with closing(sqlite3.connect(path)) as connection:
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    open_database(path, (BASE,)).close()
    assert_original(path)


def test_connection_cannot_be_used_on_another_thread(existing):
    with closing(open_database(existing, (BASE,))) as connection:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(connection.execute, "SELECT 1")
            with pytest.raises(sqlite3.ProgrammingError, match="same thread"):
                future.result()


def test_symlink_database_cannot_redirect_writes(existing):
    link = existing.with_name("symlink.sqlite3")
    link.symlink_to(existing)
    with pytest.raises(StorageError):
        open_database(link, (BASE, UPGRADE))
    assert_original(existing)
