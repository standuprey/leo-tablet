"""Application wiring: catalog, sessions, parent mode, GTK main loop."""

import os
import signal
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gtk  # noqa: E402

from leo_kiosk.adapters import wifi as wifi_adapter  # noqa: E402
from leo_kiosk.adapters.browser_profiles import BrowserProfiles  # noqa: E402
from leo_kiosk.adapters.catalog_source import BootstrapCatalogSource  # noqa: E402
from leo_kiosk.adapters.firefox import build_firefox_command  # noqa: E402
from leo_kiosk.adapters.parent_server import (  # noqa: E402
    ParentServer,
    ReviewRow,
    WifiView,
    render_exit,
    render_menu,
    render_portal_opened,
    render_poweroff,
    render_review,
    render_state,
    render_wifi,
)
from leo_kiosk.domain.gestures import (  # noqa: E402
    DEFAULT_PATTERNS,
    REVIEW_TRIAL_PATTERNS,
    GestureAction,
)
from leo_kiosk.domain.sessions import LaunchOutcome  # noqa: E402
from leo_kiosk.services.catalog import CatalogService  # noqa: E402
from leo_kiosk.services.navigation import Route, return_gesture  # noqa: E402
from leo_kiosk.services.sessions import TrialSessionService  # noqa: E402
from leo_kiosk.storage.catalog import CatalogRepository  # noqa: E402
from leo_kiosk.storage.catalog_import import import_catalog  # noqa: E402
from leo_kiosk.storage.database import default_database_path, open_database  # noqa: E402
from leo_kiosk.storage.home import HomeRepository  # noqa: E402
from leo_kiosk.storage.schema import MIGRATIONS  # noqa: E402
from leo_kiosk.storage.sessions import SessionRepository  # noqa: E402
from leo_kiosk.ui.parent_home import build_parent_screen  # noqa: E402
from leo_kiosk.ui.review_list import build_editor_placeholder, build_review_list  # noqa: E402
from leo_kiosk.ui.window import LauncherWindow  # noqa: E402

# HERE is the app/ directory (parent of the leo_kiosk package). tiles.json is
# installed flat next to the legacy scripts on the tablet; in this repo the
# canonical copy lives in config/ (see install-kiosk.sh).
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "tiles.json")
VOICES = os.path.join(HERE, "voices")
STATE = os.path.join(HERE, ".app-pid")
BOOTSTRAP = os.path.join(HERE, "catalog", "bootstrap.json")

PAGE_FOR = {
    Route.CHILD_HOME: "child",
    Route.PARENT_HOME: "parent",
    Route.REVIEW_LIST: "review",
    Route.REVIEW_EDITOR: "editor",
    Route.WIFI: "wifi",
    Route.PORTAL: "wifi",
}


def _placeholder_page(title: str) -> Gtk.Box:
    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=24,
        valign=Gtk.Align.CENTER,
        halign=Gtk.Align.CENTER,
    )
    label = Gtk.Label(label=title)
    label.get_style_context().add_class("parent-title")
    hint = Gtk.Label(
        label="This screen ships in a later deploy.\nReturn with: Volume Down, Down, Up"
    )
    hint.get_style_context().add_class("status")
    box.pack_start(label, False, False, 0)
    box.pack_start(hint, False, False, 0)
    return box


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
    """Routes gestures and tiles through navigation to visible pages.

    Limitation until session ownership lands fully: entering parent mode from
    inside a running legacy app is not wired (gestures are ignored while the
    launcher is hidden), but a review trial can always be left with Down/Up.
    """

    def __init__(
        self,
        window: LauncherWindow,
        catalog: CatalogService | None = None,
        sessions: TrialSessionService | None = None,
        monitor=None,
        profiles=None,
        parent_server=None,
    ) -> None:
        self.window = window
        self.catalog = catalog
        self.sessions = sessions
        self.monitor = monitor
        self.profiles = profiles
        self.parent_server = parent_server
        self.route = Route.CHILD_HOME
        self.trial_token: UUID | None = None
        self.trial_web = False
        self.parent_profile = None
        self.parent_proc = None
        self.web_outcomes: dict[UUID, str] = {}
        self.portal_proc = None
        self.portal_profile = None

    def on_gesture(self, action: GestureAction) -> None:
        in_trial = self.trial_token is not None
        if not self.window.is_showing() and not in_trial:
            return  # legacy app foregrounded; only the trial return passes
        if in_trial:
            # Any recognized gesture ends the trial: Down/Up returns to this
            # game's editor, Up/Down/Down goes to the parent home. Stopping
            # the session drives the visible change via the exit callback;
            # show_page() on a hidden window would do nothing.
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
            self.open_parent_browser()
            return
        transition = return_gesture(self.route)
        self.route = transition.route
        self.window.show_page(PAGE_FOR.get(transition.route, "child"))

    def exit_parent(self) -> None:
        transition = return_gesture(Route.PARENT_HOME)
        self.route = transition.route
        self.window.show_page("child")

    def power_off(self) -> None:
        """Parent-mode action: power the tablet off via logind.

        The active session may power off without polkit interaction; the
        request goes through systemd so the shutdown is clean.
        """
        subprocess.run(["systemctl", "poweroff"], check=False)

    def _go(self, route: Route) -> None:
        self.route = route
        self.window.show_page(PAGE_FOR.get(route, "child"))

    def _on_app_launch(self) -> None:
        self.route = Route.CHILD_ACTIVITY

    def _on_app_exit(self) -> None:
        self.route = Route.CHILD_HOME
        self.window.show_page("child")

    # --- web parent mode --------------------------------------------------
    def open_parent_browser(self) -> None:
        """Swap the child home for the parent browser (gesture = the gate)."""
        if self.parent_proc is not None or self.parent_server is None:
            return
        profile = self.profiles.new_trial_profile()
        self.parent_profile = profile
        cmd = build_firefox_command("firefox", profile, self.parent_server.url)
        self.parent_proc = _popen(cmd, start_new_session=True)
        try:
            fd = os.open(self.window.state_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(str(self.parent_proc.pid))
        except OSError:
            pass
        self.window.win.hide()
        self.route = Route.PARENT_HOME
        GLib.timeout_add(500, self._watch_parent_browser)

    def _watch_parent_browser(self) -> bool:
        if self.parent_proc.poll() is None:
            return True
        if self.parent_profile is not None:
            self.profiles.cleanup_profile(self.parent_profile)
            self.parent_profile = None
        try:
            os.unlink(self.window.state_path)
        except OSError:
            pass
        self.parent_proc = None
        self.route = Route.CHILD_HOME
        self.window.win.show_all()
        self.window.win.fullscreen()
        return False

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
        self.trial_web = True
        self.route = Route.REVIEW_TRIAL
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(REVIEW_TRIAL_PATTERNS)
        self.window.win.hide()

    def web_trial_state(self, game_id: UUID) -> tuple[bool, str | None]:
        running = self.trial_token is not None
        outcome = self.web_outcomes.get(game_id)
        return running, outcome

    def exit_parent_browser(self) -> None:
        """Server-driven exit: the /exit page closed the kiosk window."""
        if self.parent_proc is not None:
            os.killpg(self.parent_proc.pid, signal.SIGTERM)

    def open_portal_browser(self) -> None:
        """Sign-in window for a captive portal; Down/Up closes it again."""
        if self.parent_proc is None or self.portal_proc is not None:
            return
        profile = self.profiles.new_trial_profile()
        self.portal_profile = profile
        cmd = build_firefox_command(
            "firefox", profile, wifi_adapter.CONNECTIVITY_CHECK_URL
        )
        self.portal_proc = _popen(cmd, start_new_session=True)
        try:
            fd = os.open(
                self.window.state_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
            )
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
        # Hand .app-pid back to the parent browser so Down/Up exits it again.
        if self.parent_proc is not None:
            try:
                fd = os.open(
                    self.window.state_path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    0o600,
                )
                with os.fdopen(fd, "w") as f:
                    f.write(str(self.parent_proc.pid))
            except OSError:
                pass
        self.portal_proc = None
        return False

    # --- review flow (GTK parity path; the web UI replaces it) ------------
    def open_review(self) -> None:
        page = self.window.stack.get_child_by_name("review")
        for child in list(page.get_children()):
            page.remove(child)
        page.set_halign(Gtk.Align.FILL)  # placeholder was centered; the list must expand
        page.set_valign(Gtk.Align.FILL)
        entries = self.catalog.list_review_entries() if self.catalog else ()
        page.pack_start(build_review_list(entries, self._start_trial), True, True, 0)
        page.show_all()
        self._go(Route.REVIEW_LIST)

    def _start_trial(self, game_id: UUID, url: str) -> None:
        token = self.sessions.start_trial(url, game_id)
        self.trial_token = token
        self.route = Route.REVIEW_TRIAL
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(REVIEW_TRIAL_PATTERNS)
        self.window.win.hide()

    def trial_finished(self, game_id: UUID, outcome_value: str) -> None:
        self.trial_token = None
        if self.trial_web:
            # Web-launched trial: the parent browser page polls the state
            # endpoint and renders the interim editor; no GTK pages here.
            self.trial_web = False
            self.web_outcomes[game_id] = outcome_value
            if self.monitor is not None:
                self.monitor.recognizer.use_patterns(DEFAULT_PATTERNS)
            self.route = Route.PARENT_HOME
            return
        if outcome_value == LaunchOutcome.PARENT_REQUEST.value:
            self.route = Route.PARENT_HOME
        else:
            self.route = Route.REVIEW_EDITOR
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(DEFAULT_PATTERNS)
        name = "Game"
        if self.catalog is not None:
            try:
                name = self.catalog.get_entry(game_id).display_name
            except (LookupError, ValueError):
                pass
        target_page = PAGE_FOR.get(self.route, "child")
        self.window.show_page(target_page)  # route decides, not the pre-trial page
        if self.route is Route.REVIEW_EDITOR:
            editor = self.window.stack.get_child_by_name(target_page)
            for child in list(editor.get_children()):
                editor.remove(child)
            editor.pack_start(
                build_editor_placeholder(name, f"Trial outcome: {outcome_value}"), True, True, 0
            )
            editor.show_all()
        self.window.win.show_all()
        self.window.win.fullscreen()


class WebParentPages:
    """Parent pages rendered from the real services in the server thread.

    The server thread owns its own read-only catalog connection; trial
    launches are marshalled to the GTK main thread because the session
    service drives GLib schedulers and process watches there.
    """

    def __init__(self, db_path, controller: "AppController | None" = None):
        self._db_path = db_path
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

    def menu(self) -> str:
        return render_menu()

    def review(self) -> str:
        rows = [
            ReviewRow(str(e.game_id), e.display_name, e.status.value, e.rating)
            for e in self._service().list_review_entries()
        ]
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

    def wifi_rescan(self) -> str:
        return render_wifi(self._wifi_view())

    def wifi_connect(self, ssid: str, password: str | None) -> str:
        ok, message = wifi_adapter.connect(ssid, password)
        return render_wifi(self._wifi_view(message))

    def wifi_forget(self, name: str) -> str:
        ok, message = wifi_adapter.forget(name)
        return render_wifi(self._wifi_view(message))

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
    parent_server: ParentServer | None = None,
) -> tuple[LauncherWindow, AppController]:
    window = LauncherWindow(CONFIG, STATE, VOICES)
    controller = AppController(
        window, catalog=catalog, sessions=sessions, profiles=profiles,
        parent_server=parent_server,
    )
    editor_page = build_editor_placeholder("", None)
    window.attach_pages(
        {
            "parent": build_parent_screen(
                on_review=controller.open_review,
                on_wifi=lambda: controller._go(Route.WIFI),
                on_exit=controller.exit_parent,
                on_power=controller.power_off,
            ),
            "review": _placeholder_page("REVIEW"),
            "wifi": _placeholder_page("WIFI"),
            "editor": editor_page,
        }
    )
    window.set_launch_state_callback(controller._on_app_launch, controller._on_app_exit)
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
    print("leo-kiosk: starting (parent-mode build)", file=sys.stderr, flush=True)
    try:
        catalog, sessions, profiles, _db = _build_catalog_and_sessions()
    except Exception as exc:  # noqa: BLE001 - storage must never kill the tiles
        print(
            f"catalog unavailable ({exc}); running with legacy tiles only",
            file=sys.stderr,
            flush=True,
        )
        catalog, sessions, profiles = None, None, None

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

    parent_server = None
    if catalog is not None:
        try:
            parent_server = ParentServer(WebParentPages(default_database_path()))
        except Exception as exc:  # noqa: BLE001 - web UI must never kill the tiles
            print(f"parent server: unavailable ({exc})", file=sys.stderr, flush=True)

    window, controller = compose_launcher(
        catalog, sessions, monitor_factory, profiles=profiles,
        parent_server=parent_server,
    )
    if parent_server is not None:
        parent_server.pages._controller = controller  # bridge after compose
        parent_server.start()
        print(
            f"parent server: http://127.0.0.1:{parent_server.port}/parent",
            file=sys.stderr,
            flush=True,
        )
    if sessions is not None:
        sessions.on_finished = lambda token, game_id, outcome: controller.trial_finished(
            game_id, outcome.value
        )

    try:
        Gtk.main()
    except KeyboardInterrupt:
        sys.exit(0)
