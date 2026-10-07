"""Single-person leaf transitions preserve legacy assignments explicitly."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from planacity.domain import (
    Allocation,
    Person,
    PlanningHorizon,
    ProgramPlan,
    WorkItem,
    WorkItemType,
)
from planacity.persistence.codec import dumps, loads
from planacity.planning.allocation_settings import (
    add_allocation,
    remove_allocation,
    update_allocation,
)
from planacity.planning.assignment_policy import assignment_policy_conflicts
from planacity.planning.findings import FindingRule, planning_findings
from planacity.planning.work_items import resolve_container_effort


def assignment_plan() -> ProgramPlan:
    first = Person(name="Alex")
    second = Person(name="Sam")
    third = Person(name="Robin")
    task = WorkItem(title="Integration", kind=WorkItemType.TASK, estimate_hours=Decimal(8))
    other = WorkItem(title="Review", kind=WorkItemType.TASK, estimate_hours=Decimal(2))
    return ProgramPlan(
        name="Assignment policy",
        horizon=PlanningHorizon(date(2026, 10, 1), date(2026, 10, 31)),
        work_items=(task, other),
        people=(first, second, third),
    )


def test_new_leaf_accepts_zero_or_one_allocation_and_rejects_a_second_person() -> None:
    plan = assignment_plan()
    first = Allocation(
        work_item_id=plan.work_items[0].id,
        person_id=plan.people[0].id,
        hours=Decimal(0),
    )
    assigned = add_allocation(plan, first)

    assert assigned.allocations == (first,)
    second = Allocation(
        work_item_id=first.work_item_id,
        person_id=plan.people[1].id,
        hours=Decimal(8),
    )
    with pytest.raises(ValueError, match="at most one allocation"):
        add_allocation(assigned, second)
    assert assigned.allocations == (first,)


def test_one_assignment_can_be_reassigned_or_unassigned_without_changing_effort() -> None:
    plan = assignment_plan()
    entry = Allocation(
        work_item_id=plan.work_items[0].id,
        person_id=plan.people[0].id,
        hours=Decimal("7.25"),
    )
    assigned = add_allocation(plan, entry)
    reassigned = update_allocation(assigned, replace(entry, person_id=plan.people[1].id))

    assert reassigned.allocations[0].id == entry.id
    assert reassigned.allocations[0].person_id == plan.people[1].id
    assert reassigned.allocations[0].hours == Decimal("7.25")
    assert remove_allocation(reassigned, entry.id).allocations == ()


def test_moving_an_allocation_cannot_create_a_second_assignment_on_the_target() -> None:
    plan = assignment_plan()
    first = Allocation(
        work_item_id=plan.work_items[0].id,
        person_id=plan.people[0].id,
        hours=Decimal(8),
    )
    second = Allocation(
        work_item_id=plan.work_items[1].id,
        person_id=plan.people[1].id,
        hours=Decimal(2),
    )
    assigned = replace(plan, allocations=(first, second))

    with pytest.raises(ValueError, match="at most one allocation"):
        update_allocation(assigned, replace(first, work_item_id=second.work_item_id))


def test_legacy_multiple_assignments_remain_editable_and_incrementally_repairable() -> None:
    plan = assignment_plan()
    first = Allocation(
        work_item_id=plan.work_items[0].id,
        person_id=plan.people[0].id,
        hours=Decimal(5),
    )
    second = Allocation(
        work_item_id=plan.work_items[0].id,
        person_id=plan.people[1].id,
        hours=Decimal(3),
    )
    legacy = replace(plan, allocations=(first, second))

    edited = update_allocation(legacy, replace(first, hours=Decimal("5.5")))
    assert edited.allocations == (replace(first, hours=Decimal("5.5")), second)
    with pytest.raises(ValueError, match="at most one allocation"):
        add_allocation(
            legacy,
            Allocation(
                work_item_id=first.work_item_id,
                person_id=plan.people[2].id,
                hours=Decimal(1),
            ),
        )
    repaired = remove_allocation(edited, second.id)
    assert assignment_policy_conflicts(repaired) == ()


def test_legacy_conflict_is_deterministic_and_survives_save_reopen() -> None:
    plan = assignment_plan()
    entries = tuple(
        Allocation(
            work_item_id=plan.work_items[0].id,
            person_id=person.id,
            hours=hours,
        )
        for person, hours in zip(plan.people[:2], (Decimal(8), Decimal(0)), strict=True)
    )
    legacy = replace(plan, allocations=tuple(reversed(entries)))

    conflict = assignment_policy_conflicts(legacy)[0]
    assert conflict.work_item_id == plan.work_items[0].id
    assert conflict.allocation_ids == tuple(sorted((entry.id for entry in entries), key=str))
    assert conflict.person_ids == tuple(sorted((person.id for person in plan.people[:2]), key=str))
    assert loads(dumps(legacy)) == legacy

    finding = next(
        value
        for value in planning_findings(legacy)
        if value.rule_key == FindingRule.UNRESOLVED_ASSIGNMENT
    )
    assert finding.work_item_ids == (plan.work_items[0].id,)
    assert finding.person_ids == conflict.person_ids
    assert finding.source_ids == conflict.allocation_ids
    assert "Every stored allocation and hour still counts" in finding.explanation


def test_legacy_container_transfer_preserves_every_allocation_and_surfaces_conflict() -> None:
    plan = assignment_plan()
    parent = WorkItem(title="Program", kind=WorkItemType.EPIC, estimate_hours=Decimal(8))
    child = replace(plan.work_items[0], parent_id=parent.id)
    entries = tuple(
        Allocation(work_item_id=parent.id, person_id=person.id, hours=Decimal(4))
        for person in plan.people[:2]
    )
    legacy = replace(plan, work_items=(parent, child, plan.work_items[1]), allocations=entries)

    resolved = resolve_container_effort(legacy, parent.id, "Program coordination")
    leaf = resolved.work_items[-1]

    assert tuple(allocation.id for allocation in resolved.allocations) == tuple(
        allocation.id for allocation in entries
    )
    assert tuple(allocation.hours for allocation in resolved.allocations) == (Decimal(4),) * 2
    assert {allocation.work_item_id for allocation in resolved.allocations} == {leaf.id}
    assert assignment_policy_conflicts(resolved)[0].work_item_id == leaf.id
