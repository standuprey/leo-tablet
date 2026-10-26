"""Pure route/parent-session decisions; widgets apply transitions, never own them."""

from dataclasses import dataclass
from enum import Enum, auto
from uuid import UUID

from leo_kiosk.domain.errors import ValidationError


class Route(Enum):
    CHILD_HOME = auto()
    CHILD_ACTIVITY = auto()
    PARENT_HOME = auto()
    REVIEW_LIST = auto()
    REVIEW_TRIAL = auto()
    REVIEW_EDITOR = auto()
    VIDEOS = auto()
    WIFI = auto()
    PORTAL = auto()


@dataclass(frozen=True)
class Transition:
    route: Route
    stop_activity: bool = False
    end_parent_session: bool = False
    close_portal: bool = False
    review_game_id: UUID | None = None
    requires_confirmation: bool = False


def enter_parent(
    current: Route, review_game_id: UUID | None = None, editor_dirty: bool = False
) -> Transition:
    return _apply(current, enter=True, review_game_id=review_game_id, editor_dirty=editor_dirty)


def return_gesture(
    current: Route, review_game_id: UUID | None = None, editor_dirty: bool = False
) -> Transition:
    return _apply(current, enter=False, review_game_id=review_game_id, editor_dirty=editor_dirty)


def _apply(
    current: Route, enter: bool, review_game_id: UUID | None = None, editor_dirty: bool = False
) -> Transition:
    if current is Route.REVIEW_EDITOR and editor_dirty:
        raise ValidationError("Unsaved review requires confirmation before navigating")
    if current is Route.CHILD_ACTIVITY and enter:
        return Transition(Route.PARENT_HOME, stop_activity=True)
    if current is Route.CHILD_ACTIVITY:
        return Transition(Route.CHILD_HOME, stop_activity=True)
    if current is Route.REVIEW_TRIAL and enter:
        return Transition(Route.PARENT_HOME, stop_activity=True)
    if current is Route.REVIEW_TRIAL:
        if review_game_id is None:
            raise ValidationError("A review trial must record which game it is")
        return Transition(Route.REVIEW_EDITOR, stop_activity=True, review_game_id=review_game_id)
    if current is Route.REVIEW_EDITOR:
        target = Route.PARENT_HOME if enter else Route.REVIEW_LIST
        return Transition(target, requires_confirmation=editor_dirty)
    if current is Route.WIFI:
        return Transition(Route.PARENT_HOME)
    if current is Route.PORTAL:
        return Transition(Route.PARENT_HOME if enter else Route.WIFI, close_portal=True)
    if current is Route.VIDEOS:
        return Transition(Route.PARENT_HOME if enter else Route.CHILD_HOME)
    if enter:
        return Transition(Route.PARENT_HOME)
    if current is Route.PARENT_HOME:
        return Transition(Route.CHILD_HOME, end_parent_session=True)
    if current in (Route.REVIEW_LIST,):
        return Transition(Route.PARENT_HOME)
    return Transition(current)
