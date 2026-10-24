import shutil
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timedelta

import pytest

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.storage.database import open_database
from leo_kiosk.storage.migrations import Migration

FIRST = Migration(1, ("CREATE TABLE games (name TEXT)", "INSERT INTO games VALUES ('kept')"))
SECOND = Migration(2, ("ALTER TABLE games ADD COLUMN rating INTEGER",))


def test_fresh_migration_is_idempotent_and_keeps_checked_utc_history(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    for _ in range(2):
        with closing(open_database(path, (FIRST,))) as connection:
            assert connection.execute("SELECT name FROM games").fetchone()[0] == "kept"
            row = connection.execute("SELECT * FROM schema_migrations").fetchone()
            assert row["version"] == 1 and row["checksum"] == FIRST.checksum
            assert datetime.fromisoformat(row["applied_at"]).utcoffset() == timedelta(0)
    assert not list(tmp_path.glob("*.bak"))


def test_upgrade_backup_contains_preupgrade_committed_wal_data(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    with closing(open_database(path, (FIRST,))) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("INSERT INTO games VALUES (?)", ("latest WAL write",))
        # Prove the committed row is not in the main file before testing backup.
        main_only = tmp_path / "main-file-only.sqlite3"
        shutil.copyfile(path, main_only)
        with closing(sqlite3.connect(main_only)) as incomplete:
            assert incomplete.execute("SELECT count(*) FROM games").fetchone()[0] == 1
        # Keep source open: copying the main file would miss committed WAL pages.
        with closing(open_database(path, (FIRST, SECOND))) as upgraded:
            assert upgraded.execute("SELECT count(*) FROM games").fetchone()[0] == 2
    backups = list(tmp_path.glob("*.before-v2.*.bak"))
    assert len(backups) == 1
    backup = backups[0]
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    with closing(sqlite3.connect(backup)) as snapshot:
        assert snapshot.execute("SELECT count(*) FROM games").fetchone()[0] == 2
        assert snapshot.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 1
        assert [row[1] for row in snapshot.execute("PRAGMA table_info(games)")] == ["name"]
    assert not list(tmp_path.glob("*.partial"))


def test_initialized_version_zero_also_gets_an_upgrade_backup(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    open_database(path).close()
    open_database(path, (FIRST,)).close()
    assert len(list(tmp_path.glob("*.before-v1.*.bak"))) == 1


@pytest.mark.parametrize("versions", [(2,), (1, 1), (1, 3), (2, 1)])
def test_invalid_order_is_rejected_before_file_creation(tmp_path, versions):
    path = tmp_path / "invalid.sqlite3"
    with pytest.raises(ValidationError):
        open_database(path, tuple(Migration(v, ("CREATE TABLE x (id)",)) for v in versions))
    assert not path.exists()


@pytest.mark.parametrize(
    ("version", "statements"),
    [
        (True, ("SELECT 1",)),
        (0, ("SELECT 1",)),
        (1, []),
        (1, ()),
        (1, ("",)),
        (1, (None,)),
    ],
)
def test_migrations_require_positive_versions_and_immutable_nonempty_batches(version, statements):
    with pytest.raises(ValidationError):
        Migration(version, statements)
