"""Version 7: the child profile (birthday) for age-based game filtering.

Exactly one row (id = 1); absent row = no birthday set yet. The ISO date
string is validated by the service layer before it lands here.
"""

from ..migrations import Migration

CHILD_PROFILE = Migration(
    7,
    (
        """CREATE TABLE child_profile (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        birthday TEXT NOT NULL CHECK (length(birthday) = 10)
    )""",
    ),
)
