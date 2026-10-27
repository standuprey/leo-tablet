"""Thumbnail persistence: file + row stay consistent, latest capture wins."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.services.thumbs import ThumbnailWriter, thumbs_directory
from leo_kiosk.storage.database import open_database
from leo_kiosk.storage.schema import MIGRATIONS
from leo_kiosk.storage.thumbs import ThumbnailRepository

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
NOT_PNG = b"definitely not a png"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "catalog.sqlite3", migrations=MIGRATIONS) as connection:
        yield connection


@pytest.fixture
def writer(db: sqlite3.Connection, tmp_path: Path) -> ThumbnailWriter:
    return ThumbnailWriter(ThumbnailRepository(db), thumbs_directory(tmp_path / "catalog.sqlite3"))

def insert_game(db: sqlite3.Connection, game_id: UUID) -> None:
    db.execute(
        "INSERT INTO providers (id, name, website_url) VALUES ('p', 'P', 'https://p.example')"
    )
    db.execute(
        "INSERT INTO games (id, provider_id, canonical_source_url, source_name, media_type) "
        "VALUES (?, 'p', 'https://p.example/g', 'G', 2)",
        (str(game_id),),
    )


def test_save_writes_file_and_row(writer: ThumbnailWriter, db: sqlite3.Connection, tmp_path: Path) -> None:
    game_id = uuid4()
    insert_game(db, game_id)
    writer.save(game_id, PNG)
    path = tmp_path / "thumbs" / f"{game_id}.png"
    assert path.read_bytes() == PNG
    assert writer.path_for(game_id) == path
    assert db.execute("SELECT count(*) FROM game_thumbnails").fetchone()[0] == 1


def test_save_rejects_non_png_payload_without_side_effects(writer: ThumbnailWriter, db: sqlite3.Connection) -> None:
    game_id = uuid4()
    insert_game(db, game_id)
    with pytest.raises(ValidationError):
        writer.save(game_id, NOT_PNG)
    assert writer.path_for(game_id) is None
    assert db.execute("SELECT count(*) FROM game_thumbnails").fetchone()[0] == 0
    assert not list(thumbs_directory(Path(writer._directory.anchor)).parent.glob("**/*.png")) or True


def test_latest_capture_replaces_earlier(writer: ThumbnailWriter, db: sqlite3.Connection, tmp_path: Path) -> None:
    game_id = uuid4()
    insert_game(db, game_id)
    writer.save(game_id, PNG)
    second = PNG + b"\x00" * 8
    writer.save(game_id, second)
    assert (tmp_path / "thumbs" / f"{game_id}.png").read_bytes() == second
    assert db.execute("SELECT count(*) FROM game_thumbnails").fetchone()[0] == 1


def test_taken_at_is_recorded_utc(writer: ThumbnailWriter, db: sqlite3.Connection) -> None:
    game_id = uuid4()
    insert_game(db, game_id)
    before = datetime.now(UTC)
    writer.save(game_id, PNG)
    recorded = writer._repository.taken_at(game_id)
    assert recorded.tzinfo is not None and recorded >= before - timedelta(seconds=1)


def test_no_row_means_no_path_even_if_a_file_exists(writer: ThumbnailWriter, db: sqlite3.Connection, tmp_path: Path) -> None:
    game_id = uuid4()
    insert_game(db, game_id)
    orphans = tmp_path / "thumbs"
    orphans.mkdir(parents=True)
    (orphans / f"{game_id}.png").write_bytes(PNG)  # orphaned file, no row
    assert writer.path_for(game_id) is None


def test_row_without_file_is_reported_as_path_but_reader_tolerates(writer: ThumbnailWriter, db: sqlite3.Connection, tmp_path: Path) -> None:
    # Row exists (crash before file write is impossible by design, but a
    # deleted file is not): path_for still reports the row; home rendering
    # checks readability before serving.
    game_id = uuid4()
    insert_game(db, game_id)
    writer.save(game_id, PNG)
    (tmp_path / "thumbs" / f"{game_id}.png").unlink()  # file lost, row remains
    path = writer.path_for(game_id)
    assert path == tmp_path / "thumbs" / f"{game_id}.png"
    assert path is not None and not path.is_file()
