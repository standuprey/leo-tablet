"""Review list rows and the interim editor page (outcome banner until CTAs land)."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


def build_review_list(entries, on_trial) -> Gtk.ScrolledWindow:
    """Touch rows for playable games; a row tap starts a trial, nothing else."""
    scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    for entry in entries:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        name = Gtk.Label(label=entry.display_name, xalign=0, hexpand=True)
        name.get_style_context().add_class("word")
        name.set_line_wrap(True)
        badge_text = entry.status.value
        if entry.rating is not None:
            badge_text += f" {entry.rating}%"
        badge = Gtk.Label(label=badge_text, xalign=1)
        badge.get_style_context().add_class("status")
        box.pack_start(name, True, True, 0)
        box.pack_start(badge, False, False, 0)
        button = Gtk.Button()
        button.add(box)
        if on_trial is not None:
            game_id = entry.game_id
            button.connect(
                "clicked", lambda _b, gid=game_id, u=entry.playable_url: on_trial(gid, u)
            )
        row = Gtk.ListBoxRow()
        row.add(button)
        list_box.add(row)
    list_box.show_all()
    scrolled.add(list_box)
    return scrolled


def build_editor_placeholder(game_name: str, outcome_text: str | None) -> Gtk.Box:
    """Interim editor: shows the recorded outcome; name/rating/CTAs come next."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_border_width(24)
    title = Gtk.Label(label=game_name)
    title.get_style_context().add_class("parent-title")
    title.set_line_wrap(True)
    box.pack_start(title, False, False, 0)
    if outcome_text:
        outcome = Gtk.Label(label=outcome_text)
        outcome.get_style_context().add_class("status")
        outcome.set_line_wrap(True)
        box.pack_start(outcome, False, False, 0)
    hint = Gtk.Label(
        label="Renaming, rating and Keep/Select arrive in the next deploy.\n"
        "Return to the list with: Volume Down, Down, Up"
    )
    hint.get_style_context().add_class("status")
    hint.set_line_wrap(True)
    box.pack_start(hint, False, False, 0)
    return box
