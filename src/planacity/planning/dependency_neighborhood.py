"""Bounded selected-work dependency neighbourhoods without Qt."""

from dataclasses import dataclass
from uuid import UUID

from planacity.domain import ProgramPlan, WorkItem, WorkItemType
from planacity.planning.assignees import effective_assignee_id, work_contributors
from planacity.planning.dependency_validation import (
    DependencyFindingKind,
    dependency_edges,
    dependency_findings,
)
from planacity.planning.findings import findings_for_work, planning_findings

MAX_GRAPH_CARDS = 30


@dataclass(frozen=True)
class DependencyGraphCard:
    """Display-ready work information for one graph node."""

    item_id: UUID
    title: str
    kind: WorkItemType
    dates: str
    assignment: str
    warnings: tuple[str, ...]
    visible_in_timeline: bool


@dataclass(frozen=True)
class DependencyNeighborhood:
    """Immediate dependency context around one selected work item."""

    selected: DependencyGraphCard
    predecessors: tuple[DependencyGraphCard, ...]
    successors: tuple[DependencyGraphCard, ...]
    omitted_predecessors: tuple[DependencyGraphCard, ...] = ()
    omitted_successors: tuple[DependencyGraphCard, ...] = ()
    cycle_edges: int = 0
    conflict_edges: int = 0
    unevaluated_edges: int = 0

    @property
    def displayed_cards(self) -> int:
        return 1 + len(self.predecessors) + len(self.successors)


def _date_text(item: WorkItem) -> str:
    if item.start is not None and item.end is not None:
        return f"{item.start.isoformat()} to {item.end.isoformat()}"
    if item.start is not None:
        return f"Starts {item.start.isoformat()}; no end"
    if item.end is not None:
        return f"Ends {item.end.isoformat()}; no start"
    return "Unscheduled"


def _person_names(plan: ProgramPlan, person_ids: tuple[UUID, ...]) -> str:
    return ", ".join(plan.person(person_id).name for person_id in person_ids)


def _assignment_text(plan: ProgramPlan, item: WorkItem) -> str:
    children = plan.children(item.id)
    if children:
        parts = []
        if item.kind == WorkItemType.EPIC and item.assignee_id is not None:
            parts.append(f"Feature owner: {plan.person(item.assignee_id).name}")
        contributors = work_contributors(plan, item.id)
        if contributors:
            parts.append(
                "Aggregate team: "
                + _person_names(plan, tuple(value.person_id for value in contributors))
            )
        else:
            parts.append("Aggregate team: none")
        return " | ".join(parts)
    if item.kind == WorkItemType.EPIC and item.assignee_id is not None:
        return f"Feature owner: {plan.person(item.assignee_id).name}"

    direct_people = tuple(
        person.id
        for person in plan.people
        if any(
            entry.work_item_id == item.id and entry.person_id == person.id
            for entry in plan.allocations
        )
    )
    if len(direct_people) > 1:
        return "Legacy assignments: " + _person_names(plan, direct_people)
    assignee_id = effective_assignee_id(plan, item.id)
    if assignee_id is not None:
        return f"Assigned: {plan.person(assignee_id).name}"
    return "Unassigned"


def _split_limit(
    predecessors: tuple[UUID, ...], successors: tuple[UUID, ...], slots: int
) -> tuple[int, int]:
    predecessor_limit = min(len(predecessors), (slots + 1) // 2)
    successor_limit = min(len(successors), slots // 2)
    remaining = slots - predecessor_limit - successor_limit
    if remaining:
        predecessor_extra = min(remaining, len(predecessors) - predecessor_limit)
        predecessor_limit += predecessor_extra
        remaining -= predecessor_extra
    if remaining:
        successor_limit += min(remaining, len(successors) - successor_limit)
    return predecessor_limit, successor_limit


def project_dependency_neighborhood(
    plan: ProgramPlan,
    selected_id: UUID,
    *,
    visible_ids: frozenset[UUID] | None = None,
    max_cards: int = MAX_GRAPH_CARDS,
) -> DependencyNeighborhood:
    """Project immediate normalized links while retaining bounded omitted lists."""
    if max_cards < 1:
        raise ValueError("A dependency neighbourhood requires at least one card.")
    plan.work_item(selected_id)
    visible = (
        visible_ids if visible_ids is not None else frozenset(item.id for item in plan.work_items)
    )
    edges = dependency_edges(plan)

    predecessor_set = {edge.predecessor_id for edge in edges if edge.successor_id == selected_id}
    successor_set = {edge.successor_id for edge in edges if edge.predecessor_id == selected_id}
    predecessors = tuple(item.id for item in plan.work_items if item.id in predecessor_set)
    successors = tuple(item.id for item in plan.work_items if item.id in successor_set)
    predecessor_limit, successor_limit = _split_limit(predecessors, successors, max_cards - 1)

    dependency_problems = dependency_findings(plan)
    planning_problems = planning_findings(plan)

    def card(item_id: UUID) -> DependencyGraphCard:
        item = plan.work_item(item_id)
        messages = [
            finding.title for finding in findings_for_work(plan, planning_problems, item_id)
        ]
        messages.extend(
            finding.message
            for finding in dependency_problems
            if item_id in (finding.edge.predecessor_id, finding.edge.successor_id)
        )
        return DependencyGraphCard(
            item_id=item.id,
            title=item.title,
            kind=item.kind,
            dates=_date_text(item),
            assignment=_assignment_text(plan, item),
            warnings=tuple(dict.fromkeys(messages)),
            visible_in_timeline=item.id in visible,
        )

    relevant_edge_ids = {
        edge.relationship_id
        for edge in edges
        if selected_id in (edge.predecessor_id, edge.successor_id)
    }
    relevant_findings = tuple(
        finding
        for finding in dependency_problems
        if finding.edge.relationship_id in relevant_edge_ids
    )
    return DependencyNeighborhood(
        selected=card(selected_id),
        predecessors=tuple(card(value) for value in predecessors[:predecessor_limit]),
        successors=tuple(card(value) for value in successors[:successor_limit]),
        omitted_predecessors=tuple(card(value) for value in predecessors[predecessor_limit:]),
        omitted_successors=tuple(card(value) for value in successors[successor_limit:]),
        cycle_edges=sum(
            finding.kind == DependencyFindingKind.CYCLE for finding in relevant_findings
        ),
        conflict_edges=sum(
            finding.kind == DependencyFindingKind.CONFLICT for finding in relevant_findings
        ),
        unevaluated_edges=sum(
            finding.kind == DependencyFindingKind.UNEVALUATED for finding in relevant_findings
        ),
    )
