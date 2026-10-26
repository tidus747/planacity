"""Immutable sprint lifecycle, assignment, and schedule diagnostics."""

from dataclasses import dataclass, replace
from enum import StrEnum
from fractions import Fraction
from uuid import UUID

from planacity.domain import ProgramPlan, Sprint, SprintAssignment, WorkItemType
from planacity.planning.capacity import CapacityGapKind, calculate_dated_capacity
from planacity.planning.work_context import effective_group_ids


class SprintFindingKind(StrEnum):
    OVERLAP = "overlap"
    OUTSIDE_HORIZON = "outside_horizon"
    WORK_OUTSIDE_SPRINT = "work_outside_sprint"
    WORK_DATES_INCOMPLETE = "work_dates_incomplete"


class SprintLoadState(StrEnum):
    EMPTY_SCOPE = "empty_scope"
    UNKNOWN = "unknown"
    INCOMPLETE = "incomplete"
    OVERLOADED = "overloaded"
    NO_ASSIGNED_WORK = "no_assigned_work"
    WITHIN_CAPACITY = "within_capacity"


@dataclass(frozen=True)
class SprintFinding:
    kind: SprintFindingKind
    sprint_id: UUID
    work_item_id: UUID | None = None
    other_sprint_id: UUID | None = None


@dataclass(frozen=True)
class SprintLoad:
    """Exact sprint demand and scoped capacity from the canonical dated result."""

    sprint_id: UUID
    person_ids: tuple[UUID, ...]
    known_people: int
    planning_hours: Fraction
    sprint_hours: Fraction
    covered_hours: Fraction
    ordinary_hours: Fraction
    competing_hours: Fraction
    remaining_hours: Fraction
    unplaced_hours: Fraction
    work_without_allocation_ids: tuple[UUID, ...]
    outside_scope_person_ids: tuple[UUID, ...]
    allocation_ids: tuple[UUID, ...]
    state: SprintLoadState
    messages: tuple[str, ...]


def sprint(plan: ProgramPlan, sprint_id: UUID) -> Sprint:
    try:
        return next(value for value in plan.sprints if value.id == sprint_id)
    except StopIteration as error:
        raise ValueError(f"Sprint {sprint_id} does not exist in this plan.") from error


def add_sprint(plan: ProgramPlan, value: Sprint) -> ProgramPlan:
    return replace(plan, sprints=(*plan.sprints, value))


def update_sprint(plan: ProgramPlan, value: Sprint) -> ProgramPlan:
    sprint(plan, value.id)
    return replace(
        plan,
        sprints=tuple(value if current.id == value.id else current for current in plan.sprints),
    )


def remove_sprint(plan: ProgramPlan, sprint_id: UUID) -> ProgramPlan:
    sprint(plan, sprint_id)
    return replace(
        plan,
        sprints=tuple(value for value in plan.sprints if value.id != sprint_id),
        sprint_assignments=tuple(
            value for value in plan.sprint_assignments if value.sprint_id != sprint_id
        ),
    )


def assign_work_to_sprint(plan: ProgramPlan, sprint_id: UUID, work_item_id: UUID) -> ProgramPlan:
    sprint(plan, sprint_id)
    item = plan.work_item(work_item_id)
    if item.kind == WorkItemType.EPIC or plan.children(item.id):
        raise ValueError("Only executable leaf work can be assigned to a sprint.")
    current = next(
        (value for value in plan.sprint_assignments if value.work_item_id == work_item_id),
        None,
    )
    if current is not None and current.sprint_id == sprint_id:
        return plan
    assignment = (
        SprintAssignment(sprint_id=sprint_id, work_item_id=work_item_id)
        if current is None
        else replace(current, sprint_id=sprint_id)
    )
    return replace(
        plan,
        sprint_assignments=tuple(
            assignment if value.work_item_id == work_item_id else value
            for value in plan.sprint_assignments
        )
        if current is not None
        else (*plan.sprint_assignments, assignment),
    )


def unassign_work_from_sprint(plan: ProgramPlan, work_item_id: UUID) -> ProgramPlan:
    plan.work_item(work_item_id)
    if not any(value.work_item_id == work_item_id for value in plan.sprint_assignments):
        return plan
    return replace(
        plan,
        sprint_assignments=tuple(
            value for value in plan.sprint_assignments if value.work_item_id != work_item_id
        ),
    )


def sprint_findings(plan: ProgramPlan) -> tuple[SprintFinding, ...]:
    findings: list[SprintFinding] = []
    ordered = sorted(plan.sprints, key=lambda value: (value.period.start, str(value.id)))
    for index, value in enumerate(ordered):
        if value.period.start < plan.horizon.start or value.period.end > plan.horizon.end:
            findings.append(SprintFinding(SprintFindingKind.OUTSIDE_HORIZON, value.id))
        for other in ordered[index + 1 :]:
            if other.period.start > value.period.end:
                break
            findings.append(
                SprintFinding(
                    SprintFindingKind.OVERLAP,
                    value.id,
                    other_sprint_id=other.id,
                )
            )
    sprints = {value.id: value for value in plan.sprints}
    for assignment in plan.sprint_assignments:
        item = plan.work_item(assignment.work_item_id)
        if item.start is None or item.end is None:
            findings.append(
                SprintFinding(
                    SprintFindingKind.WORK_DATES_INCOMPLETE,
                    assignment.sprint_id,
                    work_item_id=item.id,
                )
            )
        elif (
            item.start < sprints[assignment.sprint_id].period.start
            or item.end > sprints[assignment.sprint_id].period.end
        ):
            findings.append(
                SprintFinding(
                    SprintFindingKind.WORK_OUTSIDE_SPRINT,
                    assignment.sprint_id,
                    work_item_id=item.id,
                )
            )
    return tuple(findings)


def _sprint_people(plan: ProgramPlan, value: Sprint) -> tuple[UUID, ...]:
    if value.work_group_id is None:
        return tuple(person.id for person in plan.people)
    associated = {
        allocation.person_id
        for allocation in plan.allocations
        if allocation.hours > 0
        and value.work_group_id in effective_group_ids(plan, allocation.work_item_id)
    }
    return tuple(person.id for person in plan.people if person.id in associated)


def calculate_sprint_load(plan: ProgramPlan, value: Sprint) -> SprintLoad:
    """Compare one sprint's explicit work with all demand competing for its scope."""
    value = sprint(plan, value.id)
    capacity = calculate_dated_capacity(plan, value.period)
    person_ids = _sprint_people(plan, value)
    person_set = set(person_ids)
    assigned_work_ids = {
        assignment.work_item_id
        for assignment in plan.sprint_assignments
        if assignment.sprint_id == value.id
    }
    allocations = tuple(
        allocation
        for allocation in plan.allocations
        if allocation.work_item_id in assigned_work_ids and allocation.hours > 0
    )
    allocation_ids = {allocation.id for allocation in allocations}
    allocated_work_ids = {allocation.work_item_id for allocation in allocations}
    work_without_allocation_ids = tuple(
        item.id for item in plan.work_items if item.id in assigned_work_ids - allocated_work_ids
    )
    outside_scope_person_ids = tuple(
        person.id
        for person in plan.people
        if person.id in {allocation.person_id for allocation in allocations} - person_set
    )

    planning = Fraction()
    remaining = Fraction()
    sprint_hours = Fraction()
    covered = Fraction()
    ordinary = Fraction()
    competing = Fraction()
    known_people = 0
    overloaded = False
    for person in capacity.people:
        entries = tuple(
            entry for entry in person.allocation_breakdown if entry.allocation_id in allocation_ids
        )
        sprint_hours += sum((entry.hours for entry in entries), Fraction())
        covered += sum((entry.covered_hours for entry in entries), Fraction())
        ordinary += sum((entry.excess_hours for entry in entries), Fraction())
        if person.person_id not in person_set or not person.capacity_known:
            continue
        known_people += 1
        assert (
            person.planning_hours is not None
            and person.remaining_hours is not None
            and person.excess_hours is not None
        )
        planning += person.planning_hours
        remaining += person.remaining_hours
        competing += person.excess_hours - sum(
            (entry.excess_hours for entry in entries), Fraction()
        )
        overloaded = overloaded or any(day.remaining_hours < 0 for day in person.days)

    unplaced_kinds = {
        CapacityGapKind.MISSING_CALENDAR,
        CapacityGapKind.MISSING_WORK_DATES,
        CapacityGapKind.NO_PLANNING_CAPACITY,
    }
    unplaced = sum(
        (
            gap.hours
            for gap in capacity.all_gaps
            if gap.source_id in allocation_ids
            and gap.kind in unplaced_kinds
            and gap.hours is not None
        ),
        Fraction(),
    )
    messages: list[str] = []
    if not person_ids:
        messages.append("No people have positive whole-plan allocations in this sprint scope.")
    capacity_people = {person.person_id: person for person in capacity.people}
    unknown = (
        ()
        if capacity.gaps
        else tuple(
            plan.person(person_id).name
            for person_id in person_ids
            if person_id not in capacity_people or capacity_people[person_id].calendar_id is None
        )
    )
    if unknown:
        messages.append(f"Missing work calendars: {', '.join(unknown)}.")
    if work_without_allocation_ids:
        messages.append(
            f"{len(work_without_allocation_ids)} assigned work item(s) have no positive "
            "allocation hours."
        )
    if outside_scope_person_ids:
        messages.append(
            f"{len(outside_scope_person_ids)} assigned person(s) are outside the derived "
            "WorkGroup scope."
        )
    if unplaced:
        messages.append(f"{unplaced} h of sprint allocation demand could not be placed.")
    if capacity.gaps:
        messages.extend(gap.message for gap in capacity.gaps)

    incomplete = bool(
        unknown
        or work_without_allocation_ids
        or outside_scope_person_ids
        or unplaced
        or capacity.gaps
    )
    if not person_ids:
        state = SprintLoadState.EMPTY_SCOPE
    elif known_people == 0:
        state = SprintLoadState.UNKNOWN
    elif incomplete:
        state = SprintLoadState.INCOMPLETE
    elif overloaded:
        state = SprintLoadState.OVERLOADED
    elif not assigned_work_ids:
        state = SprintLoadState.NO_ASSIGNED_WORK
    else:
        state = SprintLoadState.WITHIN_CAPACITY
    return SprintLoad(
        value.id,
        person_ids,
        known_people,
        planning,
        sprint_hours,
        covered,
        ordinary,
        competing,
        remaining,
        unplaced,
        work_without_allocation_ids,
        outside_scope_person_ids,
        tuple(sorted(allocation_ids, key=str)),
        state,
        tuple(dict.fromkeys(messages)),
    )


def calculate_sprint_loads(plan: ProgramPlan) -> tuple[SprintLoad, ...]:
    """Return deterministic sprint load rows in Calendar order."""
    ordered = sorted(
        plan.sprints,
        key=lambda value: (
            value.period.start,
            value.period.end,
            value.name.casefold(),
            str(value.id),
        ),
    )
    return tuple(calculate_sprint_load(plan, value) for value in ordered)
