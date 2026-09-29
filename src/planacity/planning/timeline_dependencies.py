"""Dependency direction, visibility and connector geometry without Qt."""

from dataclasses import dataclass
from uuid import UUID

from planacity.domain import ProgramPlan, RelationshipType
from planacity.planning.timeline import TimelineDateState, TimelineProjection


@dataclass(frozen=True)
class TimelineDependency:
    relationship_id: UUID
    predecessor: UUID
    successor: UUID
    description: str
    reason: str = ""


def timeline_dependencies(
    plan: ProgramPlan,
    projection: TimelineProjection,
) -> tuple[TimelineDependency, ...]:
    """Resolve canonical links; never infer hierarchy links or modify schedules."""
    items = {item.id: item for item in plan.work_items}
    rows = {row.item_id: row for row in projection.rows}
    links = []
    adjacency: dict[UUID, set[UUID]] = {}
    for link in plan.relationships:
        if link.kind == RelationshipType.RELATED_TO:
            continue
        before, after = (
            (link.target_id, link.source_id)
            if link.kind == RelationshipType.DEPENDS_ON
            else (link.source_id, link.target_id)
        )
        links.append((link, before, after))
        adjacency.setdefault(before, set()).add(after)

    def reaches(start: UUID, target: UUID) -> bool:
        pending, visited = [start], set()
        while pending:
            node = pending.pop()
            if node == target:
                return True
            if node not in visited:
                visited.add(node)
                pending.extend(adjacency.get(node, ()))
        return False

    result = []
    for link, before, after in links:
        reason = ""
        if reaches(after, before):
            reason = "Dependency cycle; arrow hidden"
        elif before not in rows or after not in rows:
            reason = "Endpoint hidden by filters; arrow hidden"
        elif any(rows[key].date_state != TimelineDateState.SCHEDULED for key in (before, after)):
            reason = "Endpoint not fully scheduled; arrow hidden"
        elif any(rows[key].outside_horizon for key in (before, after)):
            reason = "Endpoint outside planning horizon; arrow hidden"
        description = (
            f"{items[before].title} -> {items[after].title} "
            f"({items[link.source_id].title} {link.kind.value} {items[link.target_id].title})"
        )
        end, start = items[before].end, items[after].start
        if end is not None and start is not None:
            if end >= start:
                description += "; dates overlap or run against dependency order"
        result.append(TimelineDependency(link.id, before, after, description, reason))
    return tuple(result)


def connector_points(
    start: tuple[float, float],
    end: tuple[float, float],
    clearance: float = 10,
) -> tuple[tuple[float, float], ...]:
    """Route end -> start with a right-pointing final segment, even for overlaps.

    The horizontal lane lies just outside the predecessor bar. This avoids
    running a horizontal line through intervening row centers.
    """
    x1, y1 = start
    x2, y2 = end
    lane = y1 + (clearance if y2 >= y1 else -clearance)
    return (
        start,
        (x1 + clearance, y1),
        (x1 + clearance, lane),
        (x2 - clearance, lane),
        (x2 - clearance, y2),
        end,
    )
