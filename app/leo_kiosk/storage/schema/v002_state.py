"""Version 2: home assignments and launch/review history; catalog stays authoritative."""

from ..migrations import Migration

_UUID = """CHECK (length(id) = 36
    AND id GLOB '????????-????-????-????-????????????'
    AND length(replace(id, '-', '')) = 32
    AND replace(id, '-', '') NOT GLOB '*[^0-9a-f]*')"""

STATE = Migration(
    2,
    (
        """CREATE TABLE home_slots (
        position INTEGER PRIMARY KEY CHECK (position BETWEEN 1 AND 9),
        game_id TEXT REFERENCES games(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        legacy_tile_id TEXT CHECK (legacy_tile_id IS NULL OR length(trim(legacy_tile_id)) > 0),
        legacy_tile_json TEXT CHECK (legacy_tile_json IS NULL OR (
            json_valid(legacy_tile_json) AND json_type(legacy_tile_json) = 'object')),
        CHECK ((game_id IS NULL) != (legacy_tile_id IS NULL)),
        UNIQUE (game_id)
    )""",
        f"""CREATE TABLE launch_sessions (
        id TEXT PRIMARY KEY NOT NULL {_UUID},
        game_id TEXT REFERENCES games(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        slot INTEGER REFERENCES home_slots(position) ON UPDATE RESTRICT ON DELETE RESTRICT,
        role TEXT NOT NULL CHECK (role IN ('child_game', 'child_legacy', 'review_trial')),
        started_at TEXT,
        ended_at TEXT,
        outcome TEXT CHECK (outcome IS NULL OR outcome IN (
            'exited', 'return_gesture', 'parent_request', 'timed_out',
            'spawn_failed', 'crashed', 'abandoned')),
        failure_reason TEXT CHECK (failure_reason IS NULL OR length(failure_reason) <= 500),
        CHECK (
            CASE role
                WHEN 'review_trial' THEN game_id IS NOT NULL AND slot IS NULL
                WHEN 'child_game' THEN game_id IS NOT NULL AND slot IS NOT NULL
                ELSE game_id IS NULL AND slot IS NOT NULL
            END
        ),
        CHECK (ended_at IS NULL OR started_at IS NOT NULL),
        CHECK ((outcome IS NULL) = (ended_at IS NULL))
    )""",
        f"""CREATE TABLE review_events (
        id TEXT PRIMARY KEY NOT NULL {_UUID},
        game_id TEXT NOT NULL REFERENCES games(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        event_kind TEXT NOT NULL CHECK (event_kind IN (
            'tested', 'reviewed', 'selected', 'unselected', 'deleted', 'restored')),
        timestamp TEXT NOT NULL,
        change_json TEXT NOT NULL CHECK (
            json_valid(change_json) AND json_type(change_json) = 'object')
    )""",
        # Seeded rows are updated, never deleted; SQLite FKs alone cannot enforce this.
        "CREATE TRIGGER home_slots_no_delete BEFORE DELETE ON home_slots BEGIN "
        "SELECT RAISE(ABORT, 'home_slots rows are seeded and never deleted'); END",
        "CREATE INDEX launch_sessions_game ON launch_sessions (game_id, started_at, id)",
        "CREATE INDEX launch_sessions_unfinished ON launch_sessions (ended_at) "
        "WHERE ended_at IS NULL",
        "CREATE INDEX review_events_game ON review_events (game_id, timestamp, id)",
    ),
)
