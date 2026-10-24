"""Bootstrap source adapter: checksum gate, version gate, flattening."""

import json
from pathlib import Path

import pytest

from leo_kiosk.adapters.catalog_source import BootstrapCatalogSource
from leo_kiosk.domain.errors import ValidationError


def write_bootstrap(tmp_path, payload):
    body = {k: v for k, v in payload.items() if k != "source_sha256"}
    import hashlib

    payload = dict(payload)
    payload["source_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    path = tmp_path / "bootstrap.json"
    path.write_text(json.dumps(payload))
    return path


def payload():
    return {
        "bootstrap_version": 1,
        "providers": [{"provider_id": "pbs", "name": "PBS", "website_url": "https://pbskids.org"}],
        "games": [
            {
                "provider_id": "pbs",
                "source_url": "https://pbskids.org/g",
                "source_name": "G",
                "media_type": 2,
                "orientation": "unknown",
                "dimensions": None,
                "launch_url": None,
            }
        ],
    }


def test_valid_bootstrap_flattens_dimensions(tmp_path):
    path = write_bootstrap(tmp_path, payload())
    source = BootstrapCatalogSource(path)
    assert source.providers[0]["provider_id"] == "pbs"
    game = source.games[0]
    assert game["width"] is None and game["height"] is None
    assert game["dimension_evidence"] == "unknown"


def test_tampered_checksum_is_rejected(tmp_path):
    path = write_bootstrap(tmp_path, payload())
    tampered = json.loads(path.read_text())
    tampered["games"][0]["source_name"] = "changed"
    path.write_text(json.dumps(tampered))
    with pytest.raises(ValidationError, match="checksum"):
        BootstrapCatalogSource(path)


def test_unsupported_version_is_rejected(tmp_path):
    bad = payload() | {"bootstrap_version": 99}
    path = write_bootstrap(tmp_path, bad)
    with pytest.raises(ValidationError, match="version"):
        BootstrapCatalogSource(path)


def test_committed_bootstrap_loads():
    path = Path(__file__).resolve().parents[3] / "catalog" / "bootstrap.json"
    source = BootstrapCatalogSource(path)
    assert len(source.games) == 97 and len(source.providers) == 13
