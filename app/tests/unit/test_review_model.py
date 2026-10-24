from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from leo_kiosk.domain.errors import ConflictError, StorageError, ValidationError
from leo_kiosk.domain.reviews import HomeSlot, ReviewDraft, SelectionIntent
from leo_kiosk.domain.sessions import LaunchContext, LaunchOutcome, LaunchResult, LaunchRole


@pytest.mark.parametrize("rating", [None, 0, 1, 99, 100])
def test_review_names_and_rating_boundaries(rating):
    draft = ReviewDraft("  Étoiles 🐱  ", rating)
    assert draft.name == "Étoiles 🐱"
    assert draft.rating == rating
    assert draft.selection is SelectionIntent.KEEP
    assert len(ReviewDraft("é" * 80).name) == 80


@pytest.mark.parametrize("rating", [True, False, 0.0, 50.5, -1, 101, "50"])
def test_invalid_ratings(rating):
    with pytest.raises(ValidationError):
        ReviewDraft("Game", rating)


@pytest.mark.parametrize("name", [None, "", "  ", "é" * 81])
def test_invalid_names(name):
    with pytest.raises(ValidationError):
        ReviewDraft(name)


def test_selection_requires_domain_enum():
    with pytest.raises(ValidationError):
        ReviewDraft("Game", selection="select")
    assert ReviewDraft("Game", selection=SelectionIntent.SELECT).selection is SelectionIntent.SELECT


@pytest.mark.parametrize("position", [0, 10, True, 1.0, "1"])
def test_invalid_home_positions(position):
    with pytest.raises(ValidationError):
        HomeSlot(position)


def test_home_slots_are_exclusive_and_allow_empty():
    game = uuid4()
    assert HomeSlot(1).game_id is None
    assert HomeSlot(9, game_id=game).game_id == game
    assert HomeSlot(2, legacy_tile_id="draw").legacy_tile_id == "draw"
    for kwargs in [
        dict(game_id=game, legacy_tile_id="draw"),
        dict(game_id="pid-12"),
        dict(legacy_tile_id="  "),
    ]:
        with pytest.raises(ValidationError):
            HomeSlot(1, **kwargs)


def test_launch_roles_and_unique_ownership_tokens():
    game = uuid4()
    trial = LaunchContext(LaunchRole.REVIEW_TRIAL, game_id=game)
    assert trial.token != LaunchContext(LaunchRole.REVIEW_TRIAL, game_id=game).token
    assert LaunchContext(LaunchRole.CHILD_LEGACY, slot=9).game_id is None
    assert LaunchContext(LaunchRole.CHILD_GAME, game_id=game, slot=1).slot == 1
    for role, kwargs in [
        (LaunchRole.REVIEW_TRIAL, {}),
        (LaunchRole.REVIEW_TRIAL, dict(game_id=game, slot=1)),
        (LaunchRole.CHILD_GAME, dict(slot=1)),
        (LaunchRole.CHILD_LEGACY, dict(slot=True)),
        (LaunchRole.CHILD_LEGACY, dict(slot=1, game_id=game)),
    ]:
        with pytest.raises(ValidationError):
            LaunchContext(role, **kwargs)


def test_launch_history_uses_utc_and_never_carries_a_pid():
    context = LaunchContext(LaunchRole.REVIEW_TRIAL, game_id=uuid4())
    now = datetime.now(UTC)
    assert LaunchResult(context, LaunchOutcome.SPAWN_FAILED, None, now).started_at is None
    assert not hasattr(context, "pid")
    for start, end in [(now, now - timedelta(seconds=1)), (now.replace(tzinfo=None), now)]:
        with pytest.raises(ValidationError):
            LaunchResult(context, LaunchOutcome.EXITED, start, end)
    assert issubclass(ConflictError, Exception)
    assert issubclass(StorageError, Exception)
