"""Preview explicit consolidation of legacy multi-person leaf assignments."""

from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID

from planacity.domain import ProgramPlan
from planacity.planning.allocations import sum_hours_exact, summarize_allocations
from planacity.planning.assignment_policy import (
    assignment_policy_conflicts,
    validate_assignment_transition,
)
from planacity.planning.findings import PlanningFinding, planning_findings


@dataclass(frozen=True)
class PersonLoadChange:
    person_id: UUID
    before_hours: Decimal
    after_hours: Decimal

    @property
    def delta_hours(self) -> Decimal:
        return sum_hours_exact((self.after_hours, self.before_hours.copy_negate()))


@dataclass(frozen=True)
class AssignmentConsolidationPreview:
    work_item_id: UUID
    surviving_allocation_id: UUID
    removed_allocation_ids: tuple[UUID, ...]
    total_hours: Decimal
    person_loads: tuple[PersonLoadChange, ...]
    before_findings: tuple[PlanningFinding, ...]
    after_findings: tuple[PlanningFinding, ...]
    candidate: ProgramPlan


def _relevant_findings(
    findings: tuple[PlanningFinding, ...], work_item_id: UUID, person_ids: set[UUID]
) -> tuple[PlanningFinding, ...]:
    return tuple(
        finding
        for finding in findings
        if work_item_id in finding.work_item_ids or person_ids.intersection(finding.person_ids)
    )


def preview_assignment_consolidation(
    plan: ProgramPlan, work_item_id: UUID, surviving_allocation_id: UUID
) -> AssignmentConsolidationPreview:
    """Build one complete consolidation candidate without modifying the source plan."""
    item = plan.work_item(work_item_id)
    if plan.children(work_item_id):
        raise ValueError(f"'{item.title}' is a container. Resolve its direct effort first.")

    conflict = next(
        (
            value
            for value in assignment_policy_conflicts(plan)
            if value.work_item_id == work_item_id
        ),
        None,
    )
    if conflict is None:
        raise ValueError(f"'{item.title}' does not have multiple assignments to consolidate.")

    direct = tuple(
        allocation for allocation in plan.allocations if allocation.work_item_id == work_item_id
    )
    survivor = next(
        (allocation for allocation in direct if allocation.id == surviving_allocation_id), None
    )
    if survivor is None:
        raise ValueError("Choose one of this leaf's existing allocations as the survivor.")

    total = sum_hours_exact(tuple(allocation.hours for allocation in direct))
    removed = tuple(
        sorted((allocation.id for allocation in direct if allocation.id != survivor.id), key=str)
    )
    assigned_item = replace(item, assignee_id=survivor.person_id)
    candidate = replace(
        plan,
        work_items=tuple(
            assigned_item if current.id == item.id else current for current in plan.work_items
        ),
        allocations=tuple(
            replace(allocation, hours=total) if allocation.id == survivor.id else allocation
            for allocation in plan.allocations
            if allocation.work_item_id != work_item_id or allocation.id == survivor.id
        ),
    )
    validate_assignment_transition(plan, candidate)

    before_summary = {
        value.person_id: value.allocated_hours
        for value in summarize_allocations(plan, plan.allocations).people
    }
    after_summary = {
        value.person_id: value.allocated_hours
        for value in summarize_allocations(candidate, candidate.allocations).people
    }
    affected_people = {allocation.person_id for allocation in direct}
    loads = tuple(
        PersonLoadChange(person.id, before_summary[person.id], after_summary[person.id])
        for person in plan.people
        if person.id in affected_people
    )
    before_findings = planning_findings(plan)
    after_findings = planning_findings(candidate)
    return AssignmentConsolidationPreview(
        work_item_id=work_item_id,
        surviving_allocation_id=survivor.id,
        removed_allocation_ids=removed,
        total_hours=total,
        person_loads=loads,
        before_findings=_relevant_findings(before_findings, work_item_id, affected_people),
        after_findings=_relevant_findings(after_findings, work_item_id, affected_people),
        candidate=candidate,
    )
