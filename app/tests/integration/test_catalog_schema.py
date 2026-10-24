import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from leo_kiosk.domain.catalog import stable_game_id
from leo_kiosk.storage.database import open_database
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def catalog_db(tmp_path):
    with closing(open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)) as connection:
        connection.execute(
            "INSERT INTO providers VALUES (?, ?, ?)", ("pbs", "PBS Kids", "https://pbskids.org")
        )
        yield connection


def insert_game(connection, **overrides):
    fields = dict(
        id=str(stable_game_id("pbs", "https://pbskids.org/game?id=1#level")),
        provider_id="pbs",
        canonical_source_url="https://pbskids.org/game?id=1#level",
        source_name="Game",
        media_type=2,
    )
    fields.update(overrides)
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    connection.execute(
        f"INSERT INTO games ({columns}) VALUES ({placeholders})", tuple(fields.values())
    )


def test_schema_is_repeatable_and_initializes_catalog_tables(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    for _ in range(2):
        with closing(open_database(path, MIGRATIONS)) as connection:
            # The registry now includes version 2 (home/history tables).
            tables = {
                r[0]
                for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            assert {
                "schema_migrations",
                "providers",
                "games",
                "catalog_imports",
                "home_slots",
                "launch_sessions",
                "review_events",
            } <= tables
            assert (
                connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 3
            )
    assert not list(tmp_path.glob("*.bak"))


def test_catalog_schema_upgrades_initialized_infrastructure_with_a_backup(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    open_database(path).close()
    with closing(open_database(path, MIGRATIONS)) as connection:
        assert connection.execute("SELECT count(*) FROM games").fetchone()[0] == 0
    assert list(tmp_path.glob("*.before-*.bak"))


@pytest.mark.parametrize("rating", [None, 0, 100])
def test_review_defaults_and_rating_boundaries(catalog_db, rating):
    insert_game(catalog_db, rating=rating)
    row = catalog_db.execute("SELECT * FROM games").fetchone()
    assert row["rating"] == rating
    assert row["revision"] == 0 and row["parent_name"] is None
    assert row["tested_at"] is None and row["reviewed_at"] is None and row["deleted_at"] is None
    assert row["width"] is None and row["height"] is None and row["orientation"] == "unknown"
    assert "selected" not in row.keys()


@pytest.mark.parametrize(
    "fields",
    [
        dict(rating=-1),
        dict(rating=101),
        dict(rating=50.5),
        dict(revision=-1),
        dict(revision=0.5),
        dict(media_type=3),
        dict(media_type=1.5),
        dict(parent_name=""),
        dict(parent_name="x" * 81),
        dict(width=800),
        dict(width=0, height=0, dimension_evidence="design"),
        dict(width=800, height=600),
        dict(width=800, height=600.5, dimension_evidence="design"),
        dict(dimension_evidence="popup"),
        dict(orientation="diagonal"),
        dict(id="not-a-uuid"),
        dict(source_name=""),
        dict(provider_id="missing"),
        dict(launch_url="file:///tmp/game"),
        dict(source_metadata_json="[]"),
        dict(source_metadata_json="not json"),
    ],
)
def test_game_constraints_reject_invalid_raw_writes(catalog_db, fields):
    with pytest.raises(sqlite3.IntegrityError):
        insert_game(catalog_db, **fields)
    assert catalog_db.execute("SELECT count(*) FROM games").fetchone()[0] == 0


def test_unique_source_identity_and_restricted_provider_delete(catalog_db):
    insert_game(catalog_db)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert_game(catalog_db, id=str(uuid4()))
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        catalog_db.execute("DELETE FROM providers WHERE id = ?", ("pbs",))
    assert catalog_db.execute("SELECT count(*) FROM games").fetchone()[0] == 1


@pytest.mark.parametrize("evidence", ["design", "iframe", "popup", "inferred"])
def test_source_dimensions_keep_their_evidence_category(catalog_db, evidence):
    insert_game(catalog_db, width=800, height=600, dimension_evidence=evidence)
    assert catalog_db.execute("SELECT dimension_evidence FROM games").fetchone()[0] == evidence


@pytest.mark.parametrize(
    ("checksum", "report"), [("bad", "{}"), ("a" * 64, "[]"), ("a" * 64, "broken")]
)
def test_import_history_constraints(catalog_db, checksum, report):
    with pytest.raises(sqlite3.IntegrityError):
        catalog_db.execute(
            "INSERT INTO catalog_imports VALUES (?, ?, ?, ?)",
            (str(uuid4()), checksum, "2026-01-01T00:00:00+00:00", report),
        )
