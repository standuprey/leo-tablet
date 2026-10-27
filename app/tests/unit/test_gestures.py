import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from leo_kiosk.domain.gestures import (
    DDU,
    DEFAULT_PATTERNS,
    DU,
    REVIEW_TRIAL_PATTERNS,
    UDD,
    GestureAction,
    GestureConfig,
    GestureRecognizer,
    VolumeKey,
)

UP, DOWN = VolumeKey.UP, VolumeKey.DOWN


def taps(recognizer, clock, codes, gap=0.25):
    results = []
    for code in codes:
        result = recognizer.feed(code)
        if result is not None:
            results.append(result)
        clock.advance(gap)
    return results


@pytest.mark.parametrize(
    ("codes", "action"),
    [
        ([UP, DOWN, DOWN], GestureAction.ENTER_PARENT),
        ([DOWN, DOWN, UP], GestureAction.RETURN),
    ],
)
def test_exact_sequences(fake_clock, codes, action):
    recognizer = GestureRecognizer(fake_clock)
    assert taps(recognizer, fake_clock, codes) == [action]


def test_review_trial_returns_on_down_up_and_three_tap_ends_in_short_match(fake_clock):
    recognizer = GestureRecognizer(fake_clock, patterns=REVIEW_TRIAL_PATTERNS)
    assert taps(recognizer, fake_clock, [DOWN, UP]) == [GestureAction.RETURN]
    recognizer.reset("route_changed")
    fake_clock.advance(0.5)
    # In trial mode DD (thumbnail capture) now matches at the second Down;
    # the trailing Up lands inside the match cooldown and is swallowed, so a
    # stray DDU screenshots instead of returning — the parent presses the
    # short Down/Up again to leave. Accepted cost of the capture gesture.
    assert taps(recognizer, fake_clock, [DOWN, DOWN, UP]) == [GestureAction.SCREENSHOT]
    recognizer.reset("route_changed")
    fake_clock.advance(0.5)
    assert taps(recognizer, fake_clock, [DOWN, UP]) == [GestureAction.RETURN]
    recognizer.reset("route_changed")
    fake_clock.advance(0.5)
    assert recognizer.feed(UP) is None  # No leftover partial state after cooldown.


def test_pattern_sets_swap_with_context_and_default_set_is_unchanged(fake_clock):
    recognizer = GestureRecognizer(fake_clock)
    assert taps(recognizer, fake_clock, [UP, DOWN, DOWN]) == [GestureAction.ENTER_PARENT]
    recognizer.use_patterns(REVIEW_TRIAL_PATTERNS)
    recognizer.reset("route_changed")
    fake_clock.advance(0.5)
    assert taps(recognizer, fake_clock, [DOWN, UP]) == [GestureAction.RETURN]
    recognizer.use_patterns(DEFAULT_PATTERNS)
    recognizer.reset("route_changed")
    fake_clock.advance(0.5)
    assert taps(recognizer, fake_clock, [DOWN, DOWN, UP]) == [GestureAction.RETURN]
    assert recognizer.patterns == DEFAULT_PATTERNS


@pytest.mark.parametrize(
    "patterns",
    [
        [((DOWN, DOWN), GestureAction.RETURN), (DDU, GestureAction.RETURN)],
        [(UDD, GestureAction.ENTER_PARENT), ((UP, DOWN), GestureAction.RETURN)],
    ],
)
def test_ambiguous_prefix_sets_are_rejected(fake_clock, patterns):
    with pytest.raises(ValueError, match="Ambiguous"):
        GestureRecognizer(fake_clock, patterns=patterns)


def test_short_return_and_three_tap_sets_are_geometrically_compatible(fake_clock):
    # DU diverges from DDU at the second key, so both coexist in one recognizer.
    # Never enabling DU outside review trials is the adapter's contract.
    combined = list(DEFAULT_PATTERNS) + [(DU, GestureAction.RETURN)]
    recognizer = GestureRecognizer(fake_clock, patterns=combined)
    assert taps(recognizer, fake_clock, [DOWN, UP]) == [GestureAction.RETURN]
    recognizer.reset("route_changed")
    fake_clock.advance(0.5)
    assert taps(recognizer, fake_clock, [DOWN, DOWN, UP]) == [GestureAction.RETURN]
    recognizer.reset("route_changed")
    fake_clock.advance(0.5)
    assert taps(recognizer, fake_clock, [UP, DOWN, DOWN]) == [GestureAction.ENTER_PARENT]


@pytest.mark.parametrize(
    "patterns",
    [
        [],
        [((DOWN,), GestureAction.RETURN)],
        [((42,), GestureAction.RETURN)],  # Raw int is rejected by pattern validation.
        [((DOWN, DOWN), "return")],
        [(DDU, GestureAction.RETURN), (DDU, GestureAction.RETURN)],
    ],
)
def test_invalid_pattern_sets(patterns):
    with pytest.raises(ValueError):
        GestureRecognizer(patterns=patterns)


def test_old_shortcut_and_releases_repeats_unrelated_keys(fake_clock):
    recognizer = GestureRecognizer(fake_clock)
    # Down/Up alone is NOT a default-set gesture; three-tap sets only.
    assert taps(recognizer, fake_clock, [DOWN, UP]) == []
    recognizer.reset("route_changed")
    assert recognizer.feed(UP) is None
    for code, value in [(UP, 0), (DOWN, 2), (42, 1), (DOWN, True)]:
        assert recognizer.feed(code, value) is None
    assert recognizer.feed(DOWN) is None
    assert recognizer.feed(DOWN) is GestureAction.ENTER_PARENT


def test_gap_and_total_duration_have_independent_inclusive_boundaries(fake_clock):
    recognizer = GestureRecognizer(fake_clock)
    assert taps(recognizer, fake_clock, [UP, DOWN, DOWN], gap=1.0) == [GestureAction.ENTER_PARENT]
    recognizer = GestureRecognizer(fake_clock)
    assert recognizer.feed(UP) is None
    fake_clock.advance(1.01)
    assert taps(recognizer, fake_clock, [DOWN, DOWN]) == []
    recognizer = GestureRecognizer(fake_clock, GestureConfig(max_duration=1.0))
    assert taps(recognizer, fake_clock, [UP, DOWN, DOWN], gap=0.75) == []


def test_review_trial_short_taps_obey_gap_and_duration(fake_clock):
    recognizer = GestureRecognizer(fake_clock, patterns=REVIEW_TRIAL_PATTERNS)
    assert taps(recognizer, fake_clock, [DOWN, UP], gap=1.0) == [GestureAction.RETURN]
    recognizer = GestureRecognizer(fake_clock, patterns=REVIEW_TRIAL_PATTERNS)
    assert recognizer.feed(DOWN) is None
    fake_clock.advance(1.01)
    assert recognizer.feed(UP) is None


def test_wrong_prefix_retains_longest_valid_suffix(fake_clock):
    recognizer = GestureRecognizer(fake_clock)
    assert taps(recognizer, fake_clock, [UP, DOWN, UP, DOWN, DOWN]) == [GestureAction.ENTER_PARENT]


def test_match_consumes_taps_and_route_reset_does_not_disable_cooldown(fake_clock):
    recognizer = GestureRecognizer(fake_clock)
    assert taps(recognizer, fake_clock, [UP, DOWN, DOWN], gap=0) == [GestureAction.ENTER_PARENT]
    recognizer.reset("route_changed")
    assert taps(recognizer, fake_clock, [DOWN, DOWN, UP], gap=0) == []
    fake_clock.advance(0.5)
    assert taps(recognizer, fake_clock, [DOWN, DOWN, UP], gap=0) == [GestureAction.RETURN]
    fake_clock.advance(0.5)
    assert recognizer.feed(UP) is None  # No down/down from the previous match survive.


@pytest.mark.parametrize("reason", ["route_changed", "suspend", "resume", "device_removed"])
def test_explicit_reset_clears_partial_sequence(fake_clock, reason):
    recognizer = GestureRecognizer(fake_clock)
    assert taps(recognizer, fake_clock, [UP, DOWN]) == []
    recognizer.reset(reason)
    assert recognizer.last_reset_reason == reason
    assert recognizer.feed(DOWN) is None


def test_clock_regression_resets_old_partial_sequence(fake_clock):
    recognizer = GestureRecognizer(fake_clock)
    fake_clock.value = 5
    assert taps(recognizer, fake_clock, [UP, DOWN]) == []
    fake_clock.value = 1
    assert recognizer.feed(DOWN) is None
    assert recognizer.last_reset_reason == "clock_moved_backwards"


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(max_gap=0),
        dict(max_duration=-1),
        dict(cooldown=-1),
        dict(max_gap=float("nan")),
        dict(cooldown=float("inf")),
        dict(max_gap=True),
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        GestureConfig(**kwargs)


def test_all_short_streams_match_a_simple_consuming_reference():
    for codes in itertools.product((UP, DOWN), repeat=7):
        now = [0.0]
        recognizer = GestureRecognizer(lambda now=now: now[0], GestureConfig(cooldown=0))
        recent, expected, actual = [], [], []
        for key in codes:
            recent.append(key)
            if recent[-3:] == [UP, DOWN, DOWN]:
                expected.append(GestureAction.ENTER_PARENT)
                recent.clear()
            elif recent[-3:] == [DOWN, DOWN, UP]:
                expected.append(GestureAction.RETURN)
                recent.clear()
            result = recognizer.feed(key)
            if result is not None:
                actual.append(result)
            now[0] += 0.1
        assert actual == expected


@given(st.lists(st.tuples(st.sampled_from([UP, DOWN, 42]), st.integers(0, 2)), max_size=80))
def test_noise_cannot_create_a_match_without_three_real_presses(events):
    recognizer = GestureRecognizer(lambda: 0, GestureConfig(cooldown=0))
    presses = []
    for key, value in events:
        if key in (UP, DOWN) and value == 1:
            presses.append(key)
        action = recognizer.feed(key, value)
        if action is not None:
            expected = (
                [UP, DOWN, DOWN] if action is GestureAction.ENTER_PARENT else [DOWN, DOWN, UP]
            )
            assert presses[-3:] == expected
            presses.clear()
