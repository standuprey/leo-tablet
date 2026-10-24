import json
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions, MediaType, Orientation
from leo_kiosk.domain.errors import StorageError, ValidationError
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_import import import_catalog
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS


@dataclass(frozen=True)
class Source:
    """Minimal flexible source; field access, the old JSON shape is not a contract."""

    checksum: str
    providers: tuple[dict[str, Any], ...]
    games: tuple[dict[str, Any], ...]


def game(provider="pbs", url="https://pbskids.org/game", name="Game", media_type=2, **extra):
    fields: dict[str, Any] = {
        "provider_id": provider,
        "source_url": url,
        "source_name": name,
        "media_type": media_type,
    }
    fields.update(extra)
    return fields


@pytest.fixture
def db(tmp_path):
    with closing(open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)) as connection:
        yield connection


def test_fresh_import_populates_catalog_and_records_the_report(db):
    source = Source(
        "a" * 64,
        ({"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},),
        (game(), game(url="https://pbskids.org/v", media_type=1, name="Video")),
    )
    report = import_catalog(db, source)
    assert (report.added, report.updated, report.unchanged) == (2, 0, 0)
    assert report.preserved_local == 0
    assert json.loads(report.as_json()) == {
        "added": 2,
        "preserved_local": 0,
        "unchanged": 0,
        "updated": 0,
    }
    stored = CatalogRepository(db).list_records()
    assert [record.item.media_type for record in stored] == [MediaType.GAME, MediaType.VIDEO]
    imports = CatalogMetadataRepository(db).list_imports()
    assert len(imports) == 1 and imports[0].source_checksum == report.source_checksum
    assert json.loads(imports[0].report_json) == {
        "added": 2,
        "preserved_local": 0,
        "unchanged": 0,
        "updated": 0,
    }


def test_reimport_updates_source_fields_and_never_parent_decisions(db):
    source = Source(
        "a" * 64,
        ({"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},),
        (game(),),
    )
    import_catalog(db, source)
    catalog = CatalogRepository(db)
    record = catalog.list_records()[0]
    with transaction(db):
        db.execute(
            "UPDATE games SET parent_name = ?, rating = ?, revision = ? WHERE id = ?",
            ("Renamed", 7, 4, str(record.game_id)),
        )
    revised = Source(
        "b" * 64,
        source.providers,
        (
            game(
                name="New Title",
                url="https://pbskids.org/game",
                dimension_evidence="popup",
                width=800,
                height=600,
                source_metadata_json='{"changed": true}',
            ),
        ),
    )
    report = import_catalog(db, revised)
    assert (report.added, report.updated, report.unchanged, report.preserved_local) == (0, 1, 0, 0)
    loaded = catalog.get_record(record.game_id)
    assert loaded.display_name == "Renamed" and loaded.rating == 7 and loaded.revision == 4
    assert loaded.item.source_name == "New Title"
    assert loaded.item.dimensions == Dimensions(800, 600, DimensionEvidence.POPUP)
    assert loaded.source_metadata_json == '{"changed":true}'


def test_unchanged_reimport_is_reported_without_writes(db):
    source = Source(
        "a" * 64,
        ({"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},),
        (game(),),
    )
    import_catalog(db, source)
    before = db.execute("SELECT count(*), max(revision) FROM games").fetchone()
    report = import_catalog(db, source)
    assert (report.added, report.updated, report.unchanged) == (0, 0, 1)
    assert db.execute("SELECT count(*), max(revision) FROM games").fetchone() == before


def test_removed_source_record_with_review_survives_and_history_is_appended(db):
    source = Source(
        "a" * 64,
        ({"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},),
        (game(), game(url="https://pbskids.org/other", name="Other")),
    )
    import_catalog(db, source)
    catalog = CatalogRepository(db)
    record = catalog.list_records()[0]
    with transaction(db):
        db.execute(
            "UPDATE games SET reviewed_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), str(record.game_id)),
        )
    pruned = Source(
        "c" * 64, source.providers, (game(url="https://pbskids.org/other", name="Other"),)
    )
    report = import_catalog(db, pruned)
    assert report.preserved_local == 1 and report.added == 0
    assert catalog.get_record(record.game_id).reviewed_at is not None
    assert [r.source_checksum for r in CatalogMetadataRepository(db).list_imports()] == [
        "a" * 64,
        "c" * 64,
    ]


def test_untested_record_removed_from_source_survives_for_parent_decision(db):
    source = Source(
        "a" * 64,
        ({"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},),
        (game(), game(url="https://pbskids.org/other", name="Other")),
    )
    import_catalog(db, source)
    pruned = Source("d" * 64, source.providers, (game(),))
    report = import_catalog(db, pruned)
    assert report.preserved_local == 0 and report.added == 0 and report.unchanged == 1
    assert len(CatalogRepository(db).list_records()) == 2


def test_flexible_source_shape_uses_legacy_placeholders_correctly(db):
    source = Source(
        "e" * 64,
        ({"provider_id": "gulli", "name": "Gulli", "website_url": "https://www.gulli.fr"},),
        (
            game(
                provider="gulli",
                url="https://jeux.gulli.fr/x/",
                name="Portrait",
                media_type=2,
                is_landscape=False,
                width=600,
                height=800,
                dimension_evidence="popup",
            ),
        ),
    )
    import_catalog(db, source)
    record = CatalogRepository(db).list_records()[0]
    assert record.item.orientation is Orientation.UNKNOWN  # boolean is not measured portrait
    assert record.item.dimensions.evidence is DimensionEvidence.POPUP


@pytest.mark.parametrize(
    "broken",
    [
        Source("", (), (game(),)),
        Source("a" * 64, (), (game(),)),  # Provider for the game is missing.
        Source("a" * 64, ({"provider_id": "pbs", "name": "PBS"},), ()),
        Source("a" * 64, (), ({"source_url": "https://example.com"},)),
        Source("a" * 64, (), (game(), game(url="https://pbskids.org/game?x=1"))),
    ],
)
def test_invalid_source_leaves_catalog_unchanged(db, broken):
    good = Source(
        "a" * 64,
        ({"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},),
        (game(),),
    )
    import_catalog(db, good)
    before = db.execute("SELECT count(*) FROM games").fetchone()[0]
    with pytest.raises((ValidationError, ValueError, StorageError)):
        import_catalog(db, broken)
    assert db.execute("SELECT count(*) FROM games").fetchone()[0] == before
    assert len(CatalogMetadataRepository(db).list_imports()) == 1


def test_rejected_import_leaves_no_partial_changes_or_backup(db):
    good = Source(
        "a" * 64,
        ({"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"},),
        (game(),),
    )
    import_catalog(db, good)
    count_before = db.execute("SELECT count(*) FROM games").fetchone()[0]
    broken = Source(
        "f" * 64,
        good.providers,
        (game(url="https://pbskids.org/new", name="New"), game(url="https://pbskids.org/new")),
    )
    with pytest.raises((ValidationError, StorageError)):
        import_catalog(db, broken)
    assert db.execute("SELECT count(*) FROM games").fetchone()[0] == count_before
    assert len(CatalogMetadataRepository(db).list_imports()) == 1
