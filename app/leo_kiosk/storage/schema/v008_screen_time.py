"""Version 8: daily screen time — the parent's limit and the used budget.

`child_profile.screen_time_minutes` is the parent-set daily limit (NULL =
no limit; 0 = blocked all day). `screen_time` accumulates used seconds per
local day; rows are derived usage data, one per day, added on app exit.
"""

from ..migrations import Migration

SCREEN_TIME = Migration(
    8,
    (
        """ALTER TABLE child_profile ADD COLUMN screen_time_minutes INTEGER
        CHECK (screen_time_minutes IS NULL OR screen_time_minutes BETWEEN 0 AND 600)""",
        """CREATE TABLE screen_time (
        day TEXT PRIMARY KEY CHECK (length(day) = 10),
        seconds INTEGER NOT NULL CHECK (seconds >= 0)
    )""",
    ),
)
