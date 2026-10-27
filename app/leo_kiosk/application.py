"""Application wiring: catalog, sessions, tile launches, the kiosk web UI.

Every screen is an HTML page on the loopback server (adapters/ui_server.py)
shown in one WebKitGTK view (ui/window.py). The server thread renders; web
actions are marshalled to the GTK main thread with GLib.idle_add; the launch
engine (services/tile_launch.py) owns process lifetime exactly as the legacy
GTK launcher did.
"""

import io
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gtk  # noqa: E402

from leo_kiosk.adapters import wifi as wifi_adapter  # noqa: E402
from leo_kiosk.adapters.battery import read_battery  # noqa: E402
from leo_kiosk.adapters.catalog_source import BootstrapCatalogSource  # noqa: E402
from leo_kiosk.adapters.thumbs import fit_thumbnail  # noqa: E402
from leo_kiosk.adapters.ui_server import (  # noqa: E402
    ReviewRow,
    UiServer,
    WifiView,
    load_videos,
    render_blank,
    render_child_state,
    render_editor,
    render_exit,
    render_home,
    render_homechild_pick,
    render_homechild_preview,
    render_menu,
    render_mychild,
    render_portal_opened,
    render_poweroff,
    render_review,
    render_state,
    render_videos,
    render_wifi,
)
from leo_kiosk.adapters.video_player import build_video_command  # noqa: E402
from leo_kiosk.domain.errors import ConflictError, StorageError, ValidationError  # noqa: E402
from leo_kiosk.domain.gestures import (  # noqa: E402
    DEFAULT_PATTERNS,
    PARENT_SURFACE_PATTERNS,
    REVIEW_TRIAL_PATTERNS,
    GestureAction,
)
from leo_kiosk.domain.reviews import AgeRange, ReviewStatus, StarRating  # noqa: E402
from leo_kiosk.domain.sessions import LaunchOutcome  # noqa: E402
from leo_kiosk.services.catalog import CatalogService  # noqa: E402
from leo_kiosk.services.child import (  # noqa: E402
    ChildService,
    ScreenTimeService,
    _parse_screen_time,
    matches_age,
    parse_birthday,
)
from leo_kiosk.services.home import HomeService  # noqa: E402
from leo_kiosk.services.home_seed import seed_home  # noqa: E402
from leo_kiosk.services.navigation import Route  # noqa: E402
from leo_kiosk.services.review import ReviewService  # noqa: E402
from leo_kiosk.services.sessions import TrialSessionService  # noqa: E402
from leo_kiosk.services.thumbs import ThumbnailWriter, thumbs_directory  # noqa: E402
from leo_kiosk.services.tile_launch import TileLauncher, play  # noqa: E402
from leo_kiosk.storage.catalog import CatalogRepository  # noqa: E402
from leo_kiosk.storage.catalog_import import import_catalog  # noqa: E402
from leo_kiosk.storage.child import (  # noqa: E402
    ChildRepository,
    GamePlaytimeRepository,
    ScreenTimeRepository,
)
from leo_kiosk.storage.database import default_database_path, open_database  # noqa: E402
from leo_kiosk.storage.home import HomeRepository  # noqa: E402
from leo_kiosk.storage.schema import MIGRATIONS  # noqa: E402
from leo_kiosk.storage.sessions import SessionRepository  # noqa: E402
from leo_kiosk.storage.thumbs import ThumbnailRepository  # noqa: E402
from leo_kiosk.ui.window import LauncherWindow  # noqa: E402

# HERE is the app/ directory (parent of the leo_kiosk package). Runtime data
# files are installed flat next to the legacy scripts on the tablet; in this
# repo the canonical copies live in config/ (see install-kiosk.sh).
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "tiles.json")
VOICES = os.path.join(HERE, "voices")
STATE = os.path.join(HERE, ".app-pid")
KIOSK_VIDEOS = os.path.join(HERE, "kiosk_videos.json")
VIDEOS_SCRIPT = os.path.join(HERE, "videos.py")
BOOTSTRAP = os.path.join(HERE, "catalog", "bootstrap.json")
STATUS_SECONDS = 3.0
WIFI_STATE_CACHE_SECONDS = 10.0

URL_FOR = {
    Route.CHILD_HOME: "/",
    Route.PARENT_HOME: "/parent",
    Route.REVIEW_LIST: "/review",
    Route.HOME_PICKER: "/homechild",
    Route.MY_CHILD: "/mychild",
    Route.VIDEOS: "/videos",
    Route.WIFI: "/wifi",
}

# The view can navigate itself (page links); route state follows the page.
# This table plus web_navigated() is the routing contract: every screen is a
# server page, every navigation is a GET load the controller observes.
ROUTE_FOR_PATH = {
    "/": Route.CHILD_HOME,
    "/parent": Route.PARENT_HOME,
    "/review": Route.REVIEW_LIST,
    "/homechild": Route.HOME_PICKER,
    "/mychild": Route.MY_CHILD,
    "/videos": Route.VIDEOS,
    "/wifi": Route.WIFI,
    "/exit": Route.PARENT_HOME,
    "/poweroff": Route.PARENT_HOME,
}


def _load_config(path: str) -> dict[str, object]:
    """tiles.json contents; an unreadable config degrades to an empty home."""
    import json

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"config unavailable ({exc})", file=sys.stderr, flush=True)
        return {}


def _int_or_none(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _popen(*args, **kwargs):
    import subprocess

    return subprocess.Popen(*args, **kwargs)


class AppController:
    """Routes gestures and web actions through navigation and the engine.

    Limitation unchanged from the GTK parity build: gestures are ignored
    while a launched app is foregrounded — backwatch and leopowerd own those
    exits, through the same .app-pid / process-group contract as before.
    """

    def __init__(
        self,
        window: LauncherWindow,
        config: dict[str, object],
        server: UiServer | None = None,
        catalog: CatalogService | None = None,
        sessions: TrialSessionService | None = None,
        monitor=None,
        usage: ScreenTimeService | None = None,
    ) -> None:
        self.window = window
        self.config = config
        self.server = server
        self.catalog = catalog
        self.sessions = sessions
        self.monitor = monitor
        self.usage = usage
        self._usage_started: float | None = None
        self.route = Route.CHILD_HOME
        self.trial_token: UUID | None = None
        self.trial_game_id: UUID | None = None
        self.trial_web = False
        self._web_usage_started: float | None = None
        # Where Down/Up lands after a web trial: the review editor (default)
        # or the Home-Child pick list for the tile the trial came from.
        self.trial_return = "editor"
        self.trial_slot: int | None = None
        self._thumbnail_writer: ThumbnailWriter | None = None
        self.web_outcomes: dict[UUID, str] = {}
        self.portal_active = False
        self._status: tuple[str, float] = ("", 0.0)
        self._return_path = "/"  # page shown again when a video ends
        self.launcher = TileLauncher(
            state_path=STATE,
            voices_dir=VOICES,
            popen=_popen,
            clock=time.monotonic,
            player=play,
            call_later=lambda seconds, fn: GLib.timeout_add(int(seconds * 1000), fn),
            on_status=self.say,
            on_enter=self._on_app_launch,
            on_return=self._on_app_exit,
        )

    # --- gestures ---------------------------------------------------------
    def on_gesture(self, action: GestureAction) -> None:
        in_trial = self.trial_token is not None
        if not self.window.is_showing() and not in_trial:
            return  # legacy app foregrounded; only the trial return passes
        if in_trial:
            # Down/Down mid-trial captures a thumbnail; every other
            # recognized gesture ends the trial: Down/Up returns to this
            # game's editor, Up/Down/Down goes to the parent home. Stopping
            # the session drives the visible change via the finish callback.
            if action is GestureAction.SCREENSHOT:
                # Home-Child trials are plain try-outs: no thumbnail capture.
                if self.trial_return == "homechild":
                    return
                self._capture_trial_thumbnail()
                return
            outcome = (
                LaunchOutcome.PARENT_REQUEST
                if action is GestureAction.ENTER_PARENT
                else LaunchOutcome.RETURN_GESTURE
            )
            token = self.trial_token
            self.trial_token = None  # further gestures wait for the finish
            self.sessions.stop(token, outcome)
            return
        if self.portal_active:
            # Down/Up leaves the portal for Wifi; Up/Down/Down goes parent.
            self.portal_active = False
            self.window.hide_loader()
            self._show(
                Route.PARENT_HOME if action is GestureAction.ENTER_PARENT else Route.WIFI
            )
            return
        if action is GestureAction.ENTER_PARENT:
            self._show(Route.PARENT_HOME)
            return
        if self.route is Route.CHILD_HOME:
            return  # Down/Down/Up on the child home: no-op, as before
        # Old-world Down/Up semantics: leave the current surface for the
        # child home (the pre-port UX; backwatch killed the foregrounded
        # browser, which landed here too).
        self._show(Route.CHILD_HOME)

    def web_navigated(self, uri: str) -> None:
        """The view committed a load (page link or controller navigation)."""
        if self.trial_token is not None or not self.window.is_showing():
            return
        path = urllib.parse.urlparse(uri).path
        route = ROUTE_FOR_PATH.get(path)
        if route is None and path.startswith("/review/"):
            route = Route.PARENT_HOME  # interim trial state page
        if route is None and path.startswith("/homechild/"):
            route = Route.HOME_PICKER  # game page and interim trial page
        if route is None or route is self.route:
            return
        self.route = route
        self._use_patterns(route)

    # --- route display ----------------------------------------------------
    def _show(self, route: Route) -> None:
        self.route = route
        self._use_patterns(route)
        self._navigate(route)

    def _use_patterns(self, route: Route) -> None:
        """Switch recognizer patterns per surface.

        The launcher only owns return gestures on launcher-shown surfaces;
        foregrounded apps are exited by backwatch/powerd instead, so the
        child home keeps the default set while parent/video surfaces get the
        short Down/Up return.
        """
        if self.monitor is None:
            return
        patterns = (
            DEFAULT_PATTERNS if route is Route.CHILD_HOME else PARENT_SURFACE_PATTERNS
        )
        self.monitor.recognizer.use_patterns(patterns)

    def _navigate(self, route: Route) -> None:
        url = URL_FOR.get(route)
        if url is not None and self.server is not None:
            self.window.navigate(self.server.base + url)

    # --- web actions ------------------------------------------------------
    def launch_tile(self, tile_id: str) -> None:
        """Web action: a home tile was tapped; native tiles run via the engine."""
        if self.route is not Route.CHILD_HOME or not self.window.is_showing():
            return
        if tile_id == "videos":
            self._show(Route.VIDEOS)
            return
        tile = self._tiles_by_id().get(tile_id)
        if tile is None:
            return
        self.launcher.launch(tile)

    def play_video(self, url: str) -> None:
        """Web action: a Videos tile was tapped; mpv runs via videos.py."""
        if self.route is not Route.VIDEOS or not self.window.is_showing():
            return
        if self.launcher.proc is not None and self.launcher.proc.poll() is None:
            return
        try:
            build_video_command(VIDEOS_SCRIPT, url)
        except ValidationError:
            self.say("Cannot play this one!")
            return
        videos_tile = self._tiles_by_id().get("videos", {})
        tile = {
            "id": "videos",
            "cmd": [[VIDEOS_SCRIPT, url]],
            "minutes": videos_tile.get("minutes", 20),
        }
        self._return_path = "/videos"
        self.launcher.launch(tile, play_sound=False)

    def webview_closed(self) -> None:
        """The view closed itself (/exit page): return to the child home."""
        self.route = Route.CHILD_HOME
        self.window.set_page_zoom(1.0)  # never leak the game zoom to the home
        self._navigate(Route.CHILD_HOME)

    # --- status -----------------------------------------------------------
    def say(self, text: str, seconds: float = STATUS_SECONDS) -> None:
        self._status = (text, time.monotonic() + seconds)

    def status_text(self) -> str:
        text, deadline = self._status
        return text if time.monotonic() < deadline else ""

    # --- launch engine callbacks -----------------------------------------
    def _on_app_launch(self) -> None:
        if self._usage_started is None:
            self._usage_started = time.monotonic()
        self.route = Route.CHILD_ACTIVITY
        self.window.hide()

    def _on_app_exit(self) -> None:
        if self._usage_started is not None:
            elapsed = time.monotonic() - self._usage_started
            self._usage_started = None
            if self.usage is not None:
                try:
                    self.usage.record(elapsed, datetime.now())
                except Exception as exc:  # noqa: BLE001 - usage never blocks exits
                    print(f"screen time: record failed ({exc})", file=sys.stderr, flush=True)
        route = Route.VIDEOS if self._return_path == "/videos" else Route.CHILD_HOME
        self._return_path = "/"
        self._show(route)
        self.window.show()

    # --- review trials (launched from the web UI) -------------------------
    def request_web_trial(
        self, game_id: UUID, return_to: str = "editor", slot: int | None = None
    ) -> None:
        """Main-thread bridge: start a trial shown in the launcher's own view.

        ``return_to`` picks the page Down/Up returns to: the review editor
        (default) or the Home-Child pick list for ``slot`` ('homechild', a
        plain try-out with no thumbnail capture).

        The game URL is a page in the single WebKitGTK view — no browser
        process, no profile. The window stays visible beneath the game page.
        """
        if self.trial_token is not None or self.catalog is None:
            return
        try:
            entry = self.catalog.get_entry(game_id)
        except (LookupError, ValueError):
            return
        try:
            token = self.sessions.start_trial(entry.playable_url, game_id)
        except ValidationError:
            return  # already running or history failure; stay on the page
        self.trial_token = token
        self.trial_game_id = game_id
        self.trial_return = return_to
        self.trial_slot = slot
        self.route = Route.REVIEW_TRIAL
        # Fixed-size games (verified design dimensions) get a whole-page
        # zoom so the designed canvas fills the screen; everything else
        # stays at zoom 1 and the page's own layout decides.
        scale = 1.0
        dimensions = getattr(entry, "dimensions", None)
        if dimensions is not None:
            fit = dimensions.fit_scale(*self.window.page_size())
            if fit is not None:
                scale = fit
        self.window.set_page_zoom(scale)
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(REVIEW_TRIAL_PATTERNS)
        # Cover the view while the game page loads: its own background is
        # dark/blank for seconds before the game's first frame.
        self.window.show_loader(f"Starting {entry.display_name}...")
        if self.server is not None:
            self.window.navigate(entry.playable_url)

    def web_trial_state(self, game_id: UUID) -> tuple[bool, str | None]:
        running = self.trial_token is not None
        outcome = self.web_outcomes.get(game_id)
        return running, outcome

    def _capture_trial_thumbnail(self) -> None:
        """Down/Down in a trial: snapshot, downsize, persist, toast.

        The toast fires immediately (perceived feedback); the snapshot lands
        asynchronously and a failure is a silent no-op — a five-year-old
        pressing buttons needs no error text.
        """
        if self.trial_game_id is None:
            return
        game_id = self.trial_game_id
        self.window.toast("Screenshot captured")

        def on_surface(surface) -> None:
            if surface is None:
                return
            try:
                thumbnail = fit_thumbnail(surface)
                buffer = io.BytesIO()
                thumbnail.write_to_png(buffer)
                self._thumb_writer().save(game_id, buffer.getvalue())
            except (ValueError, OSError, StorageError, ValidationError):
                return  # a failed capture must never disturb the trial

        self.window.capture_snapshot(on_surface)

    def _thumb_writer(self) -> ThumbnailWriter:
        """The pages provider's writer (same DB, same thread-confined conn).

        Built lazily on the main thread during a capture; the server thread's
        _open() builds its own only if a home render happened first — both
        paths open the same database file, WAL handles the concurrency.
        """
        if self._thumbnail_writer is None:
            database_path = Path(default_database_path())
            connection = open_database(database_path, migrations=MIGRATIONS)
            self._thumbnail_writer = ThumbnailWriter(
                ThumbnailRepository(connection), thumbs_directory(database_path)
            )
        return self._thumbnail_writer

    def request_child_game(self, game_id: UUID, slot: int, minutes: int) -> None:
        """Main-thread bridge: the child tapped a placed game on the home.

        The game runs in the kiosk view like a review trial but counts as
        the child's screen time: Down/Up returns to the child home, Down/
        Down refreshes the game's thumbnail, the tile's minutes cap the
        session, and the elapsed time lands in the daily budget.
        """
        if self.trial_token is not None or self.catalog is None:
            return
        if self.route is not Route.CHILD_HOME or not self.window.is_showing():
            return
        try:
            entry = self.catalog.get_entry(game_id)
        except (LookupError, ValueError):
            return
        try:
            token = self.sessions.start_child_game(
                entry.playable_url, game_id, slot, minutes
            )
        except ValidationError:
            return  # already running or history failure; stay on the page
        self.trial_token = token
        self.trial_game_id = game_id
        self.trial_return = "child"
        self.trial_slot = None
        self.route = Route.CHILD_ACTIVITY
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(REVIEW_TRIAL_PATTERNS)
        self.window.show_loader(f"Starting {entry.display_name}...")
        scale = 1.0
        dimensions = getattr(entry, "dimensions", None)
        if dimensions is not None:
            fit = dimensions.fit_scale(*self.window.page_size())
            if fit is not None:
                scale = fit
        self.window.set_page_zoom(scale)
        self.window.navigate(entry.playable_url)
        self._web_usage_started = time.monotonic()

    def _record_web_usage(self, game_id: UUID | None = None) -> None:
        """Fold the finished child game's elapsed time into today's budget.

        A web child game's seconds are also attributed per game for the
        parent's "most played" ranking.
        """
        if self._web_usage_started is None:
            return
        elapsed = time.monotonic() - self._web_usage_started
        self._web_usage_started = None
        if self.usage is not None:
            try:
                self.usage.record(elapsed, datetime.now(), game_id)
            except Exception as exc:  # noqa: BLE001 - usage never blocks play
                print(f"screen time: record failed ({exc})", file=sys.stderr, flush=True)

    def trial_finished(self, game_id: UUID, outcome_value: str) -> None:
        finished_game_id = self.trial_game_id
        self.trial_token = None
        self.trial_game_id = None
        self.web_outcomes[game_id] = outcome_value
        self.window.set_page_zoom(1.0)  # our pages must never inherit the game zoom
        if self.trial_return == "child":
            # A child game ended: back to the child home, time spent counts.
            self._record_web_usage(finished_game_id)
            self.route = Route.CHILD_HOME
            self._use_patterns(Route.CHILD_HOME)
            if self.server is not None:
                self.window.navigate(self.server.base + "/")
            self.window.show()
            return
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(DEFAULT_PATTERNS)
        self.route = Route.PARENT_HOME
        self._use_patterns(Route.PARENT_HOME)
        if self.server is not None:
            if self.trial_return == "editor":
                target = f"/review/{game_id}"
            elif self.trial_slot is not None:
                target = f"/homechild/{self.trial_slot}"
            else:
                target = "/homechild"
            self.window.navigate(self.server.base + target)

    # --- portal (captive-portal sign-in, in the same view) ----------------
    def open_portal_browser(self) -> None:
        """Navigate the view to the connectivity probe; the portal redirects.

        The WebKit context is ephemeral, so the portal's cookies die with the
        view. Down/Up (or Up/Down/Down) leaves the portal from the gesture
        branch in on_gesture; there is no process to tear down.
        """
        if self.portal_active:
            return
        self.portal_active = True
        self.window.show_loader("Opening sign-in...")
        if self.server is not None:
            self.window.navigate(wifi_adapter.CONNECTIVITY_CHECK_URL)

    def _tiles_by_id(self) -> dict[str, dict[str, object]]:
        tiles = self.config.get("tiles", [])
        return {str(t["id"]): t for t in tiles if isinstance(t, dict) and "id" in t}


class WebUIPages:
    """All kiosk pages rendered from the real services in the server thread.

    The server thread owns its own read-only catalog connection; actions are
    marshalled to the GTK main thread because the session and launch engines
    drive GLib schedulers and process watches there.
    """

    def __init__(
        self,
        db_path,
        config: dict[str, object],
        controller=None,
    ) -> None:
        self._db_path = db_path
        self._config = config
        self._controller = controller
        self._conn = None
        self._catalog: CatalogService | None = None
        self._review: ReviewService | None = None
        self._thumbs: ThumbnailWriter | None = None
        self._home: HomeService | None = None
        self._child: ChildService | None = None
        self._usage: ScreenTimeService | None = None
        # Unsaved editor drafts (name/stars/ages), keyed by game: stored when
        # the parent taps Try now or hits a validation error, so the input
        # survives the trial. In-memory on purpose — drafts die with the app.
        self._drafts: dict[UUID, dict[str, object]] = {}

    def _open(self) -> None:
        if self._conn is None:
            # Migrations are required here too: without them the migration
            # check validates the real schema against an empty set and the
            # review page dies with "schema is newer or incompatible".
            self._conn = open_database(self._db_path, migrations=MIGRATIONS)
            repository = CatalogRepository(self._conn)
            selected = HomeRepository(self._conn).selected_game_ids()
            self._catalog = CatalogService(repository, selected)
            self._review = ReviewService(repository)
            self._home = HomeService(HomeRepository(self._conn), repository)
            self._child = ChildService(ChildRepository(self._conn))
            self._usage = ScreenTimeService(
                ChildRepository(self._conn),
                ScreenTimeRepository(self._conn),
                GamePlaytimeRepository(self._conn),
            )
            self._thumbs = ThumbnailWriter(
                ThumbnailRepository(self._conn), thumbs_directory(Path(self._db_path))
            )

    def _service(self) -> CatalogService:
        self._open()
        return self._catalog

    def _review_service(self) -> ReviewService:
        self._open()
        return self._review

    def _name(self, game_id: UUID) -> str:
        try:
            return self._service().get_entry(game_id).display_name
        except (LookupError, ValueError):
            return "Game"

    def _osk(self) -> bool:
        """Always show the on-screen keyboard on text fields.

        The Surface Go exposes an internal 'AT Translated Set 2 keyboard'
        evdev node with no physical keys attached, so hardware detection
        cannot distinguish an attached Type Cover from nothing (found
        on-device 2026-10-26: the probe hid the OSK for everyone). With a
        Type Cover attached the OSK is redundant but harmless (Done hides
        it; the cover keeps working).
        """
        return True

    # --- child pages ------------------------------------------------------
    def _screen_time(self) -> tuple[int | None, bool]:
        """(remaining minutes today, blocked); (None, False) = no limit set.

        Storage trouble must never kill the home page: degrade to no timer.
        """
        try:
            self._open()
            assert self._usage is not None
            if self._usage.limit() is None:
                return None, False
            remaining = self._usage.remaining_minutes(datetime.now())
            assert remaining is not None
            return remaining, remaining <= 0
        except Exception:  # noqa: BLE001
            return None, False

    def home(self) -> str:
        tiles = self._config.get("tiles", [])
        remaining, blocked = self._screen_time()
        return render_home(
            str(self._config.get("title", "")),
            self._with_thumbs(tiles),
            remaining=remaining,
            blocked=blocked,
        )

    def _with_thumbs(
        self, tiles: list[object]
    ) -> list[dict[str, object]]:
        """Decorate home tiles with the slot game's art and its real name.

        A tile whose slot holds a game shows the game's display name and
        /thumb/ art (the config label like 'TBD' is replaced); legacy tiles
        keep their color+label look, and a slot-game tile whose art is
        missing/unreadable falls back to color+label (the page never 404s).
        """
        try:
            self._open()
        except Exception:
            return list(tiles)  # storage trouble must never kill the home
        assert self._home is not None and self._thumbs is not None
        decorated: list[dict[str, object]] = []
        for position, tile in enumerate(tiles, 1):
            if not isinstance(tile, dict):
                decorated.append(tile)
                continue
            entry = dict(tile)
            try:
                slot = self._home.slot(position)
            except LookupError:
                slot = None
            game_id = slot.game_id if slot is not None else None
            if game_id is not None:
                path = self._thumbs.path_for(game_id)
                if path is not None and path.is_file():
                    entry["thumb"] = f"/thumb/{game_id}.png"
                try:
                    entry["label"] = self._service().get_entry(game_id).display_name
                except Exception:  # noqa: BLE001 - a bad record must not kill the home
                    entry["label"] = "Game"
            decorated.append(entry)
        return decorated

    def thumbnail(self, filename: str) -> tuple[bytes, int]:
        """Serve one game's PNG art; 404 when absent or unreadable."""
        try:
            game_id = UUID(filename.removesuffix(".png"))
        except ValueError:
            return b"", 404
        try:
            self._open()
            assert self._thumbs is not None
            path = self._thumbs.path_for(game_id)
        except Exception:
            return b"", 404
        if path is None or not path.is_file():
            return b"", 404
        try:
            return path.read_bytes(), 200
        except OSError:
            return b"", 404

    def videos(self) -> str:
        try:
            return render_videos(load_videos(KIOSK_VIDEOS))
        except (OSError, ValueError) as exc:
            # Missing/broken catalog must degrade to a page, not a dropped
            # connection (the handler thread would otherwise die mid-request).
            print(f"videos: catalog unavailable ({exc})", file=sys.stderr, flush=True)
            return render_blank("No videos right now. Ask Papa to fix this one!")

    def _wifi_available(self) -> bool:
        """Connected with full connectivity; nmcli errors mean not available.

        Cached: the state poll runs every 2 s and each check spawns nmcli.
        The server thread is single-threaded, so no lock is needed.
        """
        now = time.monotonic()
        cached_at, cached = getattr(self, "_wifi_cache", (0.0, None))
        if cached is None or now - cached_at > WIFI_STATE_CACHE_SECONDS:
            try:
                cached = (
                    wifi_adapter.current_network() is not None
                    and wifi_adapter.connectivity() == "full"
                )
            except wifi_adapter.WifiError:
                cached = False
            self._wifi_cache = (now, cached)
        return cached

    def child_state(self) -> str:
        status = ""
        if self._controller is not None:
            status = self._controller.status_text()
        remaining, blocked = self._screen_time()
        screen_time = (
            {"remaining": remaining, "blocked": blocked}
            if remaining is not None
            else None
        )
        return render_child_state(status, read_battery(), self._wifi_available(), screen_time)

    def launch_tile(self, tile_id: str) -> str:
        """A home tile was tapped: a placed web game runs as a child session,
        a legacy tile goes through the process-launching engine."""
        _remaining, blocked = self._screen_time()
        if blocked:
            return render_blank("No more screen time today!")
        if tile_id == "videos":
            if self._controller is not None:
                GLib.idle_add(self._controller.launch_tile, tile_id)
            return render_blank("")
        position = self._tile_position(tile_id)
        if position is None:
            return render_blank("")
        try:
            self._open()
            assert self._home is not None
            slot = self._home.slot(position)
        except Exception:  # noqa: BLE001 - storage trouble degrades to legacy launch
            slot = None
        game_id = slot.game_id if slot is not None else None
        if game_id is not None:
            if self._controller is not None:
                GLib.idle_add(
                    self._controller.request_child_game,
                    game_id,
                    position,
                    self._tile_minutes(position),
                )
            return render_blank("")
        if self._controller is not None:
            GLib.idle_add(self._controller.launch_tile, tile_id)
        return render_blank("")

    def _tile_position(self, tile_id: str) -> int | None:
        tiles = self._config.get("tiles", [])
        for position, tile in enumerate(tiles, 1):
            if isinstance(tile, dict) and tile.get("id") == tile_id:
                return position
        return None

    def _tile_minutes(self, position: int) -> int:
        tiles = self._config.get("tiles", [])
        if 0 < position <= len(tiles) and isinstance(tiles[position - 1], dict):
            minutes = tiles[position - 1].get("minutes", 20)
            if isinstance(minutes, int) and minutes > 0:
                return minutes
        return 20

    def video_play(self, url: str) -> str:
        _remaining, blocked = self._screen_time()
        if blocked:
            return render_blank("No more screen time today!")
        try:
            build_video_command(VIDEOS_SCRIPT, url)
        except ValidationError:
            return render_blank("This video cannot be played.")
        if self._controller is not None:
            GLib.idle_add(self._controller.play_video, url)
        return render_blank("")

    # --- parent pages -----------------------------------------------------
    def menu(self) -> str:
        return render_menu()

    def review(self) -> str:
        try:
            rows = self._review_rows()
        except Exception as exc:  # noqa: BLE001 - catalog failure must not kill the page
            # A dead database is NOT an empty catalog: say so, and log it.
            print(f"review: catalog unavailable ({exc})", file=sys.stderr, flush=True)
            return render_blank(f"Review is unavailable: {exc}")
        return render_review(rows)

    def _review_rows(self) -> list[ReviewRow]:
        """Display rows for the review list; one connection, one pass."""
        rows = []
        for entry in self._service().list_review_entries():
            ages = (
                f" ages {entry.age_min}-{entry.age_max}"
                if entry.age_min is not None
                else ""
            )
            rows.append(
                ReviewRow(
                    str(entry.game_id),
                    entry.display_name,
                    entry.status.value,
                    str(entry.stars) if entry.stars is not None else None,
                    ages,
                )
            )
        return rows

    # --- My Child: birthday + screen time ---------------------------------
    def mychild(self, message: str | None = None) -> str:
        """The birthday + screen-time settings page (no game lists)."""
        try:
            self._open()
            assert self._child is not None and self._usage is not None
            birthday = self._child.birthday()
            age = self._child.age(date.today())
            limit = self._usage.limit()
        except Exception as exc:  # noqa: BLE001 - catalog failure must not kill the page
            print(f"mychild: catalog unavailable ({exc})", file=sys.stderr, flush=True)
            return render_blank(f"My Child is unavailable: {exc}")
        return render_mychild(birthday, age, message=message, screen_time=limit)

    def mychild_save(self, form: dict[str, list[str]]) -> str:
        """Validate and store the birthday + screen time; re-render the page."""
        if not self._parent_surface():
            return render_blank("Not available right now.")
        today = date.today()
        try:
            birthday = parse_birthday(
                _int_or_none(form.get("day", [""])[0]),
                _int_or_none(form.get("month", [""])[0]),
                _int_or_none(form.get("year", [""])[0]),
                today,
            )
            limit = _parse_screen_time(form.get("screen_time", [""])[0])
            self._open()
            assert self._child is not None and self._usage is not None
            self._child.set_birthday(birthday)
            self._usage.set_limit(limit)
        except (ValidationError, LookupError) as exc:
            return self.mychild(message=str(exc))
        return self.mychild()

    def exit(self) -> str:
        return render_exit()

    # --- Home Child: pick a tile, then a game for it ----------------------
    def homechild(self, message: str | None = None) -> str:
        """The child home grid, parent edition; a tile tap opens its picker."""
        try:
            tiles = self._preview_tiles()
        except Exception as exc:  # noqa: BLE001 - catalog failure must not kill the page
            print(f"homechild: catalog unavailable ({exc})", file=sys.stderr, flush=True)
            return render_blank(f"Home Child is unavailable: {exc}")
        return render_homechild_preview(
            str(self._config.get("title", "")), tiles, message=message
        )

    def homechild_slot(self, position: int, message: str | None = None) -> str:
        """Pick list for one tile; tested/reviewed games only, and — when the
        child's birthday is known — only games whose age range fits."""
        try:
            self._open()
            assert self._child is not None
            age = self._child.age(date.today())
            rows = []
            for entry in self._service().list_review_entries():
                if entry.status.value not in (
                    ReviewStatus.TESTED.value,
                    ReviewStatus.REVIEWED.value,
                    ReviewStatus.SELECTED.value,
                ):
                    continue
                if age is not None:
                    # An unknown age range is not a promise of suitability:
                    # without bounds the game cannot prove it fits.
                    if entry.age_min is None and entry.age_max is None:
                        continue
                    if not matches_age(entry.age_min, entry.age_max, age):
                        continue
                rows.append(
                    ReviewRow(
                        str(entry.game_id),
                        entry.display_name,
                        entry.status.value,
                        str(entry.stars) if entry.stars is not None else None,
                        f" ages {entry.age_min}-{entry.age_max}"
                        if entry.age_min is not None
                        else "",
                    )
                )
        except Exception as exc:  # noqa: BLE001 - catalog failure must not kill the page
            print(f"homechild: catalog unavailable ({exc})", file=sys.stderr, flush=True)
            return render_blank(f"Home Child is unavailable: {exc}")
        empty = (
            "Nothing suitable for this age yet." if age is not None else "No tested games yet."
        )
        return render_homechild_pick(
            position, self._occupant_label(position), rows,
            message=message, empty_message=empty,
        )

    def homechild_try(self, position: int, game_id: UUID) -> str:
        try:
            self._review_service().mark_tested(game_id)
        except (ValueError, LookupError):
            pass
        if self._controller is not None:
            GLib.idle_add(
                self._controller.request_web_trial, game_id, "homechild", position
            )
        return render_state(self._name(game_id), running=True, outcome=None)

    def homechild_place(self, position: int, form: dict[str, list[str]]) -> str:
        """Place the tapped game into the pre-chosen tile; the explicit tap is
        the replacement confirmation. Return to the child home preview."""
        if not self._parent_surface():
            return render_blank("Not available right now.")
        try:
            game_id = UUID(form.get("game_id", [""])[0])
        except ValueError:
            return self.homechild_slot(position, message="Pick a game from the list.")
        try:
            self._open()
            assert self._home is not None and self._catalog is not None
            self._home.place(game_id, position, self._home.slot(position))
            self._catalog.refresh_selection(self._home.selected_game_ids())
            name = self._name(game_id)
        except (ValidationError, ConflictError, LookupError) as exc:
            return self.homechild_slot(position, message=str(exc))
        return self.homechild(message=f"Tile {position}: {name}")

    def _occupant_label(self, position: int) -> str:
        """What the tile currently shows: the game name or the legacy label."""
        try:
            self._open()
            assert self._home is not None
            slot = self._home.slot(position)
        except Exception:  # noqa: BLE001
            return "empty"
        if slot.game_id is not None:
            return self._name(slot.game_id)
        if slot.legacy_tile_id is not None:
            tiles = self._config.get("tiles", [])
            index = position - 1
            if index < len(tiles) and isinstance(tiles[index], dict):
                label = tiles[index].get("label")
                if isinstance(label, str) and label:
                    return label
            return str(slot.legacy_tile_id)
        return "empty"

    def _preview_tiles(self) -> list[dict[str, object]]:
        """The nine tiles as the child sees them, for the Home Child preview."""
        self._open()
        assert self._home is not None and self._thumbs is not None
        configured = self._config.get("tiles", [])
        out: list[dict[str, object]] = []
        for position in range(1, 10):
            index = position - 1
            tile: dict[str, object] = {}
            if index < len(configured) and isinstance(configured[index], dict):
                tile = dict(configured[index])
            entry: dict[str, object] = {
                "position": position,
                "label": str(tile.get("label", f"Tile {position}")),
                "color": str(tile.get("color", "#454551")),
            }
            try:
                slot = self._home.slot(position)
            except LookupError:
                slot = None
            if slot is not None and slot.game_id is not None:
                try:
                    game = self._service().get_entry(slot.game_id)
                    entry["label"] = game.display_name
                except (LookupError, ValueError):
                    entry["label"] = "Game"
                path = self._thumbs.path_for(slot.game_id)
                if path is not None and path.is_file():
                    entry["thumb"] = f"/thumb/{slot.game_id}.png"
            out.append(entry)
        return out

    def review_launch(self, game_id: UUID, form: dict[str, list[str]] | None = None) -> str:
        """Start a trial; a posted editor draft is kept for the return trip."""
        if form is not None:
            self._drafts[game_id] = self._parse_draft(form)
        try:
            self._review_service().mark_tested(game_id)
        except (ValueError, LookupError):
            pass
        if self._controller is not None:
            GLib.idle_add(self._controller.request_web_trial, game_id)
        return render_state(self._name(game_id), running=True, outcome=None)

    @staticmethod
    def _parse_draft(form: dict[str, list[str]]) -> dict[str, object]:
        return {
            "name": form.get("name", [""])[0],
            "prod": _int_or_none(form.get("production", [""])[0]),
            "edu": _int_or_none(form.get("education", [""])[0]),
            "fun": _int_or_none(form.get("fun", [""])[0]),
            "age_min": _int_or_none(form.get("age_min", [""])[0]),
            "age_max": _int_or_none(form.get("age_max", [""])[0]),
        }

    def review_state(self, game_id: UUID) -> str:
        """Running trial: banner + refresh; finished: the review editor."""
        running, outcome = False, None
        if self._controller is not None:
            running, outcome = self._controller.web_trial_state(game_id)
        if running:
            return render_state(self._name(game_id), running=True, outcome=None)
        try:
            entry = self._service().get_entry(game_id)
        except (LookupError, ValueError):
            return render_blank("This game is no longer in the catalog.")
        draft = self._drafts.get(game_id)
        if draft is not None:
            # The parent's unsaved input outranks the stored review.
            return render_editor(
                str(game_id),
                str(draft["name"]),
                None,
                draft.get("age_min"),
                draft.get("age_max"),
                thumb=self._thumb_url(game_id),
                osk=self._osk(),
                prod=draft.get("prod"),
                edu=draft.get("edu"),
                fun=draft.get("fun"),
            )
        return render_editor(
            str(game_id),
            entry.display_name,
            entry.stars,
            entry.age_min,
            entry.age_max,
            thumb=self._thumb_url(game_id),
            osk=self._osk(),
        )

    def review_save(self, game_id: UUID, form: dict[str, list[str]]) -> str:
        """Apply the editor draft; respond with the next page the parent needs.

        Runs in the server thread on the thread's own connection; trial and
        process state stay marshalled to the main thread as before.
        """
        name = form.get("name", [""])[0]
        star_values = (
            _int_or_none(form.get("production", [""])[0]),
            _int_or_none(form.get("education", [""])[0]),
            _int_or_none(form.get("fun", [""])[0]),
        )
        age_min = _int_or_none(form.get("age_min", [""])[0])
        age_max = _int_or_none(form.get("age_max", [""])[0])
        action = form.get("action", ["save"])[0]
        draft = self._parse_draft(form)
        self._drafts[game_id] = draft  # survives a validation error
        stars = None
        age = None
        try:
            if any(v is not None for v in star_values):
                stars = StarRating(*star_values)  # partial or out-of-range raise
            if age_min is not None or age_max is not None:
                age = AgeRange(age_min, age_max)  # one-sided or bad bounds raise
            self._review_service().apply_review(game_id, name, stars, age)
        except (ValidationError, ValueError, LookupError) as exc:
            entry_name = str(draft["name"]) or self._name(game_id)
            return render_editor(
                str(game_id),
                entry_name,
                None,
                age_min,
                age_max,
                str(exc),
                thumb=self._thumb_url(game_id),
                osk=self._osk(),
                prod=draft.get("prod"),
                edu=draft.get("edu"),
                fun=draft.get("fun"),
            )
        self._drafts.pop(game_id, None)  # saved: the draft has landed
        if action == "next":
            return self._next_editor(game_id)
        return self.review()

    def review_delete(self, game_id: UUID) -> str:
        self._drafts.pop(game_id, None)  # nothing left to keep
        """Delete, then land on the NEXT game (wrap at the end; owner
        decision 2026-10-26 — it used to fall on the previous one because
        the deleted id was already gone from the list)."""
        ids = [e.game_id for e in self._service().list_review_entries()]
        try:
            index = ids.index(game_id)
        except ValueError:
            index = None
        try:
            self._review_service().delete_game(game_id)
        except (ValueError, LookupError):
            pass
        entries = self._service().list_review_entries()
        if not entries:
            return self.review()
        if index is None:
            return self.review_state(entries[0].game_id)
        return self.review_state(entries[index % len(entries)].game_id)

    def _thumb_url(self, game_id: UUID) -> str | None:
        """The /thumb/ URL when art exists and the file is readable."""
        try:
            self._open()
            assert self._thumbs is not None
            path = self._thumbs.path_for(game_id)
        except Exception:
            return None
        if path is not None and path.is_file():
            return f"/thumb/{game_id}.png"
        return None

    def _next_editor(self, game_id: UUID) -> str:
        entries = self._service().list_review_entries()
        ids = [entry.game_id for entry in entries]
        if not ids:
            return self.review()
        try:
            index = ids.index(game_id)
        except ValueError:
            index = -1
        next_entry = entries[(index + 1) % len(ids)]
        return self.review_state(next_entry.game_id)

    def _wifi_view(self, message: str | None = None) -> WifiView:
        try:
            return WifiView(
                current_ssid=wifi_adapter.current_network(),
                connectivity=wifi_adapter.connectivity(),
                networks=wifi_adapter.list_networks(),
                saved=wifi_adapter.saved_networks(),
                message=message,
            )
        except wifi_adapter.WifiError as exc:
            return WifiView(None, "unknown", [], [], message=str(exc))

    def wifi(self) -> str:
        return render_wifi(self._wifi_view(), osk=self._osk())

    def _parent_surface(self) -> bool:
        """Route gate for state-changing endpoints (server thread).

        In-view game pages can reach the loopback server, so wifi changes,
        portal opening and poweroff are refused unless a parent surface is
        the shown page. The route read is a single attribute (GIL-atomic).
        """
        controller = self._controller
        return controller is not None and controller.route in (
            Route.PARENT_HOME,
            Route.REVIEW_LIST,
            Route.REVIEW_EDITOR,
            Route.HOME_PICKER,
            Route.MY_CHILD,
            Route.WIFI,
        )

    def wifi_connect(self, ssid: str, password: str | None) -> str:
        if not self._parent_surface():
            return render_blank("Not available right now.")
        ok, message = wifi_adapter.connect(ssid, password)
        return render_wifi(self._wifi_view(message), osk=self._osk())

    def wifi_forget(self, name: str) -> str:
        if not self._parent_surface():
            return render_blank("Not available right now.")
        ok, message = wifi_adapter.forget(name)
        return render_wifi(self._wifi_view(message), osk=self._osk())

    def wifi_rescan(self) -> str:
        return render_wifi(self._wifi_view(), osk=self._osk())

    def poweroff(self) -> str:
        if not self._parent_surface():
            return render_blank("Not available right now.")
        subprocess.run(["systemctl", "poweroff"], check=False)
        return render_poweroff()

    def wifi_portal(self) -> str:
        if not self._parent_surface():
            return render_blank("Not available right now.")
        if self._controller is not None:
            GLib.idle_add(self._controller.open_portal_browser)
        return render_portal_opened()


def compose_launcher(
    catalog: CatalogService | None,
    sessions: TrialSessionService | None,
    monitor_factory=None,
    server: UiServer | None = None,
    config: dict[str, object] | None = None,
    usage: ScreenTimeService | None = None,
) -> tuple[LauncherWindow, AppController]:
    window = LauncherWindow()
    controller = AppController(
        window,
        config or {},
        server=server,
        catalog=catalog,
        sessions=sessions,
        usage=usage,
    )
    window.on_webview_close = controller.webview_closed
    window.on_navigated = controller.web_navigated
    if monitor_factory is not None:
        try:
            controller.monitor = monitor_factory(controller.on_gesture)
        except Exception as exc:  # noqa: BLE001 - input must never kill the tiles
            print(f"input: unavailable ({exc})", file=sys.stderr, flush=True)
    return window, controller


def _build_catalog_and_sessions():
    db = open_database(migrations=MIGRATIONS)
    report = import_catalog(db, BootstrapCatalogSource(Path(BOOTSTRAP)))
    print(
        f"catalog import: +{report.added} ~{report.updated} "
        f"={report.unchanged} kept {report.preserved_local} purged {report.purged}",
        file=sys.stderr,
        flush=True,
    )
    # The nine slots must exist for parent selection (Home Child) to work at
    # all: seed exactly once from the trusted config. Parent replacements are
    # never touched; a broken trusted config must not disable the kiosk.
    try:
        if seed_home(db, Path(CONFIG)):
            print("home seed: nine slots created", file=sys.stderr, flush=True)
    except (StorageError, ValidationError) as exc:
        print(f"home seed: skipped ({exc})", file=sys.stderr, flush=True)
    catalog = CatalogService(CatalogRepository(db))
    sessions = TrialSessionService(
        SessionRepository(db),
        call_later=lambda seconds, fn: GLib.timeout_add_seconds(seconds, fn),
        cancel_later=GLib.source_remove,
    )
    return catalog, sessions, db


def main() -> None:
    # Startup banner: makes stale-deploy diagnosis trivial (the legacy launcher
    # printed nothing on success, so an empty log looked identical to a hang).
    print("leo-kiosk: starting (web UI build)", file=sys.stderr, flush=True)
    try:
        catalog, sessions, db = _build_catalog_and_sessions()
    except Exception as exc:  # noqa: BLE001 - storage must never kill the tiles
        print(
            f"catalog unavailable ({exc}); running with tiles only",
            file=sys.stderr,
            flush=True,
        )
        catalog, sessions = None, None
    config = _load_config(CONFIG)

    def monitor_factory(on_action):
        from leo_kiosk.adapters.input import VolumeInputMonitor, discover_volume_sources

        sources, errors = discover_volume_sources()
        for error in errors:
            print(f"input: {error}", file=sys.stderr, flush=True)
        if not sources:
            print(
                "input: no volume devices readable; gestures disabled", file=sys.stderr, flush=True
            )
            return None
        monitor = VolumeInputMonitor(sources, on_action)
        monitor.start()
        print(f"input: watching {len(sources)} volume device(s)", file=sys.stderr, flush=True)
        return monitor

    server: UiServer | None = None
    try:
        server = UiServer(WebUIPages(default_database_path(), config))
    except Exception as exc:  # noqa: BLE001 - web UI must never kill the tiles
        print(f"ui server: unavailable ({exc})", file=sys.stderr, flush=True)

    window, controller = compose_launcher(
        catalog, sessions, monitor_factory, server=server, config=config,
        usage=ScreenTimeService(
            ChildRepository(db),
            ScreenTimeRepository(db),
            GamePlaytimeRepository(db),
        )
        if catalog is not None
        else None,
    )
    if server is not None:
        server.pages._controller = controller  # bridge after compose
        server.start()
        print(
            f"ui server: {server.base}/parent",
            file=sys.stderr,
            flush=True,
        )
        controller._navigate(Route.CHILD_HOME)  # initial page
    if sessions is not None:
        sessions.on_finished = lambda token, game_id, outcome: controller.trial_finished(
            game_id, outcome.value
        )
    try:
        Gtk.main()
    except KeyboardInterrupt:
        sys.exit(0)
