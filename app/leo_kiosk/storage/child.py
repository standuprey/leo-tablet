"""Child profile persistence: one birthday row, no policy."""

import sqlite3
from datetime import date


class ChildRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def birthday(self) -> date | None:
        row = self._connection.execute(
            "SELECT birthday FROM child_profile WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return date.fromisoformat(row[0])

    def set_birthday(self, birthday: date) -> None:
        """Raw write; the caller owns the transaction (upsert, single row)."""
        self._connection.execute(
            "INSERT INTO child_profile (id, birthday) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET birthday = excluded.birthday",
            (birthday.isoformat(),),
        )

    def screen_time_minutes(self) -> int | None:
        """The daily limit; None row or NULL column means no limit."""
        row = self._connection.execute(
            "SELECT screen_time_minutes FROM child_profile WHERE id = 1"
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    def set_screen_time(self, minutes: int | None) -> None:
        """Raw write; requires the birthday row (My Child creates it first)."""
        self._connection.execute(
            "UPDATE child_profile SET screen_time_minutes = ? WHERE id = 1",
            (minutes,),
        )


class ScreenTimeRepository:
    """Used screen-time seconds per local day; raw writes, service-owned tx."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def used_seconds(self, day: str) -> int:
        row = self._connection.execute(
            "SELECT seconds FROM screen_time WHERE day = ?", (day,)
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def add_seconds(self, day: str, seconds: int) -> None:
        self._connection.execute(
            "INSERT INTO screen_time (day, seconds) VALUES (?, ?) "
            "ON CONFLICT (day) DO UPDATE SET seconds = seconds + excluded.seconds",
            (day, seconds),
        )


class GamePlaytimeRepository:
    """Per-game daily playtime seconds; raw writes, service-owned tx.

    The ranking is all-time totals (never game-deleted, FK RESTRICT);
    the per-day split stays available for later "played today" views.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def most_played(self, limit: int = 10) -> list[sqlite3.Row]:
        """Games ranked by total recorded seconds, most played first."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Playtime ranking limit must be 1-100")
        return list(
            self._connection.execute(
                "SELECT game_id, sum(seconds) AS seconds "
                "FROM game_playtime GROUP BY game_id "
                "ORDER BY seconds DESC, game_id LIMIT ?",
                (limit,),
            )
        )

    def add_seconds(self, day: str, game_id: str, seconds: int) -> None:
        self._connection.execute(
            "INSERT INTO game_playtime (day, game_id, seconds) VALUES (?, ?, ?) "
            "ON CONFLICT (day, game_id) DO UPDATE SET seconds = seconds + excluded.seconds",
            (day, game_id, seconds),
        )
