"""Version 3: home_slots may be empty (both columns NULL).

The v002 CHECK `(game_id IS NULL) != (legacy_tile_id IS NULL)` rejected the
empty-slot state the architecture requires after unselect/move. SQLite cannot
alter a CHECK constraint, so both tables rebuild; data is preserved in order.
launch_sessions rebuilds too because its FK targets home_slots(position) and
DROP TABLE runs an implicit DELETE that RESTRICT children would block.
"""

from ..migrations import Migration

_UUID = """CHECK (length(id) = 36
    AND id GLOB '????????-????-????-????-????????????'
    AND length(replace(id, '-', '')) = 32
    AND replace(id, '-', '') NOT GLOB '*[^0-9a-f]*')"""

_SESSION_COLUMNS = """id, game_id, slot, role, started_at, ended_at, outcome, failure_reason"""

EMPTY_SLOTS = Migration(
    3,
    (
        """CREATE TABLE home_slots_v3 (
        position INTEGER PRIMARY KEY CHECK (position BETWEEN 1 AND 9),
        game_id TEXT REFERENCES games(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        legacy_tile_id TEXT CHECK (legacy_tile_id IS NULL OR length(trim(legacy_tile_id)) > 0),
        legacy_tile_json TEXT CHECK (legacy_tile_json IS NULL OR (
            json_valid(legacy_tile_json) AND json_type(legacy_tile_json) = 'object')),
        CHECK (NOT (game_id IS NOT NULL AND legacy_tile_id IS NOT NULL)),
        UNIQUE (game_id)
    )""",
        "INSERT INTO home_slots_v3 (position, game_id, legacy_tile_id, legacy_tile_json) "
        "SELECT position, game_id, legacy_tile_id, legacy_tile_json FROM home_slots",
        f"""CREATE TABLE launch_sessions_v3 (
        id TEXT PRIMARY KEY NOT NULL {_UUID},
        game_id TEXT REFERENCES games(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        slot INTEGER REFERENCES home_slots_v3(position) ON UPDATE RESTRICT ON DELETE RESTRICT,
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
        f"INSERT INTO launch_sessions_v3 ({_SESSION_COLUMNS}) "
        f"SELECT {_SESSION_COLUMNS} FROM launch_sessions",
        "DROP TABLE launch_sessions",
        "DROP TABLE home_slots",
        "ALTER TABLE home_slots_v3 RENAME TO home_slots",
        "ALTER TABLE launch_sessions_v3 RENAME TO launch_sessions",
        # The delete-blocking trigger belonged to the old table; recreate it.
        "CREATE TRIGGER home_slots_no_delete BEFORE DELETE ON home_slots BEGIN "
        "SELECT RAISE(ABORT, 'home_slots rows are seeded and never deleted'); END",
        "CREATE INDEX launch_sessions_game ON launch_sessions (game_id, started_at, id)",
        "CREATE INDEX launch_sessions_unfinished ON launch_sessions (ended_at) "
        "WHERE ended_at IS NULL",
    ),
)
