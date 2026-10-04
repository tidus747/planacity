"""Dependency direction, visibility and connector geometry without Qt."""

from dataclasses import dataclass
from uuid import UUID

from planacity.domain import ProgramPlan
from planacity.planning.dependency_validation import (
    DependencyFindingKind,
    dependency_findings,
    normalize_dependency,
)
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
    for link in plan.relationships:
        edge = normalize_dependency(link)
        if edge is None:
            continue
        links.append((link, edge.predecessor_id, edge.successor_id))

    findings: dict[UUID, dict[DependencyFindingKind, str]] = {}
    for finding in dependency_findings(plan):
        findings.setdefault(finding.edge.relationship_id, {})[finding.kind] = finding.message

    result = []
    for link, before, after in links:
        reason = ""
        link_findings = findings.get(link.id, {})
        if DependencyFindingKind.CYCLE in link_findings:
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
        if conflict := link_findings.get(DependencyFindingKind.CONFLICT):
            description += "; dates overlap or run against dependency order. " + conflict
        if unevaluated := link_findings.get(DependencyFindingKind.UNEVALUATED):
            description += "; " + unevaluated
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
