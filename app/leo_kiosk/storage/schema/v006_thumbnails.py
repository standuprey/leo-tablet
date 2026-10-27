"""Version 6: per-game trial screenshots for home-tile art.

One row per game, latest capture wins (PK on game_id, upsert). The PNG
itself lives in the filesystem thumbs directory; the row is the authority
that a thumbnail exists. Rows are derived data: deleting the game cascades
here, unlike home_slots whose rows are seeded structure.
"""

from ..migrations import Migration

THUMBNAILS = Migration(
    6,
    (
        """CREATE TABLE game_thumbnails (
        game_id TEXT PRIMARY KEY NOT NULL REFERENCES games(id)
            ON UPDATE RESTRICT ON DELETE CASCADE,
        taken_at TEXT NOT NULL CHECK (length(taken_at) > 0)
    )""",
    ),
)
