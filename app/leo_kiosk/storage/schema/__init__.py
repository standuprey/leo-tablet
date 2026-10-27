"""Ordered application schema; append versions, never edit an applied migration."""

from .v001_catalog import CATALOG
from .v002_state import STATE
from .v003_empty_slots import EMPTY_SLOTS
from .v004_age_range import AGE_RANGE
from .v005_star_rating import STAR_RATING
from .v006_thumbnails import THUMBNAILS
from .v007_child_profile import CHILD_PROFILE
from .v008_screen_time import SCREEN_TIME
from .v009_game_playtime import GAME_PLAYTIME

MIGRATIONS = (
    CATALOG,
    STATE,
    EMPTY_SLOTS,
    AGE_RANGE,
    STAR_RATING,
    THUMBNAILS,
    CHILD_PROFILE,
    SCREEN_TIME,
    GAME_PLAYTIME,
)
