"""Version 5: three-dimensional five-star parent rating.

production/education/fun, each 0-5, nullable (unrated). The legacy 0-100
`rating` column stays but is no longer written.
"""

from ..migrations import Migration

_STAR_CHECK = (
    "CHECK ({column} IS NULL OR (typeof({column}) = 'integer' "
    "AND {column} BETWEEN 0 AND 5))"
)

STAR_RATING = Migration(
    5,
    (
        f"ALTER TABLE games ADD COLUMN prod_stars INTEGER {_STAR_CHECK.format(column='prod_stars')}",
        f"ALTER TABLE games ADD COLUMN edu_stars INTEGER {_STAR_CHECK.format(column='edu_stars')}",
        f"ALTER TABLE games ADD COLUMN fun_stars INTEGER {_STAR_CHECK.format(column='fun_stars')}",
    ),
)
