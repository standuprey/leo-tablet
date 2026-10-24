"""Route decisions per the architecture navigation table; pure, no GTK."""

from uuid import uuid4

import pytest

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.services.navigation import Route, enter_parent, return_gesture


def test_child_home_up_down_down_starts_parent_session():
    t = enter_parent(Route.CHILD_HOME)
    assert t.route is Route.PARENT_HOME and not t.stop_activity


def test_child_activity_gestures_stop_playback():
    assert enter_parent(Route.CHILD_ACTIVITY).route is Route.PARENT_HOME
    assert enter_parent(Route.CHILD_ACTIVITY).stop_activity is True
    back = return_gesture(Route.CHILD_ACTIVITY)
    assert back.route is Route.CHILD_HOME and back.stop_activity


def test_parent_home_return_goes_child_home_and_ends_session():
    t = return_gesture(Route.PARENT_HOME)
    assert t.route is Route.CHILD_HOME and t.end_parent_session


def test_review_list_returns_to_parent_home_both_ways():
    assert return_gesture(Route.REVIEW_LIST).route is Route.PARENT_HOME
    assert enter_parent(Route.REVIEW_LIST).route is Route.PARENT_HOME


def test_review_trial_return_opens_the_exact_game_editor():
    game = uuid4()
    t = return_gesture(Route.REVIEW_TRIAL, review_game_id=game)
    assert t.route is Route.REVIEW_EDITOR and t.stop_activity
    assert t.review_game_id == game
    with pytest.raises(ValidationError):
        return_gesture(Route.REVIEW_TRIAL)


def test_review_trial_parent_request_stops_and_returns_parent_home():
    t = enter_parent(Route.REVIEW_TRIAL)
    assert t.route is Route.PARENT_HOME and t.stop_activity


def test_dirty_editor_requires_confirmation_before_leaving():
    with pytest.raises(ValidationError):
        return_gesture(Route.REVIEW_EDITOR, editor_dirty=True)
    with pytest.raises(ValidationError):
        enter_parent(Route.REVIEW_EDITOR, editor_dirty=True)
    clean = enter_parent(Route.REVIEW_EDITOR, editor_dirty=False)
    assert clean.route is Route.PARENT_HOME and not clean.requires_confirmation
    # A clean editor leaving without confirmation still records the target.
    assert return_gesture(Route.REVIEW_EDITOR).route is Route.REVIEW_LIST


def test_wifi_returns_to_parent_home_and_portal_return_goes_to_wifi():
    assert return_gesture(Route.WIFI).route is Route.PARENT_HOME
    portal_back = return_gesture(Route.PORTAL)
    assert portal_back.route is Route.WIFI and portal_back.close_portal
    portal_up = enter_parent(Route.PORTAL)
    assert portal_up.route is Route.PARENT_HOME and portal_up.close_portal


def test_child_home_return_is_a_noop():
    t = return_gesture(Route.CHILD_HOME)
    assert t.route is Route.CHILD_HOME and not t.stop_activity and not t.end_parent_session
