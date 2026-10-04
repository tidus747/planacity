"""Pure dependency findings and edit guards over immutable Program Plans."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from planacity.domain import ProgramPlan, Relationship, RelationshipType


class DependencyFindingKind(StrEnum):
    CONFLICT = "conflict"
    UNEVALUATED = "unevaluated"
    CYCLE = "cycle"


@dataclass(frozen=True)
class DependencyEdge:
    """One relationship normalized to predecessor -> successor direction."""

    relationship_id: UUID
    predecessor_id: UUID
    successor_id: UUID


@dataclass(frozen=True)
class DependencyFinding:
    """A calculated dependency problem; findings are never persisted."""

    kind: DependencyFindingKind
    edge: DependencyEdge
    message: str
    conflict_days: int | None = None


class DependencyValidationError(ValueError):
    """A proposed edit would introduce or worsen dependency invalidity."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        self.problems = problems
        super().__init__("Dependency constraint rejected this change:\n- " + "\n- ".join(problems))


def normalize_dependency(relationship: Relationship) -> DependencyEdge | None:
    """Normalize depends_on and blocks while ignoring non-scheduling links."""
    if relationship.kind == RelationshipType.RELATED_TO:
        return None
    predecessor, successor = (
        (relationship.target_id, relationship.source_id)
        if relationship.kind == RelationshipType.DEPENDS_ON
        else (relationship.source_id, relationship.target_id)
    )
    return DependencyEdge(relationship.id, predecessor, successor)


def dependency_edges(plan: ProgramPlan) -> tuple[DependencyEdge, ...]:
    return tuple(
        edge
        for relationship in plan.relationships
        if (edge := normalize_dependency(relationship)) is not None
    )


def dependency_conflict_days(plan: ProgramPlan, edge: DependencyEdge) -> int | None:
    """Return inclusive overlap magnitude, or None when an endpoint date is missing."""
    predecessor = plan.work_item(edge.predecessor_id)
    successor = plan.work_item(edge.successor_id)
    if predecessor.end is None or successor.start is None:
        return None
    return max(0, (predecessor.end - successor.start).days + 1)


def dependency_cycle_relationship_ids(plan: ProgramPlan) -> frozenset[UUID]:
    """Return every dependency relationship participating in a directed cycle."""
    edges = dependency_edges(plan)
    adjacency: dict[UUID, set[UUID]] = {}
    for edge in edges:
        adjacency.setdefault(edge.predecessor_id, set()).add(edge.successor_id)

    def reaches(start: UUID, target: UUID) -> bool:
        pending = [start]
        visited: set[UUID] = set()
        while pending:
            node = pending.pop()
            if node == target:
                return True
            if node not in visited:
                visited.add(node)
                pending.extend(adjacency.get(node, ()))
        return False

    return frozenset(
        edge.relationship_id for edge in edges if reaches(edge.successor_id, edge.predecessor_id)
    )


def _conflict_message(plan: ProgramPlan, edge: DependencyEdge, days: int) -> str:
    predecessor = plan.work_item(edge.predecessor_id)
    successor = plan.work_item(edge.successor_id)
    assert predecessor.end is not None and successor.start is not None
    boundaries = []
    try:
        boundaries.append(
            f'"{predecessor.title}" must end on or before '
            f"{(successor.start - timedelta(days=1)).isoformat()}"
        )
    except OverflowError:
        pass
    try:
        boundaries.append(
            f'"{successor.title}" must start on or after '
            f"{(predecessor.end + timedelta(days=1)).isoformat()}"
        )
    except OverflowError:
        pass
    boundary_text = ", or ".join(boundaries) or "the predecessor must end before the successor"
    unit = "day" if days == 1 else "days"
    return (
        f'"{predecessor.title}" ends {predecessor.end.isoformat()} and '
        f'"{successor.title}" starts {successor.start.isoformat()} '
        f"({days} conflicting calendar {unit}). Permitted boundary: {boundary_text}."
    )


def dependency_findings(plan: ProgramPlan) -> tuple[DependencyFinding, ...]:
    """Calculate cycles, incomplete constraints, and fully dated conflicts."""
    cycle_ids = dependency_cycle_relationship_ids(plan)
    findings: list[DependencyFinding] = []
    for edge in dependency_edges(plan):
        predecessor = plan.work_item(edge.predecessor_id)
        successor = plan.work_item(edge.successor_id)
        if edge.relationship_id in cycle_ids:
            findings.append(
                DependencyFinding(
                    DependencyFindingKind.CYCLE,
                    edge,
                    f'Dependency cycle includes "{predecessor.title}" -> "{successor.title}".',
                )
            )
        days = dependency_conflict_days(plan, edge)
        if days is None:
            missing = []
            if predecessor.end is None:
                missing.append(f'"{predecessor.title}" end')
            if successor.start is None:
                missing.append(f'"{successor.title}" start')
            findings.append(
                DependencyFinding(
                    DependencyFindingKind.UNEVALUATED,
                    edge,
                    "Dependency unevaluated; set " + " and ".join(missing) + ".",
                )
            )
        elif days:
            findings.append(
                DependencyFinding(
                    DependencyFindingKind.CONFLICT,
                    edge,
                    _conflict_message(plan, edge, days),
                    days,
                )
            )
    return tuple(findings)


def validate_dependency_change(
    original: ProgramPlan,
    candidate: ProgramPlan,
    *,
    affected_item_ids: tuple[UUID, ...] = (),
    added_relationship_ids: tuple[UUID, ...] = (),
) -> None:
    """Reject only new cycles and new or worsened conflicts on affected edges.

    Existing conflicts elsewhere are deliberately ignored. Clearing a required
    date changes an edge to unevaluated and is allowed so legacy plans remain
    repairable.
    """
    original_edges = {edge.relationship_id: edge for edge in dependency_edges(original)}
    candidate_edges = {edge.relationship_id: edge for edge in dependency_edges(candidate)}
    relevant = set(added_relationship_ids)
    affected = set(affected_item_ids)
    relevant.update(
        edge.relationship_id
        for edge in candidate_edges.values()
        if affected.intersection((edge.predecessor_id, edge.successor_id))
    )

    problems: list[str] = []
    new_cycles = dependency_cycle_relationship_ids(candidate) - dependency_cycle_relationship_ids(
        original
    )
    for relationship_id in sorted(new_cycles, key=str):
        edge = candidate_edges[relationship_id]
        predecessor = candidate.work_item(edge.predecessor_id)
        successor = candidate.work_item(edge.successor_id)
        problems.append(f'New dependency cycle: "{predecessor.title}" -> "{successor.title}".')

    for relationship_id in sorted(relevant, key=str):
        candidate_edge = candidate_edges.get(relationship_id)
        if candidate_edge is None:
            continue
        candidate_days = dependency_conflict_days(candidate, candidate_edge)
        original_edge = original_edges.get(relationship_id)
        original_days = (
            dependency_conflict_days(original, original_edge) if original_edge is not None else None
        )
        if candidate_days is not None and candidate_days > (original_days or 0):
            problems.append(_conflict_message(candidate, candidate_edge, candidate_days))

    if problems:
        raise DependencyValidationError(tuple(problems))
