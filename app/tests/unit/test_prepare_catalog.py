"""Bootstrap catalog generation; independent of the optional discovery file."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools" / "prepare_catalog.py"


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(TOOLS), *args], capture_output=True, text=True, cwd=cwd
    )


@pytest.fixture
def source(tmp_path):
    payload = [
        {
            "name": "PBS Kids",
            "url": "https://pbskids.org",
            "items": [
                {
                    "name": "Game A",
                    "url": "https://pbskids.org/a",
                    "type": "game",
                    "is_landscape": True,
                    "width": None,
                    "height": None,
                },
            ],
        },
        {
            "name": "Gulli",
            "url": "https://www.gulli.fr",
            "items": [
                {
                    "name": "Portrait",
                    "url": "https://jeux.gulli.fr/p/",
                    "type": "game",
                    "is_landscape": False,
                    "width": 600,
                    "height": 800,
                },
                {
                    "name": "Landscape",
                    "url": "https://jeux.gulli.fr/l/",
                    "type": "game",
                    "is_landscape": True,
                    "width": 800,
                    "height": 600,
                },
            ],
        },
    ]
    path = tmp_path / "source.json"
    path.write_text(json.dumps(payload))
    return path


def test_generated_bootstrap_uses_explicit_unknown_orientation(source, tmp_path):
    output = tmp_path / "bootstrap.json"
    result = run("--source", str(source), "--output", str(output))
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["bootstrap_version"] == 1
    assert {p["provider_id"] for p in payload["providers"]} == {"pbs-kids", "gulli"}
    by_name = {g["source_name"]: g for g in payload["games"]}
    # Legacy boolean is not measured orientation data.
    assert by_name["Game A"]["orientation"] == "unknown"
    assert by_name["Game A"]["dimensions"] is None
    # Gulli sizes carry popup evidence, not a game-canvas measurement.
    assert by_name["Portrait"]["dimensions"] == {"width": 600, "height": 800, "evidence": "popup"}
    assert by_name["Landscape"]["dimensions"] == {"width": 800, "height": 600, "evidence": "popup"}
    assert by_name["Portrait"]["orientation"] == "unknown"


def test_output_is_deterministic_across_runs(source, tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    run("--source", str(source), "--output", str(first))
    run("--source", str(source), "--output", str(second))
    assert first.read_bytes() == second.read_bytes()


def test_check_passes_on_committed_bootstrap():
    result = run("--check")
    assert result.returncode == 0, result.stderr
    assert "38 games" in result.stdout and "5 providers" in result.stdout


def copy_committed(tmp_path, name="bootstrap.json"):
    committed = Path(__file__).resolve().parents[3] / "catalog" / name
    output = tmp_path / name
    output.write_text(committed.read_text())
    return output


def test_check_detects_a_tampered_checksum(tmp_path):
    output = copy_committed(tmp_path)
    payload = json.loads(output.read_text())
    payload["games"][0]["source_name"] = "tampered"
    output.write_text(json.dumps(payload))
    result = run("--check", "--output", str(output))
    assert result.returncode == 1 and "Checksum mismatch" in result.stderr


def test_check_detects_duplicate_identity(tmp_path):
    output = copy_committed(tmp_path)
    payload = json.loads(output.read_text())
    payload["games"].append(dict(payload["games"][0]))
    output.write_text(json.dumps(payload))
    result = run("--check", "--output", str(output))
    assert result.returncode == 1 and "Duplicate source identity" in result.stderr


def test_check_detects_unknown_provider(tmp_path):
    output = copy_committed(tmp_path)
    payload = json.loads(output.read_text())
    payload["games"][0]["provider_id"] = "missing-provider"
    output.write_text(json.dumps(payload))
    result = run("--check", "--output", str(output))
    assert result.returncode == 1 and "Unknown provider" in result.stderr


@pytest.mark.parametrize(
    "source_payload",
    [
        [{"name": "Unknown Provider", "url": "https://x.example", "items": []}],
        [{"name": "PBS Kids", "url": "ftp://bad", "items": []}],
        [
            {
                "name": "PBS Kids",
                "url": "https://pbskids.org",
                "items": [{"name": "G", "url": "https://pbskids.org/g", "type": "puzzle"}],
            }
        ],
        [
            {
                "name": "PBS Kids",
                "url": "https://pbskids.org",
                "items": [
                    {"name": "G", "url": "https://pbskids.org/g", "type": "game", "width": 800}
                ],
            },
        ],
    ],
)
def test_unmappable_source_values_are_rejected(source_payload, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(source_payload))
    result = run("--source", str(path), "--output", str(tmp_path / "out.json"))
    assert result.returncode == 1


def test_sizes_without_evidence_rejected(tmp_path):
    # Gulli items inherit the provider-level popup caveat; a provider without
    # any recorded evidence caveat must reject unattributed sizes.
    payload = [
        {
            "name": "PBS Kids",
            "url": "https://pbskids.org",
            "items": [
                {
                    "name": "X",
                    "url": "https://pbskids.org/x/",
                    "type": "game",
                    "width": 800,
                    "height": 600,
                }
            ],
        }
    ]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    result = run("--source", str(path), "--output", str(tmp_path / "out.json"))
    assert result.returncode == 1 and "evidence" in result.stderr


def test_lumni_inferred_evidence_in_committed_bootstrap():
    payload = json.loads(
        (Path(__file__).resolve().parents[3] / "catalog" / "bootstrap.json").read_text()
    )
    lumni = [g for g in payload["games"] if g["provider_id"] == "lumni"]
    assert lumni, "Lumni games missing from committed bootstrap"
    assert all(g["dimensions"]["evidence"] == "inferred" for g in lumni if g["dimensions"])
    starfall = [g for g in payload["games"] if g["provider_id"] == "starfall"]
    assert all(g["dimensions"]["evidence"] == "design" for g in starfall if g["dimensions"])
