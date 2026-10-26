"""Videos screen data logic: catalog validation, sampling, labels (no GTK)."""

import json
import random

import pytest

from leo_kiosk.ui.videos_window import load_videos, sample_videos, tile_label


def write_catalog(tmp_path, entries):
    path = tmp_path / "kiosk_videos.json"
    path.write_text(json.dumps(entries))
    return str(path)


VALID = {
    "channel": "SciShow Kids",
    "title": "The Biggest Volcano Ever is in Space! | SciShow Kids",
    "minutes": 5.8,
    "watch_url": "https://www.youtube.com/watch?v=8qdYCpSW2eY",
    "embed_url": "https://www.youtube.com/embed/8qdYCpSW2eY",
}


def test_load_videos_accepts_valid_catalog(tmp_path):
    videos = load_videos(write_catalog(tmp_path, [VALID, dict(VALID, title="Second")]))
    assert [str(v["title"]) for v in videos] == [
        "The Biggest Volcano Ever is in Space! | SciShow Kids",
        "Second",
    ]


@pytest.mark.parametrize(
    "entry",
    [
        {},
        dict(VALID, title=""),
        dict(VALID, title=None),
        dict(VALID, embed_url="ftp://example.org/video"),
        dict(VALID, embed_url=None),
    ],
)
def test_load_videos_rejects_malformed_entries(tmp_path, entry):
    with pytest.raises(ValueError):
        load_videos(write_catalog(tmp_path, [entry]))


def test_load_videos_rejects_empty_and_non_list(tmp_path):
    with pytest.raises(ValueError):
        load_videos(write_catalog(tmp_path, []))
    with pytest.raises(ValueError):
        path = tmp_path / "kiosk_videos.json"
        path.write_text("not json")
        load_videos(str(path))


def test_sample_videos_picks_unique_subset_without_replacement():
    videos = [dict(VALID, title=f"Video {i}") for i in range(20)]
    picks = sample_videos(videos, random.Random(7))
    assert len(picks) == 9
    assert len({str(v["title"]) for v in picks}) == 9
    again = sample_videos(videos, random.Random(7))
    assert again == picks


def test_sample_videos_with_fewer_entries_than_slots(tmp_path):
    videos = [dict(VALID, title="Only one")]
    assert sample_videos(videos, random.Random(1)) == videos



def test_tile_label_cuts_at_pipe_trims_ascii_and_caps_length():
    assert tile_label({"title": "The Biggest Volcano | SciShow Kids"}) == "The Biggest Volcano"
    assert tile_label({"title": "Caf\u00e9 \u2728 Fun day"}) == "Caf Fun day"
    assert tile_label({"title": "  a   b  "}) == "a b"
    assert tile_label({"title": "x" * 100}) == "x" * 69 + "..."
    assert tile_label({"title": "\u2728 \u00e9\u00e9\u00e9 | ch"}) == "..."
    assert tile_label({}) == "..."