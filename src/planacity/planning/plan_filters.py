"""Plan matches retain ancestor context using the same predicates as Timeline."""

from dataclasses import dataclass
from uuid import UUID

from planacity.domain import ProgramPlan
from planacity.planning.timeline import project_timeline
from planacity.planning.timeline_view import TimelineFilters


@dataclass(frozen=True)
class PlanMatches:
    matches: frozenset[UUID]
    visible: frozenset[UUID]
    total: int


def filter_plan(plan: ProgramPlan | None, filters: TimelineFilters) -> PlanMatches:
    if plan is None:
        return PlanMatches(frozenset(), frozenset(), 0)
    matches = frozenset(row.item_id for row in project_timeline(plan).rows if filters.matches(row))
    parents = {item.id: item.parent_id for item in plan.work_items}
    visible = set(matches)
    for identifier in matches:
        parent = parents[identifier]
        while parent is not None:
            visible.add(parent)
            parent = parents[parent]
    return PlanMatches(matches, frozenset(visible), len(plan.work_items))
