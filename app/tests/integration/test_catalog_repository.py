from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from leo_kiosk.domain.catalog import (
    CatalogItem,
    DimensionEvidence,
    Dimensions,
    MediaType,
    Orientation,
)
from leo_kiosk.domain.catalog_metadata import Provider
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.errors import NotFoundError, StorageError, ValidationError
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def catalog(tmp_path):
    with closing(open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)) as connection:
        with transaction(connection):
            CatalogMetadataRepository(connection).upsert_provider(
                Provider("pbs", "PBS", "https://pbskids.org")
            )
        yield CatalogRepository(connection)


def item(name="Source", url="https://pbskids.org/game?id=1#level", **kwargs):
    return CatalogItem("pbs", url, name, MediaType.GAME, **kwargs)


@pytest.mark.parametrize("rating", [None, 0, 100])
def test_complete_record_survives_reopen(catalog, rating):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    source = item(
        orientation=Orientation.LANDSCAPE,
        dimensions=Dimensions(1024, 768, DimensionEvidence.DESIGN),
        launch_url="https://cdn.example.com/run?variant=2#start",
    )
    record = StoredGame(
        source,
        parent_name="Renamed",
        rating=rating,
        tested_at=now,
        reviewed_at=now,
        revision=3,
        source_metadata_json='{"original": {"arbitrary": [1, "é"]}}',
    )
    with transaction(catalog.connection):
        catalog.insert_record(record)
    path = catalog.connection.execute("PRAGMA database_list").fetchone()[2]
    with closing(open_database(path, MIGRATIONS)) as reopened:
        loaded = CatalogRepository(reopened).get_record(source.game_id)
        assert loaded == record and loaded.display_name == "Renamed"
        assert loaded.item.source_name == "Source" and loaded.item.playable_url == source.launch_url
        assert loaded.rating == rating


def test_list_hides_tombstones_without_destroying_evidence_or_videos(catalog):
    records = [
        StoredGame(item("Z video", "https://pbskids.org/v")),
        StoredGame(item("A deleted", "https://pbskids.org/a"), deleted_at=datetime.now(UTC)),
        StoredGame(CatalogItem("pbs", "https://pbskids.org/b", "B video", MediaType.VIDEO)),
    ]
    with transaction(catalog.connection):
        for record in records:
            catalog.insert_record(record)
    assert [r.display_name for r in catalog.list_records()] == ["B video", "Z video"]
    assert len(catalog.list_records(include_deleted=True)) == 3
    assert catalog.get_record(records[1].game_id).deleted_at is not None
    assert catalog.list_records()[0].item.media_type is MediaType.VIDEO


def test_insert_is_parameterized_and_duplicate_does_not_replace_review(catalog):
    record = StoredGame(item("'; DROP TABLE games; --"), parent_name="Kept", rating=0)
    with pytest.raises(StorageError, match="caller-owned"):
        catalog.insert_record(record)
    with transaction(catalog.connection):
        catalog.insert_record(record)
    with pytest.raises(StorageError):
        with transaction(catalog.connection):
            catalog.insert_record(StoredGame(record.item))
    assert catalog.get_record(record.game_id) == record
    with pytest.raises(NotFoundError):
        catalog.get_item(uuid4())


def test_missing_provider_and_oversized_sqlite_values_fail_without_partial_insert(catalog):
    missing = StoredGame(
        CatalogItem("missing", "https://example.com/game", "Missing", MediaType.GAME)
    )
    huge = StoredGame(item(), revision=1 << 100)
    for record in (missing, huge):
        with pytest.raises(StorageError):
            with transaction(catalog.connection):
                catalog.insert_record(record)
    assert catalog.list_records() == ()


@pytest.mark.parametrize(
    "evidence", [DimensionEvidence.UNKNOWN, DimensionEvidence.POPUP, DimensionEvidence.INFERRED]
)
def test_unknown_and_inferred_resolution_evidence_roundtrips_without_promotion(catalog, evidence):
    size = Dimensions() if evidence is DimensionEvidence.UNKNOWN else Dimensions(600, 800, evidence)
    record = StoredGame(item(dimensions=size))
    with transaction(catalog.connection):
        catalog.insert_record(record)
    loaded = catalog.get_item(record.game_id)
    assert loaded.dimensions == size and not loaded.dimensions.describes_game_size
    assert loaded.orientation is Orientation.UNKNOWN


def test_repository_does_not_commit_caller_transaction(catalog):
    record = StoredGame(item())
    with pytest.raises(ValidationError):
        with transaction(catalog.connection):
            catalog.insert_record(record)
            assert catalog.get_item(record.game_id) == record.item
            raise ValidationError("later import failure")
    assert catalog.list_records() == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(rating=True),
        dict(rating=1.5),
        dict(parent_name=""),
        dict(revision=True),
        dict(revision=-1),
        dict(tested_at=datetime(2026, 1, 1)),
        dict(source_metadata_json="[]"),
        dict(item=None),
    ],
)
def test_invalid_stored_record(kwargs):
    fields = dict(item=item())
    fields.update(kwargs)
    with pytest.raises(ValidationError):
        StoredGame(**fields)


def test_inconsistent_stored_id_and_bad_timestamp_are_typed_errors(catalog):
    record = StoredGame(item())
    with transaction(catalog.connection):
        catalog.insert_record(record)
    corrupt_id = uuid4()
    catalog.connection.execute("UPDATE games SET id = ?", (str(corrupt_id),))
    with pytest.raises(StorageError, match="metadata is invalid"):
        catalog.get_record(corrupt_id)
    catalog.connection.execute(
        "UPDATE games SET id = ?, tested_at = ?", (str(record.game_id), "bad")
    )
    with pytest.raises(StorageError, match="metadata is invalid"):
        catalog.get_record(record.game_id)
