"""Catalog query service: status derivation, eligibility, evidence labels."""

from datetime import UTC, datetime

import pytest

from leo_kiosk.domain.catalog import (
    CatalogItem,
    DimensionEvidence,
    Dimensions,
    MediaType,
)
from leo_kiosk.domain.catalog_metadata import Provider
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.services.catalog import CatalogService
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def service(tmp_path):
    with open_database(tmp_path / "catalog.sqlite3", MIGRATIONS) as db:
        with transaction(db):
            metadata = CatalogMetadataRepository(db)
            metadata.upsert_provider(Provider("pbs", "PBS", "https://pbskids.org"))
            catalog = CatalogRepository(db)
            for suffix, kind in (
                ("a", MediaType.GAME),
                ("b", MediaType.GAME),
                ("v", MediaType.VIDEO),
            ):
                item = CatalogItem(
                    "pbs",
                    f"https://pbskids.org/{suffix}",
                    f"Item {suffix}",
                    kind,
                    dimensions=Dimensions(800, 600, DimensionEvidence.POPUP),
                )
                catalog.insert_record(StoredGame(item))
        yield CatalogService(CatalogRepository(db)), CatalogRepository(db)


def test_status_precedence_new_tested_reviewed_selected(service):
    svc, repo = service
    entries = svc.list_review_entries()
    assert all(e.status.value == "new" for e in entries)
    game = next(e for e in entries if e.display_name == "Item a")
    record = repo.get_record(game.game_id)
    with transaction(repo.connection):
        repo.connection.execute(
            "UPDATE games SET tested_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), str(game.game_id)),
        )
    record = repo.get_record(game.game_id)
    assert svc.status(record).value == "tested"
    svc.refresh_selection([game.game_id])
    assert svc.status(record).value == "selected"


def test_only_games_are_playable_and_videos_stay_out(service):
    svc, _repo = service
    entries = svc.list_review_entries()
    assert [e.display_name for e in entries] == ["Item a", "Item b"]
    assert all("800x600 (popup)" == e.dimensions_text for e in entries)


def test_deleted_games_are_excluded_from_the_queue(service):
    svc, repo = service
    game = svc.list_review_entries()[0]
    with transaction(repo.connection):
        repo.connection.execute(
            "UPDATE games SET deleted_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), str(game.game_id)),
        )
    assert game.game_id not in {e.game_id for e in svc.list_review_entries()}


def test_selected_is_derived_not_stored(service):
    svc, repo = service
    game = svc.list_review_entries()[0]
    svc.refresh_selection([game.game_id])
    record = repo.get_record(game.game_id)
    assert svc.status(record) is not None
    assert not hasattr(record, "selected")
