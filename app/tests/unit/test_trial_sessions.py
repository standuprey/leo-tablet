"""In-view trial sessions: history, gesture outcomes, safety deadline."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.domain.sessions import LaunchOutcome
from leo_kiosk.services.sessions import TrialSessionService
from leo_kiosk.storage.database import open_database
from leo_kiosk.storage.schema import MIGRATIONS
from leo_kiosk.storage.sessions import SessionRepository


class Scheduler:
    """Records scheduled calls; fires them on demand."""

    def __init__(self):
        self.scheduled = []  # (seconds, fn)
        self.cancelled = []

    def call_later(self, seconds, fn):
        self.scheduled.append((seconds, fn))
        return len(self.scheduled)

    def cancel(self, handle):
        self.cancelled.append(handle)

    def fire(self, index):
        self.scheduled[index][1]()


@pytest.fixture
def db(tmp_path):
    with open_database(tmp_path / "s.sqlite3", migrations=MIGRATIONS) as connection:
        yield connection


def make_game(db, name: str) -> str:
    """A real games row: launch_sessions.game_id is a RESTRICT foreign key."""
    db.execute(
        "INSERT OR IGNORE INTO providers (id, name, website_url) "
        "VALUES ('test-provider', 'Test', 'https://example.org')"
    )
    game_id = str(uuid4())
    db.execute(
        "INSERT INTO games (id, provider_id, canonical_source_url, source_name, media_type) "
        "VALUES (?, 'test-provider', ?, ?, 2)",
        (game_id, f"https://example.org/{name.replace(' ', '-')}", name),
    )
    db.commit()
    return game_id


@pytest.fixture
def service(db):
    scheduler = Scheduler()
    finished = []
    svc = TrialSessionService(
        SessionRepository(db),
        call_later=scheduler.call_later,
        cancel_later=scheduler.cancel,
        on_finished=lambda token, game_id, outcome: finished.append((token, game_id, outcome)),
        clock=lambda: datetime.now(UTC),
        timeout_seconds=60,
    )
    svc._scheduler = scheduler
    svc._finished = finished
    return svc


def test_start_trial_records_history_and_schedules_the_deadline(service, db):
    game = make_game(db, "Game A")
    token = service.start_trial("https://games.example/x", game)
    assert service.active_tokens == (token,)
    assert service._scheduler.scheduled[0][0] == 60
    row = db.execute("SELECT game_id, role, ended_at FROM launch_sessions WHERE id = ?", (str(token),)).fetchone()
    assert row["game_id"] == str(game) and row["role"] == "review_trial"
    assert row["ended_at"] is None


def test_second_trial_while_one_runs_is_refused(service, db):
    service.start_trial("https://games.example/x", make_game(db, "Game A"))
    with pytest.raises(ValidationError):
        service.start_trial("https://games.example/y", make_game(db, "Game B"))


def test_stop_records_outcome_and_cancels_the_deadline(service, db):
    game = make_game(db, "Game A")
    token = service.start_trial("https://games.example/x", game)
    service.stop(token, LaunchOutcome.RETURN_GESTURE)
    assert service.active_tokens == ()
    assert service._scheduler.cancelled == [1]
    assert service._finished == [(token, game, LaunchOutcome.RETURN_GESTURE)]
    row = db.execute("SELECT outcome FROM launch_sessions WHERE id = ?", (str(token),)).fetchone()
    assert row["outcome"] == "return_gesture"


def test_deadline_ends_the_trial_as_timed_out(service, db):
    game = make_game(db, "Game A")
    token = service.start_trial("https://games.example/x", game)
    service._scheduler.fire(0)  # the deadline fires
    assert service.active_tokens == ()
    assert service._finished == [(token, game, LaunchOutcome.TIMED_OUT)]
    row = db.execute("SELECT outcome FROM launch_sessions WHERE id = ?", (str(token),)).fetchone()
    assert row["outcome"] == "timed_out"


def test_deadline_after_stop_is_a_noop(service, db):
    token = service.start_trial("https://games.example/x", make_game(db, "Game A"))
    service.stop(token, LaunchOutcome.PARENT_REQUEST)
    service._scheduler.fire(0)  # late deadline: token already gone
    assert service._finished and len(service._finished) == 1


def test_stop_with_unknown_token_is_ignored(service):
    service.stop(uuid4(), LaunchOutcome.RETURN_GESTURE)
    assert service._finished == []


def test_clock_drives_the_recorded_timestamps(service, db):
    start = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    state = {"now": start}
    service._clock = lambda: state["now"]
    game = make_game(db, "Game A")
    token = service.start_trial("https://games.example/x", game)
    state["now"] = start + timedelta(minutes=5)
    service.stop(token, LaunchOutcome.RETURN_GESTURE)
    row = db.execute("SELECT started_at, ended_at FROM launch_sessions WHERE id = ?", (str(token),)).fetchone()
    assert row["started_at"] == start.isoformat()
    assert row["ended_at"] == (start + timedelta(minutes=5)).isoformat()


# --- child game sessions ----------------------------------------------------
def test_start_child_game_records_role_slot_and_own_deadline():

    import tempfile
    from pathlib import Path

    from leo_kiosk.domain.sessions import LaunchOutcome, LaunchRole
    from leo_kiosk.services.sessions import TrialSessionService
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS
    from leo_kiosk.storage.sessions import SessionRepository

    tmp = Path(tempfile.mkdtemp())
    db = open_database(tmp / "c.sqlite3", MIGRATIONS)
    game_id = uuid4()
    from leo_kiosk.services.home_seed import seed_home

    tiles = {"title": "L", "columns": 3, "tiles": [
        {"id": f"tbd{p}", "label": "TBD", "color": "#454551",
         "cmd": ["~/kiosk/tbd"], "minutes": 20} for p in range(1, 10)]}
    tiles_path = tmp / "tiles.json"
    tiles_path.write_text(json.dumps(tiles))
    assert seed_home(db, tiles_path)
    db.execute(
        "INSERT INTO providers (id, name, website_url) VALUES ('p', 'P', 'https://p.example')"
    )
    db.execute(
        "INSERT INTO games (id, provider_id, canonical_source_url, source_name, media_type) "
        "VALUES (?, 'p', 'https://p.example/g', 'G', 2)",
        (str(game_id),),
    )
    repo = SessionRepository(db)
    timeouts = []
    finished = []
    service = TrialSessionService(
        repo,
        call_later=lambda s, fn: timeouts.append(s) or f"h{s}",
        cancel_later=lambda h: None,
        on_finished=lambda t, g, o: finished.append(o),
    )
    token = service.start_child_game("https://g.example", game_id, 3, 20)
    assert timeouts == [20 * 60]  # the tile's minutes, not the 30-min default
    row = repo.get_session(token)
    assert row["role"] == LaunchRole.CHILD_GAME.value and row["slot"] == 3
    assert row["game_id"] == str(game_id)

    # one session at a time
    import pytest

    from leo_kiosk.domain.errors import ValidationError

    with pytest.raises(ValidationError):
        service.start_child_game("https://g.example", game_id, 4, 20)

    service.stop(token, LaunchOutcome.RETURN_GESTURE)
    assert finished == [LaunchOutcome.RETURN_GESTURE]
    row = repo.get_session(token)
    assert row["ended_at"] is not None
    db.close()


def test_start_child_game_rejects_bad_minutes():
    import tempfile
    from pathlib import Path

    import pytest

    from leo_kiosk.domain.errors import ValidationError
    from leo_kiosk.services.sessions import TrialSessionService
    from leo_kiosk.storage.database import open_database
    from leo_kiosk.storage.schema import MIGRATIONS
    from leo_kiosk.storage.sessions import SessionRepository

    tmp = Path(tempfile.mkdtemp())
    db = open_database(tmp / "c.sqlite3", MIGRATIONS)
    service = TrialSessionService(SessionRepository(db))
    with pytest.raises(ValidationError):
        service.start_child_game("https://g.example", uuid4(), 1, 0)
    with pytest.raises(ValidationError):
        service.start_child_game("https://g.example", uuid4(), 1, 999)
    db.close()
