"""Version 9: per-game daily playtime for the "most played" parent ranking.

Derived usage data like `screen_time`: the controller records one finished
child session's seconds at exit, attributed to the game. Legacy tiles and
videos have no game identity and are not attributed (they already do not
count per-game; they only fill the daily budget).
"""

from ..migrations import Migration

GAME_PLAYTIME = Migration(
    9,
    (
        """CREATE TABLE game_playtime (
        day TEXT NOT NULL CHECK (length(day) = 10),
        game_id TEXT NOT NULL REFERENCES games(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        seconds INTEGER NOT NULL CHECK (seconds > 0),
        PRIMARY KEY (day, game_id)
    )""",
        "CREATE INDEX game_playtime_total ON game_playtime (game_id) "
        "WHERE seconds > 0",
        "CREATE INDEX game_playtime_day ON game_playtime (day, seconds DESC)",
    ),
)
