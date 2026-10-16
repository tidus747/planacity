"""Immutable sprint lifecycle, assignment, and schedule diagnostics."""

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from planacity.domain import ProgramPlan, Sprint, SprintAssignment, WorkItemType


class SprintFindingKind(StrEnum):
    OVERLAP = "overlap"
    OUTSIDE_HORIZON = "outside_horizon"
    WORK_OUTSIDE_SPRINT = "work_outside_sprint"
    WORK_DATES_INCOMPLETE = "work_dates_incomplete"


@dataclass(frozen=True)
class SprintFinding:
    kind: SprintFindingKind
    sprint_id: UUID
    work_item_id: UUID | None = None
    other_sprint_id: UUID | None = None


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
