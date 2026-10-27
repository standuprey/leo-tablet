"""Composition wiring: the builder must return what main() unpacks."""

import os
from pathlib import Path

import leo_kiosk.application as application
from leo_kiosk.application import _build_catalog_and_sessions
from leo_kiosk.storage.home import HomeRepository

# The deployed layout keeps the bootstrap next to the launcher (app/catalog on
# the device); the repo keeps it at the repo root, so point the module there.
REPO_BOOTSTRAP = Path(__file__).resolve().parents[3] / "catalog" / "bootstrap.json"
REPO_TILES = Path(__file__).resolve().parents[3] / "config" / "tiles.json"


def test_build_catalog_and_sessions_returns_wired_components(tmp_path, monkeypatch):
    """Guards the startup contract: main() unpacks three values from this call.

    A signature/return mismatch here previously passed every check and only
    surfaced on-device as 'catalog unavailable', silently disabling parent
    mode and the web UI.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(application, "BOOTSTRAP", REPO_BOOTSTRAP)
    monkeypatch.setattr(application, "CONFIG", str(REPO_TILES))
    catalog, sessions, db = _build_catalog_and_sessions()
    try:
        assert catalog is not None
        assert sessions is not None
        assert len(catalog.list_review_entries()) > 0
        # startup must seed the nine home slots: without them every parent
        # placement died with 'Home position not found' (on-device, 2026-10-26)
        slots = HomeRepository(db).slots()
        assert [s.position for s in slots] == list(range(1, 10))
        assert all(s.legacy_tile_id is not None for s in slots)
    finally:
        db.close()
    assert not os.path.exists(os.path.join(str(tmp_path), "nope"))