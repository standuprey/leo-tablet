"""Thumbnail table: PK latest-wins semantics and game-delete cascade."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from leo_kiosk.domain.catalog import CatalogItem, MediaType
from leo_kiosk.domain.catalog_metadata import Provider
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS
from leo_kiosk.storage.thumbs import ThumbnailRepository


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)) as connection:
        with transaction(connection):
            CatalogMetadataRepository(connection).upsert_provider(
                Provider("pbs", "PBS", "https://pbskids.org")
            )
        yield connection


def _insert_game(db: sqlite3.Connection) -> UUID:
    record = StoredGame(CatalogItem("pbs", "https://pbskids.org/game", "Game", MediaType.GAME))
    with transaction(db):
        CatalogRepository(db).insert_record(record)
    return record.game_id


def test_row_upserts_per_game_and_reports_presence(db: sqlite3.Connection) -> None:
    repository = ThumbnailRepository(db)
    game_id = _insert_game(db)
    assert not repository.has_thumbnail(game_id)
    with transaction(db):
        repository.record(game_id, datetime.now(UTC))
    assert repository.has_thumbnail(game_id)
    with transaction(db):
        repository.record(game_id, datetime.now(UTC))  # latest-wins upsert
    assert db.execute("SELECT count(*) FROM game_thumbnails").fetchone()[0] == 1


def test_deleting_the_game_cascades_the_thumbnail_row(db: sqlite3.Connection) -> None:
    repository = ThumbnailRepository(db)
    game_id = uuid4()
    db.execute(
        "INSERT INTO games (id, provider_id, canonical_source_url, source_name, media_type) "
        "VALUES (?, 'pbs', 'https://pbskids.org/g', 'G', 2)",
        (str(game_id),),
    )
    with transaction(db):
        repository.record(game_id, datetime.now(UTC))
    with transaction(db):
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM games WHERE id = ?", (str(game_id),))
    assert not repository.has_thumbnail(game_id)


def test_unknown_game_cannot_get_a_thumbnail_row(db: sqlite3.Connection) -> None:
    from leo_kiosk.domain.errors import StorageError

    repository = ThumbnailRepository(db)
    with pytest.raises(StorageError), transaction(db):
        repository.record(uuid4(), datetime.now(UTC))
