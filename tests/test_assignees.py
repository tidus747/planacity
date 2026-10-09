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
from planacity.planning.assignees import (
    effective_assignee_id,
    set_work_assignee,
    set_work_assignment,
    work_contributors,
)
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


def test_compact_assignment_supports_owner_only_and_explicit_zero_hours() -> None:
    plan = assignee_plan()
    task = plan.work_items[1]
    alex = plan.people[0]

    owner_only = set_work_assignment(plan, task.id, alex.id, None)
    assert owner_only.work_item(task.id).assignee_id == alex.id
    assert owner_only.allocations == ()

    allocated = set_work_assignment(owner_only, task.id, alex.id, Decimal(0))
    assert allocated.work_item(task.id).assignee_id == alex.id
    assert allocated.allocations[0].hours == 0


def test_compact_reassignment_preserves_allocation_id_hours_and_order() -> None:
    plan = assignee_plan()
    task = plan.work_items[1]
    alex, sam = plan.people
    allocation = Allocation(work_item_id=task.id, person_id=alex.id, hours=Decimal("7.25"))
    plan = replace(
        plan,
        work_items=(plan.work_items[0], replace(task, assignee_id=alex.id)),
        allocations=(allocation,),
    )

    changed = set_work_assignment(plan, task.id, sam.id, Decimal("7.25"))

    assert changed.work_item(task.id).assignee_id == sam.id
    assert changed.allocations == (replace(allocation, person_id=sam.id),)
    assert changed.allocations[0].id == allocation.id


def test_compact_blank_hours_and_unassignment_are_explicit_atomic_states() -> None:
    plan = assignee_plan()
    task = plan.work_items[1]
    alex = plan.people[0]
    allocation = Allocation(work_item_id=task.id, person_id=alex.id, hours=Decimal(8))
    plan = replace(
        plan,
        work_items=(plan.work_items[0], replace(task, assignee_id=alex.id)),
        allocations=(allocation,),
    )

    owner_only = set_work_assignment(plan, task.id, alex.id, None)
    assert owner_only.work_item(task.id).assignee_id == alex.id
    assert owner_only.allocations == ()

    unassigned = set_work_assignment(plan, task.id, None, None)
    assert unassigned.work_item(task.id).assignee_id is None
    assert unassigned.allocations == ()
    assert plan.allocations == (allocation,)


def test_compact_assignment_rejects_hours_without_person_containers_and_legacy_conflicts() -> None:
    plan = assignee_plan()
    epic, task = plan.work_items
    with pytest.raises(ValueError, match="Choose an assignee"):
        set_work_assignment(plan, task.id, None, Decimal(2))
    with pytest.raises(ValueError, match="feature owners"):
        set_work_assignment(plan, epic.id, plan.people[0].id, Decimal(2))

    child = WorkItem(title="Child", kind=WorkItemType.SUBTASK, parent_id=task.id)
    container = replace(plan, work_items=(*plan.work_items, child))
    with pytest.raises(ValueError, match="derived from their leaves"):
        set_work_assignment(container, task.id, plan.people[0].id, None)

    legacy = replace(
        plan,
        allocations=tuple(
            Allocation(work_item_id=task.id, person_id=person.id, hours=Decimal(4))
            for person in plan.people
        ),
    )
    with pytest.raises(ValueError, match="Resolve the multiple assignments"):
        set_work_assignment(legacy, task.id, plan.people[0].id, Decimal(8))


def test_epic_feature_owner_and_container_contributors_keep_capacity_separate() -> None:
    plan = assignee_plan()
    epic, task = plan.work_items
    alex, sam = plan.people
    first = Allocation(work_item_id=task.id, person_id=alex.id, hours=Decimal("0.1"))
    child = WorkItem(title="Test", kind=WorkItemType.SUBTASK, parent_id=task.id)
    second = Allocation(work_item_id=child.id, person_id=alex.id, hours=Decimal("0.2"))
    third = Allocation(work_item_id=child.id, person_id=sam.id, hours=Decimal("3"))
    plan = replace(
        plan,
        work_items=(epic, task, child),
        allocations=(first, second, third),
    )

    owned = set_work_assignment(plan, epic.id, sam.id, None)
    assert owned.allocations == plan.allocations
    contributors = work_contributors(owned, epic.id)
    assert [(entry.person_id, entry.hours) for entry in contributors] == [
        (alex.id, Decimal("0.3")),
        (sam.id, Decimal("3")),
    ]
