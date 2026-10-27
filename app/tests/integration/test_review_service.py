"""ReviewService writes against a real migrated database."""

import pytest

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.domain.reviews import AgeRange, StarRating
from leo_kiosk.services.catalog import CatalogService
from leo_kiosk.services.review import ReviewService
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_import import import_catalog
from leo_kiosk.storage.database import open_database
from leo_kiosk.storage.home import HomeRepository
from leo_kiosk.storage.schema import MIGRATIONS


class Source:
    checksum: str
    providers: tuple
    games: tuple


@pytest.fixture
def db(tmp_path):
    database = open_database(tmp_path / "c.sqlite3", migrations=MIGRATIONS)
    yield database
    database.close()


@pytest.fixture
def service(db):
    source = Source()
    source.checksum = "a" * 64
    source.providers = (
        {"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},
    )
    source.games = (
        {"provider_id": "pbs", "source_url": "https://a/1", "source_name": "One", "media_type": 2},
        {"provider_id": "pbs", "source_url": "https://a/2", "source_name": "Two", "media_type": 2},
    )
    import_catalog(db, source)
    repo = CatalogRepository(db)
    catalog = CatalogService(repo, HomeRepository(db).selected_game_ids())
    yield catalog, ReviewService(repo), db


def entries(catalog):
    return catalog.list_review_entries()


def test_apply_review_records_name_stars_age_and_status(service):
    catalog, review, _db = service
    game = entries(catalog)[0].game_id
    review.mark_tested(game)
    review.apply_review(game, "Bots", StarRating(5, 4, 3), AgeRange(4, 7))
    entry = catalog.get_entry(game)
    assert entry.display_name == "Bots"
    assert (entry.stars.production, entry.stars.education, entry.stars.fun) == (5, 4, 3)
    assert (entry.age_min, entry.age_max) == (4, 7)
    assert entry.status.value == "reviewed"


def test_mark_tested_is_idempotent_on_the_timestamp(service, db):
    catalog, review, _db = service
    game = entries(catalog)[0].game_id
    review.mark_tested(game)
    row = db.execute("SELECT tested_at FROM games WHERE id = ?", (str(game),)).fetchone()
    first = row["tested_at"]
    review.mark_tested(game)
    row = db.execute("SELECT tested_at FROM games WHERE id = ?", (str(game),)).fetchone()
    assert row["tested_at"] == first
    events = db.execute("SELECT event_kind FROM review_events WHERE game_id = ?", (str(game),)).fetchall()
    assert [e[0] for e in events].count("tested") == 2


def test_delete_tombstones_and_removes_from_the_queue(service, db):
    catalog, review, _db = service
    game = entries(catalog)[0].game_id
    review.delete_game(game)
    assert all(e.game_id != game for e in entries(catalog))
    row = db.execute("SELECT deleted_at FROM games WHERE id = ?", (str(game),)).fetchone()
    assert row["deleted_at"] is not None
    event = db.execute(
        "SELECT change_json FROM review_events WHERE game_id = ? AND event_kind = 'deleted'",
        (str(game),),
    ).fetchone()
    assert '"parent"' in event[0]  # not auto: reimport cannot resurrect


def test_invalid_drafts_are_rejected_before_any_write(service):
    catalog, review, _db = service
    game = entries(catalog)[0].game_id
    with pytest.raises(ValidationError):
        review.apply_review(game, "X", StarRating(5, 4, 9), None)
    with pytest.raises(ValidationError):
        review.apply_review(game, "X", None, AgeRange(9, 4))
    entry = catalog.get_entry(game)
    assert entry.status.value == "new" and entry.stars is None
