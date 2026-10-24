from contextlib import closing
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions, MediaType, Orientation
from leo_kiosk.domain.catalog_metadata import ImportRecord, Provider
from leo_kiosk.domain.errors import NotFoundError, StorageError, ValidationError
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS


@pytest.fixture
def metadata(tmp_path):
    with closing(open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)) as connection:
        yield CatalogMetadataRepository(connection)


def test_provider_upsert_is_parameterized_and_returns_immutable_dtos(metadata):
    provider = Provider("pbs", "  '; DROP TABLE games; --  ", "HTTPS://PBSKIDS.ORG:443")
    with transaction(metadata.connection):
        metadata.upsert_provider(provider)
    assert metadata.get_provider("pbs") == provider
    with pytest.raises(FrozenInstanceError):
        provider.name = "changed"
    updated = Provider("pbs", "PBS Kids", "https://pbskids.org")
    with transaction(metadata.connection):
        metadata.upsert_provider(updated)
    assert metadata.list_providers() == (updated,)
    assert metadata.connection.execute("SELECT count(*) FROM games").fetchone()[0] == 0


def test_import_history_keeps_distinct_events_with_same_source_checksum(metadata):
    first = ImportRecord("a" * 64, datetime(2026, 1, 1, tzinfo=UTC), '{"added": 2}')
    second = ImportRecord(first.source_checksum, datetime(2026, 1, 2, tzinfo=UTC))
    with transaction(metadata.connection):
        metadata.record_import(first)
        metadata.record_import(second)
    assert metadata.get_import(first.import_id) == first
    assert metadata.list_imports() == (first, second)
    with pytest.raises(StorageError):
        with transaction(metadata.connection):
            metadata.record_import(first)
    assert len(metadata.list_imports()) == 2


def test_writes_require_caller_transaction_and_rollback_together(metadata):
    provider = Provider("pbs", "PBS", "https://pbskids.org")
    with pytest.raises(StorageError, match="caller-owned"):
        metadata.upsert_provider(provider)
    with pytest.raises(ValidationError):
        with transaction(metadata.connection):
            metadata.upsert_provider(provider)
            metadata.record_import(ImportRecord("b" * 64, datetime.now(UTC)))
            raise ValidationError("abort source import")
    assert metadata.list_providers() == () and metadata.list_imports() == ()
    with pytest.raises(NotFoundError):
        metadata.get_provider("pbs")
    with pytest.raises(NotFoundError):
        metadata.get_import(uuid4())


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(source_checksum="bad"),
        dict(imported_at=None),
        dict(imported_at=datetime(2026, 1, 1)),
        dict(report_json="[]"),
        dict(report_json="bad"),
        dict(report_json='{"count": NaN}'),
        dict(import_id="not-a-uuid"),
    ],
)
def test_invalid_import_dto(kwargs):
    fields = dict(source_checksum="c" * 64, imported_at=datetime.now(UTC))
    fields.update(kwargs)
    with pytest.raises(ValidationError):
        ImportRecord(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        ("PBS Kids", "PBS", "https://pbskids.org"),
        ("pbs", " ", "https://pbskids.org"),
        ("pbs", "PBS", "javascript:alert(1)"),
    ],
)
def test_invalid_provider_dto(fields):
    with pytest.raises(ValidationError):
        Provider(*fields)


# --- flexible source adapters (owner decision: no fixed JSON format) --------


def test_media_type_accepts_enum_integers_only(metadata):
    from leo_kiosk.storage.catalog_metadata import _media_type

    assert _media_type(2) is MediaType.GAME
    assert _media_type(MediaType.VIDEO) is MediaType.VIDEO
    for value in ["game", "2", True, 1.0, None]:
        with pytest.raises(ValueError):
            _media_type(value)


def test_legacy_orientation_booleans_stay_unknown(metadata):
    from leo_kiosk.storage.catalog_metadata import _orientation

    assert _orientation(True) is Orientation.UNKNOWN
    assert _orientation(False) is Orientation.UNKNOWN
    assert _orientation(None) is Orientation.UNKNOWN
    assert _orientation("portrait") is Orientation.PORTRAIT
    for value in ["diagonal", 1, []]:
        with pytest.raises(ValueError):
            _orientation(value)


def test_sizes_without_evidence_are_rejected_not_treated_as_measurements(metadata):
    from leo_kiosk.storage.catalog_metadata import _dimensions

    with pytest.raises(ValueError):
        _dimensions({"width": 800, "height": 600})
    with pytest.raises(ValueError):
        _dimensions({"width": 800, "height": 600, "dimension_evidence": True})
    assert _dimensions({}).width is None
    assert (
        _dimensions({"width": 800, "height": 600, "dimension_evidence": "popup"}).evidence
        is DimensionEvidence.POPUP
    )


def test_source_game_adapter_preserves_identity_and_metadata(metadata):
    game = CatalogMetadataRepository.game_from_source(
        {
            "provider_id": "gulli",
            "source_url": "HTTPS://JEUX.GULLI.FR/game/",
            "source_name": "Title",
            "type": 2,
            "is_landscape": True,
            "width": 800,
            "height": 600,
            "dimension_evidence": "popup",
            "source_metadata_json": '{"launcher": "preroll-web2"}',
        }
    )
    assert game.item.media_type is MediaType.GAME
    assert game.item.orientation is Orientation.UNKNOWN  # boolean is not measured data
    assert game.item.dimensions == Dimensions(800, 600, DimensionEvidence.POPUP)
    assert game.source_metadata_json == '{"launcher":"preroll-web2"}'
    from leo_kiosk.domain.catalog import stable_game_id

    assert game.game_id == stable_game_id("gulli", "https://jeux.gulli.fr/game/")


def test_source_game_adapter_launch_override(metadata):
    game = CatalogMetadataRepository.game_from_source(
        {
            "provider_id": "pbs",
            "source_url": "https://pbskids.org/game",
            "source_name": "A",
            "media_type": 2,
            "launch_url": "https://cdn.example.com/run",
        }
    )
    assert game.item.launch_url == "https://cdn.example.com/run"
    assert game.source_metadata_json == "{}"


@pytest.mark.parametrize(
    "raw",
    [
        {"source_url": "https://example.com", "source_name": "A", "media_type": 2},
        {"provider_id": "pbs", "source_name": "A", "media_type": 2},
        {"provider_id": "pbs", "source_url": "https://example.com", "media_type": 2},
        {
            "provider_id": "pbs",
            "source_url": "https://example.com",
            "source_name": "A",
            "media_type": "game",
        },
        {
            "provider_id": "pbs",
            "source_url": "https://example.com",
            "source_name": "A",
            "media_type": 2,
            "launch_url": 7,
        },
    ],
)
def test_invalid_source_game_adapters(raw):
    with pytest.raises(ValueError):
        CatalogMetadataRepository.game_from_source(raw)
