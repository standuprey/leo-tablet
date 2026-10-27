"""Aspect-preserving downscale: geometry, output format, degenerate inputs."""

import io

import cairo
import pytest

from leo_kiosk.adapters.thumbs import THUMB_LONG_EDGE, fit_thumbnail


def solid_surface(width: int, height: int, r: float, g: float, b: float) -> cairo.ImageSurface:
    surface = cairo.ImageSurface(cairo.Format.ARGB32, width, height)
    context = cairo.Context(surface)
    context.set_source_rgb(r, g, b)
    context.paint()
    return surface


def pixel(surface: cairo.ImageSurface, x: int, y: int) -> tuple[int, int, int]:
    data = surface.get_data()
    offset = (surface.get_stride() * y) + x * 4
    # ARGB32 on little-endian: B, G, R, A.
    return data[offset + 2], data[offset + 1], data[offset]


def test_screen_aspect_source_keeps_its_shape() -> None:
    # The kiosk screen is 3:2 (1800x1200); the whole frame must survive.
    surface = fit_thumbnail(solid_surface(1800, 1200, 1, 0, 0))
    assert surface.get_width() == THUMB_LONG_EDGE
    assert abs(surface.get_height() - surface.get_width() / 1.5) <= 1
    assert (surface.get_width(), surface.get_height()) == (800, 533)


def test_tall_source_is_scaled_not_cropped() -> None:
    surface = fit_thumbnail(solid_surface(1200, 1800, 0, 1, 0))
    assert surface.get_height() == THUMB_LONG_EDGE
    assert (surface.get_width(), surface.get_height()) == (533, 800)


def test_nothing_is_cropped_away() -> None:
    # A green band at the top and red elsewhere: both survive in the output.
    source = cairo.ImageSurface(cairo.Format.ARGB32, 1800, 1200)
    context = cairo.Context(source)
    context.set_source_rgb(1, 0, 0)
    context.paint()
    context.set_source_rgb(0, 1, 0)
    context.rectangle(0, 0, 1800, 120)  # top tenth
    context.fill()
    surface = fit_thumbnail(source)
    assert pixel(surface, 10, 10) == (0, 255, 0)  # top band intact
    assert pixel(surface, THUMB_LONG_EDGE - 10, 533 - 10) == (255, 0, 0)


def test_source_dimensions_are_never_assumed() -> None:
    for width, height in ((3440, 1440), (1280, 1920), (856, 1410), (31, 17)):
        surface = fit_thumbnail(solid_surface(width, height, 0, 1, 0))
        assert max(surface.get_width(), surface.get_height()) == THUMB_LONG_EDGE
        ratio_out = surface.get_width() / surface.get_height()
        ratio_in = width / height
        assert abs(ratio_out - ratio_in) <= 0.01


def test_output_is_a_png_writable_argb_surface() -> None:
    surface = fit_thumbnail(solid_surface(1800, 1200, 1, 0, 0))
    assert surface.get_format() == cairo.Format.ARGB32
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    assert buffer.getvalue().startswith(b"\x89PNG")


def test_empty_surface_raises() -> None:
    with pytest.raises(ValueError):
        fit_thumbnail(solid_surface(0, 0, 0, 0, 0))
