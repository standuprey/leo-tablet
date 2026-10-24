"""Ordered application schema; append versions, never edit an applied migration."""

from .v001_catalog import CATALOG
from .v002_state import STATE
from .v003_empty_slots import EMPTY_SLOTS

MIGRATIONS = (CATALOG, STATE, EMPTY_SLOTS)
