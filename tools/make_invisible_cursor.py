#!/usr/bin/env python3
"""Generate an invisible XCursor theme for the kiosk (no pointer on screen).

Writes <output>/index.theme and <output>/cursors/<name> using the Xcursor
binary format (magic 'Xcur', one 32x32 fully transparent image per name).
Both the compositor (wlroots/cage) and Firefox/GTK clients resolve the
"default" theme from ~/.icons, so the pointer becomes invisible everywhere.
"""
import argparse
import struct
from pathlib import Path

# CSS/W3C cursor names plus X11 aliases; one invisible file per name.
CURSOR_NAMES = (
    "default", "left_ptr", "text", "xterm", "vertical-text", "crosshair", "cell",
    "pointer", "hand1", "hand2", "grab", "grabbing", "wait", "watch", "progress",
    "left_ptr_watch", "help", "context-menu", "alias", "copy", "move", "no-drop",
    "not-allowed", "forbidden", "all-scroll", "col-resize", "row-resize",
    "n-resize", "s-resize", "e-resize", "w-resize", "ne-resize", "nw-resize",
    "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize",
    "nwse-resize", "zoom-in", "zoom-out",
)

_SIZE = 32
_HOTSPOT = 0
_DELAY_MS = 10
_MAGIC = b"Xcur"
_FILE_HEADER = 16
_TOC_ENTRY = 12
_IMAGE_CHUNK_HEADER = 36
_IMAGE_TYPE = 0xFFFD0002
_FILE_VERSION = 65536


def image_chunk() -> bytes:
    pixels = b"\x00\x00\x00\x00" * (_SIZE * _SIZE)  # fully transparent ARGB
    return struct.pack(
        ">9I", _IMAGE_CHUNK_HEADER, _IMAGE_TYPE, _SIZE, 1,
        _SIZE, _SIZE, _HOTSPOT, _HOTSPOT, _DELAY_MS,
    ) + pixels


def cursor_file() -> bytes:
    chunk = image_chunk()
    chunk_position = _FILE_HEADER + _TOC_ENTRY
    out = bytearray()
    out += _MAGIC
    out += struct.pack(">3I", _FILE_HEADER, _FILE_VERSION, 1)
    out += struct.pack(">3I", _IMAGE_TYPE, _SIZE, chunk_position)
    out += chunk
    return bytes(out)


def write_theme(output: Path) -> None:
    cursors = output / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    blob = cursor_file()
    for name in CURSOR_NAMES:
        (cursors / name).write_bytes(blob)
    (output / "index.theme").write_text(
        "[Icon Theme]\nName=Invisible\nComment=Kiosk cursor (hidden)\n\n"
        "Directories=32\n\n[32]\nSize=32\nMinSize=32\nMaxSize=32\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Theme directory, e.g. ~/.icons/default")
    args = parser.parse_args()
    write_theme(args.output)
    print(f"invisible cursor theme written to {args.output} ({len(CURSOR_NAMES)} names)")


if __name__ == "__main__":
    main()
