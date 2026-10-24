import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path

import pytest

from leo_kiosk.domain.errors import StorageError, ValidationError
from leo_kiosk.storage.database import default_database_path, open_database, transaction


def test_private_default_path_and_connection_settings(private_data_dir):
    with closing(open_database()) as connection:
        path = default_database_path()
        assert path == private_data_dir / "leo-kiosk" / "catalog.sqlite3"
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert connection.row_factory is sqlite3.Row
        for pragma, expected in [
            ("foreign_keys", 1),
            ("journal_mode", "wal"),
            ("busy_timeout", 3000),
            ("synchronous", 2),
        ]:
            assert connection.execute(f"PRAGMA {pragma}").fetchone()[0] == expected
        assert not connection.in_transaction


@pytest.mark.parametrize("value", [None, "", "relative/data"])
def test_xdg_unset_or_relative_uses_home(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("XDG_DATA_HOME")
    else:
        monkeypatch.setenv("XDG_DATA_HOME", value)
    assert (
        default_database_path()
        == Path(os.environ["HOME"]) / ".local/share/leo-kiosk/catalog.sqlite3"
    )


def test_explicit_path_does_not_change_parent_permissions(tmp_path):
    parent = tmp_path / "caller-owned"
    parent.mkdir(mode=0o755)
    with closing(open_database(parent / "custom?#.sqlite3")) as connection:
        assert connection.execute("PRAGMA database_list").fetchone()[2].endswith("custom?#.sqlite3")
    assert stat.S_IMODE(parent.stat().st_mode) == 0o755


def test_transactions_commit_rollback_and_preserve_domain_errors():
    with closing(open_database()) as connection:
        connection.execute("CREATE TABLE items (name TEXT UNIQUE)")
        with transaction(connection):
            connection.execute("INSERT INTO items VALUES (?)", ("first",))
        with pytest.raises(ValidationError):
            with transaction(connection):
                connection.execute("INSERT INTO items VALUES (?)", ("rollback",))
                raise ValidationError("invalid draft")
        with pytest.raises(StorageError, match="transaction failed"):
            with transaction(connection):
                connection.execute("INSERT INTO items VALUES (?)", ("first",))
        assert [r[0] for r in connection.execute("SELECT name FROM items")] == ["first"]
        assert not connection.in_transaction


def test_nested_transaction_cannot_rollback_its_caller():
    with closing(open_database()) as connection:
        with transaction(connection):
            with pytest.raises(StorageError, match="Nested"):
                with transaction(connection):
                    pytest.fail("nested transaction must not start")
            assert connection.in_transaction


@pytest.mark.parametrize("timeout", [0, -1, 60_001, True, 2.5])
def test_invalid_timeout_does_not_create_a_database(tmp_path, timeout):
    path = tmp_path / "invalid.sqlite3"
    with pytest.raises(ValidationError):
        open_database(path, busy_timeout_ms=timeout)
    assert not path.exists()
