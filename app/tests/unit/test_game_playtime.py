"""Per-game playtime: schema, attribution and the most-played ranking."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from leo_kiosk.domain.errors import StorageError, ValidationError
from leo_kiosk.services.child import ScreenTimeService
from leo_kiosk.storage.child import (
    ChildRepository,
    GamePlaytimeRepository,
    ScreenTimeRepository,
)
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def db(tmp_path):
    with open_database(tmp_path / "s.sqlite3", migrations=MIGRATIONS) as connection:
        with transaction(connection):
            connection.execute(
                "INSERT INTO providers (id, name, website_url) "
                "VALUES ('test-provider', 'Test', 'https://example.org')"
            )
            for suffix in ("a", "b"):
                connection.execute(
                    "INSERT INTO games (id, provider_id, canonical_source_url, "
                    "source_name, media_type) VALUES (?, 'test-provider', ?, ?, 2)",
                    (
                        str(uuid4()),
                        f"https://example.org/{suffix}",
                        f"Game {suffix}",
                    ),
                )
        yield connection


@pytest.fixture
def service(db):
    return ScreenTimeService(
        ChildRepository(db),
        ScreenTimeRepository(db),
        GamePlaytimeRepository(db),
    )


def test_schema_indexes_playtime_per_day_and_game(db):
    columns = [r["name"] for r in db.execute("PRAGMA table_info(game_playtime)")]
    assert columns == ["day", "game_id", "seconds"]
    indexes = {
        r["name"]
        for r in db.execute("PRAGMA index_list(game_playtime)")
    }
    assert "game_playtime_total" in indexes
    assert "game_playtime_day" in indexes


def test_session_seconds_land_in_both_budget_and_game_ranking(service, db):
    game = db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
    now = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)

    service.record(10 * 60, now, UUID(game))
    service.record(5 * 60, now, UUID(game))  # a second session, same game
    service.record(60, now, UUID(
        db.execute("SELECT id FROM games ORDER BY id DESC LIMIT 1").fetchone()[0]
    ))

    assert service.used_seconds(now) == 10 * 60 + 5 * 60 + 60
    ranking = service.most_played()
    assert [row["game_id"] for row in ranking][0] == game
    assert [row["seconds"] for row in ranking] == [15 * 60, 60]


def test_ranking_orders_by_total_seconds_across_days(service, db):
    ids = [
        r[0] for r in db.execute("SELECT id FROM games ORDER BY source_name")
    ]
    monday = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
    tuesday = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)

    service.record(5 * 60, monday, UUID(ids[0]))  # A: 5 min
    service.record(30 * 60, tuesday, UUID(ids[1]))  # B: 30 min
    service.record(10 * 60, monday, UUID(ids[1]))  # B gains 10 min

    ranking = service.most_played()
    assert [row["game_id"] for row in ranking] == [ids[1], ids[0]]
    assert [row["seconds"] for row in ranking] == [40 * 60, 5 * 60]


def test_unattributed_time_never_enters_the_ranking(service, db):
    service.record(10 * 60, datetime(2026, 10, 26, 15, 0, tzinfo=UTC))
    assert service.most_played() == []
    assert service.used_seconds(datetime(2026, 10, 26, 15, 0, tzinfo=UTC)) == 10 * 60


def test_zero_and_negative_time_is_not_recorded(service, db):
    game = UUID(db.execute("SELECT id FROM games LIMIT 1").fetchone()[0])
    now = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
    service.record(0, now, game)
    service.record(-5, now, game)
    assert db.execute("SELECT count(*) FROM game_playtime").fetchone()[0] == 0


def test_non_uuid_game_identity_is_rejected(service, db):
    with pytest.raises(ValidationError):
        service.record(60, datetime(2026, 10, 26, 15, 0, tzinfo=UTC), "not-a-uuid")
    # the budget row must not be half-committed
    assert db.execute("SELECT count(*) FROM screen_time").fetchone()[0] == 0


def test_unknown_game_id_is_rejected_by_the_foreign_key(service, db):
    with pytest.raises(StorageError):
        service.record(60, datetime(2026, 10, 26, 15, 0, tzinfo=UTC), uuid4())
    # the shared transaction rolled back: no budget half-write either
    assert db.execute("SELECT count(*) FROM screen_time").fetchone()[0] == 0


def test_deleting_a_game_can_never_orphan_playtime_rows(db):
    game = db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
    GamePlaytimeRepository(db).add_seconds("2026-10-26", game, 60)
    from leo_kiosk.domain.errors import StorageError as _StorageError

    with pytest.raises(_StorageError):
        with transaction(db):
            db.execute("DELETE FROM games WHERE id = ?", (game,))


def test_repository_ranking_limit_is_validated(db):
    repo = GamePlaytimeRepository(db)
    with pytest.raises(ValueError):
        repo.most_played(0)
    with pytest.raises(ValueError):
        repo.most_played(101)


def test_service_without_the_per_game_store_cannot_rank(db):
    service = ScreenTimeService(ChildRepository(db), ScreenTimeRepository(db))
    with pytest.raises(StorageError):
        service.most_played()
    # but plain recording still works: optional attribution stays optional
    service.record(60, datetime(2026, 10, 26, 15, 0, tzinfo=UTC))
