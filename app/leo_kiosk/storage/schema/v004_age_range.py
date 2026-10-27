"""Version 4: parent-recorded recommended age range on games.

Two nullable columns; the both-or-neither and min<=max invariants live in the
domain (AgeRange) because ADD COLUMN can only carry single-column CHECKs.
"""

from ..migrations import Migration

_AGE_CHECK = (
    "CHECK ({column} IS NULL OR (typeof({column}) = 'integer' "
    "AND {column} BETWEEN 1 AND 17))"
)

AGE_RANGE = Migration(
    4,
    (
        f"ALTER TABLE games ADD COLUMN age_min INTEGER {_AGE_CHECK.format(column='age_min')}",
        f"ALTER TABLE games ADD COLUMN age_max INTEGER {_AGE_CHECK.format(column='age_max')}",
    ),
)
