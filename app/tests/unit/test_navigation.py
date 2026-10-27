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


# --- My Child: birthday validation, age math, age matching ------------------
def test_parse_birthday_accepts_a_real_past_date():
    from datetime import date

    from leo_kiosk.services.child import parse_birthday

    today = date(2026, 10, 26)
    assert parse_birthday(5, 3, 2020, today) == date(2020, 3, 5)


def test_parse_birthday_rejects_incomplete_or_impossible_dates():
    from datetime import date

    import pytest

    from leo_kiosk.domain.errors import ValidationError
    from leo_kiosk.services.child import parse_birthday

    today = date(2026, 10, 26)
    with pytest.raises(ValidationError, match="day, month and year"):
        parse_birthday(5, None, 2020, today)
    with pytest.raises(ValidationError, match="not a real date"):
        parse_birthday(31, 2, 2020, today)


def test_parse_birthday_rejects_future_and_too_old():
    from datetime import date

    import pytest

    from leo_kiosk.domain.errors import ValidationError
    from leo_kiosk.services.child import parse_birthday

    today = date(2026, 10, 26)
    with pytest.raises(ValidationError, match="future"):
        parse_birthday(1, 1, 2027, today)
    with pytest.raises(ValidationError, match="older than 17"):
        parse_birthday(1, 1, 2000, today)


def test_age_years_counts_completed_years():
    from datetime import date

    from leo_kiosk.services.child import age_years

    assert age_years(date(2020, 3, 5), date(2026, 3, 4)) == 5
    assert age_years(date(2020, 3, 5), date(2026, 3, 5)) == 6
    assert age_years(date(2026, 1, 1), date(2026, 10, 26)) == 0


def test_matches_age_open_bounds_and_exact_fit():
    from leo_kiosk.services.child import matches_age

    assert matches_age(4, 7, 5) is True
    assert matches_age(4, 7, 8) is False
    assert matches_age(None, 6, 3) is True  # open lower bound
    assert matches_age(4, None, 9) is True  # open upper bound
    assert matches_age(None, None, 5) is True  # unknown; caller buckets it


def test_screen_time_service_records_and_computes_remaining():
    from datetime import datetime, timedelta

    from leo_kiosk.services.child import (
        ScreenTimeService,
    )
    from leo_kiosk.storage.child import ChildRepository, ScreenTimeRepository
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    with open_database(MIGRATIONS=MIGRATIONS) if False else _tmp_db() as db:
        limits = ChildRepository(db)
        usage_repo = ScreenTimeRepository(db)
        service = ScreenTimeService(limits, usage_repo)
        now = datetime(2026, 10, 26, 15, 0, 0)

        from datetime import date

        from leo_kiosk.services.child import ChildService

        ChildService(limits).set_birthday(date(2021, 1, 1))  # creates the row

        assert service.limit() is None
        service.set_limit(30)
        assert service.limit() == 30
        assert service.remaining_minutes(now) == 30
        assert service.blocked(now) is False

        service.record(10 * 60 + 30, now)  # 10.5 minutes, rounds to 11
        assert service.used_seconds(now) == 630
        assert service.remaining_minutes(now) == 19

        service.record(0, now)  # a no-op exit adds nothing
        assert service.used_seconds(now) == 630

        # yesterday's usage does not count: the budget resets every day
        tomorrow = now + timedelta(days=1)
        assert service.remaining_minutes(tomorrow) == 30

        # limit 0 blocks immediately
        service.set_limit(0)
        assert service.blocked(now) is True

        # clearing the limit removes the timer entirely
        service.set_limit(None)
        assert service.remaining_minutes(now) is None
        assert service.blocked(now) is False


def _tmp_db():
    import contextlib
    import tempfile
    from pathlib import Path

    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS

    @contextlib.contextmanager
    def ctx():
        tmp = tempfile.mkdtemp()
        db = open_database(Path(tmp) / "c.sqlite3", MIGRATIONS)
        try:
            yield db
        finally:
            db.close()

    return ctx()


def test_parse_screen_time():
    import pytest

    from leo_kiosk.domain.errors import ValidationError
    from leo_kiosk.services.child import _parse_screen_time

    assert _parse_screen_time("") is None
    assert _parse_screen_time(" 0 ") == 0
    assert _parse_screen_time("120") == 120
    with pytest.raises(ValidationError, match="between 0 and 600"):
        _parse_screen_time("601")
    with pytest.raises(ValidationError, match="number of minutes"):
        _parse_screen_time("abc")
