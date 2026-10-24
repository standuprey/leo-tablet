"""Home seeding, slot primitives, and atomic review save/delete."""

import json
from datetime import UTC, datetime

import pytest

from leo_kiosk.domain.catalog import CatalogItem, MediaType
from leo_kiosk.domain.catalog_metadata import Provider
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.errors import ConflictError, ValidationError
from leo_kiosk.domain.reviews import ReviewDraft, SelectionIntent
from leo_kiosk.services.home import HomeService
from leo_kiosk.services.home_seed import load_legacy_tiles, seed_home
from leo_kiosk.services.reviews import ReviewService
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.home import HomeRepository
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def env(tmp_path):
    db = open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)
    catalog = CatalogRepository(db)
    home_repo = HomeRepository(db)
    home = HomeService(home_repo, catalog)
    reviews = ReviewService(catalog, home)
    with transaction(db):
        CatalogMetadataRepository(db).upsert_provider(Provider("pbs", "PBS", "https://pbskids.org"))
        for suffix in ("a", "b", "c"):
            item = CatalogItem(
                "pbs", f"https://pbskids.org/{suffix}", f"Item {suffix}", MediaType.GAME
            )
            catalog.insert_record(StoredGame(item))
    seed_home(db, write_tiles(tmp_path))
    return {
        "db": db,
        "catalog": catalog,
        "home": home,
        "reviews": reviews,
        "games": {},
        "tmp": tmp_path,
    }


def write_tiles(tmp_path, tiles=None):
    path = tmp_path / "tiles.json"
    if tiles is None:
        tiles = [
            {
                "id": f"tile{i}",
                "label": f"T{i}",
                "color": "#ff6b6b",
                "cmd": [f"app{i}"],
                "minutes": 10 + i,
            }
            for i in range(9)
        ]
    path.write_text(json.dumps({"title": "L", "columns": 3, "tiles": tiles}))
    return path


def make_reviewed(env, suffix="a"):
    """Mark an existing catalog game as reviewed; return its id."""
    catalog, db = env["catalog"], env["db"]
    items = {r.display_name: r.game_id for r in catalog.list_records()}
    game_id = items[f"Item {suffix}"]
    with transaction(db):
        db.execute(
            "UPDATE games SET parent_name = 'Renamed', rating = 55, reviewed_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), str(game_id)),
        )
    return game_id


# --- parent-15: seeding -------------------------------------------------------


def test_seed_fills_nine_positions_from_trusted_config(env):
    db = env["db"]
    home_repo = HomeRepository(db)
    slots = home_repo.slots()
    assert [s.position for s in slots] == list(range(1, 10))
    assert all(s.legacy_tile_id == f"tile{i}" for i, s in zip(range(9), slots, strict=True))
    stored = json.loads(
        db.execute("SELECT legacy_tile_json FROM home_slots WHERE position = 1").fetchone()[0]
    )
    assert stored["cmd"] == ["app0"] and stored["minutes"] == 10


def test_seed_is_once_only_and_never_overwrites_a_replacement(env):
    db, home = env["db"], env["home"]
    path = write_tiles(env["tmp"])
    game = make_reviewed(env)
    home.place(game, 1, replacement_confirmation=home.slot(1))  # replaces tile0
    assert seed_home(db, path) is False
    slots = {s.position: s.game_id for s in home.slots()}
    assert slots[1] == game  # replacement survives a second seed attempt


def test_malformed_seed_config_fails_without_partial_fill(env):
    # Fresh empty table for this test.
    db2 = open_database(env["tmp"] / "second.sqlite3", MIGRATIONS)
    bad = write_tiles(
        env["tmp"],
        tiles=[
            {"id": "ok", "label": "OK", "color": "#fff", "cmd": ["app"], "minutes": 5},
            {"id": "broken", "label": "B", "color": "#fff", "cmd": [], "minutes": 5},
        ],
    )
    with pytest.raises(ValidationError):
        seed_home(db2, bad)
    assert all(s.legacy_tile_id is None for s in HomeRepository(db2).slots())
    with pytest.raises(ValidationError):
        load_legacy_tiles(
            write_tiles(
                env["tmp"],
                tiles=[
                    {"id": "dup", "label": "A", "color": "#fff", "cmd": ["x"], "minutes": 5},
                    {"id": "dup", "label": "B", "color": "#fff", "cmd": ["y"], "minutes": 5},
                ],
            )
        )
    with pytest.raises(ValidationError):
        load_legacy_tiles(
            write_tiles(
                env["tmp"],
                tiles=[
                    {
                        "id": "evil",
                        "label": "E",
                        "color": "#fff",
                        "cmd": ["sh", "-c", "rm -rf /"],
                        "minutes": True,
                    },
                ],
            )
        )


# --- parent-16: slot primitives ----------------------------------------------


def test_place_requires_reviewed_nondeleted_game(env):
    game_id = [r.game_id for r in env["catalog"].list_records() if r.display_name == "Item a"][0]
    with pytest.raises(ValidationError, match="reviewed"):
        env["home"].place(game_id, 1)


def test_place_replacement_requires_the_seen_occupant(env):
    home = env["home"]
    game = make_reviewed(env)
    other = make_reviewed(env, "b")
    home.place(game, 1, replacement_confirmation=home.slot(1))
    with pytest.raises(ConflictError, match="confirmation"):
        home.place(other, 1)  # no confirmation of the current occupant
    home.place(other, 1, replacement_confirmation=home.slot(1))
    assert home.slot(1).game_id == other


def test_move_clears_the_previous_slot(env):
    home = env["home"]
    game = make_reviewed(env)
    home.place(game, 3, replacement_confirmation=home.slot(3))
    home.place(game, 7, replacement_confirmation=home.slot(7))
    assert home.slot(7).game_id == game
    assert home.slot(3).game_id is None and home.slot(3).legacy_tile_id is None


def test_unselect_leaves_the_position_empty(env):
    home = env["home"]
    game = make_reviewed(env)
    home.place(game, 2, replacement_confirmation=home.slot(2))
    assert home.unselect(game) is True
    assert home.slot(2).game_id is None and home.slot(2).legacy_tile_id is None
    assert home.unselect(game) is False


# --- parent-17: atomic save_review -------------------------------------------


def test_save_review_keeps_metadata_and_unselect_atomically(env):
    db, home, reviews = env["db"], env["home"], env["reviews"]
    game = make_reviewed(env)
    home.place(game, 4, replacement_confirmation=home.slot(4))
    summary = reviews.save_review(game, 0, ReviewDraft("New Name", 70, SelectionIntent.KEEP))
    assert summary.display_name == "New Name" and summary.rating == 70
    assert summary.status.value == "reviewed" and summary.revision == 1
    assert home.slot_for_game(game) is None
    assert home.slot(4).game_id is None and home.slot(4).legacy_tile_id is None
    event = db.execute(
        "SELECT event_kind FROM review_events ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    assert event[0] == "reviewed"


def test_save_review_select_requires_a_slot_for_new_selection(env):
    game = make_reviewed(env)
    with pytest.raises(ValidationError, match="choosing one of the 9"):
        env["reviews"].save_review(game, 0, ReviewDraft("N", None, SelectionIntent.SELECT))


def test_save_review_select_preserves_existing_slot_without_target(env):
    home, reviews = env["home"], env["reviews"]
    game = make_reviewed(env)
    home.place(game, 5, replacement_confirmation=home.slot(5))
    reviews.save_review(game, 0, ReviewDraft("N", 1, SelectionIntent.SELECT))
    assert home.slot(5).game_id == game  # kept, not moved to a default position


def test_save_review_move_requires_confirmation_of_occupant(env):
    home, reviews = env["home"], env["reviews"]
    game = make_reviewed(env)
    home.place(game, 5, replacement_confirmation=home.slot(5))
    other = make_reviewed(env, "b")
    home.place(other, 8, replacement_confirmation=home.slot(8))
    with pytest.raises(ConflictError):
        reviews.save_review(game, 0, ReviewDraft("N", None, SelectionIntent.SELECT), target_slot=8)
    summary = reviews.save_review(
        game,
        0,
        ReviewDraft("N", None, SelectionIntent.SELECT),
        target_slot=8,
        replacement_confirmation=home.slot(8),
    )
    assert home.slot(8).game_id == game and home.slot(5).game_id is None
    assert summary.status.value == "selected"


def test_stale_revision_conflicts_and_rolls_back_everything(env):
    db, reviews = env["db"], env["reviews"]
    game = make_reviewed(env)
    before = db.execute("SELECT * FROM games WHERE id = ?", (str(game),)).fetchone()
    with pytest.raises(ConflictError):
        reviews.save_review(game, 5, ReviewDraft("X", 10, SelectionIntent.KEEP))
    after = db.execute("SELECT * FROM games WHERE id = ?", (str(game),)).fetchone()
    assert tuple(after) == tuple(before)
    assert db.execute("SELECT count(*) FROM review_events").fetchone()[0] == 0


# --- parent-18: delete --------------------------------------------------------


def test_delete_tombstones_unselects_and_never_saves_the_draft(env):
    catalog, home, reviews = env["catalog"], env["home"], env["reviews"]
    game = make_reviewed(env)
    home.place(game, 6, replacement_confirmation=home.slot(6))
    reviews.delete_game(game, 0)
    record = catalog.get_record(game)
    assert record.deleted_at is not None
    assert home.slot(6).game_id is None
    assert record.parent_name is not None  # existing metadata untouched
    reviews.delete_game(game, 1)  # idempotent
    assert catalog.get_record(game).deleted_at is not None


def test_stale_revision_delete_conflicts(env):
    game = make_reviewed(env)
    with pytest.raises(ConflictError):
        env["reviews"].delete_game(game, 9)


def test_restore_clears_tombstone_without_autoselect(env):
    catalog, home, reviews = env["catalog"], env["home"], env["reviews"]
    game = make_reviewed(env)
    reviews.delete_game(game, 0)
    reviews.restore(game)
    record = catalog.get_record(game)
    assert record.deleted_at is None
    assert home.slot_for_game(game) is None  # never auto-selected
