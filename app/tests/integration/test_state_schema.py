import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from leo_kiosk.domain.catalog import CatalogItem, MediaType
from leo_kiosk.domain.catalog_metadata import Provider
from leo_kiosk.domain.errors import StorageError
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def db(tmp_path):
    with closing(open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)) as connection:
        with transaction(connection):
            CatalogMetadataRepository(connection).upsert_provider(
                Provider("pbs", "PBS", "https://pbskids.org")
            )
            catalog = CatalogRepository(connection)
            for suffix in ("a", "b", "c"):
                item = CatalogItem(
                    "pbs",
                    f"https://pbskids.org/game?level={suffix}",
                    f"Game {suffix}",
                    MediaType.GAME,
                )
                catalog.insert_record(
                    __import__(
                        "leo_kiosk.domain.catalog_records", fromlist=["StoredGame"]
                    ).StoredGame(item)
                )
        yield connection


def slot_fields(game_id=None, position=1, legacy=None):
    fields = dict(
        position=position,
        game_id=game_id,
        legacy_tile_id=legacy,
        legacy_tile_json='{"id":"read"}' if legacy else None,
    )
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    return f"INSERT INTO home_slots ({columns}) VALUES ({placeholders})", tuple(fields.values())


def test_positions_and_exclusive_occupancy(db):
    games = [r[0] for r in db.execute("SELECT id FROM games ORDER BY id")]
    with transaction(db):
        db.execute(*slot_fields(games[0], position=1))
        db.execute(*slot_fields(position=5, legacy="read"))
    assert [r[0] for r in db.execute("SELECT position FROM home_slots ORDER BY position")] == [1, 5]
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        db.execute(*slot_fields(games[1], position=1))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(*slot_fields(games[1], position=2, legacy="draw"))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.execute(*slot_fields(position=10, legacy="draw"))
    assert not db.in_transaction


def test_slot_rows_and_game_identity_are_protected_from_deletion(db):
    game = db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
    with transaction(db):
        db.execute(*slot_fields(game))
    with pytest.raises(StorageError):
        with transaction(db):
            db.execute("DELETE FROM games WHERE id = ?", (game,))
    assert db.execute("SELECT count(*) FROM games").fetchone()[0] == 3


def test_seeded_slot_rows_cannot_be_deleted(db):
    game = db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
    with transaction(db):
        db.execute(*slot_fields(game))
    with pytest.raises(StorageError):
        with transaction(db):
            db.execute("DELETE FROM home_slots WHERE position = 1")
    assert db.execute("SELECT count(*) FROM home_slots").fetchone()[0] == 1


def test_launch_sessions_require_matching_role_context(db):
    games = [r[0] for r in db.execute("SELECT id FROM games ORDER BY id")]
    game, other = games[0], games[2]
    with transaction(db):
        db.execute(*slot_fields(game))
        db.execute(*slot_fields(position=2, legacy="read"))
    valid = [
        # An outcome exists only on a finished session; recovery may add it later.
        (
            str(uuid4()),
            game,
            1,
            "child_game",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T01:00:00+00:00",
            "exited",
            None,
        ),
        (str(uuid4()), None, 2, "child_legacy", None, None, None, None),
        (
            str(uuid4()),
            other,
            None,
            "review_trial",
            "2026-01-02T00:00:00+00:00",
            "2026-01-02T01:00:00+00:00",
            "return_gesture",
            None,
        ),
    ]
    with transaction(db):
        db.executemany("INSERT INTO launch_sessions VALUES (?,?,?,?,?,?,?,?)", valid)
    invalid = [
        (str(uuid4()), None, 1, "child_game", None, None, None, None),
        (str(uuid4()), game, None, "child_game", None, None, None, None),
        (str(uuid4()), game, None, "child_legacy", None, None, None, None),
        (str(uuid4()), None, None, "review_trial", None, None, None, None),
        (str(uuid4()), game, 1, "review_trial", None, None, None, None),
        (str(uuid4()), None, 1, "child_game", None, None, "timed_out", None),
        (
            str(uuid4()),
            None,
            2,
            "child_legacy",
            "2026-01-01T00:00:00+00:00",
            None,
            "timed_out",
            None,
        ),
        (str(uuid4()), None, 2, "child_legacy", None, None, "exited", None),
        # A finished session may defer its outcome (crash marking), but a set
        # outcome always requires ended_at.
        (
            str(uuid4()),
            None,
            2,
            "child_legacy",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T02:00:00+00:00",
            None,
            None,
        ),
    ]
    for row in invalid:
        with pytest.raises(StorageError):
            with transaction(db):
                db.execute("INSERT INTO launch_sessions VALUES (?,?,?,?,?,?,?,?)", row)
    # A running legacy session with a started_at and no outcome is valid: it is
    # exactly what recovery marks ABANDONED on the next startup. The running
    # session and the unfinished legacy row above both end with NULL ended_at.
    running = (str(uuid4()), None, 2, "child_legacy", "2026-01-01T00:00:00+00:00", None, None, None)
    with transaction(db):
        db.execute("INSERT INTO launch_sessions VALUES (?,?,?,?,?,?,?,?)", running)
    assert (
        db.execute("SELECT count(*) FROM launch_sessions WHERE ended_at IS NULL").fetchone()[0] == 2
    )


def test_ended_sessions_must_have_started_at(db):
    with pytest.raises(StorageError):
        with transaction(db):
            db.execute(
                "INSERT INTO launch_sessions VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid4()), None, 1, "child_legacy", None, None, "exited", None),
            )


def test_launch_roles_stay_within_the_domain_enum(db):
    with pytest.raises(StorageError):
        with transaction(db):
            db.execute(
                "INSERT INTO launch_sessions VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid4()), None, 1, "unlisted_role", None, None, None, None),
            )


def test_review_events_constrain_game_id_and_change_payload(db):
    game = db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
    with transaction(db):
        db.execute(
            "INSERT INTO review_events VALUES (?,?,?,?,?)",
            (str(uuid4()), game, "reviewed", "2026-01-01T00:00:00+00:00", '{"rating": 0}'),
        )
    for kind in ("approved", ""):
        with pytest.raises(StorageError):
            with transaction(db):
                db.execute(
                    "INSERT INTO review_events VALUES (?,?,?,?,?)",
                    (str(uuid4()), game, kind, "2026-01-01T00:00:00+00:00", "{}"),
                )
    for payload in ("[]", "broken"):
        with pytest.raises(StorageError):
            with transaction(db):
                db.execute(
                    "INSERT INTO review_events VALUES (?,?,?,?,?)",
                    (str(uuid4()), game, "tested", "2026-01-01T00:00:00+00:00", payload),
                )
    with pytest.raises(StorageError):
        with transaction(db):
            db.execute(
                "INSERT INTO review_events VALUES (?,?,?,?,?)",
                (str(uuid4()), str(uuid4()), "tested", "2026-01-01T00:00:00+00:00", "{}"),
            )


def test_schema_is_repeatable_on_reopen(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    for _ in range(2):
        with closing(open_database(path, MIGRATIONS)) as connection:
            # Row order is unspecified without ORDER BY; only the set matters.
            assert [
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ] == [1, 2, 3]
            assert (
                connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 3
            )
    assert not list(tmp_path.glob("*.bak"))
