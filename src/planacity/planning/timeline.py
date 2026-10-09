"""Deterministic timeline projection over the canonical Program Plan."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan, WorkItem, WorkItemType, WorkPriority
from planacity.planning.work_context import TopicState, effective_group_ids, resolve_topic


class TimelineDateState(StrEnum):
    """How much scheduling information a work item currently provides."""

    SCHEDULED = "scheduled"
    START_ONLY = "start_only"
    END_ONLY = "end_only"
    UNSCHEDULED = "unscheduled"


@dataclass(frozen=True, kw_only=True)
class TimelineGroup:
    """WorkGroup identity and display name in canonical plan order."""

    id: UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class TimelineRow:
    """One hierarchy row with zero-based day coordinates from the horizon start."""

    item_id: UUID
    parent_id: UUID | None
    title: str
    kind: WorkItemType
    priority: WorkPriority | None
    depth: int
    start: date | None
    end: date | None
    start_day: int | None
    end_day: int | None
    duration_days: int | None
    date_state: TimelineDateState
    outside_horizon: bool
    topic_state: TopicState
    primary_group_id: UUID | None
    group_ids: tuple[UUID, ...]
    section: str = ""
    section_id: UUID | None = None


@dataclass(frozen=True, kw_only=True)
class TimelineProjection:
    """Read-only timeline data derived from one complete plan snapshot."""

    horizon: PlanningHorizon
    total_days: int
    groups: tuple[TimelineGroup, ...]
    rows: tuple[TimelineRow, ...]


def _date_state(item: WorkItem) -> TimelineDateState:
    if item.start is not None and item.end is not None:
        return TimelineDateState.SCHEDULED
    if item.start is not None:
        return TimelineDateState.START_ONLY
    if item.end is not None:
        return TimelineDateState.END_ONLY
    return TimelineDateState.UNSCHEDULED


def project_timeline(plan: ProgramPlan) -> TimelineProjection:
    """Project work without changing order, dates, or canonical identities.

    Day coordinates are intentionally not clipped to the planning horizon. A
    negative start or an end beyond ``total_days - 1`` lets a renderer show that
    scheduled work extends outside the visible planning period.
    """
    by_parent: dict[UUID | None, list[WorkItem]] = {}
    for item in plan.work_items:
        by_parent.setdefault(item.parent_id, []).append(item)

    groups = tuple(TimelineGroup(id=group.id, name=group.name) for group in plan.work_groups)
    rows: list[TimelineRow] = []

    def append_rows(
        items: tuple[WorkItem, ...] | list[WorkItem],
        depth: int,
    ) -> None:
        for item in items:
            topic = resolve_topic(plan, item.id)
            group_ids = effective_group_ids(plan, item.id)
            start_day = None if item.start is None else (item.start - plan.horizon.start).days
            end_day = None if item.end is None else (item.end - plan.horizon.start).days
            known_dates = tuple(value for value in (item.start, item.end) if value is not None)
            rows.append(
                TimelineRow(
                    item_id=item.id,
                    parent_id=item.parent_id,
                    title=item.title,
                    kind=item.kind,
                    priority=item.priority,
                    depth=depth,
                    start=item.start,
                    end=item.end,
                    start_day=start_day,
                    end_day=end_day,
                    duration_days=None
                    if item.start is None or item.end is None
                    else (item.end - item.start).days + 1,
                    date_state=_date_state(item),
                    outside_horizon=any(
                        value < plan.horizon.start or value > plan.horizon.end
                        for value in known_dates
                    ),
                    topic_state=topic.state,
                    primary_group_id=topic.group_id,
                    group_ids=group_ids,
                )
            )
            append_rows(by_parent.get(item.id, ()), depth + 1)

    append_rows(by_parent.get(None, ()), 0)
    return TimelineProjection(
        horizon=plan.horizon,
        total_days=(plan.horizon.end - plan.horizon.start).days + 1,
        groups=groups,
        rows=tuple(rows),
    )
