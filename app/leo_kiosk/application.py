"""Application wiring: catalog, sessions, tile launches, the kiosk web UI.

Every screen is an HTML page on the loopback server (adapters/ui_server.py)
shown in one WebKitGTK view (ui/window.py). The server thread renders; web
actions are marshalled to the GTK main thread with GLib.idle_add; the launch
engine (services/tile_launch.py) owns process lifetime exactly as the legacy
GTK launcher did.
"""

import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from uuid import UUID

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gtk  # noqa: E402

from leo_kiosk.adapters import wifi as wifi_adapter  # noqa: E402
from leo_kiosk.adapters.battery import read_battery  # noqa: E402
from leo_kiosk.adapters.browser_profiles import BrowserProfiles  # noqa: E402
from leo_kiosk.adapters.catalog_source import BootstrapCatalogSource  # noqa: E402
from leo_kiosk.adapters.firefox import build_firefox_command  # noqa: E402
from leo_kiosk.adapters.ui_server import (  # noqa: E402
    ReviewRow,
    UiServer,
    WifiView,
    load_videos,
    render_blank,
    render_child_state,
    render_exit,
    render_home,
    render_menu,
    render_portal_opened,
    render_poweroff,
    render_review,
    render_state,
    render_videos,
    render_wifi,
)
from leo_kiosk.adapters.video_player import build_video_command  # noqa: E402
from leo_kiosk.domain.errors import ValidationError  # noqa: E402
from leo_kiosk.domain.gestures import (  # noqa: E402
    DEFAULT_PATTERNS,
    PARENT_SURFACE_PATTERNS,
    REVIEW_TRIAL_PATTERNS,
    GestureAction,
)
from leo_kiosk.domain.sessions import LaunchOutcome  # noqa: E402
from leo_kiosk.services.catalog import CatalogService  # noqa: E402
from leo_kiosk.services.navigation import Route  # noqa: E402
from leo_kiosk.services.sessions import TrialSessionService  # noqa: E402
from leo_kiosk.services.tile_launch import TileLauncher, play  # noqa: E402
from leo_kiosk.storage.catalog import CatalogRepository  # noqa: E402
from leo_kiosk.storage.catalog_import import import_catalog  # noqa: E402
from leo_kiosk.storage.database import default_database_path, open_database  # noqa: E402
from leo_kiosk.storage.home import HomeRepository  # noqa: E402
from leo_kiosk.storage.schema import MIGRATIONS  # noqa: E402
from leo_kiosk.storage.sessions import SessionRepository  # noqa: E402
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

URL_FOR = {
    Route.CHILD_HOME: "/",
    Route.PARENT_HOME: "/parent",
    Route.REVIEW_LIST: "/review",
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


def _popen(*args, **kwargs):
    import subprocess

    return subprocess.Popen(*args, **kwargs)


def _child_watch(process, callback):
    """Poll-based exit watch; avoids waitpid races with Popen."""

    def _poll():
        if process.poll() is not None:
            callback(process.pid, process.returncode)
            return False
        return True

    return GLib.timeout_add(500, _poll)


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
        profiles: BrowserProfiles | None = None,
    ) -> None:
        self.window = window
        self.config = config
        self.server = server
        self.catalog = catalog
        self.sessions = sessions
        self.monitor = monitor
        self.profiles = profiles
        self.route = Route.CHILD_HOME
        self.trial_token: UUID | None = None
        self.trial_web = False
        self.web_outcomes: dict[UUID, str] = {}
        self.portal_proc = None
        self.portal_profile = None
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
            on_corner_exit=Gtk.main_quit,
        )

    # --- gestures ---------------------------------------------------------
    def on_gesture(self, action: GestureAction) -> None:
        in_trial = self.trial_token is not None
        if not self.window.is_showing() and not in_trial:
            return  # legacy app foregrounded; only the trial return passes
        if in_trial:
            # Any recognized gesture ends the trial: Down/Up returns to this
            # game's editor, Up/Down/Down goes to the parent home. Stopping
            # the session drives the visible change via the finish callback.
            outcome = (
                LaunchOutcome.PARENT_REQUEST
                if action is GestureAction.ENTER_PARENT
                else LaunchOutcome.RETURN_GESTURE
            )
            token = self.trial_token
            self.trial_token = None  # further gestures wait for the finish
            self.sessions.stop(token, outcome)
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

    def corner_tap(self) -> None:
        """Web action: a tap in the invisible parent corner."""
        self.launcher.corner_tap()

    def webview_closed(self) -> None:
        """The view closed itself (/exit page): return to the child home."""
        self.route = Route.CHILD_HOME
        self._navigate(Route.CHILD_HOME)

    # --- status -----------------------------------------------------------
    def say(self, text: str, seconds: float = STATUS_SECONDS) -> None:
        self._status = (text, time.monotonic() + seconds)

    def status_text(self) -> str:
        text, deadline = self._status
        return text if time.monotonic() < deadline else ""

    # --- launch engine callbacks -----------------------------------------
    def _on_app_launch(self) -> None:
        self.route = Route.CHILD_ACTIVITY
        self.window.hide()

    def _on_app_exit(self) -> None:
        route = Route.VIDEOS if self._return_path == "/videos" else Route.CHILD_HOME
        self._return_path = "/"
        self._show(route)
        self.window.show()

    # --- review trials (launched from the web UI) -------------------------
    def request_web_trial(self, game_id: UUID) -> None:
        """Main-thread bridge: start a trial launched from the web UI."""
        if self.trial_token is not None or self.catalog is None:
            return
        try:
            url = self.catalog.get_entry(game_id).playable_url
        except (LookupError, ValueError):
            return
        token = self.sessions.start_trial(url, game_id)
        self.trial_token = token
        self.route = Route.REVIEW_TRIAL
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(REVIEW_TRIAL_PATTERNS)
        self.window.hide()

    def web_trial_state(self, game_id: UUID) -> tuple[bool, str | None]:
        running = self.trial_token is not None
        outcome = self.web_outcomes.get(game_id)
        return running, outcome

    def trial_finished(self, game_id: UUID, outcome_value: str) -> None:
        self.trial_token = None
        self.web_outcomes[game_id] = outcome_value
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(DEFAULT_PATTERNS)
        self.route = Route.PARENT_HOME
        self._use_patterns(Route.PARENT_HOME)
        if self.server is not None:
            self.window.navigate(self.server.base + f"/review/{game_id}")
        self.window.show()

    # --- portal (captive-portal sign-in; Firefox, above the web UI) -------
    def open_portal_browser(self) -> None:
        """Sign-in window for a captive portal; Down/Up closes it again."""
        if self.portal_proc is not None:
            return
        profile = self.profiles.new_trial_profile()
        self.portal_profile = profile
        cmd = build_firefox_command(
            "firefox", profile, wifi_adapter.CONNECTIVITY_CHECK_URL
        )
        self.portal_proc = _popen(cmd, start_new_session=True)
        try:
            fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(str(self.portal_proc.pid))
        except OSError:
            pass
        GLib.timeout_add(500, self._watch_portal_browser)

    def _watch_portal_browser(self) -> bool:
        if self.portal_proc.poll() is None:
            return True
        if self.portal_profile is not None:
            self.profiles.cleanup_profile(self.portal_profile)
            self.portal_profile = None
        try:
            os.unlink(STATE)
        except OSError:
            pass
        self.portal_proc = None
        return False

    def _tiles_by_id(self) -> dict[str, dict[str, object]]:
        tiles = self.config.get("tiles", [])
        return {str(t["id"]): t for t in tiles if isinstance(t, dict) and "id" in t}


class WebUIPages:
    """All kiosk pages rendered from the real services in the server thread.

    The server thread owns its own read-only catalog connection; actions are
    marshalled to the GTK main thread because the session and launch engines
    drive GLib schedulers and process watches there.
    """

    def __init__(self, db_path, config: dict[str, object], controller=None):
        self._db_path = db_path
        self._config = config
        self._controller = controller
        self._conn = None
        self._catalog: CatalogService | None = None

    def _service(self) -> CatalogService:
        if self._conn is None:
            self._conn = open_database(self._db_path)
            selected = HomeRepository(self._conn).selected_game_ids()
            self._catalog = CatalogService(CatalogRepository(self._conn), selected)
        return self._catalog

    def _name(self, game_id: UUID) -> str:
        try:
            return self._service().get_entry(game_id).display_name
        except (LookupError, ValueError):
            return "Game"

    # --- child pages ------------------------------------------------------
    def home(self) -> str:
        tiles = self._config.get("tiles", [])
        return render_home(str(self._config.get("title", "")), list(tiles))

    def videos(self) -> str:
        try:
            return render_videos(load_videos(KIOSK_VIDEOS))
        except (OSError, ValueError) as exc:
            # Missing/broken catalog must degrade to a page, not a dropped
            # connection (the handler thread would otherwise die mid-request).
            print(f"videos: catalog unavailable ({exc})", file=sys.stderr, flush=True)
            return render_blank("No videos right now. Ask Papa to fix this one!")

    def child_state(self) -> str:
        status = ""
        if self._controller is not None:
            status = self._controller.status_text()
        return_status = status  # read once; battery read may take a moment
        return render_child_state(return_status, read_battery())

    def launch_tile(self, tile_id: str) -> str:
        if self._controller is not None:
            GLib.idle_add(self._controller.launch_tile, tile_id)
        return render_blank("")

    def video_play(self, url: str) -> str:
        try:
            build_video_command(VIDEOS_SCRIPT, url)
        except ValidationError:
            return render_blank("This video cannot be played.")
        if self._controller is not None:
            GLib.idle_add(self._controller.play_video, url)
        return render_blank("")

    def corner(self) -> str:
        if self._controller is not None:
            GLib.idle_add(self._controller.corner_tap)
        return render_blank("")

    # --- parent pages -----------------------------------------------------
    def menu(self) -> str:
        return render_menu()

    def review(self) -> str:
        try:
            rows = [
                ReviewRow(str(e.game_id), e.display_name, e.status.value, e.rating)
                for e in self._service().list_review_entries()
            ]
        except Exception:  # noqa: BLE001 - catalog failure must not kill the page
            return render_review([])
        return render_review(rows)

    def exit(self) -> str:
        return render_exit()

    def review_launch(self, game_id: UUID) -> str:
        if self._controller is not None:
            GLib.idle_add(self._controller.request_web_trial, game_id)
        return render_state(self._name(game_id), running=True, outcome=None)

    def review_state(self, game_id: UUID) -> str:
        running = False
        outcome = None
        if self._controller is not None:
            running, outcome = self._controller.web_trial_state(game_id)
        return render_state(self._name(game_id), running, outcome)

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
        return render_wifi(self._wifi_view())

    def wifi_connect(self, ssid: str, password: str | None) -> str:
        ok, message = wifi_adapter.connect(ssid, password)
        return render_wifi(self._wifi_view(message))

    def wifi_forget(self, name: str) -> str:
        ok, message = wifi_adapter.forget(name)
        return render_wifi(self._wifi_view(message))

    def wifi_rescan(self) -> str:
        return render_wifi(self._wifi_view())

    def poweroff(self) -> str:
        subprocess.run(["systemctl", "poweroff"], check=False)
        return render_poweroff()

    def wifi_portal(self) -> str:
        if self._controller is not None:
            GLib.idle_add(self._controller.open_portal_browser)
        return render_portal_opened()


def compose_launcher(
    catalog: CatalogService | None,
    sessions: TrialSessionService | None,
    monitor_factory=None,
    profiles: BrowserProfiles | None = None,
    server: UiServer | None = None,
    config: dict[str, object] | None = None,
) -> tuple[LauncherWindow, AppController]:
    window = LauncherWindow()
    controller = AppController(
        window,
        config or {},
        server=server,
        catalog=catalog,
        sessions=sessions,
        profiles=profiles,
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
    catalog = CatalogService(CatalogRepository(db))
    data_home = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    profiles = BrowserProfiles(Path(data_home))
    sessions = TrialSessionService(
        SessionRepository(db),
        popen=_popen,
        profiles=profiles,
        call_later=lambda seconds, fn: GLib.timeout_add_seconds(seconds, fn),
        cancel_later=GLib.source_remove,
        watch_process=_child_watch,
    )
    return catalog, sessions, profiles, db


def main() -> None:
    # Startup banner: makes stale-deploy diagnosis trivial (the legacy launcher
    # printed nothing on success, so an empty log looked identical to a hang).
    print("leo-kiosk: starting (web UI build)", file=sys.stderr, flush=True)
    try:
        catalog, sessions, profiles, _db = _build_catalog_and_sessions()
    except Exception as exc:  # noqa: BLE001 - storage must never kill the tiles
        print(
            f"catalog unavailable ({exc}); running with tiles only",
            file=sys.stderr,
            flush=True,
        )
        catalog, sessions, profiles = None, None, None
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
        catalog, sessions, monitor_factory, profiles=profiles,
        server=server, config=config,
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
