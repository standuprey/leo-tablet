"""Composition wiring: the builder must return what main() unpacks."""

import os
from pathlib import Path

import leo_kiosk.application as application
from leo_kiosk.application import _build_catalog_and_sessions

# The deployed layout keeps the bootstrap next to the launcher (app/catalog on
# the device); the repo keeps it at the repo root, so point the module there.
REPO_BOOTSTRAP = Path(__file__).resolve().parents[3] / "catalog" / "bootstrap.json"


def test_build_catalog_and_sessions_returns_wired_components(tmp_path, monkeypatch):
    """Guards the startup contract: main() unpacks four values from this call.

    A signature/return mismatch here previously passed every check and only
    surfaced on-device as 'catalog unavailable', silently disabling parent
    mode and the web UI.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(application, "BOOTSTRAP", REPO_BOOTSTRAP)
    catalog, sessions, profiles, db = _build_catalog_and_sessions()
    try:
        assert catalog is not None
        assert sessions is not None
        assert profiles is not None
        assert len(catalog.list_review_entries()) > 0
    finally:
        db.close()
    assert not os.path.exists(os.path.join(str(tmp_path), "nope"))