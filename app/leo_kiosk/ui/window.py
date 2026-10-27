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
from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: E402

# Average of the child-page CSS gradient (see CHILD_CSS in ui_server.py);
# a flat first-paint color that lands mid-gradient so no frame flashes.
APP_BACKGROUND = (0.090, 0.129, 0.239)  # #17213d


class LauncherWindow:
    """The kiosk display surface. One view, one page at a time."""

    def __init__(self):
        # Registered first: the toplevel must never paint an unstyled (white)
        # frame, which happens if the provider lands after show_all().
        screen_provider = Gtk.CssProvider()
        screen_provider.load_from_data(b"window { background: #17213d; }")
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            screen_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self.win = Gtk.Window()
        self.win.connect("destroy", Gtk.main_quit)
        self.win.set_title("Leo")
        self.view = WebKit2.WebView.new_with_context(WebKit2.WebContext.new_ephemeral())
        background = Gdk.RGBA()
        background.red, background.green, background.blue, background.alpha = (
            *APP_BACKGROUND, 1.0
        )
        self.view.set_background_color(background)  # no white first-paint flash
        self.on_webview_close = None
        self.on_navigated = None  # called with the committed URI on every load
        self.view.connect("close", lambda *_args: self._closed())
        self.view.connect("load-changed", self._load_changed)
        # Touch-only kiosk: no context menu (touchpad right-click, touch
        # long-press); returning True stops the default handler.
        self.view.connect("context-menu", lambda *_args: True)

        # Loading overlay above the view: game pages boot on their own dark
        # background for seconds; the overlay covers that with ours.
        self._loader = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            spacing=12,
        )
        loader_context = self._loader.get_style_context()
        loader_context.add_class("loader")
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b".loader { background: #17213d; } "
            b".loader label { color: #ffb000; font-size: 34px; font-weight: 700; }"
        )
        Gtk.StyleContext.add_provider(
            loader_context, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._loader_label = Gtk.Label(label="Starting...")
        self._loader.pack_start(self._loader_label, False, False, 0)
        self._loader.set_no_show_all(True)

        self._overlay = Gtk.Overlay()
        self._overlay.add(self.view)
        self._overlay.add_overlay(self._loader)
        self._loader_hide_handle = None
        self.win.add(self._overlay)
        self.win.fullscreen()
        self.win.show_all()

        # Force a blank pointer at the GDK layer. WebKitGTK takes the cursor
        # from third-party pages' own CSS via hit-testing and we cannot inject
        # into them, so we re-assert a blank cursor on every pointer event;
        # WebKit only re-asserts its own choice when the hit-test type changes.
        self._blank_cursor = Gdk.Cursor.new_for_display(
            Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR
        )
        self.view.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.win.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.view.connect("map", self._force_blank_cursor)
        self.view.connect("enter-notify-event", self._force_blank_cursor)
        self.view.connect("motion-notify-event", self._force_blank_cursor)
        self.win.connect("map", self._on_window_map)
        self.win.connect("enter-notify-event", self._force_blank_cursor)
        self.win.connect("motion-notify-event", self._force_blank_cursor)

    def _on_window_map(self, *_args) -> None:
        """Dark GDK background before the first widget draw + boot loader."""
        background = Gdk.RGBA()
        background.red, background.green, background.blue, background.alpha = (
            *APP_BACKGROUND, 1.0
        )
        for gdk_window in (self.win.get_window(), self.view.get_window()):
            if gdk_window is not None:
                gdk_window.set_background_rgba(background)
        self.show_loader("Loading...")

    def _force_blank_cursor(self, *_args) -> None:
        """Re-assert the blank pointer; False keeps GTK event flow intact."""
        for gdk_window in (self.win.get_window(), self.view.get_window()):
            if gdk_window is not None:
                gdk_window.set_cursor(self._blank_cursor)

    def show_loader(self, text: str = "Starting...") -> None:
        """Cover the view while a navigation paints; capped at ten seconds."""
        self._loader_label.set_text(text)
        self._loader.show()
        if self._loader_hide_handle is None:
            self._loader_hide_handle = GLib.timeout_add_seconds(
                10, lambda: self.hide_loader() or False
            )

    def hide_loader(self) -> None:
        if self._loader_hide_handle is not None:
            GLib.source_remove(self._loader_hide_handle)
            self._loader_hide_handle = None
        self._loader.hide()

    def _closed(self) -> None:
        if self.on_webview_close is not None:
            self.on_webview_close()

    def capture_snapshot(self, on_done) -> None:
        """Snapshot the view's current frame; on_done(surface | None).

        A snapshot that fails (page still loading, view unmapped) calls
        on_done(None); gesture-side code treats that as a silent no-op.
        """

        def finished(view, result):
            try:
                surface = view.get_snapshot_finish(result)
            except GLib.Error:
                surface = None
            on_done(surface)

        self.view.get_snapshot(
            WebKit2.SnapshotOptions.NONE,
            WebKit2.SnapshotRegion.VISIBLE,
            None,
            finished,
        )

    def set_page_zoom(self, factor: float) -> None:
        """Whole-page zoom for fixed-size games (reset to 1.0 afterwards).

        WebKitGTK's default zoom mode scales the entire page (no
        text-only-zoom property on this build — setting it crashed the
        launcher on-device), so the zoom level alone gives a 1024x768
        canvas the full screen when it matches the recorded design size.
        """
        self.view.set_zoom_level(factor)

    def page_size(self) -> tuple[int, int]:
        """The (width, height) the game page is shown at (full monitor)."""
        screen = self.win.get_screen()
        return screen.get_width(), screen.get_height()

    def toast(self, message: str) -> None:
        """Small themed notification over the view for 500ms.

        Replaces the white screenshot flash, which was still easy to miss;
        the owner asked for a spoken-out toast instead.
        """
        import json

        script = (
            "(function(){var t=document.getElementById('toast');"
            "if(t){t.remove();}"
            "t=document.createElement('div');t.id='toast';"
            "t.textContent=" + json.dumps(message) + ";"
            "t.style.cssText='position:fixed;top:24px;left:50%;"
            "transform:translateX(-50%);background:#1b1b2f;color:#ffd43b;"
            "font-size:26px;font-weight:700;padding:16px 28px;"
            "border-radius:14px;border:2px solid #33323a;"
            "z-index:2147483647;pointer-events:none;';"
            "document.body.appendChild(t);"
            "setTimeout(function(){t.remove();},500);"
            "})()"
        )
        self.view.run_javascript(script, None, None)

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
