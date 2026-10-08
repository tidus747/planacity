"""Canonical work ownership stays explicit and separate from capacity hours."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from planacity.domain import (
    Allocation,
    Person,
    PlanningHorizon,
    ProgramPlan,
    WorkItem,
    WorkItemType,
)
from planacity.planning.assignees import effective_assignee_id, set_work_assignee
from planacity.planning.people import remove_person


def assignee_plan() -> ProgramPlan:
    alex, sam = Person(name="Alex"), Person(name="Sam")
    epic = WorkItem(title="Release", kind=WorkItemType.EPIC)
    task = WorkItem(
        title="Integration",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        estimate_hours=Decimal(8),
    )
    return ProgramPlan(
        name="Ownership",
        horizon=PlanningHorizon(date(2026, 10, 1), date(2026, 10, 31)),
        people=(alex, sam),
        work_items=(epic, task),
    )


def test_epic_feature_owner_does_not_create_capacity_demand() -> None:
    plan = assignee_plan()

    changed = set_work_assignee(plan, plan.work_items[0].id, plan.people[0].id)

    assert changed.work_items[0].assignee_id == plan.people[0].id
    assert changed.allocations == ()


def test_leaf_reassignment_preserves_the_single_allocation_identity_and_hours() -> None:
    plan = assignee_plan()
    allocation = Allocation(
        work_item_id=plan.work_items[1].id,
        person_id=plan.people[0].id,
        hours=Decimal("7.25"),
    )
    plan = replace(
        plan,
        work_items=(plan.work_items[0], replace(plan.work_items[1], assignee_id=plan.people[0].id)),
        allocations=(allocation,),
    )

    changed = set_work_assignee(plan, plan.work_items[1].id, plan.people[1].id)

    assert changed.work_items[1].assignee_id == plan.people[1].id
    assert changed.allocations[0] == replace(allocation, person_id=plan.people[1].id)
    assert changed.allocations[0].id == allocation.id
    assert changed.allocations[0].hours == Decimal("7.25")


def test_clearing_owner_never_silently_deletes_capacity() -> None:
    plan = assignee_plan()
    allocation = Allocation(
        work_item_id=plan.work_items[1].id,
        person_id=plan.people[0].id,
        hours=Decimal(8),
    )
    plan = replace(
        plan,
        work_items=(plan.work_items[0], replace(plan.work_items[1], assignee_id=plan.people[0].id)),
        allocations=(allocation,),
    )

    with pytest.raises(ValueError, match="Remove the Allocation.*explicitly"):
        set_work_assignee(plan, plan.work_items[1].id, None)

    assert plan.work_items[1].assignee_id == plan.people[0].id
    assert plan.allocations == (allocation,)


def test_legacy_single_allocation_is_a_read_only_fallback_until_ownership_is_saved() -> None:
    plan = assignee_plan()
    allocation = Allocation(
        work_item_id=plan.work_items[1].id,
        person_id=plan.people[0].id,
        hours=Decimal(8),
    )
    legacy = replace(plan, allocations=(allocation,))

    assert legacy.work_items[1].assignee_id is None
    assert effective_assignee_id(legacy, legacy.work_items[1].id) == plan.people[0].id
    assert effective_assignee_id(legacy, legacy.work_items[0].id) is None


def test_legacy_multiple_assignments_require_explicit_resolution() -> None:
    plan = assignee_plan()
    allocations = tuple(
        Allocation(
            work_item_id=plan.work_items[1].id,
            person_id=person.id,
            hours=Decimal(4),
        )
        for person in plan.people
    )
    legacy = replace(plan, allocations=allocations)

    assert effective_assignee_id(legacy, plan.work_items[1].id) is None
    with pytest.raises(ValueError, match="Resolve the multiple assignments"):
        set_work_assignee(legacy, plan.work_items[1].id, plan.people[0].id)


def test_assignee_must_belong_to_the_roster_and_deletion_needs_explicit_consent() -> None:
    plan = assignee_plan()
    assigned = set_work_assignee(plan, plan.work_items[1].id, plan.people[0].id)

    with pytest.raises(ValueError, match="does not exist"):
        set_work_assignee(plan, plan.work_items[1].id, uuid4())
    with pytest.raises(ValueError, match="assignee references"):
        remove_person(assigned, plan.people[0].id)

    removed = remove_person(assigned, plan.people[0].id, clear_assignees=True)
    assert removed.people == (plan.people[1],)
    assert removed.work_items[1].assignee_id is None


def test_program_plan_rejects_a_dangling_assignee_reference() -> None:
    plan = assignee_plan()
    dangling = replace(plan.work_items[1], assignee_id=uuid4())

    with pytest.raises(ValueError, match="must reference an existing roster person"):
        replace(plan, work_items=(plan.work_items[0], dangling))
