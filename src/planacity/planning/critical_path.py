"""Pure elapsed-day critical-path analysis over canonical planning work."""

from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from heapq import heappop, heappush
from uuid import UUID

from planacity.domain import ProgramPlan, WorkItem
from planacity.planning.dependency_validation import normalize_dependency


class CriticalPathStatus(StrEnum):
    """Whether a trustworthy whole-plan calculation is available."""

    COMPLETE = "complete"
    EMPTY = "empty"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"


class CriticalPathDiagnosticKind(StrEnum):
    """Why a whole-plan critical path could not be calculated."""

    NO_WORK = "no_work"
    MISSING_DATES = "missing_dates"
    DATE_CONFLICT = "date_conflict"
    CYCLE = "cycle"
    UNKNOWN_ENDPOINT = "unknown_endpoint"
    CONTAINER_DEPENDENCY = "container_dependency"


@dataclass(frozen=True)
class CriticalPathDiagnostic:
    kind: CriticalPathDiagnosticKind
    message: str
    work_item_ids: tuple[UUID, ...] = ()
    relationship_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class CriticalPathActivity:
    """One leaf activity and its optional dependency-only CPM offsets."""

    work_item_id: UUID
    duration_days: int | None
    early_start: int | None = None
    early_finish: int | None = None
    late_start: int | None = None
    late_finish: int | None = None
    total_float: int | None = None
    critical: bool = False


@dataclass(frozen=True)
class CriticalPathLink:
    """One normalized leaf edge backed by one or more stored relationships."""

    predecessor_id: UUID
    successor_id: UUID
    relationship_ids: tuple[UUID, ...]
    critical: bool = False


@dataclass(frozen=True)
class CriticalPathAnalysis:
    """A complete calculation or an explicit non-partial diagnostic result."""

    status: CriticalPathStatus
    scope_ids: tuple[UUID, ...]
    activities: tuple[CriticalPathActivity, ...]
    links: tuple[CriticalPathLink, ...]
    diagnostics: tuple[CriticalPathDiagnostic, ...] = ()
    origin: date | None = None
    finish_offset: int | None = None
    critical_node_ids: tuple[UUID, ...] = ()
    critical_relationship_ids: tuple[UUID, ...] = ()

    @property
    def complete(self) -> bool:
        return self.status == CriticalPathStatus.COMPLETE

    def activity(self, work_item_id: UUID) -> CriticalPathActivity:
        try:
            return next(value for value in self.activities if value.work_item_id == work_item_id)
        except StopIteration as error:
            raise ValueError(f"Work item {work_item_id} is outside this analysis scope.") from error


def _leaf_work(plan: ProgramPlan) -> tuple[WorkItem, ...]:
    parent_ids = {item.parent_id for item in plan.work_items if item.parent_id is not None}
    return tuple(item for item in plan.work_items if item.id not in parent_ids)


def _ordered_ids(ids: set[UUID], order: dict[UUID, int]) -> tuple[UUID, ...]:
    return tuple(sorted(ids, key=lambda value: order.get(value, len(order))))


def _reaches(adjacency: dict[UUID, tuple[UUID, ...]], start: UUID, target: UUID) -> bool:
    pending = [start]
    visited: set[UUID] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, ()))
    return False


def _topological_order(
    scope_ids: tuple[UUID, ...], links: tuple[CriticalPathLink, ...]
) -> tuple[UUID, ...]:
    order = {item_id: index for index, item_id in enumerate(scope_ids)}
    successors: dict[UUID, list[UUID]] = {item_id: [] for item_id in scope_ids}
    indegree = {item_id: 0 for item_id in scope_ids}
    for link in links:
        successors[link.predecessor_id].append(link.successor_id)
        indegree[link.successor_id] += 1
    ready: list[tuple[int, UUID]] = []
    for item_id in scope_ids:
        if indegree[item_id] == 0:
            heappush(ready, (order[item_id], item_id))
    result = []
    while ready:
        _, item_id = heappop(ready)
        result.append(item_id)
        for successor_id in successors[item_id]:
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                heappush(ready, (order[successor_id], successor_id))
    return tuple(result)


def calculate_critical_path(plan: ProgramPlan) -> CriticalPathAnalysis:
    """Calculate dependency-only CPM offsets without mutating or scheduling work."""
    leaves = _leaf_work(plan)
    scope_ids = tuple(item.id for item in leaves)
    if not leaves:
        diagnostic = CriticalPathDiagnostic(
            CriticalPathDiagnosticKind.NO_WORK,
            "Critical-path analysis requires at least one leaf work item.",
        )
        return CriticalPathAnalysis(
            CriticalPathStatus.EMPTY,
            (),
            (),
            (),
            diagnostics=(diagnostic,),
        )

    items = {item.id: item for item in plan.work_items}
    item_order = {item.id: index for index, item in enumerate(plan.work_items)}
    relationship_order = {
        relationship.id: index for index, relationship in enumerate(plan.relationships)
    }
    scope = set(scope_ids)
    containers = set(items) - scope
    diagnostics: list[CriticalPathDiagnostic] = []
    activities = tuple(
        CriticalPathActivity(
            item.id,
            (item.end - item.start).days + 1
            if item.start is not None and item.end is not None
            else None,
        )
        for item in leaves
    )
    for item in leaves:
        if item.start is None or item.end is None:
            missing = []
            if item.start is None:
                missing.append("start")
            if item.end is None:
                missing.append("end")
            date_word = "date" if len(missing) == 1 else "dates"
            diagnostics.append(
                CriticalPathDiagnostic(
                    CriticalPathDiagnosticKind.MISSING_DATES,
                    f'"{item.title}" is missing its ' + " and ".join(missing) + f" {date_word}.",
                    work_item_ids=(item.id,),
                )
            )

    stored_pairs: dict[tuple[UUID, UUID], list[UUID]] = {}
    for relationship in plan.relationships:
        edge = normalize_dependency(relationship)
        if edge is not None:
            stored_pairs.setdefault((edge.predecessor_id, edge.successor_id), []).append(
                relationship.id
            )

    valid_links: list[CriticalPathLink] = []
    unsupported = False
    for (predecessor_id, successor_id), relationship_ids in stored_pairs.items():
        ids = tuple(sorted(relationship_ids, key=relationship_order.__getitem__))
        unknown = {value for value in (predecessor_id, successor_id) if value not in items}
        if unknown:
            unsupported = True
            diagnostics.append(
                CriticalPathDiagnostic(
                    CriticalPathDiagnosticKind.UNKNOWN_ENDPOINT,
                    "A dependency references work that is not present in the plan.",
                    work_item_ids=_ordered_ids(
                        {value for value in (predecessor_id, successor_id) if value in items},
                        item_order,
                    ),
                    relationship_ids=ids,
                )
            )
            continue
        if predecessor_id in containers or successor_id in containers:
            unsupported = True
            diagnostics.append(
                CriticalPathDiagnostic(
                    CriticalPathDiagnosticKind.CONTAINER_DEPENDENCY,
                    "Critical-path analysis does not expand dependencies involving containers.",
                    work_item_ids=_ordered_ids({predecessor_id, successor_id}, item_order),
                    relationship_ids=ids,
                )
            )
            continue
        link = CriticalPathLink(predecessor_id, successor_id, ids)
        valid_links.append(link)
        predecessor = items[predecessor_id]
        successor = items[successor_id]
        if (
            predecessor.end is not None
            and successor.start is not None
            and predecessor.end >= successor.start
        ):
            conflict_days = (predecessor.end - successor.start).days + 1
            unit = "day" if conflict_days == 1 else "days"
            diagnostics.append(
                CriticalPathDiagnostic(
                    CriticalPathDiagnosticKind.DATE_CONFLICT,
                    f'"{predecessor.title}" ends {predecessor.end.isoformat()} and '
                    f'"{successor.title}" starts {successor.start.isoformat()} '
                    f"({conflict_days} conflicting calendar {unit}).",
                    work_item_ids=(predecessor_id, successor_id),
                    relationship_ids=ids,
                )
            )

    links = tuple(valid_links)
    adjacency_lists: dict[UUID, list[UUID]] = {item_id: [] for item_id in scope_ids}
    for link in links:
        adjacency_lists[link.predecessor_id].append(link.successor_id)
    adjacency = {key: tuple(values) for key, values in adjacency_lists.items()}
    cycle_links = tuple(
        link for link in links if _reaches(adjacency, link.successor_id, link.predecessor_id)
    )
    if cycle_links:
        cycle_nodes = {
            item_id for link in cycle_links for item_id in (link.predecessor_id, link.successor_id)
        }
        cycle_relationships = {
            relationship_id for link in cycle_links for relationship_id in link.relationship_ids
        }
        diagnostics.append(
            CriticalPathDiagnostic(
                CriticalPathDiagnosticKind.CYCLE,
                "Critical-path analysis requires an acyclic dependency graph.",
                work_item_ids=_ordered_ids(cycle_nodes, item_order),
                relationship_ids=tuple(
                    sorted(cycle_relationships, key=relationship_order.__getitem__)
                ),
            )
        )

    if diagnostics:
        status = CriticalPathStatus.UNSUPPORTED if unsupported else CriticalPathStatus.INCOMPLETE
        return CriticalPathAnalysis(
            status,
            scope_ids,
            activities,
            links,
            diagnostics=tuple(diagnostics),
        )

    topological = _topological_order(scope_ids, links)
    if len(topological) != len(scope_ids):
        raise AssertionError("Cycle diagnostics must prevent an incomplete topological order.")
    duration = {activity.work_item_id: activity.duration_days for activity in activities}
    assert all(value is not None for value in duration.values())
    predecessors: dict[UUID, list[UUID]] = {item_id: [] for item_id in scope_ids}
    successors: dict[UUID, list[UUID]] = {item_id: [] for item_id in scope_ids}
    for link in links:
        predecessors[link.successor_id].append(link.predecessor_id)
        successors[link.predecessor_id].append(link.successor_id)

    early_start: dict[UUID, int] = {}
    early_finish: dict[UUID, int] = {}
    for item_id in topological:
        early_start[item_id] = max(
            (early_finish[value] for value in predecessors[item_id]), default=0
        )
        activity_duration = duration[item_id]
        assert activity_duration is not None
        early_finish[item_id] = early_start[item_id] + activity_duration
    finish = max(early_finish.values())

    late_start: dict[UUID, int] = {}
    late_finish: dict[UUID, int] = {}
    for item_id in reversed(topological):
        late_finish[item_id] = min(
            (late_start[value] for value in successors[item_id]), default=finish
        )
        activity_duration = duration[item_id]
        assert activity_duration is not None
        late_start[item_id] = late_finish[item_id] - activity_duration

    calculated = tuple(
        replace(
            activity,
            early_start=early_start[activity.work_item_id],
            early_finish=early_finish[activity.work_item_id],
            late_start=late_start[activity.work_item_id],
            late_finish=late_finish[activity.work_item_id],
            total_float=late_start[activity.work_item_id] - early_start[activity.work_item_id],
            critical=late_start[activity.work_item_id] == early_start[activity.work_item_id],
        )
        for activity in activities
    )
    critical_nodes = tuple(activity.work_item_id for activity in calculated if activity.critical)
    critical_node_set = set(critical_nodes)
    calculated_links = tuple(
        replace(
            link,
            critical=(
                link.predecessor_id in critical_node_set
                and link.successor_id in critical_node_set
                and early_finish[link.predecessor_id] == early_start[link.successor_id]
            ),
        )
        for link in links
    )
    critical_relationship_set = {
        relationship_id
        for link in calculated_links
        if link.critical
        for relationship_id in link.relationship_ids
    }
    critical_relationships = tuple(
        relationship.id
        for relationship in plan.relationships
        if relationship.id in critical_relationship_set
    )
    return CriticalPathAnalysis(
        CriticalPathStatus.COMPLETE,
        scope_ids,
        calculated,
        calculated_links,
        origin=min(item.start for item in leaves if item.start is not None),
        finish_offset=finish,
        critical_node_ids=critical_nodes,
        critical_relationship_ids=critical_relationships,
    )
