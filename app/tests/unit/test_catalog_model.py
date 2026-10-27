from dataclasses import FrozenInstanceError

import pytest

from leo_kiosk.domain.catalog import (
    CatalogItem,
    DimensionEvidence,
    Dimensions,
    MediaType,
    Orientation,
    canonicalize_url,
    stable_game_id,
)
from leo_kiosk.domain.errors import ValidationError


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "HTTPS://Example.COM:443/Game?x=1&x=2#Level-A",
            "https://example.com/Game?x=1&x=2#Level-A",
        ),
        ("http://Example.com:80?", "http://example.com?"),
        ("https://example.com?#", "https://example.com?#"),
        ("https://example.com:8443/A%2fb?q=%2F#", "https://example.com:8443/A%2fb?q=%2F#"),
        ("http://[2001:DB8::1]:80/game", "http://[2001:db8::1]/game"),
        ("https://BÜCHER.de/é", "https://bücher.de/é"),
        ("https://faß.de/game", "https://faß.de/game"),
    ],
)
def test_conservative_url_normalization(source, expected):
    assert canonicalize_url(source) == expected
    assert canonicalize_url(expected) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "javascript:alert(1)",
        "file:///tmp/game",
        "https:///game",
        "//example.com/game",
        "https://user:password@example.com",
        "https://@example.com",
        "https://example.com:0",
        "https://example.com:65536",
        "https://example.com:",
        "https://bad..example/game",
        " https://example.com",
        "https://example.com/\n",
        "https://example.com/\x00",
        "https://example.com/\u200b",
        "https://example.com/a b",
        "https://bad_host/game",
        "https://[::1",
        "https://[::1]garbage/game",
        "https://[v1.host]/",
        "https://[fe80::1%25eth0]/",
        "https://example.com\\evil/game",
        None,
        2,
    ],
)
def test_unsafe_urls_are_rejected(value):
    with pytest.raises(ValidationError):
        canonicalize_url(value)


def test_stable_identity_preserves_provider_query_fragment_and_path_case():
    original = stable_game_id("pbs-kids", "HTTPS://EXAMPLE.COM:443/Game?id=1#A")
    assert original == stable_game_id("pbs-kids", "https://example.com/Game?id=1#A")
    for provider, url in [
        ("other", "https://example.com/Game?id=1#A"),
        ("pbs-kids", "https://example.com/game?id=1#A"),
        ("pbs-kids", "https://example.com/Game?id=2#A"),
        ("pbs-kids", "https://example.com/Game?id=1#B"),
    ]:
        assert stable_game_id(provider, url) != original
    with pytest.raises(ValidationError):
        stable_game_id("PBS Kids", "https://example.com")


def test_unknown_orientation_is_not_measured_portrait():
    item = CatalogItem("pbs-kids", "https://example.com", "Game", MediaType.GAME)
    assert item.orientation is Orientation.UNKNOWN
    assert item.dimensions.width is None
    assert not item.dimensions.describes_game_size
    assert item.playable_url == item.source_url
    with pytest.raises(FrozenInstanceError):
        item.source_name = "changed"


@pytest.mark.parametrize(
    ("width", "height"), [(0, 0), (1, None), (None, 1), (True, 100), (100, 2.0), (-1, 3)]
)
def test_invalid_dimensions(width, height):
    with pytest.raises(ValidationError):
        Dimensions(width, height, DimensionEvidence.DESIGN)


def test_popup_size_is_not_game_resolution_and_launch_override_keeps_identity():
    size = Dimensions(800, 600, DimensionEvidence.POPUP)
    assert not size.describes_game_size
    assert Dimensions(1024, 768, DimensionEvidence.DESIGN).describes_game_size
    item = CatalogItem(
        "gulli",
        "https://EXAMPLE.com/game",
        "Title",
        MediaType.GAME,
        dimensions=size,
        launch_url="https://cdn.example.com/run#start",
    )
    assert item.game_id == stable_game_id("gulli", "https://example.com/game")
    assert item.playable_url == "https://cdn.example.com/run#start"


@pytest.mark.parametrize(
    "kwargs", [{"media_type": 2}, {"orientation": False}, {"source_name": "  "}, {"dimensions": {}}]
)
def test_catalog_contracts(kwargs):
    fields = dict(
        provider_id="pbs",
        source_url="https://example.com",
        source_name="A",
        media_type=MediaType.GAME,
    )
    fields.update(kwargs)
    with pytest.raises(ValidationError):
        CatalogItem(**fields)


# --- fit_scale: verified design size -> whole-page zoom ---------------------
def test_fit_scale_needs_verified_design_evidence():
    from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions

    unknown = Dimensions()
    assert unknown.fit_scale(1280, 1920) is None  # no size at all
    # non-design evidence (measured differently) is not trusted for scaling
    guessed = Dimensions(1024, 768, DimensionEvidence.POPUP)
    assert guessed.fit_scale(1280, 1920) is None


def test_fit_scale_fills_the_larger_axis():
    from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions

    beetle = Dimensions(1024, 768, DimensionEvidence.DESIGN)
    assert beetle.fit_scale(1280, 1920) == 1.25  # width-limited
    assert beetle.fit_scale(1024, 768) == 1.0  # exact fit
    portrait = Dimensions(768, 1024, DimensionEvidence.DESIGN)
    assert portrait.fit_scale(1280, 1920) == 1280 / 768  # width-limited again


def test_fit_scale_clamps_extreme_scales():
    from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions

    huge = Dimensions(3000, 2000, DimensionEvidence.DESIGN)
    assert huge.fit_scale(1280, 1920) == 0.5  # never smaller than half
    tiny = Dimensions(100, 100, DimensionEvidence.DESIGN)
    assert tiny.fit_scale(1280, 1920) == 3.0  # never more than 3x


def test_fit_scale_needs_a_known_viewport():
    from leo_kiosk.domain.catalog import DimensionEvidence, Dimensions

    beetle = Dimensions(1024, 768, DimensionEvidence.DESIGN)
    assert beetle.fit_scale(0, 0) is None
