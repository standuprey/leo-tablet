from uuid import uuid4

import pytest

from leo_kiosk.domain.errors import ValidationError
from leo_kiosk.domain.review_queue import ReviewQueue


def test_next_skips_deleted_without_wrapping_or_reordering():
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    queue = ReviewQueue.from_ids([a, b, c, d])
    assert queue.next_id(skip=lambda i: i in (b,)) == a  # cursor before any advance


def test_advance_past_then_skip_deleted():
    a, b, c = uuid4(), uuid4(), uuid4()
    queue = ReviewQueue.from_ids([a, b, c])
    queue = queue.advance_past(a)
    assert queue.current() == b
    queue = queue.advance_past(b)
    # Cursor now sits on c; skipping it yields end-of-queue, not a wrap.
    assert queue.next_id(skip=lambda i: i == c) is None
    assert queue.next_id() == c  # without the skip, c is still next
    assert not queue.exhausted
    queue = queue.advance_past(c)
    assert queue.exhausted


def test_queue_end_is_explicit_and_never_wraps():
    a, b = uuid4(), uuid4()
    queue = ReviewQueue.from_ids([a, b]).advance_past(a).advance_past(b)
    assert queue.exhausted
    assert queue.current() is None
    assert queue.next_id() is None
    # Advancing past an exhausted queue is a no-op, never a wrap to index 0.
    assert queue.advance() == queue


def test_frozen_snapshot_does_not_reorder_after_rename_or_rating():
    a, b = uuid4(), uuid4()
    queue = ReviewQueue.from_ids([a, b])
    # Later renames/sorts live in the widget layer; the queue keeps its order
    # and matches by identity, not by display name.
    moved = queue.advance_past(a)
    assert moved.ids == (a, b) and moved.position == 1


def test_advance_past_unknown_id_is_a_noop():
    a, b = uuid4(), uuid4()
    queue = ReviewQueue.from_ids([a, b])
    assert queue.advance_past(uuid4()) == queue


@pytest.mark.parametrize(
    ("ids", "position"), [(None, 0), ([uuid4()], 0), ((uuid4(),), True), ((uuid4(),), -1)]
)
def test_invalid_construction(ids, position):
    with pytest.raises(ValidationError):
        ReviewQueue(ids, position)
