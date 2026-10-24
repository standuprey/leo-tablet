"""Profiles, Firefox argv, and the token-owned trial session lifecycle."""

from pathlib import Path
from uuid import uuid4

import pytest

from leo_kiosk.adapters.browser_profiles import BrowserProfiles
from leo_kiosk.adapters.firefox import build_firefox_command
from leo_kiosk.domain.catalog import CatalogItem, MediaType
from leo_kiosk.domain.catalog_metadata import Provider
from leo_kiosk.domain.catalog_records import StoredGame
from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.services.sessions import TrialSessionService
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.catalog_metadata import CatalogMetadataRepository
from leo_kiosk.storage.database import open_database, transaction
from leo_kiosk.storage.schema import MIGRATIONS
from leo_kiosk.storage.sessions import SessionRepository


@pytest.fixture
def profiles(tmp_path):
    return BrowserProfiles(tmp_path / "data")


def test_trial_profiles_are_private_and_cleaned(profiles):
    profile = profiles.new_trial_profile()
    assert profile.is_relative_to(profiles._data) and (profile / "user.js").exists()
    assert (profile / "user.js").stat().st_mode & 0o077 == 0
    profiles.cleanup_profile(profile)
    assert not profile.exists()


def test_child_profile_persists_and_cleans_are_refused(profiles):
    child = profiles.child_profile
    profiles.cleanup_profile(child)  # must not delete the persistent profile
    assert child.exists()


def test_profile_escape_is_rejected(tmp_path):
    BrowserProfiles.validate_profile_path(
        tmp_path / "data" / "firefox-profiles" / "t", tmp_path / "data"
    )
    with pytest.raises(ValidationError):
        BrowserProfiles.validate_profile_path(Path("/etc"), tmp_path / "data")


def test_firefox_command_shape_and_url_gate(tmp_path):
    argv = build_firefox_command("firefox", tmp_path, "https://example.com/game")
    assert argv[:6] == (
        "firefox",
        "--no-remote",
        "--new-instance",
        "--profile",
        str(tmp_path),
        "--kiosk",
    )
    assert argv[6] == "https://example.com/game"
    for url in ("file:///etc/passwd", "javascript:alert(1)", "", "https://exa mple.com"):
        with pytest.raises(ValidationError):
            build_firefox_command("firefox", tmp_path, url)


class FakeProcess:
    def __init__(self, pid=4242):
        self.pid = pid
        self.returncode = None

    def poll(self):
        return self.returncode


class FakeProfiles:
    def __init__(self):
        self.created = []
        self.cleaned = []

    def new_trial_profile(self):
        profile = Path(f"/tmp/fake-profile-{len(self.created)}")
        self.created.append(profile)
        return profile

    def cleanup_profile(self, profile):
        self.cleaned.append(profile)


class RecordingPopen:
    def __init__(self, fail=False):
        self.calls = []
        self.processes = []
        self.fail = fail

    def __call__(self, argv, start_new_session=False, stdout=None, stderr=None):
        self.calls.append((tuple(argv), start_new_session))
        if self.fail:
            raise OSError("no firefox")
        process = FakeProcess()
        self.processes.append(process)
        return process


counter = iter(range(1000))


def make_game(db, url="https://example.com/game"):
    item = CatalogItem("test", url, f"Game {next(counter)}", MediaType.GAME)
    with transaction(db):
        CatalogMetadataRepository(db).upsert_provider(
            Provider("test", "Test", "https://test.example")
        )
        CatalogRepository(db).insert_record(StoredGame(item))
    return item.game_id


@pytest.fixture
def session_env(tmp_path):
    db = open_database(tmp_path / "catalog.sqlite3", MIGRATIONS)
    repo = SessionRepository(db)
    popen = RecordingPopen()
    profiles = FakeProfiles()
    scheduled: list = []
    watches: dict = {}
    service = TrialSessionService(
        repo,
        popen=popen,
        profiles=profiles,
        call_later=lambda seconds, fn: (scheduled.append(fn), len(scheduled))[1],
        cancel_later=lambda handle: scheduled.clear(),
        watch_process=lambda process, callback: watches.__setitem__(process.pid, callback),
        clock=lambda: datetime_now(),
    )
    return service, repo, popen, profiles, scheduled, db, watches


from datetime import UTC, datetime  # noqa: E402


def datetime_now():
    return datetime.now(UTC)


def test_start_trial_spawns_kiosk_and_records_history(session_env):
    service, repo, popen, profiles, _scheduled, db, watches = session_env
    token = service.start_trial("https://example.com/game", make_game(db))
    argv, own_session = popen.calls[0]
    assert own_session is True and "--kiosk" in argv
    assert token in service.active_tokens
    row = repo.get_session(token)
    assert row["role"] == "review_trial" and row["ended_at"] is None


def test_spawn_failure_records_spawn_failed_and_no_active_session(session_env):
    service, repo, popen, profiles, _scheduled, db, watches = session_env
    popen.fail = True
    game_id = make_game(db, "https://example.com/fail")
    with pytest.raises(ValidationError):
        service.start_trial("https://example.com/game", game_id)
    assert service.active_tokens == ()
    assert profiles.cleaned, "failed spawn cleans the profile"
    rows = [dict(r) for r in repo.connection.execute("SELECT * FROM launch_sessions")]
    assert rows[0]["outcome"] == "spawn_failed"


def test_natural_exit_finishes_with_exited_and_cleans_profile(session_env):
    service, repo, popen, profiles, _scheduled, db, watches = session_env
    finished = []
    service.on_finished = lambda token, game_id, outcome: finished.append(outcome)
    token = service.start_trial("https://example.com/game", make_game(db))
    popen.processes[0].returncode = 0
    service._on_exit(token)
    assert [o.value for o in finished] == ["exited"]
    assert service.active_tokens == () and profiles.cleaned


def test_crash_exit_is_recorded_as_crashed(session_env):
    service, repo, popen, profiles, _scheduled, db, watches = session_env
    service.start_trial("https://example.com/game", make_game(db))
    popen.processes[0].returncode = 1
    token = next(iter(service.active_tokens))
    service._on_exit(token)
    row = repo.get_session(token)
    assert row["outcome"] == "crashed"


def test_stop_sends_term_and_schedules_kill(session_env):
    service, repo, popen, profiles, scheduled, db, watches = session_env
    service.start_trial("https://example.com/game", make_game(db))
    process = popen.processes[0]
    token = next(iter(service.active_tokens))
    service.stop(
        token,
        __import__(
            "leo_kiosk.domain.sessions", fromlist=["LaunchOutcome"]
        ).LaunchOutcome.PARENT_REQUEST,
    )
    # TERM is delivered via killpg; the kill escalation is scheduled for 3 s.
    assert len(scheduled) == 1
    process.returncode = -15
    watches[process.pid](process.pid, -15)  # exit watch fires after TERM
    assert service.active_tokens == ()
    assert profiles.cleaned
    row = repo.get_session(token)
    assert row["outcome"] == "parent_request"


def test_only_one_trial_at_a_time(session_env):
    service, repo, popen, profiles, _scheduled, db, watches = session_env
    service.start_trial("https://example.com/game", make_game(db))
    with pytest.raises(ValidationError):
        service.start_trial("https://example.com/other", make_game(db, "https://example.com/other"))


def test_exit_callback_for_unknown_token_is_ignored(session_env):
    service, repo, popen, profiles, _scheduled, db, watches = session_env
    service._on_exit(uuid4())  # must not raise
