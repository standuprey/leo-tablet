"""Version 1: catalog source data and parent review metadata, no home assignments."""

from ..migrations import Migration

_UUID = """CHECK (length(id) = 36
    AND id GLOB '????????-????-????-????-????????????'
    AND length(replace(id, '-', '')) = 32
    AND replace(id, '-', '') NOT GLOB '*[^0-9a-f]*')"""

CATALOG = Migration(
    1,
    (
        """CREATE TABLE providers (
        id TEXT PRIMARY KEY NOT NULL CHECK (length(id) > 0
            AND substr(id, 1, 1) GLOB '[a-z]' AND id NOT GLOB '*[^a-z0-9-]*'),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        website_url TEXT NOT NULL CHECK (
            website_url GLOB 'https://?*' OR website_url GLOB 'http://?*')
    )""",
        f"""CREATE TABLE games (
        id TEXT PRIMARY KEY NOT NULL {_UUID},
        provider_id TEXT NOT NULL REFERENCES providers(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        canonical_source_url TEXT NOT NULL CHECK (
            canonical_source_url GLOB 'https://?*' OR canonical_source_url GLOB 'http://?*'),
        launch_url TEXT CHECK (launch_url IS NULL OR launch_url GLOB 'https://?*'
            OR launch_url GLOB 'http://?*'),
        source_name TEXT NOT NULL CHECK (length(trim(source_name)) > 0),
        media_type INTEGER NOT NULL CHECK (typeof(media_type) = 'integer' AND media_type IN (0, 1, 2)),
        orientation TEXT NOT NULL DEFAULT 'unknown'
            CHECK (orientation IN ('unknown', 'landscape', 'portrait', 'square')),
        width INTEGER,
        height INTEGER,
        dimension_evidence TEXT NOT NULL DEFAULT 'unknown'
            CHECK (dimension_evidence IN ('unknown', 'design', 'iframe', 'popup', 'inferred')),
        source_metadata_json TEXT NOT NULL DEFAULT '{{}}'
            CHECK (json_valid(source_metadata_json) AND json_type(source_metadata_json) = 'object'),
        parent_name TEXT CHECK (parent_name IS NULL OR length(trim(parent_name)) BETWEEN 1 AND 80),
        rating INTEGER CHECK (rating IS NULL OR (typeof(rating) = 'integer' AND rating BETWEEN 0 AND 100)),
        tested_at TEXT,
        reviewed_at TEXT,
        deleted_at TEXT,
        revision INTEGER NOT NULL DEFAULT 0 CHECK (typeof(revision) = 'integer' AND revision >= 0),
        UNIQUE (provider_id, canonical_source_url),
        CHECK ((width IS NULL AND height IS NULL AND dimension_evidence = 'unknown') OR
            (typeof(width) = 'integer' AND width > 0 AND typeof(height) = 'integer'
                AND height > 0 AND dimension_evidence != 'unknown'))
    )""",
        f"""CREATE TABLE catalog_imports (
        id TEXT PRIMARY KEY NOT NULL {_UUID},
        source_checksum TEXT NOT NULL CHECK (length(source_checksum) = 64
            AND source_checksum NOT GLOB '*[^0-9a-f]*'),
        imported_at TEXT NOT NULL,
        report_json TEXT NOT NULL CHECK (json_valid(report_json) AND json_type(report_json) = 'object')
    )""",
        "CREATE INDEX games_library_order ON games (provider_id, source_name, id)",
        "CREATE INDEX catalog_imports_source ON catalog_imports (source_checksum, imported_at, id)",
    ),
)
