#!/usr/bin/env python3
"""Generate/validate the versioned bootstrap catalog from flexible discovery input.

The original web-games.json is a temporary input with no fixed format. The
generated catalog/bootstrap.json is a replaceable deployment asset for fresh
installations; it is not the live datastore (SQLite is authoritative). Layout
follows domain DTOs: explicit unknown orientation, nullable dimensions with
required evidence, no legacy boolean/zero placeholders.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "web-games.json"
DEFAULT_OUTPUT = REPO_ROOT / "catalog" / "bootstrap.json"
DEFAULT_PROVENANCE = REPO_ROOT / "catalog" / "provenance.json"
BOOTSTRAP_VERSION = 1

# Provider display name -> stable slug (validated by the domain layer).
_PROVIDER_SLUGS = {
    "PBS Kids": "pbs-kids",
    "Starfall": "starfall",
    "ABCya": "abcya",
    "Sesame Street": "sesame-street",
    "Nat Geo Kids": "nat-geo-kids",
    "Code.org": "code-org",
    "Mystery Science": "mystery-science",
    "Cosmic Kids Yoga": "cosmic-kids-yoga",
    "Lumni Enfance": "lumni",
    "Okoo (France TV)": "okoo",
    "TFO": "tfo",
    "Hugo l'escargot": "hugo-l-escargot",
    "Boukili": "boukili",
    "Gulli": "gulli",
}

_TYPE_MAP = {"other": 0, "video": 1, "game": 2}

# Per-provider dimension evidence; see catalog/provenance.json dimension_caveats.
_PROVIDER_EVIDENCE = {
    "gulli": "popup",
    "starfall": "design",
    "lumni": "inferred",
}


def slugify(name):
    slug = _PROVIDER_SLUGS.get(name)
    if slug is None:
        raise ValueError(f"Unknown provider display name: {name!r}")
    return slug


def media_type(raw):
    if isinstance(raw, int):
        if raw not in _TYPE_MAP.values():
            raise ValueError(f"Invalid media type: {raw}")
        return raw
    if raw not in _TYPE_MAP:
        raise ValueError(f"Unknown media type label: {raw!r}")
    return _TYPE_MAP[raw]


def orientation(raw):
    """Legacy discovery booleans are orientation-unaware, not measured data."""
    if raw is None or isinstance(raw, bool):
        return "unknown"
    if raw in ("unknown", "landscape", "portrait", "square"):
        return raw
    raise ValueError(f"Invalid orientation: {raw!r}")


def dimensions(width, height, evidence):
    """Unknown size keeps null/null/unknown; a provided size needs evidence."""
    if width is None and height is None:
        return None
    if not (
        isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0
    ):
        raise ValueError(
            f"Dimensions must be two positive integers, got {width}x{height}"
        )
    if not evidence or evidence == "unknown":
        raise ValueError(
            "A provided size requires a non-unknown dimension evidence category"
        )
    if evidence not in ("design", "iframe", "popup", "inferred"):
        raise ValueError(f"Invalid dimension evidence: {evidence!r}")
    return {"width": width, "height": height, "evidence": evidence}


def adapt_provider(raw):
    provider_id = slugify(raw["name"])
    url = raw["url"]
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError(f"Provider website must be an HTTP(S) URL: {url!r}")
    return {"provider_id": provider_id, "name": raw["name"], "website_url": url}


def adapt_game(raw, provider_id, provider_evidence):
    source_url = raw["url"]
    if not isinstance(source_url, str) or not source_url.startswith(
        ("http://", "https://")
    ):
        raise ValueError(f"Game URL must be HTTP(S): {source_url!r}")
    name = raw["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Game name cannot be empty")
    width, height = raw.get("width"), raw.get("height")
    # Per-entry evidence wins over the provider-level default: a measured
    # canvas size (e.g. the Nat Geo fixed-size games) must survive a
    # provider that otherwise reports 'unknown'.
    entry_evidence = raw.get("dimension_evidence")
    evidence = entry_evidence if entry_evidence else provider_evidence
    dims = dimensions(
        width,
        height,
        evidence,
    )
    launch_url = raw.get("launch_url")
    if launch_url is None:
        # Trimmed discovery input: iframe_url is the playable surface the
        # review trial must test, so it becomes the launch override.
        launch_url = raw.get("iframe_url")
    if launch_url is not None and not (
        isinstance(launch_url, str) and launch_url.startswith(("http://", "https://"))
    ):
        raise ValueError(f"Launch override must be an HTTP(S) URL: {launch_url!r}")
    return {
        "provider_id": provider_id,
        "source_url": source_url,
        "source_name": name.strip(),
        "media_type": media_type(raw.get("type", raw.get("media_type", 2))),
        "orientation": orientation(raw.get("orientation", raw.get("is_landscape"))),
        "dimensions": dims,
        "launch_url": launch_url,
    }


def load_exclusions(provenance_path):
    """Provider-level and per-entry exclusions from the audited provenance."""
    exclusions = {"providers": set(), "entries": set()}
    if not provenance_path.exists():
        return exclusions
    prov = json.loads(provenance_path.read_text())
    for item in prov.get("provider_exclusions", []):
        exclusions["providers"].add(item["provider"])
    for item in prov.get("exclusions", []):
        if not item.get("eligible", True):
            exclusions["entries"].add((item["provider"], item["source_index"]))
    return exclusions


def build_bootstrap(source_path, provenance_path=DEFAULT_PROVENANCE):
    """Read flexible discovery input and emit a deterministic bootstrap dict."""
    raw = json.loads(source_path.read_bytes())
    exclusions = load_exclusions(provenance_path)
    providers, games, excluded = [], [], 0
    for group in raw:
        provider_id = slugify(group["name"])
        if provider_id in exclusions["providers"]:
            excluded += len(group.get("items", []))
            continue
        evidence = _PROVIDER_EVIDENCE.get(provider_id)
        provider_games = []
        for index, item in enumerate(group.get("items", [])):
            if (provider_id, index) in exclusions["entries"]:
                excluded += 1
                continue
            provider_games.append(adapt_game(item, provider_id, evidence))
        if provider_games or not group.get("items"):
            providers.append(adapt_provider(group))
        games.extend(provider_games)
    seen_urls = set()
    for game in games:
        key = (game["provider_id"], game["source_url"])
        if key in seen_urls:
            raise ValueError(f"Duplicate source identity: {key}")
        seen_urls.add(key)
    payload = {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "providers": sorted(providers, key=lambda p: p["provider_id"]),
        "games": sorted(games, key=lambda g: (g["provider_id"], g["source_url"])),
    }
    payload["source_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return payload, excluded


def validate_bootstrap(payload):
    """Structural self-check; jsonschema validation is a parent-13 import concern."""
    if not isinstance(payload, dict):
        return ["Bootstrap root must be an object"]
    errors = []
    version = payload.get("bootstrap_version")
    if version != BOOTSTRAP_VERSION:
        errors.append(
            f"Expected bootstrap_version {BOOTSTRAP_VERSION}, got {version!r}"
        )
    provider_ids = {p.get("provider_id") for p in payload.get("providers", [])}
    for p in payload.get("providers", []):
        if not all(k in p for k in ("provider_id", "name", "website_url")):
            errors.append(f"Provider missing required keys: {p!r}")
    seen = set()
    for game in payload.get("games", []):
        required = (
            "provider_id",
            "source_url",
            "source_name",
            "media_type",
            "orientation",
            "dimensions",
            "launch_url",
        )
        if not all(k in game for k in required):
            errors.append(f"Game missing required keys: {game!r}")
            continue
        if game["provider_id"] not in provider_ids:
            errors.append(f"Unknown provider: {game['provider_id']}")
        key = (game["provider_id"], game["source_url"])
        if key in seen:
            errors.append(f"Duplicate source identity: {key}")
        seen.add(key)
        if game["orientation"] == "unknown" and game["dimensions"] is None:
            pass  # Unknown orientation and unknown size are independently valid.
        elif game["dimensions"] is not None:
            d = game["dimensions"]
            if not all(k in d for k in ("width", "height", "evidence")):
                errors.append(f"Dimensions missing keys: {d!r}")
        if game["media_type"] not in (0, 1, 2):
            errors.append(f"Invalid media type: {game['media_type']}")
    expected = payload.get("source_sha256", "")
    body = {k: v for k, v in payload.items() if k != "source_sha256"}
    actual = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if expected != actual:
        errors.append(
            f"Checksum mismatch: expected {expected[:12]}…, computed {actual[:12]}…"
        )
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Discovery input; optional after initial migration",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--provenance",
        type=Path,
        default=DEFAULT_PROVENANCE,
        help="Audited exclusions; providers/entries listed there are dropped",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing output without rewriting it",
    )
    args = parser.parse_args(argv)
    if args.check:
        payload = json.loads(args.output.read_text())
        errors = validate_bootstrap(payload)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(
            f"OK: {args.output} ({len(payload.get('games', []))} games, "
            f"{len(payload.get('providers', []))} providers)"
        )
        return 0
    if not args.source.exists():
        print(f"Discovery source not found: {args.source}", file=sys.stderr)
        return 1
    payload, excluded = build_bootstrap(args.source, args.provenance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    )
    errors = validate_bootstrap(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Wrote {args.output} ({len(payload['games'])} games, "
        f"{len(payload['providers'])} providers, {excluded} excluded)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
