"""Pure cairo aspect-preserving downscale for thumbnails; no GTK state, no I/O.

Takes any source surface (the WebKit snapshot's dimensions are whatever the
composited allocation was — never assumed) and renders it onto an output
surface whose longest side is THUMB_LONG_EDGE, keeping the source aspect
ratio: the whole frame survives. The home grid displays thumbnails at the
screen's own aspect ratio, so a fullscreen capture is never cropped —
unlike the old cover-crop to 800x400, which cut a third of the picture.

Runs on the GTK main thread; the cost is one scaled paint of a 1800x1200
frame (~milliseconds on the tablet's class of hardware, measured on-device
before shipping).
"""

import cairo

THUMB_LONG_EDGE = 800


def fit_thumbnail(source: cairo.ImageSurface) -> cairo.ImageSurface:
    """Scale source so its longest side is THUMB_LONG_EDGE, aspect intact."""
    source_width, source_height = source.get_width(), source.get_height()
    if source_width < 1 or source_height < 1:
        raise ValueError("Snapshot surface is empty")
    scale = THUMB_LONG_EDGE / max(source_width, source_height)
    width = max(1, round(source_width * scale))
    height = max(1, round(source_height * scale))

    destination = cairo.ImageSurface(cairo.Format.ARGB32, width, height)
    context = cairo.Context(destination)
    context.scale(width / source_width, height / source_height)
    context.set_source_surface(source, 0, 0)
    context.paint()
    return destination
