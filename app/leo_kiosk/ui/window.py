"""Kiosk window: one fullscreen WebKitGTK view of the loopback UI server.

Every screen — child home, Videos, parent mode — is an HTML page served by
adapters/ui_server.py; this window only hosts the view and forwards the
WebKit close signal (the /exit and /poweroff pages call window.close()).
The legacy GTK widget stack it replaces lives in git history; the launch
behavior it used to own now lives in services/tile_launch.py.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")  # pin 3.x; gtk4's Gdk 4.0 must not load first
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2  # noqa: E402


class LauncherWindow:
    """The kiosk display surface. One view, one page at a time."""

    def __init__(self):
        self.win = Gtk.Window()
        self.win.connect("destroy", Gtk.main_quit)
        self.win.set_title("Leo")
        self.view = WebKit2.WebView.new_with_context(WebKit2.WebContext.new_ephemeral())
        self.on_webview_close = None
        self.on_navigated = None  # called with the committed URI on every load
        self.view.connect("close", lambda *_args: self._closed())
        self.view.connect("load-changed", self._load_changed)
        # Touch-only kiosk: no context menu (touchpad right-click, touch
        # long-press); returning True stops the default handler.
        self.view.connect("context-menu", lambda *_args: True)
        self.win.add(self.view)
        self.win.fullscreen()
        self.win.show_all()

    def _closed(self) -> None:
        if self.on_webview_close is not None:
            self.on_webview_close()

    def _load_changed(self, _view, event) -> None:
        if self.on_navigated is None or event != WebKit2.LoadEvent.COMMITTED:
            return
        uri = self.view.get_uri()
        if uri:
            self.on_navigated(uri)

    def navigate(self, url: str) -> None:
        """Show a UI page; the caller passes a full loopback URL."""
        self.view.load_uri(url)

    def hide(self) -> None:
        self.win.hide()

    def show(self) -> None:
        self.win.show_all()
        self.win.fullscreen()
        self.win.present()

    def is_showing(self) -> bool:
        return self.win.get_visible()
