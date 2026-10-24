"""Ordered application schema; append versions, never edit an applied migration."""

from .v001_catalog import CATALOG
from .v002_state import STATE

MIGRATIONS = (CATALOG, STATE)
