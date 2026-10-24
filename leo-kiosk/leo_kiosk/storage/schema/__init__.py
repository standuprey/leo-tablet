"""Ordered application schema; append versions, never edit an applied migration."""

from .v001_catalog import CATALOG

MIGRATIONS = (CATALOG,)
