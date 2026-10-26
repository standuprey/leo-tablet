"""Rainbow painter: fade curve, palette, gesture lifecycle (no display)."""

import pytest

from leo_kiosk.ui.rainbow import PALETTE, RainbowPainter, fade_alpha, parse_palette


def test_fade_alpha_is_linear_and_clamped():
    assert fade_alpha(0.0) == 1.0
    assert fade_alpha(0.6) == pytest.approx(0.5)  # halfway through 1.2 s
    assert fade_alpha(1.2) == 0.0
    assert fade_alpha(10.0) == 0.0


def test_parse_palette_parses_every_color_as_distinct_rgb():
    colors = parse_palette()
    assert len(colors) == len(PALETTE)
    assert all(0.0 <= c <= 1.0 for triple in colors for c in triple)
    assert len({tuple(triple) for triple in colors}) == len(PALETTE)


class FakeClock:
    def __init__(self, start=100.0):
        self.t = start

    def __call__(self):
        return self.t


def make_painter():
    calls: list[int] = []
    painter = RainbowPainter(invalidate=lambda: calls.append(1), clock=FakeClock())
    return painter, calls


def test_painter_scroll_advances_offset_and_invalidates():
    painter, calls = make_painter()
    painter.start_scroll()
    assert painter.scrolling
    painter.tick()
    assert calls, "first tick must invalidate for a repaint"
    assert painter.offset == pytest.approx(0.0)
    painter.clock.t += 1.0
    painter.tick()
    assert painter.offset == pytest.approx(150.0)  # 1 s at 150 px/s
    assert painter.scrolling


def test_painter_lift_stops_scroll_then_fade_ends_ticking():
    painter, _ = make_painter()
    painter.start_scroll()
    painter.clock.t += 1.0
    painter.tick()
    painter.stop_scroll()
    assert not painter.scrolling
    painter.tick()  # fade starts; still ticking
    painter.clock.t += 1.2
    assert painter.tick() is False  # fade complete: source removes itself
    assert painter.fading_since is None


def test_painter_reset_clears_midgesture_state():
    painter, _ = make_painter()
    painter.start_scroll()
    painter.clock.t += 1.0
    painter.tick()
    painter.reset()
    assert painter.offset == 0.0
    assert not painter.scrolling
    assert painter.fading_since is None
    assert not painter.tick_scheduled