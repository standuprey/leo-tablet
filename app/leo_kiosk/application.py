"""Application wiring: catalog, sessions, parent mode, GTK main loop."""

import os
import sys
from pathlib import Path
from uuid import UUID

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gtk  # noqa: E402

from leo_kiosk.adapters.browser_profiles import BrowserProfiles  # noqa: E402
from leo_kiosk.adapters.catalog_source import BootstrapCatalogSource  # noqa: E402
from leo_kiosk.domain.gestures import (  # noqa: E402
    DEFAULT_PATTERNS,
    REVIEW_TRIAL_PATTERNS,
    GestureAction,
)
from leo_kiosk.services.catalog import CatalogService  # noqa: E402
from leo_kiosk.services.navigation import Route, enter_parent, return_gesture  # noqa: E402
from leo_kiosk.services.sessions import TrialSessionService  # noqa: E402
from leo_kiosk.storage.catalog import CatalogRepository  # noqa: E402
from leo_kiosk.storage.catalog_import import import_catalog  # noqa: E402
from leo_kiosk.storage.database import open_database  # noqa: E402
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
    ) -> None:
        self.window = window
        self.catalog = catalog
        self.sessions = sessions
        self.monitor = monitor
        self.route = Route.CHILD_HOME
        self.trial_token: UUID | None = None

    def on_gesture(self, action: GestureAction) -> None:
        in_trial = self.trial_token is not None
        if not self.window.is_showing() and not in_trial:
            return  # legacy app foregrounded; only the trial return passes
        if action is GestureAction.ENTER_PARENT:
            transition = enter_parent(self.route)
        else:
            transition = return_gesture(self.route)
        self.route = transition.route
        self.window.show_page(PAGE_FOR.get(transition.route, "child"))

    def exit_parent(self) -> None:
        transition = return_gesture(Route.PARENT_HOME)
        self.route = transition.route
        self.window.show_page("child")

    def _go(self, route: Route) -> None:
        self.route = route
        self.window.show_page(PAGE_FOR.get(route, "child"))

    def _on_app_launch(self) -> None:
        self.route = Route.CHILD_ACTIVITY

    def _on_app_exit(self) -> None:
        self.route = Route.CHILD_HOME
        self.window.show_page("child")

    # --- review flow ------------------------------------------------------
    def open_review(self) -> None:
        page = self.window.stack.get_child_by_name("review")
        for child in list(page.get_children()):
            page.remove(child)
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
        self.route = Route.REVIEW_EDITOR
        if self.monitor is not None:
            self.monitor.recognizer.use_patterns(DEFAULT_PATTERNS)
        name = "Game"
        if self.catalog is not None:
            try:
                name = self.catalog.get_entry(game_id).display_name
            except (LookupError, ValueError):
                pass
        editor = self.window.stack.get_child_by_name("editor")
        for child in list(editor.get_children()):
            editor.remove(child)
        editor.pack_start(
            build_editor_placeholder(name, f"Trial outcome: {outcome_value}"), True, True, 0
        )
        editor.show_all()
        self.window.win.show_all()
        self.window.win.fullscreen()


def compose_launcher(
    catalog: CatalogService | None,
    sessions: TrialSessionService | None,
    monitor_factory=None,
) -> tuple[LauncherWindow, AppController]:
    window = LauncherWindow(CONFIG, STATE, VOICES)
    controller = AppController(window, catalog=catalog, sessions=sessions)
    window.set_editor_page(build_editor_placeholder("", None))
    window.attach_pages(
        {
            "parent": build_parent_screen(
                on_review=controller.open_review,
                on_wifi=lambda: controller._go(Route.WIFI),
                on_exit=controller.exit_parent,
            ),
            "review": _placeholder_page("REVIEW"),
            "wifi": _placeholder_page("WIFI"),
        }
    )
    window.set_trial_launcher(controller._on_app_launch, controller._on_app_exit)
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
        f"={report.unchanged} kept {report.preserved_local}",
        file=sys.stderr,
        flush=True,
    )
    catalog = CatalogService(CatalogRepository(db))
    data_home = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    sessions = TrialSessionService(
        SessionRepository(db),
        popen=_popen,
        profiles=BrowserProfiles(Path(data_home)),
        call_later=lambda seconds, fn: GLib.timeout_add_seconds(seconds, fn),
        cancel_later=GLib.source_remove,
        watch_process=_child_watch,
    )
    return catalog, sessions


def main() -> None:
    try:
        catalog, sessions = _build_catalog_and_sessions()
    except Exception as exc:  # noqa: BLE001 - storage must never kill the tiles
        print(
            f"catalog unavailable ({exc}); running with legacy tiles only",
            file=sys.stderr,
            flush=True,
        )
        catalog, sessions = None, None

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

    window, controller = compose_launcher(catalog, sessions, monitor_factory)
    if sessions is not None:
        sessions.on_finished = lambda token, game_id, outcome: controller.trial_finished(
            game_id, outcome.value
        )

    try:
        Gtk.main()
    except KeyboardInterrupt:
        sys.exit(0)
