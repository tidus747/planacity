"""Read-only sprint and assigned-work projection for the Program Calendar."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.sprints import SprintLoad, calculate_sprint_loads


class SprintCalendarState(StrEnum):
    INSIDE = "inside"
    PARTIAL = "partial"
    OUTSIDE = "outside"


@dataclass(frozen=True, kw_only=True)
class SprintCalendarWork:
    id: UUID
    title: str
    start: date | None
    end: date | None
    visible_start_day: int | None
    visible_end_day: int | None
    inside_sprint: bool | None


@dataclass(frozen=True, kw_only=True)
class SprintCalendarLane:
    id: UUID
    name: str
    start: date
    end: date
    state: SprintCalendarState
    visible_start_day: int | None
    visible_end_day: int | None
    work: tuple[SprintCalendarWork, ...]
    load: SprintLoad


@dataclass(frozen=True, kw_only=True)
class SprintCalendarProjection:
    horizon: PlanningHorizon
    total_days: int
    lanes: tuple[SprintCalendarLane, ...]

    @property
    def visible_lanes(self) -> tuple[SprintCalendarLane, ...]:
        return tuple(lane for lane in self.lanes if lane.state != SprintCalendarState.OUTSIDE)

    @property
    def outside_count(self) -> int:
        return sum(lane.state == SprintCalendarState.OUTSIDE for lane in self.lanes)


def _state(period: PlanningHorizon, horizon: PlanningHorizon) -> SprintCalendarState:
    if period.end < horizon.start or period.start > horizon.end:
        return SprintCalendarState.OUTSIDE
    if period.start < horizon.start or period.end > horizon.end:
        return SprintCalendarState.PARTIAL
    return SprintCalendarState.INSIDE


def _visible_days(
    start: date | None,
    end: date | None,
    horizon: PlanningHorizon,
) -> tuple[int | None, int | None]:
    if start is None or end is None or end < horizon.start or start > horizon.end:
        return None, None
    total_days = (horizon.end - horizon.start).days + 1
    return (
        max(0, (start - horizon.start).days),
        min(total_days - 1, (end - horizon.start).days),
    )


def project_sprint_calendar(plan: ProgramPlan) -> SprintCalendarProjection:
    """Project explicit sprint inputs without inferring membership or changing dates."""
    horizon = plan.horizon
    loads = {load.sprint_id: load for load in calculate_sprint_loads(plan)}
    assignments: dict[UUID, list[UUID]] = {}
    for assignment in plan.sprint_assignments:
        assignments.setdefault(assignment.sprint_id, []).append(assignment.work_item_id)

    lanes: list[SprintCalendarLane] = []
    for sprint in sorted(
        plan.sprints,
        key=lambda value: (
            value.period.start,
            value.period.end,
            value.name.casefold(),
            str(value.id),
        ),
    ):
        sprint_start, sprint_end = _visible_days(sprint.period.start, sprint.period.end, horizon)
        work: list[SprintCalendarWork] = []
        for work_id in assignments.get(sprint.id, []):
            item = plan.work_item(work_id)
            visible_start, visible_end = _visible_days(item.start, item.end, horizon)
            work.append(
                SprintCalendarWork(
                    id=item.id,
                    title=item.title,
                    start=item.start,
                    end=item.end,
                    visible_start_day=visible_start,
                    visible_end_day=visible_end,
                    inside_sprint=(
                        None
                        if item.start is None or item.end is None
                        else item.start >= sprint.period.start and item.end <= sprint.period.end
                    ),
                )
            )
        work.sort(
            key=lambda value: (
                value.start is None,
                value.start or date.max,
                value.end or date.max,
                value.title.casefold(),
                str(value.id),
            )
        )
        lanes.append(
            SprintCalendarLane(
                id=sprint.id,
                name=sprint.name,
                start=sprint.period.start,
                end=sprint.period.end,
                state=_state(sprint.period, horizon),
                visible_start_day=sprint_start,
                visible_end_day=sprint_end,
                work=tuple(work),
                load=loads[sprint.id],
            )
        )
    return SprintCalendarProjection(
        horizon=horizon,
        total_days=(horizon.end - horizon.start).days + 1,
        lanes=tuple(lanes),
    )
